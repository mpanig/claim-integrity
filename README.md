# claim-integrity

Checks that what retailers and other pages say about a CPG product (ingredients,
free-from claims, seals, name) matches what the brand has approved, and records
each mismatch as a conflict with a verdict and severity.

Phase 1 is the backend scaffold: schema, pipeline (fetch → extract → compare),
a pilot seed, and a small API.

## Layout

```
backend/
  app/
    config.py, db.py, models.py   settings, engine, SQLAlchemy models
    main.py                       FastAPI app
    seed.py                       pilot data (CeraVe Hydrating Facial Cleanser)
    pipeline/
      fetch.py     httpx GET -> snapshot (sha256; skipped when unchanged)
      extract.py   Extractor interface + ManualExtractor (JSON fixture)
      compare.py   deterministic rules -> findings
      run.py       compare a SKU's latest extractions, store conflicts
  alembic/        migrations (0001 = core tables)
  fixtures/       Rite Aid page fixture + its manual extraction
  scripts/        create_db.py, smoke.sh
  tests/          rule tests + end-to-end test on a test database
```

## Setup (WSL / Linux)

Needs [uv](https://docs.astral.sh/uv/) and Postgres 13+ on localhost:5432.

```bash
cd backend
cp .env.example .env          # then put your Postgres user/password in .env
uv sync                       # installs Python 3.12 + deps into .venv
uv run python -m scripts.create_db
uv run alembic upgrade head
uv run python -m app.seed
uv run uvicorn app.main:app --reload
```

Then:

```bash
curl localhost:8000/health
curl localhost:8000/skus
curl -X POST localhost:8000/skus/1/run
curl localhost:8000/skus/1/conflicts
```

## Tests

```bash
cd backend
uv run pytest
```

The database tests drop and recreate `TEST_DATABASE_URL` (must end in `_test`)
on every run.

## Compare rules

| Situation | Verdict | Severity |
|---|---|---|
| Page claims free-from X but its own INCI list contains X (fragrance, parabens) | contradiction | 10 |
| Page shows a claim/seal/free-from that is not approved | risky | 9 |
| Ingredient set differs from the approved list (after renames) | outdated | 6 |
| Approved claim/seal/free-from not on the page | weaker | 4 |
| Approved field absent from the page entirely | missing | 3 |
| Same meaning, different wording / old INCI names / order / name | drift | 1 |

Ingredient names are normalised for case and whitespace, and known renames are
mapped (`Ceramide 3` → `Ceramide NP`, `Ceramide 6-II` → `Ceramide AP`,
`Ceramide 1` → `Ceramide EOP`, `Hyaluronic Acid` → `Sodium Hyaluronate`,
`Purified Water`/`Aqua/Water/Eau` → `water`).

Re-running a SKU replaces its open conflicts; conflicts already triaged
(accepted, fixed, verified, dismissed) are kept and not raised again.

## Pilot

Truth is the current cerave.com INCI list and claims; the Rite Aid page fixture
shows the old formula. Expected and asserted in tests:

- `ingredients` → **outdated** (methylparaben, propylparaben on the page;
  phenoxyethanol, tocopherol, ethylhexylglycerin missing)
- `free_from` → **drift** ("Fragrance Free" vs "Free of Added Fragrance")

The Rite Aid URL and HTML are hand-written stand-ins, and the SKU has no GTIN
yet; replace both with real values when available.

## Not built yet

- LLM extractor (`TODO` in `pipeline/extract.py`; needs API keys)
- Auth and tenant scoping on the API (`TODO` in `main.py`)
