from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.common import DB
from app.models import Conflict, ConflictStatus
from app.services.recommendations import OWNER_TYPES, build
from app.services.workflow import add_note, assign, change_status, set_due_date

router = APIRouter()


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    conflict_ids: list[int] = Field(min_length=1)
    owner: str | None = None
    due_date: date | None = None


@router.get("/recommendations")
def recommendations(session: DB, brand_id: int | None = None) -> dict[str, Any]:
    return {"owner_types": OWNER_TYPES, "items": build(session, brand_id)}


@router.post("/recommendations/task")
def create_task(body: TaskIn, session: DB) -> dict[str, int]:
    """Turn a recommendation into work: accept its open conflicts, set owner/due date, note why."""
    conflicts = session.scalars(select(Conflict).where(Conflict.id.in_(body.conflict_ids))).all()
    if len(conflicts) != len(set(body.conflict_ids)):
        raise HTTPException(404, "one or more conflicts not found")
    accepted = 0
    for c in conflicts:
        if c.status is ConflictStatus.open:
            change_status(session, c, ConflictStatus.accepted)
            accepted += 1
        if body.owner:
            assign(session, c, body.owner.strip())
        if body.due_date:
            set_due_date(session, c, body.due_date)
        add_note(session, c, f"Task created from recommendation: {body.title}")
    session.commit()
    return {"accepted": accepted, "conflicts": len(conflicts)}
