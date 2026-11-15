"""Shared helpers for the API routers."""

from typing import Annotated
from urllib.parse import urlparse

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db import get_session
from app.models import AuditEvent, Conflict, Page, Sku
from app.schemas import ConflictOut, EventOut, SkuOut
from app.services.scoring import Tally

DB = Annotated[Session, Depends(get_session)]


def get_or_404(session: Session, model: type, id_: int, what: str):
    obj = session.get(model, id_)
    if obj is None:
        raise HTTPException(404, f"{what} not found")
    return obj


def page_label(page: Page) -> str:
    return page.retailer or urlparse(page.url).hostname or page.url


def sku_out(sku: Sku, tally: Tally | None) -> SkuOut:
    tally = tally or Tally()
    return SkuOut(
        id=sku.id,
        organisation_id=sku.organisation_id,
        brand_id=sku.brand_id,
        brand_name=sku.brand.name,
        gtin=sku.gtin,
        name=sku.name,
        line=sku.line,
        last_checked_at=sku.last_checked_at,
        score=tally.score,
        unresolved=tally.unresolved,
        by_verdict=tally.by_verdict,
        pages=tally.pages,
    )


def conflict_query():
    return select(Conflict).options(
        selectinload(Conflict.sku).selectinload(Sku.brand), selectinload(Conflict.page)
    )


def conflict_out(c: Conflict) -> ConflictOut:
    return ConflictOut(
        id=c.id,
        sku_id=c.sku_id,
        sku_name=c.sku.name,
        brand_id=c.sku.brand_id,
        brand_name=c.sku.brand.name,
        page_id=c.page_id,
        page_url=c.page.url,
        page_label=page_label(c.page),
        source_type=c.page.source_type,
        field=c.field,
        page_value=c.page_value,
        truth_value=c.truth_value,
        verdict=c.verdict,
        severity=c.severity,
        status=c.status,
        owner=c.owner,
        due_date=c.due_date,
        dismiss_reason=c.dismiss_reason,
        detected_at=c.detected_at,
        status_changed_at=c.status_changed_at,
    )


def events_out(session: Session, events: list[AuditEvent]) -> list[EventOut]:
    rows = session.execute(select(Sku.id, Sku.name).where(Sku.id.in_({e.sku_id for e in events})))
    names = {sku_id: name for sku_id, name in rows}
    return [
        EventOut(
            id=e.id,
            sku_id=e.sku_id,
            sku_name=names.get(e.sku_id, ""),
            conflict_id=e.conflict_id,
            actor=e.actor,
            action=e.action,
            detail=e.detail,
            at=e.at,
        )
        for e in events
    ]
