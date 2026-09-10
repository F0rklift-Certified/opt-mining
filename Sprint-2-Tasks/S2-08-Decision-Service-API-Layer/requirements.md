# Requirements Document

## Introduction

This feature delivers Sprint 2 task S2-08 ("Decision Service / API Layer"). It exposes the decision engine — hard exclusions (S2-03), feature normalisation (S2-04), suitability scoring and ranking (S2-05), deterministic site explanations (S2-06), and scenario comparison (S2-07) — through a thin, well-defined **service layer** so that the Sprint 3 web application consumes engine output and never re-implements any decision logic itself.

This is the architectural seam the combined Sprint 2/3 client guidance calls for (guidance section 3: a "Web API/service layer if needed", and the emphatic constraint that "the scoring methodology must not be implemented only inside the user-interface code"). The service is the single boundary between backend (Sprint 2) and presentation (Sprint 3). It makes the combined-sprint acceptance criterion AC4 ("normalisation and scoring are implemented outside the UI") structurally enforceable: the UI can only call the service, so it has no path by which to recompute a score, a rank or an eligibility decision.

The service wraps the existing pipeline outputs. Scoring, ranking and explanation are produced by the pipeline stages and materialised as the Scored_Table (`DATA/scoring/`), the Eligibility_Table (`DATA/exclusions/`) and the explanation artefacts (S2-06). The service reads and serves those results and applies **display-level** operations (top-N, minimum-suitability threshold) as queries over the fixed engine output — it never re-runs normalisation on a filtered subset, which would violate the S2-04 fixed-bounds guarantee.

The stack for the MVP is decided (see S3-01a): a **React / Next.js frontend and a FastAPI backend communicating over HTTP**, so the Decision_Service is realised as a **FastAPI application exposing HTTP endpoints with an OpenAPI-described contract** — not an in-process module. The FastAPI layer imports and orchestrates the existing Python engine (`pipeline/`); the decision logic stays in the pipeline, and the API neither reimplements nor recomputes it. This feature blocks S3-01a (app shell scaffold) and, transitively, all of Sprint 3, so its contract must be frozen at the sprint boundary. This document specifies **requirements only**. Design and tasks are out of scope here.

## Glossary

- **Decision_Service**: The thin service layer specified by this feature, exposing the decision engine through a documented set of operations. It performs no decision logic of its own; it orchestrates and serves the outputs of the S2-03 through S2-07 components.
- **Decision_Engine**: The collective backend of exclusions (S2-03), normalisation (S2-04), scoring/ranking (S2-05), explanation (S2-06) and scenarios (S2-07).
- **Service_Operation**: A single named operation the Decision_Service exposes, with a documented request and response schema.
- **Scored_Table**: The S2-05 per-cell output (`cell_id`, `suitability_score`, `rank`, `confidence`, `contrib_{feature}` per criterion). The authoritative score/rank source.
- **Eligibility_Table**: The S2-03 per-cell eligibility output (`eligible`, machine- and human-readable exclusion reason(s)).
- **Explanation_Structure**: The S2-06 deterministic per-site explanation (positive factors, weaknesses, proxy caveats, data-quality notes).
- **Scenario**: A named weight set (S2-07 preset) fed to the scoring function; two Scenarios can be compared.
- **Data_Quality_Status**: The S2-02 machine-readable validation result indicating whether the frozen integrated dataset passed its data-quality checks.
- **Display_Filter**: A top-N or minimum-suitability-threshold selection applied over fixed engine output for presentation; never a re-run of normalisation or scoring.
- **Run**: One execution of the Decision_Engine under a given weights/scenario, identified by a run id, whose results the Decision_Service serves.
- **Web_Application**: The Sprint 3 client of the Decision_Service (S3-01 onward).

## Requirements

### Requirement 1: A defined set of service operations

**User Story:** As a web-application developer, I want a documented set of service operations, so that I can build every UI view against a stable contract.

#### Acceptance Criteria

1. THE Decision_Service SHALL expose a Service_Operation to run an analysis given a weights configuration or a named Scenario.
2. THE Decision_Service SHALL expose a Service_Operation to retrieve ranked results for a Run, accepting an optional Display_Filter (top-N and/or minimum suitability threshold).
3. THE Decision_Service SHALL expose a Service_Operation to retrieve a single site's detail for a Run, returning its features, per-criterion component scores, total score, eligibility, and Explanation_Structure.
4. THE Decision_Service SHALL expose a Service_Operation to retrieve the excluded cells for a Run with their machine- and human-readable exclusion reasons.
5. THE Decision_Service SHALL expose a Service_Operation to compare two Scenarios, returning a per-cell rank comparison.
6. THE Decision_Service SHALL expose a Service_Operation to retrieve the Data_Quality_Status.

### Requirement 2: All decision logic behind the service

**User Story:** As an architect, I want the UI to be unable to recompute decisions, so that the map and the ranking table can never disagree and AC4 holds structurally.

#### Acceptance Criteria

