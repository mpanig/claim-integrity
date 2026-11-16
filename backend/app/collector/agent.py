"""The collector agent loop.

collect(brand, skus, budget):
  1. pick connectors: enabled in settings and with their keys present (others are skipped with a reason)
  2. discover candidates per product: Claude plans the searches when ANTHROPIC_API_KEY is set,
     otherwise fixed query templates; brand site, product database, news and Wikidata always run
  3. relevance: GTIN, then token match; borderline -> Claude decides, or "needs review"
  4. relevant pages: fetch (direct -> rendered -> Jina Reader), extract (deterministic, then Claude),
     store page + snapshot + extraction
  5. re-run the existing compare for every product touched
Everything is logged on a CollectorRun. A request budget caps the run.
"""

import os
from collections import Counter, defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from dotenv import dotenv_values
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collector.base import BrandInfo, Candidate, Context, Parsed, SkuInfo
from app.collector.connectors import ALL, BY_NAME, default_queries, product_words
from app.collector.extract import visible_text
from app.collector.http import Blocked, BudgetExceeded, PoliteClient, canonical_url, is_blocked_host
from app.collector.llm import Claude, ClaudeRefused
from app.collector.relevance import score_candidate
from app.config import BACKEND_DIR
from app.models import (
    ApprovedClaim,
    Brand,
    CandidateStatus,
    CollectorRun,
    ConnectorSetting,
    Extraction,
    Page,
    SourceCandidate,
    Sku,
)
from app.pipeline.fetch import store_snapshot
from app.pipeline.run import run_for_sku

SOURCE_WEIGHT = {"brand": 1.0, "retailer": 1.0, "database": 0.5, "article": 0.4, "review": 0.5}
SEARCH_SOURCES = {"web_search": "web", "exa_search": "web_exa", "gdelt_news": "news", "reddit": "reddit", "youtube": "youtube"}
S = CandidateStatus


def load_env() -> dict[str, str]:
    """Process environment over backend/.env. Values are only ever passed to connectors, never logged."""
    file_values = {k: v for k, v in dotenv_values(BACKEND_DIR / ".env").items() if v}
    return {**file_values, **{k: v for k, v in os.environ.items() if v}}


def connector_states(session: Session, env: dict[str, str]) -> list[dict[str, Any]]:
    settings = {s.name: s.enabled for s in session.scalars(select(ConnectorSetting))}
    out = []
    for c in ALL:
        enabled = settings.get(c.name, True)
        reason = None if enabled else "turned off in Data sources"
        reason = reason or c.availability(env)
        out.append(
            {
                "name": c.name,
                "label": c.label,
                "description": c.description,
                "source_type": c.source_type,
                "kind": c.kind,
                "needs_key": " and ".join(c.needs_key) if c.needs_key else ("KEEPA_API_KEY or RAINFOREST_API_KEY" if c.name == "amazon" else None),
                "key_optional": c.key_optional,
                "key_present": c.key_present(env) if (c.needs_key or c.name == "amazon") else None,
                "enabled": enabled,
                "runnable": reason is None,
                "skip_reason": reason,
                "interval_seconds": c.interval,
                "weight": c.weight,
            }
        )
    return out


def brand_info(session: Session, brand: Brand) -> BrandInfo:
    site = session.scalar(
        select(ApprovedClaim.evidence_url)
        .join(Sku, ApprovedClaim.sku_id == Sku.id)
        .where(Sku.brand_id == brand.id, ApprovedClaim.evidence_url.is_not(None))
        .limit(1)
    )
    return BrandInfo(brand.id, brand.name, site)


def sku_info(sku: Sku) -> SkuInfo:
    return SkuInfo(sku.id, sku.name, sku.gtin, sku.line)


# ---------------------------------------------------------------------------- storing


