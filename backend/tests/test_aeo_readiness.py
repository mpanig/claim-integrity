"""Answer-readiness grades (fetched politely, demo hidden by real grades) and content briefs."""

import httpx

from app.ai.readiness import CHECKS, generate_demo_grades, grade_html, grade_url, latest_grades
from app.models import Brand

GOOD = """<html><head><title>Oat Cleanser | Brand</title><meta name="author" content="Dr A. Smith, dermatologist">
<script type="application/ld+json">[{"@type": "Product", "name": "Oat Cleanser", "dateModified": "2026-10-01"},
{"@type": "FAQPage", "mainEntity": []}]</script></head><body>
<h1>Oat Cleanser</h1>
<p>A gentle daily face wash for dry and sensitive skin. It uses colloidal oat to calm redness and cleans without stripping moisture.</p>
<h2>Is it safe for eczema?</h2><p>Yes. It is fragrance-free and tested on eczema-prone skin.</p>
<h2>How do I use it?</h2><ol><li>Wet skin.</li><li>Massage for 30 seconds.</li><li>Rinse.</li></ol>
<h2>Ingredients</h2><p>Water, Glycerin, Avena Sativa (Oat) Kernel Flour.</p>
<p>""" + "It suits every skin type and is easy to use. " * 40 + """</p></body></html>"""


def test_grade_html_scores_and_fixes():
    good = grade_html(GOOD)
    assert sum(p for _l, p, _f in CHECKS.values()) == 100
    assert good["score"] >= 85
    by = {c["key"]: c for c in good["checks"]}
    assert by["faq_schema"]["passed"] and by["question_headings"]["passed"] and by["answer_first"]["passed"]
    bare = grade_html("<html><body><div>Buy now</div></body></html>")
    assert bare["score"] < 20
    assert all(c["fix"] for c in bare["checks"] if not c["passed"])


def _transport(robots: str, page_status: int = 200):
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(str(req.url))
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text=robots)
        return httpx.Response(page_status, text=GOOD)

    return httpx.MockTransport(handler), calls


def test_grade_url_obeys_robots(checked, session):
    t, calls = _transport("User-agent: *\nDisallow: /private\n")
    g = grade_url(session, "https://shop.example/private/oat", transport=t)
    assert g.status == "blocked" and g.score is None
    assert calls == ["https://shop.example/robots.txt"]  # the page itself was never fetched
    t, calls = _transport("User-agent: *\nAllow: /\n")
    g = grade_url(session, "https://shop.example/oat", transport=t)
    assert g.status == "ok" and g.score >= 85 and len(calls) == 2


def test_demo_grades_hidden_by_real(checked, session):
    assert generate_demo_grades(session) == 5
    rows = latest_grades(session)
    assert len(rows) == 5 and all(r["is_demo"] for r in rows)
    url = next(r["url"] for r in rows if "cerave.com" in r["url"])
    t, _ = _transport("User-agent: *\nAllow: /\n")
    grade_url(session, url, transport=t)
    rows = latest_grades(session)
    mine = [r for r in rows if r["url"] == url]
    assert len(mine) == 1 and mine[0]["is_demo"] is False
    assert generate_demo_grades(session) == 5  # regenerating demo never removes real grades
    assert any(r["url"] == url and not r["is_demo"] for r in latest_grades(session))


def test_brief(checked, client, session):
    from app.ai.demo import generate_demo_answers

    generate_demo_answers(session, weeks=1, samples=1, density=0.1)
    session.commit()
    aveeno = session.query(Brand).filter_by(name="Aveeno").one()
    b = client.post("/aeo/brief", json={"question": "What is the best face cleanser for eczema-prone skin?", "brand_id": aveeno.id}).json()
    assert b["brand"] == "Aveeno" and "Aveeno" in b["product"]
    assert any(f["label"].startswith("Ingredients") for f in b["facts"])
    assert any(e["attribute"] == "Eczema-friendly" and e["gap"] for e in b["emphasise"])
    assert all("CeraVe" not in q for q in b["related_questions"])
    assert b["markdown"].startswith("# Content brief:") and "## Page checklist" in b["markdown"]
    assert client.post("/aeo/brief", json={"question": "x" * 10, "brand_id": 999999}).status_code == 404
