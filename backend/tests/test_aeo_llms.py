"""llms.txt: format checks, polite fetch, demo hidden by real checks, generator."""

import httpx

from app.ai.llms_txt import check_host, generate, generate_demo_checks, latest_checks, parse
from app.models import Brand

GOOD = """# Oat Co

> Gentle oat skincare for sensitive skin.

## Products

- [Oat Cleanser](https://oat.example/cleanser): daily face wash
- [Oat Cream](https://oat.example/cream): moisturiser
- [Oat Balm](https://oat.example/balm): for very dry patches
- [Ingredients](https://oat.example/ingredients): what each does
- [FAQ](https://oat.example/faq): common questions

## Optional

- [About](https://oat.example/about): our story
"""


def test_parse_scores_format():
    good = parse(GOOD, "oat.example")
    assert good["score"] == 100 and good["title"] == "Oat Co" and good["links"] == 6
    bad = parse("Welcome!\n- [x](/relative)\n", "oat.example")
    assert bad["score"] < 30 and bad["bad_links"]
    assert all(c["fix"] for c in bad["checks"] if not c["passed"])


def _transport(robots: str, llms_status: int = 200, body: str = GOOD):
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append(req.url.path)
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text=robots)
        if req.url.path == "/llms.txt":
            return httpx.Response(llms_status, text=body)
        return httpx.Response(404, text="not found")

    return httpx.MockTransport(handler), calls


def test_check_host_polite_and_statuses(checked, session):
    t, calls = _transport("User-agent: *\nDisallow: /\n")
    assert check_host(session, "oat.example", transport=t).status == "blocked"
    assert calls == ["/robots.txt"]
    t, calls = _transport("User-agent: *\nAllow: /\n")
    row = check_host(session, "oat.example", transport=t)
    assert row.status == "found" and row.score == 100 and row.result["full_txt"] is False
    t, _ = _transport("", llms_status=404)
    assert check_host(session, "none.example", transport=t).status == "missing"
    t, _ = _transport("", body="<!doctype html><html>soft 404</html>")
    assert check_host(session, "soft.example", transport=t).status == "missing"


def test_demo_hidden_by_real_and_generator(checked, session):
    assert generate_demo_checks(session) >= 2
    rows = latest_checks(session)
    assert rows and all(r["is_demo"] for r in rows if r["status"] != "unchecked")
    host = rows[0]["host"]
    t, _ = _transport("User-agent: *\nAllow: /\n")
    check_host(session, host, rows[0]["brand_id"], transport=t)
    mine = [r for r in latest_checks(session) if r["host"] == host]
    assert len(mine) == 1 and mine[0]["is_demo"] is False
    cerave = session.query(Brand).filter_by(name="CeraVe").one()
    text = generate(session, cerave)
    assert text.startswith("# CeraVe\n\n> ")
    assert "CeraVe Hydrating Facial Cleanser" in text and "## Optional" in text
    assert parse(text, "cerave.com")["checks"][0]["passed"]
