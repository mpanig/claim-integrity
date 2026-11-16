"""Prompt discovery: rule-based candidates, dedupe, estimated importance, optional Claude."""

import json
from types import SimpleNamespace

from app.ai.demo import generate_demo_answers
from app.ai.discovery import discover


def test_rules_dedupe_and_reasons(checked, session):
    generate_demo_answers(session, weeks=1, samples=1, density=0.1)
    session.commit()
    d = discover(session, env={})
    cands = d["candidates"]
    assert d["llm"] == "no key" and cands
    assert {"category", "problem", "versus", "attribute", "where_to_buy"} <= {c["intent"] for c in cands}
    assert all(0 <= c["importance"] <= 100 and c["reasons"] for c in cands)
    assert [c["importance"] for c in cands] == sorted((c["importance"] for c in cands), reverse=True)
    assert len({c["id"] for c in cands}) == len(cands)
    # A question about CeraVe never cites another brand's positioning gap.
    for c in cands:
        if c["brand"] == "CeraVe":
            assert not any("Aveeno" in r for r in c["reasons"] if r.startswith("Positioning gap"))
    # Adding a candidate to the library removes it from discovery.
    top = cands[0]
    from app.models import AiPrompt, Organisation

    org = session.query(Organisation).first()
    session.add(AiPrompt(organisation_id=org.id, text=top["text"], intent=top["intent"], category=top["category"]))
    session.commit()
    again = discover(session, env={})
    assert top["text"] not in {c["text"] for c in again["candidates"]}
    assert again["already_covered"] == d["already_covered"] + 1


def test_claude_suggestions_on_request(checked, session):
    payload = {"prompts": [{"text": "Is CeraVe or Cetaphil better for oily skin in humid weather?", "intent": "versus", "reason": "Humid climates"}]}

    class Fake:
        calls = 0

        class beta:  # noqa: N801 - mirrors the SDK shape
            class messages:  # noqa: N801
                @staticmethod
                def create(**kw):
                    Fake.calls += 1
                    assert kw["output_config"]["format"]["type"] == "json_schema"
                    return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(payload))])

    env = {"ANTHROPIC_API_KEY": "test-key"}
    assert discover(session, env=env, anthropic_client=Fake)["llm"] == "available" and Fake.calls == 0  # never by itself
    d = discover(session, llm=True, env=env, anthropic_client=Fake)
    assert d["llm"] == "used" and Fake.calls == 1
    ai = [c for c in d["candidates"] if c["source"] == "claude"]
    assert ai and ai[0]["reasons"][-1] == "Claude: Humid climates"
