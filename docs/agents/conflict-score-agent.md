# Conflict & Drift Score Agent — spec (Glean, CSV in/out)

Status: draft v4, 2026-11-17. Logic taken from claim-integrity `main` (`compare.py`, `truth.py`,
`run.py`, `scoring.py`). No code changed.

The agent runs in **Glean Agent Builder**. It takes CSV files in and gives CSV files out. Every CSV,
in and out, has exactly the structure of its Postgres table: same file name as the table, same
column names, same column order, same value formats. No extra files, no extra columns.

Flow:
1. Export the input tables from Postgres to CSV (§1).
2. Upload them to the Glean agent. It returns `conflict.csv` and `score_snapshot.csv` (§2).
3. Load both into Postgres (§9). Loading the same files twice changes nothing.

## 0. How it maps to Glean

| Glean piece | Used for |
|---|---|
| Input form, file upload enabled | the input CSVs (§1) and `run_at` (timestamp) |
| **Analyze data** step | every table operation (filter, join, group, compute, write CSV). Runs Python in Glean's sandbox, 500 MiB memory, no network; results over 1,000 rows are saved as a file |
| Respond step | the two output CSVs plus a short text summary |

Glean writes the Python behind each Analyze data step from the step's instructions. Put each step
below into its step's instructions as written (column names, order, formulas), so the generated code
stays the same between runs.

**Python only where needed.** Two steps need exact string logic that plain instructions don't
guarantee. They carry a fixed code block in the step's instructions, marked **[code]**: step 3
(match keys and rules) and step 4 (reconcile). Every other step is plain filter / join / group /
compute. No step calls an LLM for a decision. Same inputs + same `run_at` = same rows.

Glean keeps no state between runs. Export fresh from Postgres right before each run, after the last load.

## 1. CSV format (all files)

- UTF-8, comma-separated, double-quote escaping, one header row = the table's column names in table order.
- Export with `\copy (SELECT * FROM <table> ORDER BY id) TO '<table>.csv' WITH (FORMAT csv, HEADER true)`,
  so column order is the table's own.
- null = empty cell. `jsonb` = JSON text in the cell. `timestamptz` = ISO 8601 with offset
  (`2026-11-17 09:00:00+00`). `date` = `YYYY-MM-DD`. `boolean` = `true` / `false`. Enums = their text value.
- Check the live layout before building the agent:
  `SELECT table_name, string_agg(column_name, ', ' ORDER BY ordinal_position) FROM information_schema.columns
   WHERE table_schema = 'public' GROUP BY 1;` The lists below are from migrations up to 0018.

## 2. Files and columns

### Inputs

| File | Required | Columns, in table order (columns the agent reads in **bold**) |
|---|---|---|
| `organisation.csv` | yes | **id**, name, created_at |
| `brand.csv` | yes | **id**, **organisation_id**, name, aliases, positioning |
| `sku.csv` | yes | **id**, **organisation_id**, **brand_id**, gtin, **name**, line, last_checked_at, aliases |
| `variant.csv` | yes, may be empty | id, organisation_id, sku_id, market, size, formula_version, valid_from, valid_to (not used by the rules) |
| `page.csv` | yes | **id**, organisation_id, url, source_type, **retailer**, country, **weight** |
| `snapshot.csv` | yes | **id**, organisation_id, **page_id**, **fetched_at**, content_hash, html |
| `extraction.csv` | yes | **id**, organisation_id, **snapshot_id**, **sku_id**, **fields**, created_at |
| `approved_claim.csv` | yes, may be empty | **id**, organisation_id, **sku_id**, **field**, **value**, evidence_url, approved_by, created_at |
| `inferred_truth.csv` | yes, may be empty | id, sku_id, fields, agreement, method, sources, source_hash, updated_at (not used; truth is recomputed) |
| `conflict.csv` | yes, may be empty | same columns as the output below (prior conflicts) |
| `score_snapshot.csv` | yes, may be empty | same columns as the output below (prior snapshots) |

`snapshot.html` can be large. If uploads hit Glean's limit, export it as an empty string
(`SELECT id, organisation_id, page_id, fetched_at, content_hash, '' AS html ...`): same columns, the agent never reads it.

`extraction.fields` is `{field: {"value": ..., "quote": "..."}}` for the 5 compared fields.

### Outputs

**`conflict.csv`**: the full `conflict` table after the run (all prior rows, updated, plus new rows), ordered by `id`.

