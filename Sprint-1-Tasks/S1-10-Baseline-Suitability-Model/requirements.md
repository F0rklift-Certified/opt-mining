# Requirements Document

## Introduction

This feature implements Sprint 1 task S1-10 ("Add a Simple Baseline Suitability Model") for the Opt-Mining geospatial pipeline. It adds a new **scoring** pipeline stage under `pipeline/scoring/` that consumes the integrated NSW feature table (S1-08) and produces a per-cell suitability score using a transparent, deterministic weighted multi-criteria decision analysis (MCDA) function.

The scoring model is deliberately **not** a machine-learning black box. It is a weighted sum over normalised feature columns, driven by user-supplied criteria weights, that any planner can fully interrogate: for every cell the contribution of each criterion to its final score is retrievable. The Opt-Mining constitution constrains this stage directly — criteria weights are user inputs and never hard-coded constants, the platform augments planner judgement rather than replacing it, a recommendation the user cannot interrogate is treated as an assertion rather than a recommendation, the model must never be circular (wind data is an input feature, never a prediction target), and each component must be independently replaceable without requiring changes to adjacent layers.

For every eligible analysis cell in the integrated feature table, the stage normalises each configured feature to the [0, 1] range using bounds computed from the eligible cell population, applies the configured per-criterion weights, and produces a normalised suitability score in [0, 1], a rank, a per-criterion contribution for each criterion, and a confidence value carried through from the upstream composite confidence flag. Cells that are excluded by the exclusion layer (S1-07) receive a null score. The resulting scored table feeds S1-11. This stage is blocked by the integrated feature table (S1-08) and the composite confidence flag (S1-09), and it blocks S1-11.

The stage must satisfy the pipeline's established contracts: the uniform `run(verbose=False, ...) -> dict` stage contract, strict keying to the grid's `cell_id`, weights loaded from a configuration file rather than hard-coded, the project file-naming convention, atomic writes with a do-not-edit banner on generated reports, provenance capture, the "no silent passes" validation rule, and the requirement that the scoring computation is decoupled from data loading (it receives a DataFrame and returns a scored DataFrame).

This document specifies **requirements only**. Design and tasks are deliberately out of scope here.

## Glossary

