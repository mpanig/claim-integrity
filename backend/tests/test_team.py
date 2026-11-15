def test_team_crud(seeded, client):
    t = client.get("/team").json()
    assert t["roles"]["ecommerce"] == "E-commerce"
    assert t["owner_type_role"]["regulatory"] == "regulatory"
    names = [m["name"] for m in t["members"]]
    assert "Priya (E-commerce)" in names and len(names) == 6
    sam = next(m for m in t["members"] if m["name"].startswith("Sam"))
    assert (sam["role_label"], sam["brand_name"]) == ("Brand manager", "CeraVe")

    r = client.post("/team", json={"name": "Robin", "email": "robin@example.com", "role": "agency"})
    assert r.status_code == 201 and r.json()["role_label"] == "Agency"
    rid = r.json()["id"]
    assert client.post("/team", json={"name": "Robin", "role": "agency"}).status_code == 409
    assert client.post("/team", json={"name": "X", "role": "owner"}).status_code == 422
    assert client.post("/team", json={"name": "X", "role": "cmo", "email": "not-an-email"}).status_code == 422

    brands = {b["name"]: b["id"] for b in client.get("/brands").json()}
    p = client.patch(f"/team/{rid}", json={"role": "brand_manager", "brand_id": brands["Aveeno"]}).json()
    assert (p["role"], p["brand_name"], p["email"]) == ("brand_manager", "Aveeno", "robin@example.com")
    assert client.patch(f"/team/{rid}", json={"brand_id": None}).json()["brand_name"] is None

    assert client.delete(f"/team/{rid}").status_code == 204
    assert client.delete(f"/team/{rid}").status_code == 404
