"""The Truth sheets view stays bounded with hundreds of products, and bursts never exhaust the DB pool."""

from concurrent.futures import ThreadPoolExecutor

from sqlalchemy import event

from app.db import MAX_OVERFLOW, POOL_SIZE, engine
from app.models import ApprovedClaim, Brand, Sku


def _count_queries():
    seen = []

    def before(conn, cursor, statement, *a):  # noqa: ANN001
        seen.append(statement)

    return seen, before


def test_truth_sheets_queries_are_bounded(checked, client, session):
    brand = session.query(Brand).filter_by(name="CeraVe").one()
    session.add_all(Sku(organisation_id=brand.organisation_id, brand_id=brand.id, name=f"Bulk product {i}") for i in range(700))
    session.flush()
    ids = [s.id for s in session.query(Sku).filter(Sku.name.like("Bulk product %"))]
    session.add_all(ApprovedClaim(organisation_id=brand.organisation_id, sku_id=i, field="claims", value=["Gentle"]) for i in ids[::7])
    session.commit()
    seen, before = _count_queries()
    event.listen(engine, "before_cursor_execute", before)
    try:
        skus = client.get("/skus").json()
        summary = client.get("/truth-sheets").json()
    finally:
        event.remove(engine, "before_cursor_execute", before)
    assert len(skus) >= 700 and len(summary) >= 100
    # Everything the Truth sheets page needs, for 700+ products, in a handful of queries (no per-product queries).
    assert len(seen) <= 12, len(seen)


def test_concurrent_requests_do_not_exhaust_the_pool(checked, client):
    before_out = engine.pool.checkedout()
    paths = ["/truth-sheets", "/skus", "/summary", "/conflicts/page", "/brands"] * 20
    with ThreadPoolExecutor(max_workers=40) as pool:  # more workers than connections
        codes = list(pool.map(lambda p: client.get(p).status_code, paths))
    assert set(codes) == {200}
    assert engine.pool.checkedout() == before_out  # every request returned its connection
    assert POOL_SIZE + MAX_OVERFLOW >= 30
