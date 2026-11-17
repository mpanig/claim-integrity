"""Where a SKU's truth comes from.

approved  the SKU has a truth sheet: approved claims for at least one compared field other than
          its name. Pages and AI answers are compared against it (unchanged behaviour).
inferred  no truth sheet yet: a provisional truth from what the SKU's sources agree on, stored in
          InferredTruth and shown everywhere as unverified. Per field, the value with the most page
          weight behind it wins (majority); with ANTHROPIC_API_KEY set, Claude may instead choose
          among the values the pages actually show (it never writes new ones). The result is cached
          by the set of extractions it was built from, so Claude is only asked again when pages change.
none      no truth sheet and no sources to infer from.

Approving a truth sheet replaces the inferred truth (see app.api.skus.save_truth_sheet).
"""

import hashlib
import json
from collections import defaultdict
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import ApprovedClaim, Extraction, InferredTruth, Page, Sku, Snapshot
from app.pipeline.compare import COMPARED_FIELDS, _KEYS, name_key, normalise_ingredient


def has_truth_sheet(session: Session, sku_id: int) -> bool:
    return session.scalar(
        select(ApprovedClaim.id).where(ApprovedClaim.sku_id == sku_id, ApprovedClaim.field != "name").limit(1)
    ) is not None


def truth_status(session: Session, sku_id: int) -> str:
    if has_truth_sheet(session, sku_id):
        return "approved"
    return "inferred" if session.scalar(select(InferredTruth.id).where(InferredTruth.sku_id == sku_id)) else "none"


def _norm(field: str, value: Any) -> str:
    """Values that mean the same thing get the same key (renamed INCI names, wording drift)."""
    if field == "name":
        return name_key(str(value))
    if field == "ingredients":
        return json.dumps(sorted({normalise_ingredient(i) for i in value or []}))
    if field in _KEYS:
        return json.dumps(sorted({_KEYS[field](x) for x in value or []}))
    return json.dumps(value, sort_keys=True)


def _empty(v: Any) -> bool:
    return v in (None, "", [], {})


def _sources(session: Session, sku_id: int) -> list[tuple[int, str, float, dict[str, Any]]]:
    """(extraction id, page label, page weight, field values) for the latest extraction per page."""
    rows = session.execute(
        select(Extraction, Page)
        .join(Snapshot, Extraction.snapshot_id == Snapshot.id)
        .join(Page, Snapshot.page_id == Page.id)
        .where(Extraction.sku_id == sku_id)
        .order_by(Snapshot.fetched_at.desc(), Extraction.id.desc())
    ).all()
    seen, out = set(), []
    for ex, page in rows:
        if page.id in seen:
            continue
        seen.add(page.id)
        values = {f: (ex.fields.get(f) or {}).get("value") for f in COMPARED_FIELDS}
        out.append((ex.id, page.retailer or page.url, page.weight or 1.0, values))
    return out


def majority(sources: list[tuple[int, str, float, dict[str, Any]]]) -> tuple[dict[str, Any], dict[str, float], dict[str, list[dict[str, Any]]]]:
    """Per field: winning value, its share of page weight, and every candidate (for review or Claude)."""
    fields, agreement, candidates = {}, {}, {}
    for f in COMPARED_FIELDS:
        groups: dict[str, dict[str, Any]] = defaultdict(lambda: {"weight": 0.0, "pages": [], "value": None, "best": -1.0})
        for _id, label, weight, values in sources:
            v = values.get(f)
            if _empty(v):
                continue
            g = groups[_norm(f, v)]
            g["weight"] += weight
            g["pages"].append(label)
            if weight > g["best"]:
                g["best"], g["value"] = weight, v
        if not groups:
            continue
        total = sum(g["weight"] for g in groups.values())
        ranked = sorted(groups.values(), key=lambda g: (-g["weight"], -len(g["pages"])))
        fields[f] = ranked[0]["value"]
        agreement[f] = round(ranked[0]["weight"] / total, 3)
        candidates[f] = [{"value": g["value"], "weight": round(g["weight"], 2), "pages": g["pages"]} for g in ranked]
    return fields, agreement, candidates


