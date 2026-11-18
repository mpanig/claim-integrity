"""Follow-up after a Glean agent load (app.agent_sync) and the worker switch-off."""

from datetime import UTC, datetime

from sqlalchemy import select, text

from app.agent_sync import after_drift_load
from app.models import Alert, AuditEvent, Conflict, ConflictStatus, Extraction, Sku, Snapshot, Verdict
from app.worker import product_checks

RUN_AT = datetime(2026, 11, 18, 9, 0, tzinfo=UTC)


def _agent_load(session, sku_id: int) -> tuple[Conflict, Conflict]:
    """What the drift agent's CSV load leaves behind: conflicts stamped with run_at, one drift_score row."""
    sku = session.get(Sku, sku_id)
    page_id = session.scalar(
        select(Snapshot.page_id).join(Extraction, Extraction.snapshot_id == Snapshot.id).where(Extraction.sku_id == sku_id).limit(1)
    )
    new = Conflict(organisation_id=sku.organisation_id, sku_id=sku_id, page_id=page_id, field="claims", page_value="vegan",
                   truth_value=None, verdict=Verdict.risky, severity=9, status=ConflictStatus.open, detected_at=RUN_AT,
                   truth_source="inferred")
    gone = Conflict(organisation_id=sku.organisation_id, sku_id=sku_id, page_id=page_id, field="seals", page_value=None,
                    truth_value="leaping bunny", verdict=Verdict.weaker, severity=4, status=ConflictStatus.verified,
                    detected_at=datetime(2026, 11, 1, tzinfo=UTC), status_changed_at=RUN_AT)
    session.add_all([new, gone])
    session.execute(
        text("""INSERT INTO drift_score (organisation_id, brand_id, sku_id, taken_at, score, weighted_severity, page_weight,
                 unresolved, by_verdict, by_status, truth_source, truth, agent_run_id)
                VALUES (:o, :b, :s, :t, 96, 9, 1, 1, '{}', '{}', 'inferred', '{"name": "X", "claims": ["vegan"]}', 'glean-1')"""),
        {"o": sku.organisation_id, "b": sku.brand_id, "s": sku_id, "t": RUN_AT},
    )
    session.commit()
    return new, gone


def test_drift_follow_up_writes_history_alerts_and_last_checked(seeded, session):
    sku_id = seeded["Aveeno"]
    new, gone = _agent_load(session, sku_id)

    assert after_drift_load(session, "glean-1") == {"products": 1, "new": 1, "reopened": 0, "resolved": 1, "alerts": 1}

    events = session.scalars(select(AuditEvent).where(AuditEvent.sku_id == sku_id)).all()
    assert [(e.conflict_id, e.action) for e in events if e.conflict_id] == [(new.id, "detected"), (gone.id, "status")]
    run = next(e for e in events if e.action == "check_run")
    assert run.detail["new"] == 1 and run.detail["resolved"] == 1
    alert = session.scalar(select(Alert).where(Alert.conflict_id == new.id))
    assert alert.kind == "high_risk"
    assert session.get(Sku, sku_id).last_checked_at == RUN_AT

    # Running it again changes nothing.
    assert after_drift_load(session)["products"] == 0
    assert len(session.scalars(select(AuditEvent).where(AuditEvent.sku_id == sku_id)).all()) == len(events)


def test_drift_source_from_env_file(tmp_path, monkeypatch):
    import app.worker as worker

    monkeypatch.delenv("DRIFT_SOURCE", raising=False)
    monkeypatch.setattr(worker, "BACKEND_DIR", tmp_path)
    assert worker.drift_source() == "app"
    (tmp_path / ".env").write_text("DRIFT_SOURCE=agent\n")
    assert worker.drift_source() == "agent"
    monkeypatch.setenv("DRIFT_SOURCE", "app")  # the shell wins
    assert worker.drift_source() == "app"


def test_worker_leaves_checks_to_the_drift_agent(seeded, session, monkeypatch):
    monkeypatch.setenv("DRIFT_SOURCE", "agent")
    assert product_checks(session) == {"checked": 0, "skipped": "DRIFT_SOURCE=agent: the Glean drift agent checks products"}
    assert session.scalar(select(Conflict.id).where(Conflict.sku_id.in_(seeded.values())).limit(1)) is None
