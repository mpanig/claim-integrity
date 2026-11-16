"""Engine adapters against mocked API responses (no network)."""

import json
from types import SimpleNamespace

import httpx
import pytest

from app.ai.engines import ENGINES, AnthropicEngine, EngineError, Location

LOC = Location(country="IN", city="Mumbai")


def mock_http(responder):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content or b"{}")
        return responder(request)

    return httpx.Client(transport=httpx.MockTransport(handler)), seen


def test_openai_with_search_and_location():
    payload = {
        "model": "gpt-4.1-2025-04-14",
        "output": [
            {"type": "web_search_call", "status": "completed"},
            {
                "type": "message",
                "content": [
                    {
                        "type": "output_text",
                        "text": "1. CeraVe Hydrating Facial Cleanser\n2. Cetaphil",
                        "annotations": [{"type": "url_citation", "url": "https://www.cerave.com/x", "title": "CeraVe", "start_index": 0, "end_index": 5}],
                    }
                ],
            },
        ],
        "usage": {"input_tokens": 1200, "output_tokens": 300},
    }
    http, seen = mock_http(lambda r: httpx.Response(200, json=payload))
    a = ENGINES["openai"].ask("best cleanser?", model="gpt-4.1", search=True, loc=LOC, env={"OPENAI_API_KEY": "k"}, http=http)
    assert seen["url"] == "https://api.openai.com/v1/responses"
    assert seen["headers"]["authorization"] == "Bearer k"
    assert seen["body"]["tools"] == [{"type": "web_search", "user_location": {"type": "approximate", "country": "IN", "city": "Mumbai"}}]
    assert a.text.startswith("1. CeraVe")
    assert (a.model_version, a.input_tokens, a.output_tokens, a.searches) == ("gpt-4.1-2025-04-14", 1200, 300, 1)
    assert a.citations == [{"url": "https://www.cerave.com/x", "title": "CeraVe"}]
    assert a.location_mode == "api"
    assert ENGINES["openai"].cost("gpt-4.1", a) == round(1200 / 1e6 * 2 + 300 / 1e6 * 8 + 0.025, 6)

    # Without web search the region can only go in the prompt, and no tools are sent.
    http, seen = mock_http(lambda r: httpx.Response(200, json={**payload, "output": payload["output"][1:]}))
    a = ENGINES["openai"].ask("q", model="gpt-4.1", search=False, loc=LOC, env={"OPENAI_API_KEY": "k"}, http=http)
    assert "tools" not in seen["body"] and a.location_mode == "prompt-only"


def test_gemini_grounding():
    payload = {
        "candidates": [
            {
                "content": {"parts": [{"text": "Try Aveeno Calm + Restore."}]},
                "groundingMetadata": {"groundingChunks": [{"web": {"uri": "https://www.aveeno.com/p", "title": "aveeno.com"}}]},
            }
        ],
        "usageMetadata": {"promptTokenCount": 50, "candidatesTokenCount": 20},
        "modelVersion": "gemini-2.5-flash-001",
    }
    http, seen = mock_http(lambda r: httpx.Response(200, json=payload))
    a = ENGINES["gemini"].ask("q", model="gemini-2.5-flash", search=True, loc=LOC, env={"GEMINI_API_KEY": "g"}, http=http)
    assert seen["url"].endswith("/models/gemini-2.5-flash:generateContent")
    assert seen["headers"]["x-goog-api-key"] == "g"
    assert seen["body"]["tools"] == [{"google_search": {}}]
    assert (a.text, a.model_version, a.location_mode) == ("Try Aveeno Calm + Restore.", "gemini-2.5-flash-001", "prompt-only")
    assert a.citations == [{"url": "https://www.aveeno.com/p", "title": "aveeno.com"}]


def test_perplexity_always_searches():
    payload = {
        "model": "sonar",
        "choices": [{"message": {"role": "assistant", "content": "Vanicream is a good budget pick."}}],
        "search_results": [{"title": "Byrdie", "url": "https://www.byrdie.com/a"}],
        "citations": ["https://www.byrdie.com/a", "https://www.reddit.com/r/x"],
        "usage": {"prompt_tokens": 40, "completion_tokens": 25},
    }
    http, seen = mock_http(lambda r: httpx.Response(200, json=payload))
    a = ENGINES["perplexity"].ask("q", model="sonar", search=False, loc=LOC, env={"PERPLEXITY_API_KEY": "p"}, http=http)
    assert seen["body"]["web_search_options"] == {"user_location": {"country": "IN", "city": "Mumbai"}}
    assert a.search_used and a.location_mode == "api"
    assert [c["url"] for c in a.citations] == ["https://www.byrdie.com/a", "https://www.reddit.com/r/x"]
    assert (a.input_tokens, a.output_tokens) == (40, 25)


def test_http_errors_become_engine_errors():
    http, _ = mock_http(lambda r: httpx.Response(401, json={"error": "bad key"}))
    with pytest.raises(EngineError, match="HTTP 401"):
        ENGINES["openai"].ask("q", model="gpt-4.1", search=True, loc=None, env={"OPENAI_API_KEY": "x"}, http=http)


class FakeAnthropic:
    """Stands in for anthropic.Anthropic; returns a paused turn, then the final answer."""

    def __init__(self):
        self.calls = []
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.calls.append(kwargs)
        usage = SimpleNamespace(input_tokens=100, output_tokens=50, server_tool_use=SimpleNamespace(web_search_requests=1))
        if len(self.calls) == 1:
            return SimpleNamespace(model="claude-opus-5-5", stop_reason="pause_turn", usage=usage, content=[SimpleNamespace(type="text", text="Searching. ", citations=None)])
        cite = SimpleNamespace(url="https://nationaleczema.org/", title="NEA")
        return SimpleNamespace(model="claude-opus-5-5", stop_reason="end_turn", usage=usage, content=[SimpleNamespace(type="text", text="CeraVe has the NEA seal.", citations=[cite])])


def test_anthropic_resumes_paused_turn_and_reads_citations():
    fake = FakeAnthropic()
    a = AnthropicEngine(client=fake).ask("q", model="claude-opus-5-5", search=True, loc=LOC, env={"ANTHROPIC_API_KEY": "a"}, http=None)
    first = fake.calls[0]
    assert first["tools"][0]["type"] == "web_search_20260209"
    assert first["tools"][0]["user_location"] == {"type": "approximate", "country": "IN", "city": "Mumbai"}
    assert first["fallbacks"] == "default"
    assert len(fake.calls) == 2  # resumed after pause_turn
    assert a.text == "Searching. CeraVe has the NEA seal."
    assert (a.input_tokens, a.output_tokens, a.searches) == (200, 100, 2)
    assert a.citations == [{"url": "https://nationaleczema.org/", "title": "NEA"}]


def test_status_shows_key_presence_only():
    assert ENGINES["openai"].status({}) == "key missing"
    assert ENGINES["openai"].status({"OPENAI_API_KEY": "x"}) == "live"
