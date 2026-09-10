# S2-08: Decision Service / API Layer (Contract for the Web App)

**Type:** Story
**Priority:** High
**Story Points:** 5
**Labels:** api, service-layer, decision-engine
**Blocked by:** S2-06, S2-07
**Blocks:** S3-01

---

## Objective

Expose the decision engine (exclusions → normalisation → scoring → ranking → explanation → scenarios) through a thin, well-defined service/API layer so the web application consumes engine output rather than re-implementing any decision logic.

---

## Context

Guidance §3 requires a "Web API/service layer if needed" between the engine and the UI, and is emphatic that "the scoring methodology must not be implemented only inside the user-interface code." This task defines the seam between Sprint 2 (backend) and Sprint 3 (web) and makes the "UI never recomputes" guarantee (AC4) structurally enforceable — the UI can only call the service.

---

## Deliverables

1. A FastAPI service exposing HTTP endpoints (with an OpenAPI schema) wrapping the engine.
2. A documented request/response contract for each operation.
3. Contract/integration tests for the service surface.

---

## Acceptance Criteria

- [ ] The service exposes, at minimum: run analysis (with weights/scenario), get ranked results, get single-site detail + explanation, get exclusions, compare two scenarios
- [ ] All decision logic lives behind the service; the web app calls it and never re-implements scoring, normalisation or exclusions (structurally supports **AC4**)
- [ ] Results returned include component scores, total score and deterministic ranks (satisfies **AC6**)
- [ ] Site detail returns the deterministic explanation structure from S2-06 (satisfies **AC7**)
- [ ] Weights/scenario are accepted as inputs and their interpretation is documented (supports **AC5**)
- [ ] The service surfaces the S2-02 data-quality status so the UI can show a data-quality banner
- [ ] The request/response schema is documented (e.g. OpenAPI or a typed schema doc)
- [ ] Contract/integration tests exercise each operation against the real engine on the frozen dataset

---

## Suggested Service Operations

| Operation | Input | Output |
|-----------|-------|--------|
| `run_analysis` | weights or scenario id | run id + summary |
| `get_ranked_results` | run id, top-N/threshold filter | ranked cells (id, score, rank, key components) |
| `get_site_detail` | run id, cell_id | features, component scores, total, eligibility, explanation |
| `get_exclusions` | run id | excluded cells + reasons |
| `compare_scenarios` | two scenario ids | per-cell rank comparison |
| `get_data_quality` | — | S2-02 validation status |

---

## Technical Notes

- Stack decided (S3-01a): a React/Next.js frontend and a FastAPI backend over HTTP. The service is therefore a FastAPI app exposing HTTP endpoints and publishing an OpenAPI schema; the frontend generates a typed client from it (S3-01b). The API imports the Python engine (`pipeline/`) — the decision logic stays in the pipeline, and the no-recompute rule still holds.
- Filtering (top-N, min threshold) happens in the service/query layer over fixed engine output — never by re-running normalisation on a filtered subset (guards the S2-04 bounds guarantee).
- Cross-cutting impact: this contract blocks all of Sprint 3. Freeze the OpenAPI contract early at the sprint boundary so S3-01a/S3-01b can integrate against a stable surface.
