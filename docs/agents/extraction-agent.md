# Extraction Agent — spec (Glean, CSV in / CSV out)

Status: draft v2, 2026-11-17. Based on `main` at `1963935`. No code changed.
v2: built as a Glean agent instead of a backend Python module. Field rules unchanged from v1.
v3 (2026-11-18, migration 0019): input is the `web_snapshot` table, which already carries `url`,
`retailer` and `sku_id`, so `page.csv` and `page_sku.csv` are no longer needed. Output rows go to
`page_extraction` (natural key `(snapshot_id, sku_id)`; `id` may be left out, so `id = snapshot_id`
is no longer required). Field rules unchanged. Table contract: `docs/agents/tables.md`.

The agent takes page snapshots (raw HTML) as CSV files and returns `extraction.csv`: one row per
snapshot, with the fields the conflict agent compares (`name`, `ingredients`, `free_from`, `claims`,
`seals`) plus `description`. No database, no API, no web access. The default path is deterministic:
the same input files give byte-identical output. An LLM fill-in step exists but is off by default (§9).

Its output is the `extraction.csv` input of the conflict & drift score agent
(`docs/agents/conflict-score-agent.md`).

## 0. Glean building blocks used, and where Python is needed

Glean workflow agents offer input fields, **Read document**, **Think** (LLM), **Branch**
(natural-language condition), **Respond**, sub-agents, and a sandboxed Python tool
(**Analyze data** / Code Writer: CSV, XLSX and JSON in, downloadable files out, no network,
about 500 MiB memory, 0.5 CPU). There is no loop-over-rows step, and Think and Branch are LLM calls.
Glean marks Analyze data as legacy and points to Autonomous agents for data work; the script below
runs the same in either, because it only needs a Python sandbox with file in and file out.

Decision: **one Python step, the parser (§5)**. Everything else is a Glean step. Python is needed
there because:
1. **Determinism.** Same snapshot must give the same row. Think steps are LLM calls and can vary.
2. **Size.** One HTML cell is 50 KB–2 MB. Hundreds of rows do not fit in agent memory, and there is
   no row loop to feed them one at a time.
3. **Verbatim quotes.** Every value must quote page text exactly. A substring check is code, not prose.

The Python step is a fixed script that reads the rules from a CSV (`extraction_rules.csv`, §5.1).
Changing a selector, a claim pattern or a block-page phrase means editing that CSV, not the script.

The script uses the **Python standard library only** (`csv`, `json`, `re`, `html`, `html.parser`,
`hashlib`, `unicodedata`, `gzip`). The Glean sandbox does not document which packages it has, so it
does not rely on `beautifulsoup4` or `lxml`.

## 1. Glean agent layout

Workflow agent `Snapshot extraction`, task-based (input fields, no chat trigger).

| # | Step | Type | What it does |
|---|---|---|---|
| 1 | Inputs | input fields | `snapshot_csv` (file, required), `page_csv` (file, required), `page_sku_csv` (file, required), `prior_extraction_csv` (file, optional), `extraction_rules_csv` (file or linked doc, required), `reparse` (yes/no, default no), `use_llm` (yes/no, default **no**) |
| 2 | Parse | Analyze data (Python) | Runs `extraction_parse.py` (§11) on the files. Writes `extraction.csv`, `extraction_log.csv`, `llm_queue.csv`, `run_summary.json` |
| 3 | Check | Branch | If `run_summary.exit_code` is 2: go to step 6 with the validation errors. Otherwise continue |
| 4 | LLM fill-in | Branch + Think + Analyze data | Only when `use_llm` = yes and `llm_queue.csv` has rows. See §9. Otherwise skipped |
| 5 | Output | Respond | Attaches `extraction.csv` and `extraction_log.csv` as downloads. Text: counts per status from `run_summary.json` |
| 6 | Failure | Respond | Lists the validation errors. No `extraction.csv` |

Step 2 is the only step that touches HTML. Steps 3–6 read only the small summary and queue files.

Batching: one run takes one `snapshot_csv`. When the file is larger than Glean's upload limit,
split it by `snapshot.id` range (data_collect already writes `snapshot_*.csv.gz` parts) and run once
per part, passing the previous run's `extraction.csv` as `prior_extraction_csv`.

## 2. Input CSVs

UTF-8, header row, comma-separated, RFC 4180 quoting (the `html` cell holds newlines and commas).
Column names = DB column names. Empty cell = null. Timestamps ISO 8601 with offset.
`.csv.gz` is accepted for the snapshot file.

