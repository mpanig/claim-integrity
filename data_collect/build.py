"""Build the flat CSV, product matching, unmatched CSV and per-table CSVs (organisation, brand, sku, variant,
page, snapshot, extraction) matching the claim_integrity Postgres schema (alembic 0017), plus load_order.sql.

Canonical products (sku rows) come from brand sites and Open Facts. Every other row must match one of them:
  1. GTIN/UPC/EAN exact (zero-padded to 14)                       match_method=gtin, confidence 1.0
  2. normalised name (+ size) fuzzy, same brand, score >= 0.80     match_method=fuzzy_name, confidence=score
Rows below the threshold go to unmatched_rows.csv and are not in the load files.

usage: build.py OUT_DIR [existing_page_urls.txt]
"""
import csv
import gzip
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path

from bs4 import BeautifulSoup, Comment

from claims import extract_claims
from common import COLLECTOR_VERSION, fix_mojibake

csv.field_size_limit(10**9)
OUT = Path(sys.argv[1])
OUT.mkdir(parents=True, exist_ok=True)
EXISTING = set(Path(sys.argv[2]).read_text().split()) if len(sys.argv) > 2 else set()
import os
SRC = os.environ.get("SOURCES", "brand_sites,open_facts,common_crawl,wikidata").split(",")
ID0 = 100000  # well above existing ids (max ~50) so nothing collides
# Stable ids across builds and chunks: natural key -> id, persisted in a registry file (committed with the data).
REG_P = Path(sys.argv[3]) if len(sys.argv) > 3 else OUT / "id_registry.json"
REG = json.loads(REG_P.read_text()) if REG_P.exists() else {}
for _k in ("organisation", "brand", "sku", "page", "variant", "snapshot", "inferred_truth", "_next"):
    REG.setdefault(_k, {})


def alloc(table, key):
    m = REG[table]
    if key not in m:
        m[key] = REG["_next"].get(table, ID0 + 1)
        REG["_next"][table] = m[key] + 1
    return m[key]


def row_key(r):
    return f"{r['url']}|{r['captured_at']}|{hashlib.sha1(r['description'].encode()).hexdigest()[:12]}"


ORG_ID = None  # set after the registry is loaded (below)
ORG_NAME = "Public data: Aveeno & Listerine"
ORG_ID = alloc("organisation", ORG_NAME)
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")
PART_TEXT_BYTES = 180 * 1024 * 1024  # ~180 MB text per gz part -> well under 50 MB gzipped
FUZZY_MIN = 0.80

DOMAIN_COUNTRY = {".com.au": "AU", ".co.uk": "GB", ".com.br": "BR", ".co.za": "ZA", ".co.nz": "NZ", ".ca": "CA",
                  ".in": "IN", ".de": "DE", ".it": "IT", ".es": "ES", ".fr": "FR", "boots.com": "GB", ".com": "US"}
OF_COUNTRY = {"united-states": "US", "france": "FR", "united-kingdom": "GB", "germany": "DE", "canada": "CA",
              "spain": "ES", "italy": "IT", "india": "IN", "australia": "AU", "belgium": "BE", "switzerland": "CH",
              "netherlands": "NL", "brazil": "BR", "mexico": "MX", "south-korea": "KR", "ireland": "IE"}
RETAILER = {"amazon.com": "Amazon US", "amazon.co.uk": "Amazon UK", "amazon.in": "Amazon India",
            "amazon.ca": "Amazon Canada", "walmart.com": "Walmart", "target.com": "Target", "cvs.com": "CVS",
            "walgreens.com": "Walgreens", "ulta.com": "Ulta", "boots.com": "Boots"}
PAGE_TYPE = {"brand_site": "brand", "common_crawl_retailer": "retailer", "open_facts": "open_facts",
             "wikidata": "wikidata"}
POSITIONING = {"Aveeno": ["natural", "gentle", "sensitive", "eczema", "hydrating"], "Listerine": []}


