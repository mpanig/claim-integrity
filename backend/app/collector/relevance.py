"""Is a candidate page about the target product?

GTIN exact match wins. Otherwise a token score: the brand must appear, then the share
of the product's distinctive words that appear in the title, URL and snippet.

  >= RELEVANT        relevant
  >= BORDERLINE      borderline -> Claude decides if available, else needs review
  below              rejected
"""

import re
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit

from app.collector.base import BrandInfo, Candidate, SkuInfo

RELEVANT = 0.8
BORDERLINE = 0.5
STOPWORDS = {"the", "and", "for", "with", "a", "an", "of", "by", "in", "on", "to", "oz", "ml", "fl", "pack", "count"}


@dataclass
class Relevance:
    score: float
    status: str  # relevant | borderline | rejected
    reason: str


def tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", unquote(text).lower())
    out = set()
    for w in words:
        if w in STOPWORDS or len(w) < 2:
            continue
        out.add(w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith("ss") else w)
    return out


def _haystack(c: Candidate) -> set[str]:
    path = urlsplit(c.url)
    return tokens(f"{c.title} {path.netloc} {path.path} {c.snippet}")


def score_candidate(c: Candidate, brand: BrandInfo, sku: SkuInfo | None) -> Relevance:
    gtin = (c.gtin or "").lstrip("0")
    if sku and sku.gtin and gtin and gtin == sku.gtin.lstrip("0"):
        return Relevance(1.0, "relevant", "GTIN matches exactly")
    if sku and sku.gtin and gtin and gtin != sku.gtin.lstrip("0"):
        return Relevance(0.0, "rejected", f"different GTIN ({c.gtin})")

    hay = _haystack(c)
    brand_tokens = tokens(brand.name)
    if not brand_tokens <= hay and not (brand.site_url and urlsplit(brand.site_url).hostname in c.url):
        return Relevance(0.1, "rejected", f"does not mention {brand.name}")
    if sku is None:  # brand-level mention
        return Relevance(1.0, "relevant", f"mentions {brand.name}")

    product = tokens(sku.name) - brand_tokens
    if not product:
        return Relevance(0.9, "relevant", "brand matches")
    found = product & hay
    score = round(0.3 + 0.7 * len(found) / len(product), 2)
    missing = sorted(product - found)
    reason = f"matches {len(found)} of {len(product)} product words" + (f"; missing {', '.join(missing)}" if missing else "")
    if score >= RELEVANT:
        return Relevance(score, "relevant", reason)
    if score >= BORDERLINE:
        return Relevance(score, "borderline", reason)
    return Relevance(score, "rejected", reason)
