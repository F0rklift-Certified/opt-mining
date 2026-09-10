# S3-01b: Decision-Service Integration & Data-Quality Banner

**Type:** Story
**Priority:** Highest
**Story Points:** 2
**Labels:** web-app, integration, frontend, nextjs, react, fastapi
**Blocked by:** S3-01a
**Blocks:** S3-02, S3-03a, S3-04, S3-06

---

> **Split note:** Second half of the former **S3-01**. S3-01a stood up the shell; S3-01b wires the S2-08 decision-service client and surfaces the data-quality status. This is what makes the shell render real engine output.

## Objective

Wire the Next.js/React frontend to the FastAPI backend (the S2-08 decision service) via a typed HTTP client generated from the OpenAPI schema, so the shell loads real engine output, and surface the S2-02 data-quality status as a banner — with no decision logic in the UI.

---

## Context

Guidance Step 8; combined-sprint AC1 (dataset consumed) and AC4 (no decision logic in the UI). The stack is React/Next.js ↔ FastAPI over HTTP (decided in S3-01a), and the S2-08 contract is frozen and published as OpenAPI, so this ticket integrates against a stable, typed surface.

---

## Deliverables

1. A typed HTTP client (generated from the FastAPI OpenAPI schema) wrapping the S2-08 operations, used as the single frontend integration point.
2. Real engine output fetched from the FastAPI backend and rendered in the shell regions.
3. A data-quality banner driven by `get_data_quality`.

---

## Acceptance Criteria

- [ ] The frontend loads real data by calling the **FastAPI S2-08 endpoints** over HTTP — no decision logic in the UI (supports **AC4**)
- [ ] A **typed client** is generated from the FastAPI OpenAPI schema so frontend/backend types cannot drift
- [ ] The Sprint 1 integrated dataset is successfully consumed via the engine (satisfies **AC1** at the app level)
- [ ] A **data-quality banner** surfaces the S2-02 status when the dataset is flagged (via `get_data_quality`)
- [ ] The typed client is the thin, shared, single integration point, ready for S3-02/03/04/05/06 to build on
- [ ] The frontend performs no scoring, normalisation, ranking or exclusion computation

---

## Technical Notes

- Integrate against the frozen S2-08 `CONTRACT.md` and the FastAPI OpenAPI schema (HTTP form, per the S3-01a stack decision). Generate the TypeScript client from `/openapi.json` rather than hand-writing request types.
- Keep the API base URL configurable (env var), and confirm CORS allows the frontend origin.
- Cross-cutting impact: every later UI ticket calls the backend through this shared typed client — keep it the single integration point so the "UI never recomputes" guarantee holds structurally.