| File | Required | Columns read |
|---|---|---|
| `snapshot.csv` | yes | `id`, `organisation_id`, `page_id`, `fetched_at`, `content_hash`, `html` |
| `page.csv` | yes | `id`, `organisation_id`, `url`, `retailer` |
| `page_sku.csv` | yes* | `page_id`, `sku_id` — which product a page sells (§12, gap 3) |
| `extraction.csv` (prior) | no | all columns; earlier rows to keep (§7) |
| `extraction_rules.csv` | yes | `field`, `kind`, `priority`, `pattern`, `label`, `note` (§5.1) |

For data_collect output, build `page_sku.csv` from `row_product_match.csv` (snapshot_id, sku_id)
joined to `snapshot_index.csv` (snapshot_id, page_id).

\* A page missing from `page_sku.csv` falls back to the `sku_id` of that page's newest prior row.
With neither, the snapshot is `no_sku` (§6). The agent never guesses a SKU from page text.

Validation before any parsing: files and columns present, `snapshot.id` unique, every
`snapshot.page_id` in `page.csv`, every `page_sku.page_id` in `page.csv`, every rules row has a
known `field` and `kind` and a pattern that compiles. Any failure: `exit_code` 2, no output files.
A `content_hash` that is not `sha256(html)` is a warning, not an error.

## 3. Output CSVs

**`extraction.csv`**, exactly the DB columns:
`id, organisation_id, snapshot_id, sku_id, fields, created_at`

| Column | Value |
|---|---|
| `id` | `snapshot.id` (same convention as `data_collect/build.py`; one row per snapshot, stable) |
| `organisation_id` | `snapshot.organisation_id` |
| `snapshot_id` | `snapshot.id` |
| `sku_id` | from `page_sku.csv` for the snapshot's page |
| `fields` | JSON, see below |
| `created_at` | `snapshot.fetched_at` (not the run time, so reruns are identical) |

`fields` = `{field: {"value": ..., "quote": "..."}}`, the shape `extract.py`, `run.py` and `truth.py`
already read. Keys in this fixed order: `name, ingredients, free_from, claims, seals, description`;
inside each, `value` then `quote`. Serialised with `json.dumps(fields, ensure_ascii=False)`.
A field not found is left out, which `compare()` already treats as empty.

Rows sorted by `id`. Prior rows not re-parsed are copied through unchanged.

**`extraction_log.csv`**, one row per input snapshot:
`snapshot_id, page_id, sku_id, status, fields_found, method, rules_version, warnings, error`

- `status`: `ok`, `kept`, `empty`, `blocked`, `not_product`, `no_sku`, `failed`.
- `fields_found`: e.g. `name|ingredients|claims`.
- `method`: `parser`, or `parser+llm` when §9 filled a field.
- `rules_version`: sha256 of `extraction_rules.csv`, first 12 characters.

**`llm_queue.csv`**: `snapshot_id, missing_fields, visible_text` for `ok` rows with an empty
compared field. Written always; used only when `use_llm` = yes.

**`run_summary.json`**: `exit_code` (0 ok, 1 some snapshot failed, 2 validation failed),
counts per status, `errors` (validation messages), `rules_version`.

## 4. Text preparation (in the Python step)

1. Apply `fix_mojibake` (from `data_collect/common.py`: re-decode Latin-1-read UTF-8 when `Â`, `Ã`
   or `â€` appear).
2. Parse with stdlib `html.parser.HTMLParser` into a light tree (tag, attributes, children, text).
3. Read JSON-LD (`<script type="application/ld+json">`): Product / ProductGroup objects, walking
   `@graph`, `mainEntity`, `itemListElement`, `hasVariant` (as `common._jsonld_products`).
   A block that is not valid JSON is skipped with warning `bad_jsonld`.
4. Drop `script` (except JSON-LD), `style`, `svg`, `noscript`, `iframe`, comments, and `nav`,
   `header`, `footer`, `aside` and `role="navigation"` subtrees.
5. Every text piece goes through `clean()`: `html.unescape` (twice if entities remain), strip stray
   tag fragments (the `unescape_text` rules from `build.py`), collapse whitespace, remove NBSP and
   zero-width characters, Unicode NFC.
6. **Visible text** = cleaned text of the remaining tree, pieces joined by one space. Every `quote`
   must be a substring of the visible text or of a JSON-LD string, or the value is dropped.

Selectors the script supports (enough for every rule below; no full CSS engine):
`tag`, `#id`, `.class`, `[attr]`, `[attr*='x']` (case-insensitive), `[attr='x']`, and a descendant
chain of those separated by spaces (e.g. `main [class*='rich-text'] li`).

