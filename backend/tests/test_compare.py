import json

from app.models import Verdict
from app.pipeline.compare import (
    compare,
    free_from_key,
    normalise_ingredient,
    seal_key,
)
from app.seed import MANUAL_EXTRACTIONS, RITEAID_URL, TRUTH


def verdicts(findings):
    return sorted((f.field, f.verdict.value) for f in findings)


def test_normalise_ingredient_case_whitespace_and_renames():
    assert normalise_ingredient("  Cetearyl   ALCOHOL ") == "cetearyl alcohol"
    assert normalise_ingredient("Aqua / Water / Eau") == "water"
    assert normalise_ingredient("Purified Water") == "water"
    assert normalise_ingredient("Ceramide 3") == "ceramide np"
    assert normalise_ingredient("Ceramide 6-II") == "ceramide ap"
    assert normalise_ingredient("Ceramide 1") == "ceramide eop"
    assert normalise_ingredient("Hyaluronic Acid") == "sodium hyaluronate"


def test_free_from_and_seal_keys():
    assert free_from_key("Fragrance Free") == free_from_key("Free of Added Fragrance") == "fragrance"
    assert free_from_key("Parabens-Free") == "paraben"
    assert seal_key("National Eczema Association Seal of Acceptance") == seal_key("NEA Seal of Acceptance")


def test_identical_page_has_no_findings():
    truth = {"name": "Cleanser", "ingredients": ["Water", "Glycerin"], "free_from": ["Paraben Free"]}
    assert compare(truth, dict(truth)) == []


def test_old_inci_names_only_is_drift_not_outdated():
    truth = {"ingredients": ["Aqua/Water/Eau", "Ceramide NP", "Sodium Hyaluronate"]}
    page = {"ingredients": ["Purified Water", "Ceramide 3", "Hyaluronic Acid"]}
    assert verdicts(compare(truth, page)) == [("ingredients", "drift")]


def test_reordered_ingredients_is_drift():
    truth = {"ingredients": ["Water", "Glycerin"]}
    assert verdicts(compare(truth, {"ingredients": ["Glycerin", "Water"]})) == [("ingredients", "drift")]


def test_different_ingredient_set_is_outdated_with_diff():
    truth = {"ingredients": ["Water", "Glycerin", "Phenoxyethanol"]}
    page = {"ingredients": ["Water", "Glycerin", "Methylparaben"]}
    [finding] = compare(truth, page)
    assert finding.verdict is Verdict.outdated and finding.severity == 6
    assert finding.page_value["not_in_truth"] == ["methylparaben"]
    assert finding.page_value["not_on_page"] == ["phenoxyethanol"]


def test_free_from_wording_is_drift():
    [f] = compare({"free_from": ["Free of Added Fragrance"]}, {"free_from": ["Fragrance Free"]})
    assert (f.verdict, f.severity, f.page_value, f.truth_value) == (
        Verdict.drift, 1, "Fragrance Free", "Free of Added Fragrance"
    )


def test_unapproved_free_from_is_risky_and_dropped_one_is_weaker():
    truth = {"free_from": ["Fragrance Free"]}
    page = {"free_from": ["Sulfate Free"]}
    assert verdicts(compare(truth, page)) == [("free_from", "risky"), ("free_from", "weaker")]


def test_free_from_contradicted_by_page_ingredients():
    truth = {"free_from": ["Paraben Free"], "ingredients": ["Water", "Methylparaben"]}
    page = {"free_from": ["Paraben Free"], "ingredients": ["Water", "Methylparaben"]}
    [f] = compare(truth, page)
    assert f.verdict is Verdict.contradiction and f.severity == 10
    assert f.page_value == {"claim": "Paraben Free", "ingredients": ["methylparaben"]}


def test_seals():
    truth = {"seals": ["NEA Seal of Acceptance"]}
    assert compare(truth, {"seals": ["National Eczema Association Seal of Acceptance"]})[0].verdict is Verdict.drift
    assert verdicts(compare(truth, {"seals": ["Vegan Certified"]})) == [("seals", "risky"), ("seals", "weaker")]


def test_missing_field():
    [f] = compare({"seals": ["NEA Seal of Acceptance"]}, {"seals": []})
    assert (f.verdict, f.severity) == (Verdict.missing, 3)


def test_name_drift_ignores_case_and_punctuation():
    truth = {"name": "CeraVe Hydrating Facial Cleanser"}
    assert compare(truth, {"name": "cerave hydrating facial cleanser."}) == []
    assert verdicts(compare(truth, {"name": "CeraVe Hydrating Cleanser"})) == [("name", "drift")]


def test_findings_sorted_by_severity():
    truth = {"name": "A", "free_from": ["Fragrance Free"], "ingredients": ["Water"]}
    page = {"name": "B", "free_from": ["Free of fragrance"], "ingredients": ["Water", "Parfum"]}
    severities = [f.severity for f in compare(truth, page)]
    assert severities == sorted(severities, reverse=True)


def test_pilot_fixture():
    fields = json.loads(MANUAL_EXTRACTIONS.read_text())[RITEAID_URL]
    page = {k: v["value"] for k, v in fields.items()}
    findings = compare({**TRUTH, "name": "CeraVe Hydrating Facial Cleanser"}, page)
    assert verdicts(findings) == [("free_from", "drift"), ("ingredients", "outdated")]
    outdated = next(f for f in findings if f.field == "ingredients")
    assert outdated.page_value["not_in_truth"] == ["methylparaben", "propylparaben"]
    assert outdated.page_value["not_on_page"] == ["ethylhexylglycerin", "phenoxyethanol", "tocopherol"]