- **Scoring_Module**: The new scoring pipeline stage specified by this document, a new subpackage under `pipeline/scoring/`. It reads the integrated NSW feature table and the weights configuration and produces the Scored_Table plus a method report.
- **Pipeline_Orchestrator**: The pipeline CLI/orchestrator (`pipeline/__main__.py`) that resolves the stage list from `pipeline/config.py` and dispatches each stage's `run()` entry point via `_get_runner` and `_build_kwargs`.
- **Scoring_Function**: The pure, side-effect-free scoring computation within the Scoring_Module that accepts an in-memory feature DataFrame and a weights configuration and returns a scored DataFrame, without performing any file I/O or data loading itself.
- **Integrated_Feature_Table**: The integrated NSW feature table produced by S1-08 (`pipeline.integration.merge`, stored under `DATA/integration/`), one row per `cell_id`, containing the scored feature columns (`wind_speed`, `demand_proxy`, `dist_transmission_km`, `dist_substation_km`, `slope_deg`, `inside_rez`, and others), the per-layer and composite confidence flags, the `eligible` flag from S1-07, and `n_missing_features`. This is the sole feature input to the Scoring_Module.
- **cell_id**: The unique identifier of an analysis grid cell. Every layer in the pipeline joins to the grid via `cell_id`. The Scoring_Module MUST reuse the Integrated_Feature_Table `cell_id` values without modification and MUST NOT re-derive the grid. The full NSW grid contains 47,311 cells.
- **Analysis_Grid**: The common analysis cell grid produced by S1-01/S1-02, stored at `DATA/grid/nsw_analysis_grid.gpkg`, keyed by `cell_id`.
- **Eligible_Cell**: A cell whose `eligible` value in the Integrated_Feature_Table is true, meaning no exclusion rule from S1-07 was triggered. Only Eligible_Cells receive a numeric suitability score.
- **Excluded_Cell**: A cell whose `eligible` value in the Integrated_Feature_Table is false, meaning at least one S1-07 exclusion rule was triggered. Excluded_Cells receive a null suitability score.
- **Weights_Config**: The criteria weights configuration file (for example `scoring_weights.yaml`) that declares, for each criterion, the weight, the direction (`higher_is_better` or `lower_is_better`), and a documented rationale. Weights are user inputs loaded at runtime, never hard-coded constants in the Scoring_Module source.
- **Criterion**: A single named feature column from the Integrated_Feature_Table that participates in the score (for example `wind_speed`, `dist_transmission_km`, `demand_proxy`, `slope_deg`, `inside_rez`), together with its configured weight and direction.
- **Normalised_Feature**: A Criterion value rescaled to the [0, 1] range using the Normalisation_Bounds and the Criterion's direction, so that 1 is most favourable and 0 is least favourable for that Criterion.
- **Normalisation_Bounds**: The minimum and maximum value used to rescale a Criterion, computed from the Eligible_Cell population for that Criterion rather than hard-coded.
- **Suitability_Score**: The final per-cell score in the [0, 1] range, computed as the weight-weighted sum of the cell's Normalised_Features divided by the sum of the applied weights, optionally adjusted by a Confidence_Factor.
- **Per_Criterion_Contribution**: The additive contribution of a single Criterion to a cell's Suitability_Score, retrievable per cell so that the score is fully explainable.
- **Rank**: The dense ordinal position of a cell among all scored cells, ordered by descending Suitability_Score, with a documented deterministic tie-breaking rule.
- **Confidence**: A per-cell confidence value carried through from the S1-09 composite confidence flag, with values high or low.
- **Confidence_Factor**: An optional multiplier applied to the raw score to produce an adjusted score, derived from the cell's Confidence when confidence discounting is enabled.
- **MCDA**: Multi-Criteria Decision Analysis, the weighted-criteria scoring approach used by this stage.
- **Scored_Table**: The per-cell output table produced by the Scoring_Module, one row per `cell_id`, containing the score, rank, per-criterion contributions, and confidence columns defined in Requirement 6.
- **Provenance_Record**: The set of provenance artefacts the pipeline maintains for every data path: the generation manifest, the `DATA_PROVENANCE.md` table, and the `source_register` catalogue.
- **EPSG:4326**: WGS84 geographic coordinate reference system, the pipeline's storage CRS.

## Requirements

### Requirement 1: Consume the integrated feature table as sole feature input

**User Story:** As a scoring-model developer, I want the scoring stage to read the integrated feature table, so that all cells are scored from one consistent, pre-joined feature source.

#### Acceptance Criteria

1. WHEN the Scoring_Module runs, THE Scoring_Module SHALL read the Integrated_Feature_Table produced by S1-08 as its sole per-cell feature input.
2. THE Scoring_Module SHALL reuse the Integrated_Feature_Table `cell_id` values without modification and SHALL NOT re-derive, renumber, reformat, or reorder the `cell_id` values.
3. IF the Integrated_Feature_Table is missing or cannot be opened, THEN THE Scoring_Module SHALL halt before writing any Scored_Table output and SHALL return an error indicating the missing or unreadable input path.
4. IF the Integrated_Feature_Table is readable but does not contain a `cell_id` column, THEN THE Scoring_Module SHALL halt before writing any Scored_Table output and SHALL return an error indicating the absent `cell_id` column.
5. IF the Integrated_Feature_Table is readable but does not contain a Criterion column named in the Weights_Config or the `eligible` column, THEN THE Scoring_Module SHALL halt before writing any Scored_Table output and SHALL return an error identifying the missing column.

### Requirement 2: Criteria weights loaded from a configuration file

**User Story:** As a planner, I want the criteria weights to be configurable inputs rather than fixed constants, so that I can adjust the model to reflect my own priorities.

#### Acceptance Criteria

