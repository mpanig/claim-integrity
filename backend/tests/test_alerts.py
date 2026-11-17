"""Alerts from check runs, read/unread."""


def test_new_high_risk_conflicts_raise_alerts(checked, client):
    a = client.get("/alerts").json()
    # 9 unapproved claims on Aveeno pages; CeraVe has only outdated + drift (not high risk).
    assert a["unread"] == 9
    assert {x["kind"] for x in a["items"]} == {"high_risk"}
    assert all(x["sku_name"].startswith("Aveeno") for x in a["items"])
    assert any(x["title"] == "An unapproved claim on Kenvue Pro" for x in a["items"])

    # A re-check finds nothing new, so no new alerts.
    client.post(f"/skus/{checked['Aveeno']}/run")
    assert client.get("/alerts").json()["unread"] == 9


def test_score_drop_alert(checked, client):
    sku = checked["CeraVe"]
    # Approving a seal the page doesn't show makes the score drop (one more open issue).
    client.put(f"/skus/{sku}/claims/seals", json={"value": ["NEA Seal of Acceptance", "Vegan Society"]})
    assert client.post(f"/skus/{sku}/run").json()["score"] == 78  # (6 + 1 + 4) / 50 -> 78
    drops = [x for x in client.get("/alerts").json()["items"] if x["kind"] == "score_drop"]
    assert [d["title"] for d in drops] == ["CeraVe Hydrating Facial Cleanser drift score rose 8 points"]
    assert drops[0]["body"] == "Drift score went from 14 to 22 after the latest check (0 = no drift)."

    # Small moves (under 5 points) don't alert: removing the extra seal raises the score back.
    client.put(f"/skus/{sku}/claims/seals", json={"value": ["NEA Seal of Acceptance"]})
    client.post(f"/skus/{sku}/run")
    assert len([x for x in client.get("/alerts").json()["items"] if x["kind"] == "score_drop"]) == 1


def test_read_and_unread(checked, client):
    brands = {b["name"]: b["id"] for b in client.get("/brands").json()}
    first = client.get("/alerts").json()["items"][0]
    assert client.post(f"/alerts/{first['id']}/read").json() == {"read": True}
    assert client.get("/alerts").json()["unread"] == 8
    assert client.post(f"/alerts/{first['id']}/read", params={"read": False}).json() == {"read": False}
    assert len(client.get("/alerts", params={"unread_only": True}).json()["items"]) == 9

    assert client.get("/alerts", params={"brand_id": brands["CeraVe"]}).json()["unread"] == 0
    assert client.post("/alerts/read-all").json() == {"marked": 9}
    assert client.get("/alerts").json()["unread"] == 0
    assert client.post("/alerts/999999/read").status_code == 404
