"""Brand perception: attributes per brand, product names excluded, positioning gaps."""

from app.ai.demo import generate_demo_answers
from app.models import Brand


def test_perception_on_demo(checked, client, session):
    generate_demo_answers(session, weeks=2, samples=1, density=0.1)
    session.commit()
    d = client.get("/ai/perception").json()
    by = {b["name"]: b for b in d["brands"]}
    assert d["demo"] is True and {"CeraVe", "Aveeno"} <= by.keys()
    # Oat is Aveeno's; "Hydrating Facial Cleanser" is a product name, not a claim about CeraVe.
    assert d["leaders"]["natural"] == "Aveeno"
    assert by["CeraVe"]["attributes"]["hydrating"]["rate"] < 0.5
    keys = {a["key"] for a in d["attributes"]}
    assert all(set(b["attributes"]) == keys for b in d["brands"])
    assert all(not b["gaps"] for b in d["brands"] if not b["is_own"])


def test_positioning_drives_gaps(checked, client, session):
    generate_demo_answers(session, weeks=1, samples=1, density=0.1)
    session.commit()
    aveeno = session.query(Brand).filter_by(name="Aveeno").one()
    r = client.put(f"/ai/brands/{aveeno.id}/positioning", json={"attributes": ["eczema", "natural"]})
    assert r.status_code == 200 and r.json()["positioning"] == ["eczema", "natural"]
    gaps = {g["attribute"]: g["kind"] for g in next(b for b in client.get("/ai/perception").json()["brands"] if b["name"] == "Aveeno")["gaps"]}
    assert gaps.get("eczema") == "missing" and "natural" not in gaps
    assert client.put(f"/ai/brands/{aveeno.id}/positioning", json={"attributes": ["nonsense"]}).status_code == 422
