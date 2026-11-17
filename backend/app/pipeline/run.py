"""Re-check one SKU: compare its latest extraction per page against the truth and
reconcile the result with the conflicts already stored."""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import SYSTEM_USER
from app.models import ApprovedClaim, Conflict, ConflictStatus, Extraction, Sku, Snapshot
from app.pipeline.compare import Finding, compare
from app.services.alerts import alerts_for_run
from app.services.trends import take_snapshot
from app.services.workflow import log, log_conflict, set_status

S = ConflictStatus


def truth_for_sku(session: Session, sku: Sku, *, include_inferred: bool = True) -> dict[str, Any]:
    """The approved truth sheet; for a SKU without one, the stored inferred truth (unverified),
    unless include_inferred is False (places that must only state approved facts)."""
    claims = session.scalars(
        select(ApprovedClaim).where(ApprovedClaim.sku_id == sku.id).order_by(ApprovedClaim.id)
    )
    truth = {c.field: c.value for c in claims}  # later approvals of a field win
    if include_inferred and not any(f != "name" for f in truth):
        from app.pipeline.truth import inferred_for

        row = inferred_for(session, sku.id)
        if row:
            truth = {**row.fields, **truth}  # an approved name still wins
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


def page_fields(extraction: Extraction) -> dict[str, Any]:
    return {name: f.get("value") for name, f in extraction.fields.items()}


def _key(page_id: int, f: Finding | Conflict) -> tuple:
    # JSONB does not keep dict key order, so compare values as sorted JSON.
    dump = lambda v: json.dumps(v, sort_keys=True)  # noqa: E731
    return (page_id, f.field, f.verdict, dump(f.page_value), dump(f.truth_value))


@dataclass
class RunResult:
    new: list[Conflict] = field(default_factory=list)
    reopened: list[Conflict] = field(default_factory=list)
    resolved: list[Conflict] = field(default_factory=list)


def run_for_sku(session: Session, sku: Sku, actor: str = SYSTEM_USER) -> RunResult:
    """Compare and reconcile, then commit.

    - a finding with no matching conflict becomes a new open conflict
    - open/accepted conflicts no longer found are marked verified
    - fixed conflicts are verified if gone, reopened if still found
    - dismissed conflicts stay dismissed and are not raised again
    - verified conflicts are history: if the finding comes back, a new conflict is opened
    """
    from app.pipeline.truth import has_truth_sheet, refresh_inferred

    refresh_inferred(session, sku)  # no truth sheet: build the provisional truth from the sources
    source = "approved" if has_truth_sheet(session, sku.id) else "inferred"
    truth = truth_for_sku(session, sku)
    findings: dict[tuple, tuple[int, Finding]] = {}
    for page_id, extraction in latest_extractions(session, sku.id).items():
        for finding in compare(truth, page_fields(extraction)):
            findings[_key(page_id, finding)] = (page_id, finding)

    result = RunResult()
    existing = session.scalars(
        select(Conflict).where(Conflict.sku_id == sku.id, Conflict.status != S.verified)
    ).all()
    seen: set[tuple] = set()
    for conflict in existing:
        key = _key(conflict.page_id, conflict)
        present = key in findings
        seen.add(key)
        if present:
            conflict.truth_source = source
        if conflict.status is S.dismissed:
            continue
        if conflict.status is S.fixed and present:
            set_status(session, conflict, S.open, SYSTEM_USER, "still found on re-check")
            result.reopened.append(conflict)
        elif not present:
            set_status(session, conflict, S.verified, SYSTEM_USER, "no longer found on re-check")
            result.resolved.append(conflict)

    for key, (page_id, finding) in findings.items():
        if key in seen:
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
            status=S.open,
            truth_source=source,
        )
        session.add(conflict)
        session.flush()
        log_conflict(session, conflict, "detected", SYSTEM_USER, verdict=finding.verdict.value)
        result.new.append(conflict)

    sku.last_checked_at = datetime.now(UTC)
    snapshot = take_snapshot(session, sku)
    session.flush()
    alerts_for_run(session, sku, result.new, snapshot)
    log(
        session,
        organisation_id=sku.organisation_id,
        sku_id=sku.id,
        action="check_run",
        actor=actor,
        detail={"new": len(result.new), "reopened": len(result.reopened), "resolved": len(result.resolved)},
    )
    session.commit()
    return result
