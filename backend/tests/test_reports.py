import csv
import io


def test_weekly_report(checked, client):
    reports = {r["brand"]["name"]: r for r in client.get("/reports/weekly").json()["reports"]}
    assert list(reports) == ["Aveeno", "CeraVe"]
    r = reports["CeraVe"]
    assert (r["score"]["now"], r["score"]["last_week"], r["score"]["change"]) == (86, None, None)
    assert (r["drift"]["now"], r["drift"]["last_week"], r["drift"]["change"]) == (14, None, None)
    assert (r["unresolved"], r["new_issues"], r["fixes_verified"], r["in_progress"]) == (2, 2, 0, 0)
    assert [i["verdict"] for i in r["top_issues"]] == ["outdated", "drift"]
    assert r["products"] == [
        {"id": checked["CeraVe"], "name": "CeraVe Hydrating Facial Cleanser", "score": 86, "change": None, "unresolved": 2,
         "drift_score": 14, "drift_change": None}
    ]
    assert r["demo"] is False

    # Verifying a fix this week shows up in the report.
    cid = r["top_issues"][1]["id"]
    for s in ("accepted", "fixed", "verified"):
        client.patch(f"/conflicts/{cid}", json={"status": s})
    one = client.get("/reports/weekly", params={"brand_id": r["brand"]["id"]}).json()["reports"]
    assert len(one) == 1 and one[0]["fixes_verified"] == 1 and one[0]["unresolved"] == 1
    assert client.get("/reports/weekly", params={"brand_id": 999999}).status_code == 404


def test_report_uses_demo_history_for_last_week(checked, client, session):
    from app.services.trends import generate_demo_history

    generate_demo_history(session)
    r = client.get("/reports/weekly").json()["reports"][0]
    assert r["demo"] is True and r["score"]["last_week"] is not None


def test_issues_csv(checked, client):
    res = client.get("/reports/issues.csv")
    assert res.headers["content-type"].startswith("text/csv")
    assert "attachment" in res.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(res.text)))
    assert rows[0][:3] == ["Brand", "Product", "Page"]
    assert len(rows) == 1 + 12
    cerave = [row for row in rows[1:] if row[0] == "CeraVe"]
    assert cerave[0][5] == "Outdated info" and "methylparaben" in cerave[0][6]

    brands = {b["name"]: b["id"] for b in client.get("/brands").json()}
    only = client.get("/reports/issues.csv", params={"brand_id": brands["CeraVe"]}).text
    assert len(list(csv.reader(io.StringIO(only)))) == 3
