# Extraction Agent — spec (CSV mode)

Status: draft v1, 2026-11-17. Based on `main` at `b73ab64`. No code changed.

The agent reads page snapshots (raw HTML) from CSV files and writes `extraction.csv`: one row per
snapshot, with the fields the conflict agent compares (`name`, `ingredients`, `free_from`, `claims`,
`seals`) plus `description`. It uses no database and no API. The default parser is deterministic:
same input folder = byte-identical output. An LLM step exists only behind `--llm`, off by default (§9).

Its output is the `extraction.csv` input of the conflict & drift score agent
(`docs/agents/conflict-score-agent.md`).

## 0. What exists today

- `app/pipeline/extract.py` has no HTML parser. `ManualExtractor` reads hand-written fields from
  `fixtures/manual_extractions.json` keyed by page URL; `LLMExtractor` is a TODO.
- The only real HTML parsing lives in `data_collect/`: `common.extract_page()` (JSON-LD, meta,
  bullets, ingredients), `build.py` (cleaning, `valid_ingredients`, `dedupe_ingredients`, building
  `extraction.fields`) and `claims.extract_claims()` (regexes to claim/free_from/seal labels).
  It uses `lxml`, which the backend does not depend on.
- This agent moves that logic into the backend as one pure module and fixes the gaps in §12.

Dry run of today's `data_collect` extractor on the three pilot fixture pages (read-only):
- Rite Aid CeraVe: all fields match `manual_extractions.json`.
- Hannaford Aveeno: all match except the claim `Tested on sensitive skin` (no pattern in `claims.py`).
- Kenvue Pro Aveeno: name and ingredients match; no claims, because they sit in a `<p>`, not a list.
- Drug Facts pages: only the first ingredients block is read.
§5 closes all four (paragraph candidates, the added claim pattern, both Drug Facts blocks).

## 1. Run

```
uv run python -m app.agents.extraction \
    --in  data/export/            # snapshot.csv (or snapshot_*.csv.gz parts), page.csv, page_sku.csv
    --out data/agent_out/         # extraction.csv, extraction_log.csv
    [--snapshot 101,102]          # only these snapshots; default = all
    [--prior data/export/extraction.csv]  # rows already extracted; kept, not re-parsed (§7)
    [--reparse]                   # re-parse snapshots that already have a prior row
    [--llm]                       # optional LLM fill-in for empty fields; off by default (§9)
```

Snapshots are processed in `snapshot.id` order. Exit code 0 when every snapshot gave a row or a
logged skip, 1 when any snapshot hit a parse error (§8), 2 when an input file or column is missing.

## 2. Input CSVs (`--in`)

UTF-8, header row, comma-separated, RFC 4180 quoting (the `html` cell holds newlines and commas).
Column names = DB column names. Empty cell = null. Timestamps ISO 8601 with offset.
Set `csv.field_size_limit` to at least 64 MB; HTML cells are large.

| File | Required | Columns read |
|---|---|---|
| `snapshot.csv` or `snapshot_*.csv.gz` | yes | `id`, `organisation_id`, `page_id`, `fetched_at`, `content_hash`, `html` |
| `page.csv` | yes | `id`, `organisation_id`, `url`, `retailer` |
| `page_sku.csv` | yes* | `page_id`, `sku_id` — which product a page sells (see §12, gap 3) |
| `extraction.csv` | no | prior rows, via `--prior` |

`snapshot_*.csv.gz` parts are what `data_collect/build.py` writes; all parts are read and
concatenated. For data_collect output, build `page_sku.csv` from `row_product_match.csv`
(snapshot_id, sku_id) joined to `snapshot_index.csv` (snapshot_id, page_id).

\* A page missing from `page_sku.csv` falls back to the `sku_id` of that page's newest row in
`--prior`. With neither, the snapshot is `no_sku` (§6). The agent never guesses a SKU from page text.

Validation before any parsing: files and columns present, `snapshot.id` unique, every
`snapshot.page_id` in `page.csv`, every `page_sku.page_id` in `page.csv`. Any failure: exit 2,
nothing written. A `content_hash` that is not `sha256(html)` is a warning in the log, not an error.

