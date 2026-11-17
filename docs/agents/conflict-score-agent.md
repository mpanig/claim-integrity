# Conflict & Drift Score Agent — spec (Glean, CSV in/out)

Status: draft v3, 2026-11-17. Logic taken from claim-integrity `main` (`compare.py`, `truth.py`,
`run.py`, `scoring.py`). No code changed.

The agent runs in **Glean Agent Builder**. Flow:

1. Export the input tables from Postgres to CSV (§1).
2. Upload them to the Glean agent. It returns `conflict.csv`, `score_snapshot.csv`, `rollup.csv`
   and `run_log.csv`. Glean touches no database and no app API.
3. Load `conflict.csv` and `score_snapshot.csv` into the Postgres tables of the same name (§8).
   Their columns match the table columns exactly. Loading the same files twice changes nothing.

## 0. How it maps to Glean

| Glean piece | Used for |
|---|---|
| Input form, file upload enabled | the input CSVs (§1) and the run timestamp |
| **Analyze data** step | every table operation (filter, join, group, compute, write CSV). Runs Python in Glean's sandbox, 500 MiB memory, no network; results over 1,000 rows are saved as a file |
| Respond step | short summary plus the four output files |

Glean writes the Python behind each Analyze data step from the step's instructions. Write each step
below into its step's instructions as given (column names, order, formulas), so the generated code
stays the same between runs.

**Python only where needed.** Two steps need exact string logic that plain instructions don't
guarantee. They carry a fixed code block in the step's instructions, marked **[code]**:
- step 3 (normalisation keys and rule matching)
- step 4 (reconcile with prior conflicts)

Every other step is plain filter / join / group / compute. No step calls an LLM for a decision.
Same inputs give the same rows.

Glean keeps no state between runs. Always export fresh from Postgres right before a run (after the
last load), so prior conflicts and their statuses (dismissed, fixed) are in the input.

## 1. Inputs

UTF-8 CSV, header row, column names = DB column names. JSON columns hold one JSON value per cell.
Timestamps are ISO 8601. Empty cell = null. Drop `snapshot.html` before upload (size).

| File | Required | Columns used |
|---|---|---|
| `sku.csv` | yes | `id, organisation_id, brand_id, name` |
| `brand.csv` | yes | `id, organisation_id, name` |
| `page.csv` | yes | `id, url, retailer, weight` (empty weight = 1.0) |
| `snapshot.csv` | yes | `id, page_id, fetched_at` |
| `extraction.csv` | yes | `id, snapshot_id, sku_id, fields` (JSON `{field: {value, quote}}`) |
| `approved_claim.csv` | yes, may be empty | `id, sku_id, field, value` (JSON) |
| `conflict.csv` | no (first run) | prior conflicts, all columns in §5 |
| `score_snapshot.csv` | no | prior snapshots, all columns in §6 |
| `organisation.csv`, `variant.csv`, `inferred_truth.csv` | no | not used by the rules; inferred truth is recomputed |

Reference tables (part of the agent, uploaded as agent knowledge files, editable without code):

| File | Columns | Content (current values) |
|---|---|---|
| `severity.csv` | `verdict, severity` | contradiction 10, risky 9, outdated 6, weaker 4, missing 3, drift 1 |
| `ingredient_renames.csv` | `from, to` | aqua/water/eau, water/aqua/eau, aqua, purified water → water; ceramide 3 → ceramide np; ceramide 6-ii, ceramide 6 ii → ceramide ap; ceramide 1 → ceramide eop; hyaluronic acid → sodium hyaluronate |
| `seal_aliases.csv` | `from, to` | national eczema association seal of acceptance, national eczema association seal, nea seal → nea seal of acceptance |
| `free_from_markers.csv` | `claim_key, marker` | fragrance: fragrance, parfum; paraben: paraben |

Run parameter: `run_at` (timestamp). All new timestamps use it, never the clock, so re-runs match.

## 2. Step 1 — validate (Analyze data)

1. Check each required file exists and has its columns. Check `id` is unique in every table.
2. Check joins resolve: `sku.brand_id → brand.id`, `snapshot.page_id → page.id`,
   `extraction.snapshot_id → snapshot.id`, `extraction.sku_id → sku.id`, `approved_claim.sku_id → sku.id`.
3. Any failure: stop. Respond with the list of problems. Write no output.

## 3. Step 2 — latest extraction and truth (Analyze data)

