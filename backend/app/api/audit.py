"""Site and entity audits, and AI-answer coverage."""

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.ai.coverage import coverage
from app.api.common import DB, get_or_404
from app.audit.run import audit_urls, check_entities
from app.models import AuditResult, AuditUrl, Brand, EntityCheck, Sku

router = APIRouter()


class UrlIn(BaseModel):
    url: str = Field(pattern=r"^https?://", max_length=2000)
    brand_id: int
    sku_id: int | None = None


def _result(r: AuditResult | None) -> dict[str, Any] | None:
    if r is None:
        return None
    return {
        "checked_at": r.checked_at, "status": r.status, "http_status": r.http_status, "note": r.note,
        "structured": r.structured, "crawlability": r.crawlability, "freshness": r.freshness,
    }


@router.get("/audit")
def list_audits(session: DB) -> list[dict[str, Any]]:
    brands = {b.id: b.name for b in session.scalars(select(Brand))}
    skus = {s.id: s.name for s in session.scalars(select(Sku))}
    out = []
    for u in session.scalars(select(AuditUrl).order_by(AuditUrl.id)):
        r = session.scalar(select(AuditResult).where(AuditResult.audit_url_id == u.id).order_by(AuditResult.checked_at.desc(), AuditResult.id.desc()).limit(1))
        out.append({"id": u.id, "url": u.url, "brand_id": u.brand_id, "brand_name": brands.get(u.brand_id), "sku_id": u.sku_id, "sku_name": skus.get(u.sku_id), "latest": _result(r)})
    return out


@router.post("/audit/urls", status_code=201)
def add_url(body: UrlIn, session: DB) -> dict[str, Any]:
    brand = get_or_404(session, Brand, body.brand_id, "brand")
    if body.sku_id:
        get_or_404(session, Sku, body.sku_id, "SKU")
    if session.scalar(select(AuditUrl).where(AuditUrl.url == body.url.strip())):
        raise HTTPException(409, "that URL is already in the audit list")
    u = AuditUrl(organisation_id=brand.organisation_id, brand_id=brand.id, sku_id=body.sku_id, url=body.url.strip())
    session.add(u)
    session.commit()
    return {"id": u.id}


@router.delete("/audit/urls/{url_id}", status_code=204)
def delete_url(url_id: int, session: DB) -> Response:
    session.delete(get_or_404(session, AuditUrl, url_id, "audit URL"))
    session.commit()
    return Response(status_code=204)


@router.post("/audit/run")
def run_audit(session: DB, url_id: list[int] = Query(default=[])) -> dict[str, Any]:
    """Fetch and check the given URLs (or all). Each URL: robots.txt, then the page."""
    results = audit_urls(session, url_id or None)
    return {"checked": len(results), "statuses": [r.status for r in results]}


@router.get("/audit/entities")
def entities(session: DB) -> list[dict[str, Any]]:
    out = []
    for b in session.scalars(select(Brand).order_by(Brand.name)):
        e = session.scalar(select(EntityCheck).where(EntityCheck.brand_id == b.id).order_by(EntityCheck.checked_at.desc(), EntityCheck.id.desc()).limit(1))
        out.append(
            {
                "brand_id": b.id, "brand_name": b.name,
                "latest": None if e is None else {
                    "checked_at": e.checked_at, "qid": e.qid, "label": e.label, "description": e.description,
                    "wikipedia_url": e.wikipedia_url, "facts": e.facts, "missing": e.missing, "score": e.score, "note": e.note,
                },
            }
        )
    return out


@router.post("/audit/entities/run")
def run_entities(session: DB) -> dict[str, Any]:
    checks = check_entities(session)
    return {"checked": len(checks)}


@router.get("/ai/coverage")
def ai_coverage(
    session: DB,
    engine: list[str] = Query(default=[]),
    region: list[str] = Query(default=[]),
    persona_id: int | None = None,
    search: bool | None = None,
) -> dict[str, Any]:
    return coverage(session, engines=engine or None, regions=region or None, persona_id=persona_id, search=search)
