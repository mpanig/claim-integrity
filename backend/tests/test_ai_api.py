"""AI answer engine HTTP API."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import AiPrompt, Persona, RunConfig


def test_engines_report_key_presence_never_values(db_engine, client, monkeypatch):
    for k in ("OPENAI_API_KEY", "GEMINI_API_KEY", "PERPLEXITY_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "secret-value")
    rows = {e["engine"]: e for e in client.get("/ai/engines").json()}
    assert rows["gemini"]["status"] == "live" and rows["openai"]["status"] == "key missing"
    assert "secret-value" not in client.get("/ai/engines").text
    assert rows["perplexity"]["search"] == "always" and rows["gemini"]["location"] == "prompt only"


def test_library_and_editing(checked, client):
    lib = client.get("/ai/library").json()
    assert len(lib["prompts"]) == 6 and len(lib["personas"]) == 4
    assert {c["name"] for c in lib["competitors"]} >= {"Cetaphil", "La Roche-Posay"}
    assert any(v["language"] == "hi" for p in lib["prompts"] for v in p["variants"])

    pid = client.post("/ai/prompts", json={"text": "Is {product} safe for babies?", "intent": "attribute", "sku_id": lib["skus"][0]["id"]}).json()["id"]
    assert client.post("/ai/prompts", json={"text": "hello there", "intent": "nonsense"}).status_code == 422
    vid = client.post(f"/ai/prompts/{pid}/variants", json={"text": "क्या यह सुरक्षित है?", "language": "hi"}).json()["id"]
    assert client.delete(f"/ai/variants/{vid}").status_code == 204
    assert client.delete(f"/ai/prompts/{pid}").status_code == 204

    persona = client.post("/ai/personas", json={"name": "Teen", "context": "I'm 16 with oily, acne-prone skin."}).json()["id"]
    assert client.delete(f"/ai/personas/{persona}").status_code == 204
    comp = client.post("/ai/competitors", json={"name": "Simple"}).json()["id"]
    assert client.delete(f"/ai/competitors/{comp}").status_code == 204

    brand = lib["brands"][0]
    assert client.put("/ai/aliases", json={"brand_id": brand["id"], "aliases": [" X ", ""]}).json() == {"aliases": ["X"]}
    assert client.put("/ai/aliases", json={"aliases": ["x"]}).status_code == 422


def _cfg(session, **over):
    cfg = {
        "prompt_ids": session.scalars(select(AiPrompt.id)).all()[:2],
        "engines": [{"engine": "openai", "models": ["gpt-4.1"]}],
        "regions": [{"country": "US", "city": "New York", "languages": ["en"]}],
        "variants": "first",
        "samples": 3,
    }
    cfg.update(over)
    return cfg


def test_estimate_and_run_without_keys(checked, client, session, monkeypatch):
    for k in ("OPENAI_API_KEY", "GEMINI_API_KEY", "PERPLEXITY_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    import app.api.ai as api_mod

    monkeypatch.setattr(api_mod, "engine_env", lambda: {})
    est = client.post("/ai/estimate", json={"config": _cfg(session)}).json()
    assert est["cells"] == 2 * 3 and est["runnable_calls"] == 0
    assert client.post("/ai/runs", json={"config": _cfg(session)}).status_code == 409
    bad = client.post("/ai/estimate", json={"config": _cfg(session, engines=[{"engine": "bing", "models": ["x"]}])})
    assert bad.status_code == 422


def test_saved_configs_and_schedule(checked, client, session):
    from app.ai.schedule import due, run_due

    assert len(client.get("/ai/configs").json()) == 1  # the seeded pilot plan
    cid = client.post("/ai/configs", json={"name": "Weekly US", "config": _cfg(session), "schedule": "weekly"}).json()["id"]
    assert client.post("/ai/configs", json={"name": "x", "config": _cfg(session), "schedule": "hourly"}).status_code == 422
    assert [c.id for c in due(session)] == [cid]
    # No keys: nothing runs, but the plan is marked as handled until next week.
    assert run_due(session, env={}) == []
    session.expire_all()
    assert due(session) == []
    c = session.get(RunConfig, cid)
    c.last_run_at = datetime.now(UTC) - timedelta(days=8)
    session.commit()
    assert [x.id for x in due(session)] == [cid]


def test_insights_and_answers_on_demo_data(checked, client, session):
    from app.ai.demo import generate_demo_answers

    assert generate_demo_answers(session, weeks=2, samples=1) > 0
    ins = client.get("/ai/insights").json()
    assert ins["demo"] is True and {e["mode"] for e in ins["engines"]} == {"demo"}
    cerave = next(b for b in ins["brands"] if b["name"] == "CeraVe")
    assert cerave["is_own"] and 0 < cerave["mention"]["rate"] <= 1
    assert cerave["mention"]["low"] <= cerave["mention"]["rate"] <= cerave["mention"]["high"]
    assert ins["accuracy"] and ins["citations"]["total"] > 0

    only_in = client.get("/ai/insights", params={"region": "IN", "engine": "perplexity"}).json()
    assert {e["engine"]: e["answers"] for e in only_in["engines"]}["openai"] == 0

    persona = session.scalars(select(Persona.id)).first()
    listed = client.get("/ai/answers", params={"persona_id": persona, "brand": "CeraVe", "limit": 5}).json()
    assert listed["total"] > 0 and len(listed["items"]) <= 5
    assert all("CeraVe" in a["mentions"] for a in listed["items"])
    detail = client.get(f"/ai/answers/{listed['items'][0]['id']}").json()
    assert detail["is_demo"] and detail["answer"] and detail["prompt_text"]
    assert detail["mentions_detail"] and "location_mode" in detail
    assert client.get("/ai/answers/999999").status_code == 404
