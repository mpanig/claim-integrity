# Aveeno / Listerine data collection: handoff

State as of 2026-11-17 ~06:00 UTC, after chunk_001 was pushed. The released data is in `data/aveeno_listerine/`
(see its README.md and MANIFEST.csv). This file covers how to continue.

## Layout (this laptop, WSL)

- Collector code: `data_collect/*.py` (committed). Python 3.12 venv in `data_collect/.venv`
  (`uv venv .venv --python 3.12 && uv pip install --python .venv/bin/python requests beautifulsoup4 lxml warcio`).
- Raw caches (gitignored, local only): `/home/munna/projects/claim-integrity/data_collect/raw/`
  - `robots/` every robots.txt read
  - `brand_sites/sitemaps/`, `brand_sites/pages/<host>/<sha1(url)[:16]>.html` (UTF-8 fixed)
  - `open_facts/dump_matches.jsonl` (Aveeno/Listerine records from the dumps); `open_facts_api_unused/` (early API
    responses, NOT used: robots.txt disallows /api)
  - `common_crawl/collinfo.json`, `common_crawl/cdx/<crawl>_cluster.jsonl` (**indexed captures, mostly not yet
    fetched**), `common_crawl/html/<domain>/<sha1(url)[:16]>_<timestamp>.html.gz` (fetched WARC records)
  - `wikidata/`
- Intermediates (gitignored): `data_collect/out/`
  - `brand_sites.jsonl`, `open_facts.jsonl`, `wikidata.jsonl`, `common_crawl.jsonl` (rows per source)
  - `id_registry.json` (**the id registry, also copied into data/aveeno_listerine/id_registry.json; keep them in sync**)
  - `picks.json` (inferred-truth picks), `full/` (last full build), `release/` (chunks as committed)

## Scripts

| script | what | run (from data_collect/) |
|---|---|---|
| `common.py` | polite HTTP (≤1 req/s/host, retries, UTF-8 default), robots.txt checks, HTML extraction | library |
| `open_facts.py` | Open Beauty / Products Facts **data dumps** (static.*/data/, ODbL) → rows | `.venv/bin/python open_facts.py out/open_facts.jsonl` |
| `brand_sites.py` | brand sites: robots.txt → sitemaps → allowed product pages (uses page cache) | `.venv/bin/python brand_sites.py out/brand_sites.jsonl` |
| `cc_index.py` + `common_crawl.py` | Common Crawl: stream each crawl's `cluster.idx` from data.commoncrawl.org, range-read the index blocks for retailer slug prefixes, then range-read WARC records | `.venv/bin/python common_crawl.py out/common_crawl.jsonl <max_warc_fetches>` |
| `wikidata.py` | Wikidata entity API (SPARQL timed out) | `.venv/bin/python wikidata.py out/wikidata.jsonl` |
| `claims.py` | claim regexes → canonical labels for the app's `claims` / `free_from` / `seals` | library |
| `build.py` | clean, dedupe, product matching, claims, full per-table CSVs with registry ids | `SOURCES=brand_sites,open_facts,common_crawl,wikidata .venv/bin/python build.py out/full out/existing_page_urls.txt out/id_registry.json` |
| `infer.py` | inferred truth exactly as backend `truth.py` (imports its normalisers/majority) | backend venv, `PYTHONPATH=../backend`: `infer.py out/full autopick out/picks.json` then `infer.py out/full write out/picks.json out/id_registry.json` (`candidates` mode lists what needs picking) |
| `validate.py` | schema check of a table-CSV dir (NOT NULL, lengths, JSON, ISO, FKs, uniques) | `.venv/bin/python validate.py <dir>` |
| `chunk.py` | cut the next self-contained chunk from out/full | `.venv/bin/python chunk.py out/full out/id_registry.json out/release <size>` |
| `load_test.py` | create throwaway DB `claim_integrity_chunktest`, alembic head, load chunks twice, compare counts, drop it | copy into backend/ and run with backend venv: `python load_test.py <chunk dirs...>` |
| `readme.py` | README for the release from out/full stats | `.venv/bin/python readme.py out/full` |

`out/existing_page_urls.txt` = page URLs already in the main DB (read-only query), so loads never collide on page.url.

## Source status

- **Brand sites**: done. 723 pages from 15 reachable domains. Unreachable / no product URLs in sitemap:
  aveeno.fr, .es, .co.za, .co.nz, .com.br (redirects to kenvuebrands.com), listerine.fr, .in, .co.nz.
