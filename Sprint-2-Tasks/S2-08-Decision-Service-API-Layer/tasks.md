# Implementation Plan: Decision Service / API Layer (S2-08)

## Overview

This plan builds the thin `pipeline/service/` layer that exposes the decision engine to the Sprint 3 web application, following the design. The service reads materialised engine outputs (Scored_Table, Eligibility_Table, Explanation_Structure, scenario comparison, data-quality status) and serves them through six typed operations, applying only pure display-level filters. It contains **no** scoring, normalisation, ranking or exclusion logic — that all lives in S2-03 through S2-07, which this feature orchestrates.

Tasks build the contract first (it blocks all of Sprint 3), then the operations from the read path outward, then the display filters, then error handling, then contract/integration tests. The layer is a **FastAPI HTTP app publishing an OpenAPI schema** (the decided React/Next.js + FastAPI stack, S3-01a), so task 1 fixes the OpenAPI contract that S3-01a/S3-01b integrate against. This feature is blocked by S2-06b and S2-07 and blocks S3-01a.

> **Freeze note.** The OpenAPI contract (task 1) must be frozen at the Sprint 2/Sprint 3 boundary. Freeze it early so S3-01a/S3-01b do not integrate against a moving surface (Requirement 6.5).

## Tasks

- [ ] 1. Define and freeze the service contract
  - [ ] 1.1 Author `pipeline/service/CONTRACT.md`
    - Document a request and response schema for all six Service_Operations (run_analysis, get_ranked_results, get_site_detail, get_exclusions, compare_scenarios, get_data_quality) (1.1–1.6, 6.1)
    - Expose the operations as FastAPI HTTP endpoints and publish the OpenAPI schema (`/openapi.json`, `/docs`); record the endpoint mapping (6.1, 6.4)
    - Document the weights interpretation consistent with the S2-01 Decision_Engine_Spec (4.2)
    - State the contract is frozen at the sprint boundary (6.5)
    - Define the data models (RunHandle, RankedRow, SiteDetail, ExcludedRow, ScenarioComparison, DataQualityStatus) (6.2, 6.3)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 4.2, 6.1, 6.2, 6.3, 6.4, 6.5_

- [ ] 2. Implement run_analysis
  - [ ] 2.1 Implement `run_analysis` in `pipeline/service/run_analysis.py`
    - Accept an explicit weights config OR a named Scenario (1.1, 4.1); drive the S2-05 scoring stage with those weights unchanged, reusing the engine — no duplicate scoring logic (4.3); return a RunHandle
    - Raise on invalid weights/scenario, returning no Run (4.4)
    - _Requirements: 1.1, 4.1, 4.3, 4.4_

- [ ] 3. Implement the read operations over materialised output
  - [ ] 3.1 Implement `get_ranked_results` in `pipeline/service/results.py`
    - Read the Scored_Table for the Run; return RankedRows with `cell_id`, `suitability_score`, `rank`, key components (1.2, 6.3); derive from the materialised output, no recompute (2.4)
    - _Requirements: 1.2, 2.4, 6.3_

  - [ ] 3.2 Implement `get_site_detail` in `pipeline/service/results.py`
    - Return features, per-criterion component scores, total score, eligibility, and the S2-06 Explanation_Structure for one cell (1.3, 6.2); the served score/rank for a `cell_id` equals `get_ranked_results` for the same Run (2.3)
    - Raise on unknown `cell_id` (7.2)
    - _Requirements: 1.3, 2.3, 6.2, 7.2_

  - [ ] 3.3 Implement `get_exclusions` in `pipeline/service/results.py`
    - Return excluded cells with machine- and human-readable reasons from the Eligibility_Table (1.4)
    - _Requirements: 1.4_

  - [ ] 3.4 Property test — one engine output across operations
    - **Property 1: One engine output** — for a Run, the score and rank of any `cell_id` are identical across `get_ranked_results` and `get_site_detail`
    - **Validates: Requirements 2.3**

