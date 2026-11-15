from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Response
from sqlalchemy import select

from app.api.common import DB, get_or_404
from app.models import Brand
from app.services.reports import issues_csv, weekly_report

router = APIRouter()


@router.get("/reports/weekly")
def weekly(session: DB, brand_id: int | None = None) -> dict[str, Any]:
    """One weekly report per brand (or just the chosen brand)."""
    if brand_id is not None:
        brands = [get_or_404(session, Brand, brand_id, "brand")]
    else:
        brands = list(session.scalars(select(Brand).order_by(Brand.name)))
    return {"reports": [weekly_report(session, b) for b in brands]}


@router.get("/reports/issues.csv")
def issues_export(session: DB, brand_id: int | None = None) -> Response:
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    return Response(
        content=issues_csv(session, brand_id),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="claim-issues-{stamp}.csv"'},
    )
