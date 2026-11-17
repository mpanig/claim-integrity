"""White-label PDF of the weekly report (ReportLab, no browser needed)."""

import base64
import io
from typing import Any
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models import ReportBranding
from app.services.reports import FIELD_TEXT, VERDICT_TEXT

DEFAULTS = {
    "agency_name": None,
    "report_title": "Weekly claim drift report",
    "primary_color": "#1f2937",
    "accent_color": "#2a78d6",
    "logo_data_url": None,
    "footer_text": None,
}


def branding_dict(b: ReportBranding | None) -> dict[str, Any]:
    if b is None:
        return dict(DEFAULTS)
    return {k: getattr(b, k) for k in DEFAULTS}


def decode_logo(data_url: str | None) -> bytes | None:
    if not data_url or "," not in data_url:
        return None
    return base64.b64decode(data_url.split(",", 1)[1])


def _change(c: int | None) -> str:
    if c is None:
        return "no data"
    return f"+{c}" if c > 0 else str(c)


def build_pdf(reports: list[dict[str, Any]], brand: dict[str, Any]) -> bytes:
    primary = colors.HexColor(brand["primary_color"])
    accent = colors.HexColor(brand["accent_color"])
    styles = getSampleStyleSheet()
    title = ParagraphStyle("t", parent=styles["Title"], textColor=primary, alignment=0, fontSize=20, leading=24, spaceAfter=2)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], textColor=primary, spaceBefore=6)
    body = ParagraphStyle("b", parent=styles["BodyText"], fontSize=9.5, leading=12)
    small = ParagraphStyle("s", parent=body, fontSize=8, leading=10, textColor=colors.HexColor("#555555"))

    def table(rows: list[list[Any]], widths: list[float]) -> Table:
        t = Table(rows, colWidths=widths, repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), accent),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.HexColor("#dddddd")),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        return t

    story: list[Any] = []
    logo = decode_logo(brand.get("logo_data_url"))
    for i, r in enumerate(reports):
        if i:
            story.append(PageBreak())
        if logo:
            reader = ImageReader(io.BytesIO(logo))
            w, h = reader.getSize()
            width = 38 * mm
            story.append(Image(io.BytesIO(logo), width=width, height=width * h / w, hAlign="LEFT"))
            story.append(Spacer(1, 4 * mm))
        story.append(Paragraph(escape(brand["report_title"]), title))
        story.append(Paragraph(escape(f"{r['brand']['name']} · week of {r['period']['start']} to {r['period']['end']}"), body))
        story.append(Spacer(1, 5 * mm))
        s = r["drift"]
        story.append(
            table(
                [
                    ["Drift score (0 = none)", "Change vs last week", "Open issues", "New this week", "Fixes verified", "Being fixed"],
                    [str(s["now"] if s["now"] is not None else "–"), _change(s["change"]), str(r["unresolved"]), str(r["new_issues"]), str(r["fixes_verified"]), str(r["in_progress"])],
                ],
                [30 * mm, 32 * mm, 26 * mm, 26 * mm, 26 * mm, 24 * mm],
            )
        )
        if r.get("demo"):
            story.append(Paragraph("Last week's drift score comes from demo history (sample data), not real checks.", small))
        story.append(Paragraph("Top issues", h2))
        if r["top_issues"]:
            rows = [["Issue", "Where", "What the page shows", "Risk", "Status"]]
            for t in r["top_issues"]:
                rows.append(
                    [
                        Paragraph(escape(f"{VERDICT_TEXT.get(t['verdict'], t['verdict'])}: {FIELD_TEXT.get(t['field'], t['field'])}"), body),
                        Paragraph(escape(f"{t['page']} · {t['sku_name']}"), body),
                        Paragraph(escape(str(t["value"])[:160]), body),
                        str(t["severity"]),
                        t["status"],
                    ]
                )
            story.append(table(rows, [38 * mm, 40 * mm, 60 * mm, 12 * mm, 18 * mm]))
        else:
            story.append(Paragraph("No open issues.", body))
        story.append(Paragraph("Products", h2))
        rows = [["Product", "Drift", "Change", "Open issues"]]
        for p in r["products"]:
            rows.append([Paragraph(escape(p["name"]), body), str(p["drift_score"] if p["drift_score"] is not None else "–"), _change(p["drift_change"]), str(p["unresolved"])])
        story.append(table(rows, [100 * mm, 22 * mm, 22 * mm, 24 * mm]))

    footer = brand.get("footer_text") or (f"Prepared by {brand['agency_name']}" if brand.get("agency_name") else "Claim Integrity")

    def on_page(canvas, doc):  # noqa: ANN001
        canvas.saveState()
        canvas.setFillColor(accent)
        canvas.rect(0, A4[1] - 4 * mm, A4[0], 4 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.setFont("Helvetica", 8)
        canvas.drawString(18 * mm, 10 * mm, footer[:120])
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=18 * mm,
        title=brand["report_title"],
        author=brand.get("agency_name") or "Claim Integrity",
    )
    doc.build(story or [Paragraph("No brands to report on.", body)], onFirstPage=on_page, onLaterPages=on_page)
    return buf.getvalue()