- **Open Facts**: done from dumps: Open Beauty Facts JSONL (80,671 records scanned → 298), Open Products Facts CSV
  (49,619 → 1). Open Food Facts skipped (multi-GB dump; API search showed 3 products). Revision history is only
  available via /api or /cgi, both disallowed by robots.txt, so not collected.
- **Wikidata**: done, 57 label rows (31 kept; scholarly articles dropped).
- **Common Crawl**: index lookups done for ~21 of the latest 24 crawls (CC-MAIN-2026-43 … 2024-51); failed with
  server errors / timeouts: CC-MAIN-2026-30, CC-MAIN-2025-33, CC-MAIN-2025-30 (re-run: cached crawls are skipped).
  ~750 captures indexed (cvs.com, target.com, boots.com, walgreens.com; **0** for Amazon, Walmart, Ulta: they
  block CCBot). The **WARC page fetches were stopped** when chunk_001 was pushed: captures are listed in
  `raw/common_crawl/cdx/*_cluster.jsonl`; already-fetched pages are cached in `raw/common_crawl/html/`.
  Note: `index.commoncrawl.org`'s robots.txt disallows the CDX API, so do not use it; `data.commoncrawl.org` welcomes
  downloads.
- **Wayback Machine**: not started. CDX API works (`web.archive.org/cdx/search/cdx?url=<prefix>&matchType=prefix&
  output=json&fl=timestamp,original,digest,statuscode&filter=statuscode:200&collapse=digest&showDupeCount=true`),
  but the archive showed "Temporarily Offline" on some calls today. web.archive.org has no robots.txt (404).

## Id scheme (stable across chunks)

`id_registry.json` maps natural keys to ids; ids start at 100001 per table so they never collide with app rows.
- organisation: name ("Public data: Aveeno & Listerine") · brand: name
- sku: `<source_type>|<url>` of the anchor row (brand-site page or Open Facts record that created the product)
- page: url · variant: `<sku_id>|<market>|<size>`
- snapshot (and extraction, same id): `<url>|<captured_at>|<sha1(description)[:12]>`
- inferred_truth: sku_id
- `_next` holds the next free id per table; `_chunks` records which snapshot / unmatched rows went into which chunk.

**Always build with the same registry**, or ids change. Never edit ids by hand.

## Chunk rules

- Each chunk takes ~SIZE not-yet-shipped snapshots (a remainder under 25 % of SIZE joins the chunk).
- Snapshot + extraction rows belong to exactly one chunk; parent rows (organisation, brand, sku, variant, page) and
  inferred_truth for the chunk's products are repeated with the same ids.
- `load_order.sql`: staging table per table + `INSERT … ON CONFLICT DO NOTHING`; inferred_truth upserts on sku_id when
  the incoming `updated_at` is newer. Needs alembic 0018. Loads alone, in any order, twice.
- Test every chunk with `load_test.py` (loads all chunks twice into the throwaway DB; counts must not change).
- Append the commit hash to the chunk's MANIFEST.csv row in the next commit.

## Next steps toward ~50k real rows

1. Re-run `common_crawl.py` (it reuses the index cache) to fetch the indexed captures, plus the 3 failed crawls.
2. Extend Common Crawl to all crawls back to 2013 (`coll[:24]` in common_crawl.py) and add the extra retailer slug
   prefixes in `cc_index.py` (`HOSTS`): riteaid, kroger, costco, samsclub, heb, meijer, shoppersdrugmart.ca,
   londondrugs, well.ca, superdrug, tesco, sainsburys, asda, chemistwarehouse, priceline.com.au, woolworths.com.au,
   nykaa, 1mg, netmeds, dm.de, rossmann.de, douglas, lookfantastic, iherb, ebay (/itm/ product pages). Brand
   sites in CC too (`com,aveeno)/`, `com,listerine)/` etc.). Each new crawl is one ~100 MB streamed cluster.idx.
3. Wayback: `collapse=digest` CDX for every brand-site product URL prefix and every retailer product URL found
   (incl. amazon.*/dp/, walmart.com/ip/), keep `dupecount` as capture_count, fetch `web.archive.org/web/<ts>id_/<url>`
   at ≤1 req/s with 429 backoff. Expect this to be the largest source; budget ~3,600 fetches/hour.
4. For every new batch: build → infer (autopick + write) → validate → chunk → load_test → commit.
5. If the real total stays well under 50k, report the true number. Do not pad.