def country_of(r):
    if r["source_type"] == "open_facts":
        cs = r["locale"].split("-", 1)[1].split(",") if "-" in r["locale"] else []
        return OF_COUNTRY.get(cs[0]) if len(cs) == 1 else None
    if r["source_type"] == "wikidata":
        return None
    for suf, c in DOMAIN_COUNTRY.items():
        if r["source_domain"].endswith(suf):
            return c
    return None


def to_iso(v):
    if isinstance(v, (int, float)):
        return datetime.fromtimestamp(v, timezone.utc).isoformat(timespec="seconds")
    return v or NOW


# ---------- product name normalisation ----------
SIZE_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(fl\.?\s*oz|oz|ml|l|g|kg|lb|ct|count)\b", re.I)
NOISE = {"aveeno", "listerine", "amazon", "com", "in", "ca", "co", "uk", "walmart", "target", "cvs", "walgreens",
         "ulta", "boots", "beauty", "the", "and", "with", "for", "a", "of", "pack", "bottle", "tube", "oz", "fl",
         "ml", "count", "ct", "personal", "care", "health", "household", "baby", "product", "products", "buy",
         "online", "shop", "at", "best", "price", "prices", "india", "brand", "new", "us", "usa", "x", "by"}


def size_of(name):
    m = SIZE_RE.search(name or "")
    if not m:
        return None
    return f"{m.group(1).replace(',', '.')} {re.sub(r'[ .]', '', m.group(2).lower())}"


def tokens(name):
    n = (name or "").lower()
    n = re.sub(r"^amazon\.[a-z.]+\s*:\s*", "", n)
    n = n.split(" : ")[0].split(" | ")[0]
    n = SIZE_RE.sub(" ", n)
    n = n.replace("moisturising", "moisturizing").replace("moisturiser", "moisturizer").replace("colour", "color")
    n = n.replace("+", " plus ").replace("&", " and ")
    toks = [t for t in re.findall(r"[a-z0-9äöüßéèêàçñãõ]+", n) if t not in NOISE and not t.isdigit()]
    return toks


# Words that make a different product (or variant with different claims) when only one side has them.
DISTINGUISH = {
    # who / protection / variant
    "baby", "kids", "men", "spf", "sunscreen", "mild", "zero", "night", "cooling", "whitening", "scented",
    "lavender", "tinted", "tint",
    # pack
    "refill", "pouch", "kit", "set", "gift", "travel", "mini", "trial",
    # product form
    "gel", "cream", "lotion", "wash", "shampoo", "conditioner", "balm", "oil", "spray", "strips", "toothpaste",
    "floss", "mouthwash", "scrub", "mask", "serum", "cleanser", "stick",
    # Listerine lines / flavours
    "ultraclean", "nightly", "reset", "smart", "freshburst", "spearmint", "citrus", "gold", "vanilla", "clinical",
    # Aveeno lines
    "radiant", "positively", "absolutely", "ageless", "calm", "restore", "repair", "clear", "complexion",
    "stress", "therapy",
}


def score(a, b):
    """Anchor tokens a must all appear in row tokens b (retailer titles are longer); extra row words that
    name a different variant reject the match. Returns 0..1, higher = more of the row explained by the anchor."""
    if not a or not b:
        return 0.0
    sa, sb = set(a), set(b)
    if not sa <= sb or (sb - sa) & DISTINGUISH:
        return 0.0
    jac = len(sa & sb) / len(sa | sb)
    return round(0.8 + 0.2 * jac, 3)  # >= 0.8 for every valid subset match


INCI_HINT = re.compile(r"\b(aqua|water|eau|glycerin|alcohol|sorbitol|avena|oat|dimethicone|petrolatum|cetyl|stearyl|"
                       r"sodium|menthol|thymol|eucalyptol|fluoride|zinc|parfum|fragrance|citric|benzoate|poloxamer|"
                       r"paraben|phenoxyethanol|tocopherol|acid|extract|oxide|chloride|glycol|butter|wasser)\b", re.I)


