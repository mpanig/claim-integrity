"""Paged conflict lists (board / conflicts page) and brand labels across organisations."""

from app.models import Brand, Organisation


def test_conflict_page_filters_and_order(checked, client):
    full = client.get("/conflicts").json()
    page = client.get("/conflicts/page", params={"limit": 2}).json()
    assert page["total"] == len(full) and len(page["items"]) == min(2, len(full))
    sev = [c["severity"] for c in page["items"]]
    assert sev == sorted(sev, reverse=True) and sev[0] == max(c["severity"] for c in full)  # highest risk first
    rest = client.get("/conflicts/page", params={"limit": 2, "offset": 2}).json()
    assert {c["id"] for c in rest["items"]}.isdisjoint({c["id"] for c in page["items"]})
    high = client.get("/conflicts/page", params={"min_severity": 9}).json()
    assert high["total"] == sum(1 for c in full if c["severity"] >= 9) and all(c["severity"] >= 9 for c in high["items"])
    v = full[0]["verdict"]
    assert client.get("/conflicts/page", params={"verdict": v}).json()["total"] == sum(1 for c in full if c["verdict"] == v)
    assert client.get("/conflicts/page", params={"status": ["verified"], "sort": "recent"}).status_code == 200
    assert client.get("/conflicts/page", params={"limit": 0}).status_code == 422


def test_brand_labels_disambiguate_organisations(checked, client, session):
    org = Organisation(name="Public data: Aveeno & Listerine")
    session.add(org)
    session.flush()
    session.add(Brand(organisation_id=org.id, name="Aveeno"))
    session.commit()
    try:
        labels = sorted(b["label"] for b in client.get("/brands").json())
        pilot = session.query(Organisation).filter(Organisation.id != org.id).first().name.split(":")[0].lower()
        assert f"Aveeno ({pilot})" in labels and "Aveeno (public data)" in labels
        assert "CeraVe" in labels  # unique names stay as they are
    finally:  # the seed only resets the pilot organisation, so remove this one
        session.delete(org)
        session.commit()
