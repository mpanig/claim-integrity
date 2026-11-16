"""AEO alerts: the four rules, demo flagging, de-duplication, API."""

from datetime import UTC, datetime, timedelta

from app.ai.aeo_alerts import evaluate
from app.ai.demo import generate_demo_answers
from app.models import AiAnswer, AiPrompt, Alert, AnswerClaim, AnswerMention, Organisation, Sku


def _answer(session, prompt, when, text, mentions, claims=(), demo=False):
    org = session.query(Organisation).first()
    a = AiAnswer(organisation_id=org.id, prompt_id=prompt.id, assistant="OpenAI gpt-4.1", engine="openai", model_requested="gpt-4.1",
                 answer=text, asked_at=when, is_demo=demo, region="US", language="en", search_enabled=True)
    session.add(a)
    session.flush()
    for i, (name, own, recommended) in enumerate(mentions, 1):
        session.add(AnswerMention(answer_id=a.id, name=name, is_own=own, position=i, recommended=recommended, sentiment=0.3, quote=name))
    for sku_id, field, value, verdict in claims:
        session.add(AnswerClaim(answer_id=a.id, sku_id=sku_id, field=field, value=value, quote=str(value), verdict=verdict))
    return a


def test_rules_fire_on_real_answers(checked, session):
    session.query(AiAnswer).delete()
    session.commit()
    prompt = session.query(AiPrompt).filter(AiPrompt.intent.in_(("category", "problem"))).first()
    sku = session.query(Sku).filter(Sku.name.like("Aveeno%")).one()
    now = datetime.now(UTC)
    last, this = now - timedelta(days=7), now
    for _ in range(6):  # last week: Aveeno first and recommended
        _answer(session, prompt, last, "Aveeno is great. Cetaphil is fine.", [("Aveeno", True, True), ("Cetaphil", False, False)])
    for _ in range(6):  # this week: Cetaphil leads, Aveeno not recommended, a new wrong fact
        _answer(session, prompt, this, "Cetaphil is the best pick. Cetaphil again. Aveeno exists.", [("Cetaphil", False, True), ("Aveeno", True, False)],
                claims=[(sku.id, "free_from", "Sulfate-Free", "risky")])
    session.commit()
    kinds = {a.kind for a in evaluate(session, env={"OPENAI_API_KEY": "k"})}
    assert {"aeo_score_drop", "aeo_overtaken", "aeo_lost_recommendation", "aeo_wrong_fact"} <= kinds
    assert all(not a.is_demo for a in session.query(Alert).filter(Alert.kind.like("aeo_%")))
    n = session.query(Alert).filter(Alert.kind.like("aeo_%")).count()
    assert evaluate(session, env={"OPENAI_API_KEY": "k"}) == [] and session.query(Alert).filter(Alert.kind.like("aeo_%")).count() == n  # de-duplicated


def test_demo_alerts_flagged_and_listed(checked, client, session):
    generate_demo_answers(session, weeks=2, samples=1, density=0.3)
    session.commit()
    out = evaluate(session, env={})
    assert out and all(a.is_demo for a in out)
    again = evaluate(session, env={})
    assert len(session.query(Alert).filter(Alert.is_demo.is_(True)).all()) == len(again)  # replaced, not stacked
    d = client.get("/alerts", params={"kind_prefix": "aeo_"}).json()
    assert d["items"] and all(i["kind"].startswith("aeo_") and i["is_demo"] and i["sku_id"] is None and i["brand_name"] for i in d["items"])
    assert client.get("/alerts").json()["items"]  # the main list still works with brand-level alerts
    assert client.post("/aeo/alerts/evaluate").status_code == 200
