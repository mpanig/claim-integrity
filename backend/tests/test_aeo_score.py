"""AEO score: prominence, word share, composite, per engine and trend."""

from types import SimpleNamespace

from app.ai.analyse import Entity
from app.ai.score import WEIGHTS, _scan, _scores


def _answer(text, mentions=()):
    return SimpleNamespace(answer=text, mentions=[SimpleNamespace(name=n, recommended=r, sentiment=s) for n, r, s in mentions])


def test_prominence_and_word_share():
    entities = [Entity("CeraVe", [], True), Entity("Cetaphil", [], False), Entity("Aveeno", [], True)]
    patterns = {e.name: e.pattern() for e in entities}
    a = _answer(
        "Cetaphil Gentle Cleanser is the classic pick. CeraVe and Cetaphil both suit dry skin well. Drink water.",
        [("Cetaphil", True, 0.5), ("CeraVe", False, 0.0)],
    )
    t = _scan(a, entities, patterns)
    assert t["Cetaphil"].first_named == 1 and t["CeraVe"].first_named == 0
    assert t["Cetaphil"].prominence == 1.0  # named at the very start
    assert 0 < t["CeraVe"].prominence < 1
    assert t["Aveeno"].mentioned == 0 and t["Aveeno"].prominence == 0
    # Sentence 1 (7 words) is all Cetaphil; sentence 2 (8 words) is split; "Drink water." is nobody's.
    assert t["Cetaphil"].words == 7 + 4 and t["CeraVe"].words == 4
    rows = {r["name"]: r for r in _scores(entities, t)}
    assert rows["Cetaphil"]["score"] > rows["CeraVe"]["score"] > rows["Aveeno"]["score"] == 0
    assert abs(sum(WEIGHTS.values()) - 1) < 1e-9


def test_score_api_on_demo(checked, client, session):
    from app.ai.demo import generate_demo_answers

    generate_demo_answers(session, weeks=3, samples=1, density=0.1)
    session.commit()
    d = client.get("/ai/score").json()
    assert d["answers"] > 0 and d["demo"] is True
    assert {b["name"] for b in d["brands"]} >= {"CeraVe", "Aveeno"}
    assert all(0 <= b["score"] <= 100 for b in d["brands"])
    assert [b["score"] for b in d["brands"]] == sorted((b["score"] for b in d["brands"]), reverse=True)
    assert d["best_own"]["is_own"] and not d["top_rival"]["is_own"]
    assert {e["engine"] for e in d["by_engine"]} == {"openai", "gemini", "perplexity", "anthropic"}
    assert len(d["trend"]) == 3 and "change" in d["brands"][0]
    one = client.get("/ai/score", params={"engine": "gemini"}).json()
    assert [e["engine"] for e in one["by_engine"]] == ["gemini"]
