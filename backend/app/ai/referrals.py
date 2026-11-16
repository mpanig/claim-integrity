"""AI referral traffic from an analytics CSV export (GA4 or any tool).

The CSV needs a date column (date / day; YYYYMMDD or ISO), a source column (session source,
session source / medium, source, referrer, source / medium) and a sessions column (sessions,
visits, users). Optional: conversions (key events, conversions, purchases, transactions) and
landing page (landing page, landing page + query string, page). GA4's export preamble lines
starting with "#" are skipped.

Sources are matched to AI assistants by domain; everything else is kept only as one "Other"
total per day so the AI share can be shown. A direct GA4 connection is not built yet (it
needs a service account); the CSV export is the supported route.

Demo data (one flagged import) shows until the first real import.
"""

import csv
import io
import random
from collections import Counter, defaultdict
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.ai.engines import engine_env
from app.models import LogUpload, Organisation, ReferralVisit

# label, domains (substring match on the source value)
SOURCES: list[tuple[str, tuple[str, ...]]] = [
    ("ChatGPT", ("chatgpt.com", "chat.openai.com", "openai.com")),
    ("Perplexity", ("perplexity.ai", "perplexity")),
    ("Gemini", ("gemini.google.com", "bard.google.com")),
    ("Copilot", ("copilot.microsoft.com", "copilot.cloud.microsoft", "edgeservices.bing.com")),
    ("Claude", ("claude.ai",)),
    ("DeepSeek", ("chat.deepseek.com", "deepseek")),
    ("Meta AI", ("meta.ai",)),
]
AI_LABELS = [s for s, _d in SOURCES]
MAX_BYTES = 50 * 1024 * 1024


def source_for(value: str) -> str | None:
    low = value.lower()
    return next((label for label, domains in SOURCES if any(d in low for d in domains)), None)


def _num(v: str | None) -> float:
    try:
        return float((v or "0").replace(",", "").strip() or 0)
    except ValueError:
        return 0.0


def _day(v: str) -> date | None:
    v = v.strip()
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(v[:10] if fmt != "%Y%m%d" else v[:8], fmt).date()
        except ValueError:
            continue
    return None


