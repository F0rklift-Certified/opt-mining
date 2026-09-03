# Requirements Document

## Introduction

This feature implements Sprint 1 task S1-12 ("Validation and Sanity Check") for the Opt-Mining geospatial pipeline. It adds a new terminal **sanity-check** pipeline stage under `pipeline/sanity/` that consumes the outputs of the earlier Sprint 1 stages — the ranked shortlist (S1-11), the scored suitability table (S1-10), the integrated feature table (S1-08), the Geoscience Australia wind-generators dataset, and the analysis grid — and produces a human-readable validation report that checks whether the pipeline's outputs are plausible against known reality.

This stage is deliberately a **reality-check reporting** step, not a modelling step and not the structural validation step. It is distinct from the existing cross-domain structural validation in `pipeline/validate.py`, which checks internal data-integrity contracts (row counts, schema, CRS, key coverage). This S1-12 stage instead performs a *plausibility* sanity check: it asks whether known successful wind development areas score highly, whether obviously unsuitable areas are correctly excluded, whether individual cell feature values match their source data, and whether the score distribution is geographically and physically sensible. Because it is a separate concern, the stage and its domain are named separately (for example `sanity` or `sanity_check`) to avoid clashing with the structural `validate` step.

The Opt-Mining constitution constrains this stage directly and non-negotiably. The stage MUST "validate against reality" by checking that known successful wind development areas score highly, using public operational and existing wind-farm data. When a result looks surprising, the stage MUST prompt investigation of the data before any model adjustment, and it MUST NOT adjust the model to "pass" validation: discrepancies are documented honestly, never suppressed. Where systematic issues are found, they are logged as issues for Sprint 2 rather than fixed ad hoc within this stage. The analysis resolution and its limitations MUST be stated wherever results are presented, and every output MUST make clear that this is a preliminary-screening plausibility sanity check — not a formal accuracy assessment and not a site approval.

The stage must satisfy the pipeline's established contracts: the uniform `run(verbose=False, ...) -> dict` stage contract, strict keying to the grid's `cell_id`, explicit and logged CRS handling (EPSG:4326 for storage, EPSG:3577 Australian Albers for any distance or point-in-polygon containment computation), computation of percentile and quartile statistics over the eligible/scored cell population only, the project file-naming convention, atomic writes with a do-not-edit banner on the generated report and any machine-readable sidecar, provenance capture, the "no silent passes" validation rule with explicit expected-versus-observed pass/fail reporting for each automated check, and a reusable, re-runnable design so the same checks can be executed after future pipeline changes.

This document specifies **requirements only**. Design and tasks are deliberately out of scope here.

## Glossary