## 3. Output CSVs (`--out`)

Written to a temp folder, renamed into `--out` only when the run finished.

**`extraction.csv`** — exactly the DB columns:
`id, organisation_id, snapshot_id, sku_id, fields, created_at`

| Column | Value |
|---|---|
| `id` | `snapshot.id` (same convention as `data_collect/build.py`; one row per snapshot, stable across runs) |
| `organisation_id` | `snapshot.organisation_id` |
| `snapshot_id` | `snapshot.id` |
| `sku_id` | from `page_sku.csv` for the snapshot's page |
| `fields` | JSON, see below |
| `created_at` | `snapshot.fetched_at` (not the wall clock, so reruns are identical) |

`fields` = `{field: {"value": ..., "quote": "..."}}`, the shape `extract.py`, `run.py` and
`truth.py` already read. Keys in this fixed order: `name, ingredients, free_from, claims, seals,
description`; inside each, `value` then `quote`. Serialised with
`json.dumps(fields, ensure_ascii=False)`. A field not found on the page is left out (not written as
empty), which `compare()` already treats as empty.

Rows sorted by `id`. Prior rows (from `--prior`) not re-parsed are copied through unchanged.

**`extraction_log.csv`** — one row per selected snapshot:
`snapshot_id, page_id, sku_id, status, fields_found, method, parser_version, warnings, error`

- `status`: `ok`, `kept` (prior row kept), `empty`, `blocked`, `not_product`, `no_sku`, `failed`.
- `fields_found`: e.g. `name|ingredients|claims`.
- `method`: `parser`, or `parser+llm` when §9 filled a field.
- `parser_version`: constant in the module (e.g. `ex-1`), bumped on any rule change.

## 4. Text preparation (before any field rule)

1. Decode: the cell is already text. Apply `fix_mojibake` (from `data_collect/common.py`).
2. Parse with BeautifulSoup `html.parser` (the backend has `beautifulsoup4`, not `lxml`).
3. Read JSON-LD (`<script type="application/ld+json">`) first, with `_jsonld_products` from
   `common.py`: Product / ProductGroup, walking `@graph`, `mainEntity`, `itemListElement`, `hasVariant`.
4. Remove `script` (except JSON-LD), `style`, `svg`, `noscript`, `iframe`, comments, and the
   `nav`, `header`, `footer`, `aside` elements and anything with `role="navigation"`.
5. Every text piece goes through `clean()` = `html.unescape`, then the `unescape_text` fragment
   stripping from `build.py`, then whitespace collapsed to one space, NBSP and zero-width chars removed,
   Unicode NFC.
6. **Visible text** = `clean(body.get_text(" "))`. Every `quote` must be a substring of the visible
   text or of a JSON-LD string. Tests enforce this (§10).

## 5. Field rules

First source that yields a valid value wins. Sources are listed in priority order.

### name (string)
1. JSON-LD Product `name`.
2. First `h1`.
3. `og:title`.
4. `<title>` with a trailing `| Retailer`, `- Retailer` or ` – Retailer` removed when the tail
   matches `page.retailer` or the page host.

Value = the cleaned text, case and symbols (®, ™) kept; `compare.name_key` ignores them.
Quote = same text. Rejected when longer than 300 characters (the `sku.name` limit).

### ingredients (list of strings, INCI order)
Sources:
1. Element whose `id` or `class` contains `ingredient` (case-insensitive): its text without the heading.
2. A heading or label whose whole text is `Ingredients`, `Inactive Ingredients`, `Active Ingredients`
   (optional colon): the next text block of 20+ characters (as `common.extract_page`).
3. Regex `Ingredients\s*:\s*(.+?)(\.\s|$)` over visible text.
4. JSON-LD `ingredients` / `hasIngredient` when present.

Drug Facts pages (Listerine-type: `Active ingredients` and `Inactive ingredients`): value = active
ingredient names (strength like `0.092%` and the purpose word dropped) followed by the inactive list.
Quote = both blocks joined by ` | `.

