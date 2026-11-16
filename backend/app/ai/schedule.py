"""Recurring runs: run every saved plan whose schedule is due. Call from cron, e.g. hourly:

  uv run python -m app.ai.schedule

Plans run only for engines with keys; with none, nothing is spent.
"""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.engines import engine_env
from app.ai.plan import PlanConfig, estimate
from app.ai.runner import execute
from app.models import AiRun, RunConfig

PERIOD = {"daily": timedelta(days=1), "weekly": timedelta(days=7)}


def due(session: Session, now: datetime | None = None) -> list[RunConfig]:
    now = now or datetime.now(UTC)
    configs = session.scalars(select(RunConfig).where(RunConfig.schedule.in_(list(PERIOD)))).all()
    return [c for c in configs if c.last_run_at is None or now - c.last_run_at >= PERIOD[c.schedule]]


def run_due(session: Session, env: dict[str, str] | None = None, **execute_kwargs) -> list[AiRun]:
    env = engine_env() if env is None else env
    runs = []
    for c in due(session):
        cfg = PlanConfig.model_validate(c.config)
        est = estimate(session, cfg, env)
        c.last_run_at = datetime.now(UTC)
        if est["runnable_calls"] == 0:
            session.commit()
            continue
        run = AiRun(organisation_id=c.organisation_id, run_config_id=c.id, config=c.config, budget_usd=c.budget_usd, est_cost_usd=est["est_usd"])
        session.add(run)
        session.commit()
        runs.append(execute(session, run, env=env, **execute_kwargs))
    return runs


if __name__ == "__main__":
    from app.db import SessionLocal

    with SessionLocal() as s:
        done = run_due(s)
        print(f"ran {len(done)} scheduled plan(s)" + "".join(f"\n  run {r.id}: {r.status}, {r.done_calls} answers, ${r.cost_usd:.2f}" for r in done))
