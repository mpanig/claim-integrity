"""One adapter per AI engine, all through official APIs.

Each adapter takes the final prompt text and returns the raw answer plus everything
needed to interpret it: the exact model version the API reports, citations, tokens,
latency, whether web search was on, and how the region was applied:

  location_mode "api"          region passed through the API's user-location option
  location_mode "prompt-only"  the API has no such option here; the prompt states the region
  location_mode "none"         no region requested

APIs are stateless: no account memory or personalisation like the consumer apps.
Endpoints and model names change; both are configurable (env vars below, models per plan).
"""

import os
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

FALLBACK_BETA = "server-side-fallback-2026-07-01"


class EngineError(Exception):
    pass


@dataclass
class Location:
    country: str  # ISO 3166-1 alpha-2, e.g. "US", "IN"
    city: str | None = None
    region: str | None = None


@dataclass
class EngineAnswer:
    text: str
    model_version: str | None
    citations: list[dict[str, str]] = field(default_factory=list)  # {"url", "title"}
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: int = 0
    search_used: bool = False
    location_mode: str = "none"
    searches: int = 0  # web searches billed, where the API reports them


@dataclass(frozen=True)
class Price:
    """Approximate list prices in USD; check the provider's pricing page before relying on them."""

    input_per_mtok: float
    output_per_mtok: float
    per_search: float = 0.0


class Engine:
    name = ""
    label = ""
    env_key = ""
    default_models: tuple[str, ...] = ()
    search_toggle = True  # False: the engine always searches (Perplexity Sonar)
    location_in_api = False  # True when the API accepts a user location with web search
    prices: dict[str, Price] = {}
    default_price = Price(5.0, 15.0, 0.02)
    timeout = 120.0

    def key(self, env: dict[str, str]) -> str | None:
        return env.get(self.env_key) or None

    def status(self, env: dict[str, str]) -> str:
        return "live" if self.key(env) else "key missing"

    def location_mode(self, search: bool, loc: Location | None) -> str:
        if loc is None:
            return "none"
        return "api" if (self.location_in_api and search) else "prompt-only"

    def price(self, model: str) -> Price:
        return self.prices.get(model, self.default_price)

    def cost(self, model: str, a: EngineAnswer) -> float:
        p = self.price(model)
        searches = a.searches if a.searches else (1 if a.search_used else 0)
        return round(a.input_tokens / 1e6 * p.input_per_mtok + a.output_tokens / 1e6 * p.output_per_mtok + searches * p.per_search, 6)

    def ask(self, prompt: str, *, model: str, search: bool, loc: Location | None, env: dict[str, str], http: httpx.Client) -> EngineAnswer:
        raise NotImplementedError

    # helpers
    def _post(self, http: httpx.Client, url: str, **kwargs: Any) -> dict[str, Any]:
        try:
            res = http.post(url, timeout=self.timeout, **kwargs)
        except httpx.HTTPError as e:
            raise EngineError(f"{self.label}: {type(e).__name__}") from e
        if res.status_code >= 400:
            detail = res.text[:300].replace("\n", " ")
            raise EngineError(f"{self.label}: HTTP {res.status_code}: {detail}")
        try:
            return res.json()
        except ValueError as e:
            raise EngineError(f"{self.label}: response was not JSON") from e


def _dedupe(citations: list[dict[str, str]]) -> list[dict[str, str]]:
    seen, out = set(), []
    for c in citations:
        if c.get("url") and c["url"] not in seen:
            seen.add(c["url"])
            out.append({"url": c["url"], "title": c.get("title") or ""})
    return out


