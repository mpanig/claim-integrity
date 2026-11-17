"""Page answer-readiness: how easy a page is for AI assistants to quote correctly.

grade_html() scores one page on 12 checks (points add up to 100); each failed check comes
with a fix. grade_url() fetches the page once with the audit's polite fetcher (robots.txt
first, honest User-Agent, nothing fetched if robots.txt or the site says no).

Demo grades come from bundled hand-written pages (fixtures/), flagged is_demo; for a URL
they are hidden as soon as a real grade of that URL exists.
"""

import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
from bs4 import BeautifulSoup
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.audit.checks import freshness, jsonld_blocks
from app.audit.run import USER_AGENT, PoliteFetcher
from app.config import BACKEND_DIR
from app.models import AnswerGrade, Brand, Organisation, Sku

QUESTION = re.compile(r"\?\s*$|^(what|how|is|are|does|do|can|which|why|when|who|should)\b", re.I)
EXPERTISE = re.compile(r"reviewed by|dermatologist|written by|medically reviewed|expert|author", re.I)
NUMBER = re.compile(r"\b\d+(?:[.,]\d+)?\s?(?:%|ml|fl\.? ?oz|oz|g|mg|hours?|days?|weeks?|spf)?\b", re.I)
SENT = re.compile(r"(?<=[.!?])\s+")

# key: (label, points, fix)
CHECKS: dict[str, tuple[str, int, str]] = {
    "title_h1": ("Clear title and one H1", 8, "Give the page a descriptive <title> and exactly one H1 naming the product."),
    "answer_first": ("Answer-first summary", 14, "Open with a 20-80 word paragraph that directly answers what the product is and who it's for."),
    "question_headings": ("Question-style headings", 12, "Add H2/H3s phrased as the questions shoppers ask (e.g. “Is it safe for eczema?”) with a direct answer under each."),
    "faq_schema": ("FAQ structured data", 10, "Mark up the question-and-answer section with schema.org FAQPage JSON-LD."),
    "product_schema": ("Product structured data", 8, "Add schema.org Product JSON-LD with name, brand, GTIN, image and offers."),
    "short_paragraphs": ("Short paragraphs", 8, "Split long paragraphs: keep them under about 80 words, one idea each."),
    "lists_tables": ("Lists or tables", 8, "Put key benefits, ingredients and how-to-use steps in bullet lists or a table."),
    "specific_facts": ("Specific facts", 8, "State concrete facts: full ingredient list, sizes, concentrations, test results."),
    "readability": ("Readable sentences", 8, "Shorten sentences to about 20 words or fewer on average."),
    "expertise": ("Expertise signals", 6, "Show who stands behind the claims: dermatologist review, author, testing body."),
    "freshness": ("Dated", 5, "Show a last-updated date (visible and in dateModified)."),
    "depth": ("Enough depth", 5, "Cover the product in at least ~300 words: what it is, who it's for, how to use it, what's in it."),
}


def _paragraphs(soup: BeautifulSoup) -> list[str]:
    return [p.get_text(" ", strip=True) for p in soup.find_all("p") if p.get_text(strip=True)]


def grade_html(html: str, headers: dict[str, str] | None = None) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        if tag.name != "script" or tag.get("type") != "application/ld+json":
            tag.decompose()
    blocks, _ = jsonld_blocks(soup)
    types = set()
    for b in blocks:
        t = b.get("@type")
        types.update(t if isinstance(t, list) else [t])
    text = soup.get_text(" ", strip=True)
    words = len(text.split())
    paras = _paragraphs(soup)
    para_words = [len(p.split()) for p in paras]
    headings = [h.get_text(" ", strip=True) for h in soup.find_all(["h2", "h3"])]
    h1s = soup.find_all("h1")
    first = next((p for p in paras if len(p.split()) >= 12), "")
    sentences = [s for s in SENT.split(" ".join(paras)) if s.split()]
    avg_sentence = sum(len(s.split()) for s in sentences) / len(sentences) if sentences else 0
    list_items = sum(len(lst.find_all("li")) for lst in soup.find_all(["ul", "ol"])) + len(soup.find_all("tr"))
    has_ingredients = any("ingredient" in h.lower() for h in headings)
    authorish = bool(soup.find("meta", attrs={"name": "author"})) or bool(EXPERTISE.search(text))
    fresh = freshness(soup, headers or {}, None)

    results = {
        "title_h1": (bool(soup.title and soup.title.get_text(strip=True)) and len(h1s) == 1, f"{len(h1s)} H1" + ("" if soup.title else ", no title")),
        "answer_first": (20 <= len(first.split()) <= 80, f"First paragraph: {len(first.split())} words" if first else "No opening paragraph"),
        "question_headings": (sum(1 for h in headings if QUESTION.search(h)) >= 2, f"{sum(1 for h in headings if QUESTION.search(h))} of {len(headings)} headings are questions"),
        "faq_schema": (bool({"FAQPage", "QAPage"} & types), "FAQPage found" if {"FAQPage", "QAPage"} & types else "No FAQPage JSON-LD"),
        "product_schema": ("Product" in types, "Product found" if "Product" in types else "No Product JSON-LD"),
        "short_paragraphs": (bool(para_words) and sum(para_words) / len(para_words) <= 80 and max(para_words) <= 150, f"Average {round(sum(para_words) / len(para_words)) if para_words else 0} words, longest {max(para_words, default=0)}"),
        "lists_tables": (list_items >= 3, f"{list_items} list items or table rows"),
        "specific_facts": (has_ingredients or len(NUMBER.findall(text)) >= 3, "Ingredient list present" if has_ingredients else f"{len(NUMBER.findall(text))} figures"),
        "readability": (0 < avg_sentence <= 22, f"Average sentence {round(avg_sentence)} words"),
        "expertise": (authorish, "Expert or author named" if authorish else "No reviewer, author or expert named"),
        "freshness": (bool(fresh.get("newest")), f"Dated {fresh['newest'][:10]}" if fresh.get("newest") else "No date found"),
        "depth": (words >= 300, f"{words} words"),
    }
    checks = []
    for key, (label, points, fix) in CHECKS.items():
        ok, detail = results[key]
        checks.append({"key": key, "label": label, "points": points, "passed": bool(ok), "detail": detail, "fix": None if ok else fix})
    return {
        "title": soup.title.get_text(strip=True) if soup.title else (h1s[0].get_text(strip=True) if h1s else None),
        "score": sum(c["points"] for c in checks if c["passed"]),
        "checks": checks,
    }


