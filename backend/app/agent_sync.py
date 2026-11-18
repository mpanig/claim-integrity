"""Follow-up after a Glean agent load, so the app looks the same as after its own check run.

The drift agent writes `conflict` and `drift_score` (seen by the app as `score_snapshot`). A check run
in the app also writes history lines, alerts, the inferred truth and the "last checked" date.
`drift` does those for the agent's rows, reusing the app's own functions:

  - history: "detected" for each new conflict, "status" for each reopened or resolved one,
    one "check_run" per product (with new / reopened / resolved counts)
  - alerts: new high-risk conflicts and score drops (services.alerts.alerts_for_run)
  - inferred truth: refreshed from the pages (majority, no Claude call), with the fields set to the
    truth the agent compared against (drift_score.truth) when the product has no truth sheet
  - sku.last_checked_at = the run time

A conflict counts as new / reopened / resolved when its detected_at / status_changed_at equals the
run time (drift_score.taken_at), as the drift agent spec sets them. Each drift_score row is handled
once: its id is stored on the check_run event, so running this twice changes nothing.

`aeo` runs the AEO alert evaluation after an aeo_response load.

  uv run python -m app.agent_sync drift [--run <agent_run_id>]
  uv run python -m app.agent_sync aeo
"""

import argparse
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import SYSTEM_USER
from app.models import AuditEvent, Conflict, ConflictStatus, ScoreSnapshot, Sku
from app.services.alerts import alerts_for_run
from app.services.workflow import log, log_conflict

S = ConflictStatus


def _pending(session: Session, agent_run_id: str | None) -> list[Any]:
    """Agent-written drift_score rows not yet followed up, oldest first."""
    done = select(AuditEvent.detail["drift_score_id"].as_integer()).where(
        AuditEvent.action == "check_run", AuditEvent.detail.has_key("drift_score_id")
    )
    done_ids = {i for i in session.scalars(done) if i is not None}
    rows = session.execute(
        text(
            "SELECT id, sku_id, taken_at, truth_source, truth FROM drift_score "
            "WHERE agent_run_id IS NOT NULL AND (CAST(:run AS text) IS NULL OR agent_run_id = :run) "
            "ORDER BY taken_at, id"
        ),
        {"run": agent_run_id},
    ).all()
    return [r for r in rows if r.id not in done_ids]


def _set_inferred(session: Session, sku: Sku, row: Any) -> None:
    from app.pipeline.truth import refresh_inferred

    inferred = refresh_inferred(session, sku, env={})
    if inferred is not None and row.truth_source == "inferred" and row.truth:
        inferred.fields = {f: v for f, v in row.truth.items() if f != "name"} | (
            {"name": inferred.fields["name"]} if "name" in inferred.fields else {}
        )


def after_drift_load(session: Session, agent_run_id: str | None = None) -> dict[str, Any]:
    out = {"products": 0, "new": 0, "reopened": 0, "resolved": 0, "alerts": 0}
    for row in _pending(session, agent_run_id):
        sku = session.get(Sku, row.sku_id)
        if sku is None:
            continue
        at = row.taken_at
        conflicts = session.scalars(select(Conflict).where(Conflict.sku_id == sku.id)).all()
        new = [c for c in conflicts if c.detected_at == at and c.status is S.open]
        reopened = [c for c in conflicts if c.status is S.open and c.status_changed_at == at and c.detected_at != at]
        resolved = [c for c in conflicts if c.status is S.verified and c.status_changed_at == at]
        for c in sorted(new, key=lambda c: c.id):
            log_conflict(session, c, "detected", SYSTEM_USER, verdict=c.verdict.value)
        for c in reopened:
            log_conflict(session, c, "status", SYSTEM_USER, to=S.open.value, reason="still found on re-check")
        for c in resolved:
            log_conflict(session, c, "status", SYSTEM_USER, to=S.verified.value, reason="no longer found on re-check")

        _set_inferred(session, sku, row)
        if sku.last_checked_at is None or sku.last_checked_at < at:
            sku.last_checked_at = at
        snapshot = session.get(ScoreSnapshot, row.id)
        alerts = alerts_for_run(session, sku, new, snapshot) if snapshot is not None else []
        log(
            session,
            organisation_id=sku.organisation_id,
            sku_id=sku.id,
            action="check_run",
            actor=SYSTEM_USER,
            detail={"new": len(new), "reopened": len(reopened), "resolved": len(resolved), "drift_score_id": row.id},
        )
        session.commit()
        out["products"] += 1
        out["new"] += len(new)
        out["reopened"] += len(reopened)
        out["resolved"] += len(resolved)
        out["alerts"] += len(alerts)
    return out


def after_aeo_load(session: Session) -> dict[str, Any]:
    from app.ai.aeo_alerts import evaluate

    return {"alerts": len(evaluate(session))}


def main() -> None:
    from app.db import SessionLocal

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("step", choices=["drift", "aeo"])
    parser.add_argument("--run", help="only this Glean run (drift_score.agent_run_id)")
    args = parser.parse_args()
    with SessionLocal() as s:
        print(after_drift_load(s, args.run) if args.step == "drift" else after_aeo_load(s), flush=True)


if __name__ == "__main__":
    main()
