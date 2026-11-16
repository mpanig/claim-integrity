"""Background worker: keeps trend history real.

Every few minutes it
  1. re-checks each product not checked in the last CHECK_INTERVAL_HOURS (default 24).
     Every check writes a score snapshot, which is what the trend charts plot.
  2. runs saved AI test plans whose daily/weekly schedule is due (engines with keys only).

Run it next to the API:   uv run python -m app.worker
Or one pass from cron:    uv run python -m app.worker --once
Demo history stays flagged; real snapshots build up alongside it.
"""

import argparse
import os
import time
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.config import SYSTEM_USER
from app.models import JobRun, Sku
from app.pipeline.run import run_for_sku

TICK_SECONDS = 300


def check_interval() -> timedelta:
    return timedelta(hours=float(os.environ.get("CHECK_INTERVAL_HOURS", "24")))


def _job(session: Session, name: str, fn) -> JobRun:
    job = JobRun(name=name)
    session.add(job)
    session.commit()
    try:
        job.detail = fn()
        job.status = "done"
    except Exception as e:  # recorded, never crashes the worker
        session.rollback()
        job.status = "failed"
        job.detail = {"error": f"{type(e).__name__}: {e}"[:500]}
    job.finished_at = datetime.now(UTC)
    session.commit()
    return job


def product_checks(session: Session, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    cutoff = now - check_interval()
    due = session.scalars(select(Sku).where(or_(Sku.last_checked_at.is_(None), Sku.last_checked_at < cutoff)).order_by(Sku.id)).all()
    for sku in due:
        run_for_sku(session, sku, actor=SYSTEM_USER)
    return {"checked": len(due), "products": [s.name for s in due]}


def ai_plans(session: Session, env: dict[str, str] | None = None) -> dict[str, Any]:
    from app.ai.schedule import run_due

    runs = run_due(session, env=env)
    return {"runs": [{"id": r.id, "status": r.status, "answers": r.done_calls, "cost_usd": r.cost_usd} for r in runs]}


def run_once(session: Session, *, env: dict[str, str] | None = None, now: datetime | None = None) -> list[JobRun]:
    return [
        _job(session, "product_checks", lambda: product_checks(session, now)),
        _job(session, "ai_plans", lambda: ai_plans(session, env)),
    ]


def main() -> None:
    from app.db import SessionLocal

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--once", action="store_true", help="run one pass and exit (for cron)")
    args = parser.parse_args()
    while True:
        with SessionLocal() as s:
            for job in run_once(s):
                print(f"{job.finished_at:%Y-%m-%d %H:%M} {job.name}: {job.status} {job.detail}", flush=True)
        if args.once:
            return
        time.sleep(TICK_SECONDS)


if __name__ == "__main__":
    main()
