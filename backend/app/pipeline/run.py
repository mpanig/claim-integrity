"""Run the comparison for one SKU over its latest stored extraction per page."""

import json
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import ApprovedClaim, Conflict, ConflictStatus, Extraction, Sku, Snapshot
from app.pipeline.compare import Finding, compare


def truth_for_sku(session: Session, sku: Sku) -> dict[str, Any]:
    claims = session.scalars(
        select(ApprovedClaim).where(ApprovedClaim.sku_id == sku.id).order_by(ApprovedClaim.id)
    )
    truth = {c.field: c.value for c in claims}  # later approvals of a field win
    truth.setdefault("name", sku.name)
    return truth


def latest_extractions(session: Session, sku_id: int) -> dict[int, Extraction]:
    """page_id -> newest extraction for this SKU on that page."""
    rows = session.execute(
        select(Snapshot.page_id, Extraction)
        .join(Snapshot, Extraction.snapshot_id == Snapshot.id)
        .where(Extraction.sku_id == sku_id)
        .order_by(Snapshot.fetched_at.desc(), Extraction.id.desc())
    )
    latest: dict[int, Extraction] = {}
    for page_id, extraction in rows:
        latest.setdefault(page_id, extraction)
    return latest


def _key(page_id: int, f: Finding | Conflict) -> tuple:
    # JSONB does not keep dict key order, so compare values as sorted JSON.
    dump = lambda v: json.dumps(v, sort_keys=True)  # noqa: E731
    return (page_id, f.field, f.verdict, dump(f.page_value), dump(f.truth_value))


def run_for_sku(session: Session, sku: Sku) -> list[Conflict]:
    """Replace this SKU's open conflicts with fresh ones and commit.

    Conflicts a person already triaged (accepted, fixed, dismissed, ...) are kept, and
    the same finding is not raised again as a new open conflict.
    """
    session.execute(
        delete(Conflict).where(Conflict.sku_id == sku.id, Conflict.status == ConflictStatus.open)
    )
    triaged = {
        _key(c.page_id, c)
        for c in session.scalars(select(Conflict).where(Conflict.sku_id == sku.id))
    }

    truth = truth_for_sku(session, sku)
    created = []
    for page_id, extraction in latest_extractions(session, sku.id).items():
        page_fields = {name: f.get("value") for name, f in extraction.fields.items()}
        for finding in compare(truth, page_fields):
            if _key(page_id, finding) in triaged:
                continue
            conflict = Conflict(
                organisation_id=sku.organisation_id,
                sku_id=sku.id,
                page_id=page_id,
                field=finding.field,
                page_value=finding.page_value,
                truth_value=finding.truth_value,
                verdict=finding.verdict,
                severity=finding.severity,
            )
            session.add(conflict)
            created.append(conflict)
    session.commit()
    return created
