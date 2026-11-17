"""Write README.md for the data folder from stats.json + product_sources.csv + collector reports."""
import csv
import json
import sys
from pathlib import Path

D = Path(sys.argv[1])
st = json.loads((D / "stats.json").read_text(encoding="utf-8"))
brand_report = json.loads(Path("out/brand_sites_report.json").read_text())
cc = json.loads(Path("out/common_crawl_stats.json").read_text()) if Path("out/common_crawl_stats.json").exists() else {}
prods = list(csv.DictReader(open(D / "product_sources.csv", encoding="utf-8")))
files = sorted(p for p in D.iterdir() if p.is_file() and p.name != "README.md")
_its = json.loads((D / "inferred_truth_stats.json").read_text())
it_line = (f"Rows: **{_its['rows']}** products · `claude` {_its['claude']} · `majority` {_its['majority']} · "
           f"fields picked {_its['picked_fields']} (of which {_its['picked_non_majority']} differ from the plain majority).")


def table(d, h=("key", "rows")):
    out = [f"| {h[0]} | {h[1]} |", "|---|---:|"]
    out += [f"| {k} | {v} |" for k, v in d.items()]
    return "\n".join(out)


blocked = [f"- `{d}`: {v}" for d, v in brand_report.items() if "unreachable" in v or "fetched=0" in v]
top = [p for p in prods if p["scoreable"] == "True"][:40]
md = """# Aveeno & Listerine public product descriptions""" + f"""

Real, public product descriptions and claims for Aveeno and Listerine products, collected for the
claim-consistency (drift) score. Nothing here is synthetic. The collector is in `data_collect/`; raw
responses stay on the collecting machine (`data_collect/raw/`, not committed).

Collected: {st['captured_range_by_source'].get('brand_site', ['?'])[0][:10]} (brand sites, Open Facts, Wikidata); retailer
pages come from Common Crawl snapshots, so their `captured_at` is the crawl capture time.
Overall `captured_at` range: **{st['captured_min']} → {st['captured_max']}**.

## Chunks

Data ships in chunks under `chunk_NNN/` (see `MANIFEST.csv`). Each chunk is a complete, self-contained set of
per-table CSVs plus its own `load_order.sql`: it loads alone into an empty claim_integrity DB (alembic head, 0018)
or on top of other chunks, in any order, and can be re-run. Parent rows (organisation, brand, sku, variant, page,
inferred_truth) repeat across chunks with the same stable ids (`id_registry.json`, natural key → id); snapshot and
extraction rows belong to exactly one chunk. Every table loads through a staging table with
`INSERT ... ON CONFLICT DO NOTHING`; `inferred_truth` upserts on `sku_id` when the incoming row is newer.

The numbers below describe everything collected and built so far (all chunks).

## Row counts

**{st['flat_rows']}** rows in the flat CSV · **{st['loadable_rows']}** matched to a product and in the load files ·
**{st['unmatched_rows']}** unmatched (in `unmatched_rows.csv` only).

{table(st['rows_by_source'], ('source_type', 'rows'))}

{table(st['rows_by_brand'], ('brand', 'rows'))}

{table(st['rows_by_source_brand'], ('source/brand', 'rows'))}

Captured range per source:

{table({k: f"{v[0]} → {v[1]}" for k, v in st['captured_range_by_source'].items()}, ('source', 'range'))}

<details><summary>Rows per domain</summary>

{table(st['rows_by_domain'], ('domain', 'rows'))}
</details>

## Products and scoreability

- Canonical products (`sku.csv`): **{st['products']}** ({', '.join(f'{k} {v}' for k, v in st['products_by_brand'].items())})
- **Scoreable** (seen on ≥2 distinct domains): **{st['scoreable_products_2plus_domains']}** ({', '.join(f'{k} {v}' for k, v in st['scoreable_by_brand'].items())})
- Seen in ≥2 source *types* (e.g. brand site + retailer): {st['products_2plus_source_types']}
- Unique GTINs: {st['unique_gtins']}
- Retailer URLs with ≥2 crawl snapshots (drift over time): {st['retailer_urls_with_multiple_snapshots']}

Per-product source counts for every product are in `product_sources.csv`. Top scoreable products:

| sku_id | brand | product | domains | brand rows | retailer rows | open facts rows |
|---:|---|---|---:|---:|---:|---:|
""" + "\n".join(f"| {p['sku_id']} | {p['brand']} | {p['name'][:70]} | {p['source_domains']} | {p['brand_site']} | {p['common_crawl_retailer']} | {p['open_facts']} |" for p in top) + f"""

## Product matching

Canonical products come from the brand sites and Open Facts (an Open Facts row joins a brand-site product when the
GTIN matches or the normalised name scores ≥ 0.92). Every other row is matched to one of them:

1. GTIN/UPC/EAN exact (zero-padded to 14 digits): `match_method=gtin`, confidence 1.0
2. Normalised name (brand words, sizes and retailer noise removed; UK/US spelling folded), same brand, token
   similarity ≥ 0.80: `match_method=fuzzy_name`, confidence = score

All captures of one retailer URL share one match. Results per row are in `row_product_match.csv` and in the
`sku_id / match_method / match_confidence` columns of the flat CSV.

{table(st['match_methods'], ('match_method', 'rows'))}

Unmatched by reason: {', '.join(f'{k} {v}' for k, v in st['unmatched_by_reason'].items())}.
Unmatched by source: {', '.join(f'{k} {v}' for k, v in st['unmatched_by_source'].items())}.

## Claims

Claims are read from the title, description and bullet list of each row and mapped to canonical labels in the
three list fields the app compares (`claims`, `free_from`, `seals`; see `backend/app/pipeline/compare.py`), e.g.
"Fragrance Free", "Kills 99.9% of germs", "Dermatologist recommended", "24-hour moisture", "ADA Seal of Acceptance".
The sentence each claim came from is kept as the `quote`. Rules: `data_collect/claims.py` (English plus common
FR/DE/IT/ES/PT wordings). Rows with ≥1 normalised claim: {st['rows_with_normalized_claim']}.

Most frequent claims in the load files:

{table(st['top_claims_in_load'], ('field:claim', 'rows'))}

## Inferred truth (`inferred_truth.csv`, schema alembic 0018)

`approved_claim` is empty, so each product's truth is the **LLM-inferred truth**, built the way
`backend/app/pipeline/truth.py` builds it: latest extraction per page, the app's own `compare.py` normalisers and
`majority()` (imported from the backend, not re-implemented). Where a field had more than one candidate value, the
pick was made by **Claude in a Claude Code session**, because `backend/.env` has no ANTHROPIC_API_KEY and the app
could not call Claude itself. The pick follows the same instruction `_claude_pick` sends: choose among the listed
values only, the one most likely to match the manufacturer's current product; brand sites and higher page weight
are more reliable; old formulas linger on retailer pages. After reviewing the candidate sets, Claude applied these
decision rules to every field:

- name: brand-site name with the most page weight; tie → the name without a size/pack suffix
- ingredients: brand-site INCI list over crowd-sourced Open Facts; then weight; then the most complete list
- claims / free_from / seals: the manufacturer's own site over retailer copies; then weight; then the most complete statement

Every picked field, with the chosen value, its sources and the reason, is in `inferred_truth_reasons.csv`.
{it_line}

- `method` = `claude` (the value `truth.py` writes for a Claude pick) on rows with at least one picked field,
  `majority` where all sources agreed (nothing to pick).
- The schema has **no "unverified" flag column**. `inferred_truth` is unverified by definition (the app shows it as
  unverified and replaces it as soon as a truth sheet is approved). The schema was not changed.
- `conflict` rows are not shipped: the app computes them on the next check. Because no truth sheet exists, the app
  will write `conflict.truth_source = 'inferred'` itself.

**Will `refresh_inferred` overwrite these rows?** `source_hash` is computed exactly as `refresh_inferred` computes
it: `sha256(json.dumps(sorted extraction ids + [use_claude]))`, with `use_claude = false` because no key is set.
So on the next check run, while `ANTHROPIC_API_KEY` stays empty and a product's extractions don't change, the
hash matches and the row is **kept as is**. The row **is recomputed** (overwritten) when (a) a new extraction is
added for that product (a new snapshot): it falls back to `majority` without a key, or (b) an ANTHROPIC_API_KEY is
set: the hash changes and the app asks Claude through the API. Approving a truth sheet deletes the row.

## Files

| file | what |
|---|---|
| `aveeno_listerine_descriptions.csv` | flat CSV, one row per source × capture (requested columns + `sku_id, match_method, match_confidence, normalized_claims, free_from, seals`) |
| `unmatched_rows.csv` | rows that could not be matched to a product, with the best candidate |
| `organisation.csv`, `brand.csv`, `sku.csv`, `variant.csv`, `page.csv`, `snapshot_partNN.csv.gz`, `extraction.csv` | one CSV per Postgres table, exact column names and order (alembic 0017) |
| `inferred_truth.csv` | one row per product, alembic 0018 `inferred_truth` schema (LLM-inferred truth, see above) |
| `inferred_truth_reasons.csv` | every picked field: chosen value, sources, number of candidates, reason |
| `load_order.sql` | `\\copy` script in FK order, one transaction, resets sequences; needs alembic 0018 |
| `snapshot_index.csv` | snapshot id → page id → fetched_at (helper, not a table) |
| `row_product_match.csv` | flat row → snapshot → sku, with match method and confidence |
| `product_sources.csv` | per product: rows per source type, distinct domains, scoreable flag |
| `stats.json` | all numbers in this README |

Sizes: {', '.join(f'{p.name} {p.stat().st_size / 1e6:.1f} MB' for p in files)}

### Loading

```
cd backend && uv run alembic upgrade head   # 0018 adds inferred_truth + conflict.truth_source
cd ../data/aveeno_listerine
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f load_order.sql
```

Everything goes into a new organisation **"Public data: Aveeno & Listerine"** (id 100001); all ids start at 100001
so they don't collide with existing rows. Page URLs already in the DB are skipped ({st['dropped'].get('url_already_in_db', 0)}).

### Schema notes (collected data with no table column; schema not changed)

- `extraction.fields` holds `name`, `ingredients`, `claims`, `free_from`, `seals` (the fields `compare.py` uses) plus
  `description` and `raw_bullets`, which the comparer ignores.
- No column for: page `title`, meta / og descriptions, `locale` (only the 2-letter `page.country`), match
  method / confidence (→ `row_product_match.csv`), Open Facts labels / categories, `is_synthetic`, `collector_version`.
- `page.source_type` uses `brand` and `retailer` like the app, plus `open_facts` and `wikidata` for those sources.
- `approved_claim` is left empty: public pages are evidence, not the approved source of truth.
- `snapshot.html` is the page with scripts (except JSON-LD), styles and SVG removed, to keep the files small.
  Open Facts / Wikidata snapshots hold the JSON record instead of HTML. Snapshot files are gzipped and split so
  each stays under 50 MB.
- `variant.market` is `XX` when the country is unknown (Open Facts products sold in several countries).

## Sources, method and limits

- **Open Beauty Facts / Open Products Facts** official data dumps (`static.*/data/`; all countries). Their robots.txt
  disallows `/api` for all user agents, so the API is not used: an early test run used the search API, and those
  responses were discarded and replaced with the dumps. Open Food Facts was skipped (multi-GB dump; only 3 such
  products). Rows: product name (+ all `product_name_xx`), generic name, ingredients, labels as claims.
  `captured_at` = the record's last edit. Dumps (listed on the projects' official /data pages, ODbL):
  `https://static.openbeautyfacts.org/data/openbeautyfacts-products.jsonl.gz`,
  `https://static.openproductsfacts.org/data/en.openproductsfacts.org.products.csv.gz`.
- **Brand sites** (Aveeno/Listerine country sites): robots.txt read and honoured, URLs from sitemap.xml, ≤1 req/s per host.
  Title, meta / og description, JSON-LD Product description and GTIN, PDP bullet list, ingredients.
- **Common Crawl** retailer snapshots (Amazon .com/.co.uk/.in/.ca, Walmart, Target, CVS, Walgreens, Ulta, Boots):
  no live retailer requests. `index.commoncrawl.org`'s robots.txt disallows its CDX API, so lookups use the
  index shards on `data.commoncrawl.org` (one streamed `cluster.idx` per crawl, then byte-range reads of the
  matching index blocks and WARC records). Each crawl capture of a page is its own row. Captures that were bot-check
  or empty pages are dropped. Crawls: {cc.get('crawls', 'see stats')}.
- **Wikidata**: brand / product items whose label names the brand; labels and descriptions in all languages
  (SPARQL timed out, so the entity API was used). Scholarly articles mentioning the brand are dropped.

Blocked / empty brand sources:
{chr(10).join(blocked) or '- none'}

Common Crawl run: {json.dumps(cc)}

### Amazon and Walmart rows

Rows from `amazon.*` and `walmart.com` (filter: `source_domain` in amazon.com, amazon.co.uk, amazon.in, amazon.ca,
walmart.com): **{sum(v for k, v in st['rows_by_domain'].items() if k.startswith('amazon') or k == 'walmart.com')}**
so far. Common Crawl holds no captures for their Aveeno/Listerine product URLs (both sites largely block its
crawler). Any later rows come only from archives (Common Crawl / Wayback), never live requests. Kept in their own
section so you can decide whether to keep them.

Not reached: the requested 1,000,000 rows. Public, ToS-respecting sources for two brands hold roughly a few thousand
product-description records. These are true counts, with no padding or synthetic rows.

## Licences

- Open Beauty/Food/Products Facts: **ODbL 1.0** (database), DbCL (contents). Attribution: "© Open Food Facts
  contributors". Derived databases must stay under ODbL (share-alike).
- Common Crawl: used under the [Common Crawl Terms of Use](https://commoncrawl.org/terms-of-use). The page text is
  still the retailer's / brand's copyright; use it for internal analysis, don't republish.
- Brand sites: © Kenvue / the brand owners; collected for internal claim-consistency analysis only.
- Wikidata: CC0.
"""
(D / "README.md").write_text(md, encoding="utf-8")
print("README written", len(md))
