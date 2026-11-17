# Conflict & Drift Score Agent — spec

Status: draft, 2026-11-17. Based on `main` at `7d6e9ac`. No code changed.

The agent recomputes `conflict` and `score_snapshot` rows for one SKU. Today this logic lives in
`app/pipeline/run.py::run_for_sku`; the agent wraps it as one named, triggerable, observable job.
It is deterministic: no LLM call happens in matching, conflict creation or scoring.

## 1. Purpose

For one SKU: compare the latest extraction on every page against the SKU's truth, reconcile the
findings with the stored conflicts, and append one score snapshot. Output feeds the conflicts list,
fix board, alerts, overview and trend charts.

## 2. Triggers

| Trigger | Today | Agent |
|---|---|---|
| Truth sheet saved (`POST /skus/{id}/truth-sheet`) | calls `run_for_sku` | same, synchronous |
| Claim approved / removed (`PUT`/`DELETE /skus/{id}/claims/{field}`) | calls `run_for_sku` | same, synchronous |
| On demand (`POST /skus/{id}/run`, seed) | calls `run_for_sku` | same |
| Scheduled (`app.worker.product_checks`) | SKUs with `last_checked_at` older than `CHECK_INTERVAL_HOURS` (24) | same |
| New extraction stored for the SKU | **not wired**; waits for the 24 h worker | **add**: enqueue the SKU after an `Extraction` insert |

One run = one SKU. Batch triggers loop SKUs; one failing SKU never stops the others.

## 3. Inputs (read only)

| Table | Fields used |
|---|---|
| `sku` | `id`, `organisation_id`, `brand_id`, `name` |
| `page` | `id`, `weight` (default 1.0), `retailer`, `url` |
| `snapshot` | `page_id`, `fetched_at` |
| `extraction` | `sku_id`, `snapshot_id`, `fields` = `{field: {value, quote}}` |
| `approved_claim` | `sku_id`, `field`, `value` (latest row per field wins) |
| `inferred_truth` | `sku_id`, `fields`, `agreement`, `method`, `source_hash` |
| `conflict` | existing rows for the SKU with `status != verified` |
| `variant` | **not used today.** Conflicts are per SKU, not per market/size/formula. See §10. |

Latest extraction per page = newest `snapshot.fetched_at`, then highest `extraction.id`.

Compared fields (`COMPARED_FIELDS`, 5): `name`, `ingredients`, `free_from`, `claims`, `seals`.

## 4. Truth resolution

1. **Approved path.** The SKU has an `approved_claim` for any field other than `name`. Truth = latest
   approved value per field. `truth_source = "approved"`.
2. **Inferred path.** No truth sheet. `refresh_inferred` builds `inferred_truth`: per field, the value
   with the largest summed page weight wins (normalised keys, so renames/wording variants group).
   `truth_source = "inferred"`. UI shows the **Unverified** badge and an "add truth sheet"
   recommendation with the inferred values prefilled.
3. **None.** No truth sheet and no extractions. No conflicts; score = `None`.

An approved `name` overrides the inferred name. Saving a truth sheet deletes `inferred_truth` and
re-runs the agent, so every conflict flips to `truth_source = "approved"` or is verified away.

**LLM boundary.** With `ANTHROPIC_API_KEY` set, `_claude_pick` may choose *which existing page value*
becomes the inferred truth for a contested field (`method = "claude"`). It cannot invent values, is
cached by `source_hash`, and falls back to majority on any error. This is truth *selection*, upstream
of the agent's deterministic steps. Rule: the comparison, severity and score never call a model.
Recommendation: add `INFERRED_TRUTH_METHOD=majority|claude` (default `majority`) so the agent can
run fully deterministic end to end.

## 5. Conflict rules (`app/pipeline/compare.py`)

Normalisation before matching:
- ingredients: lowercase, collapse spaces/slashes, strip trailing dot, then `INGREDIENT_RENAMES`
  (aqua→water, ceramide 3→ceramide np, hyaluronic acid→sodium hyaluronate, …)
- free_from: drop stopwords (free, of, from, added, no, without), singularise
- seals: words only, then `SEAL_ALIASES` (e.g. NEA variants)
- claims: alphanumerics only; name: words only

| Verdict | Severity | Fires when |
|---|---|---|
| `contradiction` | 10 | page `free_from` says fragrance/paraben-free but page INCI has a matching ingredient (`FREE_FROM_MARKERS`) |
| `risky` | 9 | list field (free_from, claims, seals): item on page, not in truth |
| `outdated` | 6 | ingredients: normalised set differs from truth (detail lists `not_in_truth`, `not_on_page`) |
| `weaker` | 4 | list field: truth item not on page |
| `missing` | 3 | field has a truth value but page value is empty |
| `drift` | 1 | same meaning, other wording: name differs after normalising; ingredients same set but old names or other order; list item same key, other wording |

One finding per (page, field, verdict, page_value, truth_value). Contradiction is checked against
the page's own INCI, so it fires even on the inferred path.

## 6. Reconcile (idempotency)

Conflict identity key: `(page_id, field, verdict, json(page_value), json(truth_value))`, JSON sorted.

