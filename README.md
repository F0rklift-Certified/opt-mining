# Opt-Mining

Preliminary **screening** tool for onshore wind siting in New South Wales. It
builds a per-cell feature dataset on a ~5 km (0.05°) analysis grid, applies
exclusions, scores and ranks the eligible cells with a transparent weighted
multi-criteria model, explains every cell, and serves the result through an API
and a thin web client.

> ⚠️ **Screening-level tool — read this first.** Opt-Mining surfaces
> higher-ranked candidate cells for *further investigation* under a selected set
> of assumptions and criteria. It does **not** identify "the best site to build a
> wind farm", a "best place to build", an optimal location or a final
> recommendation, and it is never a site approval, a project cost, an LCOE, an
> energy-yield estimate or an engineering-grade assessment. Results are produced
> at the analysis-grid resolution and indicate only *where to look next*.

> ⚠️ **The electricity demand layer is a PROXY.** `demand_proxy` is a spatial
> proxy *indicator* — each NEM region's annual-mean operational demand is spread
> across its cells by distance to real NSW zone substations weighted by their
> recorded load (`load_weighted`), then expressed as a **percentile within the
> region** (0–1, a rank position, not a magnitude). It is **never** measured or
> actual local demand at a cell. See
> [`DATA/electricity-demand/demand_feature_method.md`](DATA/electricity-demand/demand_feature_method.md).

The architecture follows a strict **data → criteria → scoring → presentation**
separation: the engine makes every decision and records it; the browser contains
no scoring, normalisation, ranking or exclusion logic.

```
raw data ─▶ pipeline/engine (Python) ─▶ frozen integrated dataset
                                          │
                                          ▼
                         Decision_Service (FastAPI + OpenAPI, pipeline.service)
                                          │
                                          ▼
                            web app (Next.js / React, decision-free client)
```

---

## 1. End-to-end integration test (data → engine → app)

A single in-process test exercises the whole chain — the **frozen integrated
dataset** → the **decision engine** (score / rank / explain / exclude) → the
**API/app output** (the published FastAPI `Decision_Service`, the exact contract
the web client is generated from) — with **no network and no Docker**:

- [`tests/integration/test_e2e_dataset_engine_app.py`](tests/integration/test_e2e_dataset_engine_app.py)

It drives the FastAPI app through `TestClient`: creates a Run over the committed
frozen dataset, asserts the ranked results are rank-ordered with scores in
`[0, 1]`, confirms site detail agrees with the ranked row for the same cell and
carries the verbatim S2-06 explanation (the one-engine-output guarantee), and
checks that frozen exclusions and the data-quality verdict are surfaced. The
inputs are git-tracked, so the test runs in CI as well as locally.

**Run it:**

```bash
# from the repository root, in your virtualenv (see §2)
pytest -v -m "not integration" --ignore=tests/backend tests/integration/test_e2e_dataset_engine_app.py
```

The test carries **no** `integration` marker on purpose — that marker is
reserved for Docker/Compose-tier tests, which CI runs separately — so it is
collected by CI's "Run remaining non-Docker tests" step
(`pytest -v -m "not integration" --ignore=tests/backend`) rather than being
silently skipped. CI configuration: [`.github/workflows/ci.yml`](.github/workflows/ci.yml).

A docs-consistency guard, [`tests/backend/test_s309_docs_consistency.py`](tests/backend/test_s309_docs_consistency.py),
additionally enforces the screening-level language and demand-proxy framing in
the documentation so neither can silently regress.

---

## 2. Clean-environment install & run

A clean checkout already ships the built, frozen artefacts the app serves, so
you do **not** need to rebuild the data to run the application.

### Prerequisites

| Stack      | Requirement                                                         |
| ---------- | ------------------------------------------------------------------- |
| Engine     | Python **3.13** (`>=3.13,<3.14` — the engine does not support 3.14) |
| Frontend   | Node **>= 20**                                                      |
| Full stack | Docker + Docker Compose v2 (`docker compose`)                       |

### Run the application stack (single command)

From **`app/`**:

```bash
docker compose -f docker-compose.yml up --build
```

This builds and starts both services as production images. (Plain
`docker compose up --build` also merges `docker-compose.override.yml`, which runs
the **dev** servers with your source tree mounted — use that only for
development.)

