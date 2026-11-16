"""AEO / GEO tools: page answer-readiness grades and content briefs."""

from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.ai.brief import build_brief
from app.ai.crawlers import analytics, ingest
from app.ai.llms_txt import brand_hosts, check_host, generate, latest_checks
from app.ai.readiness import grade_url, latest_grades
from app.api.common import DB, get_or_404
from app.models import AuditUrl, Brand, LogUpload

router = APIRouter(prefix="/aeo")


class GradeIn(BaseModel):
    url: str = Field(pattern=r"^https?://", max_length=2000)
    brand_id: int | None = None
    sku_id: int | None = None


@router.get("/grades")
def list_grades(session: DB) -> list[dict[str, Any]]:
    """Newest answer-readiness grade per page (demo hidden for a page once it has a real grade)."""
    return latest_grades(session)


@router.post("/grades", status_code=201)
def add_grade(body: GradeIn, session: DB) -> dict[str, Any]:
    """Fetch the page once (robots.txt obeyed) and grade it."""
    g = grade_url(session, body.url.strip(), brand_id=body.brand_id, sku_id=body.sku_id)
    return {"id": g.id, "status": g.status, "score": g.score, "note": g.note}


@router.post("/grades/audited")
def grade_audited(session: DB) -> dict[str, Any]:
    """Grade every page on the audit list (one fetch each)."""
    rows = session.scalars(select(AuditUrl).order_by(AuditUrl.id)).all()
    done = [grade_url(session, u.url, brand_id=u.brand_id, sku_id=u.sku_id) for u in rows]
    return {"graded": len(done), "ok": sum(1 for g in done if g.status == "ok")}


class BriefIn(BaseModel):
    question: str = Field(min_length=5, max_length=500)
    brand_id: int
    sku_id: int | None = None


@router.post("/brief")
def brief(body: BriefIn, session: DB) -> dict[str, Any]:
    get_or_404(session, Brand, body.brand_id, "Brand")
    try:
        return build_brief(session, body.question.strip(), body.brand_id, body.sku_id)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.get("/llms")
def llms_checks(session: DB) -> list[dict[str, Any]]:
    """Latest /llms.txt check per brand site (demo hidden once a site has a real check)."""
    return latest_checks(session)


@router.post("/llms/check")
def llms_check_all(session: DB) -> dict[str, Any]:
    """Fetch /llms.txt once per brand site (robots.txt obeyed)."""
    rows = [check_host(session, host, brand.id) for brand, host in brand_hosts(session)]
    return {"checked": len(rows), "found": sum(1 for r in rows if r.status == "found")}


@router.get("/llms/generate/{brand_id}")
def llms_generate(brand_id: int, session: DB) -> dict[str, str]:
    """A draft llms.txt for the brand, from its products, approved facts and positioning."""
    return {"text": generate(session, get_or_404(session, Brand, brand_id, "Brand"))}


@router.get("/crawlers")
def crawler_analytics(session: DB, days: int = Query(default=28, ge=1, le=365)) -> dict[str, Any]:
    """AI crawler hits from uploaded logs (demo until the first real upload)."""
    return analytics(session, days)


@router.post("/crawlers/upload", status_code=201)
async def crawler_upload(request: Request, session: DB, filename: str = Query(default="access.log", max_length=300)) -> dict[str, Any]:
    """Upload a log as the raw request body (combined log format or CSV). Only AI-bot counts are kept."""
    data = await request.body()
    if not data:
        raise HTTPException(422, "Empty file")
    try:
        up = ingest(session, filename, data)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    return {"id": up.id, "lines": up.lines, "matched": up.matched, "skipped": up.skipped}


@router.delete("/crawlers/uploads/{upload_id}", status_code=204)
def crawler_delete(upload_id: int, session: DB) -> Response:
    up = get_or_404(session, LogUpload, upload_id, "Upload")
    session.delete(up)
    session.commit()
    return Response(status_code=204)