| Stored status | Finding still present | Finding gone |
|---|---|---|
| none | insert `open`, log `detected` | — |
| `open` / `accepted` | keep | → `verified` ("no longer found on re-check") |
| `fixed` | → `open` ("still found on re-check") | → `verified` |
| `dismissed` | keep dismissed, never re-raised | keep dismissed |
| `verified` | history; open a **new** conflict | — |

Present conflicts get `truth_source` updated. Rows are never deleted; stale rows leave the active set
by moving to `verified`. Re-running with unchanged inputs creates no new conflicts (idempotent).

Known gap: a changed `page_value` or `truth_value` is a new key. The old conflict is verified and a
new one opens, so owner, due date and notes do not carry over. Optional fix: match on
`(page_id, field, verdict)` first and update values in place.

## 7. Drift score (`app/services/scoring.py`)

```
weighted_severity = Σ severity × page.weight   over conflicts with status in (open, accepted, fixed)
max               = 10 × 5 fields × Σ page.weight   over pages with any extraction for the SKU
consistency       = max(0, round(100 × (1 − weighted_severity / max)))   stored in score_snapshot.score
drift_score       = 100 − consistency          shown in UI and API (0 = no drift, 100 = worst)
```

No checked pages: score and drift are `None`. `dismissed` and `verified` do not count.

Roll-ups re-apply the same formula to summed parts, never average scores:
- **Product (SKU):** its own tally.
- **Brand / organisation / overall:** sum `weighted_severity` and `page_weight` across SKUs, then
  score (`api/summary.py`, `Tally.add`). Weekly trends use each SKU's last snapshot before week end.
- **Page:** **not computed today** (only an unresolved count per page in `by_source`). Add
  `page_drift = 100 − score(Σ severity×weight on that page, 10 × 5 × weight × SKUs on that page)`.

## 8. Outputs

`conflict` (insert or status change): `organisation_id, sku_id, page_id, field, page_value,
truth_value, verdict, severity, status, truth_source, detected_at, status_changed_at`. Every
change writes an audit event (`detected` or a status transition) and one `check_run` event with
counts `{new, reopened, resolved}`.

`score_snapshot` (append one row per run): `organisation_id, brand_id, sku_id, taken_at, score,
weighted_severity, page_weight, unresolved, by_verdict, by_status, mean_days_to_fix, is_demo=false`.

Also: `sku.last_checked_at = now`, alerts via `alerts_for_run` for new conflicts and score change.

Snapshots are history, never replaced. Repeat runs append duplicates. Recommendation: skip the
insert when score, `unresolved`, `by_verdict` and `by_status` equal the SKU's last snapshot from the
same day. Demo rows (`is_demo=true`) are only replaced by `seed --demo-history`.

All writes for one SKU happen in one transaction (single `commit` at the end of the run).

## 9. Error handling

| Case | Behaviour |
|---|---|
| Claude pick fails or times out | majority truth, run continues (already so) |
| Extraction missing a field / malformed value | treated as empty, produces `missing` if truth has it |
| SKU has no pages | no conflicts, snapshot with `score = None` |
| DB error mid-run | roll back the SKU; worker logs `job_run.status = failed`, next SKU continues |
| Two runs for one SKU at once | **not guarded today**; can insert duplicate conflicts. Add `pg_advisory_xact_lock(sku_id)` at run start |
| Unknown field in `approved_claim` | ignored by compare (only `COMPARED_FIELDS`) |

## 10. Out of scope / open questions

- **Variant.** `variant` (market, size, formula_version, valid_from/to) is not linked to
  extraction or conflict. Per-variant truth needs a `variant_id` on `extraction`, `approved_claim`
  and `conflict`. Decide before multi-market data.
- AI answers vs truth live in `app/ai/*`, not this agent.
- Free-from contradiction only knows fragrance and paraben. Add markers (sulfate, alcohol, …) as data.

## 11. Tests to add

Existing: `test_compare.py` (rules), `test_workflow.py` (reconcile), `test_truth_paths.py` (paths),
`test_trends.py` (snapshots). Add:

1. Idempotency: two runs with no input change, second run returns `new=0, reopened=0, resolved=0`.
2. Score math: fixed fixture, assert exact `weighted_severity`, `page_weight`, score and drift.
3. Roll-up: brand drift equals formula on summed parts, not mean of SKU drifts.
4. Page weight: same conflict on weight-2 page doubles its weighted severity.
5. Dismissed conflict stays dismissed after re-run; verified one reopens as new row.
6. Truth flip: inferred → approved switches `truth_source` on surviving conflicts, clears `inferred_truth`.
7. No pages: snapshot written with `score = None`.
8. New-extraction trigger enqueues and runs the SKU (once wired).
9. Concurrency: two parallel runs leave no duplicate conflict keys (once lock added).
10. Determinism: with `INFERRED_TRUTH_METHOD=majority`, no Anthropic client constructed.

## 12. Build steps (when approved)

1. `app/agents/conflict_score.py`: `run(sku_id, trigger) -> RunResult`, wraps `run_for_sku`, adds
   advisory lock and the `trigger` in the `check_run` audit detail.
2. Hook `Extraction` insert to enqueue the SKU (worker queue, not inline).
3. Snapshot dedupe rule from §8.
4. Page-level drift in `api/summary.py`.
5. `INFERRED_TRUTH_METHOD` env flag.
6. Tests from §11.
