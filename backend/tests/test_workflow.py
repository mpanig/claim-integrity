"""Conflict status transitions, re-check reconciliation, owners, notes and history."""

import pytest


def _conflict(client, sku_id, field):
    return next(c for c in client.get(f"/skus/{sku_id}/conflicts").json() if c["field"] == field)


@pytest.mark.parametrize(
    "path, bad",
    [
        ([], "fixed"),
        ([], "verified"),
        (["accepted"], "dismissed"),
        (["accepted"], "verified"),
        (["accepted", "fixed"], "accepted"),
        (["accepted", "fixed", "verified"], "open"),
    ],
)
def test_invalid_transitions_are_rejected(checked, client, path, bad):
    cid = _conflict(client, checked["CeraVe"], "ingredients")["id"]
    for status in path:
        assert client.patch(f"/conflicts/{cid}", json={"status": status}).status_code == 200
    r = client.patch(f"/conflicts/{cid}", json={"status": bad})
    assert r.status_code == 409
    assert client.get(f"/conflicts/{cid}").json()["status"] == (path[-1] if path else "open")


def test_allowed_transitions_are_listed(checked, client):
    cid = _conflict(client, checked["CeraVe"], "ingredients")["id"]
    assert client.get(f"/conflicts/{cid}").json()["allowed_transitions"] == ["accepted", "dismissed"]
    client.patch(f"/conflicts/{cid}", json={"status": "accepted"})
    assert client.get(f"/conflicts/{cid}").json()["allowed_transitions"] == ["fixed"]


def test_accept_fix_verify(checked, client):
    cid = _conflict(client, checked["CeraVe"], "ingredients")["id"]
    for status in ("accepted", "fixed", "verified"):
        r = client.patch(f"/conflicts/{cid}", json={"status": status})
        assert r.status_code == 200 and r.json()["status"] == status


def test_fixed_but_still_found_is_reopened_on_recheck(checked, client):
    sku_id = checked["CeraVe"]
    cid = _conflict(client, sku_id, "ingredients")["id"]
    client.patch(f"/conflicts/{cid}", json={"status": "accepted"})
    client.patch(f"/conflicts/{cid}", json={"status": "fixed"})

    run = client.post(f"/skus/{sku_id}/run").json()
    assert run["reopened"] == 1
    assert client.get(f"/conflicts/{cid}").json()["status"] == "open"
    last = client.get(f"/conflicts/{cid}/history").json()[-1]
    assert (last["actor"], last["detail"]["to"], last["detail"]["reason"]) == (
        "system", "open", "still found on re-check"
    )


def test_conflict_no_longer_found_is_verified_on_recheck(checked, client):
    sku_id = checked["CeraVe"]
    cid = _conflict(client, sku_id, "free_from")["id"]
    # Approve the retailer's wording, so the drift disappears: saving re-checks straight away.
    client.put(f"/skus/{sku_id}/claims/free_from", json={"value": ["Fragrance Free"]})
    assert client.get(f"/conflicts/{cid}").json()["status"] == "verified"
    run = client.post(f"/skus/{sku_id}/run").json()
    assert (run["resolved"], run["unresolved"]) == (0, 1)


def test_owner_due_date_notes_and_history(checked, client):
    cid = _conflict(client, checked["CeraVe"], "ingredients")["id"]
    r = client.patch(f"/conflicts/{cid}", json={"owner": "Priya (e-commerce)", "due_date": "2026-12-01"})
    assert (r.json()["owner"], r.json()["due_date"]) == ("Priya (e-commerce)", "2026-12-01")

    # Sending only status leaves owner untouched; sending owner: null clears it.
    client.patch(f"/conflicts/{cid}", json={"status": "accepted"})
    assert client.get(f"/conflicts/{cid}").json()["owner"] == "Priya (e-commerce)"
    assert client.patch(f"/conflicts/{cid}", json={"owner": None}).json()["owner"] is None

    assert client.post(f"/conflicts/{cid}/notes", json={"text": "  "}).status_code == 422
    history = client.post(f"/conflicts/{cid}/notes", json={"text": "Emailed Rite Aid content team"}).json()
    actions = [e["action"] for e in history]
    assert actions == ["detected", "assigned", "due_date", "status", "assigned", "note"]
    assert history[-1]["detail"]["text"] == "Emailed Rite Aid content team"
    assert history[-1]["actor"] == "Demo CMO"


def test_unknown_conflict_404(db_engine, client):
    assert client.get("/conflicts/999999").status_code == 404
    assert client.patch("/conflicts/999999", json={"status": "accepted"}).status_code == 404
    assert client.get("/conflicts/999999/history").status_code == 404
