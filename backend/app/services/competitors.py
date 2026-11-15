"""Brand-vs-brand comparison: scores, issues per product, claim coverage, field heatmap."""

import re
from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Conflict, Sku
from app.pipeline.compare import COMPARED_FIELDS, claim_key, free_from_key, seal_key
from app.pipeline.run import latest_extractions, page_fields, truth_for_sku
from app.services.scoring import UNRESOLVED, Tally, sku_tallies

# Performance / testing claims that usually need clinical substantiation.
CLINICAL = re.compile(r"clinic|dermatolog|tested|proven|hypoallergenic|protectant|%|hours?\b", re.I)

KEYS = {"free_from": free_from_key, "claims": claim_key, "seals": seal_key}

CATEGORIES = {
    "free_from": "Free-from claims",
    "seals": "Seals & endorsements",
    "clinical": "Clinical & testing claims",
    "claims": "Other claims",
}


def _categorise(field: str, items: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = defaultdict(list)
    for item in items:
        if field == "claims":
            out["clinical" if CLINICAL.search(item) else "claims"].append(item)
        else:
            out[field].append(item)
    return out


def _add_unique(target: list[str], items: list[str]) -> None:
    seen = {x.lower() for x in target}
    for item in items:
        if item.lower() not in seen:
            target.append(item)
            seen.add(item.lower())


def compare_brands(session: Session) -> dict[str, Any]:
    skus = session.scalars(select(Sku).options(selectinload(Sku.brand)).order_by(Sku.brand_id, Sku.id)).all()
    tallies = sku_tallies(session, [s.id for s in skus])
    open_cells = {
        (c.sku_id, c.page_id, c.field)
        for c in session.scalars(select(Conflict).where(Conflict.status.in_(UNRESOLVED)))
    }

    brands: dict[int, dict[str, Any]] = {}
    for sku in skus:
        b = brands.setdefault(
            sku.brand_id,
            {
                "id": sku.brand_id,
                "name": sku.brand.name,
                "skus": 0,
                "tally": Tally(),
                "approved": {k: [] for k in CATEGORIES},
                "unapproved_on_pages": {k: [] for k in CATEGORIES},
                "cells": {f: [0, 0] for f in COMPARED_FIELDS},  # [checked, with open issue]
            },
        )
        b["skus"] += 1
        b["tally"].add(tallies.get(sku.id) or Tally())

        truth = truth_for_sku(session, sku)
        # Compare with the same normalisation as the rules, so wording drift is not "unapproved".
        approved_keys: dict[str, set[str]] = {}
        for field in ("free_from", "claims", "seals"):
            items = truth.get(field) or []
            approved_keys[field] = {KEYS[field](i) for i in items}
            for cat, vals in _categorise(field, items).items():
                _add_unique(b["approved"][cat], vals)

        for page_id, extraction in latest_extractions(session, sku.id).items():
            fields = page_fields(extraction)
            for field in COMPARED_FIELDS:
                if fields.get(field) in (None, "", []) and truth.get(field) in (None, "", []):
                    continue  # nothing to compare on either side
                b["cells"][field][0] += 1
                if (sku.id, page_id, field) in open_cells:
                    b["cells"][field][1] += 1
            for field in ("free_from", "claims", "seals"):
                extra = [i for i in (fields.get(field) or []) if KEYS[field](i) not in approved_keys[field]]
                for cat, vals in _categorise(field, extra).items():
                    _add_unique(b["unapproved_on_pages"][cat], vals)

    out = []
    for b in brands.values():
        t: Tally = b.pop("tally")
        cells = b.pop("cells")
        out.append(
            {
                **b,
                "score": t.score,
                "unresolved": t.unresolved,
                "pages": t.pages,
                "issues_per_product": round(t.unresolved / b["skus"], 1) if b["skus"] else 0,
                "by_verdict": t.by_verdict,
                "heatmap": {
                    f: {
                        "checked": n,
                        "with_issues": bad,
                        "consistent_pct": round(100 * (n - bad) / n) if n else None,
                    }
                    for f, (n, bad) in cells.items()
                },
            }
        )
    return {"categories": CATEGORIES, "fields": list(COMPARED_FIELDS), "brands": sorted(out, key=lambda b: b["name"])}
