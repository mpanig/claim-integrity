"""Brand perception: which attributes AI answers attach to each brand, vs intended positioning.

For each answer and brand, the sentences that name the brand are checked against a fixed
attribute lexicon (English keywords; other languages are not matched yet). Product names
right after the brand ("CeraVe Hydrating Facial Cleanser") are removed first so a product
name doesn't count as the attribute. Rate = answers associating the attribute with the brand
/ answers naming the brand.

Gaps for a brand with a positioning: intended attributes AI rarely associates (below
WEAK), and unintended attributes it often does (at or above STRONG), negatives first.
"""

import re
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.analyse import load_entities
from app.ai.insights import rate, select_answers
from app.ai.score import SENTENCE
from app.models import Brand, Organisation

# key: (label, polarity, keywords regex)
ATTRIBUTES: dict[str, tuple[str, str, str]] = {
    "barrier": ("Ceramides / skin barrier", "positive", r"ceramide|skin barrier|barrier repair"),
    "gentle": ("Gentle, mild, soothing", "positive", r"gentle|mild|sooth|calming"),
    "sensitive": ("For sensitive skin", "positive", r"sensitive|reactive"),
    "eczema": ("Eczema-friendly", "positive", r"eczema|atopic"),
    "derm": ("Dermatologist-backed", "positive", r"dermatologist"),
    "hydrating": ("Hydrating", "positive", r"hydrat|moistur|hyaluronic|dry skin|dry patches|very dry"),
    "value": ("Good value", "positive", r"value|affordable|budget|inexpensive|cheap"),
    "natural": ("Oat / natural ingredients", "positive", r"\boat|natural|feverfew|botanical"),
    "fragrance_free": ("Fragrance- and irritant-free", "positive", r"fragrance-free|unscented|free of common irritants|soap-free"),
    "available": ("Easy to find", "positive", r"widely available|easy to find|pharmacy|drugstore"),
    "pricey": ("Pricey", "negative", r"expensive|pricier|pricey|costly"),
    "irritation": ("Irritation / drying", "negative", r"irritat|sting|breakout|drying|harsh"),
    "hard_to_find": ("Hard to find", "negative", r"hard to find|not available"),
}
PATTERNS = {k: re.compile(p, re.I) for k, (_, _, p) in ATTRIBUTES.items()}
WEAK, STRONG = 0.15, 0.25
PRODUCT_AFTER = r"(?:\s+(?:[A-Z][\w'-]*|\+|&))+"  # "CeraVe Hydrating Facial Cleanser"


def attribute_list() -> list[dict[str, str]]:
    return [{"key": k, "label": label, "polarity": pol} for k, (label, pol, _) in ATTRIBUTES.items()]


def perception(session: Session, **filters: Any) -> dict[str, Any]:
    answers, modes = select_answers(session, **filters)
    org = session.scalars(select(Organisation)).first()
    entities = load_entities(session, org.id)[0] if org else []
    brand_rows = {b.name: b for b in session.scalars(select(Brand))}
    plain = {e.name: e.pattern() for e in entities}
    named_with_product = {e.name: re.compile(plain[e.name].pattern + PRODUCT_AFTER, re.I) for e in entities}

    named: dict[str, int] = defaultdict(int)
    hits: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    examples: dict[tuple[str, str], str] = {}
    for a in answers:
        sentences = SENTENCE.split(a.answer or "")
        for e in entities:
            mine = [s for s in sentences if plain[e.name].search(s)]
            if not mine:
                continue
            named[e.name] += 1
            cleaned = [named_with_product[e.name].sub(e.name, s) for s in mine]
            text = " ".join(cleaned)
            for key, pat in PATTERNS.items():
                if pat.search(text):
                    hits[e.name][key] += 1
                    if (e.name, key) not in examples:
                        examples[(e.name, key)] = next(m for m, c in zip(mine, cleaned, strict=True) if pat.search(c)).strip()[:220]

    brands = []
    for e in entities:
        n = named[e.name]
        attrs = {k: {**rate(hits[e.name][k], n), "example": examples.get((e.name, k))} for k in ATTRIBUTES}
        intended = list(brand_rows[e.name].positioning or []) if e.name in brand_rows else []
        gaps = []
        if e.is_own:
            for k in intended:
                r = attrs[k]["rate"] or 0
                if r < WEAK:
                    gaps.append({"attribute": k, "kind": "missing", "rate": r})
            for k, (_, pol, _) in ATTRIBUTES.items():
                r = attrs[k]["rate"] or 0
                if k not in intended and r >= STRONG:
                    gaps.append({"attribute": k, "kind": "unwanted" if pol == "negative" else "unplanned", "rate": r})
            order = {"unwanted": 0, "missing": 1, "unplanned": 2}
            gaps.sort(key=lambda g: (order[g["kind"]], -g["rate"] if g["kind"] != "missing" else g["rate"]))
        # Attributes this brand "owns": its rate is highest among brands.
        brands.append(
            {
                "name": e.name,
                "is_own": e.is_own,
                "brand_id": e.brand_id,
                "answers": n,
                "attributes": attrs,
                "positioning": intended,
                "gaps": gaps,
            }
        )
    leaders = {}
    for k in ATTRIBUTES:
        ranked = sorted((b for b in brands if b["answers"]), key=lambda b: -(b["attributes"][k]["rate"] or 0))
        if ranked and (ranked[0]["attributes"][k]["rate"] or 0) > 0:
            leaders[k] = ranked[0]["name"]
    brands.sort(key=lambda b: (not b["is_own"], -b["answers"]))
    return {
        "answers": len(answers),
        "engines": modes,
        "demo": any(a.is_demo for a in answers),
        "attributes": attribute_list(),
        "brands": brands,
        "leaders": leaders,
        "thresholds": {"weak": WEAK, "strong": STRONG},
    }
