"""AI crawler analytics from uploaded web server logs.

Accepts the Apache/Nginx combined log format, or CSV with a header naming a time column
(time / timestamp / date / datetime), a path column (path / url / uri / request), a status
column and a user-agent column (user_agent / useragent / ua / user-agent). Lines from AI bots
are kept only as counts per day, bot, path and status: no IP addresses, no raw lines.

Bots are recognised by user agent only (it can be faked; IP verification is not done).
Google-Extended and Applebot-Extended are robots.txt tokens, not user agents: those companies
crawl as Googlebot and Applebot, so the tokens never appear in logs.

Demo data (one flagged upload) shows until the first real upload.
"""

import csv
import io
import random
import re
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models import AuditUrl, CrawlerHit, LogUpload, Organisation

# name, company, purpose, UA substring (checked in order; most specific first)
BOTS: list[tuple[str, str, str, str]] = [
    ("OAI-SearchBot", "OpenAI", "search", "oai-searchbot"),
    ("ChatGPT-User", "OpenAI", "user fetch", "chatgpt-user"),
    ("GPTBot", "OpenAI", "training", "gptbot"),
    ("Claude-User", "Anthropic", "user fetch", "claude-user"),
    ("Claude-SearchBot", "Anthropic", "search", "claude-searchbot"),
    ("ClaudeBot", "Anthropic", "training", "claudebot"),
    ("Perplexity-User", "Perplexity", "user fetch", "perplexity-user"),
    ("PerplexityBot", "Perplexity", "search", "perplexitybot"),
    ("Google-Extended", "Google", "training (robots token)", "google-extended"),
    ("Googlebot", "Google", "search (also AI Overviews)", "googlebot"),
    ("Applebot-Extended", "Apple", "training (robots token)", "applebot-extended"),
    ("Applebot", "Apple", "search (Siri, Spotlight)", "applebot"),
    ("Bingbot", "Microsoft", "search (also Copilot)", "bingbot"),
    ("CCBot", "Common Crawl", "training datasets", "ccbot"),
    ("Meta-ExternalAgent", "Meta", "training", "meta-externalagent"),
    ("Bytespider", "ByteDance", "training", "bytespider"),
]
BOT_INFO = {name: {"company": co, "purpose": p} for name, co, p, _ in BOTS}
COMBINED = re.compile(r'^\S+ \S+ \S+ \[([^\]]+)\] "(?:\S+) (\S+)[^"]*" (\d{3}) \S+ "[^"]*" "([^"]*)"')
MAX_BYTES = 50 * 1024 * 1024


def bot_for(ua: str) -> str | None:
    low = ua.lower()
    return next((name for name, _c, _p, key in BOTS if key in low), None)


