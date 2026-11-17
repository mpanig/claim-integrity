# Aveeno & Listerine public product descriptions

Real, public product descriptions and claims for Aveeno and Listerine products, collected for the
claim-consistency (drift) score. Nothing here is synthetic. The collector is in `data_collect/`; raw
responses stay on the collecting machine (`data_collect/raw/`, not committed).

Collected: 2026-11-17 (brand sites, Open Facts, Wikidata); retailer
pages come from Common Crawl snapshots, so their `captured_at` is the crawl capture time.
Overall `captured_at` range: **2016-03-04T15:36:36+00:00 → 2026-11-17T05:16:33+00:00**.

## Chunks

Data ships in chunks under `chunk_NNN/` (see `MANIFEST.csv`). Each chunk is a complete, self-contained set of
per-table CSVs plus its own `load_order.sql`: it loads alone into an empty claim_integrity DB (alembic head, 0018)
or on top of other chunks, in any order, and can be re-run. Parent rows (organisation, brand, sku, variant, page,
inferred_truth) repeat across chunks with the same stable ids (`id_registry.json`, natural key → id); snapshot and
extraction rows belong to exactly one chunk. Every table loads through a staging table with
`INSERT ... ON CONFLICT DO NOTHING`; `inferred_truth` upserts on `sku_id` when the incoming row is newer.

The numbers below describe everything collected and built so far (all chunks).

## Row counts

**1052** rows in the flat CSV · **880** matched to a product and in the load files ·
**172** unmatched (in `unmatched_rows.csv` only).

| source_type | rows |
|---|---:|
| brand_site | 723 |
| open_facts | 298 |
| wikidata | 31 |

| brand | rows |
|---|---:|
| Aveeno | 644 |
| Listerine | 408 |

| source/brand | rows |
|---|---:|
| brand_site/Aveeno | 535 |
| brand_site/Listerine | 188 |
| open_facts/Aveeno | 103 |
| open_facts/Listerine | 195 |
| wikidata/Aveeno | 6 |
| wikidata/Listerine | 25 |

Captured range per source:

| source | range |
|---|---:|
| brand_site | 2026-11-17T05:11:50+00:00 → 2026-11-17T05:16:33+00:00 |
| open_facts | 2016-03-04T15:36:36+00:00 → 2026-11-16T21:00:44+00:00 |
| wikidata | 2026-11-17T05:08:23+00:00 → 2026-11-17T05:08:23+00:00 |

<details><summary>Rows per domain</summary>

| domain | rows |
|---|---:|
| openbeautyfacts.org | 298 |
| www.aveeno.com | 208 |
| www.aveeno.ca | 135 |
| www.listerine.com | 61 |
| www.aveeno.co.uk | 52 |
| www.aveeno.in | 43 |
| www.aveeno.com.au | 38 |
| www.aveeno.de | 32 |
| wikidata.org | 31 |
| www.aveeno.it | 27 |
| www.listerine.ca | 27 |
| www.listerine.co.uk | 26 |
| www.listerine.com.br | 17 |
| www.listerine.de | 16 |
| www.listerine.es | 16 |
| www.listerine.it | 14 |
| www.listerine.co.za | 7 |
| www.listerine.com.au | 4 |
</details>

## Products and scoreability

- Canonical products (`sku.csv`): **688** (Aveeno 394, Listerine 294)
- **Scoreable** (seen on ≥2 distinct domains): **101** (Aveeno 74, Listerine 27)
- Seen in ≥2 source *types* (e.g. brand site + retailer): 64
- Unique GTINs: 687
- Retailer URLs with ≥2 crawl snapshots (drift over time): 0

Per-product source counts for every product are in `product_sources.csv`. Top scoreable products:

| sku_id | brand | product | domains | brand rows | retailer rows | open facts rows |
|---:|---|---|---:|---:|---:|---:|
| 100010 | Aveeno | Aveeno® Skin Relief Moisturizing Lotion | 5 | 4 | 0 | 4 |
| 100150 | Aveeno | Aveeno® Daily Moisturizing Body Wash | 5 | 4 | 0 | 2 |
| 100005 | Aveeno | Aveeno® Daily Moisturizing Lotion | 4 | 5 | 0 | 4 |
| 100006 | Aveeno | Aveeno Baby Daily Moisture Lotion | 4 | 3 | 0 | 2 |
| 100364 | Aveeno | AVEENO® Stress Relief Moisturising Lotion | 4 | 3 | 0 | 2 |
| 100025 | Aveeno | Aveeno® Daily Moisturising Body Lotion | 4 | 3 | 0 | 1 |
| 100132 | Aveeno | Aveeno® Skin Relief Body Wash | 4 | 3 | 0 | 1 |
| 100143 | Aveeno | Aveeno® Dermexa Daily Emollient Cream | 4 | 3 | 0 | 1 |
| 100243 | Aveeno | Aveeno® Daily Moisturising Oil Mist | 4 | 3 | 0 | 1 |
| 100291 | Aveeno | AVEENO Intense Relief™ Hand Cream | 4 | 3 | 0 | 1 |
| 100323 | Aveeno | AVEENO Stress Relief™ Body Wash | 4 | 3 | 0 | 1 |
| 100079 | Aveeno | AVEENO® Oat Milk Blend Conditioner | 3 | 2 | 0 | 1 |
| 100101 | Aveeno | AVEENO® Oat Milk Blend Shampoo hair | 3 | 2 | 0 | 1 |
| 100136 | Aveeno | AVEENO® Baby Calming Comfort Bath | 3 | 2 | 0 | 1 |
| 100174 | Aveeno | AVEENO® Baby Calming Comfort Lotion | 3 | 2 | 0 | 1 |
| 100181 | Aveeno | Aveeno® Daily Moisturising Creamy Oil | 3 | 2 | 0 | 1 |
| 100192 | Aveeno | AVEENO® Baby Wash & Shampoo | 3 | 3 | 0 | 0 |
| 100280 | Aveeno | Blackberry & Quinoa Blend Color Protect & Strengthen Conditioner | 3 | 3 | 0 | 0 |
| 100288 | Aveeno | AVEENO® DAILY MOISTURISING HAND CREAM | 3 | 2 | 0 | 1 |
| 100289 | Aveeno | Aveeno Blackberry & Quinoa Blend Color Protect & Strengthen Shampoo 12 | 3 | 3 | 0 | 0 |
| 100134 | Listerine | Enjuague Bucal LISTERINE® Mentol | 2 | 1 | 0 | 2 |
| 100156 | Aveeno | AVEENO® Baby Eczema Care Moisturizing Cream | 2 | 2 | 0 | 1 |
| 100267 | Aveeno | Baby Eczema Therapy Nighttime Balm | 2 | 1 | 0 | 2 |
| 100498 | Aveeno | Eczema Therapy Daily Moisturizing Cream | 2 | 1 | 0 | 2 |
| 100002 | Aveeno | Aveeno Moisturizing Bar, 3.5 Oz | 2 | 2 | 0 | 0 |
| 100003 | Aveeno | Aveeno Baby Daily Moisture Wash & Shampoo | 2 | 1 | 0 | 1 |
| 100009 | Aveeno | AVEENO THERAPEUTIC SHAVE GEL 7OZ | 2 | 2 | 0 | 0 |
| 100023 | Aveeno | Kids Sensitive Skin Face & Body Gel Cream | 2 | 2 | 0 | 0 |
| 100024 | Listerine | LISTERINE® COOL MINT Intensiv | 2 | 1 | 0 | 1 |
| 100032 | Listerine | LISTERINE® On-The-Go COOL MINT® Alcohol Free Mouthwash Packets | 2 | 2 | 0 | 0 |
| 100033 | Listerine | LISTERINE® ADVANCED WHITE MILDER GESCHMACK | 2 | 1 | 0 | 1 |
| 100039 | Listerine | Listerine® Pocketmist Freshburst Fresh Breath Spray | 2 | 2 | 0 | 0 |
| 100042 | Listerine | LISTERINE® Flavours Mild and Minty Mouthwash​ | 2 | 1 | 0 | 1 |
| 100049 | Listerine | Listerine® Pocketmist Cool Mint Fresh Breath Spray | 2 | 2 | 0 | 0 |
| 100050 | Listerine | LISTERINE® Total Care Intense Taste Classic Mouthwash | 2 | 1 | 0 | 1 |
| 100064 | Aveeno | Aveeno Daily Moisturizing Body Scrub, 8 Oz | 2 | 2 | 0 | 0 |
| 100066 | Listerine | LISTERINE® Advanced White Milder Taste Mouthwash​ | 2 | 2 | 0 | 0 |
| 100081 | Listerine | Enjuague Bucal LISTERINE® Mentol Suave Sin Alcohol | 2 | 1 | 0 | 1 |
| 100086 | Listerine | Collutorio LISTERINE® Total Care Denti & Gengive Gusto Delicato Senza  | 2 | 1 | 0 | 1 |
| 100091 | Aveeno | AVEENO Daily Moisturizing™ Lotion Sheer Hydration | 2 | 2 | 0 | 0 |

## Product matching

Canonical products come from the brand sites and Open Facts (an Open Facts row joins a brand-site product when the
GTIN matches or the normalised name scores ≥ 0.92). Every other row is matched to one of them:

1. GTIN/UPC/EAN exact (zero-padded to 14 digits): `match_method=gtin`, confidence 1.0
2. Normalised name (brand words, sizes and retailer noise removed; UK/US spelling folded), same brand, token
   similarity ≥ 0.80: `match_method=fuzzy_name`, confidence = score

All captures of one retailer URL share one match. Results per row are in `row_product_match.csv` and in the
`sku_id / match_method / match_confidence` columns of the flat CSV.

| match_method | rows |
|---|---:|
| anchor | 688 |
| unmatched | 172 |
| fuzzy_name | 112 |
| gtin | 80 |

Unmatched by reason: not_a_product_page 100, no_name 41, below_threshold(fuzzy_name) 31.
Unmatched by source: brand_site 115, open_facts 26, wikidata 31.

## Claims