- **Sanity_Module**: The new sanity-check pipeline stage specified by this document, a new subpackage under `pipeline/sanity/`. It reads the Shortlist, the Scored_Table, the Integrated_Feature_Table, the Wind_Generators dataset, and the Analysis_Grid, runs the four validation checks, and produces the Validation_Report and any machine-readable sidecar. It is distinct from the structural `pipeline/validate.py` step.
- **Pipeline_Orchestrator**: The pipeline CLI/orchestrator (`pipeline/__main__.py`) that resolves the stage list from `pipeline/config.py` and dispatches each stage's `run()` entry point via `_get_runner` and `_build_kwargs`.
- **Structural_Validation**: The existing cross-domain structural validation in `pipeline/validate.py` that checks internal data-integrity contracts (row counts, schema, CRS, key coverage). The Sanity_Module is a separate reality-check stage and MUST NOT be conflated with Structural_Validation.
- **Scored_Table**: The per-cell scored suitability table produced by S1-10, stored at `DATA/scoring/optmining_suitability-score_2026_nsw.gpkg` with a CSV sidecar, one row per `cell_id`, containing `cell_id`, `suitability_score` (float in [0, 1], null for excluded or ineligible cells), `rank` (integer, null for excluded cells), `confidence` (high or low), the per-criterion contribution columns (`contrib_*`), and a Polygon geometry in EPSG:4326. Used for percentile, quartile, and distribution statistics and for per-cell score lookups.
- **Shortlist**: The ranked shortlist produced by S1-11, stored under `DATA/shortlist/` as `sprint1_shortlist_<UTCdate>.csv` and `.geojson`, containing at least `rank`, `cell_id`, `suitability_score`, `confidence`, `centroid_lat`, `centroid_lon`, and an optional `rez` column. Provides the top-ranked cells for the known-wind-farm comparison and geographic-diversity checks.
- **Integrated_Feature_Table**: The integrated NSW feature table produced by S1-08, stored at `DATA/integration/optmining_integrated-features_2026_nsw.gpkg`, one row per `cell_id`, containing the per-cell feature values used in spot-checks (for example `wind_speed`, `slope_deg`, `dist_transmission_km`, a protected-area flag, and the `eligible` flag).
- **Wind_Generators**: The Geoscience Australia wind-generators dataset, stored at `DATA/infrastructure/generators/ga_wind_generators_2026_nsw.geojson`, containing existing NSW wind farms as point (or polygon) geometries with a name attribute. Used to identify known operational wind farms for the known-wind-farm comparison.
- **Analysis_Grid**: The common analysis cell grid produced by S1-01/S1-02, stored at `DATA/grid/nsw_analysis_grid.gpkg`, keyed by `cell_id` and carrying `centroid_lat` and `centroid_lon` per cell. Cell size is 0.05 degree (~5 km). Used to locate which cell a wind-farm point falls within and to confirm that no offshore or ocean cells exist in the grid.
- **CAPAD**: The Collaborative Australian Protected Area Database, the protected-areas source used upstream in the exclusions and geographic layers, referenced for independent verification of protected-area flags in spot-checks.
- **cell_id**: The unique identifier of an Analysis_Grid cell. Every layer in the pipeline joins to the grid via `cell_id`. The Sanity_Module MUST reuse the existing `cell_id` values from its inputs without modification and MUST NOT re-derive the grid.
- **Eligible_Cell**: A cell that was scored and ranked by S1-10, having a non-null `suitability_score` and a non-null `rank`. Percentile, quartile, and distribution statistics are computed over the Eligible_Cell population only.
- **Excluded_Cell**: A cell that was excluded or ineligible in S1-10, having a null `suitability_score` and a null `rank`, or a cell that is not present in the grid at all (for example an offshore location).
- **Known_Wind_Farm**: An existing NSW wind farm identified from the Wind_Generators dataset (for example Sapphire, Bango, or Collector), located to its containing Analysis_Grid cell for the known-wind-farm comparison.
- **Containing_Cell**: The Analysis_Grid cell whose polygon contains a given Wind_Generators point, determined by a point-in-polygon spatial join performed in a single explicit, logged CRS.
- **Percentile**: The percentile rank of a cell's `suitability_score` within the Eligible_Cell population, expressed on a 0-to-100 scale, used to judge whether Known_Wind_Farms score highly.
- **Upper_Quartile**: The top 25 percent of the Eligible_Cell population by `suitability_score` (percentile at or above 75). Most operational wind farms are expected to fall in the Upper_Quartile.
- **Known_Wind_Farm_Comparison**: Check 1. A results table with columns `Wind Farm`, `Cell ID`, `Score`, `Rank`, `Percentile`, and `Notes`, recording for each Known_Wind_Farm its Containing_Cell's score, rank, and percentile, plus a count of how many known farms fall in the Upper_Quartile and an honest investigation note for any that score poorly.
- **Exclusion_Validation**: Check 2. An assertion that named urban centres (Sydney, Newcastle, Wollongong), named national parks (Blue Mountains, Kosciuszko), and offshore or ocean areas are correctly excluded, each reported as an explicit expected-versus-observed pass or fail.
- **Feature_Value_Spot_Check**: Check 3. Independent verification of feature values for a configurable set of Spot_Check_Cells spanning the score range, recording each cell's `wind_speed`, elevation or `slope_deg`, `dist_transmission_km`, and protected-area flag with a discrepancy field for manual comparison against source data.
- **Score_Distribution_Plausibility**: Check 4. A report of distribution statistics over Eligible_Cells, a flag for degenerate clustering at 0 or 1, a report of the geographic diversity of the top-scoring cells, and a report of the correlation between wind resource and score.
- **Spot_Check_Cells**: A configurable set of 5 to 10 cells selected to span the score range (top, middle, and bottom of the Eligible_Cell population) for the Feature_Value_Spot_Check.
- **Anomaly**: An observed result that is surprising or inconsistent with reality, recorded honestly with an investigation note rather than suppressed or used to auto-adjust the model.
- **Sprint2_Issue**: A systematic issue identified during validation, logged as a bug or improvement for Sprint 2 rather than fixed ad hoc within this stage.
- **Validation_Report**: The generated Markdown report at `outputs/sprint1_validation_report.md` containing the Known Wind Farm Comparison, Exclusion Validation, Feature Value Spot-Checks, Score Distribution, Issues for Sprint 2, and Conclusion sections, plus run metadata and the required disclaimers.
- **Results_Sidecar**: An optional machine-readable file (for example JSON) recording the structured results of the automated checks (such as the Known_Wind_Farm_Comparison table), written atomically and carrying provenance.
- **Analysis_Resolution**: The stated spatial resolution of the analysis, being the ~5 km (0.05 degree) analysis grid cell, which must be stated wherever results are presented.
- **Preliminary_Disclaimer**: The explicit statement that the validation is a preliminary-screening plausibility sanity check at the stated Analysis_Resolution, and is not a formal accuracy assessment and not a site approval.
- **Pipeline_Version**: The identifier of the pipeline version that produced a validation run, recorded in the report metadata.
- **Run_Timestamp**: The UTC timestamp at which a validation run executed, used in the report metadata and any sidecar filename.
- **Provenance_Record**: The set of provenance artefacts the pipeline maintains for every generated data path: the generation manifest, the `DATA_PROVENANCE.md` table, and the `source_register` catalogue.
- **EPSG:4326**: WGS84 geographic coordinate reference system, the pipeline's storage CRS.
- **EPSG:3577**: GDA94 Australian Albers equal-area projected coordinate reference system, used for distance and area computation and for containment operations that require metric accuracy.