## 5. Field rules

### 5.1 Rules file

`extraction_rules.csv` holds every selector, regex and word list. The script applies rows in
`priority` order per `field` and `kind`. First source that yields a valid value wins, except for list
fields, where all `match` rows run.

| `kind` | Meaning |
|---|---|
| `jsonld` | JSON-LD Product key, e.g. `name`, `description`, `ingredients` |
| `meta` | `<meta>` by `property` or `name`, e.g. `og:title`, `description` |
| `selector` | text of the first element (or all, for `bullets`) matching the selector |
| `heading` | regex that a heading or label's whole text must match; the value is the next text block of 20+ characters |
| `regex` | regex over visible text; group 1 is the value |
| `bullets` | selector whose matches are candidate texts for list fields |
| `paragraphs` | selector for extra candidate texts (20–600 characters) |
| `match` | list-field pattern; `label` = canonical label; the match span is the value |
| `negation` | words that cancel a `match` when within 3 words before it |
| `block` | phrase that marks a block page (§6) |
| `limit` | numeric setting, e.g. `name.max_len = 300` |

The repo ships a starter `extraction_rules.csv` built from the tables below and from
`data_collect/claims.py`. The tables are the content of that file, in readable form.

### 5.2 name (string)

| priority | kind | pattern |
|---|---|---|
| 1 | jsonld | `name` |
| 2 | selector | `h1` |
| 3 | meta | `og:title` |
| 4 | selector | `title`, with a trailing `| X`, `- X` or `– X` removed when X matches `page.retailer` or the page host |

Value = cleaned text, case and symbols (®, ™) kept; `compare.name_key` ignores them. Quote = same
text. Over 300 characters: rejected.

### 5.3 ingredients (list, INCI order)

| priority | kind | pattern |
|---|---|---|
| 1 | selector | `[id*='ingredient']`, then `[class*='ingredient']` (text without its heading) |
| 2 | heading | `^((in)?active )?ingredients:?$` |
| 3 | regex | `Ingredients\s*:\s*(.+?)(?:\.\s|$)` |
| 4 | jsonld | `ingredients`, `hasIngredient` |

Drug Facts pages (both `Active ingredients` and `Inactive ingredients` present): value = active
ingredient names (strength such as `0.092%` and the purpose word removed), then the inactive list.
Quote = both blocks joined by ` | `.

Then, in order (fixed in the script, from `build.py`):
- strip a leading `[label]` and `(In)active ingredients:`; drop a trailing `.`;
- split on commas not inside parentheses: `,(?![^()]*\))`;
- de-duplicate case- and whitespace-insensitively, order kept;
- accept only if 3+ items, mean item length ≤ 45, 2+ INCI hint words (the `INCI_HINT` list, a
  `limit`/`match` row set in the rules file), and no `{` or `@type`. Else the field is left out with
  warning `ingredients_rejected`.

Value = items as written (no renames; `compare.normalise_ingredient` does that). Quote = accepted
source text before splitting.

### 5.4 free_from, claims, seals (lists)

Candidate texts, in document order: `bullets` rows (the `BULLET_SELECTORS` list from `common.py`,
then `main li`, then any `li`), then the description (§5.5), then `paragraphs` rows (`main p`, `p`).
The name and title are not candidates: "Fragrance Free" in a product name is a name, not a claim.

Each candidate is matched against every `match` row of the field.
- **Value = the matched span as written** (cleaned, original case), not the canonical label.
  `compare.py` maps wordings to one key; keeping the page wording lets it report `drift`.
- **Quote = the whole candidate text** the span came from.
- One item per `label` per page: the first match in document order. For seals, when one text holds
  several alternatives for one label, keep the one whose `seal_key` is a value of `SEAL_ALIASES`
  (e.g. `NEA Seal of Acceptance` over `National Eczema Association`).
- A match with a `negation` word (`not`, `isn't`, `never`) within 3 words before it is dropped,
  warning `negated_claim`.
- Item order = document order.

Starter `match` rows (case-insensitive):

