# Opt-Mining

Opt-Mining is a **preliminary screening** tool for onshore wind siting in New
South Wales. It builds a per-cell feature dataset on a ~5 km (0.05°) analysis
grid, excludes ineligible land, scores and ranks the eligible cells with a
transparent weighted multi-criteria model, explains every cell, and serves the
results through a FastAPI service and a Next.js web app.

> ⚠️ **This is a screening-level tool. Read this first.** Opt-Mining surfaces
> higher-ranked candidate cells for *further investigation* under a chosen set
> of assumptions and criteria. It does **not** find "the best site to build a
> wind farm", a "best place to build", an optimal location or a final
> recommendation. It is never a site approval, a project cost, an LCOE, an
> energy-yield estimate or an engineering-grade assessment. Results are at
> analysis-grid resolution and only show *where to look next*.

> ⚠️ **The electricity demand layer is a PROXY.** `demand_proxy` is a spatial
> proxy *indicator*. Each NEM region's annual-mean operational demand is spread
> across its cells by distance to real NSW zone substations, weighted by their
> recorded load (`load_weighted`). It is then expressed as a **percentile within
> the region** (0–1: a rank position, not a magnitude). It is **never** measured
> or actual local demand at a cell. See
> [`DATA/electricity-demand/demand_feature_method.md`](DATA/electricity-demand/demand_feature_method.md).

---

## Contents