## Requirements

### Requirement 1: Consume the pipeline outputs with fail-fast on missing or unreadable inputs

**User Story:** As a validation analyst, I want the sanity-check stage to read the shortlist, scored table, integrated features, wind-generators dataset, and grid, so that the checks are performed against the actual pipeline outputs.

#### Acceptance Criteria

1. WHEN the Sanity_Module runs, THE Sanity_Module SHALL read the Shortlist, the Scored_Table, the Integrated_Feature_Table, the Wind_Generators dataset, and the Analysis_Grid as its inputs.
2. THE Sanity_Module SHALL reuse the `cell_id` values from its inputs without modification and SHALL NOT re-derive, renumber, reformat, or reorder the `cell_id` values or the Analysis_Grid.
3. THE Sanity_Module SHALL NOT re-score, re-rank, or otherwise recompute any `suitability_score` or `rank` value, and SHALL rely on the values produced by S1-10 and S1-11.
4. IF any required input is missing or cannot be opened, THEN THE Sanity_Module SHALL halt before writing any Validation_Report or Results_Sidecar and SHALL return an error identifying the missing or unreadable input path.
5. IF a required input is readable but does not contain a column needed by a check (for example `cell_id`, `suitability_score`, `rank`, `wind_speed`, `slope_deg`, `dist_transmission_km`, the protected-area flag, the `eligible` flag, or the wind-farm name attribute), THEN THE Sanity_Module SHALL halt before writing any Validation_Report or Results_Sidecar and SHALL return an error identifying the missing column and the input it was expected in.
6. WHERE the Shortlist is stored as timestamped files under `DATA/shortlist/`, THE Sanity_Module SHALL resolve the Shortlist input by a documented, deterministic selection rule (for example the most recent Run_Timestamp) and SHALL record the resolved Shortlist path in the report metadata.

