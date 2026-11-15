"""Conflict status transitions and the audit log."""

from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.config import PLACEHOLDER_USER
from app.models import AuditEvent, Conflict, ConflictStatus

S = ConflictStatus

# Transitions a person may make. The re-check can also resolve or reopen conflicts.
TRANSITIONS: dict[ConflictStatus, set[ConflictStatus]] = {
    S.open: {S.accepted, S.dismissed},
    S.accepted: {S.fixed},
    S.fixed: {S.verified, S.open},
    S.verified: set(),
    S.dismissed: set(),
}


class WorkflowError(ValueError):
    pass


def log(
    session: Session,
    *,
    organisation_id: int,
    sku_id: int,
    action: str,
    conflict_id: int | None = None,
    detail: dict[str, Any] | None = None,
    actor: str = PLACEHOLDER_USER,
) -> AuditEvent:
    event = AuditEvent(
        organisation_id=organisation_id,
        sku_id=sku_id,
        conflict_id=conflict_id,
        actor=actor,
        action=action,
        detail=detail or {},
    )
    session.add(event)
    return event


def log_conflict(session: Session, conflict: Conflict, action: str, actor: str, **detail: Any) -> None:
    log(
        session,
        organisation_id=conflict.organisation_id,
        sku_id=conflict.sku_id,
        conflict_id=conflict.id,
        action=action,
        detail={k: v for k, v in detail.items() if v is not None},
        actor=actor,
    )


def set_status(
    session: Session, conflict: Conflict, new: ConflictStatus, actor: str, reason: str | None = None
) -> None:
    """Change status without checking TRANSITIONS (used by the re-check)."""
    old = conflict.status
    conflict.status = new
    conflict.status_changed_at = datetime.now(UTC)
    if new is S.dismissed:
        conflict.dismiss_reason = reason
    log_conflict(session, conflict, "status", actor, **{"from": old.value, "to": new.value, "reason": reason})


def change_status(
    session: Session,
    conflict: Conflict,
    new: ConflictStatus,
    *,
    reason: str | None = None,
    actor: str = PLACEHOLDER_USER,
) -> None:
    if new is conflict.status:
        return
    if new not in TRANSITIONS[conflict.status]:
        raise WorkflowError(f"cannot move a conflict from {conflict.status.value} to {new.value}")
    if new is S.dismissed and not (reason and reason.strip()):
        raise WorkflowError("a reason is required to dismiss a conflict")
    set_status(session, conflict, new, actor, reason.strip() if reason else None)


def assign(session: Session, conflict: Conflict, owner: str | None, actor: str = PLACEHOLDER_USER) -> None:
    if owner == conflict.owner:
        return
    conflict.owner = owner
    log_conflict(session, conflict, "assigned", actor, owner=owner)


def set_due_date(
    session: Session, conflict: Conflict, due: date | None, actor: str = PLACEHOLDER_USER
) -> None:
    if due == conflict.due_date:
        return
    conflict.due_date = due
    log_conflict(session, conflict, "due_date", actor, due_date=due.isoformat() if due else None)


def add_note(session: Session, conflict: Conflict, text: str, actor: str = PLACEHOLDER_USER) -> None:
    if not text.strip():
        raise WorkflowError("note is empty")
    log_conflict(session, conflict, "note", actor, text=text.strip())
