"""Run audits: fetch each entered URL once (robots.txt first) and run the page checks;
check each brand's Wikidata/Wikipedia entry."""

import re
import time
import urllib.robotparser
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.checks import crawlability, freshness, structured_data
from app.models import ApprovedClaim, AuditResult, AuditUrl, Brand, EntityCheck, Sku
from app.pipeline.run import truth_for_sku

USER_AGENT = "claim-integrity-audit/0.1 (checks pages its users entered; respects robots.txt)"
PAUSE = 2.0  # seconds between requests to the same host
STALE_AFTER = timedelta(days=7)  # the worker re-audits weekly


class PoliteFetcher:
    def __init__(self, transport: httpx.BaseTransport | None = None, sleep: Callable[[float], None] = time.sleep):
        self.http = httpx.Client(timeout=20, follow_redirects=True, headers={"User-Agent": USER_AGENT}, transport=transport)
        self.sleep = sleep
        self._last: dict[str, float] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self.refused: set[str] = set()  # sites that refused our robots.txt request (401/403)

    def close(self) -> None:
        self.http.close()

    def get(self, url: str) -> httpx.Response:
        host = urlsplit(url).netloc
        wait = PAUSE - (time.monotonic() - self._last.get(host, -1e9))
        if wait > 0:
            self.sleep(wait)
        self._last[host] = time.monotonic()
        return self.http.get(url)

    def robots(self, url: str) -> urllib.robotparser.RobotFileParser | None:
        parts = urlsplit(url)
        root = f"{parts.scheme}://{parts.netloc}"
        if root not in self._robots:
            parser: urllib.robotparser.RobotFileParser | None = urllib.robotparser.RobotFileParser()
            try:
                res = self.get(f"{root}/robots.txt")
                if res.status_code in (401, 403):
                    self.refused.add(root)  # blocked, not "no rules": don't fetch, don't guess
                    parser = None
                elif res.status_code >= 400:
                    parser = None
                else:
                    parser.parse(res.text.splitlines())
            except httpx.HTTPError:
                parser = None
            self._robots[root] = parser
        return self._robots[root]


def audit_one(session: Session, row: AuditUrl, fetcher: PoliteFetcher) -> AuditResult:
    session.commit()  # hand the DB connection back while we wait on the network
    robots = fetcher.robots(row.url)
    result = AuditResult(audit_url_id=row.id, status="ok")
    parts = urlsplit(row.url)
    if f"{parts.scheme}://{parts.netloc}" in fetcher.refused:
        result.status = "blocked"
        result.note = "The site refused our request for robots.txt (it blocks automated visitors), so the page was not fetched and its AI crawler rules could not be read."
        result.crawlability = {"bots": [], "score": None, "issues": ["robots.txt could not be read: the site refuses automated requests."]}
    elif robots is not None and not robots.can_fetch(USER_AGENT, row.url):
        result.status = "blocked"
        result.note = "robots.txt asks crawlers like ours not to fetch this page, so it was not fetched. AI crawler rules are still shown."
        result.crawlability = crawlability(robots, row.url, None, {}, "")
    else:
        try:
            res = fetcher.get(row.url)
            result.http_status = res.status_code
            headers = {k.lower(): v for k, v in res.headers.items()}
            if res.status_code >= 400:
                result.status = "blocked" if res.status_code in (401, 403, 429) else "error"
                result.note = f"The site answered HTTP {res.status_code}" + (" (it may block automated visitors)" if res.status_code in (401, 403, 429) else "")
                result.crawlability = crawlability(robots, row.url, None, headers, "")
            else:
                html = res.text
                truth = truth_for_sku(session, session.get(Sku, row.sku_id)) if row.sku_id else None
                result.structured = structured_data(BeautifulSoup(html, "html.parser"))
                result.crawlability = crawlability(robots, row.url, BeautifulSoup(html, "html.parser"), headers, html)
                result.freshness = freshness(BeautifulSoup(html, "html.parser"), headers, truth)
        except httpx.HTTPError as e:
            result.status = "error"
            result.note = f"Could not fetch the page: {type(e).__name__}"
    row.last_checked_at = datetime.now(UTC)
    session.add(result)
    session.commit()
    return result


def audit_urls(session: Session, ids: list[int] | None = None, *, only_due: bool = False, transport: httpx.BaseTransport | None = None, sleep: Callable[[float], None] = time.sleep) -> list[AuditResult]:
    q = select(AuditUrl).order_by(AuditUrl.id)
    if ids:
        q = q.where(AuditUrl.id.in_(ids))
    rows = session.scalars(q).all()
    if only_due:
        cutoff = datetime.now(UTC) - STALE_AFTER
        rows = [r for r in rows if r.last_checked_at is None or r.last_checked_at < cutoff]
    fetcher = PoliteFetcher(transport, sleep)
    try:
        return [audit_one(session, r, fetcher) for r in rows]
    finally:
        fetcher.close()


