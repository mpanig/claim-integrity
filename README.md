# claim-integrity

Checks that what retailers, professional sites and AI assistants say about a CPG
product (ingredients, free-from claims, other claims, seals, name) matches what the
brand has approved. Every mismatch becomes a conflict with a verdict, a severity
and a workflow. The web app turns this into a suite for a marketing team: scores,
trends, competitor comparison, recommendations, alerts and reports.

- [Set up on a fresh machine](#set-up-on-a-fresh-machine)
- [Run it](#run-it)
- [Tests](#tests)
- [Project structure](#project-structure)
- [Screens](#screens) · [Rules](#rules) · [Pilot data](#pilot-data) · [What is demo data](#what-is-demo-data) · [Not built yet](#not-built-yet-todo)
- [Troubleshooting](#troubleshooting)

## Set up on a fresh machine

### 1. Prerequisites

| Tool | Version used | Notes |
|---|---|---|
| OS | Ubuntu 22.04 on WSL2 (Windows), any Linux, or macOS | Windows: run everything inside WSL |
| [uv](https://docs.astral.sh/uv/getting-started/installation/) | 0.13 | installs Python 3.12 for you (`requires-python >=3.12,<3.13`) |
| Node.js | 24 (20 or newer works) | e.g. via [nvm](https://github.com/nvm-sh/nvm): `nvm install --lts` |
| PostgreSQL | 15 (13 or newer) | reachable on `localhost:5432` |
| git | any recent | |
| Chromium for Playwright | optional | only for the end-to-end check |

Install uv and Node if you don't have them:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.3/install.sh | bash
nvm install --lts
```

Install PostgreSQL (Ubuntu / WSL):

```bash
sudo apt update && sudo apt install -y postgresql postgresql-client
sudo service postgresql start
```

macOS: `brew install postgresql@15 && brew services start postgresql@15`.

### 2. Get the code

```bash
git clone <repository-url> claim-integrity
cd claim-integrity
```

### 3. Create the databases

You need two databases: `claim_integrity` for the app and `claim_integrity_test` for the tests
(the test suite drops and recreates it on every run).

**Option A: psql.** Create a login role and both databases (pick your own password):

```bash
sudo -u postgres psql -c "CREATE ROLE claim_app LOGIN PASSWORD 'choose-a-password';"
sudo -u postgres psql -c "CREATE DATABASE claim_integrity OWNER claim_app;"
sudo -u postgres psql -c "ALTER ROLE claim_app CREATEDB;"   # lets the tests recreate claim_integrity_test
```

The test database is created by the tests themselves. To create it up front anyway:
`sudo -u postgres psql -c "CREATE DATABASE claim_integrity_test OWNER claim_app;"`

**Option B: the included script.** If you already have a Postgres user that may create
databases (for example `postgres`), fill in `.env` (next step) and run:

```bash
cd backend
uv run python -m scripts.create_db     # creates the database named in DATABASE_URL if missing
```

### 4. Configure `backend/.env`

```bash
cd backend
cp .env.example .env
```

Edit `backend/.env`. It is git-ignored; never commit it.

| Variable | Required | What it is |
|---|---|---|
| `DATABASE_URL` | yes | `postgresql+psycopg://USER:PASSWORD@localhost:5432/claim_integrity` |
| `TEST_DATABASE_URL` | for tests | same server, database name must end in `_test`: `.../claim_integrity_test` |
| `CORS_ORIGINS` | no | JSON list of browser origins allowed to call the API directly; default `["http://localhost:3000","http://127.0.0.1:3000"]` |

AI answer engine keys (all optional, empty placeholders in `.env.example`). Each key switches
that engine from demo answers to live answers; engines without a key are skipped and cost nothing.

| Variable | Unlocks |
|---|---|
| `OPENAI_API_KEY` | OpenAI Responses API, with or without its web search tool (region passed as user location) |
| `GEMINI_API_KEY` | Gemini with or without Google Search grounding (no location option: region goes in the question) |
| `PERPLEXITY_API_KEY` | Perplexity Sonar (always searches the web; region passed as user location) |
| `ANTHROPIC_API_KEY` | Claude, with or without its web search tool (region passed as user location); also makes Claude the answer analyser |
| `OLLAMA_URL`, `OLLAMA_MODEL` | If no Anthropic key: a local model through [Ollama](https://ollama.com) analyses answers (`ollama pull qwen2.5:7b`). Without either, built-in rules analyse them |

Provider endpoints can be overridden with `OPENAI_API_URL`, `GEMINI_API_URL` and `PERPLEXITY_API_URL`
if a provider moves them.

### 5. Install, migrate, seed

```bash
cd backend
uv sync                                       # creates .venv with Python 3.12 and all packages
uv run alembic upgrade head                   # creates all tables
uv run python -m app.seed --demo-history      # pilot data + sample history (see below)
```

- `uv run python -m app.seed` loads the pilot products, retailer pages and a sample team, and runs a check.
  Re-running it resets the pilot organisation.
- `--demo-history` also adds 12 weeks of drift-score history and about 8,700 demo AI-assistant answers
  (4 engines with 2 models each, search on and off, US / India (English and Hindi) / UK, 4 personas,
  12 weekly runs). These rows are flagged as demo in the database and every chart or card that uses them
  shows a **Demo data** badge. Leave the flag out to see only real results.
- `--demo-ai` only regenerates the AEO / GEO demo data (AI answers, page grades, llms.txt checks,
  crawler log, referral export, outreach rows, AEO alerts), leaving everything else as it is.
- When you add an engine's API key to `backend/.env`, that engine's demo answers stop showing (no restart
  needed). Until it has real answers, the AI pages say "Key found, no real answers yet" with a **Run now**
  button that shows the pilot plan's cost estimate and a budget cap first. Engines without a key keep
  their badged demo answers.
- `--no-run` seeds without running the first check.

### 6. Install the frontend

```bash
cd frontend
npm install
```

Frontend environment (optional, e.g. in `frontend/.env.local`):

| Variable | Default | What it is |
|---|---|---|
| `API_URL` | `http://127.0.0.1:8000` | where the Next server finds the FastAPI backend; the browser calls `/api/*` on the Next server, which forwards there |

## Run it

Two terminals:

```bash
# terminal 1: API on http://localhost:8000 (docs at /docs)
cd backend
uv run uvicorn app.main:app --reload
```

```bash
# terminal 2: web app on http://localhost:3000
cd frontend
npm run dev
```

Open <http://localhost:3000>. For a production build: `npm run build && npm start`.

Optional third terminal: the background worker keeps trend history real. It re-checks each
product every `CHECK_INTERVAL_HOURS` (default 24; each check adds a score snapshot) and runs
saved AI plans that are due. Settings shows when each job last ran.

```bash
cd backend
uv run python -m app.worker            # loop, every 5 minutes
uv run python -m app.worker --once     # one pass, e.g. from cron
```

## Tests

Backend (needs `TEST_DATABASE_URL`):

```bash
cd backend
uv run pytest
```

Frontend type check and lint:

```bash
cd frontend
npx tsc --noEmit
npx eslint src
```

End-to-end check (both apps running, seeded with `--demo-history`). It opens every screen,
fails on any console error, runs Accept → Mark fixed on a conflict, and writes screenshots
to `docs/screenshots/`:

```bash
cd frontend
npx playwright install chromium        # once; or set BROWSER_CHANNEL=chrome to use an installed Chrome
node e2e/verify.mjs
```

## Project structure

```
backend/                 FastAPI + SQLAlchemy 2 + Alembic (Python 3.12, uv)
  app/
    models.py            all tables
    pipeline/            fetch -> extract -> compare -> run (reconcile conflicts)
    services/            workflow, scoring, trends, competitors, recommendations,
                         alerts, reports
    ai/                  AI answer engine: engines (OpenAI, Gemini, Perplexity, Claude),
                         plan, runner, analyse, insights, library, demo, schedule
    api/                 one router per area
    seed.py              pilot data (CeraVe + Aveeno)
  alembic/versions/      database migrations
  fixtures/              hand-written stand-in retailer pages + their extractions
  scripts/               create_db.py, smoke.sh
  tests/                 pytest (rules + API against a real test database)
frontend/                Next.js 16 (App Router), Tailwind 4, shadcn/ui (Base UI), Recharts
  src/app/               one folder per screen
  src/components/        shell, conflict panel, charts, tables, forms
  e2e/verify.mjs         Playwright check of every screen + screenshots
docs/screenshots/        screenshots from the last end-to-end run
```

## Screens

| Screen | What it does |
|---|---|
| Overview | Drift score (0 = no drift), open / in-progress issues, next best actions, drift trend by brand, open vs fixed by week, issues by type and by source, mean time to fix, top 5 to fix, activity |
| Products | Search and brand filter, drift score, inferred-truth badge, open issues, last checked, Run check |
| Product | Matrix of claim types × sources (brand site = truth); cells are green / amber / red; click opens the conflict |
| Conflict panel | Approved vs page value with differences highlighted, evidence quote, source links, plain-English explanation; Accept, Dismiss (reason), owner, due date, notes, Mark fixed / verified, Re-check; full history |
| Conflicts | All issues with status / type / owner filters in the URL; bulk accept, dismiss, assign |
| Fix board | To review → Accepted → Fixed → Verified, drag or buttons, owner and due date on cards |
| Competitors | Brand cards, drift score and issues-per-product charts, claim-type × brand heatmap, claims coverage (approved vs unapproved), insights |
| AEO / GEO | Answer / generative engine optimisation, a sidebar group with 10 subsections (see [AEO / GEO](#aeo--geo) below): Overview, Prompts, Answers, Citations & sources, Brand perception, Content & pages, Crawlers & traffic, Coverage, Alerts. Old `/ai-visibility/*` and `/audit` links redirect. |
| Recommendations | Ranked actions (risk × page weight × ease) with why, impact, owner team, Create task |
| Alerts | New high-risk issues and drift-score rises (5+ points), AEO alerts, read / unread, bell in the top bar |
| Reports | Weekly per brand: drift score and change, new issues, fixes verified, top issues, products; CSV export; white-label PDF download (logo, colours, title, footer set in Settings › Report branding); print |
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

**Drift score** = 100 × Σ severity × page weight of unresolved issues ÷ (10 × 5 claim types × Σ page weights).
0 means every page matches the truth; higher means more drift. Unresolved = open, accepted, fixed.
(It replaces the earlier "consistency score", which was 100 − drift. APIs return `drift_score`
alongside the old `score` field, kept for older clients.)

## Truth sheets and inferred truth

- **Product with a truth sheet** (approved claims for at least one field besides the name): every
  page, the drift score and AI answer checks use the approved claims.
- **Product without one**: a provisional truth is built from what its pages agree on (per field, the
  value with the most page weight behind it; with `ANTHROPIC_API_KEY` set, Claude may instead pick
  among the values the pages show, never inventing one). It is shown everywhere as
  "Inferred truth, unverified" (product, claim matrix, drift score, conflicts), and an
  **"Add a truth sheet for <product>"** recommendation appears on Recommendations, the product page and
  Truth sheets. Its button opens the truth sheet editor pre-filled with the inferred claims.
- **Approving a truth sheet** (or saving any claim) re-checks the product straight away: conflicts and
  the drift score are recomputed, the inferred truth is removed and the recommendation resolves.
- Content briefs and the llms.txt draft only ever use approved facts, never inferred ones.

Recommendations, alert and AI rules are documented at the top of
`backend/app/services/recommendations.py`, `alerts.py` and `ai_visibility.py`.

## AI answer engine

`backend/app/ai/` asks AI assistants shopper questions through their official APIs and measures
the answers. A test plan expands to prompts × wording variants × engines × models × web search
on/off × regions × languages × personas × samples (default 3, since answers vary run to run).
Every answer is stored raw with what shaped it: requested model and the exact version returned,
web search on/off, region and how it was applied (`api` user location, or `prompt-only`),
language, persona, sample number, tokens, cost, latency.

Each answer is analysed for brand mentions (alias matching), rank in list answers, recommended
or not, sentiment, product facts checked against the truth sheet (with links to open page
issues they repeat), and citations by page type. Rates are reported with 95% Wilson ranges.
APIs are stateless: they don't reproduce the consumer apps' memory or personalisation, so the
plan sets that context explicitly (persona, region, language).

Run a saved plan on its schedule from cron (e.g. hourly): `uv run python -m app.ai.schedule`.
Nothing scrapes consumer chat apps.

## AEO / GEO

Everything about how AI assistants answer shoppers, in one sidebar group. Each subsection is its
own page; the group opens when you are in it and otherwise remembers whether you left it open.

| Subsection | What it does |
|---|---|
| Overview | **AEO score** 0–100 per brand (mentioned 35%, recommended 25%, prominence 20%, share of words 10%, sentiment 10%) with week-on-week change, competitor benchmark, score by week, score by brand × engine; **prominence** (named first, how far into the answer, share of words); mention / recommendation / top-3 rates with 95% ranges, heatmap, rank distribution, fact accuracy, trend. Engine strip shows live / demo / "key found, no real answers yet" (with Run now) and planned engines |
| Prompts | Library; **Discovery** (rule-based questions per type, persona, competitor and product, deduplicated against the library, with an *estimated* importance and its reasons; "Suggest more with Claude" when an Anthropic key is set, one call on request); Test plans & runs; planned engines |
| Answers | Explorer and side-by-side compare |
| Citations & sources | Most cited sites, source types, gap sites (cited when a competitor is recommended and our brands aren't); **outreach tracker** (to contact → contacted → published / declined, owner, due date, note; competitor and retailer sites never suggested) |
| Brand perception | Attribute × brand map from AI answers (13 attributes incl. negatives; product names excluded), the brand that owns each attribute, **intended positioning** per brand (editable) and its gaps |
| Content & pages | **Answer-readiness grader** (12 checks, 100 points, a fix for each); **content briefs** from your own data (Markdown); **llms.txt** checker (llmstxt.org format, score and fixes) and draft generator; structured data, freshness, brand entity clarity |
| Crawlers & traffic | **AI crawler log analytics** from uploaded access logs (combined format or CSV; counts only, no IPs); **AI referral traffic** from an analytics CSV (ChatGPT, Perplexity, Gemini, Copilot, Claude, DeepSeek, Meta AI; GA4 connector planned); crawlability per page |
| Coverage | Shopper situations (question type × persona) where competitors are mentioned more |
| Alerts | **AEO alerts**: score drop, competitor overtaking, lost recommendation on a top prompt, new wrong fact; checked after every AI run and on demand, also in the bell and on Alerts |

Engines: OpenAI, Gemini, Perplexity and Claude are connected (official APIs; a key in
`backend/.env` switches that engine from demo to real answers, re-read on every request).
Google AI Overviews, Google AI Mode, Copilot, Grok, DeepSeek and Meta AI are listed as
**planned** with the key each will use; they are never run, estimated or given demo answers.

How it fetches: every page, robots.txt and llms.txt fetch goes through one polite fetcher
(robots.txt first, honest User-Agent, one request per URL per check, nothing fetched when the
site says no). AI crawler and referral analytics only read files you upload.

## Page and entity checks (AEO / GEO › Content & pages, Crawlers & traffic)

`backend/app/audit/` checks pages a user enters (the seed adds each product's brand page from its
truth sheet). Each page is fetched once with an honest User-Agent after reading robots.txt; if
robots.txt disallows us, or the site refuses the request, the page is marked blocked and not
fetched. Nothing impersonates an AI crawler.

- Structured data: schema.org Product present, required/recommended properties, GTIN check digit, price
- AI crawlability: robots.txt rules for GPTBot, OAI-SearchBot, ClaudeBot, Claude-SearchBot,
  PerplexityBot, Google-Extended, Googlebot, Bingbot, CCBot and others; noindex/noai; JavaScript-only pages
- Freshness: dates on the page (JSON-LD, meta, Last-Modified), and how much of the approved
  ingredient list the page shows
- Entity clarity: each brand's Wikidata entry and Wikipedia article (public APIs), scored on the facts AI models use

AEO / GEO › Coverage uses AI answers: use cases (question type × persona) where a competitor
is mentioned more than us. AEO / GEO › Citations & sources lists the third-party sites the answers
cite. The worker re-audits weekly.

## Pilot data

- CeraVe Hydrating Facial Cleanser (truth: cerave.com) vs a Rite Aid page with the old formula:
  outdated ingredient list (parabens) and free-from wording drift. Drift score 14.
- Aveeno Calm + Restore Nourishing Oat Cleanser (truth: aveeno.com, 16 ingredients, no free-from
  claims) vs Hannaford (name drift, five unapproved free-from claims, "tested on sensitive skin")
  and Kenvue Pro (hypoallergenic, sulfate-free, colloidal oatmeal skin protectant). Drift score 87.

The retailer pages are **hand-written stand-ins** (`backend/fixtures/`), not scraped copies, and
the GTINs are empty. The sample team in Settings uses fictional names.

## What is demo data

`--demo-history` adds, all flagged `is_demo` in the database and shown with a **Demo data** badge:

- 12 weeks of drift-score history (Overview trend charts, last week in Reports)
- About 8,750 template-generated AI answers across all four engines (2 models each), US, India
  (English and Hindi) and UK, every persona, 12 weekly runs (AEO / GEO, and the "Correct what AI
  assistants say" recommendation). For each engine they are hidden as soon as its API key is set.
- AEO extras, each hidden as soon as real data of that kind exists: page answer-readiness grades
  (bundled hand-written pages, per URL), llms.txt checks (per site), a 28-day AI crawler log and an
  8-week AI referral export (until your first upload), five outreach rows (until your first tracked
  site), and AEO alerts computed from the demo answers (replaced on every check).

The prompt library, personas, competitors and aliases that the seed adds are real configuration,
not demo data.

Everything else (scores, conflicts, recommendations, alerts, competitor comparison) is computed
from the seeded pages.

## Not built yet (TODO)

- Sign-in, per-organisation access and real users (everyone acts as "Demo CMO")
- Live AI answers need API keys (the engine is built; without keys it shows demo data)
- Reading real retailer pages: a scraper/collector was started and is shelved on the
  `shelved/scraper` branch
- Email / Slack delivery of alerts and per-user notification settings
- Connectors for the planned AI engines (Google AI Overviews / AI Mode and Copilot via a SERP provider, Grok, DeepSeek, Meta AI)
- Direct GA4 connection for AI referral traffic (CSV import works today)
- Brand perception and the rule-based analyser read English wording only

## Troubleshooting

**Port already in use** (`address already in use` for 8000 or 3000). Find and stop the process,
or run on another port:

```bash
lsof -i :8000                                   # or :3000
uv run uvicorn app.main:app --reload --port 8001
API_URL=http://127.0.0.1:8001 npm run dev -- -p 3001
```

**Database authentication failed** (`password authentication failed for user`). Check the user,
password and database in `backend/.env`. Test them directly:
`psql "postgresql://USER:PASSWORD@localhost:5432/claim_integrity" -c "select 1"`. If Postgres
runs on Windows while the code runs in WSL, make sure it listens on localhost and that WSL
can reach it.

**Database does not exist.** Run `uv run python -m scripts.create_db` or create it with psql (step 3),
then `uv run alembic upgrade head`.

**The web app says it can't reach the service.** The backend isn't running, or `API_URL` points
to the wrong place. Start the backend and check <http://localhost:8000/health>.

**Tests refuse to run** (`TEST_DATABASE_URL must name a database ending in _test`). That guard stops
the tests from wiping your real database; point `TEST_DATABASE_URL` at a `_test` database.

**Playwright can't find a browser** (`Executable doesn't exist`). Run `npx playwright install chromium`
in `frontend/` (on Linux also `npx playwright install-deps chromium`, which needs sudo), or use an
installed Chrome: `BROWSER_CHANNEL=chrome node e2e/verify.mjs`.

**Charts show "Demo data".** You seeded with `--demo-history`. Re-seed without it for real data only.
