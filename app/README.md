# Opt-Mining Web Stack (S3-01a — Application Shell Scaffold)

This directory holds the MVP web stack for the Opt-Mining decision tool:

- **`api/`** — the FastAPI **Backend_App**. It exposes the six frozen S2-08
  `Decision_Service` operations over HTTP and publishes an auto-generated
  OpenAPI schema. It **delegates every operation to `pipeline.service`** and
  holds no decision logic of its own (combined-sprint AC4 / `CONTRACT.md` §1).
- **`web/`** — the Next.js/React **Frontend_App**. A thin, decision-free shell
  that lays out four labelled placeholder regions (analysis controls,
  interactive map, ranked results, site detail/explanation) and reads the
  backend URL from an environment variable. The region is fixed to **NSW**.
- **`docker-compose.yml`** — the **Compose_Stack** that builds and starts both
  apps with a single command.

The typed service client and the data-quality banner are **S3-01b**, not this
scaffold.

---

## Prerequisites

| Stack        | Requirement                                                              |
| ------------ | ------------------------------------------------------------------------ |
| Backend      | Python **3.13** (`>=3.13,<3.14` — the engine does not support 3.14)      |
| Frontend     | Node **>= 20**                                                           |
| Full stack   | Docker + Docker Compose v2 (`docker compose`)                            |

---

## Run commands

### Backend (dev)

Run from **`app/api/`**:

```bash
PYTHONPATH=../.. uvicorn app:app --reload --port 8000
```

The `PYTHONPATH=../..` prefix puts the **repository root** on the import path so
`import pipeline.service` resolves. This is required because the repo-root
`pyproject.toml` declares `[project]` metadata only — it has **no
`[build-system]` and no package discovery** — so the engine cannot be installed
with `pip install -e`. Putting the repo root on `PYTHONPATH` mirrors how the
repo's own pytest suite imports `pipeline` today. See
[`api/requirements.txt`](api/requirements.txt) for the full rationale.

You also need the engine's runtime dependencies (from the repo-root
`requirements.txt`) and the API's own dependencies installed:

```bash
# from the repository root, in your virtualenv
pip install -r requirements.txt          # engine deps (pandas, geopandas, …)
pip install -r app/api/requirements.txt  # fastapi, uvicorn[standard]
```

Once running, the OpenAPI docs are reachable at:

- Swagger UI: <http://localhost:8000/docs>
- OpenAPI schema (JSON): <http://localhost:8000/openapi.json>
- ReDoc: <http://localhost:8000/redoc>

### Frontend (dev)

Run from **`app/web/`**:

```bash
npm install
npm run dev        # -> next dev  (http://localhost:3000)
```

Copy the env template first and point it at your backend:

```bash
cp .env.example .env.local   # then edit NEXT_PUBLIC_API_BASE_URL if needed
```

### Frontend (built / production)

Run from **`app/web/`**:

```bash
npm run build      # -> next build
npm run start      # -> next start (http://localhost:3000)
```

`NEXT_PUBLIC_API_BASE_URL` is inlined at **build time**, so set it before
`next build` if the production backend URL differs from the default.

### Whole stack (single command)

Run from **`app/`**:

```bash
docker compose up --build
```

This builds and starts both services in one command:

- Backend (`api`) published on the host at <http://localhost:8000> (`/docs`,
  `/openapi.json` reachable there).
- Frontend (`web`) published on the host at <http://localhost:3000>.

`web` starts after `api` (`depends_on`). The API Dockerfile builds with the
**repository root** as its build context (so the `pipeline/` package and the
root `requirements.txt` are reachable); this is wired for you in
[`docker-compose.yml`](docker-compose.yml).

---

## Environment variables

Every cross-service URL, origin, and host port flows through an environment
variable — **no host address or origin literal is baked into source**. Defaults
below are the `${VAR:-default}` values wired in
[`docker-compose.yml`](docker-compose.yml).

| Variable                   | Consumer            | Default                  | Purpose                                                                                     |
| -------------------------- | ------------------- | ------------------------ | ------------------------------------------------------------------------------------------- |
| `NEXT_PUBLIC_API_BASE_URL` | Frontend (browser)  | `http://localhost:8000`  | The URL the **browser** uses to reach the API. Inlined at Next.js build time. See [`web/.env.example`](web/.env.example). |
| `CORS_ALLOW_ORIGINS`       | Backend (FastAPI)   | `http://localhost:3000`  | Comma-separated list of allowed CORS origins (the web app's origin). Parsed by `api/settings.py`. |
| `API_HOST_PORT`            | Compose             | `8000`                   | Host port the API is published on.                                                          |
| `WEB_HOST_PORT`            | Compose             | `3000`                   | Host port the web app is published on.                                                      |

There are two distinct notions of the backend URL and the stack keeps both
explicit:

- **`NEXT_PUBLIC_API_BASE_URL`** is the **browser-reachable** URL (a published
  host port).
- **`API_INTERNAL_URL`** (default `http://api:8000`, wired in
  `docker-compose.yml`) is the **in-network** Compose service-name URL used by
  any server-side call. This ticket's frontend makes no calls yet, so it is
  wired and documented for S3-01b to inherit.

To override a default for the whole stack, set the variable in the environment
(or an `app/.env` file) before `docker compose up --build`, e.g.:

```bash
API_HOST_PORT=9000 WEB_HOST_PORT=4000 docker compose up --build
```

---

## Tests

The backend/stack tests live under `tests/backend/` and run with `pytest` from
the repository root.

### Fast unit suite (default)

```bash
pytest tests/backend -m "not integration"
```

This excludes the slow, CI-tier `integration`-marked tests (see below), so it
stays fast and needs no Docker.

### CI-tier stack integration test

`tests/backend/test_compose_stack_integration.py` brings the whole stack up with
the single documented command (`docker compose up --build`), health-checks that
both `web` and `api` come up, confirms the browser-facing API host port answers
`/openapi.json` with `200`, and always tears the stack down afterwards. It is
marked `@pytest.mark.integration` (registered in the repo-root `pytest.ini`) so
it does **not** run in the fast unit suite.

```bash
pytest -m integration            # run only the CI-tier integration test(s)
pytest -m "not integration"      # exclude them (the fast suite)
```

When Docker is unavailable — the `docker` CLI is missing, the Compose v2 plugin
is absent, or the Docker daemon is not running — the test **skips with a clear
reason** rather than failing. It runs for real in CI, where Docker is present.
To avoid clashing with anything already bound on the default `8000`/`3000`, it
publishes the stack on host ports `18000`/`13000` (driven through the same
documented `API_HOST_PORT` / `WEB_HOST_PORT` env vars the Compose file reads).