def valid_ingredients(s):
    """Keep only text that looks like an INCI list: >=3 comma items, short items, known INCI words, no JSON."""
    s = (s or "").strip()
    if not s or "{" in s or "@type" in s:
        return ""
    s = re.sub(r"^\s*(\[[^\]]*\]\s*)?((in)?active )?ingredients?\s*:?\s*", "", s, flags=re.I)
    items = [x.strip() for x in re.split(r",(?![^()]*\))", s) if x.strip()]
    if len(items) < 3 or sum(len(x) for x in items) / len(items) > 45 or len(INCI_HINT.findall(s)) < 2:
        return ""
    return s


def gtin14(g):
    g = re.sub(r"\D", "", g or "")
    return g.zfill(14) if 8 <= len(g) <= 14 else ""


def strip_html(html):
    """Drop scripts (except JSON-LD), styles, svg, comments: keeps text, meta and structured data."""
    soup = BeautifulSoup(html, "lxml")
    for t in soup.find_all(["script", "style", "svg", "noscript", "iframe", "link"]):
        if t.name == "script" and "ld+json" in (t.get("type") or ""):
            continue
        t.decompose()
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()
    return re.sub(r"\n\s*\n+", "\n", str(soup))


def raw_html(r):
    p = r.get("raw_path")
    if not p:
        return json.dumps({k: r[k] for k in ("product_name", "description", "claims", "ingredients")} |
                          {"extra": r.get("extra", {})}, ensure_ascii=False)
    b = Path(p).read_bytes()
    if p.endswith(".gz"):
        b = gzip.decompress(b)
    return strip_html(b.decode("utf-8", "replace")).replace("\x00", "")


# ---------- load + clean + dedupe ----------
rows, seen, dropped = [], set(), Counter()
for s in SRC:
    f = Path("out") / f"{s}.jsonl"
    if not f.exists():
        continue
    for line in f.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        for k in ("product_name", "title", "description", "ingredients"):
            r[k] = fix_mojibake(r.get(k) or "").replace("\x00", "")
        r["claims"] = [fix_mojibake(c).replace("\x00", "") for c in r.get("claims") or []]
        r["captured_at"] = to_iso(r["captured_at"])
        dl = r["description"].lower()
        if r["source_type"] == "wikidata" and ("scholarly article" in dl or "scientific article" in dl):
            dropped["wikidata_scholarly_article"] += 1
            continue
        if r["source_type"] not in ("wikidata", "brand_site") and r["brand"].lower() not in (
                r["product_name"] + r["title"] + r["url"] + r.get("extra", {}).get("brands", "")).lower():
            dropped[f"{r['source_type']}_brand_not_named"] += 1
            continue
        key = (r["url"], r["captured_at"], r["description"])
        if key in seen:
            dropped["exact_duplicate_url_captured_desc"] += 1
            continue
        seen.add(key)
        if r["ingredients"] and not valid_ingredients(r["ingredients"]):
            dropped["ingredients_text_rejected_not_inci"] += 1
        r["ingredients"] = valid_ingredients(r["ingredients"])
        r["gtin"] = re.sub(r"\D", "", r.get("gtin") or "")
        r["size"] = size_of(r["product_name"] or r["title"])
        r["toks"] = tokens(r["product_name"] or r["title"])
        rows.append(r)

# ---------- canonical products ----------
skus = {}  # sid -> dict
by_gtin = {}
next_sid = ID0 + 1


