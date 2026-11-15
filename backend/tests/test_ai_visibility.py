from app.models import Verdict
from app.pipeline.compare import Finding
from app.seed import CERAVE
from app.services.ai_visibility import compare_answer

TRUTH = {**CERAVE["truth"], "name": CERAVE["name"]}


def verdicts(findings: list[Finding]):
    return sorted((f.field, f.verdict.value) for f in findings)


def test_answer_rules():
    assert compare_answer(TRUTH, {}) == []
    # Omitting claims is fine; correct facts are fine.
    assert compare_answer(TRUTH, {"seals": ["NEA Seal of Acceptance"], "contains": ["Ceramide 3"]}) == []
    found = compare_answer(
        TRUTH,
        {"contains": ["Methylparaben"], "free_from": ["Fragrance Free"], "claims": ["Hypoallergenic"], "name": "CeraVe Cleanser"},
    )
    assert verdicts(found) == [
        ("claims", "risky"),
        ("free_from", "drift"),
        ("ingredients", "outdated"),
        ("name", "drift"),
    ]
    assert found[0].verdict is Verdict.risky


def test_empty_state_before_any_answers(seeded, client):
    a = client.get("/ai-visibility").json()
    assert (a["configured"], a["demo"], a["answers"], a["prompts"]) == (False, False, [], [])


def test_prompts_and_demo_answers(checked, client, session):
    from app.services.ai_visibility import generate_demo_answers

    r = client.post("/ai-visibility/prompts", json={"text": "Which cleanser has ceramides?"})
    assert r.status_code == 201
    assert client.post("/ai-visibility/prompts", json={"text": "x"}).status_code == 422

    assert generate_demo_answers(session) == 6
    a = client.get("/ai-visibility").json()
    assert a["demo"] is True and all(x["is_demo"] for x in a["answers"])
    assert len(a["prompts"]) == 4
    assert a["accuracy"] == {"checked": 4, "with_issues": 2}

    parabens = next(x for x in a["answers"] if x["stated_facts"].get("contains") == ["Methylparaben", "Propylparaben"])
    outdated = [f for f in parabens["findings"] if f["verdict"] == "outdated"]
    assert len(outdated) == 2
    # The assistant repeats the Rite Aid page's outdated ingredient list.
    assert [f["echoes"] for f in outdated] == [["Rite Aid"], ["Rite Aid"]]
    drift = next(f for f in parabens["findings"] if f["verdict"] == "drift")
    assert drift["echoes"] == ["Rite Aid"]

    # Echoes match the specific claim: Hannaford says "Fragrance Free", Kenvue Pro only "Sulfate-free".
    hypo = next(x for x in a["answers"] if x["stated_facts"].get("claims") == ["Hypoallergenic"])
    by_claim = {f["stated"]: f["echoes"] for f in hypo["findings"]}
    assert by_claim == {"Fragrance Free": ["Hannaford"], "Hypoallergenic": ["Kenvue Pro"]}

    sov = {s["brand"]: s for s in a["share_of_voice"]}
    assert sov["CeraVe"]["mentions"] == 4 and sov["Aveeno"]["mentions"] == 3

    # Running it again replaces demo answers rather than adding more.
    generate_demo_answers(session)
    assert len(client.get("/ai-visibility").json()["answers"]) == 6

    pid = r.json()["id"]
    assert client.delete(f"/ai-visibility/prompts/{pid}").status_code == 204
    assert client.delete(f"/ai-visibility/prompts/{pid}").status_code == 404