- [ ] 4. Implement the display filters
  - [ ] 4.1 Implement top-N and minimum-score filters in `pipeline/service/filters.py`
    - Reuse the `pipeline/shortlist/select.py` selection-by-rank pattern for top-N; threshold filter for minimum score; both pure selections over the fixed Run output, never re-running normalisation or scoring (3.1); ranks preserved (3.2)
    - top-N over the eligible count returns all eligible cells, no padding (3.3); an all-excluding threshold returns an empty set, not an error (3.4)
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [ ] 4.2 Property test — filters do not re-score
    - **Property 2: Filters do not re-score** — for any Display_Filter, the score and rank of every returned cell equal its unfiltered Run values
    - **Validates: Requirements 3.1, 3.2**

  - [ ] 4.3 Property test — empty-but-valid results
    - **Property 4: Empty-but-valid** — top-N over the eligible count returns all eligible cells with no padding; an all-excluding threshold returns an empty set, not an error
    - **Validates: Requirements 3.3, 3.4**

- [ ] 5. Implement scenario comparison and data-quality surfacing
  - [ ] 5.1 Implement `compare_scenarios` in `pipeline/service/scenarios.py`
    - Produce each scenario's ranks via the S2-05 engine (not a second scorer) and return a per-cell rank comparison with rank deltas (1.5, 4.3)
    - _Requirements: 1.5, 4.3_

  - [ ] 5.2 Implement `get_data_quality` in `pipeline/service/quality.py`
    - Surface the S2-02 Data_Quality_Status (1.6, 5.1); report a failed check so the UI can show a banner (5.2); never emit a Run result from a failed dataset without making the failure retrievable (5.3)
    - _Requirements: 1.6, 5.1, 5.2, 5.3_

  - [ ] 5.3 Property test — scenario reuse
    - **Property 5: Scenario reuse** — `compare_scenarios` produces ranks via the S2-05 engine, not a second scorer
    - **Validates: Requirements 4.3**

- [ ] 6. Checkpoint — operations serve real engine output
  - Ensure all tests pass; confirm no decision arithmetic lives in `pipeline/service/`; ask the user if questions arise.

- [ ] 7. Implement honest-failure error handling
  - [ ] 7.1 Add error handling across the operations
    - Missing Run → error naming the Run (7.1); unknown `cell_id` → error (7.2); missing/unreadable engine output → error naming the input, no fabricated result (7.3); distinguish empty-but-valid from error (7.4)
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [ ] 7.2 Property test — no recompute path
    - **Property 3: No recompute path** — no scoring/normalisation/ranking/exclusion arithmetic exists in `pipeline/service/`; all served values trace to a materialised engine output
    - **Validates: Requirements 2.1, 2.2, 2.4**

  - [ ] 7.3 Property test — honest failure
    - **Property 6: Honest failure** — missing Run / `cell_id` / engine output each yield an error naming the fault, never a misleading empty success
    - **Validates: Requirements 7.1, 7.2, 7.3**

- [ ] 8. Contract and integration tests against the real engine
  - [ ] 8.1 Write contract/integration tests
    - Exercise each Service_Operation against the real engine output on the frozen dataset (8.1)
    - Assert ranked results and site detail return identical score/rank for the same `cell_id` in a Run (8.2)
    - Assert a Display_Filter changes the returned set but never scores/ranks (8.3)
    - Assert compare_scenarios reuses the engine and returns a per-cell rank comparison (8.4)
    - Assert honest-failure for missing Run, missing `cell_id`, missing engine output (8.5)
    - Tests run in CI
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [ ] 9. Checkpoint — contract frozen for Sprint 3
  - Confirm `CONTRACT.md` and the FastAPI OpenAPI schema are complete and frozen; hand the stable HTTP surface to S3-01a/S3-01b. Ask the user if questions arise.

## Notes

- The service is deliberately thin: read materialised engine outputs and serve them; the only computation it performs is pure display-level selection.
- Property tests (P1–P6) sit next to the operation they validate; each is tagged `# Feature: s2-08-decision-service-api, Property {n}: {text}`.
- The no-recompute rule (P3) is the structural guarantee behind combined-sprint AC4 — keep all decision arithmetic in S2-03..S2-07.
- The contract freeze (tasks 1 and 9) is the gate that unblocks Sprint 3; treat a late contract change as a cross-cutting event that ripples into every S3 ticket.
- The layer is a FastAPI HTTP app (decided stack); FastAPI auto-generates the OpenAPI schema that `CONTRACT.md` narrates and that the Next.js/React frontend generates its typed client from.