| Column | Type | Set by the agent |
|---|---|---|
| id | integer | prior id; new rows: max(prior id, 0) + 1, +2, … (§6) |
| organisation_id | integer | `sku.organisation_id` |
| sku_id | integer | SKU |
| page_id | integer | page |
| field | varchar(50) | `name`, `ingredients`, `free_from`, `claims` or `seals` |
| page_value | jsonb | §5 |
| truth_value | jsonb | §5 |
| verdict | enum verdict | §5 |
| severity | integer | §5 |
| status | enum conflict_status | §6 |
| detected_at | timestamptz | prior value; new rows: `run_at` |
| status_changed_at | timestamptz | `run_at` when status changes, else prior value |
| owner | varchar(200) | prior value; new rows empty |
| due_date | date | prior value; new rows empty |
| dismiss_reason | text | prior value; new rows empty |
| truth_source | varchar(20) | `approved` or `inferred` (§4) |

**`score_snapshot.csv`**: the full `score_snapshot` table (all prior rows unchanged, plus one new row
per SKU), ordered by `id`.

| Column | Type | Set by the agent |
|---|---|---|
| id | integer | new rows: max(prior id, 0) + 1, +2, … in `sku_id` order |
| organisation_id | integer | `sku.organisation_id` |
| brand_id | integer | `sku.brand_id` |
| sku_id | integer | SKU |
| taken_at | timestamptz | `run_at` |
| score | integer | §7 (consistency; the app shows drift = 100 − score) |
| weighted_severity | double | §7 |
| page_weight | double | §7 |
| unresolved | integer | §7 |
| by_verdict | jsonb | §7 |
| by_status | jsonb | §7 |
| mean_days_to_fix | double | §7 |
| is_demo | boolean | `false` |

No new `score_snapshot` row for a SKU when its last prior row has the same score, unresolved,
by_verdict, by_status and the same `taken_at` date.

Brand, organisation and page roll-ups are not output: they are not tables. The app computes them
from these rows (§7). The run summary (new, reopened, resolved per SKU, errors) is the Respond
step's text, not a file.

## 3. Step 1 — validate (Analyze data)

1. Every required file is present and its header equals the column list in §2, in order.
2. `id` is unique in every file.
3. Joins resolve: `sku.brand_id → brand.id`, `snapshot.page_id → page.id`,
   `extraction.snapshot_id → snapshot.id`, `extraction.sku_id → sku.id`, `approved_claim.sku_id → sku.id`,
   `conflict.sku_id → sku.id`, `conflict.page_id → page.id`.
4. Any failure: stop. Respond with the list of problems. Write no output.

## 4. Step 2 — latest extraction and truth (Analyze data)

**Latest extraction per (sku, page):** join `extraction → snapshot (snapshot_id) → page (page_id)`;
sort by `fetched_at` desc, then `extraction.id` desc; keep the first row per (`sku_id`, `page_id`).
Read the `value` of `name, ingredients, free_from, claims, seals` from `fields`.

**Truth per SKU** (5 compared fields):

| Case | Test | Truth | `truth_source` |
|---|---|---|---|
| Approved | SKU has an `approved_claim` row with `field ≠ name` | per field, `value` of the row with the highest `id` | `approved` |
| Inferred | no such row, has extractions | per field, majority (below) | `inferred` (UI badge: **Unverified**) |
| None | no extractions | none, no conflicts | — |

Majority, per field: group the SKU's latest-extraction rows by the field's match key (§5), ignoring
empty values. Sum `page.weight` per group. Winner = largest weight; tie: more pages; tie: lowest
`page_id`. Truth value = the value from the highest-weight page in the winning group.

Name: an approved `name` always wins; else `sku.name`.

## 5. Step 3 — compare **[code]** (Analyze data)

