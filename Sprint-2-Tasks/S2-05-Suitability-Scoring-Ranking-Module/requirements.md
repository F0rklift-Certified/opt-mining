# Requirements Document

## Introduction

This feature delivers Sprint 2 task S2-05 ("Suitability Scoring & Ranking Module"). It **hardens and formalises the existing Sprint 1 scoring stage** (`pipeline/scoring/`, delivered by S1-10) up to the combined Sprint 2/3 acceptance bar, rather than building a new engine. The transparent weighted multi-criteria decision analysis (MCDA) function, the directional min-max normalisation, the ranking, the weights loader, and the per-criterion contribution columns already exist; this feature confirms they satisfy the combined-sprint acceptance criteria (AC4, AC5, AC6, and the score data underlying AC7), closes any gaps against the frozen S2-01 decision-engine specification, and raises test coverage to the "controlled test case with a known expected ranking" standard the guidance requires.

The scoring engine is deliberately **not** a machine-learning model. It is a weighted sum over normalised feature columns, driven entirely by user-supplied criteria weights loaded from a configuration file, where the contribution of every criterion to every cell's score is retrievable. The constitution constrains it directly: weights are user inputs and never hard-coded constants, the model is never circular (wind is an input criterion, never a prediction target), a recommendation the planner cannot interrogate is treated as an assertion, and the scoring computation must be independently replaceable without touching the data-loading layer.

The engine consumes the integrated NSW feature table (S1-08 + S1-09 confidence), scores only eligible cells (excluded cells receive a null score, null rank and null contributions and take no part in the normalisation bounds or the ranking), produces a normalised suitability score in `[0, 1]`, a deterministic rank with a documented tie-break, and per-criterion contributions that sum back to the score. This feature is blocked by S2-04 (feature normalisation, itself surfaced from the same package) and blocks S2-06 (explanations) and S2-07 (scenarios). It also underpins the S2-08 service layer.

Where this specification and the existing implementation disagree, the S2-01 Decision_Engine_Spec is authoritative and this feature reconciles the code to it. This document specifies **requirements only**. Design and tasks are out of scope here.

## Glossary

- **Scoring_Module**: The existing scoring pipeline stage under `pipeline/scoring/` that this feature hardens. It reads the Integrated_Feature_Table and the Weights_Config and produces the Scored_Table plus a method report.
- **Scoring_Function**: The pure, side-effect-free scoring computation (`pipeline/scoring/score.py`) that accepts an in-memory feature DataFrame and a Weights_Config and returns a scored DataFrame without any file I/O.
- **Integrated_Feature_Table**: The S1-08 integrated NSW feature table (`DATA/integration/`, one row per `cell_id`) carrying the criterion columns, the `eligible` flag (S1-07), and the S1-09 composite confidence. The sole feature input.
- **Weights_Config**: The runtime criteria weights configuration (`pipeline/scoring/scoring_weights.yaml` or a `--scoring-weights` path) declaring each Criterion's feature name, weight, direction (`higher_is_better`/`lower_is_better`) and rationale.
- **Decision_Engine_Spec**: The frozen S2-01 specification that is authoritative for the feature contract, formula, normalisation method and default weights this feature must conform to.
- **Criterion**: A named feature column from the Integrated_Feature_Table participating in the score, with its configured weight and direction.
- **Normalised_Feature**: A Criterion value rescaled to `[0, 1]` using directional min-max bounds from the eligible population (produced by the S2-04 normalisation component).
- **Suitability_Score**: The final per-cell score in `[0, 1]`, the weight-weighted sum of Normalised_Features divided by the applied weight sum.
- **Per_Criterion_Contribution**: The additive contribution of a single Criterion to a cell's Suitability_Score, written as a `contrib_{feature}` column, such that the contributions reconstruct the score.
- **Rank**: The ordinal position of a cell among scored eligible cells, ordered by descending Suitability_Score with a documented deterministic tie-break.
- **Eligible_Cell / Excluded_Cell**: A cell with `eligible = true` (scored) / `eligible = false` (null score, null rank, null contributions).
- **Scored_Table**: The per-cell output (`DATA/scoring/`) with `cell_id`, `suitability_score`, `rank`, `confidence`, and one `contrib_{feature}` per Criterion.
- **Controlled_Test_Case**: A small synthetic input with a hand-computed expected ranking used to verify the scoring code end-to-end (guidance Step 11).