def _existing(session: Session, brand_id: int, sku_id: int | None, canon: str) -> SourceCandidate | None:
    return session.scalar(
        select(SourceCandidate).where(
            SourceCandidate.brand_id == brand_id,
            SourceCandidate.sku_id.is_(None) if sku_id is None else SourceCandidate.sku_id == sku_id,
            SourceCandidate.canonical_url == canon,
        )
    )


def save_page(session: Session, row: SourceCandidate, fetched, parsed: Parsed, via: str) -> Page:
    page = session.scalar(select(Page).where(Page.url == row.url))
    if page is None:
        from app.collector.http import host_of

        label = "Open Beauty Facts" if row.connector == "open_beauty_facts" else host_of(row.url).removeprefix("www.")
        page = Page(
            organisation_id=row.organisation_id,
            url=row.url,
            source_type=row.source_type,
            retailer=label,
            weight=SOURCE_WEIGHT.get(row.source_type, 0.5),
        )
        session.add(page)
        session.flush()
    snapshot = store_snapshot(session, page, fetched.text)
    if snapshot is not None:
        fields = dict(parsed.fields)
        fields["_meta"] = {"partial": True, "method": parsed.method, "connector": row.connector, "via": via}
        session.add(Extraction(organisation_id=row.organisation_id, snapshot_id=snapshot.id, sku_id=row.sku_id, fields=fields))
    row.page_id = page.id
    return page


def process_candidate(session: Session, ctx: Context, row: SourceCandidate, brand: BrandInfo, sku: SkuInfo | None, cand: Candidate | None = None) -> bool:
    """Fetch, extract and store one relevant page. Returns True if a page was stored."""
    connector = BY_NAME.get(row.connector)
    cand = cand or Candidate(url=row.url, connector=row.connector, source_type=row.source_type, kind=row.kind, title=row.title or "", data=row.data)
    if connector is None or row.kind != "page" or sku is None:
        return False
    if row.connector == "open_beauty_facts" and cand.parsed is None and row.data:
        from app.collector.connectors import parse_obf

        cand.parsed = parse_obf(row.data)
    try:
        fetched = connector.fetch(ctx, cand)
    except Blocked as e:
        row.fetch_note = str(e)
        return False
    if fetched is None:
        row.fetch_note = "could not fetch enough page text (blocked, empty or JavaScript-only)"
        return False
    parsed = connector.parse(fetched, cand) or Parsed()
    if ctx.claude and fetched.via != "api":
        text = fetched.text
        if "html" in fetched.content_type:
            from bs4 import BeautifulSoup

            text = visible_text(BeautifulSoup(fetched.text, "html.parser"))
        try:
            for field, value in ctx.claude.extract(brand.name, sku.name, text).items():
                parsed.fields.setdefault(field, value)
            parsed.method = "+".join(x for x in (parsed.method, "llm") if x)
        except ClaudeRefused as e:
            ctx.note("llm_extract", url=row.url, error=str(e))
    if parsed.gtin and sku.gtin and parsed.gtin.lstrip("0") != sku.gtin.lstrip("0"):
        row.status = S.rejected
        row.relevance_reason = f"page GTIN {parsed.gtin} is a different product"
        return False
    row.extracted_fields = sorted(k for k in parsed.fields if not k.startswith("_"))
    row.extraction_method = parsed.method or "none"
    row.fetch_note = f"fetched via {fetched.via}"
    if not row.extracted_fields:
        row.fetch_note += "; no claim fields found"
        return False
    save_page(session, row, fetched, parsed, fetched.via)
    return True