1. THE Scoring_Module SHALL load the criteria weights, per-criterion direction, and per-criterion rationale from the Weights_Config file at runtime.
2. THE Scoring_Module SHALL NOT hard-code criteria weight values as constants in its source code.
3. WHEN the Scoring_Module loads the Weights_Config, THE Scoring_Module SHALL treat each entry as a Criterion definition consisting of a feature name, a weight, a direction of exactly `higher_is_better` or `lower_is_better`, and a rationale.
4. WHERE the Pipeline_Orchestrator or a caller supplies an alternative Weights_Config path, THE Scoring_Module SHALL load weights from that supplied path instead of the default path, and THE Pipeline_Orchestrator SHALL expose a corresponding CLI flag in `pipeline/__main__.py` and pass its value into the stage via `_build_kwargs`.
5. IF the Weights_Config file is missing or cannot be parsed, THEN THE Scoring_Module SHALL halt before writing any Scored_Table output and SHALL return an error indicating the missing or unparsable configuration path.
6. IF a Criterion in the Weights_Config declares a direction other than `higher_is_better` or `lower_is_better`, THEN THE Scoring_Module SHALL halt before writing any Scored_Table output and SHALL return an error identifying the offending Criterion and its invalid direction.
7. IF a Criterion in the Weights_Config declares a weight that is negative or non-numeric, THEN THE Scoring_Module SHALL halt before writing any Scored_Table output and SHALL return an error identifying the offending Criterion.
8. IF the sum of the configured Criterion weights is zero, THEN THE Scoring_Module SHALL halt before writing any Scored_Table output and SHALL return an error indicating that the weights sum to zero.

### Requirement 3: Default weights with documented rationale

**User Story:** As a reviewer, I want the shipped default weights to carry a rationale for each criterion, so that I can understand and challenge the baseline model's assumptions.

#### Acceptance Criteria

1. THE Scoring_Module SHALL ship a default Weights_Config file that defines each default Criterion together with its weight, direction, and a written rationale for that weight and direction.
2. THE default Weights_Config SHALL define the criteria `wind_speed` (direction `higher_is_better`), `dist_transmission_km` (direction `lower_is_better`), `dist_substation_km` (direction `lower_is_better`), `demand_proxy` (direction `higher_is_better`), `slope_deg` (direction `lower_is_better`), and `inside_rez` (direction `higher_is_better`).
3. THE default Weights_Config SHALL record a non-empty rationale string for every default Criterion.
4. WHERE a default Criterion feature name does not exactly match a column present in the Integrated_Feature_Table, THE default Weights_Config Criterion name SHALL be corrected to match the Integrated_Feature_Table column name, so that every default Criterion resolves to a real feature column.

### Requirement 4: Deterministic, reproducible normalisation to [0, 1]

**User Story:** As a scoring-model developer, I want each feature normalised deterministically to a common range, so that criteria measured in different units can be combined comparably.

#### Acceptance Criteria

1. WHEN the Scoring_Function normalises a Criterion whose direction is `higher_is_better`, THE Scoring_Function SHALL compute the Normalised_Feature as `(value - min) / (max - min)` using the Criterion's Normalisation_Bounds.
2. WHEN the Scoring_Function normalises a Criterion whose direction is `lower_is_better`, THE Scoring_Function SHALL compute the Normalised_Feature as `1 - (value - min) / (max - min)` using the Criterion's Normalisation_Bounds.
3. THE Scoring_Function SHALL compute each Criterion's Normalisation_Bounds from the Eligible_Cell population for that Criterion and SHALL NOT use hard-coded normalisation bounds.
4. THE Scoring_Function SHALL constrain every Normalised_Feature to the inclusive [0, 1] range.
5. IF a Criterion's Normalisation_Bounds have equal minimum and maximum over the Eligible_Cell population, THEN THE Scoring_Function SHALL assign a single documented constant Normalised_Feature value for that Criterion for every cell and SHALL record that this Criterion was constant in the method report, rather than dividing by zero.
6. WHEN the Scoring_Function runs twice over identical inputs and an identical Weights_Config, THE Scoring_Function SHALL produce identical Normalised_Features, so that normalisation is deterministic and reproducible.
7. WHERE a Criterion is a boolean feature such as `inside_rez`, THE Scoring_Function SHALL map its values to the [0, 1] range using a documented rule consistent with the Criterion's direction.

