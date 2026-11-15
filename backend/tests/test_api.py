"""Summary, matrix, conflict listing and SKU / approved-claim CRUD."""


def test_summary_scores(checked, client):
    s = client.get("/summary").json()
    brands = {b["name"]: b for b in s["brands"]}
    # CeraVe: (6 + 1) / (10 x 5 fields x 1.0)            -> 86
    # Aveeno: (1 + 5x9 + 9 + 0.7 x 3x9) / (10 x 5 x 1.7) -> 13
    assert (brands["CeraVe"]["score"], brands["Aveeno"]["score"]) == (86, 13)
    assert s["overall"]["score"] == 40
    assert s["overall"]["unresolved"] == 12
    assert s["overall"]["by_verdict"]["risky"] == 9
    assert s["overall"]["by_status"]["open"] == 12
    assert len(s["top"]) == 5 and all(c["verdict"] == "risky" for c in s["top"])
    assert {e["action"] for e in s["activity"]} == {"check_run"}

    only_cerave = client.get("/summary", params={"brand_id": brands["CeraVe"]["id"]}).json()
    assert [b["name"] for b in only_cerave["brands"]] == ["CeraVe"]
    assert only_cerave["overall"]["score"] == 86


def test_summary_before_any_check_scores_100(seeded, client):
    s = client.get("/summary").json()
    assert s["overall"]["unresolved"] == 0
    assert s["overall"]["score"] == 100  # pages exist, nothing found yet


def test_matrix(checked, client):
    m = client.get(f"/skus/{checked['CeraVe']}/matrix").json()
    assert m["fields"] == ["name", "ingredients", "free_from", "claims", "seals"]
    assert m["truth"]["url"].startswith("https://www.cerave.com/")
    [rite_aid] = m["sources"]
    states = {f: cell["state"] for f, cell in rite_aid["cells"].items()}
    assert states == {
        "name": "match",
        "ingredients": "bad",
        "free_from": "warn",
        "claims": "match",
        "seals": "match",
    }
    assert rite_aid["cells"]["ingredients"]["conflicts"][0]["verdict"] == "outdated"
    assert "Methylparaben" in rite_aid["cells"]["ingredients"]["quote"]

    aveeno = client.get(f"/skus/{checked['Aveeno']}/matrix").json()
    assert [s["label"] for s in aveeno["sources"]] == ["Hannaford", "Kenvue Pro"]
    hannaford = aveeno["sources"][0]["cells"]
    assert hannaford["seals"]["state"] == "na"
    assert hannaford["free_from"]["state"] == "bad"
    assert len(hannaford["free_from"]["conflicts"]) == 5


def test_conflict_filters(checked, client):
    brands = {b["name"]: b["id"] for b in client.get("/brands").json()}
    assert len(client.get("/conflicts").json()) == 12
    assert len(client.get("/conflicts", params={"brand_id": brands["CeraVe"]}).json()) == 2
    assert len(client.get("/conflicts", params={"verdict": ["risky", "drift"]}).json()) == 11
    assert client.get("/conflicts", params={"status": "accepted"}).json() == []
    detail = client.get(f"/conflicts/{client.get('/conflicts').json()[0]['id']}").json()
    assert detail["quote"] and detail["truth_evidence_url"] and detail["page_fetched_at"]


def test_sku_crud_and_claims(db_engine, seeded, client):
    r = client.post(
        "/skus",
        json={
            "brand_name": "La Roche-Posay",
            "name": "Toleriane Hydrating Gentle Cleanser",
            "gtin": "00000000000000",
            "claims": {"ingredients": ["Aqua/Water", "Glycerin"], "free_from": ["Fragrance Free"]},
            "evidence_url": "https://example.com/toleriane",
        },
    )
    assert r.status_code == 201, r.text
    sku = r.json()
    assert (sku["brand_name"], sku["score"], sku["pages"]) == ("La Roche-Posay", None, 0)
    sid = sku["id"]

    claims = {c["field"]: c for c in client.get(f"/skus/{sid}/claims").json()}
    assert claims["free_from"]["value"] == ["Fragrance Free"]
    assert claims["free_from"]["approved_by"] == "Demo CMO"

    put = client.put(f"/skus/{sid}/claims/seals", json={"value": [" NEA Seal of Acceptance ", ""]})
    assert put.status_code == 200 and put.json()["value"] == ["NEA Seal of Acceptance"]
    client.put(f"/skus/{sid}/claims/free_from", json={"value": ["Fragrance Free", "Paraben Free"]})
    claims = {c["field"]: c["value"] for c in client.get(f"/skus/{sid}/claims").json()}
    assert claims["free_from"] == ["Fragrance Free", "Paraben Free"]

    assert client.put(f"/skus/{sid}/claims/colour", json={"value": ["red"]}).status_code == 422
    assert client.put(f"/skus/{sid}/claims/ingredients", json={"value": []}).status_code == 422
    assert client.put(f"/skus/{sid}/claims/name", json={"value": ["x"]}).status_code == 422
    assert client.delete(f"/skus/{sid}/claims/name").status_code == 422

    assert client.delete(f"/skus/{sid}/claims/seals").status_code == 204
    assert client.delete(f"/skus/{sid}/claims/seals").status_code == 404

    client.put(f"/skus/{sid}/claims/name", json={"value": "Toleriane Gentle Cleanser"})
    assert client.get(f"/skus/{sid}").json()["name"] == "Toleriane Gentle Cleanser"
    assert client.patch(f"/skus/{sid}", json={"line": "Toleriane"}).json()["line"] == "Toleriane"
    assert [s["name"] for s in client.get("/skus", params={"q": "toleriane"}).json()] == [
        "Toleriane Gentle Cleanser"
    ]

    assert client.delete(f"/skus/{sid}").status_code == 204
    assert client.get(f"/skus/{sid}").status_code == 404


def test_create_sku_needs_brand(db_engine, client):
    assert client.post("/skus", json={"name": "x"}).status_code == 422
    assert client.post("/skus", json={"brand_id": 999999, "name": "x"}).status_code == 404
