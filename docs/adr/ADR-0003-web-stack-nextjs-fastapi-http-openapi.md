# ADR-0003: Web stack — React/Next.js frontend + FastAPI backend over HTTP/OpenAPI

**Status:** Accepted

**Date:** 2026 (Sprint 3, S3-01a)

**Deciders:** Opt-Mining team

**Context tickets:** S3-01a (Application Shell Scaffold); constrains S3-01b and S3-02 … S3-06.

---

## Context

Sprint 3 delivers the MVP web application on top of the frozen Sprint 2 decision
engine. The `Decision_Service` surface — six operations (`run_analysis`,
`get_ranked_results`, `get_site_detail`, `get_exclusions`, `compare_scenarios`,
`get_data_quality`) — was frozen at the Sprint 2/Sprint 3 boundary
(`pipeline/service/CONTRACT.md`), but two questions were left open:

1. **Which frontend framework** the MVP would use, and
2. **Whether the `Decision_Service` boundary is an in-process module call or a
   network boundary.**

Both must be settled before service integration (S3-01b) and the view tickets
(S3-02 … S3-06), because the stack choice constrains every one of them: it
decides how the UI reaches decision output, how the request/response contract is
described, and how the apps are built and run. The combined-sprint guidance
(Step 8) explicitly permits "a separated frontend/backend if already justified
by the team's architecture."

A hard invariant carried down from the frozen contract (CONTRACT.md §1, §7-P3;
combined-sprint AC4) frames the choice: **no decision logic — scoring,
normalisation, ranking, exclusion — may live in the API or the frontend.** All
such logic stays in the `pipeline/` engine. Whatever stack is chosen, the API
layer must *delegate to* the pure operation functions in `pipeline/service/`,
never recompute a score, rank, normalisation bound, or exclusion.

## Decision

The MVP web stack is a **React / Next.js frontend** and a **FastAPI backend**,
communicating over **HTTP** with an **OpenAPI**-described contract.

- The **Backend_App** (`app/api/`) is a FastAPI application that maps each of the
  six frozen `Decision_Service` operations to one HTTP endpoint, imports and
  delegates to `pipeline/service/`, and publishes an auto-generated OpenAPI
  schema at `/openapi.json` (browsable docs at `/docs`, `/redoc`). The API is a
  pure mapping/serialisation layer; it holds no decision arithmetic.
- The **Frontend_App** (`app/web/`) is a browser-based Next.js/React application
  that reaches the backend only over HTTP, reading the backend `Service_URL`
  from an environment variable (never a hard-coded host address).
- FastAPI's automatic OpenAPI generation gives a machine-readable contract and a
  generatable typed client (wired in S3-01b), so the frontend and backend types
  cannot drift.

## Consequences

- **This fixes the S2-08 `Decision_Service` boundary as HTTP + OpenAPI, not an
  in-process module.** The frontend can only reach decisions by calling the
  backend over HTTP; the backend can only produce decisions by delegating to
  `pipeline/service/`. This is the structural expression of CONTRACT.md §1 and
  combined-sprint AC4 — the single decision boundary the whole architecture
  rests on.
- Every later Sprint 3 UI ticket (S3-02 … S3-06) builds against this stack and
  consumes the OpenAPI-described HTTP contract; none of them recompute engine
  output.
- The published OpenAPI schema is the canonical, machine-readable contract and
  the source for the S3-01b typed client. Where the OpenAPI schema and
  CONTRACT.md ever disagree, the OpenAPI schema is authoritative
  (CONTRACT.md preamble).
- A separated frontend/backend requires cross-origin configuration: CORS allowed
  origins and all cross-service URLs are driven through environment variables
  (never hard-coded), and the whole stack is brought up with one command via
  Docker Compose.
- The engine is imported, not reimplemented: the backend container installs the
  repo `pipeline` package and imports `pipeline.service`, preserving the
  "pure of transport" guarantee (CONTRACT.md §2).