### Requirement 2: Known-wind-farm comparison (Check 1)

**User Story:** As a validation analyst, I want each known operational wind farm located to its grid cell and its suitability score reported, so that I can confirm that known successful wind areas score highly.

#### Acceptance Criteria

1. WHEN the Sanity_Module performs the Known_Wind_Farm_Comparison, THE Sanity_Module SHALL locate each Wind_Generators feature to its Containing_Cell by a point-in-polygon spatial join against the Analysis_Grid performed in a single explicit CRS, and SHALL log the CRS used for the containment operation.
2. WHERE the containment operation requires metric accuracy, THE Sanity_Module SHALL perform the point-in-polygon join in EPSG:3577 and SHALL make the transformation from EPSG:4326 storage explicit rather than converting between coordinate reference systems silently.
3. FOR each Known_Wind_Farm, THE Sanity_Module SHALL look up the Containing_Cell's `suitability_score`, `rank`, and Percentile within the Eligible_Cell population, and SHALL record a results-table row containing the wind-farm name, the Containing_Cell `cell_id`, the score, the rank, the Percentile, and a notes field.
4. THE Sanity_Module SHALL compute each Known_Wind_Farm's Percentile over the Eligible_Cell population only and SHALL exclude Excluded_Cell values from the Percentile computation.
5. THE Sanity_Module SHALL report the count and proportion of Known_Wind_Farms whose Containing_Cell falls in the Upper_Quartile, and SHALL state the expectation that most operational wind farms fall in the Upper_Quartile.
6. IF a Known_Wind_Farm falls in a Containing_Cell that scores poorly (for example below a documented Percentile threshold) or in an Excluded_Cell with a null score, THEN THE Sanity_Module SHALL record the outcome honestly in the notes field with an investigation note distinguishing a likely data issue from a legitimate model result, and SHALL NOT adjust the model to raise that cell's score.
7. IF a Known_Wind_Farm point does not fall within any Analysis_Grid cell, THEN THE Sanity_Module SHALL record that outcome explicitly in the results table with a note rather than omitting the wind farm silently.

### Requirement 3: Exclusion validation (Check 2)

**User Story:** As a validation analyst, I want obviously unsuitable areas confirmed as excluded, so that I can trust that the pipeline removes land it should never rank.

#### Acceptance Criteria

1. WHEN the Sanity_Module performs the Exclusion_Validation, THE Sanity_Module SHALL assert that cells covering the named urban centres Sydney, Newcastle, and Wollongong are excluded, treating an excluded cell as an Excluded_Cell that is ineligible with a null `suitability_score`.
2. WHEN the Sanity_Module performs the Exclusion_Validation, THE Sanity_Module SHALL assert that cells covering the named national parks Blue Mountains and Kosciuszko are excluded.
3. WHEN the Sanity_Module performs the Exclusion_Validation, THE Sanity_Module SHALL assert that no offshore or ocean cells exist in the Analysis_Grid.
4. FOR each Exclusion_Validation assertion, THE Sanity_Module SHALL report the expected outcome, the observed outcome, and an explicit pass or fail result, and SHALL NOT record a pass without an observed value.
5. THE Sanity_Module SHALL resolve each named urban centre and national park to the cells covering it by a documented, deterministic rule (for example a named-place coordinate or boundary geometry located to the grid in a single explicit CRS), and SHALL record the rule and the CRS used in the report.
6. IF any Exclusion_Validation assertion fails (for example an urban or protected cell is found eligible, or an offshore cell is found in the grid), THEN THE Sanity_Module SHALL report the failure honestly as an Anomaly with an investigation note and SHALL NOT suppress the failure to make the check pass.

