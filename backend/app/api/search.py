from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import String, cast, or_, select

from app.api.common import DB, conflict_out, conflict_query, page_label
from app.models import Brand, Conflict, ConflictStatus, Extraction, Page, Snapshot, Sku
from app.services.workflow import WorkflowError, assign, change_status

router = APIRouter()

LIMIT = 8


@router.get("/search")
def search(session: DB, q: str = Query(min_length=2, max_length=100)) -> dict[str, Any]:
    """Products, pages and conflicts matching q (case-insensitive substring)."""
    like = f"%{q.strip()}%"
    products = session.execute(
        select(Sku.id, Sku.name, Brand.name, Sku.gtin)
        .join(Brand, Sku.brand_id == Brand.id)
        .where(or_(Sku.name.ilike(like), Brand.name.ilike(like), Sku.gtin.ilike(like), Sku.line.ilike(like)))
        .order_by(Sku.name)
        .limit(LIMIT)
    ).all()

    pages = session.scalars(
        select(Page).where(or_(Page.url.ilike(like), Page.retailer.ilike(like))).order_by(Page.retailer).limit(LIMIT)
    ).all()
    page_skus: dict[int, list[int]] = {}
    for page_id, sku_id in session.execute(
        select(Snapshot.page_id, Extraction.sku_id)
        .join(Extraction, Extraction.snapshot_id == Snapshot.id)
        .where(Snapshot.page_id.in_([p.id for p in pages]))
        .distinct()
    ):
        page_skus.setdefault(page_id, []).append(sku_id)

    conflicts = session.scalars(
        conflict_query()
        .join(Sku, Conflict.sku_id == Sku.id)
        .join(Page, Conflict.page_id == Page.id)
        .where(
            or_(
                Sku.name.ilike(like),
                Page.retailer.ilike(like),
                Conflict.owner.ilike(like),
                cast(Conflict.page_value, String).ilike(like),
                cast(Conflict.truth_value, String).ilike(like),
            )
        )
        .order_by(Conflict.severity.desc(), Conflict.id)
        .limit(LIMIT)
    ).all()

    return {
        "products": [{"id": i, "name": n, "brand_name": b, "gtin": g} for i, n, b, g in products],
        "pages": [
            {"id": p.id, "label": page_label(p), "url": p.url, "source_type": p.source_type, "sku_ids": page_skus.get(p.id, [])}
            for p in pages
        ],
        "conflicts": [conflict_out(c).model_dump(mode="json") for c in conflicts],
    }


class BulkIn(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)
    action: Literal["accept", "dismiss", "assign"]
    owner: str | None = None
    reason: str | None = None


@router.post("/conflicts/bulk")
def bulk(body: BulkIn, session: DB) -> dict[str, Any]:
    """Apply one action to many conflicts. Conflicts the action doesn't apply to are skipped."""
    if body.action == "dismiss" and not (body.reason and body.reason.strip()):
        raise HTTPException(422, "a reason is required to dismiss conflicts")
    conflicts = session.scalars(select(Conflict).where(Conflict.id.in_(body.ids))).all()
    found = {c.id for c in conflicts}
    skipped = [{"id": i, "reason": "not found"} for i in body.ids if i not in found]
    done = 0
    for c in conflicts:
        try:
            if body.action == "assign":
                assign(session, c, (body.owner or "").strip() or None)
            elif body.action == "accept":
                change_status(session, c, ConflictStatus.accepted)
            else:
                change_status(session, c, ConflictStatus.dismissed, reason=body.reason)
            done += 1
        except WorkflowError as e:
            skipped.append({"id": c.id, "reason": str(e)})
    session.commit()
    return {"done": done, "skipped": skipped}
