from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from sqlalchemy import func, select, update
from sqlalchemy.orm import selectinload

from app.api.common import DB, get_or_404
from app.models import Alert, Brand, Sku

router = APIRouter()


def _scope(stmt, brand_id: int | None, kind_prefix: str | None = None):
    if kind_prefix:
        stmt = stmt.where(Alert.kind.startswith(kind_prefix))
    if brand_id is None:
        return stmt
    return stmt.where(Alert.sku_id.in_(select(Sku.id).where(Sku.brand_id == brand_id)) | (Alert.brand_id == brand_id))


@router.get("/alerts")
def list_alerts(session: DB, brand_id: int | None = None, unread_only: bool = False, limit: int = 100, kind_prefix: str | None = None) -> dict[str, Any]:
    stmt = _scope(select(Alert).options(selectinload(Alert.sku)), brand_id, kind_prefix)
    if unread_only:
        stmt = stmt.where(Alert.read_at.is_(None))
    alerts = session.scalars(stmt.order_by(Alert.created_at.desc(), Alert.id.desc()).limit(limit)).all()
    unread = session.scalar(_scope(select(func.count()).select_from(Alert).where(Alert.read_at.is_(None)), brand_id, kind_prefix))
    brands = {b.id: b.name for b in session.scalars(select(Brand))}
    return {
        "unread": unread,
        "items": [
            {
                "id": a.id,
                "kind": a.kind,
                "title": a.title,
                "body": a.body,
                "sku_id": a.sku_id,
                "sku_name": a.sku.name if a.sku else None,
                "brand_name": brands.get(a.brand_id) if a.brand_id else (brands.get(a.sku.brand_id) if a.sku else None),
                "link": a.link,
                "is_demo": a.is_demo,
                "conflict_id": a.conflict_id,
                "created_at": a.created_at.isoformat(),
                "read": a.read_at is not None,
            }
            for a in alerts
        ],
    }


@router.post("/alerts/{alert_id}/read")
def mark_read(alert_id: int, session: DB, read: bool = True) -> dict[str, bool]:
    a = get_or_404(session, Alert, alert_id, "alert")
    a.read_at = datetime.now(UTC) if read else None
    session.commit()
    return {"read": a.read_at is not None}


@router.post("/alerts/read-all")
def mark_all_read(session: DB, brand_id: int | None = None) -> dict[str, int]:
    stmt = _scope(update(Alert).where(Alert.read_at.is_(None)), brand_id).values(read_at=datetime.now(UTC))
    n = session.execute(stmt.execution_options(synchronize_session=False)).rowcount
    session.commit()
    return {"marked": n}