class OpenAIEngine(Engine):
    """Responses API; web search tool with approximate user location."""

    name = "openai"
    label = "OpenAI"
    env_key = "OPENAI_API_KEY"
    default_models = ("gpt-4.1",)
    location_in_api = True
    prices = {"gpt-4.1": Price(2.0, 8.0, 0.025), "gpt-4.1-mini": Price(0.4, 1.6, 0.025)}

    def ask(self, prompt, *, model, search, loc, env, http):
        body: dict[str, Any] = {"model": model, "input": prompt}
        if search:
            tool: dict[str, Any] = {"type": "web_search"}
            if loc:
                tool["user_location"] = {k: v for k, v in {"type": "approximate", "country": loc.country, "city": loc.city, "region": loc.region}.items() if v}
            body["tools"] = [tool]
        url = env.get("OPENAI_API_URL") or "https://api.openai.com/v1/responses"
        t0 = time.monotonic()
        data = self._post(http, url, json=body, headers={"Authorization": f"Bearer {self.key(env)}"})
        latency = int((time.monotonic() - t0) * 1000)
        texts, cites, searches = [], [], 0
        for item in data.get("output", []):
            if item.get("type") == "web_search_call":
                searches += 1
            if item.get("type") != "message":
                continue
            for part in item.get("content", []):
                if part.get("type") == "output_text":
                    texts.append(part.get("text", ""))
                    cites += [{"url": a.get("url", ""), "title": a.get("title", "")} for a in part.get("annotations", []) if a.get("type") == "url_citation"]
        usage = data.get("usage") or {}
        return EngineAnswer(
            text="\n".join(texts).strip(),
            model_version=data.get("model"),
            citations=_dedupe(cites),
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            latency_ms=latency,
            search_used=search,
            location_mode=self.location_mode(search, loc),
            searches=searches,
        )


class GeminiEngine(Engine):
    """generateContent with Google Search grounding. No user-location option: region goes in the prompt."""

    name = "gemini"
    label = "Gemini"
    env_key = "GEMINI_API_KEY"
    default_models = ("gemini-2.5-flash",)
    location_in_api = False
    prices = {"gemini-2.5-flash": Price(0.3, 2.5, 0.035), "gemini-2.5-pro": Price(1.25, 10.0, 0.035)}

    def ask(self, prompt, *, model, search, loc, env, http):
        body: dict[str, Any] = {"contents": [{"role": "user", "parts": [{"text": prompt}]}]}
        if search:
            body["tools"] = [{"google_search": {}}]
        base = env.get("GEMINI_API_URL") or "https://generativelanguage.googleapis.com/v1beta"
        t0 = time.monotonic()
        data = self._post(http, f"{base}/models/{model}:generateContent", json=body, headers={"x-goog-api-key": self.key(env) or ""})
        latency = int((time.monotonic() - t0) * 1000)
        cand = (data.get("candidates") or [{}])[0]
        text = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []))
        grounding = cand.get("groundingMetadata") or {}
        cites = [{"url": c.get("web", {}).get("uri", ""), "title": c.get("web", {}).get("title", "")} for c in grounding.get("groundingChunks", [])]
        usage = data.get("usageMetadata") or {}
        return EngineAnswer(
            text=text.strip(),
            model_version=data.get("modelVersion") or model,
            citations=_dedupe(cites),
            input_tokens=usage.get("promptTokenCount", 0),
            output_tokens=usage.get("candidatesTokenCount", 0),
            latency_ms=latency,
            search_used=search,
            location_mode=self.location_mode(search, loc),
            searches=1 if search and grounding else 0,
        )


class PerplexityEngine(Engine):
    """Sonar always searches the web. Region goes to web_search_options.user_location."""

    name = "perplexity"
    label = "Perplexity"
    env_key = "PERPLEXITY_API_KEY"
    default_models = ("sonar",)
    search_toggle = False
    location_in_api = True
    prices = {"sonar": Price(1.0, 1.0, 0.008), "sonar-pro": Price(3.0, 15.0, 0.01)}

    def ask(self, prompt, *, model, search, loc, env, http):
        body: dict[str, Any] = {"model": model, "messages": [{"role": "user", "content": prompt}]}
        if loc:
            body["web_search_options"] = {"user_location": {k: v for k, v in {"country": loc.country, "city": loc.city, "region": loc.region}.items() if v}}
        url = env.get("PERPLEXITY_API_URL") or "https://api.perplexity.ai/v1/sonar"
        t0 = time.monotonic()
        data = self._post(http, url, json=body, headers={"Authorization": f"Bearer {self.key(env)}"})
        latency = int((time.monotonic() - t0) * 1000)
        msg = ((data.get("choices") or [{}])[0].get("message") or {}).get("content", "")
        results = data.get("search_results") or []
        cites = [{"url": r.get("url", ""), "title": r.get("title", "")} for r in results]
        cites += [{"url": u, "title": ""} for u in data.get("citations") or [] if isinstance(u, str)]
        usage = data.get("usage") or {}
        return EngineAnswer(
            text=(msg or "").strip(),
            model_version=data.get("model") or model,
            citations=_dedupe(cites),
            input_tokens=usage.get("prompt_tokens", usage.get("input_tokens", 0)),
            output_tokens=usage.get("completion_tokens", usage.get("output_tokens", 0)),
            latency_ms=latency,
            search_used=True,
            location_mode=self.location_mode(True, loc),
            searches=1,
        )