### Requirement 5: Weighted MCDA scoring formula

**User Story:** As a planner, I want cells scored by a transparent weighted sum of normalised criteria, so that the ranking is explainable and reproducible.

#### Acceptance Criteria

1. WHEN the Scoring_Function scores an Eligible_Cell, THE Scoring_Function SHALL compute the Suitability_Score as the sum over configured Criteria of `(weight_i × normalised_feature_i)` divided by the sum of the applied Criterion weights.
2. THE Scoring_Function SHALL constrain every Suitability_Score for an Eligible_Cell to the inclusive [0, 1] range.
3. WHERE confidence discounting is enabled, THE Scoring_Function SHALL compute an adjusted Suitability_Score as `score × confidence_factor` using the cell's Confidence_Factor, and SHALL document the Confidence_Factor mapping in the method report.
4. WHERE confidence discounting is disabled, THE Scoring_Function SHALL use the unadjusted Suitability_Score as the cell's final score.
5. THE Scoring_Function SHALL be a pure computation that accepts an in-memory feature DataFrame and a Weights_Config and returns a scored DataFrame, and SHALL NOT perform any file input or output, so that the scoring computation is independently replaceable without changes to the data-loading layer.
6. WHEN the Scoring_Function scores identical inputs with an identical Weights_Config twice, THE Scoring_Function SHALL return identical Suitability_Scores.
7. THE Scoring_Module SHALL NOT use the `wind_speed` feature, or any feature derived from wind data, as a prediction target, and SHALL treat `wind_speed` only as an input Criterion, so that the model is not circular.

### Requirement 6: Scored output table schema, naming, and format

**User Story:** As a downstream consumer, I want a stable, well-named scored table, so that S1-11 and reviewers can join it to the grid and read every score component.

#### Acceptance Criteria

1. THE Scoring_Module SHALL write a Scored_Table containing at least the columns `cell_id`, `suitability_score`, `rank`, `confidence`, and one Per_Criterion_Contribution column per configured Criterion.
2. THE Scoring_Module SHALL name each Per_Criterion_Contribution column with a stable, documented naming pattern derived from the Criterion name, so that every configured Criterion has a corresponding contribution column.
3. THE Scoring_Module SHALL emit exactly one Scored_Table row per Integrated_Feature_Table `cell_id`, with no missing and no duplicate `cell_id`, joinable to the Analysis_Grid on `cell_id`.
4. WHEN a cell is an Excluded_Cell, THE Scoring_Module SHALL record a null `suitability_score`, a null `rank`, and null Per_Criterion_Contribution values for that cell.
5. THE Scoring_Module SHALL name the output file following the `{source}_{dataset}_{year/vintage}_{region}.{ext}` convention using the region slug `nsw`.
6. THE Scoring_Module SHALL store any geometry in the Scored_Table in EPSG:4326.
7. THE Scoring_Module SHALL write the Scored_Table using an atomic write (temporary file plus `os.replace`) via the shared `common/geo` helpers.
8. IF the Scored_Table write fails, THEN THE Scoring_Module SHALL leave any previously existing Scored_Table output unmodified and SHALL return an error indication.
9. THE Scoring_Module SHALL produce the Scored_Table as a fully regenerable derived product reproducible from the Integrated_Feature_Table and the Weights_Config without manual editing.

### Requirement 7: Only eligible cells are scored

**User Story:** As a planner, I want cells excluded by the exclusion layer to carry a null score rather than a misleading number, so that ineligible land is never ranked as if it were developable.

#### Acceptance Criteria