| field | pattern | label |
|---|---|---|
| free_from | `\b(X)[\s-]*free\b` · `\bfree (?:of|from) (?:added )?(X)\b` · `\b(?:no|without) (?:added )?(X)\b`, X in fragrance, parfum, parabens?, phthalates?, dyes?, alcohol, sulfates?, soap, oil, gluten, silicones?, talc, preservatives?, sugar | the X word, singular |
| claims | `non[- ]?comedogenic` | non-comedogenic |
| claims | `hypoallergenic` | hypoallergenic |
| claims | `dermatologist[- ](?:tested|recommended|developed)` | dermatologist … |
| claims | `tested on sensitive skin` | tested on sensitive skin |
| claims | `ph[- ]balanced` · `tear[- ]free` · `allergy[- ]tested` · `clinically (?:proven|shown)[^.]{0,60}` | one label each |
| claims | `colloidal oatmeal(?:,? a skin protectant)?` | colloidal oatmeal |
| claims | `kills 99\.9% of (?:germs|bacteria)[^.]{0,40}` | kills 99.9% |
| claims | `cruelty[- ]free` · `\bvegan\b` | one label each |
| seals | `NEA Seal of Acceptance` · `National Eczema Association(?: Seal(?: of Acceptance)?)?` | nea seal |
| seals | `ADA Seal(?: of Acceptance)?` · `American Dental Association(?: Seal(?: of Acceptance)?| Accepted)` | ada seal |
| seals | `Leaping Bunny` · `EWG Verified` · `USDA Organic` | one label each |

`Fragrance free, paraben free, phthalate free, dye free and alcohol free` gives five items.

### 5.5 description (string)

| priority | kind | pattern |
|---|---|---|
| 1 | jsonld | `description` (HTML inside stripped) |
| 2 | meta | `og:description` |
| 3 | meta | `description` |
| 4 | selector | first `main p`, then `p`, of 60+ characters, not inside the ingredients block |

Value = cleaned text, cut at 3000 characters on a word boundary. Quote = same text.
Not compared by `compare.py` today (§12, gap 6).

## 6. Missing, blocked and non-product pages

A snapshot that is not a readable product page gets **no** extraction row, only a log row.
`run.py` and `truth.py` use the newest extraction per page: an empty row would hide the last good
extraction and raise false `missing` conflicts. With no row, the last good extraction stays in use.

Checked in this order:

| status | When |
|---|---|
| `no_sku` | no SKU for the page (no `page_sku.csv` row, no prior row), or more than one |
| `empty` | `html` empty, or visible text under 200 characters and no JSON-LD Product |
| `blocked` | title or first 2000 visible characters contain a `block` phrase: access denied, pardon our interruption, robot or human, are you a robot, captcha, request blocked, just a moment, attention required, verify you are human, enable javascript and cookies, 403 forbidden, 404 not found, page not found, this product is no longer available |
| `not_product` | none of `ingredients`, `free_from`, `claims`, `seals` found (name or description alone is not enough) |
| `ok` | otherwise; missing fields are left out of `fields` |

## 7. Idempotency

- One row per snapshot: `id = snapshot_id`. A page has exactly one SKU (§6).
- No run time, randomness, network or dict order reaches the output: `created_at` = `fetched_at`,
  field order fixed, lists in document order, rows sorted by `id`.
- Same input files with `use_llm` = no: byte-identical `extraction.csv` and `extraction_log.csv`.
- With a prior file, snapshots that already have a row are kept (`status=kept`), so manual or
  reviewed rows are never overwritten. `reparse` = yes replaces them, same `id`.
- Same `content_hash` gives the same `fields`.

## 8. Error handling

| Case | Behaviour |
|---|---|
| Missing file / column, duplicate snapshot id, unknown page id, bad rules row | `exit_code` 2, step 6 lists the errors, no output files |
| Exception while parsing one snapshot | that snapshot `failed` with the error; prior row (if any) copied; others continue; `exit_code` 1 |
| Malformed JSON-LD block | block ignored, warning `bad_jsonld` |
| `content_hash` ≠ sha256(html) | warning `hash_mismatch`; parsed anyway |
| Prior row with invalid JSON | copied unchanged, warning; not re-parsed unless `reparse` = yes |
| Sandbox time or memory limit hit | Glean step fails; split the snapshot file smaller (§1) and rerun with the prior file |

## 9. Optional LLM fill-in (`use_llm`, default no)

With `use_llm` = no, step 4 is skipped and no LLM sees page text. The run is deterministic.

With `use_llm` = yes:
1. **Branch**: skip when `llm_queue.csv` is empty.
2. **Think** (sub-agent, one call per queue row, capped at 25 rows per run): input = `missing_fields`
   and `visible_text` (cut to 30,000 characters). Instruction: for each missing field, return JSON
   `{field: {"value": ..., "quote": ...}}` where `quote` is copied exactly from the text; return
   nothing for a field the page does not state. Never invent values.
3. **Analyze data** (Python, same script, `--merge-llm`): keeps an item only when its `quote` is a
   verbatim substring of the visible text (warning `llm_quote_not_found` otherwise), never overrides a
   parser value, sets `method = parser+llm`, and writes the final `extraction.csv`.

