def test_competitor_comparison(checked, client):
    c = client.get("/competitors").json()
    brands = {b["name"]: b for b in c["brands"]}
    assert list(brands) == ["Aveeno", "CeraVe"]

    cerave, aveeno = brands["CeraVe"], brands["Aveeno"]
    assert (cerave["score"], aveeno["score"]) == (86, 13)
    assert (cerave["issues_per_product"], aveeno["issues_per_product"]) == (2.0, 10.0)

    assert cerave["approved"]["free_from"] == ["Free of Added Fragrance"]
    assert cerave["approved"]["seals"] == ["NEA Seal of Acceptance"]
    assert cerave["approved"]["claims"] == ["Non-comedogenic"]
    assert aveeno["approved"]["free_from"] == []

    # Claims seen on pages but not approved, sorted into categories.
    assert sorted(aveeno["unapproved_on_pages"]["clinical"]) == [
        "Colloidal oatmeal skin protectant",
        "Hypoallergenic",
        "Tested on sensitive skin",
    ]
    assert "Sulfate-free" in aveeno["unapproved_on_pages"]["free_from"]
    # Wording drift is not an unapproved claim.
    assert cerave["unapproved_on_pages"]["free_from"] == []

    heat = cerave["heatmap"]
    assert heat["ingredients"] == {"checked": 1, "with_issues": 1, "consistent_pct": 0}
    assert heat["seals"]["consistent_pct"] == 100
    # Aveeno has no approved seals and the pages show none: nothing to compare.
    assert aveeno["heatmap"]["seals"] == {"checked": 0, "with_issues": 0, "consistent_pct": None}
    assert aveeno["heatmap"]["free_from"]["consistent_pct"] == 0
