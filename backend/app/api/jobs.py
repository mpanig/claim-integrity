from typing import Any

from fastapi import APIRouter
from sqlalchemy import select

from app.api.common import DB
from app.models import JobRun, RunConfig
from app.worker import check_interval

router = APIRouter()

JOBS = {
    "product_checks": "Re-check every product (writes score history)",
    "ai_plans": "Run scheduled AI test plans",
}


@router.get("/jobs")
def jobs(session: DB) -> dict[str, Any]:
    """Last run of each background job, and what is scheduled."""
    out = []
    for name, label in JOBS.items():
        last = session.scalar(select(JobRun).where(JobRun.name == name).order_by(JobRun.started_at.desc(), JobRun.id.desc()).limit(1))
        out.append(
            {
                "name": name,
                "label": label,
                "last_started_at": last.started_at if last else None,
                "last_finished_at": last.finished_at if last else None,
                "last_status": last.status if last else None,
                "last_detail": last.detail if last else None,
            }
        )
    scheduled = session.scalars(select(RunConfig).where(RunConfig.schedule != "none")).all()
    return {
        "check_interval_hours": check_interval().total_seconds() / 3600,
        "jobs": out,
        "scheduled_plans": [{"id": c.id, "name": c.name, "schedule": c.schedule, "last_run_at": c.last_run_at} for c in scheduled],
    }