- Frontend (`web`) on <http://localhost:3000>
- Backend (`api`) on <http://localhost:8000> (`/docs`, `/openapi.json` there)

Every host port and cross-service URL is driven by environment variables
(`API_HOST_PORT`, `WEB_HOST_PORT`, `NEXT_PUBLIC_API_BASE_URL`,
`CORS_ALLOW_ORIGINS`, `NEXT_PUBLIC_BASEMAP_TILE_URL`, …) — no address is baked
into source. If `CORS_ALLOW_ORIGINS` is unset the API allows **no** browser
origin. Full table, override examples and the **non-Docker** start commands
(uvicorn + `npm run dev`) are in [`app/README.md`](app/README.md).

Each analysis run is stored under `DATA/service/runs/<run_id>/` (not tracked by
git). The run id hashes the weights, the integrated input and the explanation
templates, so a rebuilt dataset never reuses an old run; the folder can be
deleted at any time to reclaim space.

**Verify the running stack** (with both services up, from the repository root):

```bash
python app/smoke_test.py
```

This exercises the web page, the browser CORS preflight and all real service
operations. CI runs the same check against the built Compose containers.

### Rebuild the frozen data from raw sources (optional)

The pipeline runs raw data → ranked shortlist and sanity check with a **single
command**:

```bash
# from the repository root
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt      # engine deps (pandas, geopandas, …)
pip install -r app/api/requirements.txt pytest==9.1.1   # API + test runner

python -m pipeline                   # the one documented full-run command
```

`--only <domain|stage>` re-runs a single stage against already-built upstream
artefacts. Full stage list, CLI options and the per-stage design are in
[`pipeline/README.md`](pipeline/README.md).

### Run the tests

```bash
# fast suite (no Docker): backend gate, then everything else
pytest -v -m "not integration" tests/backend
pytest -v -m "not integration" --ignore=tests/backend

# Docker/Compose-tier integration tests (opt-in)
pytest -m integration

# frontend, from app/web/
npm ci && npm test -- --runInBand && npm run typecheck && npm run build
```

The full install, run and verification matrix CI uses is in
[`.github/workflows/ci.yml`](.github/workflows/ci.yml).

---

## 3. Consolidated documentation

The single consolidated technical reference — **architecture, data provenance,
assumptions, scoring equations, exclusions, default weights and limitations** —
is [`docs/technical-reference.md`](docs/technical-reference.md). It links the
authoritative source documents rather than duplicating their frozen tables. A
quick orientation:

### Architecture

Three decision-free layers behind a strict data → criteria → scoring →
presentation boundary (HTTP + OpenAPI between engine and app):

- Pipeline / engine (Python) — [`pipeline/README.md`](pipeline/README.md)
- Decision service (FastAPI + OpenAPI, `pipeline.service`) —
  [`docs/adr/ADR-0003-web-stack-nextjs-fastapi-http-openapi.md`](docs/adr/ADR-0003-web-stack-nextjs-fastapi-http-openapi.md)
- Web app (Next.js / React) — [`app/README.md`](app/README.md)

### Scoring equations

A transparent, deterministic **weighted MCDA** (not a machine-learning model).
For each eligible cell and criterion *i*:

```
norm_i    = (v_i - min_i) / (max_i - min_i)          direction higher_is_better
norm_i    = 1 - (v_i - min_i) / (max_i - min_i)      direction lower_is_better
contrib_i = weight_i * norm_i / W_cell
score     = SUM_i contrib_i                          -> [0, 1]
```

Normalisation bounds are computed from the **eligible** population on each run —
never hard-coded — so a score is relative to the candidate set. `rank` 1 is the
highest-ranked cell; ties break by ascending `cell_id`. Authoritative sources:
[Decision-Engine Specification](Sprint-2-Tasks/decision_engine_specification.md),
data specification §4.7, and the formula header in
[`pipeline/scoring/scoring_weights.yaml`](pipeline/scoring/scoring_weights.yaml).

### Default weights

Defaults from [`pipeline/scoring/scoring_weights.yaml`](pipeline/scoring/scoring_weights.yaml)
(user inputs — retune by editing the YAML, not hard-coded constants):

