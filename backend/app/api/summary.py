from typing import Any

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.common import DB, conflict_out, conflict_query, events_out
from app.models import AuditEvent, Conflict, ConflictStatus, Page, Sku
from app.services.scoring import UNRESOLVED, Tally, sku_tallies
from app.services.trends import mean_days_to_fix, weekly_trends

router = APIRouter()


@router.get("/summary")
def summary(session: DB, brand_id: int | None = None) -> dict[str, Any]:
    sku_stmt = select(Sku).options(selectinload(Sku.brand))
    if brand_id is not None:
        sku_stmt = sku_stmt.where(Sku.brand_id == brand_id)
    skus = session.scalars(sku_stmt).all()
    sku_ids = [s.id for s in skus]
    tallies = sku_tallies(session, sku_ids)

    overall = Tally()
    brands: dict[int, dict[str, Any]] = {}
    for sku in skus:
        tally = tallies.get(sku.id, Tally())
        overall.add(tally)
        entry = brands.setdefault(sku.brand_id, {"id": sku.brand_id, "name": sku.brand.name, "tally": Tally(), "skus": 0})
        entry["tally"].add(tally)
        entry["skus"] += 1

    by_status = {s.value: 0 for s in ConflictStatus}
    for status, count in session.execute(
        select(Conflict.status, func.count()).where(Conflict.sku_id.in_(sku_ids)).group_by(Conflict.status)
    ):
        by_status[status.value] = count

    top = session.scalars(
        conflict_query()
        .join(Page, Conflict.page_id == Page.id)
        .where(
            Conflict.sku_id.in_(sku_ids),
            Conflict.status.in_((ConflictStatus.open, ConflictStatus.accepted)),
        )
        .order_by((Conflict.severity * Page.weight).desc(), Conflict.detected_at.desc())
        .limit(5)
    ).all()

    activity = session.scalars(
        select(AuditEvent)
        .where(AuditEvent.sku_id.in_(sku_ids), AuditEvent.action != "detected")
        .order_by(AuditEvent.at.desc(), AuditEvent.id.desc())
        .limit(15)
    ).all()

    by_source = session.execute(
        select(Page.id, Page.retailer, Page.url, func.count())
        .join(Conflict, Conflict.page_id == Page.id)
        .where(Conflict.sku_id.in_(sku_ids), Conflict.status.in_(UNRESOLVED))
        .group_by(Page.id)
        .order_by(func.count().desc())
    ).all()

    return {
        "overall": {
            "score": overall.score,
            "unresolved": overall.unresolved,
            "by_verdict": overall.by_verdict,
            "by_status": by_status,
            "skus": len(skus),
            "pages": overall.pages,
            "mean_days_to_fix": mean_days_to_fix(session, sku_ids),
        },
        "by_source": [
            {"page_id": pid, "label": retailer or url, "unresolved": n} for pid, retailer, url, n in by_source
        ],
        "brands": [
            {"id": b["id"], "name": b["name"], "score": b["tally"].score, "unresolved": b["tally"].unresolved, "skus": b["skus"]}
            for b in sorted(brands.values(), key=lambda b: b["name"])
        ],
        "top": [conflict_out(c).model_dump(mode="json") for c in top],
        "activity": [e.model_dump(mode="json") for e in events_out(session, list(activity))],
    }


@router.get("/trends")
def trends(session: DB, brand_id: int | None = None, weeks: int = Query(12, ge=1, le=104)) -> dict[str, Any]:
    """Weekly score, open and fixed counts. `demo` is true if any generated history was used."""
    stmt = select(Sku).options(selectinload(Sku.brand))
    if brand_id is not None:
        stmt = stmt.where(Sku.brand_id == brand_id)
    return weekly_trends(session, list(session.scalars(stmt)), weeks)