class AnthropicEngine(Engine):
    """Messages API via the official SDK; web search tool with approximate user location."""

    name = "anthropic"
    label = "Claude"
    env_key = "ANTHROPIC_API_KEY"
    default_models = ("claude-opus-5-5",)
    location_in_api = True
    prices = {"claude-opus-5-5": Price(4.0, 20.0, 0.01), "claude-sonnet-5-5": Price(2.0, 10.0, 0.01), "claude-haiku-5-5": Price(0.1, 0.5, 0.01)}

    def __init__(self, client: Any | None = None):
        self._client = client

    def client(self, env: dict[str, str]) -> Any:
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic(api_key=self.key(env))
        return self._client

    def ask(self, prompt, *, model, search, loc, env, http):
        client = self.client(env)
        kwargs: dict[str, Any] = {}
        if search:
            tool: dict[str, Any] = {"type": "web_search_20260209", "name": "web_search", "max_uses": 5}
            if loc:
                tool["user_location"] = {k: v for k, v in {"type": "approximate", "country": loc.country, "city": loc.city, "region": loc.region}.items() if v}
            kwargs["tools"] = [tool]
        messages: list[dict[str, Any]] = [{"role": "user", "content": prompt}]
        texts, cites = [], []
        in_tok = out_tok = searches = 0
        version = None
        t0 = time.monotonic()
        try:
            for _ in range(4):  # a long server-side search turn can pause; resume it
                resp = client.beta.messages.create(
                    model=model,
                    max_tokens=16000,
                    betas=[FALLBACK_BETA],
                    fallbacks="default",
                    messages=messages,
                    **kwargs,
                )
                version = resp.model
                in_tok += resp.usage.input_tokens or 0
                out_tok += resp.usage.output_tokens or 0
                server = getattr(resp.usage, "server_tool_use", None)
                searches += getattr(server, "web_search_requests", 0) or 0
                if resp.stop_reason == "refusal":
                    raise EngineError("Claude declined to answer")
                for block in resp.content:
                    if block.type == "text":
                        texts.append(block.text)
                        for c in getattr(block, "citations", None) or []:
                            url = getattr(c, "url", None)
                            if url:
                                cites.append({"url": url, "title": getattr(c, "title", "") or ""})
                if resp.stop_reason != "pause_turn":
                    break
                messages.append({"role": "assistant", "content": resp.content})
        except EngineError:
            raise
        except Exception as e:  # SDK errors: auth, rate limit, network
            raise EngineError(f"Claude: {type(e).__name__}: {str(e)[:200]}") from e
        return EngineAnswer(
            text="".join(texts).strip(),
            model_version=version,
            citations=_dedupe(cites),
            input_tokens=in_tok,
            output_tokens=out_tok,
            latency_ms=int((time.monotonic() - t0) * 1000),
            search_used=search,
            location_mode=self.location_mode(search, loc),
            searches=searches,
        )


ENGINES: dict[str, Engine] = {e.name: e for e in (OpenAIEngine(), GeminiEngine(), PerplexityEngine(), AnthropicEngine())}


def engine_env() -> dict[str, str]:
    from dotenv import dotenv_values

    from app.config import BACKEND_DIR

    file_values = {k: v for k, v in dotenv_values(BACKEND_DIR / ".env").items() if v}
    return {**file_values, **{k: v for k, v in os.environ.items() if v}}
