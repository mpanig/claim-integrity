"""Recommendation rules, ranking and the 'Create task' action."""


def recs(client, **params):
    return client.get("/recommendations", params=params).json()["items"]


def by_rule(items):
    out: dict[str, list] = {}
    for r in items:
        out.setdefault(r["rule"], []).append(r)
    return out


def test_pilot_recommendations(checked, client):
    items = recs(client)
    rules = by_rule(items)
    assert set(rules) == {
        "add_free_from",
        "regulatory_review",
        "update_ingredients",
        "unify_name",
        "align_wording",
        "complete_truth_sheet",
    }

    # All unapproved free-from claims for Aveeno roll up into one brand-web action.
    [free_from] = rules["add_free_from"]
    assert free_from["owner_type"] == "brand_web" and free_from["sku_name"].startswith("Aveeno")
    assert len(free_from["conflict_ids"]) == 6
    assert free_from["pages"] == ["Hannaford", "Kenvue Pro"]
    # priority = (5 x 9 x 1.0 + 9 x 0.7) x 0.7
    assert free_from["priority"] == round((45 + 6.3) * 0.7, 2)
    assert free_from["impact_points"] == 60  # 51.3 of a possible 85

    # Clinical / testing claims go to regulatory review, one per claim.
    assert sorted(r["title"] for r in rules["regulatory_review"]) == [
        "Regulatory review of “Colloidal oatmeal skin protectant”",
        "Regulatory review of “Hypoallergenic”",
        "Regulatory review of “Tested on sensitive skin”",
    ]
    assert all(r["owner_type"] == "regulatory" and r["ease"] == 0.4 for r in rules["regulatory_review"])

    [outdated] = rules["update_ingredients"]
    assert (outdated["title"], outdated["owner_type"], outdated["priority"]) == (
        "Update the ingredient list on Rite Aid", "ecommerce", 4.8
    )
    assert outdated["impact_points"] == 12

    [wording] = rules["align_wording"]
    assert "Fragrance Free" in wording["why"] and "Free of Added Fragrance" in wording["why"]

    # Aveeno has no approved free-from, claims or seals: complete the truth sheet.
    [truth] = rules["complete_truth_sheet"]
    assert truth["sku_name"].startswith("Aveeno") and truth["link"].endswith("/truth")
    assert truth["conflict_ids"] == []

    # Ranked by priority, highest first.
    priorities = [r["priority"] for r in items]
    assert priorities == sorted(priorities, reverse=True)
    assert items[0]["rule"] == "add_free_from"


def test_brand_filter(checked, client):
    brands = {b["name"]: b["id"] for b in client.get("/brands").json()}
    assert {r["brand_name"] for r in recs(client, brand_id=brands["CeraVe"])} == {"CeraVe"}


def test_create_task_accepts_conflicts(checked, client):
    [outdated] = by_rule(recs(client))["update_ingredients"]
    r = client.post(
        "/recommendations/task",
        json={"title": outdated["title"], "conflict_ids": outdated["conflict_ids"], "owner": "Priya", "due_date": "2026-12-01"},
    )
    assert r.json() == {"accepted": 1, "conflicts": 1}
    c = client.get(f"/conflicts/{outdated['conflict_ids'][0]}").json()
    assert (c["status"], c["owner"], c["due_date"]) == ("accepted", "Priya", "2026-12-01")
    history = client.get(f"/conflicts/{c['id']}/history").json()
    assert history[-1]["detail"]["text"] == "Task created from recommendation: Update the ingredient list on Rite Aid"

    # The recommendation is now in progress and sorts after open ones.
    items = recs(client)
    moved = next(x for x in items if x["key"] == outdated["key"])
    assert moved["state"] == "in_progress" and items[-1]["key"] == moved["key"]

    assert client.post("/recommendations/task", json={"title": "x", "conflict_ids": [999999]}).status_code == 404


def test_ai_recommendation_is_flagged_demo(checked, client, session):
    from app.ai.demo import generate_demo_answers

    generate_demo_answers(session)
    ai = by_rule(recs(client))["correct_ai_answers"]
    assert {r["owner_type"] for r in ai} == {"pr_editorial"}
    assert all(r["is_demo"] for r in ai)
