"""Citation outreach: suggestions from gap sites, statuses, owners, demo vs real."""

from app.ai.demo import generate_demo_answers
from app.ai.outreach import generate_demo_outreach
from app.models import TeamMember


def test_gap_sites_exist_in_demo(checked, client, session):
    generate_demo_answers(session, weeks=1, samples=1, density=0.2)
    session.commit()
    third = client.get("/ai/coverage").json()["third_party"]
    rival_leaning = {"verywellhealth.com", "dermstore.com", "goodhousekeeping.com", "cosmopolitan.com"}
    gaps = {d["domain"]: d["gap"] for d in third}
    assert any(gaps.get(d, 0) > 0 for d in rival_leaning)


def test_tracker_flow(checked, client, session):
    generate_demo_answers(session, weeks=1, samples=1, density=0.2)
    session.commit()
    assert generate_demo_outreach(session) > 0
    d = client.get("/aeo/outreach").json()
    assert d["demo"] is True and all(r["is_demo"] for r in d["rows"])
    assert d["suggestions"] is not None
    r = client.post("/aeo/outreach", json={"domain": "https://www.Example-Reviews.com/best-cleansers"})
    assert r.status_code == 201 and r.json()["domain"] == "example-reviews.com"
    d = client.get("/aeo/outreach").json()
    assert d["demo"] is False and [x["domain"] for x in d["rows"]] == ["example-reviews.com"]  # demo hidden
    row = d["rows"][0]
    assert row["status"] == "to_contact"
    owner = session.query(TeamMember).first()
    assert client.patch(f"/aeo/outreach/{row['id']}", json={"status": "contacted", "owner_id": owner.id, "due_date": "2020-01-01"}).status_code == 200
    row = client.get("/aeo/outreach").json()["rows"][0]
    assert row["status"] == "contacted" and row["owner"] == owner.name and row["overdue"] is True
    assert client.patch(f"/aeo/outreach/{row['id']}", json={"status": "nope"}).status_code == 422
    assert client.patch(f"/aeo/outreach/{row['id']}", json={"status": "published", "published_url": "https://example-reviews.com/a"}).status_code == 200
    assert client.get("/aeo/outreach").json()["rows"][0]["overdue"] is False
    assert client.delete(f"/aeo/outreach/{row['id']}").status_code == 204
    assert client.get("/aeo/outreach").json()["demo"] is True


def test_competitor_sites_never_targets(checked, client, session):
    generate_demo_answers(session, weeks=1, samples=1, density=0.2)
    session.commit()
    generate_demo_outreach(session)
    d = client.get("/aeo/outreach").json()
    domains = {s["domain"] for s in d["suggestions"]} | {r["domain"] for r in d["rows"]}
    assert not any(x in dom for dom in domains for x in ("laroche-posay", "cetaphil", "vanicream", "neutrogena", "eucerin"))