- [Key features](#key-features)
- [Tech stack](#tech-stack)
- [Prerequisites](#prerequisites)
- [Quick start (Docker, one command)](#quick-start-docker-one-command)
- [Local development without Docker](#local-development-without-docker)
- [Architecture](#architecture)
  - [Repository layout](#repository-layout)
  - [Pipeline stages](#pipeline-stages)
  - [Decision service API](#decision-service-api)
  - [Web app](#web-app)
- [The scoring model](#the-scoring-model)
- [Data, provenance and assumptions](#data-provenance-and-assumptions)
- [Environment variables](#environment-variables)
- [Command reference](#command-reference)
- [Testing](#testing)
- [Continuous integration](#continuous-integration)
- [Rebuilding the data](#rebuilding-the-data)
- [Sensitivity analysis](#sensitivity-analysis)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)
- [Limitations](#limitations)
- [Further documentation](#further-documentation)

---

## Key features

- **A full-NSW analysis grid**: 47,311 cells at ~5 km (0.05°). On the current
  baseline, **23,266** of them are eligible after exclusions.
- **Six scored criteria**: wind speed at 100 m, distance to ≥132 kV
  transmission, the demand proxy, distance to substation, slope, and whether the
  cell is inside a Renewable Energy Zone (REZ).
- **Auditable exclusions**: eight reason codes, defined as data in YAML. Every
  excluded cell says why it was excluded.
- **A transparent weighted MCDA**, not a machine-learning model. Every
  criterion's contribution to every score is stored and reconciles back to the
  score.
- **Deterministic explanations for every cell**, written from templates and
  rules (no LLM). Eligible cells list their factors and weaknesses; excluded
  cells list their reasons. Every record carries proxy and data-quality caveats.
- **Scenarios and custom weights**: run the packaged `wind_led` / `grid_led`
  scenarios or edit the weights, then compare two runs cell by cell.
- **A sanity check against reality**: known operating wind farms, expected
  exclusions (cities, national parks, offshore), feature spot-checks and
  score-distribution plausibility. Each check shows expected versus observed
  with an explicit pass or fail.
- **A web app**: an interactive map, the ranked shortlist with CSV export, site
  detail, scenario comparison, data-quality status and the sanity-check panel.
  The browser does no scoring at all.

## Tech stack

| Layer | Technology |
| ----- | ---------- |
| Pipeline / decision engine | Python **3.13**: pandas 2.2, GeoPandas 1.1, Shapely 2.1, rasterio 1.4, pyogrio, pyproj, NumPy 2.2, PyYAML |
| Decision service | FastAPI 0.115 + Uvicorn, auto-generated OpenAPI schema |
| Web app | Next.js 14 (App Router), React 18, TypeScript 5.5, MapLibre GL 4.7, `openapi-fetch` + `openapi-typescript` (typed client generated from the API contract) |
| Tests | pytest 9 + Hypothesis (Python); Jest 29 + Testing Library (frontend); Playwright 1.63 (browser end-to-end) |
| Packaging / CI | Docker + Docker Compose v2; GitHub Actions |

## Prerequisites

| Need | Version | Why |
| ---- | ------- | --- |
| Docker + Docker Compose v2 | any recent | The one-command full stack (`docker compose`) |
| Python | **3.13 exactly** (`>=3.13,<3.14`) | Engine, API, tests. **3.14 is not supported** (see [Troubleshooting](#python-314-produces-a-broken-grid)) |
| Node.js | **>= 20** | Web app outside Docker, frontend tests, Playwright |
| Git | any | Clone the repo |

You only need Docker to *run* the app. Python and Node are needed for
development, tests or rebuilding the data.

---

## Quick start (Docker, one command)

A clean checkout already includes the built, frozen data the app serves: the
integrated feature table, the exclusions and the explanations. **You do not need
to rebuild the data to run the app.**

```bash
git clone https://github.com/F0rklift-Certified/opt-mining.git
cd opt-mining/app
docker compose -f docker-compose.yml up --build
```

This builds both services as production images and starts them:

- Web app (`web`): <http://localhost:3000>
- Decision service (`api`): <http://localhost:8000>, with Swagger UI at
  `/docs`, ReDoc at `/redoc` and the schema at `/openapi.json`

> Plain `docker compose up --build` also merges `docker-compose.override.yml`,
> which runs the **dev** servers with your source tree mounted. Use that only
> for development.

**Check that the running stack works** (from the repository root, with both
services up):

```bash
python app/smoke_test.py
```

The smoke test uses only the Python standard library. It checks the web page,
the browser CORS preflight and every real service operation. CI runs the same
check against the built containers.

To use different ports, see [Environment variables](#environment-variables).
For example:

```bash
API_HOST_PORT=9000 WEB_HOST_PORT=4000 \
NEXT_PUBLIC_API_BASE_URL=http://localhost:9000 \
CORS_ALLOW_ORIGINS=http://localhost:4000 \
docker compose -f docker-compose.yml up --build
```

---

## Local development without Docker

### 1. Python environment

From the repository root:

```bash
python3.13 -m venv .venv
source .venv/bin/activate                 # Windows: .venv\Scripts\activate
pip install -r requirements.txt           # engine deps (pandas, geopandas, rasterio, …)
pip install -r app/api/requirements.txt   # fastapi, uvicorn[standard]
pip install pytest==9.1.1                 # test runner (same pin as CI)
```

The repo-root `pyproject.toml` contains `[project]` metadata only, with **no
build system**, so the engine cannot be installed with `pip install -e`. Code
imports `pipeline` by putting the repository root on `PYTHONPATH`. pytest does
this automatically, and the API command below does it explicitly.

### 2. Start the API (terminal 1)

From **`app/api/`**:

```bash
CORS_ALLOW_ORIGINS=http://localhost:3000 PYTHONPATH=../.. uvicorn app:app --reload --port 8000
```

`CORS_ALLOW_ORIGINS` must match the browser's frontend origin exactly,
including the port. **If it is unset, the API accepts no browser origin.**

### 3. Start the web app (terminal 2)

From **`app/web/`**:

```bash
cp .env.example .env.local   # check NEXT_PUBLIC_API_BASE_URL points at the API
npm install
npm run dev                  # next dev -> http://localhost:3000
```

On first load, the page fetches the data-quality status and the sanity-check
result, then starts the packaged `wind_led` scenario.

### 4. Production build of the web app (optional)

```bash
cd app/web
npm run build    # NEXT_PUBLIC_API_BASE_URL is inlined at BUILD time
npm run start    # http://localhost:3000
```

Full detail on the web stack, including regenerating the typed client, is in
[`app/README.md`](app/README.md).

---

## Architecture

The system keeps a strict **data → criteria → scoring → presentation**
separation. The Python engine makes and records every decision. The API passes
those decisions through unchanged. The browser contains **no** scoring,
normalisation, ranking or exclusion logic, and front-end tests check for any
decision arithmetic.

```
raw sources (GWA, SRTM, NLUM, GA, AEMO, ABS, CAPAD, …)
        │
        ▼
pipeline/  ── python -m pipeline ──▶  frozen artefacts in DATA/
(probe → download → derive → features → grid → exclusions →
 integration → scoring → explanation → shortlist → validate → sanity)
        │
        ▼
pipeline.service  (Decision_Service: run, rank, explain, compare, quality, sanity)
        │   in-process Python calls
        ▼
app/api  (FastAPI: thin HTTP + OpenAPI wrapper, no decision logic)
        │   HTTP + OpenAPI contract
        ▼
app/web  (Next.js / React: typed client generated from the contract, decision-free)
```

The choice of web stack is recorded in
[`docs/adr/ADR-0003-web-stack-nextjs-fastapi-http-openapi.md`](docs/adr/ADR-0003-web-stack-nextjs-fastapi-http-openapi.md).
The service contract is in [`pipeline/service/CONTRACT.md`](pipeline/service/CONTRACT.md).

### Repository layout

```
opt-mining/
├── pipeline/                  # Geospatial pipeline + decision engine (Python package)
│   ├── __main__.py            #   `python -m pipeline` entry point / CLI
│   ├── config.py              #   stage registry (config.STAGES) and defaults
│   ├── wind/ geographic/      #   per-domain probe/download/inspect/derive/features
│   ├── infrastructure/ demand/
│   ├── grid/                  #   47,311-cell NSW analysis grid
│   ├── exclusions/            #   exclusion_rules.yaml + eligibility stage
│   ├── integration/           #   joins every layer by cell_id + confidence_weights.yaml
│   ├── scoring/               #   scoring_weights.yaml, scenarios.yaml, normalise/score/rank
│   ├── explanation/           #   explanation_templates.yaml + deterministic explainer
│   ├── shortlist/             #   top-N CSV / GeoJSON export
│   ├── sanity/                #   reality checks (terminal stage)
│   ├── service/               #   Decision_Service operations + CONTRACT.md
│   └── validate.py            #   structural cross-domain checks
├── app/
│   ├── api/                   # FastAPI Backend_App (app.py, models.py, settings.py, Dockerfile)
│   ├── web/                   # Next.js Frontend_App
│   │   ├── app/shell/         #   UI regions (map, shortlist, site detail, scenarios, sanity…)
│   │   ├── app/api/           #   the ONLY place that calls HTTP (decision-service.ts, generated.ts)
│   │   ├── openapi/           #   committed OpenAPI snapshot
│   │   ├── __tests__/ e2e/    #   Jest tests, Playwright happy path
│   │   └── Dockerfile
│   ├── docker-compose.yml     # production Compose stack
│   ├── docker-compose.override.yml  # dev servers with source mounted
│   ├── smoke_test.py          # stdlib-only check of a running stack
│   └── rehearse_demo.py       # drives the demo flow, records evidence JSON
├── DATA/                      # input and frozen derived datasets, with DATA_PROVENANCE.md per domain
│   ├── data-specification/    #   the Sprint 1 Data Specification (authoritative)
│   ├── wind-resource/ geographic/ infrastructure/ electricity-demand/
│   ├── grid/ exclusions/ integration/ scoring/ explanation/ shortlist/ sanity/
│   ├── sensitivity/           #   S4-08 sensitivity results
│   └── service/runs/          #   per-run cache written by the API (git-ignored)
├── scripts/                   # full-NSW data acquisition / rebuild runners, sensitivity analysis
├── tests/                     # pytest suite (per-domain, backend/stack, integration)
├── docs/
│   ├── technical-reference.md #   consolidated technical reference
│   ├── adr/                   #   architecture decision records
│   └── release/               #   demo script, limitations, verification evidence
├── outputs/                   # generated validation (sanity) report
├── Sprint-*-Tasks/            # sprint task sheets with completion evidence
├── requirements.txt           # pinned engine dependencies
├── pyproject.toml             # project metadata (Python 3.13 pin and why)
├── pytest.ini                 # markers (`integration` = Docker tier)
└── .github/workflows/ci.yml   # CI
```

The three top-level `Opt-Mining - *.md` files (Vision & Strategy, Product
Knowledge Base, AI Development Constitution) are the project's founding product
documents.

### Pipeline stages

`python -m pipeline` runs every stage in order. `--only` and `--skip` pick
stages or domains.

```
wind.probe → wind.download → wind.inspect → wind.validate → wind.analyse
→ geographic.probe → geographic.download → geographic.inspect → geographic.derive → geographic.validate
→ infrastructure.download → infrastructure.inspect
→ demand
→ grid                     common 0.05° analysis grid
→ wind.features            per-cell wind (consumes the grid)
→ geographic.features      per-cell elevation / slope / land use
→ infrastructure.features  per-cell distances to lines / substations
→ demand.feature           per-cell demand proxy
→ exclusions               eligibility per cell (S1-07)
→ integration              joins every layer by cell_id + composite data confidence (S1-08/09)
→ scoring                  weighted MCDA, rank, per-criterion contributions (S1-10)
→ explanation              deterministic explanation of every cell (S2-06)
→ shortlist                top-N eligible cells by rank → CSV + GeoJSON (S1-11)
→ validate                 structural cross-domain integrity checks
→ sanity                   plausibility checks against known reality, TERMINAL (S1-12)
```

Every stage reads what upstream stages left on disk. If an input is missing, the
stage stops and names the stage you need to run first. The full CLI, per-stage
design and expected outputs are in [`pipeline/README.md`](pipeline/README.md).

### Decision service API

`app/api/app.py` exposes the eight `pipeline.service` operations over HTTP. The
interactive docs at <http://localhost:8000/docs> are generated from the same
models.

| Method & path | Operation | Returns |
| ------------- | --------- | ------- |
| `POST /runs` | `run_analysis` | A Run handle for the given weights or named scenario. Runs are cached under `DATA/service/runs/<run_id>/` |
| `GET /runs/{run_id}/results` | `get_ranked_results` | Ranked eligible rows (score, rank, per-criterion values), with optional display filters |
| `GET /runs/{run_id}/sites/{cell_id}` | `get_site_detail` | One cell's full detail, including its verbatim explanation |
| `GET /runs/{run_id}/exclusions` | `get_exclusions` | Excluded cells with their reason codes and text |
| `GET /runs/{run_id}/cells` | `get_run_cells` | The Run's cells as a GeoJSON FeatureCollection, for the map |
| `POST /scenario-comparison` | `compare_scenarios` | Per-cell `rank_a` / `rank_b` / `rank_delta` for two weightings |
| `GET /data-quality` | `get_data_quality` | The frozen dataset's data-quality status and flags |
| `GET /sanity-check` | `get_sanity_check` | The baseline sanity result: caveat, four checks, known-wind-farm table, contradictions, lineage |

The `run_id` is a hash of the weights, the integrated input and the explanation
templates, so a rebuilt dataset never reuses an old run.
`DATA/service/runs/` is not tracked by git and can be deleted at any time. If
the engine output is missing or unreadable, the API returns **HTTP 503**.

### Web app

The page is a fixed shell of regions (`app/web/app/shell/`). Each one renders
values from the service as they arrive:

| Region | Component | What it shows |
| ------ | --------- | ------------- |
| Analysis controls | `AnalysisControls` | Pick a scenario or edit the six weights, then start a Run |
| Interactive map | `CellMap` (MapLibre) | Eligible and excluded cells over a configurable basemap, styled only from the served properties |
| Ranked shortlist | `RankedShortlist` + `shortlistExport` | Ranked rows. **CSV export** writes exactly what is on screen, with no recomputation |
| Site detail | `SiteDetailPanel`, `CellPicker` | The selected cell's values, explanation, caveats and confidence |
| Scenario comparison | `ScenarioComparison` | Rank changes between two weightings |
| Data quality | `DataQualityBanner` | The data-quality status and any flags |
| Sanity check | `SanityCheckPanel` | The caveat, PASS/FAIL for each check, the known-wind-farm table and contradictions. Shows a warning strip when the active run is not the unmodified baseline |

All HTTP calls go through `app/web/app/api/decision-service.ts`, which is built
on the generated types in `app/web/app/api/generated.ts`. New views should
import that module rather than call `fetch`.

---

## The scoring model

A transparent, deterministic **weighted multi-criteria decision analysis
(MCDA)**. For each eligible cell and criterion *i*:

```
norm_i    = (v_i - min_i) / (max_i - min_i)          direction higher_is_better
norm_i    = 1 - (v_i - min_i) / (max_i - min_i)      direction lower_is_better
contrib_i = weight_i * norm_i / W_cell
score     = SUM_i contrib_i                          -> [0, 1]
```

- **Bounds come from the eligible population on each run** and are never
  hard-coded, so a score is relative to the candidate set.
- **Only eligible cells are scored.** Excluded cells get a null score and a
  null rank.
- `rank` 1 is the highest-ranked cell. Ties are broken by ascending `cell_id`.
- Each `contrib_{criterion}` is stored and checked to sum back to the score.
- `wind_speed` is only ever an input, never a prediction target.

**Default weights** (from [`pipeline/scoring/scoring_weights.yaml`](pipeline/scoring/scoring_weights.yaml)).
These are user inputs: change them by editing the YAML or passing
`--scoring-weights PATH`. There are no constants in the code.

| Criterion | Default weight | Direction | Role |
|-----------|----------------|-----------|------|
| `wind_speed` | 0.35 | higher is better | primary resource indicator (mean, 100 m hub height) |
| `dist_transmission_km` | 0.20 | lower is better | connection cost (distance to ≥132 kV line) |
| `demand_proxy` | 0.15 | higher is better | offtake prospects (**proxy**) |
| `dist_substation_km` | 0.10 | lower is better | interconnection complexity |
| `slope_deg` | 0.10 | lower is better | civil-works cost / siting room |
| `inside_rez` | 0.10 | higher is better | REZ policy signal (boolean) |

Weights are relative, because the score divides by the sum of the applied
weights. They add up to 1.00 only to make them easier to read. The two named
scenarios, **Wind-led** and **Grid-led**, are weight sets in
[`pipeline/scoring/scenarios.yaml`](pipeline/scoring/scenarios.yaml).

**Exclusions.** Rules are data in
[`pipeline/exclusions/exclusion_rules.yaml`](pipeline/exclusions/exclusion_rules.yaml).
There are eight reason codes: `protected_area`, `missing_wind_data`,
`excessive_slope`, `urban_area`, `offshore_or_marine`, `missing_slope_data`,
`missing_demand_data` and `outside_nsw_land`. The last one applies when the cell
centre is outside the ABS NSW boundary, which also excludes the ACT.

The authoritative design is the
[Decision-Engine Specification](Sprint-2-Tasks/decision_engine_specification.md).
Any change to a frozen scoring decision must be applied to the specification,
the weights YAML and the data specification (§4.7) together.

---

## Data, provenance and assumptions

- **Every dataset** (source, variables, units, CRS, resolution, temporal
  coverage, licence, limitations, pipeline use) is recorded in the
  [Sprint 1 Data Specification](DATA/data-specification/sprint1_data_specification.md).
- **Generated provenance for each domain** (SHA-256 of inputs and outputs,
  regeneration command) is in the `DATA/*/DATA_PROVENANCE.md` files.
- **Seven frozen team decisions** (data specification §2):
  1. Wind aggregation statistic: mean
  2. Hub height: 100 m
  3. Slope statistic: mean for scoring, P90 in explanations
  4. Population source: ABS Census 2021 ERP at SA2
  5. Demand metric: AEMO operational demand
  6. Protected-area exclusion: binary
  7. Infrastructure distance: a continuous penalty, never a hard exclusion

Data licences differ by source. Check the data specification before you
redistribute anything under `DATA/`.

---

## Environment variables

No host address or origin is hard-coded. Defaults are the `${VAR:-default}`
values in [`app/docker-compose.yml`](app/docker-compose.yml).

| Variable | Used by | Default | Purpose |
| -------- | ------- | ------- | ------- |
| `NEXT_PUBLIC_API_BASE_URL` | Web (browser) | `http://localhost:8000` | URL the **browser** uses to reach the API. **Inlined at build time**, so rebuild after changing it |
| `NEXT_PUBLIC_BASEMAP_TILE_URL` | Web (browser) | `https://tile.openstreetmap.org/{z}/{x}/{y}.png` | XYZ basemap tiles. Public OSM tiles are for development only and **must** be replaced for any deployment (OSM tile policy) |
| `CORS_ALLOW_ORIGINS` | API | `http://localhost:3000` (Compose) / *unset = none* (bare uvicorn) | Comma-separated list of allowed browser origins |
| `API_HOST_PORT` | Compose | `8000` | Host port for the API |
| `WEB_HOST_PORT` | Compose | `3000` | Host port for the web app |
| `API_INTERNAL_URL` | Compose | `http://api:8000` | URL for server-side calls inside the Compose network. Reserved: no code reads it today |
| `E2E_BASE_URL` | Playwright | `http://localhost:3000` | Web app URL the browser tests run against |

For the web app outside Docker, put these in `app/web/.env.local` (start from
[`app/web/.env.example`](app/web/.env.example)). For Compose, export them or put
them in `app/.env`.

---

## Command reference

| Command | Run from | What it does |
| ------- | -------- | ------------ |
| `docker compose -f docker-compose.yml up --build` | `app/` | Build and start the production stack |
| `docker compose up --build` | `app/` | Start the dev stack (override file, source mounted) |
| `python app/smoke_test.py` | root | Check a running stack (web, CORS, every operation) |
| `python app/rehearse_demo.py --output docs/release/rehearsal.json` | root | Run the demo flow against a running stack and record evidence |
| `PYTHONPATH=../.. uvicorn app:app --reload --port 8000` | `app/api/` | API dev server (set `CORS_ALLOW_ORIGINS`) |
| `npm run dev` / `build` / `start` | `app/web/` | Next.js dev / production build / serve |
| `npm test -- --runInBand` | `app/web/` | Jest unit and component tests |
| `npm run typecheck` | `app/web/` | `tsc --noEmit` |
| `npm run e2e` | `app/web/` | Playwright browser tests (needs a running stack) |
| `npm run generate:api-client` | `app/web/` | Re-export the OpenAPI snapshot and regenerate the TS types |
| `python -m pipeline` | root | Full pipeline from raw data to the sanity report |
| `python -m pipeline --only <domain\|stage>` | root | Re-run one domain or stage against existing upstream outputs |
| `python -m pipeline --only scoring --scoring-weights my.yaml` | root | Re-score with custom weights |
| `python -m pipeline --only shortlist --shortlist-top-n 50` | root | Change the shortlist size |
| `python -m scripts.sensitivity_analysis` | root | S4-08 weight-sensitivity analysis → `DATA/sensitivity/` |
| `pytest -v -m "not integration" tests/backend` | root | Backend gate (fast, no Docker) |
| `pytest -v -m "not integration" --ignore=tests/backend` | root | Every other non-Docker test |
| `pytest -m integration` | root | Docker/Compose-tier tests (opt-in) |

---

## Testing

### Python

```bash
# fast suite, no Docker: the backend gate first, then everything else (same order as CI)
pytest -v -m "not integration" tests/backend
pytest -v -m "not integration" --ignore=tests/backend

# Docker/Compose tier: brings the stack up on ports 18000/13000, then tears it down
pytest -m integration
```

The `integration` marker (registered in `pytest.ini`) is **reserved for
Docker/Compose tests**. When Docker is unavailable, those tests are skipped with
a clear reason rather than failing.

**End-to-end test (data → engine → app), no network and no Docker:**
[`tests/integration/test_e2e_dataset_engine_app.py`](tests/integration/test_e2e_dataset_engine_app.py)
drives the FastAPI app through `TestClient`. It creates a Run over the committed
frozen dataset and checks four things:

- ranked results are in rank order, with scores in `[0, 1]`
- site detail matches the ranked row and carries the verbatim explanation
- frozen exclusions are surfaced
- the data-quality verdict is surfaced

```bash
pytest -v -m "not integration" --ignore=tests/backend tests/integration/test_e2e_dataset_engine_app.py
```

**Documentation guards.** Some tests read the docs themselves:

- `tests/backend/test_s309_docs_consistency.py` checks the screening-level
  wording and the demand-proxy framing in `pipeline/README.md`,
  `app/README.md` and `docs/release/`.
- `tests/shortlist/test_shortlist_docs_consistency.py` checks that the
  stage-order block in `pipeline/README.md` matches `config.STAGES`.
- `tests/backend/test_adr_and_run_commands_docs.py` checks that the run
  commands documented in `app/README.md` match reality.

If you edit those files, run the guards.

### Frontend

```bash
cd app/web
npm ci
npm test -- --runInBand     # components, typed-client operations, "no decision math" scope guard
npm run typecheck
npm run build
```

`__tests__/scope-guard.test.ts` fails if decision arithmetic appears in the UI.
The backend suite fails if the committed OpenAPI snapshot drifts from the live
app; regenerate it with `npm run generate:api-client`.

### Browser end-to-end (Playwright)

```bash
# with the stack running (see Quick start)
cd app/web
npx playwright install --with-deps chromium   # first time only
npm run e2e                                   # E2E_BASE_URL defaults to http://localhost:3000
```

---

## Continuous integration

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs three jobs:

1. **Test (Python 3.13)**: installs the engine, API and test dependencies, then
   runs the backend gate followed by the remaining non-Docker tests.
2. **Docker Compose build**: builds the production images, starts the stack,
   runs `app/smoke_test.py`, then runs the Playwright happy path against the
   containers. On failure it uploads the Playwright report and prints the
   container logs.
3. **Frontend (Node 20)**: `npm ci`, Jest, type-check, `next build`.

---

## Rebuilding the data

This step is optional. The committed artefacts are enough to run the app.

```bash
source .venv/bin/activate
python -m pipeline              # raw → grid → features → exclusions → … → shortlist → validate → sanity
python -m pipeline --verbose    # with detailed logging
```

Run a subset:

```bash
python -m pipeline --only grid          # grid first if it is missing
python -m pipeline --only integration   # re-join already-built layers
python -m pipeline --skip wind          # skip a domain
```

The full-NSW geographic rasters (SRTM, NLUM) and connection-point data come
from dedicated runners in [`scripts/`](scripts/README.md). They need network
access, and some downloads are large (NLUM is about 64 MB). Their `*_nsw.tif`
outputs go over the repo's 10 MB commit limit, so **do not commit them**.

```bash
.venv/bin/python -m scripts.fetch_build_geographic_nsw --verbose
.venv/bin/python -m scripts.refreeze_revalidate --verbose
```

After you rebuild the data, **rebuild the API image**, because the image bakes
in the frozen integration, exclusion and explanation datasets.

---

## Sensitivity analysis

`python -m scripts.sensitivity_analysis` re-scores the frozen integrated table
with the real engine. It varies each weight by ±10 % and ±20 % one at a time,
and also runs both named scenarios. Each run is compared with the baseline:
Spearman and Kendall correlation, top-20 and top-50 overlap, rank-1 stability,
and the largest shift within the top 20. It also lists which cells stay robust
in the top 20 and which are sensitive to the weights. The engine's outputs are
never modified.

Results: [`DATA/sensitivity/optmining_sensitivity_2026_nsw.md`](DATA/sensitivity/optmining_sensitivity_2026_nsw.md)
(plus `.json`). In brief:

- The baseline ranking is stable under ±20 % changes to any single weight. The
  Spearman correlation stays at or above 0.996, and the top-20 overlap stays at
  or above 0.90.
- Switching to the **Wind-led** scenario changes the shortlist substantially:
  only half of the baseline top 20 remains.

---

## Deployment

The repository ships production Docker images (`app/api/Dockerfile` and
`app/web/Dockerfile`), wired together by `app/docker-compose.yml`. It has no
cloud-specific deployment config. To deploy on any Docker host:

1. Set `NEXT_PUBLIC_API_BASE_URL` to the **public** API URL *before* building,
   because it is inlined into the web bundle.
2. Set `CORS_ALLOW_ORIGINS` to the public web origin.
3. Point `NEXT_PUBLIC_BASEMAP_TILE_URL` at a tile provider you are licensed to
   use. Do not use the public OSM tiles.
4. `docker compose -f docker-compose.yml up --build -d` from `app/`, then run
   `python app/smoke_test.py` against the deployed URLs (it reads the same two
   variables).
5. Put a TLS-terminating reverse proxy in front of both services. Neither
   service handles TLS or authentication itself.

The API writes run caches to `DATA/service/runs/`. You can mount a volume there
to keep them, or let them be rebuilt on demand.

---

## Troubleshooting

### Python 3.14 produces a broken grid

On CPython 3.14 the grid builder produces degenerate zero-area cells: every cell
collapses to a point, which breaks every downstream layer. Use **Python 3.13**.
The pin in `pyproject.toml` explains this in full.

### Web page shows `Failed to fetch` / `ERR_CONNECTION_REFUSED`

1. From `app/`: `docker compose ps -a` and `docker compose logs api`.
2. Check that <http://localhost:8000/docs> loads.
3. Outside Docker, check that the API was started with
   `CORS_ALLOW_ORIGINS=http://localhost:3000` (it must match the web origin and
   port exactly), and that `app/web/.env.local` exists with the right
   `NEXT_PUBLIC_API_BASE_URL`.
4. After you change the API URL, **restart or rebuild the web app**. The URL is
   inlined at build time.

### Data-quality flags are showing

Data-quality flags come from the validation report and describe the dataset. A
flag does **not** mean the connection failed.

### `ModuleNotFoundError: No module named 'pipeline'`

Run the API from `app/api/` with `PYTHONPATH=../..`, and run pytest from the
repository root. The engine cannot be `pip install`ed (there is no build
system).

### A stage stops with "missing input"

Stages read upstream outputs from disk. Run the stage the error names. A common
case is `python -m pipeline --only grid` before `--only wind` or
`--only geographic`.

### Ports 8000 / 3000 are already in use

Override `API_HOST_PORT` / `WEB_HOST_PORT`, and update
`NEXT_PUBLIC_API_BASE_URL` and `CORS_ALLOW_ORIGINS` to match. See
[Environment variables](#environment-variables).

### Running the tests changed files under `DATA/`

Some test stages regenerate feature-table outputs when real source data is
present. Check `git status` after a full run and restore anything you did not
mean to change with `git checkout -- DATA/`.

### Disk space under `DATA/service/runs/`

That directory is only a cache of Runs. Delete it whenever you like; Runs are
recreated on demand.

---

## Limitations

- **Screening-level only.** The tool surfaces candidates for further
  investigation. It never claims a "best site", never approves a site and never
  provides an engineering assessment.
- **Relative scores.** Min-max normalisation over the eligible population means
  a score is relative to the candidate set. It is not a portable absolute
  rating.
- **Demand is a proxy.** NEM-region demand is spread by distance to recorded
  zone-substation load and ranked within the region. It is never measured local
  demand.
- **Coarse border handling.** A cell is in or out of NSW by its centre point, so
  border and coastal cells can straddle the boundary. ACT cells are excluded.
- **Connection-point distance is unavailable.** `dist_connection_km` is null for
  every cell, so it is shown as context only and never scored.
- **Linear normalisation, no cost, yield or engineering-grade modelling**, at
  **~5 km resolution**. Mean-wind aggregation hides ridge-scale signals within a
  cell.

The full list is in [`docs/release/limitations.md`](docs/release/limitations.md)
and [`docs/technical-reference.md`](docs/technical-reference.md).

---

## Further documentation

| Document | Contents |
| -------- | -------- |
| [`docs/technical-reference.md`](docs/technical-reference.md) | **The consolidated reference**: architecture, provenance, assumptions, equations, exclusions, weights, limitations |
| [`pipeline/README.md`](pipeline/README.md) | Pipeline CLI, every stage's design, expected outputs, data sources |
| [`app/README.md`](app/README.md) | Web stack: run commands, environment, typed-client regeneration, stack tests |
| [`pipeline/service/CONTRACT.md`](pipeline/service/CONTRACT.md) | Decision_Service operation contract |
| [`Sprint-2-Tasks/decision_engine_specification.md`](Sprint-2-Tasks/decision_engine_specification.md) | Authoritative scoring and exclusion design |
| [`DATA/data-specification/sprint1_data_specification.md`](DATA/data-specification/sprint1_data_specification.md) | Authoritative dataset specification and frozen decisions |
| [`docs/release/`](docs/release/README.md) | Demo script, limitations, verification and rehearsal evidence |
| [`scripts/README.md`](scripts/README.md) | Full-NSW data acquisition and re-freeze runners |
| [`docs/demand-proxy-spatial-weighting-history.md`](docs/demand-proxy-spatial-weighting-history.md) | How the demand proxy's spatial weighting evolved |
| `Sprint-*-Tasks/` | Sprint task sheets with completion evidence |
