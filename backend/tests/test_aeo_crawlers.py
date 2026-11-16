"""AI crawler log analytics: parsing, privacy, demo vs real, API upload."""

from app.ai.crawlers import analytics, bot_for, generate_demo_crawls, parse_log
from app.models import CrawlerHit

LOG = "\n".join(
    [
        '203.0.113.5 - - [10/Nov/2026:10:00:01 +0000] "GET /cleanser?utm=x HTTP/1.1" 200 5120 "-" "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.2; +https://openai.com/gptbot)"',
        '203.0.113.6 - - [10/Nov/2026:10:05:00 +0000] "GET /cleanser HTTP/1.1" 200 5120 "-" "Mozilla/5.0 (compatible; OAI-SearchBot/1.0; +https://openai.com/searchbot)"',
        '203.0.113.7 - - [11/Nov/2026:09:00:00 +0000] "GET /faq HTTP/1.1" 403 0 "-" "Mozilla/5.0 (compatible; ClaudeBot/1.0; +claudebot@anthropic.com)"',
        '198.51.100.1 - - [11/Nov/2026:09:01:00 +0000] "GET / HTTP/1.1" 200 900 "-" "Mozilla/5.0 (Windows NT 10.0) Chrome/130"',
        "garbage line",
    ]
)
CSV = "timestamp,path,status,user_agent\n2026-11-12T08:00:00Z,/cleanser,200,Perplexity-User/1.0\n2026-11-12T08:00:05Z,/cleanser,200,Mozilla/5.0 (compatible; PerplexityBot/1.0)\n"


def test_bot_detection_order():
    assert bot_for("Mozilla/5.0 (compatible; OAI-SearchBot/1.0)") == "OAI-SearchBot"
    assert bot_for("ChatGPT-User/1.0") == "ChatGPT-User"
    assert bot_for("Claude-User/1.0") == "Claude-User" and bot_for("ClaudeBot/1.0") == "ClaudeBot"
    assert bot_for("Mozilla/5.0 Chrome/130") is None


def test_parse_combined_and_csv():
    counts, lines, skipped = parse_log(LOG)
    assert lines == 5 and skipped == 1
    assert sum(counts.values()) == 3  # the human visit is not kept
    assert {k[1] for k in counts} == {"GPTBot", "OAI-SearchBot", "ClaudeBot"}
    assert all(k[2] == "/cleanser" for k in counts if k[1] == "GPTBot")  # query strings dropped
    counts, lines, _ = parse_log(CSV)
    assert lines == 2 and {k[1] for k in counts} == {"Perplexity-User", "PerplexityBot"}


def test_upload_replaces_demo(checked, client, session):
    assert generate_demo_crawls(session) > 0
    assert analytics(session)["demo"] is True
    r = client.post("/aeo/crawlers/upload", params={"filename": "access.log"}, content=LOG.encode())
    assert r.status_code == 201 and r.json()["matched"] == 3
    d = client.get("/aeo/crawlers").json()
    assert d["demo"] is False and d["total"] == 3 and [u["filename"] for u in d["uploads"]] == ["access.log"]
    assert d["errors"][0]["status"] == 403 and d["errors"][0]["bots"] == ["ClaudeBot"]
    # No IPs or raw lines are stored anywhere.
    stored = " ".join(f"{h.path} {h.bot}" for h in session.query(CrawlerHit).all())
    assert "203.0.113" not in stored and "Mozilla" not in stored
    assert client.post("/aeo/crawlers/upload", content=b"").status_code == 422
    assert client.post("/aeo/crawlers/upload", content=b"a,b\n1,2\n").status_code == 422
    up = d["uploads"][0]["id"]
    assert client.delete(f"/aeo/crawlers/uploads/{up}").status_code == 204
    assert client.get("/aeo/crawlers").json()["demo"] is True  # back to demo when no real upload is left