def grade_url(session: Session, url: str, *, brand_id: int | None = None, sku_id: int | None = None, transport: httpx.BaseTransport | None = None) -> AnswerGrade:
    org = session.scalars(select(Organisation)).first()
    g = AnswerGrade(organisation_id=org.id, url=url, brand_id=brand_id, sku_id=sku_id, status="ok")
    fetcher = PoliteFetcher(transport=transport, sleep=lambda _s: None)
    session.commit()  # hand the DB connection back while we wait on the network
    try:
        robots = fetcher.robots(url)
        parts = urlsplit(url)
        if f"{parts.scheme}://{parts.netloc}" in fetcher.refused:
            g.status, g.note = "blocked", "The site refused our request for robots.txt (it blocks automated visitors), so the page was not fetched."
        elif robots is not None and not robots.can_fetch(USER_AGENT, url):
            g.status, g.note = "blocked", "robots.txt asks crawlers like ours not to fetch this page, so it was not graded."
        else:
            res = fetcher.get(url)
            g.http_status = res.status_code
            if res.status_code >= 400:
                g.status = "blocked" if res.status_code in (401, 403, 429) else "error"
                g.note = f"The site answered HTTP {res.status_code}"
            else:
                out = grade_html(res.text, {k.lower(): v for k, v in res.headers.items()})
                g.title, g.score, g.checks = out["title"], out["score"], out["checks"]
    except httpx.HTTPError as e:
        g.status, g.note = "error", f"Could not fetch the page: {type(e).__name__}"
    finally:
        fetcher.close()
    session.add(g)
    session.commit()
    return g


# Demo: bundled pages, graded locally (no network). URL -> (fixture, brand).
DEMO_PAGES = {
    "https://www.cerave.com/skincare/cleansers/hydrating-facial-cleanser": ("demo_pages/cerave_hydrating_cleanser.html", "CeraVe"),
    "https://www.aveeno.com/products/calm-restore-nourishing-oat-cleanser": ("demo_pages/aveeno_oat_cleanser.html", "Aveeno"),
    "https://www.riteaid.com/shop/cerave-hydrating-facial-cleanser": ("riteaid_cerave_hydrating_cleanser.html", "CeraVe"),
    "https://www.hannaford.com/product/aveeno-calm-restore-nourishing-oat-cleanser": ("hannaford_aveeno_oat_cleanser.html", "Aveeno"),
    "https://www.kenvuepro.com/aveeno/calm-restore-nourishing-oat-cleanser": ("kenvuepro_aveeno_oat_cleanser.html", "Aveeno"),
}


def generate_demo_grades(session: Session) -> int:
    """Replace demo grades only; real grades are never touched."""
    session.execute(delete(AnswerGrade).where(AnswerGrade.is_demo.is_(True)))
    org = session.scalars(select(Organisation)).first()
    if org is None:
        return 0
    brands = {b.name: b for b in session.scalars(select(Brand))}
    skus = {s.brand_id: s for s in session.scalars(select(Sku))}
    n = 0
    for url, (fixture, brand_name) in DEMO_PAGES.items():
        path = Path(BACKEND_DIR / "fixtures" / fixture)
        if not path.exists():
            continue
        out = grade_html(path.read_text(encoding="utf-8"))
        brand = brands.get(brand_name)
        sku = skus.get(brand.id) if brand else None
        session.add(AnswerGrade(organisation_id=org.id, url=url, brand_id=brand.id if brand else None, sku_id=sku.id if sku else None,
                                status="ok", title=out["title"], score=out["score"], checks=out["checks"], is_demo=True))
        n += 1
    session.commit()
    return n


def latest_grades(session: Session) -> list[dict[str, Any]]:
    """Newest grade per URL; a URL with any real grade shows only real grades."""
    rows = session.scalars(select(AnswerGrade).order_by(AnswerGrade.graded_at.desc(), AnswerGrade.id.desc())).all()
    real_urls = {g.url for g in rows if not g.is_demo}
    brands = {b.id: b.name for b in session.scalars(select(Brand))}
    out, seen = [], set()
    for g in rows:
        if g.url in seen or (g.is_demo and g.url in real_urls):
            continue
        seen.add(g.url)
        out.append({"id": g.id, "url": g.url, "brand_name": brands.get(g.brand_id), "sku_id": g.sku_id, "graded_at": g.graded_at, "status": g.status,
                    "http_status": g.http_status, "note": g.note, "title": g.title, "score": g.score, "checks": g.checks, "is_demo": g.is_demo})
    out.sort(key=lambda r: (r["score"] is None, -(r["score"] or 0)))
    return out