Then:
- Strip a leading `[label]` and `(In)active ingredients:`; drop a trailing `.`; drop a trailing
  `May contain` / `+/-` tail into the same list (kept as items).
- Split on commas not inside parentheses: `re.split(r",(?![^()]*\))", s)`.
- `dedupe_ingredients` (case/whitespace-insensitive, order kept).
- Accept only if `valid_ingredients` passes (3+ items, mean item length ≤ 45, 2+ INCI hint words,
  no `{` or `@type`). Otherwise the field is left out and `warnings` gets `ingredients_rejected`.

Value = list of items as written (no renames; `compare.normalise_ingredient` does that).
Quote = the accepted source text before splitting.

### free_from, claims, seals (lists of strings)
Candidate texts, in document order: bullet items (the `BULLET_SELECTORS` list from `common.py`,
plus `main li`, then any `li` outside removed regions), then the description (below), then other
`p` blocks of 20–600 characters. Not the name or title: a product named "Fragrance Free ..." is a
name, not a claim, unless a bullet or the description says it too.

Each candidate text is matched against the pattern table (moved from `data_collect/claims.py` into
`app/pipeline/claim_patterns.py`, shared by data_collect and the agent). Each pattern has a field,
a canonical label and a regex.

- **Value = the matched span as written on the page** (cleaned, original case). Not the canonical
  label. `compare.py` already maps wordings to one key (`free_from_key`, `claim_key`, `seal_key`);
  keeping the page's wording is what lets it report `drift` for a different wording.
- **Quote = the whole candidate text** the span came from (a sentence or bullet).
- One item per canonical label per page: the first match in document order. For seals, when one
  text holds several alternatives of the same seal, keep the one whose `seal_key` is a value of
  `SEAL_ALIASES` (e.g. `NEA Seal of Acceptance` over `National Eczema Association`).
- Item order = document order of first match.

Minimum patterns (pilot + Aveeno/Listerine; claims.py already has more):

| Field | Pattern (case-insensitive) | Example span |
|---|---|---|
| free_from | `(X)[\s-]*free` · `free (of|from) (added )?(X)` · `(no|without) (added )?(X)` with X in fragrance, parfum, paraben(s), phthalate(s), dye(s), alcohol, sulfate(s), soap, oil, gluten, silicone(s), talc, preservative(s), sugar | `Fragrance Free`, `paraben free`, `sulfate-free` |
| claims | non-comedogenic · hypoallergenic · dermatologist (tested|recommended|developed) · tested on sensitive skin · pH[- ]balanced · tear[- ]free · clinically (proven|shown) … · allergy tested · (colloidal oatmeal)( skin protectant)? · kills 99.9% of germs · cruelty[- ]free · vegan | `Non-comedogenic`, `hypoallergenic` |
| seals | `(NEA|National Eczema Association)( Seal( of Acceptance)?)?` · `(ADA|American Dental Association) (Seal|Accepted)` · Leaping Bunny · EWG Verified · USDA Organic | `NEA Seal of Acceptance` |

Conjunctions are handled by matching each `X[\s-]*free` separately:
`Fragrance free, paraben free, phthalate free, dye free and alcohol free` gives five items.

A match preceded within 3 words by `not` or `isn't` is dropped (warning `negated_claim`).

### description (string)
1. JSON-LD Product `description` (HTML inside it stripped).
2. `og:description`.
3. `meta name="description"`.
4. First `p` in `main` (or body) of 60+ characters that is not inside the ingredients block.

Value = cleaned text, cut at 3000 characters on a word boundary. Quote = same text.
Not compared by `compare.py` today (§12, gap 6); stored so the text travels with the extraction.

## 6. Missing, blocked and non-product pages

A snapshot that is not a readable product page gets **no** extraction row, only a log row.
This matters: `run.py` and `truth.py` use the newest extraction per page. An empty row would hide the
last good extraction and raise false `missing` conflicts for every field. With no row, the last
good extraction stays in use.