Fixed lists (written in the step's instructions):

| List | Values |
|---|---|
| severity | contradiction 10, risky 9, outdated 6, weaker 4, missing 3, drift 1 |
| ingredient renames | aqua/water/eau, water/aqua/eau, aqua, purified water → water; ceramide 3 → ceramide np; ceramide 6-ii, ceramide 6 ii → ceramide ap; ceramide 1 → ceramide eop; hyaluronic acid → sodium hyaluronate |
| seal aliases | national eczema association seal of acceptance, national eczema association seal, nea seal → nea seal of acceptance |
| free-from markers | fragrance: fragrance, parfum; paraben: paraben |

Match keys (when two values count as "the same"):

| Field | Match key |
|---|---|
| ingredient item | lowercase, trim, collapse spaces, remove spaces around `/`, strip trailing `.`, then renames |
| ingredients (list) | set of item keys |
| free_from item | lowercase words `[a-z0-9]+`, drop `free, of, from, added, no, without`, join with space, drop final `s` unless it ends in `ss` |
| claims item | lowercase alphanumerics only, joined |
| seals item | lowercase words joined with space, then seal aliases |
| name | lowercase words joined with space |

Rules, for each (SKU, page) against the SKU's truth. One finding per match.

| # | Verdict | Field | Condition | `page_value` | `truth_value` |
|---|---|---|---|---|---|
| R1 | missing | any of 5 | truth not empty, page empty | null | truth |
| R2 | drift | name | both present, name keys differ | page name | truth name |
| R3 | outdated | ingredients | both present, key sets differ | `{value, not_in_truth, not_on_page}` | truth list |
| R4 | drift | ingredients | key sets equal, but key order or pre-rename names differ | page list | truth list |
| R5 | risky | free_from, claims, seals | page item key not in truth keys | page item | null |
| R6 | weaker | free_from, claims, seals | truth item key not in page keys (page field not empty) | null | truth item |
| R7 | drift | free_from, claims, seals | same key, wording differs after lowercase + collapse spaces | page item | truth item |
| R8 | contradiction | free_from | page free_from item key is a marker key and a page ingredient key contains one of its markers | `{claim, ingredients: [hits]}` | null |

R8 uses only the page's own data, so it fires on both truth paths.

Code: port `compare()` and helpers from `backend/app/pipeline/compare.py` (~150 lines, standard
library only). Paste into the step's instructions with "run this code exactly".

## 6. Step 4 — reconcile with prior conflicts **[code]** (Analyze data)

Key: `sku_id, page_id, field, verdict, page_value, truth_value` (JSON with sorted keys).

| Prior status | Finding found again | Finding gone |
|---|---|---|
| no prior row | new row: `status=open`, `detected_at=run_at` | — |
| open, accepted | keep; set `truth_source` | `status=verified`, `status_changed_at=run_at` |
| fixed | `status=open`, `status_changed_at=run_at` | `status=verified`, `status_changed_at=run_at` |
| dismissed | keep, never re-raised | keep |
| verified | keep as history; add a new open row | keep |

Never drop a row. Rows of SKUs with no extractions are copied unchanged. New ids are assigned in
order `sku_id, page_id, severity desc, field, key`, so the same input always gives the same ids.
Code: port the loop in `run_for_sku` (`backend/app/pipeline/run.py`, ~30 lines).

## 7. Step 5 — drift score (Analyze data)

Unresolved = `status` in (open, accepted, fixed).

| Column / quantity | Formula |
|---|---|
| `weighted_severity` | Σ `severity × page.weight` over the SKU's unresolved conflicts |
| `page_weight` | Σ `page.weight` over distinct pages with an extraction for the SKU |
| worst | `10 × 5 × page_weight` (max severity × compared fields × weight) |
| `score` | `max(0, round(100 × (1 − weighted_severity / worst)))`; empty if `page_weight = 0` |
| drift (shown in app) | `100 − score` (0 = no drift, 100 = worst) |
| `unresolved` | count of unresolved conflicts |
| `by_verdict` | JSON count of unresolved per verdict, all 6 keys |
| `by_status` | JSON count of all conflicts per status, all 5 keys |
| `mean_days_to_fix` | mean of `(status_changed_at − detected_at)` in days, 1 decimal, over verified conflicts; empty if none |

Roll-ups (done by the app from `score_snapshot`, listed so results can be checked): sum
`weighted_severity` and `page_weight` over the SKUs of a brand or organisation, then apply the same
`score` formula. Never average scores.

## 8. Step 6 — respond

Return `conflict.csv` and `score_snapshot.csv`, plus a text summary: per SKU new / reopened /
resolved / unresolved / drift and `truth_source`; any SKU that failed and why; the 5 highest
`severity × weight` open conflicts.

## 9. Load into Postgres

Because the CSVs have the exact table layout, the load is an upsert on `id`, in one transaction.

```sql
BEGIN;
-- abort if the app wrote rows after the export (ids would clash)
--   SELECT max(id) FROM conflict;        must equal the max id in the input conflict.csv
--   SELECT max(id) FROM score_snapshot;  must equal the max id in the input score_snapshot.csv
CREATE TEMP TABLE conflict_in (LIKE conflict) ON COMMIT DROP;
\copy conflict_in FROM 'conflict.csv' WITH (FORMAT csv, HEADER true)
INSERT INTO conflict SELECT * FROM conflict_in
ON CONFLICT (id) DO UPDATE SET status = EXCLUDED.status,
  status_changed_at = EXCLUDED.status_changed_at, truth_source = EXCLUDED.truth_source;

CREATE TEMP TABLE snap_in (LIKE score_snapshot) ON COMMIT DROP;
\copy snap_in FROM 'score_snapshot.csv' WITH (FORMAT csv, HEADER true)
INSERT INTO score_snapshot SELECT * FROM snap_in ON CONFLICT (id) DO NOTHING;

SELECT setval(pg_get_serial_sequence('conflict', 'id'), (SELECT max(id) FROM conflict));
SELECT setval(pg_get_serial_sequence('score_snapshot', 'id'), (SELECT max(id) FROM score_snapshot));
COMMIT;
```

- Same files loaded twice: updates write the same values, inserts are skipped.
- Only `status`, `status_changed_at` and `truth_source` of existing conflicts change; owner, due date
  and notes set in the app are kept.
- `setval` moves the id sequences past the agent's ids, so the app's next insert does not clash.
- TablePlus works too: import each CSV into the staging table, then run the `INSERT … ON CONFLICT` lines.
- Not written: `audit_event`, `alert`, `sku.last_checked_at`.

## 10. Error handling

| Case | Behaviour |
|---|---|
| Missing file, wrong header, broken join | stop at step 1, list problems, no output |
| Invalid JSON in one SKU's `fields` or `value` | that SKU's rows copied unchanged and no snapshot for it; summary names it; others continue |
| Extraction missing a field | treated as empty (R1 if truth has it) |
| SKU with no pages | no conflicts; snapshot row with empty `score` |
| Unknown field in `approved_claim` | ignored |
| Input too large for the sandbox | export one brand at a time (all tables filtered to that brand's SKUs, pages and conflicts) |
| Max id check fails at load | do not load; re-export and re-run |

## 11. Tests (CSV fixtures, row-by-row compare)

Each case is a folder `tests/agent_csv/<case>/` with `in/` (input table CSVs + `run_at.txt`) and
`expected/` (`conflict.csv`, `score_snapshot.csv`). Run the agent on `in/`, compare each output with
`expected/` row by row on `id`, JSON cells compared as parsed JSON. Pass = headers identical and no
row added, missing or changed.

| # | Case | Checks |
|---|---|---|
| 1 | `pilot` | CeraVe + Aveeno pilot export, full expected output |
| 2 | `rules_each` | one page per rule R1–R8, one conflict each with the right severity |
| 3 | `renames` | old INCI names only: drift, not outdated |
| 4 | `idempotent` | output of run 1 used as `conflict.csv` / `score_snapshot.csv` input of run 2 (same `run_at`): identical output |
| 5 | `score_math` | exact weighted_severity, page_weight, score |
| 6 | `rollup` | brand score from summed rows equals formula, not mean of SKU scores |
| 7 | `page_weight` | weight 2 page doubles its weighted severity |
| 8 | `statuses` | dismissed stays; fixed+found reopens; verified+found adds a new id |
| 9 | `truth_flip` | adding approved claims switches `truth_source` to approved |
| 10 | `majority_tie` | tie broken by page count, then lowest page_id; stable after row shuffle |
| 11 | `bad_json` | one SKU unchanged, others written |
| 12 | `wrong_header` | stops at step 1, no output |
| 13 | `parity` | same data through the app's `run_for_sku` gives the same conflicts and scores |
| 14 | `load_twice` | load SQL run twice on a test DB: same row counts and values |
| 15 | `columns` | output headers equal `information_schema` column order for both tables |

Expected files for 1 and 13 come from the current app (DB version) on the same data.

## 12. Open

- `variant` is unused: truth and conflicts are per SKU, not per market or size.
- Free-from contradiction knows only fragrance and paraben; extend the marker list in step 3.
- Confirm Glean upload limits for the export size on your plan.
