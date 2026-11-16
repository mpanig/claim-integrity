"""Site audit checks, entity clarity and AI coverage (no network: mocked responses)."""

import urllib.robotparser
from datetime import UTC, datetime

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select

from app.audit.checks import crawlability, freshness, gtin_valid, structured_data
from app.models import AuditResult, AuditUrl, Brand, EntityCheck

PRODUCT_PAGE = """<html><head>
<meta property="og:updated_time" content="2026-10-01T00:00:00Z">
<script type="application/ld+json">{"@context":"https://schema.org","@type":"Product","name":"Hydrating Facial Cleanser",
 "image":"https://x/img.jpg","brand":{"@type":"Brand","name":"CeraVe"},"gtin13":"4006381333931",
 "offers":{"@type":"Offer","priceCurrency":"USD"},"dateModified":"2024-01-15"}</script>
<script type="application/ld+json">{ broken json </script>
</head><body><main><h1>Hydrating Facial Cleanser</h1>
<p>Ingredients: Aqua/Water/Eau, Glycerin, Cetearyl Alcohol, Ceramide NP, Ceramide AP, Ceramide EOP</p>
<p>A gentle cleanser for normal to dry skin, developed with dermatologists and suitable for daily use.</p>
</main></body></html>"""


def soup(html: str = PRODUCT_PAGE) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


def robots(text: str) -> urllib.robotparser.RobotFileParser:
    r = urllib.robotparser.RobotFileParser()
    r.parse(text.splitlines())
    return r


def test_gtin_check_digit():
    assert gtin_valid("4006381333931")
    assert not gtin_valid("4006381333932")
    assert not gtin_valid("12345")


def test_structured_data():
    s = structured_data(soup())
    assert s["found"] and s["format"] == "json-ld" and s["name"] == "Hydrating Facial Cleanser"
    assert set(s["present"]) == {"name", "image", "brand", "offers", "gtin"}
    assert set(s["missing"]) == {"description", "aggregateRating"}
    assert s["score"] == round(100 * 5 / 7)
    assert any("not valid JSON" in i for i in s["issues"])
    assert any("no price" in i for i in s["issues"])

    none = structured_data(soup("<html><body><p>hi</p></body></html>"))
    assert not none["found"] and none["score"] == 0
    bad_gtin = PRODUCT_PAGE.replace("4006381333931", "4006381333932")
    assert any("not a valid GTIN" in i for i in structured_data(soup(bad_gtin))["issues"])


def test_crawlability():
    rules = robots("User-agent: GPTBot\nDisallow: /\n\nUser-agent: CCBot\nDisallow: /skincare/\n\nUser-agent: *\nAllow: /\n")
    c = crawlability(rules, "https://brand.example/skincare/x", soup(), {}, PRODUCT_PAGE)
    allowed = {b["bot"]: b["allowed"] for b in c["bots"]}
    assert allowed["GPTBot"] is False and allowed["CCBot"] is False and allowed["ClaudeBot"] is True
    assert any("GPTBot, CCBot" in i for i in c["issues"])
    assert not c["noindex"] and not c["js_heavy"]

    shell = "<html><head><meta name='robots' content='noindex, nofollow'></head><body><div id='app'></div>" + "<script>x</script>" * 3000 + "</body></html>"
    c2 = crawlability(None, "https://x/", soup(shell), {"x-robots-tag": ""}, shell)
    assert c2["noindex"] and c2["js_heavy"] and c2["score"] < 60
    assert any("No robots.txt" in i for i in c2["issues"])


def test_freshness_and_facts():
    truth = {"ingredients": ["Aqua/Water/Eau", "Glycerin", "Cetearyl Alcohol", "Ceramide NP", "Ceramide AP", "Ceramide EOP", "Phenoxyethanol", "Tocopherol"]}
    f = freshness(soup(), {}, truth, now=datetime(2026, 11, 17, tzinfo=UTC))
    assert f["newest"].startswith("2026-10-01") and f["age_days"] == 47 and not f["stale"]
    assert f["facts"]["ingredients_on_page"] == 0.75
    assert "Phenoxyethanol" in f["facts"]["missing_ingredients"]

    old = freshness(soup("<html><body>x</body></html>"), {"last-modified": "Wed, 01 Jan 2020 00:00:00 GMT"}, None, now=datetime(2026, 11, 17, tzinfo=UTC))
    assert old["stale"] and any("days ago" in i for i in old["issues"])
    nodate = freshness(soup("<html><body>x</body></html>"), {}, None)
    assert nodate["stale"] and nodate["newest"] is None