1. THE Decision_Service SHALL be the only interface through which the Web_Application obtains scores, ranks, eligibility and explanations.
2. THE Decision_Service SHALL NOT require the Web_Application to perform any scoring, normalisation, ranking or exclusion computation.
3. WHEN the Decision_Service serves ranked results and single-site detail for the same Run, THE served score and rank for a given `cell_id` SHALL be identical across both operations, so the ranking table and the map represent one engine output.
4. THE Decision_Service SHALL derive all served values from the materialised Decision_Engine outputs (Scored_Table, Eligibility_Table, Explanation_Structure) and SHALL NOT recompute them.

### Requirement 3: Display filters operate over fixed engine output

**User Story:** As a planner, I want to filter the results to the top sites without changing the scores, so that filtering the view never silently changes the model.

#### Acceptance Criteria

1. WHEN the Decision_Service applies a Display_Filter, THE Decision_Service SHALL select over the fixed Run output and SHALL NOT re-run normalisation or scoring on the filtered subset.
2. THE Decision_Service SHALL preserve the S2-05 ranks under any Display_Filter, so that filtering changes which cells are shown but never their scores or ranks.
3. IF a top-N Display_Filter exceeds the eligible count, THEN THE Decision_Service SHALL return every eligible cell without padding.
4. IF a minimum-suitability-threshold Display_Filter excludes every cell, THEN THE Decision_Service SHALL return an empty result set rather than an error.

### Requirement 4: Weights and scenarios as inputs

**User Story:** As a planner, I want to supply weights or pick a scenario, so that I can express my priorities and rerun the analysis.

#### Acceptance Criteria

1. THE run-analysis Service_Operation SHALL accept either an explicit weights configuration or a named Scenario as input.
2. THE Decision_Service SHALL document the interpretation of the weights (for example normalised to sum to one) consistent with the S2-01 Decision_Engine_Spec.
3. WHEN the run-analysis operation is invoked with a Scenario, THE Decision_Service SHALL run the S2-05 scoring function with that Scenario's weight set unchanged, reusing the engine and not duplicating scoring logic.
4. IF the supplied weights or Scenario are invalid, THEN THE Decision_Service SHALL return an error identifying the fault and SHALL NOT return a Run result.

### Requirement 5: Data-quality surfacing

**User Story:** As a planner, I want the app to warn me when the input dataset is flagged, so that I do not trust rankings built on invalid input.

#### Acceptance Criteria

1. THE Decision_Service SHALL surface the S2-02 Data_Quality_Status through the get-data-quality Service_Operation.
2. WHEN the frozen integrated dataset has failed a data-quality check, THE Decision_Service SHALL report the failure through the Data_Quality_Status so the Web_Application can show a data-quality banner.
3. THE Decision_Service SHALL NOT emit a Run result derived from a dataset that failed a blocking data-quality check without also making the failure retrievable via the Data_Quality_Status.

### Requirement 6: Documented request/response contract

**User Story:** As a web-application developer, I want each operation's request and response schema documented, so that I can integrate without reading engine internals.

#### Acceptance Criteria

1. THE Decision_Service SHALL expose its operations as HTTP endpoints from a FastAPI application and SHALL publish a machine-readable OpenAPI schema describing every operation's request and response.
2. THE documented response for single-site detail SHALL include the Explanation_Structure fields defined by S2-06.
3. THE documented response for ranked results SHALL include at least `cell_id`, `suitability_score`, `rank`, and the key component values per cell.
4. THE Decision_Service SHALL be implemented over HTTP (FastAPI) rather than as an in-process module, consistent with the decided React/Next.js + FastAPI stack (S3-01a), so the Next.js/React Web_Application integrates against the published OpenAPI surface.
5. THE Decision_Service contract (the OpenAPI schema and its semantics) SHALL be frozen at the Sprint 2/Sprint 3 boundary so that S3-01a and S3-01b integrate against a stable surface.

### Requirement 7: Error handling and honest failures

**User Story:** As a web-application developer, I want the service to fail clearly, so that the UI can present a real error rather than a misleading empty result.

#### Acceptance Criteria

1. IF a requested Run does not exist, THEN THE Decision_Service SHALL return an error identifying the missing Run rather than an empty success.
2. IF a requested `cell_id` does not exist in a Run, THEN THE Decision_Service SHALL return an error identifying the missing `cell_id`.
3. IF a materialised Decision_Engine output required by an operation is missing or unreadable, THEN THE Decision_Service SHALL return an error naming the missing input rather than fabricating a result.
4. THE Decision_Service SHALL distinguish an empty-but-valid result (for example a threshold that legitimately excludes all cells) from an error condition.

### Requirement 8: Contract and integration tests

**User Story:** As a reviewer, I want the service covered by contract and integration tests against the real engine, so that the Sprint 3 boundary is trustworthy.

#### Acceptance Criteria

1. THE tests SHALL exercise each Service_Operation against the real Decision_Engine output on the frozen dataset.
2. THE tests SHALL assert that ranked results and single-site detail return identical score and rank for the same `cell_id` in the same Run.
3. THE tests SHALL assert that a Display_Filter changes which cells are returned but never their scores or ranks.
4. THE tests SHALL assert that comparing two Scenarios reuses the scoring engine and returns a per-cell rank comparison.
5. THE tests SHALL assert the honest-failure behaviour for a missing Run, a missing `cell_id`, and a missing engine output.
