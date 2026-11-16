"""AI referral traffic import: source matching, GA4-style CSV, demo vs real."""

from app.ai.referrals import generate_demo_referrals, parse_csv, source_for

GA4 = """# ----------------------------------------
# Traffic acquisition: Session source
# 20261101-20261107
# ----------------------------------------
Session source,Landing page + query string,Date,Sessions,Key events
chatgpt.com,/cleanser?utm_source=chatgpt.com,20261101,40,2
perplexity.ai,/cleanser,20261101,10,0
google,/,20261101,900,18
gemini.google.com,/cream,20261102,5,1
(direct),/,20261102,300,6
claude.ai,/cleanser,20261102,3,0
"""


def test_source_matching():
    assert source_for("chatgpt.com / referral") == "ChatGPT"
    assert source_for("chat.openai.com") == "ChatGPT"
    assert source_for("copilot.microsoft.com") == "Copilot"
    assert source_for("gemini.google.com") == "Gemini" and source_for("google") is None


def test_parse_ga4_export():
    sessions, conversions, rows, skipped = parse_csv(GA4)
    assert rows == 6 and skipped == 0
    by = {}
    for (_d, src, lp), n in sessions.items():
        by[src] = by.get(src, 0) + n
    assert by == {"ChatGPT": 40, "Perplexity": 10, "Gemini": 5, "Claude": 3, "Other": 1200}
    assert all(lp == "" for (_d, src, lp) in sessions if src == "Other")  # non-AI pages not kept
    assert ("/cleanser" in {lp for (_d, src, lp) in sessions if src == "ChatGPT"})  # query string dropped
    assert sum(conversions.values()) == 27


def test_import_replaces_demo(checked, client, session):
    assert generate_demo_referrals(session) > 0
    assert client.get("/aeo/referrals").json()["demo"] is True
    r = client.post("/aeo/referrals/upload", params={"filename": "ga4.csv"}, content=GA4.encode())
    assert r.status_code == 201 and r.json()["matched"] == 58
    d = client.get("/aeo/referrals").json()
    assert d["demo"] is False and d["ai_sessions"] == 58
    assert d["sources"][0]["source"] == "ChatGPT" and d["ai_share"] == round(58 / 1258, 4)
    assert d["ga4"]["status"] == "not connected"
    assert client.post("/aeo/referrals/upload", content=b"foo,bar\n1,2\n").status_code == 422
    assert client.delete(f"/aeo/referrals/uploads/{d['uploads'][0]['id']}").status_code == 204
    assert client.get("/aeo/referrals").json()["demo"] is True