def parse_csv(text: str) -> tuple[Counter, Counter, int, int]:
    """(sessions, conversions) keyed by (day, source, landing); rows read; rows skipped."""
    body = "\n".join(line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#"))
    reader = csv.DictReader(io.StringIO(body))
    cols = {c.lower().strip(): c for c in (reader.fieldnames or [])}
    pick = lambda *names: next((cols[n] for n in names if n in cols), None)  # noqa: E731
    d = pick("date", "day")
    s = pick("session source", "session source / medium", "source", "source / medium", "referrer", "session source/medium")
    n = pick("sessions", "visits", "users", "total users")
    c = pick("key events", "conversions", "purchases", "transactions")
    lp = pick("landing page", "landing page + query string", "page", "landing")
    if not (d and s and n):
        raise ValueError("CSV needs date, source and sessions columns")
    sessions: Counter = Counter()
    conversions: Counter = Counter()
    rows = skipped = 0
    for row in reader:
        rows += 1
        day = _day(row.get(d) or "")
        if day is None:
            skipped += 1
            continue
        label = source_for(row.get(s) or "")
        landing = ((row.get(lp) or "").split("?")[0][:500] or "/") if (lp and label) else ""
        key = (day, label or "Other", landing)
        sessions[key] += int(_num(row.get(n)))
        conversions[key] += _num(row.get(c)) if c else 0
    return sessions, conversions, rows, skipped


def store(session: Session, filename: str, sessions: Counter, conversions: Counter, rows: int, skipped: int, *, is_demo: bool = False) -> LogUpload:
    org = session.scalars(select(Organisation)).first()
    days = [k[0] for k in sessions]
    up = LogUpload(organisation_id=org.id, kind="referral", filename=filename[:300], lines=rows,
                   matched=sum(v for k, v in sessions.items() if k[1] != "Other"), skipped=skipped,
                   first_day=min(days) if days else None, last_day=max(days) if days else None, is_demo=is_demo)
    session.add(up)
    session.flush()
    session.add_all(ReferralVisit(upload_id=up.id, day=dd, source=src, landing=lp, sessions=v, conversions=conversions.get((dd, src, lp), 0)) for (dd, src, lp), v in sessions.items())
    session.commit()
    return up


def ingest(session: Session, filename: str, data: bytes) -> LogUpload:
    if len(data) > MAX_BYTES:
        raise ValueError("File is larger than 50 MB")
    return store(session, filename, *parse_csv(data.decode("utf-8-sig", errors="replace")))


DEMO_SHARE = {"ChatGPT": 62, "Perplexity": 21, "Gemini": 9, "Copilot": 6, "Claude": 4}
DEMO_PAGES = [("/skincare/cleansers/hydrating-facial-cleanser", 5), ("/skincare/moisturizers/moisturizing-cream", 3), ("/", 2), ("/science/ceramides", 1), ("/products/calm-restore-nourishing-oat-cleanser", 1)]


def generate_demo_referrals(session: Session, days: int = 56, seed: int = 5) -> int:
    ids = list(session.scalars(select(LogUpload.id).where(LogUpload.is_demo.is_(True), LogUpload.kind == "referral")))
    if ids:
        session.execute(delete(ReferralVisit).where(ReferralVisit.upload_id.in_(ids)))
        session.execute(delete(LogUpload).where(LogUpload.id.in_(ids)))
    rng = random.Random(seed)
    today = datetime.now(UTC).date()
    sessions: Counter = Counter()
    conversions: Counter = Counter()
    for i in range(days):
        day = today - timedelta(days=days - 1 - i)
        growth = 1 + 1.2 * i / days
        weekend = 0.8 if day.weekday() >= 5 else 1.0
        for label, base in DEMO_SHARE.items():
            total = max(0, int(rng.gauss(base * growth * weekend, base * 0.15)))
            for _ in range(total):
                lp = rng.choices([p for p, _w in DEMO_PAGES], [w for _p, w in DEMO_PAGES])[0]
                sessions[(day, label, lp)] += 1
                conversions[(day, label, lp)] += 1 if rng.random() < 0.045 else 0
        other = int(rng.gauss(5200 * weekend, 300))
        sessions[(day, "Other", "")] += other
        conversions[(day, "Other", "")] += round(other * 0.021)
    store(session, "demo-ga4-traffic-acquisition.csv", sessions, conversions, len(sessions), 0, is_demo=True)
    return sum(v for k, v in sessions.items() if k[1] != "Other")


def referrals(session: Session, days: int = 56) -> dict[str, Any]:
    real = session.scalar(select(func.count()).select_from(LogUpload).where(LogUpload.kind == "referral", LogUpload.is_demo.is_(False))) or 0
    uploads = list(session.scalars(select(LogUpload).where(LogUpload.kind == "referral", LogUpload.is_demo.is_(real == 0)).order_by(LogUpload.uploaded_at.desc())))
    ids = [u.id for u in uploads]
    rows = list(session.scalars(select(ReferralVisit).where(ReferralVisit.upload_id.in_(ids)))) if ids else []
    if rows:
        end = max(r.day for r in rows)
        rows = [r for r in rows if r.day > end - timedelta(days=days)]
    by_src: dict[str, dict[str, float]] = defaultdict(lambda: {"sessions": 0, "conversions": 0.0})
    weekly: dict[str, Counter] = defaultdict(Counter)
    pages: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        by_src[r.source]["sessions"] += r.sessions
        by_src[r.source]["conversions"] += r.conversions
        wk = (r.day - timedelta(days=r.day.weekday())).isoformat()
        weekly[wk][r.source] += r.sessions
        if r.source != "Other":
            pages[r.landing][r.source] += r.sessions
    ai_sessions = sum(v["sessions"] for k, v in by_src.items() if k != "Other")
    ai_conv = sum(v["conversions"] for k, v in by_src.items() if k != "Other")
    other = by_src.get("Other", {"sessions": 0, "conversions": 0.0})
    total = ai_sessions + other["sessions"]
    sources = sorted(
        ({"source": k, "sessions": int(v["sessions"]), "conversions": round(v["conversions"], 1),
          "conversion_rate": round(v["conversions"] / v["sessions"], 4) if v["sessions"] else None,
          "share_of_ai": round(v["sessions"] / ai_sessions, 3) if ai_sessions else None}
         for k, v in by_src.items() if k != "Other"),
        key=lambda s: -s["sessions"],
    )
    top = [s["source"] for s in sources[:4]]
    # Whole weeks only: a partial first or last week would look like a drop.
    days_in: dict[str, set] = defaultdict(set)
    for r in rows:
        days_in[(r.day - timedelta(days=r.day.weekday())).isoformat()].add(r.day)
    full = [wk for wk in sorted(weekly) if len(days_in[wk]) == 7]
    series = [{"day": wk, **{src: weekly[wk].get(src, 0) for src in top}, **({"Other AI": sum(v for k, v in weekly[wk].items() if k not in top and k != "Other")} if len(sources) > 4 else {})}
              for wk in full]
    # Last 28 days vs the 28 before (needs 56 days of data).
    change = None
    if rows:
        end = max(r.day for r in rows)
        recent = sum(r.sessions for r in rows if r.source != "Other" and r.day > end - timedelta(days=28))
        before = sum(r.sessions for r in rows if r.source != "Other" and end - timedelta(days=56) < r.day <= end - timedelta(days=28))
        if before and min(r.day for r in rows) <= end - timedelta(days=55):
            change = round(recent / before - 1, 3)
    env = engine_env()
    return {
        "demo": real == 0 and bool(uploads),
        "uploads": [{"id": u.id, "filename": u.filename, "uploaded_at": u.uploaded_at, "lines": u.lines, "matched": u.matched, "skipped": u.skipped,
                     "first_day": u.first_day, "last_day": u.last_day, "is_demo": u.is_demo} for u in uploads],
        "ai_sessions": int(ai_sessions),
        "ai_share": round(ai_sessions / total, 4) if total and other["sessions"] else None,
        "ai_conversion_rate": round(ai_conv / ai_sessions, 4) if ai_sessions else None,
        "other_conversion_rate": round(other["conversions"] / other["sessions"], 4) if other["sessions"] else None,
        "change_28d": change,
        "sources": sources,
        "series": series,
        "series_keys": top + (["Other AI"] if len(sources) > 4 else []),
        "pages": sorted(({"landing": p, "sessions": sum(c.values()), "sources": dict(c.most_common(3))} for p, c in pages.items()), key=lambda r: -r["sessions"])[:15],
        "known_sources": [{"source": label, "domains": list(d)} for label, d in SOURCES],
        "ga4": {"status": "property id set, connector not built yet" if env.get("GA4_PROPERTY_ID") else "not connected", "property_set": bool(env.get("GA4_PROPERTY_ID"))},
    }