LLM output is not deterministic. Rows it touched are marked by `method`, so a reviewer can find them.

## 10. Tests

Fixtures in `docs/agents/fixtures/extraction/<case>/{in,expected}/` (CSV only). Each case is run
twice: by the script locally (`python extraction_parse.py --in in/ --out out/`, compared to
`expected/` with a diff), and once in Glean through the agent, downloading and diffing the output.
The local run is the regression check; the Glean run checks the wiring.

1. **Pilot golden**: the three pilot fixture pages (Rite Aid CeraVe, Hannaford and Kenvue Pro Aveeno);
   exact `extraction.csv`.
2. **Pilot parity**: `compare(truth, parsed)` gives the same (field, verdict) list as
   `compare(truth, manual_extractions.json)` for each pilot page (run in the backend test suite).
3. **Quote invariant**: every `quote` is a substring of that snapshot's visible text or JSON-LD.
4. **Idempotency**: two runs, byte-identical. Shuffled input rows: same output.
5. **Prior rows**: run 1 output as prior gives all `kept`, identical file; `reparse` keeps ids.
6. **JSON-LD first**: JSON-LD name/description beat a different `h1`.
7. **Drug Facts**: actives (no %) then inactives.
8. **Ingredients edge cases**: commas in parentheses, trailing period, duplicates, `Ingredients:`
   label, rejected list.
9. **Free-from conjunction**: the Hannaford sentence gives five items in order.
10. **Name is not a claim**: "Fragrance Free" only in `h1` gives no `free_from`.
11. **Negation**: "not fragrance free" gives no item.
12. **Entities and mojibake**: `&amp;`, `Â®`, double-escaped text.
13. **Blocked / empty / not_product / no_sku**: no row, right status, `exit_code` 0.
14. **Parse error** in one snapshot: `failed`, others written, `exit_code` 1.
15. **Missing `page.csv`**: `exit_code` 2, no output.
16. **Rules change**: adding a `match` row for a new claim adds it, and `rules_version` changes.
17. **LLM off**: `use_llm` = no gives the same output as the local script.
18. **LLM merge** (fixture LLM answers in a CSV): fills only empty fields; non-verbatim quote dropped.
19. **Hand-off**: output passes the conflict agent's `extraction.csv` validation.

## 11. Build steps

1. `docs/agents/glean/extraction_parse.py`: one stdlib-only script, about 500 lines. Modes: parse
   (default) and `--merge-llm`. Ported from `data_collect/common.py`, `build.py` and `claims.py`.
2. `docs/agents/glean/extraction_rules.csv`: starter rules from §5.
3. Fixtures and expected outputs from §10.
4. Glean agent from §1: input fields, Analyze data step with the script pasted in (or attached as a
   file it reads), Branch, optional Think sub-agent, Respond.
5. Optional, later: the backend imports the same script for `HtmlExtractor` in `extract.py`, so the
   app and the Glean agent produce the same rows.

## 12. Gaps found in the current code

1. **No HTML extractor in the backend.** Only `ManualExtractor` (JSON keyed by URL) and an
   `LLMExtractor` TODO.
2. **Parser lives only in `data_collect/`** and uses `lxml`; nothing shares it.
3. **No page→SKU link in the schema.** `seed.py` binds them in code; data_collect uses
   `row_product_match.csv`. Proposal: `page.sku_id`, or a `page_sku` table for multi-SKU pages.
4. **No fetch status on `snapshot`.** No HTTP status, final URL or error columns; blocked pages can
   only be detected from content (§6).
5. **No provenance or uniqueness on `extraction`.** No `method` / `rules_version` column; no unique
   `(snapshot_id, sku_id)`, so `save_extraction` adds a duplicate on every rerun.
6. **`description` is extracted but never compared.** `COMPARED_FIELDS` has five fields.
7. **data_collect writes canonical labels as values** and joins quotes with ` | `, which hides
   wording drift and breaks the verbatim-quote rule.
8. **Stale `backend/app/collector/`**: only `__pycache__`, no sources.
9. **No tests for `extract.py`, `fetch_page` or `store_snapshot`.**
10. **`data_collect` also writes `raw_bullets`**; nothing reads it. This agent does not.

Open:
- A page that sells several SKUs would need one row per (snapshot, SKU); `id` could then not be
  `snapshot_id`.
- Glean's upload limit and the Analyze data sandbox's exact time limit and package list are not
  documented; the first Glean test run with the full Aveeno/Listerine chunk sets the batch size.