**Latest extraction per (sku, page):**
join `extraction → snapshot (snapshot_id) → page (page_id)`; sort by `fetched_at` desc, then
`extraction.id` desc; keep the first row per (`sku_id`, `page_id`).
Expand `fields` into columns `name, ingredients, free_from, claims, seals` (the `value` of each).

**Truth per SKU** (5 compared fields: `name, ingredients, free_from, claims, seals`):

| Case | Test | Truth | `truth_source` |
|---|---|---|---|
| Approved | SKU has an `approved_claim` row with `field ≠ name` | per field, `value` of the row with the highest `id` | `approved` |
| Inferred | no such row, has extractions | per field, majority (below) | `inferred` (UI badge: **Unverified**) |
| None | no extractions | none, no conflicts | — |

Majority, per field: group the SKU's latest-extraction rows by the field's **match key** (step 3),
ignoring empty values. Sum `page.weight` per group. Winner = largest weight; tie: more pages; tie:
lowest `page_id`. Truth value = the value from the highest-weight page in the winning group.

Name: an approved `name` always wins; if none, `sku.name`.

## 4. Step 3 — compare **[code]** (Analyze data)

Match keys (how two values are judged "the same"):

| Field | Match key |
|---|---|
| ingredient item | lowercase, trim, collapse spaces, remove spaces around `/`, strip trailing `.`, then `ingredient_renames` |
| ingredients (list) | set of item keys |
| free_from item | lowercase words `[a-z0-9]+`, drop `free, of, from, added, no, without`, join with space, drop final `s` unless it ends in `ss` |
| claims item | lowercase alphanumerics only, joined |
| seals item | lowercase words joined with space, then `seal_aliases` |
| name | lowercase words joined with space |

Rules, for each (SKU, page) row against the SKU's truth. One output row per finding.

| # | Verdict | Field | Condition | `page_value` | `truth_value` |
|---|---|---|---|---|---|
| R1 | missing | any of 5 | truth not empty, page empty | null | truth |
| R2 | drift | name | both present, name keys differ | page name | truth name |
| R3 | outdated | ingredients | both present, key sets differ | `{value, not_in_truth, not_on_page}` | truth list |
| R4 | drift | ingredients | key sets equal, but key order differs or basic (pre-rename) names differ | page list | truth list |
| R5 | risky | free_from, claims, seals | page item key not in truth keys | page item | null |
| R6 | weaker | free_from, claims, seals | truth item key not in page keys (page field not empty) | null | truth item |
| R7 | drift | free_from, claims, seals | same key, wording differs after lowercase + collapse spaces | page item | truth item |
| R8 | contradiction | free_from | page free_from item's key is in `free_from_markers` and a page ingredient key contains a marker | `{claim, ingredients: [hits]}` | null |

`severity` = lookup in `severity.csv`. R8 uses only the page's own data, so it fires on both truth paths.

Fixed code for this step: port `compare()` and its helpers from `backend/app/pipeline/compare.py`
(~150 lines, standard library only), reading the three alias/marker tables from the CSVs instead of
the Python dicts. Paste it into the step's instructions with "run this code exactly".

## 5. Step 4 — reconcile with prior `conflict.csv` **[code]** (Analyze data)

Key: `sku_id, page_id, field, verdict, page_value, truth_value` (JSON values with sorted keys, no spaces).

| Prior status | Finding found again | Finding gone |
|---|---|---|
| no prior row | add row: `status=open`, `detected_at=run_at` | — |
| open, accepted | keep; set `truth_source` | `status=verified`, `status_changed_at=run_at` |
| fixed | `status=open`, `status_changed_at=run_at` | `status=verified`, `status_changed_at=run_at` |
| dismissed | keep, never re-raised | keep |
| verified | keep as history; add a new open row | keep |

Never delete rows. Write only rows that are new or changed in this run. New rows have an empty
`id`; Postgres assigns it on load. Order: existing rows by `id`, then new rows by
`sku_id, page_id, severity desc, field, key`. Code: port the loop in `run_for_sku`
(`backend/app/pipeline/run.py`, ~30 lines).

Output `conflict.csv`: exactly the `conflict` table columns, in table order:
`id, organisation_id, sku_id, page_id, field, page_value, truth_value, verdict, severity, status,
detected_at, status_changed_at, owner, due_date, dismiss_reason, truth_source`
(`page_value`, `truth_value` as JSON text; `owner, due_date, dismiss_reason` copied from the prior
row, empty for new rows.)

