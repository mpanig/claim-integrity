"""Deterministic comparison of one page's extracted fields against the approved truth.

Both inputs are plain dicts of field -> value (quotes already stripped):
    name: str
    ingredients: list[str]          (INCI order)
    free_from: list[str]            e.g. ["Free of Added Fragrance"]
    claims: list[str]               e.g. ["Non-comedogenic"]
    seals: list[str]                e.g. ["NEA Seal of Acceptance"]

Rules, per field present in the truth or on the page:
    field in truth but absent on page ............ missing
    ingredients: different set after renames ..... outdated
    ingredients: same set, other names/order ..... drift
    list fields: item on page, not in truth ...... risky
    list fields: truth item not on page .......... weaker
    list fields: same item, other wording ........ drift
    free_from item contradicted by page INCI ..... contradiction
    name differs after normalising ............... drift
"""

import re
from dataclasses import dataclass
from typing import Any

from app.models import SEVERITY, Verdict

INGREDIENT_RENAMES = {
    "aqua/water/eau": "water",
    "water/aqua/eau": "water",
    "aqua": "water",
    "purified water": "water",
    "ceramide 3": "ceramide np",
    "ceramide 6-ii": "ceramide ap",
    "ceramide 6 ii": "ceramide ap",
    "ceramide 1": "ceramide eop",
    "hyaluronic acid": "sodium hyaluronate",
}

# Only free-from claims we can check against an INCI list; others are never called contradictions.
FREE_FROM_MARKERS = {
    "fragrance": ("fragrance", "parfum"),
    "paraben": ("paraben",),
}

SEAL_ALIASES = {
    "national eczema association seal of acceptance": "nea seal of acceptance",
    "national eczema association seal": "nea seal of acceptance",
    "nea seal": "nea seal of acceptance",
}

_FREE_FROM_STOPWORDS = {"free", "of", "from", "added", "no", "without"}
LIST_FIELDS = ("free_from", "claims", "seals")
COMPARED_FIELDS = ("name", "ingredients", *LIST_FIELDS)


@dataclass(frozen=True)
class Finding:
    field: str
    verdict: Verdict
    page_value: Any
    truth_value: Any

    @property
    def severity(self) -> int:
        return SEVERITY[self.verdict]


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _basic_ingredient(name: str) -> str:
    s = re.sub(r"\s+", " ", name.strip().lower())
    s = re.sub(r"\s*/\s*", "/", s)
    return s.rstrip(".")


def normalise_ingredient(name: str) -> str:
    s = _basic_ingredient(name)
    return INGREDIENT_RENAMES.get(s, s)


def free_from_key(claim: str) -> str:
    key = " ".join(w for w in _words(claim) if w not in _FREE_FROM_STOPWORDS)
    if key.endswith("s") and not key.endswith("ss"):
        key = key[:-1]
    return key


def seal_key(seal: str) -> str:
    key = " ".join(_words(seal))
    return SEAL_ALIASES.get(key, key)


def claim_key(claim: str) -> str:
    return "".join(_words(claim))


def name_key(name: str) -> str:
    return " ".join(_words(name))


_KEYS = {"free_from": free_from_key, "claims": claim_key, "seals": seal_key}


def _same_wording(a: str, b: str) -> bool:
    return " ".join(a.lower().split()) == " ".join(b.lower().split())


def _is_empty(value: Any) -> bool:
    return value is None or value == "" or value == []


def compare_ingredients(truth: list[str], page: list[str]) -> Finding | None:
    t = [normalise_ingredient(i) for i in truth]
    p = [normalise_ingredient(i) for i in page]
    if set(t) != set(p):
        detail = {
            "value": page,
            "not_in_truth": sorted(set(p) - set(t)),
            "not_on_page": sorted(set(t) - set(p)),
        }
        return Finding("ingredients", Verdict.outdated, detail, truth)
    if p != t or [_basic_ingredient(i) for i in page] != [_basic_ingredient(i) for i in truth]:
        # Same ingredients, but old INCI names or a different order.
        return Finding("ingredients", Verdict.drift, page, truth)
    return None


def compare_list(field: str, truth: list[str], page: list[str]) -> list[Finding]:
    key = _KEYS[field]
    t = {key(x): x for x in truth}
    p = {key(x): x for x in page}
    findings = [Finding(field, Verdict.risky, p[k], None) for k in sorted(p.keys() - t.keys())]
    findings += [Finding(field, Verdict.weaker, None, t[k]) for k in sorted(t.keys() - p.keys())]
    findings += [
        Finding(field, Verdict.drift, p[k], t[k])
        for k in sorted(t.keys() & p.keys())
        if not _same_wording(p[k], t[k])
    ]
    return findings


def free_from_contradictions(free_from: list[str], ingredients: list[str]) -> list[Finding]:
    normalised = [normalise_ingredient(i) for i in ingredients]
    findings = []
    for claim in free_from:
        markers = FREE_FROM_MARKERS.get(free_from_key(claim), ())
        hits = [i for i in normalised if any(m in i for m in markers)]
        if hits:
            findings.append(
                Finding("free_from", Verdict.contradiction, {"claim": claim, "ingredients": hits}, None)
            )
    return findings


def compare(truth: dict[str, Any], page: dict[str, Any]) -> list[Finding]:
    findings: list[Finding] = []

    for field in COMPARED_FIELDS:
        if not _is_empty(truth.get(field)) and _is_empty(page.get(field)):
            findings.append(Finding(field, Verdict.missing, None, truth[field]))

    if not _is_empty(page.get("name")) and "name" in truth:
        if name_key(page["name"]) != name_key(truth["name"]):
            findings.append(Finding("name", Verdict.drift, page["name"], truth["name"]))

    if not _is_empty(page.get("ingredients")) and "ingredients" in truth:
        finding = compare_ingredients(truth["ingredients"], page["ingredients"])
        if finding:
            findings.append(finding)

    for field in LIST_FIELDS:
        if not _is_empty(page.get(field)):
            findings += compare_list(field, truth.get(field, []), page[field])

    if page.get("free_from") and page.get("ingredients"):
        findings += free_from_contradictions(page["free_from"], page["ingredients"])

    return sorted(findings, key=lambda f: (-f.severity, f.field))