Checked in this order:

| Status | When |
|---|---|
| `no_sku` | page has no SKU (no `page_sku.csv` row and no prior extraction), or more than one |
| `empty` | `html` empty, or visible text under 200 characters and no JSON-LD Product |
| `blocked` | title or first 2000 visible characters match a block-page pattern: `access denied`, `pardon our interruption`, `robot or human`, `are you a robot`, `captcha`, `request blocked`, `just a moment`, `attention required`, `verify you are human`, `enable javascript and cookies`, `403 forbidden`, `404 not found`, `page not found`, `this product is no longer available` |
| `not_product` | parsing found none of `ingredients`, `free_from`, `claims`, `seals` (a name or description alone is not enough) |
| `ok` | otherwise |

A page with some fields missing is `ok`; the missing fields are left out of `fields` and listed in
nothing else. The parser cannot tell "page does not state seals" from "parser did not find seals",
so the golden tests (§10) are the guard.

## 7. Idempotency

- One row per snapshot: `id = snapshot_id`. A page has exactly one SKU (§6).
- No wall clock, random, network or dict-order input reaches the output: `created_at` is
  `fetched_at`, field order is fixed, lists keep document order, rows are sorted by `id`.
- Same input folder and flags gives byte-identical `extraction.csv` and `extraction_log.csv`.
- With `--prior`, snapshots that already have a row are kept as is (`status=kept`), so manual or
  reviewed rows are never overwritten. `--reparse` replaces them with the parser output, same `id`.
- Two snapshots of a page with the same `content_hash` give identical `fields` (same function of the
  same HTML). `store_snapshot` already avoids storing unchanged HTML twice.

## 8. Error handling

| Case | Behaviour |
|---|---|
| Missing file / column, duplicate snapshot id, unknown page id | exit 2, nothing written |
| Exception while parsing one snapshot | that snapshot `failed` in the log with the error; prior row (if any) copied; others continue; exit 1 |
| Malformed JSON-LD block | that block ignored, warning `bad_jsonld`; other sources used |
| `content_hash` ≠ sha256(html) | warning `hash_mismatch`; parsed anyway |
| Prior `extraction.csv` row with invalid JSON | copied unchanged, warning; not re-parsed unless `--reparse` |

## 9. Optional LLM step (`--llm`, off by default)

Without `--llm` the agent imports no LLM client and makes no network call (a test blocks sockets).

With `--llm` and `ANTHROPIC_API_KEY` set:
- Only for `ok` snapshots, and only for compared fields the parser left out. Never overrides a
  parser value.
- The prompt gives the visible text (cut to 30,000 characters) and asks for each missing field a value
  and a quote, as structured JSON output (same client style as `truth._claude_pick`).
- A returned item is kept only if its quote is a verbatim substring of the visible text; others are
  dropped with warning `llm_quote_not_found`.
- Results are cached in `--out/llm_cache.csv` keyed by `(content_hash, field, parser_version)`, and the
  cache is read on the next run, so reruns stay identical once the cache is filled.
- `method = parser+llm` in the log. A failed call is a warning; the parser row is written as is.

## 10. Tests (pytest, CSV fixtures, no DB, no network)

Fixtures in `backend/tests/fixtures/extraction_csv/<case>/{in,expected}/`. Each test runs the agent
on `in/` and diffs `out/` against `expected/`.

1. **Pilot golden**: the three pilot fixture pages (Rite Aid CeraVe, Hannaford and Kenvue Pro Aveeno)
   as `snapshot.csv`; exact `extraction.csv`.
2. **Pilot parity with manual**: for each pilot page, `compare(truth, parsed)` gives the same
   (field, verdict) list as `compare(truth, manual_extractions.json)`. Known wording differences are
   allowed only where both map to the same `compare` key.
3. **Quote invariant**: every `quote` in every expected file is a substring of that snapshot's visible
   text or JSON-LD.
4. **Idempotency**: run twice, byte-identical output. Shuffle input row order: same output.
5. **Prior rows**: run 1 output fed as `--prior` gives all `kept`, identical file; with `--reparse`,
   same ids.