## 6. Step 5 — drift score and roll-ups (Analyze data)

Unresolved = `status` in (open, accepted, fixed).

| Quantity | Formula |
|---|---|
| `weighted_severity` | Σ `severity × page.weight` over the SKU's unresolved conflicts |
| `page_weight` | Σ `page.weight` over distinct pages with an extraction for the SKU |
| `worst` | `10 × 5 × page_weight` (max severity × compared fields × weight) |
| `score` (consistency) | `max(0, round(100 × (1 − weighted_severity / worst)))`; empty if `page_weight = 0` |
| `drift_score` | `100 − score` (0 = no drift, 100 = worst) |
| `unresolved` | count of unresolved conflicts |
| `by_verdict` | JSON count of unresolved per verdict (all 6 keys) |
| `by_status` | JSON count of all conflicts per status (all 5 keys) |
| `mean_days_to_fix` | mean of `(status_changed_at − detected_at)` in days, 1 decimal, over verified conflicts; empty if none |

Roll-ups: sum `weighted_severity` and `page_weight` first, then apply the same `score` formula.
Never average scores.

| `scope` | Group by | `page_weight` |
|---|---|---|
| `sku` | sku | as above |
| `brand` | `sku.brand_id` | sum of its SKUs |
| `organisation` | `sku.organisation_id` | sum of its SKUs |
| `page` | `conflict.page_id` | `page.weight × number of SKUs extracted on that page` |

Output `score_snapshot.csv`: `sku` scope only, one new row per SKU, exactly the `score_snapshot`
table columns in table order:
`id, organisation_id, brand_id, sku_id, taken_at, score, weighted_severity, page_weight, unresolved,
by_verdict, by_status, mean_days_to_fix, is_demo`
with `id` empty, `taken_at = run_at`, `is_demo = false`. `score` is the consistency value the table
stores; the app shows `drift = 100 − score`. Skip a SKU's row when its last prior snapshot has the
same score, unresolved, by_verdict, by_status and the same date.

Output `rollup.csv` (report only, not loaded; the app computes roll-ups itself):
`scope, organisation_id, brand_id, sku_id, page_id, score, drift_score, weighted_severity,
page_weight, unresolved, truth_source`, one row per `sku`, `brand`, `organisation` and `page`.

## 7. Step 6 — run log and respond

`run_log.csv`: `sku_id, status (ok | failed | skipped), truth_source, new, reopened, resolved,
unresolved, drift_score, error`, one row per SKU.

Respond with: totals (new, reopened, resolved, overall drift), the 5 highest `severity × weight`
open conflicts, and the four files.

## 8. Load into Postgres

Run after a successful agent run, in one transaction. Load each CSV into a temp staging table,
then merge. JSON columns cast with `::jsonb`, enums with `::verdict` / `::conflict_status`.

```sql
BEGIN;
CREATE TEMP TABLE conflict_in (LIKE conflict INCLUDING DEFAULTS) ON COMMIT DROP;
ALTER TABLE conflict_in ALTER COLUMN id DROP NOT NULL;
\copy conflict_in FROM 'conflict.csv' WITH (FORMAT csv, HEADER true)

-- existing rows: update status fields by id
UPDATE conflict c SET status = i.status, status_changed_at = i.status_changed_at,
       truth_source = i.truth_source
FROM conflict_in i WHERE i.id IS NOT NULL AND c.id = i.id;

-- new rows: insert unless an active conflict with the same natural key exists
INSERT INTO conflict (organisation_id, sku_id, page_id, field, page_value, truth_value, verdict,
                      severity, status, detected_at, truth_source)
SELECT organisation_id, sku_id, page_id, field, page_value, truth_value, verdict,
       severity, status, detected_at, truth_source
FROM conflict_in i
WHERE i.id IS NULL AND NOT EXISTS (
  SELECT 1 FROM conflict c
  WHERE c.sku_id = i.sku_id AND c.page_id = i.page_id AND c.field = i.field
    AND c.verdict = i.verdict AND c.status <> 'verified'
    AND c.page_value IS NOT DISTINCT FROM i.page_value
    AND c.truth_value IS NOT DISTINCT FROM i.truth_value);

CREATE TEMP TABLE snap_in (LIKE score_snapshot INCLUDING DEFAULTS) ON COMMIT DROP;
ALTER TABLE snap_in ALTER COLUMN id DROP NOT NULL;
\copy snap_in FROM 'score_snapshot.csv' WITH (FORMAT csv, HEADER true)

-- natural key (sku_id, taken_at): a rerun of the same load inserts nothing
INSERT INTO score_snapshot (organisation_id, brand_id, sku_id, taken_at, score, weighted_severity,
       page_weight, unresolved, by_verdict, by_status, mean_days_to_fix, is_demo)
SELECT organisation_id, brand_id, sku_id, taken_at, score, weighted_severity,
       page_weight, unresolved, by_verdict, by_status, mean_days_to_fix, is_demo
FROM snap_in i
WHERE NOT EXISTS (SELECT 1 FROM score_snapshot s WHERE s.sku_id = i.sku_id AND s.taken_at = i.taken_at);
COMMIT;
```

