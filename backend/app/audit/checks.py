"""Page checks: schema.org structured data, AI crawlability, freshness.

All three read one fetched page (plus its site's robots.txt) and return plain dicts with a
score and plain-language issues.
"""

import json
import re
import urllib.robotparser
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

from bs4 import BeautifulSoup

from app.pipeline.compare import normalise_ingredient

# ----------------------------------------------------------------------------- structured data

REQUIRED = ("name",)
RECOMMENDED = ("image", "description", "brand", "offers", "gtin", "aggregateRating")
GTIN_KEYS = ("gtin", "gtin8", "gtin12", "gtin13", "gtin14")


def jsonld_blocks(soup: BeautifulSoup) -> tuple[list[dict[str, Any]], int]:
    """All JSON-LD objects on the page, flattened; and how many blocks failed to parse."""
    objs: list[dict[str, Any]] = []
    broken = 0

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for n in node:
                walk(n)
        elif isinstance(node, dict):
            objs.append(node)
            for key in ("@graph", "mainEntity", "itemListElement", "item", "hasVariant"):
                if key in node:
                    walk(node[key])

    for tag in soup.find_all("script", attrs={"type": re.compile("ld\\+json", re.I)}):
        try:
            walk(json.loads(tag.string or "", strict=False))
        except (json.JSONDecodeError, TypeError):
            broken += 1
    return objs, broken


def _types(obj: dict[str, Any]) -> list[str]:
    t = obj.get("@type")
    return [str(x) for x in (t if isinstance(t, list) else [t]) if x]


def gtin_valid(code: str) -> bool:
    """GS1 check digit."""
    if not re.fullmatch(r"\d{8}|\d{12}|\d{13}|\d{14}", code):
        return False
    digits = [int(d) for d in code]
    body, check = digits[:-1], digits[-1]
    total = sum(d * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(body)))
    return (10 - total % 10) % 10 == check


def structured_data(soup: BeautifulSoup) -> dict[str, Any]:
    objs, broken = jsonld_blocks(soup)
    products = [o for o in objs if any(t.lower() in ("product", "productgroup") for t in _types(o))]
    microdata = soup.find(attrs={"itemtype": re.compile(r"schema\.org/Product", re.I)}) is not None
    issues: list[str] = []
    if broken:
        issues.append(f"{broken} JSON-LD block(s) are not valid JSON, so search and AI tools ignore them.")
    if not products:
        if microdata:
            issues.append("Product data is only in microdata; JSON-LD is easier for search engines and AI tools to read.")
        else:
            issues.append("No schema.org Product data. AI assistants and search engines can't read the product's facts reliably.")
        return {"found": bool(microdata), "format": "microdata" if microdata else None, "types": sorted({t for o in objs for t in _types(o)}), "present": [], "missing": list(REQUIRED + RECOMMENDED), "score": 0, "issues": issues}

    p = products[0]
    present, missing = [], []
    for key in REQUIRED + RECOMMENDED:
        has = any(p.get(k) for k in GTIN_KEYS) if key == "gtin" else bool(p.get(key))
        (present if has else missing).append(key)
    for key in REQUIRED:
        if key in missing:
            issues.append(f"Required property “{key}” is missing.")
    labels = {"image": "an image", "description": "a description", "brand": "the brand", "offers": "price and availability (offers)", "gtin": "a GTIN barcode", "aggregateRating": "ratings"}
    for key in RECOMMENDED:
        if key in missing:
            issues.append(f"Add {labels[key]} to the product data.")
    for k in GTIN_KEYS:
        v = p.get(k)
        if v and not gtin_valid(str(v).strip()):
            issues.append(f"{k} “{v}” is not a valid GTIN (check digit fails).")
    offers = p.get("offers")
    offer = offers[0] if isinstance(offers, list) and offers else offers
    if isinstance(offer, dict) and offer and not (offer.get("price") or offer.get("lowPrice")):
        issues.append("Offers have no price.")
    total = len(REQUIRED) + len(RECOMMENDED)
    return {
        "found": True,
        "format": "json-ld",
        "types": sorted({t for o in objs for t in _types(o)}),
        "name": p.get("name"),
        "present": present,
        "missing": missing,
        "score": round(100 * len(present) / total),
        "issues": issues,
    }


# ----------------------------------------------------------------------------- AI crawlability

AI_BOTS = {
    "GPTBot": "OpenAI model training",
    "OAI-SearchBot": "ChatGPT search results",
    "ChatGPT-User": "ChatGPT fetching a page for a user",
    "ClaudeBot": "Anthropic model training",
    "Claude-SearchBot": "Claude search results",
    "Claude-User": "Claude fetching a page for a user",
    "PerplexityBot": "Perplexity search index",
    "Perplexity-User": "Perplexity fetching a page for a user",
    "Google-Extended": "Gemini use of Google-crawled content",
    "Googlebot": "Google Search (and AI Overviews)",
    "Bingbot": "Bing and Copilot",
    "CCBot": "Common Crawl (used to train many models)",
}