def find(r):
    """Best canonical match: (sid, method, confidence)."""
    g = gtin14(r["gtin"])
    # some brand sites reuse one GTIN on several product pages: only trust it when names don't name different variants
    if g and g in by_gtin and not (set(skus[by_gtin[g]]["toks"]) ^ set(r["toks"])) & DISTINGUISH:
        return by_gtin[g], "gtin", 1.0
    best, bs, blen = None, 0.0, 0
    for sid, s in skus.items():
        if s["brand"] != r["brand"]:
            continue
        sc = score(s["toks"], r["toks"])
        n = len(set(s["toks"]))
        if sc and n >= 2 and (n > blen or (n == blen and sc > bs)):  # most specific anchor wins
            best, bs, blen = sid, sc, n
    return best, "fuzzy_name", bs


def new_sku(r):
    sid = alloc("sku", f"{r['source_type']}|{r['url']}")
    skus[sid] = {"brand": r["brand"], "name": (r["product_name"] or r["title"])[:300], "toks": r["toks"],
                 "gtin": r["gtin"] or None,
                 "aliases": [], "sizes": set(), "sources": Counter(), "domains": set()}
    if r["gtin"]:
        by_gtin.setdefault(gtin14(r["gtin"]), sid)
    return sid


# brand-site pages that are not single products (category/collection/overview pages) are not anchors
NOT_PRODUCT = re.compile(r"/(products?|produkte|produits|productos|prodotti|produtos)/?$|/(all|alle|tous|todos|tutti)[-/]|"
                         r"/(by-|collection|range|line|category|kategorie)", re.I)
matches = []  # (row, sid|None, method, conf)
anchor_rows = [r for r in rows if r["source_type"] in ("brand_site", "open_facts")]
for r in anchor_rows:
    generic = r["source_type"] == "brand_site" and not r["gtin"] and not r["ingredients"] and len(set(r["toks"])) < 3
    cat_url = (r["source_type"] == "brand_site" and NOT_PRODUCT.search(r["url"]) and not r["gtin"]
               and len(set(r["toks"])) < 4)
    if not r["toks"] or cat_url or generic:
        matches.append((r, None, "no_name" if not r["toks"] else "not_a_product_page", 0.0))
        continue
    sid, method, conf = find(r)
    # another anchor source joins an existing product only on GTIN or the same name tokens
    if sid and (method == "gtin" or set(skus[sid]["toks"]) == set(r["toks"])):
        matches.append((r, sid, method, conf))
        if r["gtin"] and gtin14(r["gtin"]) not in by_gtin:
            by_gtin[gtin14(r["gtin"])] = sid
            skus[sid]["gtin"] = skus[sid]["gtin"] or r["gtin"]
    else:
        matches.append((r, new_sku(r), "anchor", 1.0))

# retailer / wikidata rows: match per URL (all crawl captures of one URL are the same product)
url_best = {}
for r in rows:
    if r["source_type"] in ("brand_site", "open_facts"):
        continue
    url_best.setdefault(r["url"], None)
    sid, method, conf = find(r)
    prev = url_best[r["url"]]
    if prev is None or conf > prev[2]:
        url_best[r["url"]] = (sid, method, conf)
for r in rows:
    if r["source_type"] in ("brand_site", "open_facts"):
        continue
    sid, method, conf = url_best[r["url"]]
    if sid and (method == "gtin" or conf >= FUZZY_MIN):
        matches.append((r, sid, method, conf))
    else:
        matches.append((r, None, f"below_threshold({method})", conf))

# ---------- claims per row ----------
for r, sid, method, conf in matches:
    r["norm_claims"] = extract_claims([r["title"], r["description"], *r["claims"]], r["brand"])

# ---------- flat CSV (all rows) + unmatched CSV ----------
FLAT = ["row_id", "brand", "product_name", "gtin", "source_type", "source_domain", "url", "captured_at", "locale",
        "title", "description", "claims", "ingredients", "is_synthetic", "collector_version",
        "sku_id", "match_method", "match_confidence", "normalized_claims", "free_from", "seals", "row_key"]