6. **JSON-LD first**: page with JSON-LD name/description and a different `h1`: JSON-LD wins.
7. **Drug Facts**: Listerine-style active/inactive blocks give actives (no %) then inactives.
8. **Ingredients edge cases**: commas inside parentheses, trailing period, duplicates, `Ingredients:`
   label, list that fails `valid_ingredients` (field left out, warning).
9. **Free-from conjunction**: the Hannaford sentence gives five items in order.
10. **Name is not a claim**: "Fragrance Free" only in the `h1` gives no `free_from`.
11. **Negation**: "not fragrance free" gives no item.
12. **Entities and mojibake**: `&amp;`, `Â®`, double-escaped text cleaned.
13. **Blocked / empty / not_product / no_sku**: no extraction row, correct log status, exit 0.
14. **Parse error** in one snapshot: `failed`, others written, exit 1.
15. **Missing `page.csv`**: exit 2, `--out` untouched.
16. **No LLM by default**: sockets blocked, run passes.
17. **LLM fill-in** (fake client): fills only empty fields; a non-verbatim quote is dropped.
18. **Hand-off**: output loads into the conflict agent's `extraction.csv` validation with no errors.

## 11. Build steps

1. `app/pipeline/html_extract.py`: pure `extract_fields(html, page) -> (fields, status, warnings)`,
   ported from `data_collect/common.py` and `build.py`, on `html.parser`.
2. `app/pipeline/claim_patterns.py`: patterns from `data_collect/claims.py`, returning spans.
   `data_collect` imports it too, so both produce the same values.
3. `app/agents/csv_io.py` (shared with the conflict agent): read/validate, atomic write.
4. `app/agents/extraction.py`: CLI from §1.
5. `HtmlExtractor` in `extract.py` implementing the existing `Extractor` protocol by calling
   `extract_fields`, so the DB pipeline and the seed can use the same parser.
6. Fixtures and tests from §10.

## 12. Gaps found in the current code

1. **No HTML extractor in the backend.** Only `ManualExtractor` (JSON keyed by URL) and an
   `LLMExtractor` TODO. Nothing turns a stored snapshot into fields.
2. **Parser lives only in `data_collect/`**, uses `lxml` (not a backend dependency) and is not shared
   with the backend, so DB extractions and loaded CSV extractions can differ.
3. **No page→SKU link in the schema.** `seed.py` binds page and SKU in code; data_collect uses
   `row_product_match.csv`. A new fetch has no way to know its SKU. Proposal: `page.sku_id` column
   (or a `page_sku` table if one page can list several SKUs).
4. **No fetch status on `snapshot`.** No HTTP status, final URL or error columns; `fetch_page` raises
   on HTTP errors and stores nothing. Blocked pages can only be detected from content (§6).
5. **No provenance or uniqueness on `extraction`.** No `method` / `parser_version` column, so manual,
   parsed and LLM rows look alike and cannot be re-parsed selectively. No unique
   `(snapshot_id, sku_id)`: `save_extraction` adds a duplicate on every rerun.
6. **`description` is extracted but never compared.** `COMPARED_FIELDS` has five fields; description
   changes are invisible to conflicts and drift.
7. **data_collect writes canonical labels as values.** `build.py` stores `claims.py` labels as `value`
   and joins quotes with ` | `, so wording differences that `compare.py` reports as `drift` disappear,
   and the quote is not a verbatim span. This spec stores the page's wording instead.
8. **Stale `backend/app/collector/`**: only `__pycache__` (agent, http, extract, llm, …), no sources.
   Leftover of a deleted module; safe to delete.
9. **No tests for `extract.py`, `fetch_page` or `store_snapshot`.**
10. **`data_collect` also writes `raw_bullets`** into `fields`; nothing reads it. This agent does not.

Open: whether a page that sells several SKUs (bundles, size pickers) needs one extraction per SKU;
then "one row per snapshot" becomes "one row per (snapshot, SKU)" and `id` can no longer be
`snapshot_id`.