| Criterion | Default weight | Direction | Role |
|-----------|----------------|-----------|------|
| `wind_speed` | 0.35 | higher is better | primary resource indicator |
| `dist_transmission_km` | 0.20 | lower is better | connection cost (≥132 kV line distance) |
| `demand_proxy` | 0.15 | higher is better | offtake prospects (**proxy**) |
| `dist_substation_km` | 0.10 | lower is better | interconnection complexity |
| `slope_deg` | 0.10 | lower is better | civil-works cost / siting room |
| `inside_rez` | 0.10 | higher is better | REZ policy signal (boolean) |

Weights are relative (the score divides by the sum of applied weights), so
summing to 1.00 is for readability only.

### Exclusions

Only eligible cells are scored; the exclusion layer rejects ineligible land in a
separate, auditable stage (rules are data in
[`pipeline/exclusions/exclusion_rules.yaml`](pipeline/exclusions/exclusion_rules.yaml)).
The eight reason codes: `protected_area`, `missing_wind_data`,
`excessive_slope`, `urban_area`, `offshore_or_marine`, `missing_slope_data`,
`missing_demand_data` and `outside_nsw_land` (cell centre outside the ABS NSW
boundary, added for QA F-01). On the current baseline 23,266 of 47,311 cells are
eligible. Authoritative source: decision-engine specification §6.5.

### Data provenance

Every dataset (custodial and derived) is recorded in the
[Sprint 1 Data Specification](DATA/data-specification/sprint1_data_specification.md)
(source, variables, units, CRS, resolution, temporal coverage, licence,
limitations, pipeline use). Per-domain generated provenance (SHA-256, inputs,
regeneration command) lives in the `DATA/*/DATA_PROVENANCE.md` files.

### Assumptions

Seven frozen team decisions (data specification §2): wind aggregation statistic
(mean), hub height (100 m), slope statistic (mean for scoring / P90 in
explanation), population source (ABS Census 2021 ERP at SA2), demand metric
(AEMO operational demand), protected-area exclusion (binary), and infrastructure
distance (continuous penalty, no hard exclusion).

### Limitations

- **Screening-level only** — surfaces candidates for further investigation, never
  a "best site" claim, a site approval or an engineering assessment.
- **Relative scores** — min-max over the eligible population; a score is relative
  to the candidate set, not a portable absolute rating.
- **Demand is a proxy** — NEM-region demand spread by distance to recorded
  zone-substation load and ranked within the region; never measured local demand.
- **Coarse border handling** — a cell is in or out of NSW by its centre point, so
  border and coastal cells can straddle the boundary. ACT cells are excluded.
- **Connection-point distance is unavailable** — `dist_connection_km` is null for
  every cell, so it is context only and never scored.
- **Linear normalisation**, **no cost/yield/engineering-grade modelling**, at
  **~5 km resolution** (mean-wind aggregation buries sub-cell ridge signals).

Full detail and the authoritative links for all of the above are in
[`docs/technical-reference.md`](docs/technical-reference.md).

---

## Repository layout

| Path | Contents |
|------|----------|
| [`pipeline/`](pipeline/README.md) | Modular geospatial pipeline / decision engine |
| [`app/`](app/README.md) | FastAPI `Decision_Service` + Next.js web client + Compose stack |
| `DATA/` | Input and frozen derived datasets, with provenance per domain |
| [`docs/`](docs/technical-reference.md) | Consolidated technical reference and ADRs |
| [`docs/release/`](docs/release/README.md) | Release evidence: demo script, limitations, AC-evidence matrix, rehearsal & verification |
| [`scripts/`](scripts/README.md) | Data acquisition / rebuild runners and the S4-08 sensitivity analysis (`python -m scripts.sensitivity_analysis`) |
| `outputs/` | Generated sanity-check (validation) report |
| `Sprint-*-Tasks/` | Sprint task sheets with completion evidence; Sprint 4 holds the final backlog |
| `tests/` | Pytest suite, including the end-to-end integration test |
| `app/web/e2e/` | Playwright browser end-to-end tests (`npm run e2e` against a running stack) |
| [`.github/workflows/ci.yml`](.github/workflows/ci.yml) | CI: tests, Docker build + smoke test, frontend |