1. WHEN the Scoring_Module scores a cell whose `eligible` value is true, THE Scoring_Module SHALL assign that cell a numeric Suitability_Score.
2. WHEN the Scoring_Module encounters a cell whose `eligible` value is false, THE Scoring_Module SHALL assign that cell a null Suitability_Score and SHALL NOT include that cell in the Rank ordering.
3. THE Scoring_Module SHALL compute every Criterion's Normalisation_Bounds from the Eligible_Cell population only and SHALL exclude Excluded_Cell values from the bounds computation.
4. THE Scoring_Module SHALL report, in the method report, the count of Eligible_Cells scored and the count of Excluded_Cells assigned a null score.

### Requirement 8: Rank ordering

**User Story:** As a planner, I want scored cells ranked from most to least suitable, so that I can identify the strongest candidate sites at a glance.

#### Acceptance Criteria

1. WHEN the Scoring_Module assigns ranks, THE Scoring_Module SHALL order scored cells by descending final Suitability_Score, assigning `rank` 1 to the highest-scoring Eligible_Cell.
2. IF two or more Eligible_Cells share the same final Suitability_Score, THEN THE Scoring_Module SHALL break the tie using a documented deterministic rule so that repeated runs over identical inputs produce identical ranks.
3. THE Scoring_Module SHALL assign a `rank` only to Eligible_Cells and SHALL leave `rank` null for every Excluded_Cell.
4. WHEN the Scoring_Module runs twice over identical inputs and an identical Weights_Config, THE Scoring_Module SHALL produce identical `rank` values.

### Requirement 9: Explainability through per-criterion contributions

**User Story:** As a planner, I want to see how much each criterion contributed to a cell's score, so that a recommendation is something I can interrogate rather than an unexplained assertion.

#### Acceptance Criteria

1. FOR every scored Eligible_Cell, THE Scoring_Module SHALL record the Per_Criterion_Contribution of each configured Criterion to that cell's final Suitability_Score.
2. THE Scoring_Module SHALL define each Per_Criterion_Contribution as the additive amount that the Criterion contributes to the final Suitability_Score, such that the configured Criterion contributions for a cell reconstruct that cell's final Suitability_Score within a documented numeric tolerance.
3. WHERE confidence discounting is enabled, THE Scoring_Module SHALL apply the same Confidence_Factor to the recorded Per_Criterion_Contributions as to the final Suitability_Score, so that the contributions remain reconcilable with the final score.
4. THE Scoring_Module SHALL document, in the method report, the definition of a Per_Criterion_Contribution and the reconciliation rule between contributions and the final Suitability_Score.

### Requirement 10: Confidence carried through

**User Story:** As a data-quality reviewer, I want each scored cell to carry a confidence value, so that low-confidence scores are visible downstream.

#### Acceptance Criteria

1. THE Scoring_Module SHALL populate the `confidence` column of each scored cell from the S1-09 composite confidence flag present in the Integrated_Feature_Table.
2. THE Scoring_Module SHALL set every scored cell's `confidence` to exactly one of the two values high or low, and SHALL set no other value.
3. WHERE confidence discounting is enabled, THE Scoring_Module SHALL derive the Confidence_Factor from the cell's `confidence` value using a documented mapping.
4. IF the composite confidence flag is absent from the Integrated_Feature_Table, THEN THE Scoring_Module SHALL halt before writing any Scored_Table output and SHALL return an error indicating the missing confidence column, rather than fabricating a confidence value.

### Requirement 11: Automated pipeline stage under the run() contract

**User Story:** As a pipeline operator, I want the scoring model to run automatically as a registered stage, so that suitability scores regenerate as part of the standard pipeline run.

#### Acceptance Criteria

