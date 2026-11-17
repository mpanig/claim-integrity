# Conflict & Drift Score Agent — spec (CSV mode)

Status: draft v2, 2026-11-17. Based on `main` at `9969154`. No code changed.

The agent reads the exported tables as CSV files and writes `conflict.csv` and `score_snapshot.csv`.
It uses no database, no API and no LLM. Same input folder + same `--now` = byte-identical output.

It reuses the pure logic already in the repo: `app/pipeline/compare.py` (rules),
`app.pipeline.truth.majority` (inferred truth) and `app.services.scoring.score` (drift). Only the
I/O layer is new: CSV readers replace the SQLAlchemy queries in `run.py`, `truth.py`, `scoring.py`
and `trends.py`.

## 1. Run

```
uv run python -m app.agents.conflict_score \
    --in  data/export/            # input CSVs
    --out data/agent_out/         # conflict.csv, score_snapshot.csv, run_log.csv
    --now 2026-11-17T09:00:00Z    # run timestamp; default = current UTC time
    [--sku 12,14]                 # only these SKUs; default = all SKUs in sku.csv
```

One run processes each selected SKU in `sku.id` order. Exit code 0 when every SKU passed,
1 when any SKU failed (see §8), 2 when an input file or column is missing.

## 2. Input CSVs (`--in`)

UTF-8, header row, comma-separated, column names = DB column names. JSONB columns hold one JSON
value per cell (e.g. `["Non-comedogenic"]`). Timestamps are ISO 8601 with offset. Empty cell = null.

| File | Required | Columns read |
|---|---|---|
| `organisation.csv` | yes | `id`, `name` |
| `brand.csv` | yes | `id`, `organisation_id`, `name` |
| `sku.csv` | yes | `id`, `organisation_id`, `brand_id`, `name` |
| `page.csv` | yes | `id`, `url`, `retailer`, `weight` (empty = 1.0) |
| `snapshot.csv` | yes | `id`, `page_id`, `fetched_at` (`html` ignored, can be dropped) |
| `extraction.csv` | yes | `id`, `snapshot_id`, `sku_id`, `fields` (JSON `{field: {value, quote}}`) |
| `approved_claim.csv` | yes (may be empty) | `id`, `sku_id`, `field`, `value` (JSON) |
| `inferred_truth.csv` | no | ignored for computing; recomputed (§3) and only used to report a diff in `run_log.csv` |
| `variant.csv` | no | read and validated only; not used by rules (same as DB version) |
| `conflict.csv` | no | prior conflicts, needed to keep statuses (§5). Absent = first run, all new |
| `score_snapshot.csv` | no | prior snapshots; copied to output, new rows appended (§6) |

Validation before any SKU runs: required files exist, required columns present, ids unique,
every foreign key resolves (`sku.brand_id`, `snapshot.page_id`, `extraction.snapshot_id`,
`extraction.sku_id`, `approved_claim.sku_id`). Any failure: exit 2, no output written.

## 3. Truth per SKU

Latest extraction per page = newest `snapshot.fetched_at`, tie broken by highest `extraction.id`.

Compared fields (5): `name`, `ingredients`, `free_from`, `claims`, `seals`.

1. **Approved.** SKU has an `approved_claim` row for any field other than `name`. Truth = value of the
   highest `id` per field. `truth_source = approved`.
2. **Inferred.** No such row. Truth = `majority()` over the latest extraction per page: per field, the
   normalised value with the largest summed `page.weight` wins (ties: more pages, then first seen).
   `truth_source = inferred`; the UI shows the **Unverified** badge for these conflicts.
3. **None.** No extractions. No conflicts; snapshot with empty `score`.

An approved `name` overrides the inferred name; with no name at all, truth `name = sku.name`.

The DB version can let Claude choose among page values for inferred truth. CSV mode never does:
it is always `majority`, so the run is fully deterministic.

## 4. Conflict rules (unchanged, `compare.py`)

Normalisation: ingredients lowercased, spaces/slashes collapsed, trailing dot stripped, then
`INGREDIENT_RENAMES` (aqua→water, ceramide 3→ceramide np, …); free_from drops stopwords (free, of,
from, added, no, without) and singularises; seals use `SEAL_ALIASES`; claims keep alphanumerics;
name keeps words.

| Verdict | Severity | Fires when |
|---|---|---|
| `contradiction` | 10 | page `free_from` says fragrance/paraben-free but page INCI contains a matching ingredient |
| `risky` | 9 | list field (free_from, claims, seals): item on page, not in truth |
| `outdated` | 6 | ingredients: normalised set differs from truth |
| `weaker` | 4 | list field: truth item not on page |
| `missing` | 3 | truth has a value, page value empty |
| `drift` | 1 | same meaning, other wording (name, ingredient names/order, list item wording) |

## 5. Reconcile with prior `conflict.csv`

Conflict key: `(sku_id, page_id, field, verdict, json(page_value), json(truth_value))`, JSON with sorted keys.

| Prior status | Still found | Not found |
|---|---|---|
| none | new row, `status=open`, `detected_at=--now` | — |
| `open` / `accepted` | keep | `verified`, `status_changed_at=--now` |
| `fixed` | `open`, `status_changed_at=--now` | `verified`, `status_changed_at=--now` |
| `dismissed` | keep, never re-raised | keep |
| `verified` | keep as history; add a **new** open row | keep |

