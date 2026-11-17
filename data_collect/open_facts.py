"""Open Facts from the official data dumps (static.*/data/ is allowed by robots.txt; /api is disallowed for
User-agent: *, so the search API is not used). Streams each dump and keeps Aveeno / Listerine products.

Dumps:
  Open Beauty Facts   openbeautyfacts-products.jsonl.gz   (all fields incl. product_name_xx)
  Open Products Facts en.openproductsfacts.org.products.csv.gz
  Open Food Facts     not used: its dump is several GB and the API search found only 3 such products.
"""
import csv
import gzip
import io
import json
import sys

from common import clean, polite_get, save_raw, S

BRANDS = ("aveeno", "listerine")
DUMPS = [
    ("openbeautyfacts.org", "https://world.openbeautyfacts.org",
     "https://static.openbeautyfacts.org/data/openbeautyfacts-products.jsonl.gz", "jsonl"),
    ("openproductsfacts.org", "https://world.openproductsfacts.org",
     "https://static.openproductsfacts.org/data/en.openproductsfacts.org.products.csv.gz", "csv"),
]


def brand_of(p):
    tags = p.get("brands_tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]
    text = " ".join(tags).lower() + " " + str(p.get("brands") or "").lower()
    for b in BRANDS:
        if b in text:
            return b
    return None


def row(dom, base, p, brand):
    code = str(p.get("code", ""))
    names = {k: v for k, v in p.items() if k.startswith("product_name") and v}
    langs = [k[len("product_name_"):] for k in names if k != "product_name"]
    lang = p.get("lang") or (langs[0] if langs else "")
    ctags = p.get("countries_tags") or []
    if isinstance(ctags, str):
        ctags = [t for t in ctags.split(",") if t]
    countries = ",".join(c.replace("en:", "") for c in ctags)
    name = p.get("product_name") or next(iter(names.values()), "")
    alt = " | ".join(f"{k}={clean(v)}" for k, v in names.items() if k != "product_name")
    labels = p.get("labels") or ""
    labels = [clean(x) for x in (labels if isinstance(labels, str) else ",".join(labels)).split(",") if clean(x)]
    desc = [clean(p.get("generic_name") or "")]
    if alt:
        desc.append("Names: " + alt)
    ts = p.get("last_modified_t") or p.get("created_t")
    return {
        "brand": brand.capitalize(), "product_name": clean(name),
        "gtin": code if code.isdigit() and 8 <= len(code) <= 14 else "", "source_type": "open_facts",
        "source_domain": dom, "url": f"{base}/product/{code}",
        "captured_at": int(ts) if str(ts).isdigit() else ts, "locale": f"{lang}-{countries}" if countries else lang,
        "title": clean(name), "description": " ".join(x for x in desc if x), "claims": labels,
        "ingredients": clean(p.get("ingredients_text") or ""),
        "extra": {"categories": p.get("categories", ""), "brands": p.get("brands", ""), "dump": True},
    }


def main(out_path):
    rows, kept = [], []
    for dom, base, url, kind in DUMPS:
        n = 0
        with S.get(url, stream=True, timeout=300) as r:
            r.raise_for_status()
            gz = gzip.GzipFile(fileobj=r.raw)
            text = io.TextIOWrapper(gz, encoding="utf-8", errors="replace")
            it = (json.loads(l) for l in text) if kind == "jsonl" else csv.DictReader(text, delimiter="\t")
            for p in it:
                n += 1
                b = brand_of(p)
                if b:
                    rows.append(row(dom, base, p, b))
                    kept.append(p)
        print(dom, "scanned", n, "kept", sum(1 for x in rows if x["source_domain"] == dom), file=sys.stderr)
    save_raw("open_facts/dump_matches.jsonl", "\n".join(json.dumps(p, ensure_ascii=False) for p in kept))
    with open(out_path, "w", encoding="utf-8") as f:
        for x in rows:
            f.write(json.dumps(x, ensure_ascii=False) + "\n")
    print("open_facts rows", len(rows), file=sys.stderr)


if __name__ == "__main__":
    csv.field_size_limit(10**9)
    main(sys.argv[1])