1. THE Scoring_Module SHALL expose an importable `run(verbose=False, ...) -> dict` entry point whose first parameter is `verbose` defaulting to `False` and whose return value is a dict, matching the entry-point signature used by the other registered pipeline stages.
2. WHEN the Scoring_Module `run()` completes successfully, THE Scoring_Module SHALL return a summary dict containing a key for the output Scored_Table path and a key for the method report path, and both values SHALL be non-empty filesystem paths that exist on disk after the call returns.
3. IF the Scoring_Module `run()` cannot produce the output Scored_Table or the method report, THEN THE Scoring_Module SHALL raise an error indicating the failure cause and SHALL NOT return a summary dict, so that the Pipeline_Orchestrator halts the run with a non-zero exit status.
4. THE Scoring_Module stage SHALL be registered in the `STAGES` list in `pipeline/config.py` at a position later than the `integration` stage, so that the integrated feature table producer is scheduled before this consumer.
5. THE Pipeline_Orchestrator SHALL dispatch the Scoring_Module stage by returning its `run()` function from `_get_runner` and SHALL supply its keyword arguments from `_build_kwargs` in `pipeline/__main__.py`, including the `verbose` flag and the Weights_Config path.
6. THE scoring subpackage `__init__.py` docstring SHALL describe the scoring stage and its position in the pipeline stage sequence.
7. WHERE the scoring stage introduces a new domain, THE `DOMAINS` list in `pipeline/config.py` SHALL be updated to include the scoring domain.
8. WHEN the Pipeline_Orchestrator resolves the stages to run, THE resolved execution order SHALL place the Scoring_Module stage after the `integration` stage for every invocation that includes both stages, so that every producer runs before its consumers.

### Requirement 12: Provenance for the generated scored output

**User Story:** As a data-governance reviewer, I want the generated scored table to carry provenance, so that its origin, weights, and derivation are traceable.

#### Acceptance Criteria

1. WHEN the Scoring_Module writes the Scored_Table, THE Scoring_Module SHALL record a Provenance_Record entry for the Scored_Table identifying it as a derived product, listing the Integrated_Feature_Table input, the Weights_Config used, and the generation timestamp in UTC.
2. THE Scoring_Module SHALL record, in the Provenance_Record or the method report, an identifier of the Weights_Config content used for the run so that the exact weights that produced the scores are traceable.
3. THE Scoring_Module SHALL label the Scored_Table as a derived product in its provenance so that it is not mistaken for custodial source data.
4. WHERE the Scoring_Module generates the method report, THE Scoring_Module SHALL write it using an atomic write and SHALL stamp it with the do-not-edit banner used by other generated pipeline reports.

### Requirement 13: Method report documenting formula and weights

**User Story:** As a reviewer, I want the scoring method documented in a generated report, so that the formula, weights, and normalisation choices are transparent and reproducible.

#### Acceptance Criteria

1. WHEN the Scoring_Module completes a run, THE Scoring_Module SHALL write a method report stating the scoring formula, the configured Criteria with their weights, directions, and rationales, and the normalisation rule applied to each Criterion.
2. THE method report SHALL record, for each Criterion, the Normalisation_Bounds (minimum and maximum) computed from the Eligible_Cell population for that run.
3. THE method report SHALL record whether confidence discounting was enabled and, when enabled, the Confidence_Factor mapping applied.
4. THE method report SHALL record the count of Eligible_Cells scored, the count of Excluded_Cells assigned a null score, and the count of cells at each `confidence` value.
5. THE method report SHALL state whether the normalisation was linear and, WHERE a non-linear normalisation such as logarithmic normalisation is applied to any distance Criterion, SHALL identify the affected Criteria and the function applied.

### Requirement 14: Validation coverage under the no-silent-passes rule

**User Story:** As a quality reviewer, I want the scored output validated with explicit pass/fail reporting, so that silent scoring problems are caught.

#### Acceptance Criteria