def _day(value: str) -> date | None:
    value = value.strip()
    for fmt in ("%d/%b/%Y:%H:%M:%S %z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value.replace("Z", "+0000"), fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _path(raw: str) -> str:
    parts = urlsplit(raw)
    return (parts.path or "/")[:500]


def parse_log(text: str) -> tuple[Counter, int, int]:
    """(counts by (day, bot, path, status), lines read, lines skipped as unreadable)."""
    counts: Counter = Counter()
    lines = skipped = 0
    first = next((line for line in text.splitlines() if line.strip()), "")
    if COMBINED.match(first) is None and "," in first:
        reader = csv.DictReader(io.StringIO(text))
        cols = {c.lower().strip(): c for c in (reader.fieldnames or [])}
        pick = lambda *names: next((cols[n] for n in names if n in cols), None)  # noqa: E731
        t, p, s, u = pick("time", "timestamp", "date", "datetime"), pick("path", "url", "uri", "request"), pick("status", "status_code"), pick("user_agent", "useragent", "ua", "user-agent")
        if not (t and p and s and u):
            raise ValueError("CSV needs time, path, status and user_agent columns")
        for row in reader:
            lines += 1
            bot = bot_for(row.get(u) or "")
            day = _day(row.get(t) or "")
            if day is None or not (row.get(s) or "").strip().isdigit():
                skipped += 1
                continue
            if bot:
                counts[(day, bot, _path(row.get(p) or "/"), int(row[s]))] += 1
        return counts, lines, skipped
    for line in text.splitlines():
        if not line.strip():
            continue
        lines += 1
        m = COMBINED.match(line)
        day = _day(m.group(1)) if m else None
        if not m or day is None:
            skipped += 1
            continue
        bot = bot_for(m.group(4))
        if bot:
            counts[(day, bot, _path(m.group(2)), int(m.group(3)))] += 1
    return counts, lines, skipped


def store(session: Session, filename: str, counts: Counter, lines: int, skipped: int, *, is_demo: bool = False) -> LogUpload:
    org = session.scalars(select(Organisation)).first()
    days = [k[0] for k in counts]
    up = LogUpload(organisation_id=org.id, kind="crawler", filename=filename[:300], lines=lines, matched=sum(counts.values()), skipped=skipped,
                   first_day=min(days) if days else None, last_day=max(days) if days else None, is_demo=is_demo)
    session.add(up)
    session.flush()
    session.add_all(CrawlerHit(upload_id=up.id, day=d, bot=b, path=p, status=s, hits=n) for (d, b, p, s), n in counts.items())
    session.commit()
    return up


def ingest(session: Session, filename: str, data: bytes) -> LogUpload:
    if len(data) > MAX_BYTES:
        raise ValueError("File is larger than 50 MB; split it or upload a shorter period")
    return store(session, filename, *parse_log(data.decode("utf-8", errors="replace")))


DEMO_PATHS = [
    ("/skincare/cleansers/hydrating-facial-cleanser", 10), ("/skincare/moisturizers/moisturizing-cream", 7), ("/", 6),
    ("/skincare/cleansers/foaming-facial-cleanser", 5), ("/science/ceramides", 3), ("/faq", 2), ("/llms.txt", 1),
    ("/skincare/cleansers/old-formula-page", 1),
]
DEMO_RATES = {"GPTBot": 14, "OAI-SearchBot": 9, "ChatGPT-User": 11, "ClaudeBot": 8, "Claude-User": 3, "PerplexityBot": 6, "Perplexity-User": 4,
              "Googlebot": 22, "Bingbot": 12, "Applebot": 3, "CCBot": 2}


def generate_demo_crawls(session: Session, days: int = 28, seed: int = 11) -> int:
    """One flagged demo upload with 4 weeks of AI crawler hits on a brand site."""
    ids = list(session.scalars(select(LogUpload.id).where(LogUpload.is_demo.is_(True), LogUpload.kind == "crawler")))
    if ids:
        session.execute(delete(CrawlerHit).where(CrawlerHit.upload_id.in_(ids)))
        session.execute(delete(LogUpload).where(LogUpload.id.in_(ids)))
    rng = random.Random(seed)
    today = datetime.now(UTC).date()
    counts: Counter = Counter()
    weights = [w for _p, w in DEMO_PATHS]
    for i in range(days):
        day = today - timedelta(days=days - 1 - i)
        growth = 0.6 + 0.8 * i / days  # AI search bots ramp up over the month
        for bot, rate in DEMO_RATES.items():
            n = max(0, int(rng.gauss(rate * (growth if bot in ("OAI-SearchBot", "ChatGPT-User", "Claude-User", "Perplexity-User") else 1), rate * 0.25)))
            for _ in range(n):
                path = rng.choices([p for p, _w in DEMO_PATHS], weights)[0]
                status = 404 if path.endswith("old-formula-page") else (403 if bot == "CCBot" else (304 if rng.random() < 0.08 else 200))
                counts[(day, bot, path, status)] += 1
    store(session, "demo-access.log", counts, sum(counts.values()) * 9, 0, is_demo=True)
    return sum(counts.values())


def analytics(session: Session, days: int = 28) -> dict[str, Any]:
    real = session.scalar(select(func.count()).select_from(LogUpload).where(LogUpload.kind == "crawler", LogUpload.is_demo.is_(False))) or 0
    uploads = list(session.scalars(select(LogUpload).where(LogUpload.kind == "crawler", LogUpload.is_demo.is_(real == 0)).order_by(LogUpload.uploaded_at.desc())))
    ids = [u.id for u in uploads]
    rows = list(session.scalars(select(CrawlerHit).where(CrawlerHit.upload_id.in_(ids)))) if ids else []
    if rows:
        end = max(r.day for r in rows)
        start = end - timedelta(days=days - 1)
        rows = [r for r in rows if r.day >= start]
    by_bot: dict[str, dict[str, Any]] = {}
    daily: dict[str, Counter] = defaultdict(Counter)
    pages: dict[str, Counter] = defaultdict(Counter)
    status: Counter = Counter()
    for r in rows:
        b = by_bot.setdefault(r.bot, {"bot": r.bot, **BOT_INFO.get(r.bot, {"company": "", "purpose": ""}), "hits": 0, "errors": 0, "pages": set(), "last_seen": r.day})
        b["hits"] += r.hits
        b["errors"] += r.hits if r.status >= 400 else 0
        b["pages"].add(r.path)
        b["last_seen"] = max(b["last_seen"], r.day)
        daily[r.day.isoformat()][r.bot] += r.hits
        pages[r.path][r.bot] += r.hits
        status[f"{r.status // 100}xx"] += r.hits
    bots = sorted(({**b, "pages": len(b["pages"])} for b in by_bot.values()), key=lambda b: -b["hits"])
    # Chart: the four busiest bots, the rest folded into "Other" (four colour slots).
    top = [b["bot"] for b in bots[:4]]
    series = [{"day": d, **{bot: c.get(bot, 0) for bot in top}, "Other": sum(v for k, v in c.items() if k not in top)} for d, c in sorted(daily.items())]
    if len(bots) > 4:
        top.append("Other")
    page_rows = sorted(({"path": p, "hits": sum(c.values()), "bots": dict(c.most_common())} for p, c in pages.items()), key=lambda r: -r["hits"])[:20]
    err: dict[tuple[str, int], Counter] = defaultdict(Counter)
    for r in rows:
        if r.status >= 400:
            err[(r.path, r.status)][r.bot] += r.hits
    audited = {urlsplit(u.url).path or "/" for u in session.scalars(select(AuditUrl))}
    ai_bots = {name for name, _c, p, _k in BOTS if "search" in p or "user" in p or "training" in p} - {"Googlebot", "Bingbot", "Applebot"}
    crawled_by_ai = {r.path for r in rows if r.bot in ai_bots}
    return {
        "demo": real == 0 and bool(uploads),
        "uploads": [{"id": u.id, "filename": u.filename, "uploaded_at": u.uploaded_at, "lines": u.lines, "matched": u.matched, "skipped": u.skipped,
                     "first_day": u.first_day, "last_day": u.last_day, "is_demo": u.is_demo} for u in uploads],
        "total": sum(b["hits"] for b in bots),
        "bots": bots,
        "series": series,
        "series_bots": top,
        "pages": page_rows,
        "status": dict(status),
        "errors": sorted(({"path": p, "status": s, "hits": sum(c.values()), "bots": [b for b, _n in c.most_common()]} for (p, s), c in err.items()), key=lambda e: -e["hits"])[:20],
        "not_crawled": sorted(audited - crawled_by_ai),
        "known_bots": [{"bot": n, "company": c, "purpose": p} for n, c, p, _k in BOTS],
    }
