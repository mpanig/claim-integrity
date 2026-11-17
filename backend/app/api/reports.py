import base64
import binascii
import io
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.common import DB, get_or_404
from app.models import Brand, Organisation, ReportBranding
from app.services.report_pdf import branding_dict, build_pdf
from app.services.reports import issues_csv, weekly_report

router = APIRouter()

HEX = r"^#[0-9a-fA-F]{6}$"
LOGO_TYPES = ("image/png", "image/jpeg", "image/webp")
MAX_LOGO_BYTES = 300_000


def _reports(session, brand_id: int | None) -> list[dict[str, Any]]:
    if brand_id is not None:
        brands = [get_or_404(session, Brand, brand_id, "brand")]
    else:
        brands = list(session.scalars(select(Brand).order_by(Brand.name)))
    return [weekly_report(session, b) for b in brands]


def _branding(session) -> ReportBranding | None:
    # TODO(auth): the signed-in user's organisation.
    org_id = session.scalar(select(Organisation.id).order_by(Organisation.id))
    return session.scalar(select(ReportBranding).where(ReportBranding.organisation_id == org_id)) if org_id else None


@router.get("/reports/weekly")
def weekly(session: DB, brand_id: int | None = None) -> dict[str, Any]:
    """One weekly report per brand (or just the chosen brand), plus the white-label branding."""
    return {"reports": _reports(session, brand_id), "branding": branding_dict(_branding(session))}


@router.get("/reports/weekly.pdf")
def weekly_pdf(session: DB, brand_id: int | None = None) -> Response:
    pdf = build_pdf(_reports(session, brand_id), branding_dict(_branding(session)))
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="weekly-report-{stamp}.pdf"'})


@router.get("/reports/issues.csv")
def issues_export(session: DB, brand_id: int | None = None) -> Response:
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    return Response(
        content=issues_csv(session, brand_id),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="claim-issues-{stamp}.csv"'},
    )


class BrandingIn(BaseModel):
    agency_name: str | None = Field(default=None, max_length=200)
    report_title: str = Field(default="Weekly claim drift report", min_length=1, max_length=200)
    primary_color: str = Field(default="#1f2937", pattern=HEX)
    accent_color: str = Field(default="#2a78d6", pattern=HEX)
    logo_data_url: str | None = None
    footer_text: str | None = Field(default=None, max_length=300)


def _check_logo(data_url: str) -> None:
    head, _, payload = data_url.partition(",")
    mime = head.removeprefix("data:").removesuffix(";base64")
    if not head.startswith("data:") or not head.endswith(";base64") or mime not in LOGO_TYPES:
        raise HTTPException(422, "logo must be a PNG, JPEG or WebP image")
    try:
        raw = base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as e:
        raise HTTPException(422, "logo is not valid base64") from e
    if len(raw) > MAX_LOGO_BYTES:
        raise HTTPException(422, f"logo must be under {MAX_LOGO_BYTES // 1000} KB")
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(raw)) as img:
            img.verify()
    except (UnidentifiedImageError, OSError) as e:
        raise HTTPException(422, "logo is not a readable image") from e


@router.get("/reports/branding")
def get_branding(session: DB) -> dict[str, Any]:
    return branding_dict(_branding(session))


@router.put("/reports/branding")
def set_branding(body: BrandingIn, session: DB) -> dict[str, Any]:
    if body.logo_data_url:
        _check_logo(body.logo_data_url)
    org_id = session.scalar(select(Organisation.id).order_by(Organisation.id))
    if org_id is None:
        raise HTTPException(409, "add a product first")
    row = _branding(session) or ReportBranding(organisation_id=org_id)
    for k, v in body.model_dump().items():
        setattr(row, k, v.strip() if isinstance(v, str) and k != "logo_data_url" else v)
    session.add(row)
    session.commit()
    return branding_dict(row)
