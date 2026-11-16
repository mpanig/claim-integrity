"""llms.txt: check a brand site's /llms.txt against the llmstxt.org format, and draft one.

Format (llmstxt.org): Markdown with one H1 (site or project name) first, then an optional
blockquote summary, optional prose, then H2 sections holding lists of links written as
"- [name](url): notes". A section called "Optional" holds links that can be skipped.
A companion /llms-full.txt may hold the full text.

The check fetches /llms.txt and /llms-full.txt once each, after robots.txt, with the audit's
honest User-Agent. Nothing is fetched if robots.txt or the
site refuses. Demo checks are flagged and hidden for a host once it has a real check.
"""

import re
from typing import Any
from urllib.parse import urlsplit

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.ai.analyse import load_entities
from app.ai.perception import ATTRIBUTES
from app.audit.run import USER_AGENT, PoliteFetcher
from app.models import ApprovedClaim, Brand, LlmsCheck, Organisation, Sku
from app.pipeline.run import truth_for_sku

LINK = re.compile(r"^\s*[-*]\s+\[([^\]]+)\]\(([^)\s]+)\)(?::\s*(.*))?\s*$")
MAX_BYTES = 200_000


def parse(text: str, host: str) -> dict[str, Any]:
    """Validate llms.txt text. Returns score 0-100, issues, and what was found."""
    lines = text.splitlines()
    content = [line for line in lines if line.strip()]
    h1 = [line for line in lines if re.match(r"^#\s+\S", line)]
    first_is_h1 = bool(content) and re.match(r"^#\s+\S", content[0]) is not None
    summary = next((line.lstrip("> ").strip() for line in content[1:4] if line.startswith(">")), None)
    sections: list[dict[str, Any]] = []
    bad_links: list[str] = []
    for line in lines:
        if re.match(r"^##\s+\S", line):
            sections.append({"title": line[2:].strip(), "links": 0})
        m = LINK.match(line)
        if m and sections:
            sections[-1]["links"] += 1
            url = m.group(2)
            if not url.startswith(("http://", "https://")):
                bad_links.append(url)
        elif m and not sections:
            bad_links.append(f"{m.group(2)} (outside any H2 section)")
    links = sum(s["links"] for s in sections)
    own = sum(1 for line in lines if (m := LINK.match(line)) and host in (urlsplit(m.group(2)).hostname or ""))

    checks = [
        ("One H1 title first", 20, first_is_h1 and len(h1) == 1, "Start the file with exactly one H1: the brand or site name."),
        ("Summary blockquote", 15, bool(summary), "Add a one-paragraph summary as a blockquote (> ...) right after the H1."),
        ("Sections of links", 20, any(s["links"] for s in sections), "Group key pages under H2 headings as '- [Name](https://...): what it covers'."),
        ("Absolute, valid links", 15, links > 0 and not bad_links, "Use full https:// URLs for every link, inside an H2 section."),
        ("Links to your own pages", 10, own >= 3, "Link at least 3 pages on your own site (products, ingredients, FAQs)."),
        ("Product coverage", 10, links >= 5, "List each key product page with a one-line note of what it is."),
        ("Optional section", 5, any(s["title"].lower() == "optional" for s in sections), "Put nice-to-have links under '## Optional' so tools can skip them."),
        ("Reasonable size", 5, len(text.encode()) <= MAX_BYTES, "Keep llms.txt short (well under 200 KB); move full text to /llms-full.txt."),
    ]
    return {
        "score": sum(p for _l, p, ok, _f in checks if ok),
        "checks": [{"label": label, "points": p, "passed": bool(ok), "fix": None if ok else fix} for label, p, ok, fix in checks],
        "title": h1[0][1:].strip() if h1 else None,
        "summary": summary,
        "sections": sections,
        "links": links,
        "bad_links": bad_links[:10],
        "bytes": len(text.encode()),
    }


def brand_hosts(session: Session) -> list[tuple[Brand, str]]:
    org = session.scalars(select(Organisation)).first()
    if not org:
        return []
    by_id = {b.id: b for b in session.scalars(select(Brand))}
    out = []
    for e in load_entities(session, org.id)[0]:
        if e.is_own and e.brand_id in by_id:
            out += [(by_id[e.brand_id], h) for h in e.site_hosts]
    return out


def check_host(session: Session, host: str, brand_id: int | None = None, *, transport: httpx.BaseTransport | None = None) -> LlmsCheck:
    org = session.scalars(select(Organisation)).first()
    row = LlmsCheck(organisation_id=org.id, brand_id=brand_id, host=host, status="missing")
    base = f"https://{host}"
    fetcher = PoliteFetcher(transport=transport, sleep=lambda _s: None)
    try:
        robots = fetcher.robots(base + "/llms.txt")
        if base in fetcher.refused or (robots is not None and not robots.can_fetch(USER_AGENT, base + "/llms.txt")):
            row.status = "blocked"
            row.result = {"note": "robots.txt or the site refuses automated requests, so /llms.txt was not fetched."}
        else:
            res = fetcher.get(base + "/llms.txt")
            row.http_status = res.status_code
            if res.status_code == 200 and not res.text.lstrip().lower().startswith(("<!doctype", "<html")):
                parsed = parse(res.text, host)
                full = fetcher.get(base + "/llms-full.txt")
                parsed["full_txt"] = full.status_code == 200 and not full.text.lstrip().lower().startswith(("<!doctype", "<html"))
                row.status, row.score, row.result = "found", parsed["score"], parsed
            elif res.status_code in (401, 403, 429):
                row.status = "blocked"
                row.result = {"note": f"The site answered HTTP {res.status_code}."}
            else:
                row.result = {"note": "No /llms.txt on this site" + (" (the URL returns a web page instead)." if res.status_code == 200 else f" (HTTP {res.status_code}).")}
    except httpx.HTTPError as e:
        row.status = "error"
        row.result = {"note": f"Could not fetch: {type(e).__name__}"}
    finally:
        fetcher.close()
    session.add(row)
    session.commit()
    return row