def test_audit_respects_robots_and_records_results(seeded, session):
    from app.audit.run import audit_urls

    requested = []

    def handler(req: httpx.Request) -> httpx.Response:
        requested.append(str(req.url))
        if req.url.path == "/robots.txt":
            body = "User-agent: *\nDisallow: /private/\n" if req.url.host == "www.cerave.com" else "User-agent: *\nDisallow: /\n"
            return httpx.Response(200, text=body)
        return httpx.Response(200, text=PRODUCT_PAGE, headers={"content-type": "text/html"})

    results = audit_urls(session, transport=httpx.MockTransport(handler), sleep=lambda s: None)
    by_host = {session.get(AuditUrl, r.audit_url_id).url.split("/")[2]: r for r in results}
    ok, blocked = by_host["www.cerave.com"], by_host["www.aveeno.com"]
    assert ok.status == "ok" and ok.structured["found"] and ok.freshness["facts"]
    assert blocked.status == "blocked" and "robots.txt" in blocked.note
    # The disallowed page itself was never requested.
    assert not any("aveeno.com/products" in u for u in requested)
    assert len(session.scalars(select(AuditResult)).all()) == 2


def test_blocked_by_status(seeded, session):
    from app.audit.run import audit_urls

    t = httpx.MockTransport(lambda r: httpx.Response(404) if r.url.path == "/robots.txt" else httpx.Response(403))
    results = audit_urls(session, transport=t, sleep=lambda s: None)
    assert {r.status for r in results} == {"blocked"} and "HTTP 403" in results[0].note


def test_refused_robots_is_blocked_not_allowed(seeded, session):
    from app.audit.run import audit_urls

    requested = []

    def handler(req: httpx.Request) -> httpx.Response:
        requested.append(req.url.path)
        return httpx.Response(403)

    results = audit_urls(session, transport=httpx.MockTransport(handler), sleep=lambda s: None)
    assert {r.status for r in results} == {"blocked"}
    assert all(r.crawlability["bots"] == [] and r.crawlability["score"] is None for r in results)
    assert set(requested) == {"/robots.txt"}  # the pages themselves were never fetched


def test_entity_check(seeded, session):
    from app.audit.run import check_entities

    def handler(req: httpx.Request) -> httpx.Response:
        q = dict(req.url.params)
        if q.get("action") == "wbsearchentities":
            if q["search"] == "Aveeno":
                return httpx.Response(200, json={"search": []})
            return httpx.Response(200, json={"search": [{"id": "Q1", "label": "CeraVe", "description": "skin care brand"}]})
        if q.get("props") == "labels":
            return httpx.Response(200, json={"entities": {"Q2": {"labels": {"en": {"value": "L'Oréal"}}}}})
        return httpx.Response(200, json={"entities": {"Q1": {
            "descriptions": {"en": {"value": "skin care brand"}},
            "sitelinks": {},
            "claims": {
                "P856": [{"mainsnak": {"datavalue": {"value": "https://www.cerave.com/"}}}],
                "P749": [{"mainsnak": {"datavalue": {"value": {"id": "Q2"}}}}],
                "P571": [{"mainsnak": {"datavalue": {"value": {"time": "+2005-00-00T00:00:00Z"}}}}],
            },
        }}})

    checks = {session.get(Brand, c.brand_id).name: c for c in check_entities(session, transport=httpx.MockTransport(handler))}
    cerave, aveeno = checks["CeraVe"], checks["Aveeno"]
    assert cerave.qid == "Q1" and cerave.facts["parent organisation"] == ["L'Oréal"] and cerave.facts["founded"] == ["2005"]
    assert cerave.score == 10 + 15 + 15 + 10  # description, website, parent, founded
    assert "an English Wikipedia article" in cerave.missing
    assert aveeno.score == 0 and aveeno.qid is None and "No Wikidata entry" in aveeno.note
    assert len(session.scalars(select(EntityCheck)).all()) == 2


def test_audit_api(seeded, client):
    rows = client.get("/audit").json()
    assert len(rows) == 2 and all(r["latest"] is None for r in rows)
    brand = rows[0]["brand_id"]
    new = client.post("/audit/urls", json={"url": "https://www.ulta.com/p/cerave-hydrating", "brand_id": brand}).json()["id"]
    assert client.post("/audit/urls", json={"url": "https://www.ulta.com/p/cerave-hydrating", "brand_id": brand}).status_code == 409
    assert client.post("/audit/urls", json={"url": "ftp://x", "brand_id": brand}).status_code == 422
    assert client.delete(f"/audit/urls/{new}").status_code == 204
    assert [e["latest"] for e in client.get("/audit/entities").json()] == [None, None]


def test_ai_coverage(checked, client, session):
    from app.ai.demo import generate_demo_answers

    generate_demo_answers(session, weeks=1, samples=1, density=0.1)
    cov = client.get("/ai/coverage").json()
    assert cov["demo"] is True
    assert cov["third_party"] and all(d["page_type"] != "brand" for d in cov["third_party"])
    assert all(d["gap"] <= d["citations"] for d in cov["third_party"])
    gaps = [u["gap"] for u in cov["use_cases"]]
    assert gaps == sorted(gaps, reverse=True)
    assert {"use_case", "persona", "ours", "competitor", "top_competitor"} <= set(cov["use_cases"][0])
