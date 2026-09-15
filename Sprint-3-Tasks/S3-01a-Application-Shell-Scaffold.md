# S3-01a: Application Shell Scaffold (Next.js/React + FastAPI)

**Type:** Story
**Priority:** Highest
**Story Points:** 3
**Labels:** web-app, frontend, backend, architecture, nextjs, react, fastapi
**Blocked by:** S2-08
**Blocks:** S3-01b

---

> **Split note:** First half of the former **S3-01**. S3-01a scaffolds the decided stack and stands up the app shell + run commands; S3-01b wires the service client and the data-quality banner.

> **Stack decision (agreed):** A **React / Next.js** frontend and a **FastAPI** backend, communicating over **HTTP** with an **OpenAPI**-described contract. This resolves the previously-open framework question and fixes the S2-08 service boundary as HTTP (not an in-process module). This is a documented architecture decision for the MVP, recorded in [ADR-0003: Web stack — React/Next.js + FastAPI over HTTP/OpenAPI](../docs/adr/ADR-0003-web-stack-nextjs-fastapi-http-openapi.md).

## Objective

Scaffold the decided web stack — a Next.js/React frontend and a FastAPI backend — and stand up a lightweight application shell with placeholder regions for controls, map, ranked results and site detail, runnable from documented commands. The whole stack must also start with a single command via **Docker Compose**.

---

## Context

Guidance Step 8. The guidance explicitly permits "a separated frontend/backend if already justified by the team's architecture" — that is the path chosen here. The stack is decided before service integration (S3-01b) because it constrains every later UI ticket (S3-02 through S3-06) and fixes the S2-08 service form as HTTP. The interface prioritises functionality and clarity over visual effects, and the region is fixed to NSW for the MVP.

---

## Deliverables

1. A FastAPI backend project scaffold exposing the S2-08 decision-service operations over HTTP, publishing an OpenAPI schema.
2. A Next.js/React frontend project scaffold with the four placeholder regions.
3. Documented run commands for both apps (dev and a clean-environment start).
4. A **Docker Compose** setup (a `docker-compose.yml` plus a `Dockerfile` per app) that builds and starts the full stack — frontend and backend — with a single command.
5. An Architecture Decision Record noting the React/Next.js + FastAPI choice and its rationale.

---

## Acceptance Criteria

- [ ] The app is a **browser-based web application** (Next.js/React frontend), not a desktop executable
- [ ] A **FastAPI** backend scaffold exposes the S2-08 decision-service operations over HTTP and publishes an **OpenAPI** schema (e.g. at `/openapi.json` / `/docs`)
- [ ] The **Next.js/React** frontend scaffold contains placeholder regions for: analysis controls, interactive map, ranked results, site detail/explanation
- [ ] The frontend↔backend boundary is HTTP; the frontend holds no decision logic (integration proper is S3-01b)
- [ ] Region is fixed to NSW for the MVP
- [ ] Both apps run from **documented commands** in a clean environment (e.g. `uvicorn` for the API, `next dev`/`next start` for the frontend)
- [ ] The **entire stack starts with a single command** via Docker Compose (e.g. `docker compose up`), bringing up both the frontend and the backend; a `docker-compose.yml` and a `Dockerfile` per app are committed
- [ ] The Compose setup wires the frontend↔backend over HTTP using service-based URLs (no hard-coded host addresses) and exposes both apps on documented host ports
- [ ] The stack decision and rationale are recorded (short ADR referenced from the Sprint 3 docs)
- [ ] Interface prioritises functionality and clarity over visual effects

---

## Technical Notes

- **Backend:** FastAPI wraps the S2-08 `Decision_Service` operations (`run_analysis`, `get_ranked_results`, `get_site_detail`, `get_exclusions`, `compare_scenarios`, `get_data_quality`). FastAPI's automatic OpenAPI generation satisfies the S2-08 requirement for a documented request/response schema. The API imports the existing Python engine (`pipeline/`) — the decision logic stays in the pipeline, not in the API layer.
- **Frontend:** Next.js/React consumes the FastAPI HTTP endpoints. Prefer generating a typed client from the published OpenAPI schema (done in S3-01b) so the frontend/backend types cannot drift.
- **CORS/config:** configure the API's allowed origins for the frontend dev/host URL; keep the base URL configurable rather than hard-coded. Under Compose the frontend reaches the backend by its service name (e.g. `http://api:8000`) while the browser reaches it via the published host port — pass both through environment variables, not literals.
- **Docker Compose:** provide a `docker-compose.yml` at the app root defining two services (`web` for the Next.js frontend, `api` for the FastAPI backend), each with its own `Dockerfile`. `docker compose up --build` must bring up the full stack in one command in a clean environment. Set `depends_on` so the frontend starts after the API, expose both apps on documented host ports, and drive all cross-service URLs and allowed origins through environment variables. Keep the images thin (a slim Python base for the API, a Node base for the frontend); this is the one-command "clean-environment start" path referenced in the run-commands deliverable.
- Cross-cutting impact: this fixes the S2-08 service form as HTTP+OpenAPI (see the updated S2-08 spec). The region layout and stack chosen here are the substrate for S3-02/03/04/05/06. Keep the shell thin.
