"""Demo vs real answers per engine, driven by whether that engine's API key is present."""

import httpx
from sqlalchemy import func, select

from app.ai.insights import insights
from app.models import AiAnswer, AiPrompt, AiRun, Organisation


def _demo(session):
    from app.ai.demo import generate_demo_answers

    return generate_demo_answers(session, weeks=2, samples=1, density=0.05)


def _modes(result):
    return {e["engine"]: (e["mode"], e["answers"]) for e in result["engines"]}


def test_demo_is_rich_flagged_and_deterministic(checked, session):
    n = _demo(session)
    assert n > 0
    rows = session.scalars(select(AiAnswer).where(AiAnswer.engine.is_not(None))).all()
    assert rows and all(a.is_demo for a in rows)
    assert {a.engine for a in rows} == {"openai", "gemini", "perplexity", "anthropic"}
    assert {a.region for a in rows} == {"US", "IN", "GB"}
    assert {"en", "hi"} <= {a.language for a in rows}
    assert {a.search_enabled for a in rows} == {True, False}
    assert all(not a.citations for a in rows if not a.search_enabled)  # no web search, no citations
    assert session.scalar(select(func.count()).select_from(AiRun).where(AiRun.is_demo.is_(True))) == 2
    # Same seed, same data.
    first = sorted((a.engine, a.region, a.answer) for a in rows)
    assert _demo(session) == n
    again = sorted((a.engine, a.region, a.answer) for a in session.scalars(select(AiAnswer).where(AiAnswer.engine.is_not(None))))
    assert again == first


def test_key_absent_shows_demo(checked, session):
    _demo(session)
    modes = _modes(insights(session, env={}))
    assert all(mode == "demo" and n > 0 for mode, n in modes.values())


def test_key_present_without_real_answers_hides_demo(checked, session, client, monkeypatch):
    _demo(session)
    result = insights(session, env={"OPENAI_API_KEY": "x"})
    modes = _modes(result)
    assert modes["openai"] == ("awaiting", 0)
    assert modes["gemini"][0] == "demo"
    assert result["awaiting"] == ["openai"]
    assert result["answers"] == sum(n for _, n in modes.values())

    # The API re-reads keys on every request.
    import app.ai.insights as mod

    monkeypatch.setattr(mod, "engine_env", lambda: {"GEMINI_API_KEY": "y"})
    api = client.get("/ai/insights").json()
    assert {e["engine"]: e["mode"] for e in api["engines"]}["gemini"] == "awaiting"
    listed = client.get("/ai/answers", params={"engine": "gemini"}).json()
    assert listed["total"] == 0


def test_key_present_with_real_answers_shows_only_real(checked, session):
    from app.ai.plan import PlanConfig
    from app.ai.runner import execute

    _demo(session)
    org = session.scalar(select(Organisation.id))
    payload = {"model": "gpt-4.1-2025", "output": [{"type": "message", "content": [{"type": "output_text", "text": "1. CeraVe Hydrating Facial Cleanser", "annotations": []}]}], "usage": {"input_tokens": 10, "output_tokens": 5}}
    http = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=payload)))
    cfg = PlanConfig(prompt_ids=[session.scalar(select(AiPrompt.id))], engines=[{"engine": "openai", "models": ["gpt-4.1"]}], search_modes=[True], regions=[{"country": "US", "languages": ["en"]}], variants="first", samples=1)
    run = AiRun(organisation_id=org, config=cfg.model_dump(), budget_usd=1)
    session.add(run)
    session.commit()
    execute(session, run, env={"OPENAI_API_KEY": "x"}, http=http, sleep=lambda s: None, analyser="rules")

    answers, modes = __import__("app.ai.insights", fromlist=["select_answers"]).select_answers(session, env={"OPENAI_API_KEY": "x"})
    openai = [a for a in answers if a.engine == "openai"]
    assert len(openai) == 1 and not openai[0].is_demo
    assert {m["engine"]: m["mode"] for m in modes}["openai"] == "live"
