"""Planned engines: listed with their key, never run or estimated."""

from app.ai.engines import ENGINES
from app.ai.planned import PLANNED, planned


def test_planned_are_listed_not_run(client):
    names = {p["engine"] for p in PLANNED}
    assert {"google_aio", "google_ai_mode", "copilot", "grok", "deepseek", "meta_ai"} == names
    assert not names & set(ENGINES)  # never part of runs, estimates or demo answers
    rows = client.get("/ai/engines/planned").json()
    assert {r["engine"] for r in rows} == names
    assert all("key" not in r or r.get("key") is None for r in rows)  # the key value is never returned


def test_key_switches_status():
    off = {p["engine"]: p for p in planned(env={})}
    on = {p["engine"]: p for p in planned(env={"XAI_API_KEY": "x", "SERPAPI_API_KEY": "y"})}
    assert off["grok"]["status"] == "planned" and not off["grok"]["key_set"]
    assert on["grok"]["status"] == "key set, connector coming"
    assert on["google_aio"]["key_set"] and on["copilot"]["key_set"] and not on["deepseek"]["key_set"]
