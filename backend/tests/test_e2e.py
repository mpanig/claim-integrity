"""End to end on the pilot seed, against the real test database."""

import httpx
from sqlalchemy import select

from app.models import Page, Snapshot


def verdicts(conflicts):
    return sorted((c["page_label"], c["field"], c["verdict"]) for c in conflicts)


def test_pilot_cerave(seeded, client):
    sku_id = seeded["CeraVe"]
    assert client.get("/health").json() == {"status": "ok"}
    assert sorted(s["name"] for s in client.get("/skus").json()) == [
        "Aveeno Calm + Restore Nourishing Oat Cleanser",
        "CeraVe Hydrating Facial Cleanser",
    ]
    assert client.get(f"/skus/{sku_id}/conflicts").json() == []

    run = client.post(f"/skus/{sku_id}/run").json()
    assert (run["new"], run["unresolved"], run["score"]) == (2, 2, 86)
    conflicts = client.get(f"/skus/{sku_id}/conflicts").json()
    assert verdicts(conflicts) == [
        ("Rite Aid", "free_from", "drift"),
        ("Rite Aid", "ingredients", "outdated"),
    ]
    ingredients = next(c for c in conflicts if c["field"] == "ingredients")
    assert ingredients["page_value"]["not_in_truth"] == ["methylparaben", "propylparaben"]
    assert ingredients["severity"] == 6 and ingredients["status"] == "open"

    # Running again keeps the same conflicts instead of duplicating them.
    again = client.post(f"/skus/{sku_id}/run").json()
    assert (again["new"], again["unresolved"]) == (0, 2)
    assert [c["id"] for c in client.get(f"/skus/{sku_id}/conflicts").json()] == [c["id"] for c in conflicts]


def test_pilot_aveeno(seeded, client):
    sku_id = seeded["Aveeno"]
    client.post(f"/skus/{sku_id}/run")
    assert verdicts(client.get(f"/skus/{sku_id}/conflicts").json()) == [
        ("Hannaford", "claims", "risky"),
        ("Hannaford", "free_from", "risky"),
        ("Hannaford", "free_from", "risky"),
        ("Hannaford", "free_from", "risky"),
        ("Hannaford", "free_from", "risky"),
        ("Hannaford", "free_from", "risky"),
        ("Hannaford", "name", "drift"),
        ("Kenvue Pro", "claims", "risky"),
        ("Kenvue Pro", "claims", "risky"),
        ("Kenvue Pro", "free_from", "risky"),
    ]


def test_dismissed_conflict_is_not_raised_again(checked, client):
    sku_id = checked["CeraVe"]
    drift = next(c for c in client.get(f"/skus/{sku_id}/conflicts").json() if c["field"] == "free_from")
    assert client.patch(f"/conflicts/{drift['id']}", json={"status": "dismissed"}).status_code == 409
    r = client.patch(f"/conflicts/{drift['id']}", json={"status": "dismissed", "reason": "same meaning"})
    assert r.status_code == 200 and r.json()["dismiss_reason"] == "same meaning"

    run = client.post(f"/skus/{sku_id}/run").json()
    assert (run["new"], run["unresolved"]) == (0, 1)
    statuses = sorted((c["field"], c["status"]) for c in client.get(f"/skus/{sku_id}/conflicts").json())
    assert statuses == [("free_from", "dismissed"), ("ingredients", "open")]


def test_fetch_stores_snapshot_and_skips_unchanged(seeded, session):
    from app.pipeline.fetch import content_hash, fetch_page

    bodies = iter(["<p>v1</p>", "<p>v1</p>", "<p>v2</p>"])
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=next(bodies)))

    with httpx.Client(transport=transport) as http:
        page = session.scalar(select(Page).where(Page.retailer == "Rite Aid"))
        first = fetch_page(session, page, http)
        assert first is not None and first.content_hash == content_hash("<p>v1</p>")
        assert fetch_page(session, page, http) is None
        assert fetch_page(session, page, http).html == "<p>v2</p>"
        # seed snapshot + v1 + v2
        assert len(session.scalars(select(Snapshot).where(Snapshot.page_id == page.id)).all()) == 3
        session.rollback()