flat = open(OUT / "aveeno_listerine_descriptions.csv", "w", newline="", encoding="utf-8")
um = open(OUT / "unmatched_rows.csv", "w", newline="", encoding="utf-8")
fw, uw = csv.writer(flat), csv.writer(um)
fw.writerow(FLAT)
uw.writerow(FLAT + ["best_candidate_sku_id", "best_candidate_name"])
loadable = []
for i, (r, sid, method, conf) in enumerate(matches, 1):
    r["row_id"] = i
    nc = r["norm_claims"]
    line = [i, r["brand"], r["product_name"], r["gtin"], r["source_type"], r["source_domain"], r["url"],
            r["captured_at"], r["locale"], r["title"], r["description"],
            " | ".join(c.replace("|", "/") for c in r["claims"]), r["ingredients"], "false", COLLECTOR_VERSION,
            sid or "", method, conf, " | ".join(l for l, _ in nc["claims"]),
            " | ".join(l for l, _ in nc["free_from"]), " | ".join(l for l, _ in nc["seals"]), row_key(r)]
    fw.writerow(line)
    if sid is None:
        cand, _, _ = find(r) if r["toks"] else (None, None, None)
        uw.writerow(line + [cand or "", skus[cand]["name"] if cand else ""])
    elif r["url"] in EXISTING:
        dropped["url_already_in_db"] += 1
    else:
        loadable.append((r, sid, method, conf))
flat.close()
um.close()

# ---------- per-table CSVs ----------
pages, variants = {}, {}
for r, sid, method, conf in loadable:
    s = skus[sid]
    s["sources"][r["source_type"]] += 1
    s["domains"].add(r["source_domain"])
    nm = r["product_name"][:300]
    if nm and nm != s["name"] and nm not in s["aliases"] and len(s["aliases"]) < 25:
        s["aliases"].append(nm)
    c = country_of(r)
    if r["url"] not in pages:
        pages[r["url"]] = {"id": alloc("page", r["url"]), "source_type": PAGE_TYPE[r["source_type"]], "country": c,
                           "retailer": RETAILER.get(r["source_domain"]) or {
                               "brand_site": f"{r['brand']} brand site ({r['source_domain']})",
                               "open_facts": r["source_domain"], "wikidata": "Wikidata"}[r["source_type"]]}
    vk = (sid, c or "XX", r["size"] or "")
    variants.setdefault(vk, alloc("variant", "|".join(map(str, vk))))
    r["snapshot_id"] = alloc("snapshot", row_key(r))
used_skus = {sid for _, sid, _, _ in loadable}

