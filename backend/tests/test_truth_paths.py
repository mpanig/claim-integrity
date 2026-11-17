"""Truth sources: approved truth sheet vs inferred (unverified) truth, and recompute on approval."""

import json
from types import SimpleNamespace

from app.models import Brand, Conflict, Extraction, InferredTruth, Page, Snapshot
from app.pipeline.truth import refresh_inferred

INGR = ["Water", "Glycerin", "Avena Sativa (Oat) Kernel Flour"]
OLD = [*INGR, "Methylparaben"]


def _page(session, org_id, sku_id, url, weight, fields):
    page = Page(organisation_id=org_id, url=url, source_type="retailer", retailer=url.split("/")[2], weight=weight)
    session.add(page)
    session.flush()
    snap = Snapshot(organisation_id=org_id, page_id=page.id, content_hash=url, html="<html></html>")
    session.add(snap)
    session.flush()
    session.add(Extraction(organisation_id=org_id, snapshot_id=snap.id, sku_id=sku_id, fields={k: {"value": v, "quote": str(v)} for k, v in fields.items()}))
    session.flush()
    return page


def _product_without_truth(client, session):
    brand = session.query(Brand).filter_by(name="Aveeno").one()
    sku = client.post("/skus", json={"brand_id": brand.id, "name": "Aveeno Daily Oat Wash"}).json()
    name = "Aveeno Daily Oat Wash"
    _page(session, brand.organisation_id, sku["id"], "https://shop-a.example/oat-wash", 1.0, {"name": name, "ingredients": INGR, "free_from": ["Fragrance Free"]})
    _page(session, brand.organisation_id, sku["id"], "https://shop-b.example/oat-wash", 1.0, {"name": name, "ingredients": INGR, "free_from": ["Fragrance Free"]})
    old = _page(session, brand.organisation_id, sku["id"], "https://shop-c.example/oat-wash", 0.7, {"name": name, "ingredients": OLD, "free_from": ["Fragrance Free", "Sulfate Free"]})
    session.commit()
    return sku["id"], old.id


def test_products_with_a_truth_sheet_use_it(checked, client, session):
    for name, sku_id in checked.items():
        s = client.get(f"/skus/{sku_id}").json()
        assert s["truth_status"] == "approved", name
        assert s["drift_score"] == 100 - s["score"]
        assert all(c["truth_source"] == "approved" for c in client.get(f"/skus/{sku_id}/conflicts").json())
    assert session.query(InferredTruth).count() == 0
    matrix = client.get(f"/skus/{checked['CeraVe']}/matrix").json()
    assert matrix["truth"]["status"] == "approved" and "approved" in matrix["truth"]["label"]
    recs = client.get("/recommendations").json()
    assert not any(r["rule"] == "add_truth_sheet" for r in (recs["items"] if isinstance(recs, dict) else recs))


def _recs(client):
    data = client.get("/recommendations").json()
    return data["items"] if isinstance(data, dict) else data


def test_without_truth_sheet_infers_flags_and_recommends(checked, client, session):
    sku_id, old_page = _product_without_truth(client, session)
    run = client.post(f"/skus/{sku_id}/run").json()
    assert run["truth_status"] == "inferred"
    s = client.get(f"/skus/{sku_id}").json()
    assert s["truth_status"] == "inferred" and s["inferred_method"] == "majority" and s["drift_score"] > 0
    inferred = client.get(f"/skus/{sku_id}/inferred-truth").json()
    assert inferred["fields"]["ingredients"] == INGR  # two of three pages (most page weight) agree
    assert inferred["fields"]["free_from"] == ["Fragrance Free"]
    assert inferred["agreement"]["ingredients"] == round(2 / 2.7, 3)
    conflicts = client.get(f"/skus/{sku_id}/conflicts").json()
    assert conflicts and all(c["truth_source"] == "inferred" and c["page_id"] == old_page for c in conflicts)
    assert {c["verdict"] for c in conflicts} >= {"outdated", "risky"}
    matrix = client.get(f"/skus/{sku_id}/matrix").json()
    assert matrix["truth"]["status"] == "inferred" and matrix["truth"]["label"] == "Inferred truth, unverified"
    rec = next(r for r in _recs(client) if r["rule"] == "add_truth_sheet" and r["sku_id"] == sku_id)
    assert rec["title"] == "Add a truth sheet for Aveeno Daily Oat Wash"
    assert rec["link"] == f"/products/{sku_id}/truth?prefill=inferred" and rec["action_label"]


def test_approving_the_truth_sheet_recomputes(checked, client, session):
    sku_id, old_page = _product_without_truth(client, session)
    client.post(f"/skus/{sku_id}/run")
    before = client.get(f"/skus/{sku_id}").json()
    draft = client.get(f"/skus/{sku_id}/inferred-truth").json()["fields"]
    # The reviewer corrects the inferred ingredients: the older page was right after all.
    approved = {**draft, "ingredients": OLD}
    s = client.post(f"/skus/{sku_id}/truth-sheet", json={"claims": approved, "evidence_url": "https://www.aveeno.com/x"}).json()
    assert s["truth_status"] == "approved" and s["inferred_method"] is None
    assert session.query(InferredTruth).filter_by(sku_id=sku_id).count() == 0
    open_conflicts = [c for c in client.get(f"/skus/{sku_id}/conflicts").json() if c["status"] != "verified"]
    assert open_conflicts and all(c["truth_source"] == "approved" for c in open_conflicts)
    assert {c["page_id"] for c in open_conflicts if c["field"] == "ingredients"} == {p for p in {c["page_id"] for c in open_conflicts} if p != old_page}
    session.expire_all()
    assert session.query(Conflict).filter_by(sku_id=sku_id, truth_source="inferred", status="verified").count() >= 1
    assert s["drift_score"] != before["drift_score"]
    assert not any(r["rule"] == "add_truth_sheet" and r["sku_id"] == sku_id for r in _recs(client))
    assert client.post(f"/skus/{sku_id}/truth-sheet", json={"claims": {"name": "x"}}).status_code == 422


def test_claude_chooses_among_page_values(checked, client, session, monkeypatch):
    sku_id, _ = _product_without_truth(client, session)

    class Fake:
        class beta:  # noqa: N801
            class messages:  # noqa: N801
                @staticmethod
                def create(**kw):
                    picks = {"choices": [{"field": "ingredients", "index": 1}, {"field": "free_from", "index": 0}]}
                    return SimpleNamespace(stop_reason="end_turn", content=[SimpleNamespace(type="text", text=json.dumps(picks))])

    from app.models import Sku

    sku = session.get(Sku, sku_id)
    row = refresh_inferred(session, sku, env={"ANTHROPIC_API_KEY": "k"}, anthropic_client=Fake)
    session.commit()
    assert row.method == "claude" and row.fields["ingredients"] == OLD  # the minority value, chosen, never invented
    assert client.get(f"/skus/{sku_id}").json()["inferred_method"] == "claude"


def test_truth_sheet_summary(checked, client, session):
    sku_id, _ = _product_without_truth(client, session)
    rows = {r["sku_id"]: r for r in client.get("/truth-sheets").json()}
    assert set(rows[checked["CeraVe"]]["fields"]) >= {"ingredients", "free_from"}
    assert sku_id not in rows  # no approved claims yet