1. THE Scoring_Module validation SHALL confirm that the Scored_Table contains exactly one row per Integrated_Feature_Table `cell_id` and SHALL report the expected cell count, the observed row count, and an explicit pass or fail result.
2. THE Scoring_Module validation SHALL confirm that every Integrated_Feature_Table `cell_id` is present in the Scored_Table with no missing and no extra `cell_id`, and SHALL report the counts and an explicit pass or fail result.
3. THE Scoring_Module validation SHALL confirm that every non-null `suitability_score` value lies within the inclusive [0, 1] range and SHALL report the count of out-of-range values and an explicit pass or fail result.
4. THE Scoring_Module validation SHALL confirm that every Eligible_Cell has a non-null `suitability_score` and every Excluded_Cell has a null `suitability_score`, and SHALL report the count of violating cells and an explicit pass or fail result.
5. THE Scoring_Module validation SHALL confirm that the configured Per_Criterion_Contributions reconcile to the final `suitability_score` within the documented tolerance for every scored Eligible_Cell and SHALL report the count of violating cells and an explicit pass or fail result.
6. THE Scoring_Module validation SHALL confirm that `confidence` contains only the defined values high or low and SHALL report any other value as a fail result, otherwise a pass result.
7. THE Scoring_Module validation SHALL confirm that `rank` is a contiguous ordering over the scored Eligible_Cells with no `rank` assigned to an Excluded_Cell and SHALL report the result as an explicit pass or fail.
8. WHERE cross-domain validation is required, THE cross-domain checks SHALL be placed in `pipeline/validate.py` consistent with the pipeline's validation-tier convention.

### Requirement 15: Unit tests for scoring logic with known inputs and outputs

**User Story:** As a developer, I want the scoring logic covered by unit tests with hand-computed expectations, so that the model stays correct as the code evolves.

#### Acceptance Criteria

1. THE unit tests SHALL cover `higher_is_better` normalisation using a small synthetic feature set, asserting the computed Normalised_Features equal hand-computed expected values within a documented numeric tolerance.
2. THE unit tests SHALL cover `lower_is_better` normalisation using a small synthetic feature set, asserting the computed Normalised_Features equal hand-computed expected values within a documented numeric tolerance.
3. THE unit tests SHALL cover the weighted scoring formula using a small synthetic feature set and a known Weights_Config, asserting the computed Suitability_Scores equal hand-computed expected values within a documented numeric tolerance.
4. THE unit tests SHALL assert that the configured Per_Criterion_Contributions reconstruct the final Suitability_Score within the documented tolerance for the synthetic input.
5. THE unit tests SHALL assert that an Excluded_Cell receives a null Suitability_Score, a null `rank`, and null Per_Criterion_Contributions.
6. THE unit tests SHALL assert that Rank ordering is descending by Suitability_Score and that the documented tie-breaking rule produces deterministic ranks for equal scores.
7. THE unit tests SHALL assert that a Criterion with equal minimum and maximum over the eligible population is handled by the documented constant-value rule rather than raising a divide-by-zero error.
8. THE unit tests SHALL assert that the Scoring_Function returns identical outputs for two runs over identical inputs and an identical Weights_Config, confirming determinism.

### Requirement 16: Documentation updates

**User Story:** As a project maintainer, I want the data specification and README kept consistent with this new stage and output, so that documentation matches behaviour.

#### Acceptance Criteria

1. WHEN the Scoring_Module stage and Scored_Table are added, THE data specification SHALL be updated in section 4 (dataset detail) and section 7 (dataset-to-stage-to-criterion mapping) so that both sections name the Scored_Table output and its columns and reference the Scoring_Module stage that produces it.
2. WHEN the Scoring_Module stage is added, THE README stage-order table and CLI documentation SHALL be updated to list the new stage at the same execution position that the pipeline stage configuration resolves at runtime.
3. IF the README stage-order position or stage name for the Scoring_Module stage does not match the resolved runtime stage configuration, THEN THE documentation SHALL be treated as failing validation and SHALL be corrected to match the runtime configuration before the stage is considered documented.
4. THE documentation SHALL state the scoring formula, the source of the criteria weights (the Weights_Config), the normalisation rule, and the rule that only eligible cells receive a score, so that the model is explicit and reproducible.
5. WHERE a frozen decision (Q1-Q7) is affected by this feature, THE change SHALL follow the specification section 8 change-control process AND SHALL be recorded identically in both the data specification section 2 and the README.