Rules:
- **Natural keys.** `conflict`: `(sku_id, page_id, field, verdict, page_value, truth_value)` among
  non-verified rows (same key the app uses). `score_snapshot`: `(sku_id, taken_at)`.
- **Idempotent.** Loading the same files twice: updates write the same values, inserts are skipped.
- **Stale export guard.** Before the merge, abort if any `conflict` row with an `id` in the CSV has a
  `status_changed_at` in Postgres later than the export time (someone changed it in the app meanwhile).
- TablePlus: import each CSV into the staging table, then run the SQL from the `UPDATE` on.
- Not written by the load: audit events, alerts, `sku.last_checked_at`. If needed later, add
  inserts for `audit_event` from the status changes.

## 9. Error handling

| Case | Behaviour |
|---|---|
| Missing file or column, broken join | stop at step 1, list problems, no output |
| Invalid JSON in one SKU's `fields` or `value` | that SKU `failed` in `run_log.csv`, its prior conflicts copied unchanged, others continue |
| Extraction missing a field | treated as empty (R1 if truth has it) |
| SKU with no pages | `skipped`, `sku` snapshot row with empty score |
| Unknown field in `approved_claim` | ignored |
| Input too large for the sandbox | split by brand (`sku.brand_id`) and run once per brand; roll-ups for `organisation` then need one extra run on the `sku` rows |

## 10. Tests (CSV fixtures, row-by-row compare)

Each case is a folder `tests/agent_csv/<case>/` with `in/` (inputs + `run_at.txt`) and `expected/`
(`conflict.csv`, `score_snapshot.csv`, `run_log.csv`). Run the agent on `in/`, then compare each
output with `expected/` row by row: existing rows matched by `id`, new rows (empty `id`) by
natural key; JSON cells compared as parsed JSON.
Pass = no row added, missing or changed.

| # | Case | Checks |
|---|---|---|
| 1 | `pilot` | CeraVe + Aveeno pilot export, full expected output |
| 2 | `rules_each` | one page per rule R1–R8, one conflict each with the right severity |
| 3 | `renames` | old INCI names only: drift, not outdated |
| 4 | `idempotent` | run, load, re-export, run again with same `run_at`: 0 new / reopened / resolved, empty `conflict.csv`, no new snapshot row |
| 5 | `score_math` | exact weighted_severity, page_weight, score, drift |
| 6 | `rollup` | brand drift = formula on sums, not mean of SKU drifts |
| 7 | `page_weight` | weight 2 page doubles its weighted severity |
| 8 | `statuses` | dismissed stays; fixed+found reopens; verified+found adds new id |
| 9 | `truth_flip` | adding approved claims switches `truth_source` to approved |
| 10 | `majority_tie` | tie broken by page count, then lowest page_id; stable after row shuffle |
| 11 | `bad_json` | one SKU failed, others written |
| 12 | `missing_file` | stops at step 1, no output |
| 13 | `parity` | same data through the app's `run_for_sku` gives the same conflicts and scores |
| 14 | `load_twice` | load SQL run twice on a test DB: row counts unchanged after the second run |
| 15 | `columns` | output CSV headers equal the `conflict` / `score_snapshot` table columns |

Expected files for 1 and 13 come from the current app (DB version) on the same data.

## 11. Open

- `variant` is unused: truth and conflicts are per SKU, not per market or size.
- Free-from contradiction knows only fragrance and paraben; add rows to `free_from_markers.csv`.
- Confirm Glean upload limits for the export size on your plan.
