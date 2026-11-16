"""AI engines that are planned but not connected yet (key-gated placeholders).

They are listed so the team can see coverage gaps and which key will switch each one on.
They are never run, never estimated, and never get demo answers (there is nothing real to
imitate yet). When a connector is built it moves into app.ai.engines.ENGINES.
"""

from typing import Any

from app.ai.engines import engine_env

# id, label, env key, has an official answer API, how it will connect
PLANNED: list[dict[str, Any]] = [
    {
        "engine": "google_aio",
        "label": "Google AI Overviews",
        "env_key": "SERPAPI_API_KEY",
        "official_api": False,
        "how": "Google has no API for AI Overviews; read them from a SERP data provider's Google results (e.g. SerpApi's ai_overview).",
    },
    {
        "engine": "google_ai_mode",
        "label": "Google AI Mode",
        "env_key": "SERPAPI_API_KEY",
        "official_api": False,
        "how": "No official API; read AI Mode answers through a SERP data provider.",
    },
    {
        "engine": "copilot",
        "label": "Microsoft Copilot",
        "env_key": "SERPAPI_API_KEY",
        "official_api": False,
        "how": "Consumer Copilot answers have no public API; read them through a SERP data provider that returns Copilot results.",
    },
    {
        "engine": "grok",
        "label": "Grok (xAI)",
        "env_key": "XAI_API_KEY",
        "official_api": True,
        "how": "Official xAI API (OpenAI-compatible chat completions).",
    },
    {
        "engine": "deepseek",
        "label": "DeepSeek",
        "env_key": "DEEPSEEK_API_KEY",
        "official_api": True,
        "how": "Official DeepSeek API (OpenAI-compatible). No web search in the API, so answers come from model knowledge only.",
    },
    {
        "engine": "meta_ai",
        "label": "Meta AI",
        "env_key": "LLAMA_API_KEY",
        "official_api": False,
        "how": "The Meta AI assistant has no public API. The Llama API gives the underlying models without Meta AI's search, so results would be indicative only.",
    },
]


def planned(env: dict[str, str] | None = None) -> list[dict[str, Any]]:
    env = engine_env() if env is None else env
    return [
        {**p, "key_set": bool(env.get(p["env_key"])), "status": "key set, connector coming" if env.get(p["env_key"]) else "planned"}
        for p in PLANNED
    ]