## Requirements

### Requirement 1: Conform to the frozen decision-engine specification

**User Story:** As a reviewer, I want the scoring engine to match the signed-off S2-01 design, so that the implementation and the documented methodology cannot diverge.

#### Acceptance Criteria

1. THE Scoring_Module SHALL implement the Scoring_Formula exactly as fixed in the Decision_Engine_Spec.
2. THE Scoring_Module SHALL use the Criteria, directions and default weights fixed in the Decision_Engine_Spec.
3. IF the existing implementation differs from the Decision_Engine_Spec, THEN THE Scoring_Module SHALL be reconciled to the Decision_Engine_Spec and the reconciliation SHALL be recorded.
4. THE Scoring_Module SHALL use the S2-04 normalisation component and SHALL NOT implement a second, divergent normaliser.

### Requirement 2: Configurable weights, no hard-coded constants

**User Story:** As a planner, I want the criteria weights to be configurable inputs, so that I can adjust the model to my priorities.

#### Acceptance Criteria

1. THE Scoring_Module SHALL load weights, directions and rationales from the Weights_Config at runtime.
2. THE Scoring_Module SHALL NOT hard-code any criterion weight value as a constant in its source code.
3. WHERE a caller supplies an alternative Weights_Config path, THE Scoring_Module SHALL load weights from that path, and THE Pipeline_Orchestrator SHALL expose the corresponding CLI flag and pass its value via `_build_kwargs`.
4. THE Scoring_Module SHALL enforce or automatically normalise the weights so that the interpretation of the weights is unambiguous, and SHALL document the applied rule.
5. IF the Weights_Config is missing, unparsable, declares an invalid direction, declares a negative or non-numeric weight, or has a zero weight sum, THEN THE Scoring_Module SHALL halt before writing any Scored_Table output and SHALL return an error identifying the fault.

### Requirement 3: Weighted MCDA scoring, deterministic and bounded

**User Story:** As a planner, I want cells scored by a transparent weighted sum of normalised criteria, so that the ranking is explainable and reproducible.

#### Acceptance Criteria

1. WHEN the Scoring_Function scores an Eligible_Cell, THE Scoring_Function SHALL compute the Suitability_Score as the sum over Criteria of `(weight_i × normalised_feature_i)` divided by the sum of the applied weights.
2. THE Scoring_Function SHALL constrain every Eligible_Cell Suitability_Score to the inclusive `[0, 1]` range.
3. THE Scoring_Function SHALL be a pure computation accepting an in-memory feature DataFrame and a Weights_Config and returning a scored DataFrame, performing no file I/O, so it is independently replaceable without changing the data-loading layer.
4. WHEN the Scoring_Function runs twice over identical inputs and an identical Weights_Config, THE Scoring_Function SHALL return identical Suitability_Scores.
5. THE Scoring_Module SHALL treat the wind feature only as an input Criterion and SHALL NOT use it or any wind-derived feature as a prediction target, so the model is not circular.

### Requirement 4: Only eligible cells are scored and ranked

**User Story:** As a planner, I want excluded cells to carry a null score and no rank, so that ineligible land is never ranked as developable.

#### Acceptance Criteria

1. WHEN a cell's `eligible` value is true, THE Scoring_Module SHALL assign it a numeric Suitability_Score, a rank, and per-criterion contributions.
2. WHEN a cell's `eligible` value is false, THE Scoring_Module SHALL assign it a null Suitability_Score, a null rank, and null Per_Criterion_Contributions, and SHALL NOT include it in the Rank ordering.
3. THE Scoring_Module SHALL compute every Criterion's normalisation bounds from the Eligible_Cell population only and SHALL exclude Excluded_Cell values from the bounds.

### Requirement 5: Deterministic ranking

**User Story:** As a planner, I want scored cells ranked from most to least suitable deterministically, so that the shortlist is stable across runs.

#### Acceptance Criteria

1. THE Scoring_Module SHALL order scored cells by descending Suitability_Score, assigning `rank` 1 to the highest-scoring Eligible_Cell.
2. IF two or more Eligible_Cells share the same Suitability_Score, THEN THE Scoring_Module SHALL break the tie using a documented deterministic rule (ascending `cell_id`) so repeated runs produce identical ranks.
3. THE Scoring_Module SHALL assign a `rank` only to Eligible_Cells and leave `rank` null for every Excluded_Cell.
4. WHEN the Scoring_Module runs twice over identical inputs and an identical Weights_Config, THE resulting `rank` values SHALL be identical.

