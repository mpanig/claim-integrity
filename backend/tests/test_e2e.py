"""End to end on the pilot seed, against the real test database."""

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.models import Conflict, ConflictStatus, Organisation, Page, Snapshot


def test_pilot_seed_run_and_endpoints(db_engine):
    from app.db import SessionLocal
    from app.main import app
    from app.seed import seed

    with SessionLocal() as s:
        ids = seed(s)
    sku_id = ids["sku_id"]
    client = TestClient(app)

    assert client.get("/health").json() == {"status": "ok"}
    assert [s["id"] for s in client.get("/skus").json()] == [sku_id]
    assert client.get(f"/skus/{sku_id}/conflicts").json() == []
    assert client.get("/skus/999999/conflicts").status_code == 404

    run = client.post(f"/skus/{sku_id}/run")
    assert run.status_code == 200
    got = sorted((c["field"], c["verdict"], c["severity"], c["status"]) for c in run.json())
    assert got == [("free_from", "drift", 1, "open"), ("ingredients", "outdated", 6, "open")]
    ingredients = next(c for c in run.json() if c["field"] == "ingredients")
    assert ingredients["page_value"]["not_in_truth"] == ["methylparaben", "propylparaben"]

    # Running again replaces open conflicts rather than duplicating them.
    client.post(f"/skus/{sku_id}/run")
    listed = client.get(f"/skus/{sku_id}/conflicts").json()
    assert [c["severity"] for c in listed] == [6, 1]

    # A dismissed conflict stays dismissed and is not raised again.
    with SessionLocal() as s:
        s.execute(
            update(Conflict).where(Conflict.field == "free_from").values(status=ConflictStatus.dismissed)
        )
        s.commit()
    rerun = client.post(f"/skus/{sku_id}/run").json()
    assert [c["field"] for c in rerun] == ["ingredients"]
    statuses = sorted((c["field"], c["status"]) for c in client.get(f"/skus/{sku_id}/conflicts").json())
    assert statuses == [("free_from", "dismissed"), ("ingredients", "open")]

    # Seeding again resets the pilot organisation cleanly.
    with SessionLocal() as s:
        seed(s)
        assert s.scalar(select(Organisation).where(Organisation.name == "Pilot: CeraVe")) is not None


def test_fetch_stores_snapshot_and_skips_unchanged(db_engine):
    from app.db import SessionLocal
    from app.pipeline.fetch import content_hash, fetch_page
    from app.seed import seed

    bodies = iter(["<p>v1</p>", "<p>v1</p>", "<p>v2</p>"])
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=next(bodies)))

    with SessionLocal() as s, httpx.Client(transport=transport) as client:
        seed(s)
        page = s.scalar(select(Page))
        first = fetch_page(s, page, client)
        assert first is not None and first.content_hash == content_hash("<p>v1</p>")
        assert fetch_page(s, page, client) is None
        assert fetch_page(s, page, client).html == "<p>v2</p>"
        # seed snapshot + v1 + v2
        assert len(s.scalars(select(Snapshot).where(Snapshot.page_id == page.id)).all()) == 3
        s.rollback()
