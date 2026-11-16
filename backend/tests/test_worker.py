"""Background worker: scheduled product checks write real score history."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import JobRun, RunConfig, ScoreSnapshot, Sku


def test_worker_checks_due_products_and_records_jobs(checked, client, session):
    from app.worker import run_once

    # Just checked: nothing is due yet.
    jobs = run_once(session, env={})
    assert [(j.name, j.status) for j in jobs] == [("product_checks", "done"), ("ai_plans", "done")]
    assert jobs[0].detail == {"checked": 0, "products": []}

    # A day later both products are due; each check adds a real (non-demo) snapshot.
    before = len(session.scalars(select(ScoreSnapshot)).all())
    jobs = run_once(session, env={}, now=datetime.now(UTC) + timedelta(hours=25))
    assert jobs[0].detail["checked"] == 2
    snaps = session.scalars(select(ScoreSnapshot)).all()
    assert len(snaps) == before + 2 and not any(s.is_demo for s in snaps)

    status = client.get("/jobs").json()
    assert status["check_interval_hours"] == 24
    assert {j["name"]: j["last_status"] for j in status["jobs"]} == {"product_checks": "done", "ai_plans": "done"}


def test_worker_runs_due_ai_plans_without_spending_when_no_keys(checked, session):
    from app.worker import run_once

    cfg = session.scalar(select(RunConfig))
    cfg.schedule = "daily"
    session.commit()
    jobs = run_once(session, env={})
    assert jobs[1].detail == {"runs": []}  # no engine keys: nothing runs
    session.refresh(cfg)
    assert cfg.last_run_at is not None


def test_failing_job_is_recorded_not_raised(checked, session, monkeypatch):
    import app.worker as worker

    monkeypatch.setattr(worker, "product_checks", lambda s, now=None: (_ for _ in ()).throw(RuntimeError("boom")))
    jobs = worker.run_once(session, env={})
    assert jobs[0].status == "failed" and "boom" in jobs[0].detail["error"]
    assert jobs[1].status == "done"
    assert session.scalar(select(JobRun).where(JobRun.status == "failed")) is not None
    assert session.scalars(select(Sku)).first() is not None