### Requirement 4: Feature-value spot-checks (Check 3)

**User Story:** As a validation analyst, I want feature values for a sample of cells recorded for independent verification, so that I can confirm the pipeline's per-cell feature values match their source data.

#### Acceptance Criteria

1. THE Sanity_Module SHALL select a configurable number of Spot_Check_Cells between 5 and 10 inclusive, defaulting to a documented value within that range when no value is supplied.
2. WHEN the Sanity_Module selects the Spot_Check_Cells, THE Sanity_Module SHALL select cells spanning the score range of the Eligible_Cell population, including cells from the top, the middle, and the bottom of the score range, using a documented deterministic selection rule.
3. FOR each Spot_Check_Cell, THE Sanity_Module SHALL record the cell's `cell_id`, its centroid coordinates in EPSG:4326, and its feature values `wind_speed`, elevation or `slope_deg`, `dist_transmission_km`, and protected-area flag, together with a discrepancy field for recording the result of independent verification against source data (open GWA for wind speed, a topographic reference for elevation, a GIS measurement for distance, and CAPAD for the protected-area flag).
4. THE Sanity_Module SHALL state, for each recorded feature value, the source against which it should be independently verified, so that a human reviewer can perform the verification without ambiguity.
5. IF the number of Spot_Check_Cells requested is outside the inclusive range 5 to 10, THEN THE Sanity_Module SHALL halt before writing any Validation_Report and SHALL return an error identifying the invalid Spot_Check_Cells count.
6. IF a selected Spot_Check_Cell is missing a required feature value in the Integrated_Feature_Table, THEN THE Sanity_Module SHALL record the missing value explicitly in the spot-check table with a note rather than fabricating a value.

### Requirement 5: Score-distribution plausibility (Check 4)

**User Story:** As a validation analyst, I want the score distribution characterised, so that I can judge whether the scores are physically and geographically sensible.

#### Acceptance Criteria

1. THE Sanity_Module SHALL report distribution statistics over the Eligible_Cell population, including at least the minimum, maximum, mean, standard deviation, and quartiles of `suitability_score`, and SHALL compute them over the Eligible_Cell population only.
2. THE Sanity_Module SHALL evaluate whether the score distribution is degenerately clustered at 0 or at 1 using a documented rule, and SHALL report an explicit pass or fail for the clustering check.
3. THE Sanity_Module SHALL report the geographic diversity of the top-scoring cells, reporting at least the latitude range and longitude range of the top-scoring cells so that a single-region concentration is visible.
4. THE Sanity_Module SHALL report the relationship between wind resource and score by computing and reporting a correlation between `wind_speed` and `suitability_score` over the Eligible_Cell population, and SHALL state the expectation that higher wind resource generally corresponds to higher score.
5. IF the score distribution is degenerately clustered, or the wind-resource-versus-score relationship is not sensibly positive, THEN THE Sanity_Module SHALL report the outcome honestly as an Anomaly with an investigation note and SHALL NOT adjust the model to alter the distribution.

### Requirement 6: Anomaly recording and Sprint 2 issues log

**User Story:** As a project maintainer, I want anomalies and systematic issues recorded honestly, so that surprising results are investigated and carried forward rather than hidden or patched ad hoc.

#### Acceptance Criteria

1. WHEN the Sanity_Module observes an Anomaly during any check, THE Sanity_Module SHALL record the Anomaly with an investigation note in the Validation_Report and SHALL NOT suppress it.
2. THE Sanity_Module SHALL NOT adjust, re-weight, or re-tune the model in response to any check outcome, and SHALL document discrepancies honestly rather than making a check pass by changing the model.
3. WHERE a check reveals a systematic issue, THE Sanity_Module SHALL log the issue as a Sprint2_Issue in the Issues for Sprint 2 section of the Validation_Report rather than fixing it ad hoc within this stage.
4. FOR each recorded Sprint2_Issue, THE Sanity_Module SHALL record a description of the issue, the check that surfaced it, and whether it is a suspected data issue or a suspected model issue.
5. THE Sanity_Module SHALL distinguish, for each surprising result, between a likely data issue and a legitimate model result, consistent with the constitution's requirement to investigate the data before adjusting the model.