with open(OUT / "organisation.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["id", "name", "created_at"])
    w.writerow([ORG_ID, ORG_NAME, NOW])
brand_ids = {b: alloc("brand", b) for b in sorted({s["brand"] for s in skus.values()})}
with open(OUT / "brand.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["id", "organisation_id", "name", "aliases", "positioning"])
    for b, i in brand_ids.items():
        w.writerow([i, ORG_ID, b, "[]", json.dumps(POSITIONING.get(b, []))])
last_seen = defaultdict(str)
for r, sid, _, _ in loadable:
    last_seen[sid] = max(last_seen[sid], r["captured_at"])
with open(OUT / "sku.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["id", "organisation_id", "brand_id", "gtin", "name", "line", "last_checked_at", "aliases"])
    for sid in sorted(used_skus):
        s = skus[sid]
        g = re.sub(r"\D", "", s["gtin"] or "")
        w.writerow([sid, ORG_ID, brand_ids[s["brand"]], g[-14:] if g else "", s["name"], "", last_seen[sid],
                    json.dumps(s["aliases"], ensure_ascii=False)])
with open(OUT / "variant.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["id", "organisation_id", "sku_id", "market", "size", "formula_version", "valid_from", "valid_to"])
    for (sid, m, size), vid in sorted(variants.items(), key=lambda x: x[1]):
        w.writerow([vid, ORG_ID, sid, m, size[:50], "", "", ""])
with open(OUT / "page.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["id", "organisation_id", "url", "source_type", "retailer", "country", "weight"])
    for url, p in pages.items():
        w.writerow([p["id"], ORG_ID, url, p["source_type"], p["retailer"][:100], p["country"] or "", "1.0"])

# row -> product match (not a DB table; kept for audit of the matching step)
with open(OUT / "row_product_match.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["row_id", "snapshot_id", "sku_id", "gtin", "match_method", "match_confidence", "row_key"])
    for r, sid, method, conf in loadable:
        w.writerow([r["row_id"], r["snapshot_id"], sid, r["gtin"], method, conf, row_key(r)])

snap_parts, part_f, part_w, part_bytes = [], None, None, 0


def new_part():
    global part_f, part_w, part_bytes
    if part_f:
        part_f.close()
    name = f"snapshot_part{len(snap_parts) + 1:02d}.csv.gz"
    snap_parts.append(name)
    part_f = gzip.open(OUT / name, "wt", encoding="utf-8", newline="")
    part_w = csv.writer(part_f)
    part_w.writerow(["id", "organisation_id", "page_id", "fetched_at", "content_hash", "html"])
    part_bytes = 0


new_part()
sidx = csv.writer(open(OUT / "snapshot_index.csv", "w", newline="", encoding="utf-8"))
sidx.writerow(["snapshot_id", "page_id", "fetched_at"])
for r, sid, method, conf in loadable:
    sidx.writerow([r["snapshot_id"], pages[r["url"]]["id"], r["captured_at"]])
ef = open(OUT / "extraction.csv", "w", newline="", encoding="utf-8")
ew = csv.writer(ef)
ew.writerow(["id", "organisation_id", "snapshot_id", "sku_id", "fields", "created_at"])
claim_counts = Counter()
for r, sid, method, conf in loadable:
    html = raw_html(r)
    if part_bytes > PART_TEXT_BYTES:
        new_part()
    part_w.writerow([r["snapshot_id"], ORG_ID, pages[r["url"]]["id"], r["captured_at"],
                     hashlib.sha256(html.encode("utf-8")).hexdigest(), html])
    part_bytes += len(html.encode("utf-8"))
    fields = {}
    if r["product_name"]:
        fields["name"] = {"value": r["product_name"], "quote": r["product_name"]}
    for fld in ("claims", "free_from", "seals"):
        items = r["norm_claims"][fld]
        if items:
            fields[fld] = {"value": [l for l, _ in items], "quote": " | ".join(q for _, q in items)}
            claim_counts.update(f"{fld}:{l}" for l, _ in items)
    if r["ingredients"]:
        fields["ingredients"] = {"value": [x.strip() for x in re.split(r",(?![^()]*\))", r["ingredients"]) if x.strip()],
                                 "quote": r["ingredients"]}
    # not in compare.py's COMPARED_FIELDS; kept so the raw marketing text travels with the extraction
    if r["description"]:
        fields["description"] = {"value": r["description"], "quote": r["description"]}
    if r["claims"]:
        fields["raw_bullets"] = {"value": r["claims"], "quote": " | ".join(r["claims"])}
    ew.writerow([r["snapshot_id"], ORG_ID, r["snapshot_id"], sid, json.dumps(fields, ensure_ascii=False), r["captured_at"]])
part_f.close()
ef.close()

# ---------- load_order.sql ----------
cols = {
    "organisation": "id, name, created_at",
    "brand": "id, organisation_id, name, aliases, positioning",
    "sku": "id, organisation_id, brand_id, gtin, name, line, last_checked_at, aliases",
    "variant": "id, organisation_id, sku_id, market, size, formula_version, valid_from, valid_to",
    "page": "id, organisation_id, url, source_type, retailer, country, weight",
    "snapshot": "id, organisation_id, page_id, fetched_at, content_hash, html",
    "extraction": "id, organisation_id, snapshot_id, sku_id, fields, created_at",
}
# load_order.sql is written per chunk by chunk.py; here only the id registry is saved
REG_P.write_text(json.dumps(REG, ensure_ascii=False), encoding="utf-8")

# ---------- per-product source counts ----------
prod_rows = []
for sid in sorted(used_skus):
    s = skus[sid]
    n_types = len(s["sources"])
    prod_rows.append({"sku_id": sid, "brand": s["brand"], "name": s["name"], "gtin": s["gtin"] or "",
                      "source_types": n_types, "source_domains": len(s["domains"]),
                      "rows": sum(s["sources"].values()), **{k: s["sources"].get(k, 0) for k in PAGE_TYPE},
                      "scoreable": len(s["domains"]) >= 2})
with open(OUT / "product_sources.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(prod_rows[0].keys()))
    w.writeheader()
    w.writerows(sorted(prod_rows, key=lambda x: (-x["source_domains"], -x["rows"])))

# ---------- stats ----------
mm = Counter(m if sid else "unmatched" for _, sid, m, _ in matches)
stats = {
    "flat_rows": len(matches), "loadable_rows": len(loadable), "unmatched_rows": sum(1 for m in matches if m[1] is None),
    "unmatched_by_source": dict(Counter(r["source_type"] for r, sid, _, _ in matches if sid is None)),
    "unmatched_by_reason": dict(Counter(m for _, sid, m, _ in matches if sid is None)),
    "match_methods": dict(mm), "dropped": dict(dropped),
    "rows_by_source": dict(Counter(r["source_type"] for r, *_ in matches)),
    "rows_by_brand": dict(Counter(r["brand"] for r, *_ in matches)),
    "rows_by_source_brand": {f"{a}/{b}": v for (a, b), v in Counter((r["source_type"], r["brand"]) for r, *_ in matches).items()},
    "rows_by_domain": dict(Counter(r["source_domain"] for r, *_ in matches).most_common()),
    "loadable_by_source": dict(Counter(r["source_type"] for r, *_ in loadable)),
    "products": len(used_skus), "products_by_brand": dict(Counter(skus[s]["brand"] for s in used_skus)),
    "scoreable_products_2plus_domains": sum(p["scoreable"] for p in prod_rows),
    "scoreable_by_brand": dict(Counter(p["brand"] for p in prod_rows if p["scoreable"])),
    "products_2plus_source_types": sum(1 for p in prod_rows if p["source_types"] >= 2),
    "pages": len(pages), "variants": len(variants), "snapshots": len(loadable), "snapshot_parts": snap_parts,
    "unique_gtins": len({gtin14(r["gtin"]) for r, *_ in matches if r["gtin"]}),
    "captured_min": min(r["captured_at"] for r, *_ in matches), "captured_max": max(r["captured_at"] for r, *_ in matches),
    "captured_range_by_source": {s: [min(r["captured_at"] for r, *_ in matches if r["source_type"] == s),
                                     max(r["captured_at"] for r, *_ in matches if r["source_type"] == s)]
                                 for s in {r["source_type"] for r, *_ in matches}},
    "rows_with_description": sum(1 for r, *_ in matches if r["description"]),
    "rows_with_raw_bullets": sum(1 for r, *_ in matches if r["claims"]),
    "rows_with_normalized_claim": sum(1 for r, *_ in matches if any(r["norm_claims"].values())),
    "rows_with_ingredients": sum(1 for r, *_ in matches if r["ingredients"]),
    "top_claims_in_load": dict(claim_counts.most_common(40)),
    "retailer_urls_with_multiple_snapshots": sum(1 for v in Counter(r["url"] for r, *_ in loadable if r["source_type"] == "common_crawl_retailer").values() if v > 1),
}
(OUT / "stats.json").write_text(json.dumps(stats, indent=1, ensure_ascii=False), encoding="utf-8")
print(json.dumps(stats, indent=1, ensure_ascii=False))