def seed_brand_pages(session: Session, organisation_id: int) -> int:
    """Add each product's approved-truth URL (its brand page) as an audit URL, once."""
    added = 0
    for sku in session.scalars(select(Sku).where(Sku.organisation_id == organisation_id)):
        url = session.scalar(select(ApprovedClaim.evidence_url).where(ApprovedClaim.sku_id == sku.id, ApprovedClaim.evidence_url.is_not(None)).limit(1))
        if url and not session.scalar(select(AuditUrl).where(AuditUrl.url == url)):
            session.add(AuditUrl(organisation_id=organisation_id, brand_id=sku.brand_id, sku_id=sku.id, url=url))
            added += 1
    session.commit()
    return added


# ----------------------------------------------------------------------------- entity clarity

WIKIDATA = "https://www.wikidata.org/w/api.php"
ENTITY_FACTS = {
    "P856": "official website",
    "P749": "parent organisation",
    "P127": "owned by",
    "P571": "founded",
    "P112": "founded by",
    "P17": "country",
    "P452": "industry",
    "P154": "logo",
    "P2002": "X (Twitter) account",
    "P2003": "Instagram account",
}
WEIGHTS = {"description": 10, "wikipedia": 20, "P856": 15, "P749|P127": 15, "P571": 10, "P17": 10, "P452": 5, "P154": 5, "P2002|P2003": 10}


def check_entity(session: Session, brand: Brand, http: httpx.Client) -> EntityCheck:
    row = EntityCheck(brand_id=brand.id, score=0)
    session.commit()  # hand the DB connection back while we wait on the network
    try:
        res = http.get(WIKIDATA, params={"action": "wbsearchentities", "search": brand.name, "language": "en", "type": "item", "limit": 5, "format": "json"})
        hits = res.json().get("search", []) if res.status_code == 200 else []
        exact = [h for h in hits if h.get("label", "").lower() == brand.name.lower()] or hits
        pref = [h for h in exact if re.search(r"brand|company|cosmetic|skin|care|manufacturer", h.get("description", ""), re.I)]
        item = (pref or exact or [None])[0]
        if item is None:
            row.note = "No Wikidata entry found. AI models have no structured facts about this brand."
            row.missing = ["Wikidata entry"]
        else:
            row.qid, row.label = item["id"], item.get("label")
            ent = http.get(WIKIDATA, params={"action": "wbgetentities", "ids": item["id"], "props": "claims|descriptions|sitelinks/urls", "languages": "en", "format": "json"}).json()["entities"][item["id"]]
            row.description = ((ent.get("descriptions") or {}).get("en") or {}).get("value")
            row.wikipedia_url = ((ent.get("sitelinks") or {}).get("enwiki") or {}).get("url")
            claims = ent.get("claims") or {}
            ids: dict[str, list[str]] = {}
            facts: dict[str, list[str]] = {}
            for prop, label in ENTITY_FACTS.items():
                for c in claims.get(prop, []):
                    v = c.get("mainsnak", {}).get("datavalue", {}).get("value")
                    if isinstance(v, dict) and "id" in v:
                        ids.setdefault(label, []).append(v["id"])
                    elif isinstance(v, dict) and "time" in v:
                        facts.setdefault(label, []).append(v["time"].lstrip("+")[:4])
                    elif v is not None:
                        facts.setdefault(label, []).append(str(v))
            qids = sorted({q for qs in ids.values() for q in qs})
            if qids:
                labels = http.get(WIKIDATA, params={"action": "wbgetentities", "ids": "|".join(qids[:50]), "props": "labels", "languages": "en", "format": "json"}).json().get("entities", {})
                for label, qs in ids.items():
                    facts[label] = [labels.get(q, {}).get("labels", {}).get("en", {}).get("value", q) for q in qs]
            row.facts = facts
            score, missing = 0, []
            for key, weight in WEIGHTS.items():
                if key == "description":
                    ok = bool(row.description)
                    name = "a description"
                elif key == "wikipedia":
                    ok = bool(row.wikipedia_url)
                    name = "an English Wikipedia article"
                else:
                    props = key.split("|")
                    ok = any(claims.get(p) for p in props)
                    name = " or ".join(ENTITY_FACTS[p] for p in props)
                score += weight if ok else 0
                if not ok:
                    missing.append(name)
            row.score, row.missing = score, missing
    except (httpx.HTTPError, KeyError, ValueError) as e:
        row.note = f"Could not read Wikidata: {type(e).__name__}"
    session.add(row)
    session.commit()
    return row


def check_entities(session: Session, transport: httpx.BaseTransport | None = None) -> list[EntityCheck]:
    with httpx.Client(timeout=20, headers={"User-Agent": USER_AGENT}, transport=transport) as http:
        return [check_entity(session, b, http) for b in session.scalars(select(Brand).order_by(Brand.name))]


def latest(session: Session) -> dict[str, Any]:
    urls = session.scalars(select(AuditUrl).order_by(AuditUrl.id)).all()
    out = []
    for u in urls:
        r = session.scalar(select(AuditResult).where(AuditResult.audit_url_id == u.id).order_by(AuditResult.checked_at.desc(), AuditResult.id.desc()).limit(1))
        out.append((u, r))
    return {"urls": out}