### Requirement 7: Validation report generation with required sections, metadata, and disclaimers

**User Story:** As a decision-maker, I want a single validation report with all check results, run metadata, and the required disclaimers, so that I can judge whether the pipeline output is trustworthy for preliminary screening.

#### Acceptance Criteria

1. WHEN the Sanity_Module completes a run, THE Sanity_Module SHALL write the Validation_Report to `outputs/sprint1_validation_report.md`.
2. THE Validation_Report SHALL contain the sections Known Wind Farm Comparison, Exclusion Validation, Feature Value Spot-Checks, Score Distribution, Issues for Sprint 2, and Conclusion.
3. THE Validation_Report SHALL record the run metadata comprising the run date, the Pipeline_Version, the total cell count, and the eligible cell count.
4. THE Conclusion section SHALL state an overall assessment of whether the pipeline output is or is not trustworthy for preliminary screening, based on the recorded check results.
5. THE Validation_Report SHALL include the Preliminary_Disclaimer stating that the validation is a preliminary-screening plausibility sanity check and is not a formal accuracy assessment and not a site approval.
6. THE Validation_Report SHALL state the Analysis_Resolution (the ~5 km, 0.05 degree analysis grid cell) and its limitations wherever results are presented.
7. THE Sanity_Module SHALL write the Validation_Report using an atomic write (temporary file plus `os.replace`) via the shared `common/geo` helpers and SHALL stamp it with the do-not-edit banner used by other generated pipeline reports.
8. WHERE the Sanity_Module produces a Results_Sidecar, THE Results_Sidecar SHALL contain the structured results of the automated checks (including the Known_Wind_Farm_Comparison table), SHALL be written using an atomic write, and SHALL be labelled a derived product.
9. IF writing the Validation_Report or the Results_Sidecar fails, THEN THE Sanity_Module SHALL leave any previously existing output for that run unmodified and SHALL return an error indication.

### Requirement 8: Do-not-adjust-the-model-to-pass rule

**User Story:** As a project reviewer, I want the validation stage to never modify the model to make checks pass, so that the checks remain an honest independent test of the pipeline.

#### Acceptance Criteria

1. THE Sanity_Module SHALL treat all inputs as read-only and SHALL NOT write to, overwrite, or modify the Shortlist, the Scored_Table, the Integrated_Feature_Table, the Wind_Generators dataset, or the Analysis_Grid.
2. THE Sanity_Module SHALL NOT alter any criteria weight, normalisation bound, exclusion rule, or scoring parameter as a consequence of any check outcome.
3. WHEN a check produces a failing or surprising result, THE Sanity_Module SHALL report the result honestly and, where systematic, record a Sprint2_Issue, and SHALL NOT change the model to convert a fail into a pass.

### Requirement 9: Automated pipeline stage under the run() contract, registered as the terminal stage

**User Story:** As a pipeline operator, I want the sanity check to run automatically as the final registered stage, so that the validation report regenerates as part of the standard pipeline run.

#### Acceptance Criteria

