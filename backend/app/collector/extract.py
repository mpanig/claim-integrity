"""Deterministic extraction: schema.org Product data, then text rules.

Every value carries the exact text it came from (the quote). Text rules are
deliberately narrow; anything they miss is left out rather than guessed, and the
extraction is marked partial so missing fields are not reported as page issues.
"""

import json
import re
from typing import Any

from bs4 import BeautifulSoup

from app.collector.base import Parsed
from app.collector.http import Fetched
from app.pipeline.compare import free_from_key

MAX_TEXT = 200_000

FREE_FROM_PATTERNS = [
    re.compile(
        r"\b((?:fragrance|paraben|sulfate|sulphate|phthalate|dye|alcohol|oil|soap|silicone|gluten|mineral oil)s?[- ]free)\b",
        re.I,
    ),
    re.compile(r"\b(free (?:of|from) (?:added )?(?:fragrances?|parabens?|sulfates?|dyes?|alcohol|oils?|soap))\b", re.I),
]
CLAIM_PATTERNS = [
    re.compile(p, re.I)
    for p in (
        r"\bnon[- ]comedogenic\b",
        r"\bhypoallergenic\b",
        r"\bdermatologist[- ](?:tested|recommended|developed)\b",
        r"\ballergy[- ]tested\b",
        r"\btested on sensitive skin\b",
        r"\bclinically (?:proven|tested|shown)\b",
        r"\bophthalmologist[- ]tested\b",
        r"\bsoap[- ]free\b",
    )
]
SEAL_PATTERNS = [
    (re.compile(r"\bNational Eczema Association\b|\bNEA Seal\b", re.I), "NEA Seal of Acceptance"),
    (re.compile(r"\bLeaping Bunny\b", re.I), "Leaping Bunny"),
    (re.compile(r"\bEWG Verified\b", re.I), "EWG Verified"),
]
INCI = re.compile(
    r"\bingredients?\b\s*[:\-–]?\s*((?:[A-Za-z0-9(][^,\n:]{1,90},\s*){4,}[^,\n.:]{1,90})",
    re.I,
)


def sentence_around(text: str, start: int, end: int, width: int = 160) -> str:
    left = max(text.rfind(".", 0, start), text.rfind("\n", 0, start))
    right_candidates = [i for i in (text.find(".", end), text.find("\n", end)) if i != -1]
    right = min(right_candidates) if right_candidates else len(text)
    left = max(left + 1, start - width)
    right = min(right + 1, end + width)
    return " ".join(text[left:right].split())


def jsonld_products(soup: BeautifulSoup) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, list):
            for n in node:
                walk(n)
        elif isinstance(node, dict):
            t = node.get("@type")
            types = t if isinstance(t, list) else [t]
            if any(str(x).lower() in ("product", "productgroup") for x in types):
                found.append(node)
            for key in ("@graph", "mainEntity", "itemListElement", "item"):
                if key in node:
                    walk(node[key])

    for tag in soup.find_all("script", attrs={"type": re.compile("ld\\+json", re.I)}):
        try:
            walk(json.loads(tag.string or "", strict=False))
        except (json.JSONDecodeError, TypeError):
            continue
    return found


def microdata_product(soup: BeautifulSoup) -> dict[str, Any] | None:
    scope = soup.find(attrs={"itemtype": re.compile(r"schema\.org/Product", re.I)})
    if scope is None:
        return None
    out: dict[str, Any] = {}
    for prop in ("name", "gtin13", "gtin12", "gtin14", "gtin8", "gtin", "description"):
        el = scope.find(attrs={"itemprop": prop})
        if el is not None:
            out[prop] = el.get("content") or el.get_text(" ", strip=True)
    return out or None


def visible_text(soup: BeautifulSoup) -> str:
    for tag in soup(["script", "style", "noscript", "nav", "header", "footer", "form", "svg"]):
        tag.decompose()
    root = soup.find("main") or soup.body or soup
    lines = [" ".join(line.split()) for line in root.get_text("\n").splitlines()]
    return "\n".join(line for line in lines if line)[:MAX_TEXT]


def _gtin(product: dict[str, Any]) -> str | None:
    for key in ("gtin13", "gtin12", "gtin14", "gtin8", "gtin"):
        v = product.get(key)
        if v and re.fullmatch(r"\d{8,14}", str(v).strip()):
            return str(v).strip()
    return None


def rules_from_text(text: str) -> dict[str, dict[str, Any]]:
    fields: dict[str, dict[str, Any]] = {}

    m = INCI.search(text)
    if m:
        items = [i.strip(" .;*") for i in m.group(1).split(",")]
        items = [i for i in items if 1 < len(i) <= 90]
        if len(items) >= 5:
            fields["ingredients"] = {"value": items, "quote": " ".join(m.group(0).split())[:2000]}

    free: dict[str, tuple[str, str]] = {}
    for pattern in FREE_FROM_PATTERNS:
        for fm in pattern.finditer(text):
            phrase = " ".join(fm.group(1).split()).title()
            free.setdefault(free_from_key(phrase), (phrase, sentence_around(text, fm.start(), fm.end())))
    if free:
        fields["free_from"] = {
            "value": [v for v, _ in free.values()],
            "quote": " | ".join(q for _, q in free.values())[:2000],
        }

    claims: dict[str, tuple[str, str]] = {}
    for pattern in CLAIM_PATTERNS:
        cm = pattern.search(text)
        if cm:
            phrase = " ".join(cm.group(0).split())
            phrase = phrase[0].upper() + phrase[1:]
            claims.setdefault(phrase.lower(), (phrase, sentence_around(text, cm.start(), cm.end())))
    if claims:
        fields["claims"] = {
            "value": [v for v, _ in claims.values()],
            "quote": " | ".join(q for _, q in claims.values())[:2000],
        }

    seals = []
    seal_quotes = []
    for pattern, seal in SEAL_PATTERNS:
        sm = pattern.search(text)
        if sm:
            seals.append(seal)
            seal_quotes.append(sentence_around(text, sm.start(), sm.end()))
    if seals:
        fields["seals"] = {"value": seals, "quote": " | ".join(seal_quotes)[:2000]}
    return fields


def extract_page(fetched: Fetched) -> Parsed:
    """Fields from a fetched HTML page or Reader text."""
    parsed = Parsed()
    methods = []
    if "html" in fetched.content_type or fetched.text.lstrip()[:15].lower().startswith(("<!doctype", "<html")):
        soup = BeautifulSoup(fetched.text, "html.parser")
        products = jsonld_products(soup)
        product = products[0] if products else microdata_product(soup)
        if product:
            methods.append("jsonld" if products else "microdata")
            name = product.get("name")
            if isinstance(name, str) and name.strip():
                parsed.name = " ".join(name.split())
                parsed.fields["name"] = {"value": parsed.name, "quote": f"Product data on the page: name = {parsed.name}"}
            parsed.gtin = _gtin(product)
        text = visible_text(soup)
        if product and isinstance(product.get("description"), str):
            text = f"{product['description']}\n{text}"
    else:
        text = fetched.text[:MAX_TEXT]
    rules = rules_from_text(text)
    if rules:
        methods.append("text_rules")
    parsed.fields.update(rules)
    parsed.method = "+".join(methods)
    return parsed