### Requirement 6: Explainability through reconcilable contributions

**User Story:** As a planner, I want each cell's per-criterion contributions to reconstruct its score, so that a recommendation is interrogable rather than an assertion.

#### Acceptance Criteria

1. FOR every scored Eligible_Cell, THE Scoring_Module SHALL record a `contrib_{feature}` value for each configured Criterion.
2. THE configured Per_Criterion_Contributions for a cell SHALL reconstruct that cell's Suitability_Score within a documented numeric tolerance.
3. WHERE confidence discounting is enabled, THE Scoring_Module SHALL apply the same factor to the contributions as to the score, so they remain reconcilable.
4. THE Scoring_Module SHALL retain the contribution columns in the Scored_Table so that S2-06 and S2-08 can consume them without recomputation.

### Requirement 7: Scoring implemented outside the UI, covered by tests

**User Story:** As a reviewer, I want normalisation and scoring implemented in the backend and tested, so that the UI cannot become a hidden second implementation.

#### Acceptance Criteria

1. THE Scoring_Module SHALL implement scoring and ranking entirely in the backend pipeline, not in any user-interface code (supports combined-sprint AC4).
2. THE Scoring_Module SHALL retain unit tests covering the scoring formula, weight re-normalisation, the tie-break rule, and the eligible-only rule.
3. THE Scoring_Module SHALL include at least one Controlled_Test_Case with a hand-computed expected ranking that verifies the scoring code end-to-end.
4. THE unit tests SHALL assert determinism: identical inputs and Weights_Config yield identical scores, ranks and contributions.

### Requirement 8: Stable output schema and stage contract

**User Story:** As a downstream consumer, I want a stable scored table and stage contract, so that S2-06, S2-07 and S2-08 can build against it.

#### Acceptance Criteria

1. THE Scoring_Module SHALL write a Scored_Table containing at least `cell_id`, `suitability_score`, `rank`, `confidence`, and one `contrib_{feature}` column per Criterion.
2. THE Scoring_Module SHALL emit exactly one Scored_Table row per Integrated_Feature_Table `cell_id`, with no missing and no duplicate `cell_id`, joinable to the Analysis_Grid on `cell_id`.
3. THE Scoring_Module SHALL expose an importable `run(verbose=False, ...) -> dict` entry point matching the registered-stage contract, returning a summary dict with the Scored_Table and method-report paths that exist on disk after the call.
4. THE Scoring_Module SHALL keep the score/rank/contribution schema stable, as it is the contract for S2-06, S2-07 and S2-08.

### Requirement 9: Validation under the no-silent-passes rule

**User Story:** As a quality reviewer, I want the scored output validated with explicit pass/fail reporting, so that silent scoring problems are caught.

#### Acceptance Criteria

1. THE Scoring_Module validation SHALL confirm one row per `cell_id` and report expected vs observed vs pass/fail.
2. THE Scoring_Module validation SHALL confirm every non-null `suitability_score` lies within `[0, 1]` and report the out-of-range count and pass/fail.
3. THE Scoring_Module validation SHALL confirm every Eligible_Cell has a non-null score and every Excluded_Cell a null score, reporting the violating count and pass/fail.
4. THE Scoring_Module validation SHALL confirm the contributions reconcile to the score within tolerance for every scored cell, reporting the violating count and pass/fail.
5. THE Scoring_Module validation SHALL confirm `rank` is a contiguous ordering over scored Eligible_Cells with no rank on an Excluded_Cell, reporting pass/fail.
6. Each check SHALL report expected vs observed vs an explicit pass or fail (no silent passes).

### Requirement 10: Documentation and traceability

**User Story:** As a maintainer, I want the scoring documentation kept consistent with the frozen design, so that documentation matches behaviour.

#### Acceptance Criteria

1. THE Scoring_Module documentation (README stage notes and method report) SHALL match the Decision_Engine_Spec formula, criteria, directions and default weights.
2. THE method report SHALL record the formula, the configured criteria with weights/directions/rationales, the per-criterion normalisation bounds for the run, and the counts of eligible/excluded/confidence cells.
3. IF the README stage-order or the method report diverges from the Decision_Engine_Spec, THEN the divergence SHALL be corrected so documentation matches behaviour.