1. THE Sanity_Module SHALL expose an importable `run(verbose=False, ...) -> dict` entry point whose first parameter is `verbose` defaulting to `False` and whose return value is a dict, matching the entry-point signature used by the other registered pipeline stages.
2. WHEN the Sanity_Module `run()` completes successfully, THE Sanity_Module SHALL return a summary dict containing a key for the Validation_Report path and, where produced, a key for the Results_Sidecar path, and each value SHALL be a non-empty filesystem path that exists on disk after the call returns.
3. IF the Sanity_Module `run()` cannot produce the Validation_Report, THEN THE Sanity_Module SHALL raise an error indicating the failure cause and SHALL NOT return a summary dict, so that the Pipeline_Orchestrator halts the run with a non-zero exit status.
4. THE Sanity_Module stage SHALL be registered in the `STAGES` list in `pipeline/config.py` at a position later than the `shortlist` stage, so that the shortlist producer is scheduled before this consumer, and SHALL be the terminal stage in the Sprint 1 stage sequence.
5. THE Sanity_Module stage SHALL be named distinctly (for example `sanity` or `sanity_check`) so that it does not clash with the existing structural `validate` step, and THE `DOMAINS` list in `pipeline/config.py` SHALL be updated to include the corresponding validation domain.
6. THE Pipeline_Orchestrator SHALL dispatch the Sanity_Module stage by returning its `run()` function from `_get_runner` and SHALL supply its keyword arguments from `_build_kwargs` in `pipeline/__main__.py`, including the `verbose` flag.
7. WHERE a CLI flag is useful, THE Pipeline_Orchestrator SHALL expose a corresponding flag in `pipeline/__main__.py` (for example a Spot_Check_Cells count flag such as `--sanity-spot-check-cells` and a Wind_Generators dataset path override) and SHALL pass its value into the stage via `_build_kwargs`.
8. THE sanity subpackage `__init__.py` docstring SHALL describe the sanity-check stage, its distinction from the structural `validate` step, and its terminal position in the pipeline stage sequence.
9. WHEN the Pipeline_Orchestrator resolves the stages to run, THE resolved execution order SHALL place the Sanity_Module stage after the `shortlist` stage for every invocation that includes both stages, so that every producer runs before its consumers.

### Requirement 10: Provenance for the generated report and sidecar

**User Story:** As a data-governance reviewer, I want the generated validation report and any sidecar to carry provenance, so that their origin and derivation are traceable.

#### Acceptance Criteria

1. WHEN the Sanity_Module writes the Validation_Report or the Results_Sidecar, THE Sanity_Module SHALL record a Provenance_Record entry for each generated output identifying it as a derived product, listing the Shortlist, Scored_Table, Integrated_Feature_Table, Wind_Generators, and Analysis_Grid inputs, and the Run_Timestamp in UTC.
2. THE Sanity_Module SHALL label the Validation_Report and the Results_Sidecar as derived products in their provenance so that they are not mistaken for custodial source data.
3. THE Sanity_Module SHALL add a `DATA_PROVENANCE.md` row and a `source_register` entry for the generated outputs consistent with the pipeline's provenance convention.
4. WHERE the Sanity_Module produces the Results_Sidecar, THE Sanity_Module SHALL name it following the project `{source}_{dataset}_{year/vintage}_{region}.{ext}` naming convention using the region slug `nsw`, or SHALL document the naming rule where the report retains its fixed `outputs/sprint1_validation_report.md` path.

### Requirement 11: No-silent-passes explicit pass/fail reporting for each automated check

**User Story:** As a quality reviewer, I want every automated check to report expected versus observed with an explicit pass or fail, so that no check silently passes.

#### Acceptance Criteria

1. FOR each automated check, THE Sanity_Module SHALL report the expected outcome, the observed outcome, and an explicit pass or fail result, and SHALL NOT record a pass without a recorded observed value.
2. THE Sanity_Module SHALL report the Known_Wind_Farm_Comparison outcome (for example the count of known farms in the Upper_Quartile against the expectation) as an explicit pass or fail with the observed count recorded.
3. THE Sanity_Module SHALL report each Exclusion_Validation assertion as an explicit pass or fail with the observed eligibility or grid-membership recorded.
4. THE Sanity_Module SHALL report the Score_Distribution_Plausibility clustering and wind-resource-correlation checks as explicit pass or fail results with the observed statistics recorded.
5. WHEN any automated check fails, THE Sanity_Module SHALL surface the failure in the Validation_Report and SHALL NOT overwrite or hide the failing result, consistent with the "no silent passes" rule.
6. WHERE cross-domain structural validation is required, THE cross-domain structural checks SHALL remain in `pipeline/validate.py` and THE Sanity_Module SHALL NOT duplicate or replace Structural_Validation.

