from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select

from app.api.common import DB, conflict_out, conflict_query, events_out, get_or_404
from app.models import (
    ApprovedClaim,
    AuditEvent,
    Conflict,
    ConflictStatus,
    Extraction,
    Sku,
    Snapshot,
    Verdict,
)
from app.schemas import ConflictDetail, ConflictOut, ConflictPatch, EventOut, NoteIn
from app.services.workflow import TRANSITIONS, WorkflowError, add_note, assign, change_status, set_due_date

router = APIRouter()


def _load(session, conflict_id: int) -> Conflict:
    conflict = session.scalar(conflict_query().where(Conflict.id == conflict_id))
    if conflict is None:
        raise HTTPException(404, "conflict not found")
    return conflict


@router.get("/conflicts", response_model=list[ConflictOut])
def list_conflicts(
    session: DB,
    status: list[ConflictStatus] = Query(default=[]),
    verdict: list[Verdict] = Query(default=[]),
    sku_id: int | None = None,
    brand_id: int | None = None,
    page_id: int | None = None,
    owner: str | None = None,
) -> list[ConflictOut]:
    stmt = conflict_query().join(Sku, Conflict.sku_id == Sku.id)
    if status:
        stmt = stmt.where(Conflict.status.in_(status))
    if verdict:
        stmt = stmt.where(Conflict.verdict.in_(verdict))
    if sku_id is not None:
        stmt = stmt.where(Conflict.sku_id == sku_id)
    if brand_id is not None:
        stmt = stmt.where(Sku.brand_id == brand_id)
    if page_id is not None:
        stmt = stmt.where(Conflict.page_id == page_id)
    if owner:
        stmt = stmt.where(Conflict.owner == owner)
    rows = session.scalars(stmt.order_by(Conflict.severity.desc(), Conflict.detected_at.desc(), Conflict.id))
    return [conflict_out(c) for c in rows]


@router.get("/conflicts/{conflict_id}", response_model=ConflictDetail)
def get_conflict(conflict_id: int, session: DB) -> ConflictDetail:
    c = _load(session, conflict_id)
    latest = session.execute(
        select(Extraction, Snapshot.fetched_at)
        .join(Snapshot, Extraction.snapshot_id == Snapshot.id)
        .where(Extraction.sku_id == c.sku_id, Snapshot.page_id == c.page_id)
        .order_by(Snapshot.fetched_at.desc(), Extraction.id.desc())
        .limit(1)
    ).first()
    quote, fetched_at = None, None
    if latest:
        extraction, fetched_at = latest
        quote = (extraction.fields.get(c.field) or {}).get("quote")
    evidence = session.scalar(
        select(ApprovedClaim.evidence_url)
        .where(ApprovedClaim.sku_id == c.sku_id, ApprovedClaim.field == c.field)
        .order_by(ApprovedClaim.id.desc())
        .limit(1)
    ) or session.scalar(
        select(ApprovedClaim.evidence_url)
        .where(ApprovedClaim.sku_id == c.sku_id, ApprovedClaim.evidence_url.is_not(None))
        .limit(1)
    )
    return ConflictDetail(
        **conflict_out(c).model_dump(),
        quote=quote,
        truth_evidence_url=evidence,
        page_fetched_at=fetched_at,
        allowed_transitions=sorted(TRANSITIONS[c.status], key=lambda s: list(ConflictStatus).index(s)),
    )


@router.patch("/conflicts/{conflict_id}", response_model=ConflictDetail)
def update_conflict(conflict_id: int, body: ConflictPatch, session: DB) -> ConflictDetail:
    c = _load(session, conflict_id)
    sent = body.model_fields_set
    try:
        if "owner" in sent:
            assign(session, c, (body.owner or "").strip() or None)
        if "due_date" in sent:
            set_due_date(session, c, body.due_date)
        if body.status is not None:
            change_status(session, c, body.status, reason=body.reason)
    except WorkflowError as e:
        session.rollback()
        raise HTTPException(409, str(e)) from e
    session.commit()
    return get_conflict(conflict_id, session)


@router.post("/conflicts/{conflict_id}/notes", response_model=list[EventOut], status_code=201)
def post_note(conflict_id: int, body: NoteIn, session: DB) -> list[EventOut]:
    c = _load(session, conflict_id)
    try:
        add_note(session, c, body.text)
    except WorkflowError as e:
        raise HTTPException(422, str(e)) from e
    session.commit()
    return conflict_history(conflict_id, session)


@router.get("/conflicts/{conflict_id}/history", response_model=list[EventOut])
def conflict_history(conflict_id: int, session: DB) -> list[EventOut]:
    get_or_404(session, Conflict, conflict_id, "conflict")
    events = session.scalars(
        select(AuditEvent).where(AuditEvent.conflict_id == conflict_id).order_by(AuditEvent.at, AuditEvent.id)
    ).all()
    return events_out(session, list(events))
