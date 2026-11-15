def test_search(checked, client):
    r = client.get("/search", params={"q": "aveeno"}).json()
    assert [p["name"] for p in r["products"]] == ["Aveeno Calm + Restore Nourishing Oat Cleanser"]
    assert {p["label"] for p in r["pages"]} == {"Hannaford", "Kenvue Pro"}
    assert r["pages"][0]["sku_ids"] == [checked["Aveeno"]]
    assert len(r["conflicts"]) == 8  # capped

    # Conflicts match on what the page says.
    r = client.get("/search", params={"q": "paraben"}).json()
    assert {c["page_label"] for c in r["conflicts"]} == {"Rite Aid", "Hannaford"}
    assert r["products"] == [] and r["pages"] == []

    r = client.get("/search", params={"q": "rite"}).json()
    assert [p["label"] for p in r["pages"]] == ["Rite Aid"]
    assert client.get("/search", params={"q": "x"}).status_code == 422


def test_bulk_actions(checked, client):
    ids = [c["id"] for c in client.get("/conflicts", params={"sku_id": checked["Aveeno"]}).json()]
    assert len(ids) == 10

    r = client.post("/conflicts/bulk", json={"ids": ids[:3], "action": "assign", "owner": "Priya (E-commerce)"}).json()
    assert r == {"done": 3, "skipped": []}

    r = client.post("/conflicts/bulk", json={"ids": ids[:3], "action": "accept"}).json()
    assert r == {"done": 3, "skipped": []}

    # Already accepted ones can't be dismissed: they are skipped, the rest are dismissed.
    assert client.post("/conflicts/bulk", json={"ids": ids, "action": "dismiss"}).status_code == 422
    r = client.post("/conflicts/bulk", json={"ids": ids[:5] + [999999], "action": "dismiss", "reason": "Legal approved"}).json()
    assert r["done"] == 2
    reasons = {s["id"]: s["reason"] for s in r["skipped"]}
    assert reasons[999999] == "not found"
    assert reasons[ids[0]] == "cannot move a conflict from accepted to dismissed"

    statuses = {c["id"]: c["status"] for c in client.get("/conflicts", params={"sku_id": checked["Aveeno"]}).json()}
    assert [statuses[i] for i in ids[:5]] == ["accepted"] * 3 + ["dismissed"] * 2