### Requirement 12: Reusable, re-runnable validation

**User Story:** As a developer, I want the validation checks to be reusable and re-runnable, so that the same sanity checks can be executed after future pipeline changes.

#### Acceptance Criteria

1. THE Sanity_Module SHALL implement the automated check logic so that it can be re-run against updated pipeline outputs without manual code changes between runs.
2. THE Sanity_Module SHALL separate the automated check computations (point-in-cell location, Percentile computation, exclusion assertions, distribution statistics) from report formatting and file input/output, so that the check computations are independently testable and reusable.
3. WHEN the Sanity_Module is re-run over identical inputs, THE Sanity_Module SHALL produce identical automated check results, so that the checks are deterministic and reproducible.
4. WHERE a Wind_Generators dataset path or a Spot_Check_Cells count is supplied, THE Sanity_Module SHALL use the supplied values so that the same checks can be re-run with alternative inputs.

### Requirement 13: Unit tests for the automated check logic

**User Story:** As a developer, I want the automated check logic covered by unit tests, so that the sanity checks stay correct as the code evolves.

#### Acceptance Criteria

1. THE unit tests SHALL cover point-in-cell location using a small synthetic grid and synthetic wind-farm points, asserting that each point is located to the correct Containing_Cell in the documented CRS.
2. THE unit tests SHALL cover Percentile computation over a small synthetic Eligible_Cell population, asserting that computed percentiles equal hand-computed expected values within a documented numeric tolerance and that Excluded_Cell values are omitted from the computation.
3. THE unit tests SHALL cover the exclusion assertions, asserting that a synthetic urban, protected, or offshore location is correctly detected as excluded and that a failing assertion is reported as a fail with the observed value.
4. THE unit tests SHALL cover the distribution statistics, asserting that the minimum, maximum, mean, standard deviation, quartiles, degenerate-clustering flag, and wind-resource correlation equal hand-computed expected values within a documented numeric tolerance for the synthetic input.
5. THE unit tests SHALL cover the Spot_Check_Cells selection, asserting that the selected count lies within the inclusive range 5 to 10 and that the selected cells span the top, middle, and bottom of the synthetic score range.
6. THE unit tests SHALL assert that the automated check computations return identical results for two runs over identical inputs, confirming determinism.

### Requirement 14: Documentation updates

**User Story:** As a project maintainer, I want the data specification and README kept consistent with this new stage and output, so that documentation matches behaviour.

#### Acceptance Criteria

1. WHEN the Sanity_Module stage and the Validation_Report are added, THE data specification SHALL be updated in section 4 (dataset detail) and section 7 (dataset-to-stage-to-criterion mapping) so that both sections name the Validation_Report and any Results_Sidecar and reference the Sanity_Module stage that produces them.
2. WHEN the Sanity_Module stage is added, THE README stage-order table and CLI documentation SHALL be updated to list the new terminal stage at the same execution position that the pipeline stage configuration resolves at runtime, including any Spot_Check_Cells and Wind_Generators-path CLI flags.
3. IF the README stage-order position or stage name for the Sanity_Module stage does not match the resolved runtime stage configuration, THEN THE documentation SHALL be treated as failing validation and SHALL be corrected to match the runtime configuration before the stage is considered documented.
4. THE documentation SHALL state that the validation is a preliminary-screening plausibility sanity check at the stated Analysis_Resolution and is not a formal accuracy assessment and not a site approval, so that the constraint is explicit in the project documentation.
5. THE documentation SHALL state that this Sanity_Module stage is distinct from the structural `pipeline/validate.py` step, so that the two validation concerns are not conflated.
6. WHERE a frozen decision (Q1-Q7) is affected by this feature, THE change SHALL follow the specification section 8 change-control process AND SHALL be recorded identically in both the data specification section 2 and the README; this stage does not change any frozen decision.
