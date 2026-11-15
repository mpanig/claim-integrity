# claim-integrity

Checks that what retailers, professional sites and AI assistants say about a CPG
product (ingredients, free-from claims, other claims, seals, name) matches what the
brand has approved. Every mismatch becomes a conflict with a verdict, a severity
and a workflow, and the web app turns this into a suite for a marketing team:
scores, trends, competitor comparison, recommendations, alerts and reports.

## Layout

```
backend/                 FastAPI + SQLAlchemy 2 + Alembic (Python 3.12, uv)
  app/
    models.py            all tables
    pipeline/            fetch -> extract -> compare -> run (reconcile conflicts)
    services/            workflow, scoring, trends, competitors, recommendations,
                         ai_visibility, alerts, reports
    api/                 one router per area
    seed.py              pilot data (CeraVe + Aveeno)
  alembic/versions/      0001 core ... 0006 team_member
  fixtures/              hand-written stand-in retailer pages + their extractions
  tests/                 pytest (rules + API against a real test database)
frontend/                Next.js 16 (App Router), Tailwind 4, shadcn/ui (Base UI), Recharts
  src/app/               one folder per screen
  src/components/        shell, conflict panel, charts, tables, forms
  e2e/verify.mjs         Playwright check of every screen + screenshots
docs/screenshots/        screenshots from the last verify run
```

## Run it (WSL / Linux)

Needs [uv](https://docs.astral.sh/uv/), Node 20+ and Postgres 13+ on localhost:5432.

Backend (terminal 1):

```bash
cd backend
cp .env.example .env            # put your Postgres user/password in .env
uv sync
uv run python -m scripts.create_db
uv run alembic upgrade head
uv run python -m app.seed --demo-history   # omit --demo-history for real data only
uv run uvicorn app.main:app --reload       # http://localhost:8000
```

Frontend (terminal 2):

```bash
cd frontend
npm install
npm run dev                      # http://localhost:3000
```

The browser calls `/api/*` on the Next server, which forwards to the backend
(`API_URL`, default `http://127.0.0.1:8000`). CORS also allows `localhost:3000`.
For a production build: `npm run build && npm start`.

## Tests

```bash
cd backend && uv run pytest      # drops and recreates TEST_DATABASE_URL (must end in _test)
cd frontend && npx tsc --noEmit && npx eslint src
```

End-to-end (both apps running, seeded with `--demo-history`):

```bash
cd frontend
npx playwright install chromium  # or set BROWSER_CHANNEL=chrome to use installed Chrome
node e2e/verify.mjs              # loads every screen, fails on console errors,
                                 # does Accept -> Mark fixed, writes docs/screenshots/
```

## Screens

| Screen | What it does |
|---|---|
| Overview | Consistency score, open / in-progress issues, next best actions, score trend by brand, open vs fixed by week, issues by type and by source, mean time to fix, top 5 to fix, activity |
| Products | Search and brand filter, score, open issues, last checked, Run check |
| Product | Matrix of claim types × sources (brand site = truth); cells are green / amber / red; click opens the conflict |
| Conflict panel | Approved vs page value with differences highlighted, evidence quote, source links, plain-English explanation; Accept, Dismiss (reason), owner, due date, notes, Mark fixed / verified, Re-check; full history |
| Conflicts | All issues with status / type / owner filters in the URL; bulk accept, dismiss, assign |
| Fix board | To review → Accepted → Fixed → Verified, drag or buttons, owner and due date on cards |
| Competitors | Brand cards, score and issues-per-product charts, claim-type × brand heatmap, claims coverage (approved vs unapproved), insights |
| AI visibility | Prompts to track, answers, facts checked against the truth sheet, repeats of page issues, share of voice |
| Recommendations | Ranked actions (risk × page weight × ease) with why, impact, owner team, Create task |
| Alerts | New high-risk issues and score drops (5+ points), read / unread, bell in the top bar |
| Reports | Weekly per brand: score change, new issues, fixes verified, top issues, products; CSV export; print / PDF |
| Truth sheets | Approved claims per product; edit them or add a product |
| Settings | Team members and roles (owner menus use them), connection status |
| Search | Products, pages and issues (Ctrl/Cmd+K) |

The top bar has a brand switcher, a date range (trend charts), search, alerts and light/dark mode.

## Rules

Compare (per page and claim type):

| Situation | Verdict | Severity |
|---|---|---|
| Page claims free-from X but its own INCI list contains X (fragrance, parabens) | contradiction | 10 |
| Page shows a claim / seal / free-from that is not approved | risky | 9 |
| Ingredient set differs from the approved list (after renames) | outdated | 6 |
| Approved claim / seal / free-from not on the page | weaker | 4 |
| Approved field absent from the page entirely | missing | 3 |
| Same meaning, different wording / old INCI names / order / name | drift | 1 |

Known INCI renames are normalised (`Ceramide 3` → `Ceramide NP`, `Ceramide 6-II` → `Ceramide AP`,
`Ceramide 1` → `Ceramide EOP`, `Hyaluronic Acid` → `Sodium Hyaluronate`, `Purified Water` → water).

Workflow: open → accepted | dismissed (reason required); accepted → fixed; fixed → verified | open.
A re-check verifies conflicts no longer found, reopens fixed ones still found, never re-raises
dismissed ones, and opens a new conflict if a verified one comes back.

Consistency score = 100 × (1 − Σ severity × page weight of unresolved issues ÷ (10 × 5 claim types × Σ page weights)).
Unresolved = open, accepted, fixed.

Recommendations, alert and AI rules are documented at the top of
`backend/app/services/recommendations.py`, `alerts.py` and `ai_visibility.py`.

## Pilot data

- CeraVe Hydrating Facial Cleanser (truth: cerave.com) vs a Rite Aid page with the old formula:
  outdated ingredient list (parabens) and free-from wording drift. Score 86.
- Aveeno Calm + Restore Nourishing Oat Cleanser (truth: aveeno.com, 16 ingredients, no free-from
  claims) vs Hannaford (name drift, five unapproved free-from claims, "tested on sensitive skin")
  and Kenvue Pro (hypoallergenic, sulfate-free, colloidal oatmeal skin protectant). Score 13.

The retailer pages are **hand-written stand-ins** (`backend/fixtures/`), not scraped copies, and
the GTINs are empty. The sample team in Settings uses fictional names.

## What is demo data

`--demo-history` adds, all flagged `is_demo` in the database and shown with a **Demo data** badge:

- 12 weeks of score history (Overview trend charts, last-week score in Reports)
- six invented AI-assistant answers from "Assistant A/B (demo)" (AI visibility, and the
  "Correct what AI assistants say" recommendation)

Everything else (scores, conflicts, recommendations, alerts, competitor comparison) is computed
from the seeded pages.

## Not built yet (TODO)

- Sign-in, per-organisation access and real users (everyone acts as "Demo CMO")
- LLM extraction of pages and live AI-assistant queries (needs API keys)
- Scheduled fetching of real retailer pages
- Email / Slack delivery of alerts and per-user notification settings
