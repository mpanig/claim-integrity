"""Shared helpers: polite HTTP session, robots.txt checks, raw storage, HTML extraction."""
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.robotparser
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

COLLECTOR_VERSION = "dc-0.1"
UA = "claim-integrity-research-collector/0.1 (non-commercial product-claim research)"
ROOT = Path(__file__).resolve().parent
RAW = ROOT / "raw"
RAW.mkdir(exist_ok=True)

_last: dict[str, float] = {}
_robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
S = requests.Session()
S.headers.update({"User-Agent": UA, "Accept-Language": "en;q=0.9,*;q=0.5"})


def polite_get(url: str, min_interval: float = 1.1, **kw) -> requests.Response:
    host = urlparse(url).netloc
    wait = _last.get(host, 0) + min_interval - time.time()
    if wait > 0:
        time.sleep(wait)
    kw.setdefault("timeout", 40)
    for attempt in range(4):
        try:
            r = S.get(url, **kw)
        except requests.RequestException as e:
            _last[host] = time.time()
            if attempt == 3:
                raise
            time.sleep(3 * (attempt + 1))
            continue
        _last[host] = time.time()
        if r.status_code in (429, 503) and attempt < 3:
            time.sleep(10 * (attempt + 1))
            continue
        if "charset" not in r.headers.get("content-type", "").lower():
            r.encoding = "utf-8"  # requests would otherwise assume ISO-8859-1 for text/*
        return r
    return r


def robots_for(base: str):
    if base in _robots:
        return _robots[base]
    rp = urllib.robotparser.RobotFileParser()
    try:
        r = polite_get(base + "/robots.txt")
        save_raw(f"robots/{urlparse(base).netloc}.txt", r.text if r.ok else f"HTTP {r.status_code}")
        if r.status_code >= 400 and r.status_code < 500:
            rp.parse([])  # no robots = allowed
        elif not r.ok:
            rp = None
        else:
            rp.parse(r.text.splitlines())
    except requests.RequestException:
        rp = None
    _robots[base] = rp
    return rp


def allowed(url: str) -> bool:
    p = urlparse(url)
    rp = robots_for(f"{p.scheme}://{p.netloc}")
    return bool(rp and rp.can_fetch(UA, url))


def save_raw(rel: str, content: str | bytes) -> Path:
    path = RAW / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(content, str):
        path.write_text(content, encoding="utf-8")
    else:
        path.write_bytes(content)
    return path


def slug(url: str) -> str:
    return hashlib.sha1(url.encode()).hexdigest()[:16]


def fix_mojibake(s: str) -> str:
    """Undo UTF-8 bytes that were decoded as Latin-1 (e.g. 'Â®' -> '®')."""
    if "Â" in s or "Ã" in s or "â€" in s:
        try:
            return s.encode("latin-1").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return s
    return s


def clean(t: str | None) -> str:
    if not t:
        return ""
    return re.sub(r"\s+", " ", t).strip()


def _jsonld_products(soup):
    out = []
    for s in soup.find_all("script", type=lambda v: v and "ld+json" in v):
        try:
            data = json.loads(s.string or s.get_text() or "")
        except Exception:
            continue
        stack = [data]
        while stack:
            d = stack.pop()
            if isinstance(d, list):
                stack.extend(d)
            elif isinstance(d, dict):
                t = d.get("@type")
                types = t if isinstance(t, list) else [t]
                if "Product" in types or "ProductGroup" in types:
                    out.append(d)
                for k in ("@graph", "mainEntity", "itemListElement", "hasVariant"):
                    if k in d:
                        stack.append(d[k])
    return out


def _gtin(p: dict) -> str:
    for k in ("gtin13", "gtin12", "gtin14", "gtin8", "gtin"):
        v = p.get(k)
        if v:
            v = re.sub(r"\D", "", str(v))
            if 8 <= len(v) <= 14:
                return v
    return ""


BULLET_SELECTORS = [
    "main [class*='rich-text'] li", "[class*='rich-text'] li",  # Kenvue brand sites (PDP overview bullets)
    "#feature-bullets li",  # amazon
    "[data-testid='product-highlights'] li", "[data-test='item-details-highlights'] li",  # target
    "#product-details li", ".product-details li", ".product-description li", ".pdp-description li",
    ".product-benefits li", ".benefits li", ".product-features li", ".key-benefits li",
    "[class*='benefit'] li", "[class*='Benefit'] li", "[class*='feature'] li", "[class*='highlight'] li",
    "[itemprop='description'] li", ".about-product li",
]


def extract_page(html: str) -> dict:
    """Title, meta/og/JSON-LD description, bullet claims, ingredients, gtin, name from an HTML page."""
    soup = BeautifulSoup(html, "lxml")
    title = clean(soup.title.get_text()) if soup.title else ""
    meta = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
    og = soup.find("meta", attrs={"property": "og:description"})
    ogt = soup.find("meta", attrs={"property": "og:title"})
    meta_d = clean(meta.get("content")) if meta else ""
    og_d = clean(og.get("content")) if og else ""
    prods = _jsonld_products(soup)
    ld_desc, name, gtin = "", "", ""
    for p in prods:
        if not ld_desc and p.get("description"):
            ld_desc = clean(BeautifulSoup(str(p["description"]), "lxml").get_text(" "))
        if not name and p.get("name"):
            name = clean(str(p["name"]))
        if not gtin:
            gtin = _gtin(p)
    if not name:
        h1 = soup.find("h1")
        name = clean(h1.get_text(" ")) if h1 else clean(ogt.get("content")) if ogt else title
    bullets: list[str] = []
    for sel in BULLET_SELECTORS:
        try:
            for li in soup.select(sel):
                t = clean(li.get_text(" "))
                if 3 < len(t) < 400 and t not in bullets:
                    bullets.append(t)
        except Exception:
            continue
        if len(bullets) > 40:
            break
    ingredients = ""
    for el in soup.find_all(string=re.compile(r"^\s*(Active |Inactive )?Ingredients\s*:?\s*$", re.I)):
        parent = el.find_parent()
        nxt = parent.find_next(string=lambda s: s and len(clean(s)) > 20) if parent else None
        if nxt:
            ingredients = clean(nxt)[:3000]
            break
    if not ingredients:
        m = re.search(r"Ingredients\s*:\s*([A-Z][^<]{20,2000}?)(?:\.|<)", html)
        if m:
            ingredients = clean(m.group(1))
    description = ld_desc or og_d or meta_d
    return {
        "title": title, "name": name, "gtin": gtin, "meta_description": meta_d, "og_description": og_d,
        "jsonld_description": ld_desc, "description": description, "claims": bullets[:40],
        "ingredients": ingredients,
    }