def _claude_pick(sku: Sku, candidates: dict[str, list[dict[str, Any]]], env: dict[str, str], client: Any = None) -> dict[str, int]:
    """Ask Claude which candidate value per field is most likely the manufacturer's current one."""
    import anthropic

    schema = {
        "type": "object",
        "properties": {
            "choices": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"field": {"type": "string", "enum": list(candidates)}, "index": {"type": "integer"}},
                    "required": ["field", "index"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["choices"],
        "additionalProperties": False,
    }
    listing = "\n".join(
        f"{f}:\n" + "\n".join(f"  [{i}] {json.dumps(c['value'], ensure_ascii=False)} (page weight {c['weight']}; from {', '.join(c['pages'])})" for i, c in enumerate(cs))
        for f, cs in candidates.items()
    )
    ask = (
        f"Product: {sku.name}. Several web pages describe it and disagree. For each field, pick the index of the value "
        "most likely to match the manufacturer's current product (brand sites and pages with higher weight are usually more "
        "reliable; old formulas linger on retailer pages). Only choose from the listed values.\n\n" + listing
    )
    client = client or anthropic.Anthropic(api_key=env.get("ANTHROPIC_API_KEY"))
    resp = client.beta.messages.create(
        model="claude-opus-5-5",
        max_tokens=2000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": ask}],
    )
    data = json.loads(next(b.text for b in resp.content if b.type == "text"))
    return {c["field"]: c["index"] for c in data.get("choices", []) if 0 <= c["index"] < len(candidates.get(c["field"], []))}


def refresh_inferred(session: Session, sku: Sku, *, env: dict[str, str] | None = None, anthropic_client: Any = None) -> InferredTruth | None:
    """Build or update the inferred truth for a SKU without a truth sheet. Removes it if one exists."""
    if has_truth_sheet(session, sku.id):
        session.execute(delete(InferredTruth).where(InferredTruth.sku_id == sku.id))
        return None
    sources = _sources(session, sku.id)
    row = session.scalar(select(InferredTruth).where(InferredTruth.sku_id == sku.id))
    if not sources:
        if row:
            session.delete(row)
        return None
    if env is None:
        from app.ai.engines import engine_env

        env = engine_env()
    use_claude = bool(env.get("ANTHROPIC_API_KEY"))
    digest = hashlib.sha256(json.dumps([s[0] for s in sorted(sources)] + [use_claude]).encode()).hexdigest()
    if row and row.source_hash == digest:
        return row
    fields, agreement, candidates = majority(sources)
    method = "majority"
    if use_claude and any(len(c) > 1 for c in candidates.values()):
        try:
            picks = _claude_pick(sku, {f: c for f, c in candidates.items() if len(c) > 1}, env, anthropic_client)
            for f, i in picks.items():
                fields[f] = candidates[f][i]["value"]
                agreement[f] = round(candidates[f][i]["weight"] / sum(c["weight"] for c in candidates[f]), 3)
            method = "claude"
        except Exception:  # noqa: BLE001 - fall back to the majority; never block a check
            method = "majority"
    if row is None:
        row = InferredTruth(sku_id=sku.id)
        session.add(row)
    row.fields, row.agreement, row.method, row.sources, row.source_hash = fields, agreement, method, len(sources), digest
    session.flush()
    return row


def inferred_for(session: Session, sku_id: int) -> InferredTruth | None:
    if has_truth_sheet(session, sku_id):
        return None
    return session.scalar(select(InferredTruth).where(InferredTruth.sku_id == sku_id))


def inferred_claims(session: Session, sku_id: int) -> dict[str, Any]:
    """Inferred values as a draft truth sheet (fields with a value), for the editor."""
    row = inferred_for(session, sku_id)
    return {} if row is None else {f: v for f, v in row.fields.items() if not _empty(v)}