def crawlability(robots: urllib.robotparser.RobotFileParser | None, url: str, soup: BeautifulSoup | None, headers: dict[str, str], html: str) -> dict[str, Any]:
    bots = []
    for bot, purpose in AI_BOTS.items():
        allowed = True if robots is None else robots.can_fetch(bot, url)
        bots.append({"bot": bot, "purpose": purpose, "allowed": allowed})
    issues: list[str] = []
    blocked = [b["bot"] for b in bots if not b["allowed"]]
    if robots is None:
        issues.append("No robots.txt found: every crawler is allowed by default.")
    if blocked:
        issues.append(f"robots.txt blocks {', '.join(blocked)} from this page. Those AI tools can't read it directly.")

    meta = ""
    if soup is not None:
        tags = soup.find_all("meta", attrs={"name": re.compile(r"^(robots|googlebot|gptbot|claudebot)$", re.I)})
        meta = " ".join((t.get("content") or "").lower() for t in tags)
    header = (headers.get("x-robots-tag") or "").lower()
    noindex = "noindex" in meta or "noindex" in header
    noai = any(x in meta + " " + header for x in ("noai", "noimageai"))
    if noindex:
        issues.append("The page asks not to be indexed (noindex), so search-based AI answers won't use it.")
    if noai:
        issues.append("The page carries a 'noai' directive.")

    text_len = 0
    if soup is not None:
        for t in soup(["script", "style", "noscript"]):
            t.decompose()
        text_len = len(" ".join(soup.get_text(" ").split()))
    js_heavy = bool(html) and text_len < 500 and len(html) > 20_000
    if js_heavy:
        issues.append("Very little text without JavaScript. Many AI crawlers don't run JavaScript and may see an empty page.")
    allowed = sum(1 for b in bots if b["allowed"])
    score = round(100 * allowed / len(bots)) - (30 if noindex else 0) - (20 if js_heavy else 0)
    return {"bots": bots, "noindex": noindex, "noai": noai, "text_chars": text_len, "js_heavy": js_heavy, "score": max(0, score), "issues": issues}


# ----------------------------------------------------------------------------- freshness

STALE_DAYS = 365


def _parse_date(value: str) -> datetime | None:
    value = value.strip()
    for fn in (
        lambda v: datetime.fromisoformat(v.replace("Z", "+00:00")),
        lambda v: parsedate_to_datetime(v),
        lambda v: datetime.strptime(v[:10], "%Y-%m-%d"),
    ):
        try:
            d = fn(value)
            return d if d.tzinfo else d.replace(tzinfo=UTC)
        except (ValueError, TypeError, IndexError):
            continue
    return None


def freshness(soup: BeautifulSoup | None, headers: dict[str, str], truth: dict[str, Any] | None, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(UTC)
    dates: dict[str, str] = {}
    if soup is not None:
        objs, _ = jsonld_blocks(soup)
        for o in objs:
            for key in ("dateModified", "datePublished"):
                if isinstance(o.get(key), str):
                    dates.setdefault(f"json-ld {key}", o[key])
        for prop in ("article:modified_time", "og:updated_time", "article:published_time"):
            tag = soup.find("meta", attrs={"property": prop})
            if tag and tag.get("content"):
                dates.setdefault(f"meta {prop}", tag["content"])
    if headers.get("last-modified"):
        dates["Last-Modified header"] = headers["last-modified"]
    parsed = {k: d for k, v in dates.items() if (d := _parse_date(v))}
    newest = max(parsed.values()) if parsed else None
    age = (now - newest).days if newest else None
    issues: list[str] = []
    if newest is None:
        issues.append("No date on the page. AI tools can't tell how current it is; add dateModified to the product data.")
    elif age is not None and age > STALE_DAYS:
        issues.append(f"Last updated {age} days ago. Stale pages are less likely to be trusted or cited.")

    facts: dict[str, Any] = {}
    if truth and truth.get("ingredients") and soup is not None:
        text = normalise_ingredient(" ".join(soup.get_text(" ").split()))
        wanted = [normalise_ingredient(i) for i in truth["ingredients"]]
        found = [w for w in wanted if w.split("/")[0] in text]
        share = round(len(found) / len(wanted), 2)
        missing = [truth["ingredients"][i] for i, w in enumerate(wanted) if w not in found]
        facts = {"ingredients_on_page": share, "missing_ingredients": missing[:10]}
        if share < 0.6:
            issues.append(f"Only {round(share * 100)}% of the approved ingredient list appears on the page. It may show an older formula, or load ingredients with JavaScript.")
    return {
        "dates": {k: v.isoformat() for k, v in parsed.items()},
        "newest": newest.isoformat() if newest else None,
        "age_days": age,
        "stale": newest is None or (age is not None and age > STALE_DAYS),
        "facts": facts,
        "issues": issues,
    }