def generate(session: Session, brand: Brand) -> str:
    """A draft llms.txt for a brand from its products, approved facts and positioning."""
    skus = list(session.scalars(select(Sku).where(Sku.brand_id == brand.id).order_by(Sku.name)))
    host = next((h for b, h in brand_hosts(session) if b.id == brand.id), None)
    site = f"https://{host}" if host else "https://YOUR-SITE"
    focus = [ATTRIBUTES[k][0].lower() for k in brand.positioning or [] if k in ATTRIBUTES]
    lines = [f"# {brand.name}", ""]
    summary = f"{brand.name} makes skincare"
    if focus:
        summary += " known for " + ", ".join(focus[:-1]) + (" and " if len(focus) > 1 else "") + focus[-1]
    lines += [f"> {summary}. Product facts below come from approved product information.", ""]
    lines += ["Use the product pages for current ingredients and claims; retailer listings can be out of date.", "", "## Products", ""]
    for s in skus:
        truth = truth_for_sku(session, s)
        url = session.scalar(select(ApprovedClaim.evidence_url).where(ApprovedClaim.sku_id == s.id, ApprovedClaim.evidence_url.is_not(None)).limit(1))
        notes = [", ".join(truth[k]) for k in ("claims", "free_from", "seals") if truth.get(k)]
        if truth.get("ingredients"):
            notes.append(f"{len(truth['ingredients'])} listed ingredients")
        lines.append(f"- [{s.name}]({url or site + '/'}): {'; '.join(notes) or 'product page'}")
    # Pages every brand site has; the paths are placeholders to replace with yours.
    lines += ["", "## Ingredients and safety", "", f"- [Ingredient glossary]({site}/REPLACE-ingredients-page): what each key ingredient does", ""]
    lines += ["## Optional", "", f"- [About {brand.name}]({site}/REPLACE-about-page): brand background", ""]
    return "\n".join(lines)


DEMO = {
    "cerave.com": "# CeraVe\n\n> Skincare developed with dermatologists, with three essential ceramides.\n\n## Products\n\n- [Hydrating Facial Cleanser](https://www.cerave.com/skincare/cleansers/hydrating-facial-cleanser): non-foaming cleanser for normal to dry skin\n- [Moisturizing Cream](https://www.cerave.com/skincare/moisturizers/moisturizing-cream): rich cream for dry skin\n- [Ceramides explained](/science/ceramides)\n",
}


def generate_demo_checks(session: Session) -> int:
    """Demo checks for the brand sites (no network): CeraVe has a partial llms.txt, others none."""
    session.execute(delete(LlmsCheck).where(LlmsCheck.is_demo.is_(True)))
    org = session.scalars(select(Organisation)).first()
    n = 0
    for brand, host in brand_hosts(session):
        text = DEMO.get(host.removeprefix("www."))
        if text:
            parsed = {**parse(text, host), "full_txt": False}
            row = LlmsCheck(organisation_id=org.id, brand_id=brand.id, host=host, status="found", http_status=200, score=parsed["score"], result=parsed, is_demo=True)
        else:
            row = LlmsCheck(organisation_id=org.id, brand_id=brand.id, host=host, status="missing", http_status=404, result={"note": "No /llms.txt on this site (HTTP 404)."}, is_demo=True)
        session.add(row)
        n += 1
    session.commit()
    return n


def latest_checks(session: Session) -> list[dict[str, Any]]:
    rows = session.scalars(select(LlmsCheck).order_by(LlmsCheck.checked_at.desc(), LlmsCheck.id.desc())).all()
    real = {r.host for r in rows if not r.is_demo}
    names = {b.id: b.name for b in session.scalars(select(Brand))}
    seen: dict[str, dict[str, Any]] = {}
    for r in rows:
        if r.host in seen or (r.is_demo and r.host in real):
            continue
        seen[r.host] = {"id": r.id, "host": r.host, "brand_id": r.brand_id, "brand_name": names.get(r.brand_id), "checked_at": r.checked_at, "status": r.status,
                        "http_status": r.http_status, "score": r.score, "result": r.result, "is_demo": r.is_demo}
    for brand, host in brand_hosts(session):  # sites never checked still show
        seen.setdefault(host, {"id": None, "host": host, "brand_id": brand.id, "brand_name": brand.name, "checked_at": None, "status": "unchecked",
                               "http_status": None, "score": None, "result": {}, "is_demo": False})
    return sorted(seen.values(), key=lambda r: (r["brand_name"] or "", r["host"]))