Rows for SKUs not in this run are copied through unchanged. Rows are never deleted.
New ids: `max(prior id, 0) + 1, +2, …`, assigned in order (sku_id, page_id, -severity, field, key).
Running twice on the same inputs (feeding run 1's `conflict.csv` back in) gives 0 new, 0 reopened,
0 resolved.

## 6. Drift score (unchanged formula)

```
weighted_severity = Σ severity × page.weight   over the SKU's conflicts with status open, accepted or fixed
page_weight       = Σ page.weight              over distinct pages with any extraction for the SKU
consistency       = max(0, round(100 × (1 − weighted_severity / (10 × 5 × page_weight))))
drift_score       = 100 − consistency          (0 = no drift, 100 = worst)
```

`page_weight = 0`: `score` and `drift_score` empty. `dismissed` and `verified` do not count.

Roll-ups re-apply the formula to summed `weighted_severity` and `page_weight`, never average scores:
- **Product:** the SKU row.
- **Brand / organisation:** sum across the SKUs' rows from this run.
- **Page:** sum over that page's conflicts; `page_weight` = page weight × SKUs extracted on that page.

## 7. Output CSVs (`--out`)

Written to a temp folder and renamed into `--out` only after every SKU finished, so a crash never
leaves half a file.

**`conflict.csv`**, all prior rows plus new ones, sorted by `id`:
`id, organisation_id, sku_id, page_id, field, page_value, truth_value, verdict, severity, status,
truth_source, detected_at, status_changed_at, owner, due_date, dismiss_reason`
(`page_value`, `truth_value` as JSON; `owner`, `due_date`, `dismiss_reason` copied from prior row.)

**`score_snapshot.csv`**, prior rows plus one row per SKU in this run:
`id, scope, organisation_id, brand_id, sku_id, page_id, taken_at, score, drift_score,
weighted_severity, page_weight, unresolved, by_verdict, by_status, mean_days_to_fix, truth_source, is_demo`
- `scope` = `sku` (same columns as the DB table, plus `drift_score` and `truth_source`),
  `brand`, `organisation` or `page` for roll-up rows (unused ids empty). Only `sku` rows go back to the DB.
- `by_verdict`, `by_status` as JSON; `mean_days_to_fix` = mean of (`status_changed_at` −
  `detected_at`) in days over the SKU's verified conflicts; `taken_at = --now`; `is_demo=false`.
- Dedupe: skip a SKU row when the SKU's last prior `sku` row has the same score, unresolved,
  by_verdict and by_status and the same `taken_at` date.

**`run_log.csv`**: `sku_id, status (ok|failed|skipped), truth_source, new, reopened, resolved,
unresolved, drift_score, error`. One row per selected SKU.

Not produced in CSV mode: audit events, alerts, `sku.last_checked_at`. The DB import (later) derives
them from the conflict status changes.

## 8. Error handling

| Case | Behaviour |
|---|---|
| Missing file / column, bad foreign key | exit 2, nothing written |
| Cell with invalid JSON in `fields`/`value` | that SKU `failed` in `run_log.csv` with row id; its prior conflicts copied unchanged; other SKUs continue; exit 1 |
| Extraction missing a field | field treated as empty, gives `missing` if truth has it |
| SKU with no pages | `skipped`, snapshot row with empty score |
| Unknown field in `approved_claim` | ignored (only the 5 compared fields) |
| Duplicate prior conflict keys | keep lowest `id` active, log a warning in `run_log.csv` |

## 9. Tests (pytest, CSV fixtures, no DB)

Fixtures in `backend/tests/fixtures/agent_csv/<case>/{in,expected}/`. Each test runs the agent on
`in/` with a fixed `--now` and diffs `out/` against `expected/`.

Keep (port from DB tests): every rule in `test_compare.py` (pure, unchanged); reconcile cases from
`test_workflow.py`; truth paths from `test_truth_paths.py`; snapshot per run from `test_trends.py`.

Add:
1. Golden run: CeraVe + Aveeno pilot export, exact `conflict.csv` and `score_snapshot.csv`.
2. Idempotency: output of run 1 fed as input to run 2 gives 0 new/reopened/resolved and no new snapshot.
3. Score math: exact `weighted_severity`, `page_weight`, score, drift for a fixed case.
4. Roll-up: brand drift = formula on summed parts, not mean of SKU drifts.
5. Page weight 2 doubles a conflict's weighted severity.
6. Dismissed stays dismissed; verified finding coming back opens a new id.
7. Truth flip: adding `approved_claim` rows switches `truth_source` to approved.
8. Inferred tie-break is stable across row order shuffles of the input CSVs.
9. Bad JSON in one SKU: that SKU failed, others written, exit 1.
10. Missing `page.csv`: exit 2, `--out` untouched.
11. Parity: same data loaded into the test DB through `run_for_sku` gives the same conflicts and scores.

## 10. Build steps

1. `app/agents/csv_io.py`: read/validate inputs, write outputs atomically.
2. `app/agents/conflict_score.py`: CLI from §1. Calls `compare()`, `majority()`, `score()` unchanged.
3. Reconcile logic from `run.py` extracted into a pure function shared by DB and CSV mode.
4. Fixtures and tests from §9.

Open: `variant` is still unused (no `variant_id` on extraction/claim/conflict). Free-from
contradiction only knows fragrance and paraben.
