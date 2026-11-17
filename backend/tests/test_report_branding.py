"""White-label branding and the PDF export."""

import base64
import io

from PIL import Image


def png_data_url(size=(40, 20), color=(42, 120, 214)) -> str:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def test_branding_defaults_and_update(checked, client):
    b = client.get("/reports/branding").json()
    assert b["report_title"] == "Weekly claim drift report" and b["logo_data_url"] is None

    body = {
        "agency_name": "Brightside Agency",
        "report_title": "CeraVe & Aveeno: weekly claims",
        "primary_color": "#112233",
        "accent_color": "#ff6600",
        "logo_data_url": png_data_url(),
        "footer_text": "Confidential",
    }
    saved = client.put("/reports/branding", json=body).json()
    assert saved["agency_name"] == "Brightside Agency" and saved["accent_color"] == "#ff6600"
    assert client.get("/reports/weekly").json()["branding"]["report_title"] == "CeraVe & Aveeno: weekly claims"

    assert client.put("/reports/branding", json={**body, "primary_color": "red"}).status_code == 422
    assert client.put("/reports/branding", json={**body, "logo_data_url": "data:image/svg+xml;base64,PHN2Zz4="}).status_code == 422
    assert client.put("/reports/branding", json={**body, "logo_data_url": "data:image/png;base64,bm90IGFuIGltYWdl"}).status_code == 422
    big = "data:image/png;base64," + base64.b64encode(b"\x89PNG" + b"0" * 400_000).decode()
    assert client.put("/reports/branding", json={**body, "logo_data_url": big}).status_code == 422


def test_pdf_export(checked, client):
    plain = client.get("/reports/weekly.pdf")
    assert plain.status_code == 200 and plain.headers["content-type"] == "application/pdf"
    assert plain.content.startswith(b"%PDF") and "attachment" in plain.headers["content-disposition"]

    client.put("/reports/branding", json={"agency_name": "Brightside", "report_title": "Claims report", "logo_data_url": png_data_url()})
    brands = {b["name"]: b["id"] for b in client.get("/brands").json()}
    branded = client.get("/reports/weekly.pdf", params={"brand_id": brands["CeraVe"]})
    assert branded.status_code == 200 and branded.content.startswith(b"%PDF")
    assert b"/Title (Claims report)" in branded.content and b"/Author (Brightside)" in branded.content
    assert b"/Subtype /Image" in branded.content  # the logo is embedded