def _decide(ctx: Context, cand: Candidate, brand: BrandInfo, sku: SkuInfo | None) -> tuple[CandidateStatus, float, str]:
    if is_blocked_host(cand.url):
        return S.rejected, 0.0, "never fetched directly (licensed data only)"
    scored = score_candidate(cand, brand, None if cand.kind != "page" else sku)
    if scored.status == "relevant":
        return S.relevant, scored.score, scored.reason
    if scored.status == "rejected":
        return S.rejected, scored.score, scored.reason
    if ctx.claude and sku is not None:
        try:
            v = ctx.claude.verify_relevance(brand.name, sku.name, cand.title, cand.url, cand.snippet)
            return (S.relevant if v.is_target_product else S.rejected), scored.score, f"{scored.reason}; Claude: {v.reason}"
        except ClaudeRefused:
            pass
    return S.needs_review, scored.score, f"{scored.reason}; borderline, needs review"


# ---------------------------------------------------------------------------- the loop


def collect(
    session: Session,
    brand_id: int,
    sku_ids: list[int] | None = None,
    budget: int = 50,
    *,
    env: dict[str, str] | None = None,
    claude: Claude | None = None,
    http: PoliteClient | None = None,
    run: CollectorRun | None = None,
    max_plan_steps: int = 6,
    on_progress: Callable[[CollectorRun], None] | None = None,
) -> CollectorRun:
    env = load_env() if env is None else env
    brand_row = session.get(Brand, brand_id)
    if brand_row is None:
        raise ValueError(f"brand {brand_id} not found")
    skus = session.scalars(select(Sku).where(Sku.brand_id == brand_id).order_by(Sku.id)).all()
    if sku_ids:
        skus = [s for s in skus if s.id in set(sku_ids)]
    if run is None:
        run = CollectorRun(organisation_id=brand_row.organisation_id, brand_id=brand_id, sku_ids=[s.id for s in skus], budget=budget)
        session.add(run)
        session.commit()

    claude = claude if claude is not None else Claude.from_env(env)
    http = http or PoliteClient(budget=budget)
    states = connector_states(session, env)
    runnable = {s["name"] for s in states if s["runnable"]}
    ctx = Context(http=http, env=env, claude=claude, enabled=runnable)
    stats: dict[str, dict[str, Any]] = {
        s["name"]: ({"status": "ready", **Counter()} if s["runnable"] else {"status": "skipped", "reason": s["skip_reason"]}) for s in states
    }
    for s in states:
        if not s["runnable"]:
            ctx.note("skip", connector=s["name"], reason=s["skip_reason"])
    for name in runnable:
        BY_NAME[name].prepare(ctx)
    run.planner = "claude" if claude else "templates"

    brand = brand_info(session, brand_row)
    touched: set[int] = set()
    skipped: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    counts = Counter()

    def bump(connector: str, key: str, n: int = 1) -> None:
        st = stats[connector]
        st[key] = st.get(key, 0) + n
        st["status"] = "ran"

    def record(cand: Candidate, sku_row: Sku | None) -> None:
        sku = sku_info(sku_row) if sku_row else None
        canon = canonical_url(cand.url)
        row = _existing(session, brand.id, sku.id if sku else None, canon)
        bump(cand.connector, "candidates")
        if row is not None:
            bump(cand.connector, "duplicates")
            if row.status is S.relevant and row.kind == "page" and row.page_id is None and sku:
                if process_candidate(session, ctx, row, brand, sku, cand):
                    bump(cand.connector, "fetched")
                    counts["fetched"] += 1
                    touched.add(sku.id)
            return
        status, score, reason = _decide(ctx, cand, brand, sku)
        row = SourceCandidate(
            organisation_id=brand_row.organisation_id,
            brand_id=brand.id,
            sku_id=sku.id if sku else None,
            run_id=run.id,
            connector=cand.connector,
            source_type=cand.source_type,
            kind=cand.kind,
            url=cand.url,
            canonical_url=canon,
            title=cand.title[:1000] or None,
            why=cand.why or None,
            snippet=cand.snippet[:2000] or None,
            status=status,
            relevance_score=score,
            relevance_reason=reason,
            data=cand.data,
        )
        session.add(row)
        session.flush()
        counts["found"] += 1
        bump(cand.connector, status.value)
        if status is S.rejected:
            skipped.append({"url": cand.url, "reason": reason})
        if status is S.relevant and cand.kind == "page" and sku:
            if process_candidate(session, ctx, row, brand, sku, cand):
                bump(cand.connector, "fetched")
                counts["fetched"] += 1
                touched.add(sku.id)
            elif row.fetch_note:
                skipped.append({"url": cand.url, "reason": row.fetch_note})
        session.commit()

    def run_connector(name: str, sku_row: Sku | None, queries: list[str]) -> list[Candidate]:
        try:
            found = BY_NAME[name].discover(ctx, brand, sku_info(sku_row) if sku_row else None, queries)
        except BudgetExceeded:
            raise
        except Exception as e:  # one connector failing must not stop the run
            errors.append({"connector": name, "error": f"{type(e).__name__}: {e}"[:300]})
            stats[name]["status"] = "error"
            ctx.note("error", connector=name, error=f"{type(e).__name__}: {e}"[:300])
            return []
        stats[name]["status"] = "ran"
        stats[name]["searches"] = stats[name].get("searches", 0) + 1
        for cand in found:
            record(cand, sku_row)
        return found

    try:
        for sku_row in [None, *skus]:  # None = brand-level (Wikidata, brand news)
            sku = sku_info(sku_row) if sku_row else None
            queries = default_queries(brand, sku)
            searchers = [n for n in SEARCH_SOURCES if n in runnable]
            if claude and sku and searchers:
                tools = {
                    SEARCH_SOURCES[n]: (
                        lambda q, n=n: [f"{c.title} | {c.url}" for c in run_connector(n, sku_row, [q])]
                    )
                    for n in searchers
                }
                try:
                    planned = claude.plan(brand.name, product_words(brand, sku), tools, max_steps=max_plan_steps)
                    ctx.note("plan", sku=sku.name, queries=planned)
                except ClaudeRefused as e:
                    ctx.note("plan", sku=sku.name, error=str(e))
                    for n in searchers:
                        run_connector(n, sku_row, queries)
            else:
                for n in searchers:
                    run_connector(n, sku_row, queries)
            for n in ("brand_site", "open_beauty_facts", "wikidata"):
                if n in runnable:
                    run_connector(n, sku_row, queries)
        run.status = "done"
    except BudgetExceeded as e:
        run.status = "done"
        ctx.note("budget", message=str(e))
        errors.append({"connector": "collector", "error": str(e)})
    except Exception as e:
        run.status = "failed"
        errors.append({"connector": "collector", "error": f"{type(e).__name__}: {e}"[:300]})
        session.rollback()
    finally:
        http.close()

    if "jsonld_product" in stats and stats["jsonld_product"]["status"] != "skipped":
        used = sum(1 for e in ctx.log if e.get("step") == "fetch" and e.get("used") in ("direct", "rendered"))
        stats["jsonld_product"].update({"status": "ran" if used else "ready", "pages_parsed": used})
    for name in ("rendered", "jina_reader"):
        if stats.get(name, {}).get("status") != "skipped":
            used = sum(1 for e in ctx.log if e.get("step") == "fetch" and e.get("used") == name)
            stats[name].update({"status": "ran" if used else "ready", "pages_fetched": used})

    for sku_id in touched:
        run_for_sku(session, session.get(Sku, sku_id))

    run.stats = stats
    run.found = counts["found"]
    run.fetched = counts["fetched"]
    run.requests_used = http.used
    run.skipped = skipped[:500]
    run.errors = errors
    run.cost = claude.usage() if claude else {"usd": 0, "calls": 0}
    run.log = ctx.log[-500:]
    run.finished_at = datetime.now(UTC)
    session.commit()
    if on_progress:
        on_progress(run)
    return run


def by_status(session: Session, brand_id: int) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for c in session.scalars(select(SourceCandidate).where(SourceCandidate.brand_id == brand_id)):
        out[c.status.value] += 1
    return dict(out)