Claims are read from the title, description and bullet list of each row and mapped to canonical labels in the
three list fields the app compares (`claims`, `free_from`, `seals`; see `backend/app/pipeline/compare.py`), e.g.
"Fragrance Free", "Kills 99.9% of germs", "Dermatologist recommended", "24-hour moisture", "ADA Seal of Acceptance".
The sentence each claim came from is kept as the `quote`. Rules: `data_collect/claims.py` (English plus common
FR/DE/IT/ES/PT wordings). Rows with ≥1 normalised claim: 628.

Most frequent claims in the load files:

| field:claim | rows |
|---|---:|
| free_from:Fragrance Free | 145 |
| claims:Clinically proven | 129 |
| claims:For sensitive skin | 111 |
| claims:Hypoallergenic | 102 |
| free_from:Alcohol Free | 83 |
| free_from:Paraben Free | 81 |
| claims:Contains colloidal oatmeal | 79 |
| free_from:Dye Free | 77 |
| claims:Non-comedogenic | 72 |
| claims:Contains prebiotic oat | 71 |
| claims:Fights bad breath | 68 |
| claims:Prevents cavities | 63 |
| claims:Dermatologist recommended | 63 |
| free_from:Soap Free | 54 |
| claims:Relieves itchy skin | 53 |
| free_from:Sulfate Free | 46 |
| claims:Fights gingivitis | 45 |
| claims:Dermatologist tested | 45 |
| claims:Strengthens enamel | 41 |
| claims:Fresh breath | 36 |
| claims:Kills 99.9% of germs | 35 |
| claims:Tartar control | 33 |
| claims:Tear free | 32 |
| claims:Contains fluoride | 32 |
| claims:Reduces plaque | 31 |
| claims:24-hour moisture | 31 |
| claims:Relieves eczema | 31 |
| claims:Vegan | 29 |
| free_from:Phthalate Free | 27 |
| claims:Broad spectrum SPF | 26 |
| claims:Pediatrician recommended | 19 |
| claims:Whitening | 16 |
| claims:Natural ingredients | 13 |
| claims:48-hour moisture | 13 |
| free_from:Steroid Free | 12 |
| claims:Water resistant | 11 |
| claims:Sensitive teeth | 10 |
| seals:ADA Seal of Acceptance | 9 |
| seals:NEA Seal of Acceptance | 3 |

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
Rows: **688** products · `claude` 115 · `majority` 573 · fields picked 178 (of which 45 differ from the plain majority).

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
| `load_order.sql` | `\copy` script in FK order, one transaction, resets sequences; needs alembic 0018 |
| `snapshot_index.csv` | snapshot id → page id → fetched_at (helper, not a table) |
| `row_product_match.csv` | flat row → snapshot → sku, with match method and confidence |
| `product_sources.csv` | per product: rows per source type, distinct domains, scoreable flag |
| `stats.json` | all numbers in this README |

Sizes: aveeno_listerine_descriptions.csv 1.0 MB, brand.csv 0.0 MB, build_stdout.txt 0.0 MB, extraction.csv 1.9 MB, inferred_truth.csv 0.3 MB, inferred_truth_reasons.csv 0.1 MB, inferred_truth_stats.json 0.0 MB, organisation.csv 0.0 MB, page.csv 0.1 MB, product_sources.csv 0.1 MB, row_product_match.csv 0.1 MB, sku.csv 0.1 MB, snapshot_index.csv 0.0 MB, snapshot_part01.csv.gz 13.1 MB, snapshot_part02.csv.gz 0.7 MB, stats.json 0.0 MB, unmatched_rows.csv 0.1 MB, variant.csv 0.0 MB

### Loading

```
cd backend && uv run alembic upgrade head   # 0018 adds inferred_truth + conflict.truth_source
cd ../data/aveeno_listerine
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f load_order.sql
```

Everything goes into a new organisation **"Public data: Aveeno & Listerine"** (id 100001); all ids start at 100001
so they don't collide with existing rows. Page URLs already in the DB are skipped (0).

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
  or empty pages are dropped. Crawls: see stats.
- **Wikidata**: brand / product items whose label names the brand; labels and descriptions in all languages
  (SPARQL timed out, so the entity API was used). Scholarly articles mentioning the brand are dropped.

Blocked / empty brand sources:
- `listerine.co.nz`: base=https://www.listerine.com.au sitemap=83 cands=0 allowed=0 fetched=0 failed=0
- `listerine.in`: base=https://www.listerine.in sitemap=111 cands=0 allowed=0 fetched=0 failed=0
- `aveeno.com.br`: base=https://www.kenvuebrands.com sitemap=1949 cands=0 allowed=0 fetched=0 failed=0
- `aveeno.es`: unreachable
- `aveeno.fr`: unreachable
- `aveeno.co.za`: unreachable
- `listerine.fr`: unreachable
- `aveeno.co.nz`: unreachable

Common Crawl run: {}

### Amazon and Walmart rows

Rows from `amazon.*` and `walmart.com` (filter: `source_domain` in amazon.com, amazon.co.uk, amazon.in, amazon.ca,
walmart.com): **0**
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
