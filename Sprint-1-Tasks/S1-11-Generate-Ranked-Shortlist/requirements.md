# Requirements Document

## Introduction

This feature implements Sprint 1 task S1-11 ("Generate a Preliminary Ranked Shortlist") for the Opt-Mining geospatial pipeline. It adds a new **shortlist** pipeline stage under `pipeline/shortlist/` that consumes the scored suitability table produced by the scoring stage (S1-10) and produces the Sprint 1 headline output: a ranked list of the top candidate cells in NSW for wind energy development, exported for both tabular review (CSV) and map visualisation (GeoJSON), together with summary statistics.

This stage is deliberately a **filtering and formatting** step, not a modelling step. The suitability scores and ranks are computed upstream in S1-10; this stage selects the top-N eligible cells by their existing rank, joins their geographic coordinates from the analysis grid, formats the selection into the two documented output formats, and computes descriptive summary statistics over the eligible population and the selected top sites. It performs no re-scoring and no re-ranking that would diverge from the S1-10 rank ordering.

The Opt-Mining constitution constrains this stage directly. The shortlist is a **preliminary screening starting point**, not a final recommendation: "Its output informs what to study next; it never constitutes a site approval." The analysis resolution and its limitations must be stated wherever results are presented. Accordingly, every output and its metadata must carry an explicit preliminary-screening disclaimer and an explicit statement of the analysis resolution (the ~5 km analysis grid cell), so that no consumer mistakes a screening shortlist for a site approval. The stage is blocked by the scoring stage (S1-10) and blocks the mapping/reporting stage (S1-12).

The stage must satisfy the pipeline's established contracts: the uniform `run(verbose=False, ...) -> dict` stage contract, strict keying to the grid's `cell_id`, explicit and logged CRS handling (EPSG:4326 storage, GeoJSON output in EPSG:4326), the project file-naming convention for timestamped and versioned outputs, atomic writes with a do-not-edit banner on generated reports, provenance capture, and the "no silent passes" validation rule.

This document specifies **requirements only**. Design and tasks are deliberately out of scope here.

## Glossary

- **Shortlist_Module**: The new shortlist pipeline stage specified by this document, a new subpackage under `pipeline/shortlist/`. It reads the Scored_Table and the Analysis_Grid and produces the ranked shortlist outputs (CSV and GeoJSON) plus a summary report.
- **Pipeline_Orchestrator**: The pipeline CLI/orchestrator (`pipeline/__main__.py`) that resolves the stage list from `pipeline/config.py` and dispatches each stage's `run()` entry point via `_get_runner` and `_build_kwargs`.
- **Scored_Table**: The per-cell scored suitability table produced by the scoring stage (S1-10), stored at `DATA/scoring/optmining_suitability-score_2026_nsw.gpkg` with a CSV sidecar, one row per `cell_id` (47,311 NSW cells), containing `cell_id`, `suitability_score` (float in [0, 1], null for excluded or ineligible cells), `rank` (integer, null for excluded cells), `confidence` (high or low, carried from S1-09), the per-criterion contribution columns (`contrib_*`), and a Polygon geometry in EPSG:4326. This is the sole score input to the Shortlist_Module.
- **Analysis_Grid**: The common analysis cell grid produced by S1-01/S1-02, stored at `DATA/grid/nsw_analysis_grid.gpkg`, keyed by `cell_id`, carrying `centroid_lat` and `centroid_lon` per cell. Cell size is 0.05 degree (~5 km); the full NSW grid contains 47,311 cells.
- **cell_id**: The unique identifier of an Analysis_Grid cell. Every layer in the pipeline joins to the grid via `cell_id`. The Shortlist_Module MUST reuse the Scored_Table and Analysis_Grid `cell_id` values without modification and MUST NOT re-derive the grid.
- **Eligible_Cell**: A cell in the Scored_Table with a non-null `suitability_score` and a non-null `rank`, meaning it was scored and ranked by S1-10. Only Eligible_Cells are candidates for the shortlist.
- **Excluded_Cell**: A cell in the Scored_Table with a null `suitability_score` and a null `rank`, meaning it was excluded or ineligible in S1-10. Excluded_Cells MUST NOT appear in the shortlist.
- **Top_N**: The configurable number of highest-ranked Eligible_Cells to include in the shortlist, defaulting to 20.
- **Shortlist**: The ordered selection of up to Top_N Eligible_Cells, ordered by ascending `rank` (rank 1 first), that forms the headline output of this stage.
- **Shortlist_CSV**: The tabular CSV export of the Shortlist, with the documented output schema defined in Requirement 4.
- **Shortlist_GeoJSON**: The GeoJSON export of the Shortlist, in EPSG:4326, for map visualisation, with one feature per shortlisted cell.
- **Centroid_Coordinates**: The `centroid_lat` and `centroid_lon` values of a cell, joined from the Analysis_Grid on `cell_id`, expressed in EPSG:4326.
- **REZ**: Renewable Energy Zone. A shortlisted cell may carry an optional `rez` context column identifying the Renewable Energy Zone it lies within, where that information is available upstream.
- **Summary_Statistics**: The descriptive statistics computed by the Shortlist_Module, covering the score distribution over Eligible_Cells, the geographic spread of the top sites, and the confidence distribution of the top sites, defined in Requirement 6.
- **Summary_Report**: The generated report produced by the Shortlist_Module recording the run metadata, the Summary_Statistics, the disclaimer, and the analysis-resolution statement.
- **Analysis_Resolution**: The stated spatial resolution of the analysis, being the ~5 km (0.05 degree) analysis grid cell, which must be stated wherever results are presented.
- **Preliminary_Disclaimer**: The explicit statement that the shortlist is a preliminary screening output at the stated Analysis_Resolution and is not a site approval or a final recommendation.
- **Pipeline_Version**: The identifier of the pipeline version that produced a shortlist run, recorded in the output metadata.
- **Run_Timestamp**: The UTC timestamp at which a shortlist run executed, used both in the output filenames and in the output metadata.
- **Provenance_Record**: The set of provenance artefacts the pipeline maintains for every data path: the generation manifest, the `DATA_PROVENANCE.md` table, and the `source_register` catalogue.
- **EPSG:4326**: WGS84 geographic coordinate reference system, the pipeline's storage and GeoJSON output CRS.

## Requirements

### Requirement 1: Consume the scored table as the sole score input

**User Story:** As a screening analyst, I want the shortlist stage to read the scored suitability table, so that the ranking reflects the S1-10 scoring without re-computation.

#### Acceptance Criteria

1. WHEN the Shortlist_Module runs, THE Shortlist_Module SHALL read the Scored_Table produced by S1-10 as its sole per-cell score input.
2. THE Shortlist_Module SHALL reuse the Scored_Table `cell_id` values without modification and SHALL NOT re-derive, renumber, reformat, or reorder the `cell_id` values.
3. THE Shortlist_Module SHALL NOT re-score or re-rank cells, and SHALL rely on the `suitability_score` and `rank` values as produced by S1-10.
4. IF the Scored_Table is missing or cannot be opened, THEN THE Shortlist_Module SHALL halt before writing any shortlist output and SHALL return an error indicating the missing or unreadable input path.
5. IF the Scored_Table is readable but does not contain the `cell_id`, `suitability_score`, `rank`, or `confidence` column, THEN THE Shortlist_Module SHALL halt before writing any shortlist output and SHALL return an error identifying the missing column.

### Requirement 2: Select the top-N eligible cells by rank

**User Story:** As a screening analyst, I want the top-ranked eligible cells selected in rank order, so that the shortlist shows the strongest candidate sites first.

#### Acceptance Criteria

1. WHEN the Shortlist_Module selects the Shortlist, THE Shortlist_Module SHALL select the Eligible_Cells with the smallest `rank` values up to Top_N, ordered by ascending `rank` so that the cell with `rank` 1 appears first.
2. THE Shortlist_Module SHALL include only Eligible_Cells in the Shortlist and SHALL NOT include any Excluded_Cell.
3. THE Shortlist ordering SHALL be consistent with the S1-10 `rank` ordering, such that for any two shortlisted cells the cell with the smaller `rank` appears earlier in the Shortlist.
4. WHERE the Scored_Table `rank` values contain ties or gaps, THE Shortlist_Module SHALL preserve the S1-10 rank ordering and SHALL NOT re-assign ranks, so that the shortlist reflects the upstream ranking exactly.
5. THE Shortlist_Module SHALL record, in the Summary_Report, the count of Eligible_Cells available for selection and the count of cells actually included in the Shortlist.

### Requirement 3: Configurable Top_N with edge-case handling

**User Story:** As a screening analyst, I want to configure how many cells the shortlist contains, so that I can widen or narrow the screening output to suit the review.

#### Acceptance Criteria

1. THE Shortlist_Module SHALL accept a configurable Top_N value and SHALL default Top_N to 20 when no value is supplied.
2. WHERE the Pipeline_Orchestrator or a caller supplies a Top_N value, THE Shortlist_Module SHALL use the supplied value, and THE Pipeline_Orchestrator SHALL expose a corresponding CLI flag (for example `--shortlist-top-n`) in `pipeline/__main__.py` and pass its value into the stage via `_build_kwargs`.
3. WHERE a Top_N value is also declared in the pipeline configuration, THE Shortlist_Module SHALL resolve the effective Top_N from the configuration when no command-line value is supplied, and SHALL prefer an explicitly supplied command-line value over the configuration default.
4. IF Top_N exceeds the count of Eligible_Cells, THEN THE Shortlist_Module SHALL include every Eligible_Cell in the Shortlist, SHALL record in the Summary_Report that the requested Top_N exceeded the eligible count, and SHALL NOT pad the Shortlist with Excluded_Cells or fabricated rows.
5. IF Top_N is not a positive integer, THEN THE Shortlist_Module SHALL halt before writing any shortlist output and SHALL return an error identifying the invalid Top_N value.
6. IF the count of Eligible_Cells is zero, THEN THE Shortlist_Module SHALL produce an empty Shortlist, SHALL record in the Summary_Report that no eligible cells were available, and SHALL still emit the output files with headers and the Preliminary_Disclaimer rather than failing silently.

### Requirement 4: Shortlist output schema and coordinate join

**User Story:** As a screening analyst, I want each shortlisted cell to carry its rank, score, confidence, and map coordinates, so that I can verify candidate sites on a map.

#### Acceptance Criteria

1. THE Shortlist_Module SHALL produce a Shortlist containing at least the columns `rank`, `cell_id`, `suitability_score`, `confidence`, `centroid_lat`, and `centroid_lon`, in that documented column order.
2. THE Shortlist_Module SHALL join `centroid_lat` and `centroid_lon` for each shortlisted cell from the Analysis_Grid on `cell_id`, expressed in EPSG:4326.
3. WHERE an optional context column such as `rez` (Renewable Energy Zone) or a nearby-existing-wind-farm indicator is available from an upstream layer, THE Shortlist_Module SHALL add it as a named, documented column and SHALL record its definition and source in the Summary_Report.
4. IF the Analysis_Grid is missing or cannot be opened, THEN THE Shortlist_Module SHALL halt before writing any shortlist output and SHALL return an error indicating the missing or unreadable grid path.
5. IF a shortlisted `cell_id` has no matching row in the Analysis_Grid, THEN THE Shortlist_Module SHALL halt before writing any shortlist output and SHALL return an error identifying the unmatched `cell_id`, rather than emitting a shortlist row with a fabricated or null coordinate.
6. THE Shortlist_Module SHALL carry `suitability_score`, `confidence`, and `rank` values byte-for-consistent with the Scored_Table for every shortlisted cell, and SHALL NOT recompute them.

### Requirement 5: CSV and GeoJSON export in documented formats

**User Story:** As a screening analyst, I want the shortlist as both a table and a map layer, so that I can review it in a spreadsheet and visualise it on a map.

#### Acceptance Criteria

1. THE Shortlist_Module SHALL export the Shortlist as a Shortlist_CSV containing the documented columns from Requirement 4 in the documented column order.
2. THE Shortlist_Module SHALL export the Shortlist as a Shortlist_GeoJSON containing one feature per shortlisted cell, with the documented columns from Requirement 4 carried as feature properties.
3. THE Shortlist_Module SHALL store the Shortlist_GeoJSON geometry in EPSG:4326, and SHALL make the storage CRS explicit rather than assuming an unstated CRS.
4. WHERE the Shortlist_GeoJSON feature geometry represents a shortlisted cell, THE Shortlist_Module SHALL use a documented geometry choice (the cell centroid point or the cell polygon) and SHALL state the chosen geometry type in the Summary_Report.
5. THE Shortlist_CSV and Shortlist_GeoJSON SHALL contain the same set of shortlisted `cell_id` values in the same rank order, so that the two exports are consistent with one another.
6. THE Shortlist_Module SHALL write each output file using an atomic write (temporary file plus `os.replace`) via the shared `common/geo` helpers.
7. IF an output write fails, THEN THE Shortlist_Module SHALL leave any previously existing output for that run unmodified and SHALL return an error indication.

### Requirement 6: Summary statistics over eligible cells and top sites

**User Story:** As a screening analyst, I want summary statistics for the eligible population and the top sites, so that I can judge how the shortlist sits within the wider results.

#### Acceptance Criteria

1. THE Shortlist_Module SHALL compute a score distribution over the Eligible_Cells reporting the minimum, maximum, mean, and standard deviation of `suitability_score`, and SHALL record it in the Summary_Report.
2. THE Shortlist_Module SHALL compute the geographic spread of the shortlisted top sites, reporting at least the latitude range and longitude range of the shortlisted `centroid_lat` and `centroid_lon` values, and SHALL record it in the Summary_Report.
3. WHERE Renewable Energy Zone membership is available for shortlisted cells, THE Shortlist_Module SHALL report which Renewable Energy Zones are represented among the top sites in the Summary_Report.
4. THE Shortlist_Module SHALL compute the confidence distribution of the shortlisted top sites, reporting the count of shortlisted cells at each `confidence` value (high and low), and SHALL record it in the Summary_Report.
5. THE Shortlist_Module SHALL record, in the Summary_Report, the total cell count, the eligible cell count, and the scored cell count for the run.
6. WHEN the Shortlist_Module computes the score distribution, THE Shortlist_Module SHALL compute it over the Eligible_Cell population only and SHALL exclude Excluded_Cell values from the distribution.

### Requirement 7: Timestamped and versioned output filenames

**User Story:** As a project maintainer, I want each shortlist run written to a timestamped, versioned file, so that successive screening runs are distinguishable and never silently overwrite one another.

#### Acceptance Criteria

1. THE Shortlist_Module SHALL name the Shortlist_CSV and Shortlist_GeoJSON output files with a timestamped, versioned pattern that includes the Run_Timestamp (for example `sprint1_shortlist_<UTCdate>.csv` and `sprint1_shortlist_<UTCdate>.geojson`).
2. THE Shortlist_Module SHALL derive the Run_Timestamp in UTC and SHALL use the same Run_Timestamp value in the output filenames and in the output metadata for a single run.
3. WHERE the project `{source}_{dataset}_{year/vintage}_{region}.{ext}` naming convention applies to a shortlist output, THE Shortlist_Module SHALL use the region slug `nsw`.
4. IF an output file with the resolved timestamped name already exists, THEN THE Shortlist_Module SHALL follow a documented, deterministic rule for that collision (for example including a finer-grained timestamp) and SHALL NOT silently discard the earlier file without recording the outcome in the Summary_Report.

### Requirement 8: Preliminary-screening disclaimer and analysis-resolution statement

**User Story:** As a decision-maker, I want every shortlist output to state that it is a preliminary screening result at the stated resolution, so that it is never mistaken for a site approval.

#### Acceptance Criteria

1. THE Shortlist_Module SHALL include the Preliminary_Disclaimer stating that the shortlist is a preliminary screening output and is not a site approval or final recommendation in the Summary_Report and in the output metadata.
2. THE Shortlist_Module SHALL state the Analysis_Resolution (the ~5 km, 0.05 degree analysis grid cell) wherever the shortlist results are presented, including the Summary_Report and the output metadata.
3. WHERE the Shortlist_GeoJSON supports file-level metadata or properties, THE Shortlist_Module SHALL carry the Preliminary_Disclaimer and the Analysis_Resolution statement in that metadata.
4. WHERE the Shortlist_CSV format does not support embedded metadata rows, THE Shortlist_Module SHALL record the Preliminary_Disclaimer and the Analysis_Resolution statement in the accompanying Summary_Report and metadata sidecar so that the disclaimer travels with the tabular output.
5. THE Shortlist_Module SHALL NOT emit any shortlist output that omits both the Preliminary_Disclaimer and the Analysis_Resolution statement.

### Requirement 9: Output metadata with pipeline version and run timestamp

**User Story:** As a data-governance reviewer, I want each shortlist output to record the pipeline version and run timestamp, so that a shortlist can be traced to the run that produced it.

#### Acceptance Criteria

1. WHEN the Shortlist_Module writes a shortlist output, THE Shortlist_Module SHALL record the Pipeline_Version and the Run_Timestamp in UTC in the output metadata.
2. THE Shortlist_Module SHALL record, in the output metadata, the effective Top_N used for the run and the count of cells included in the Shortlist.
3. THE Shortlist_Module SHALL record, in the output metadata, an identifier of the Scored_Table input used, so that the exact scores that produced the shortlist are traceable.
4. THE Shortlist_Module SHALL record the Pipeline_Version and Run_Timestamp identically across the Summary_Report and the output metadata for a single run.

### Requirement 10: Automated pipeline stage under the run() contract

**User Story:** As a pipeline operator, I want the shortlist to run automatically as a registered stage, so that the headline output regenerates as part of the standard pipeline run.

#### Acceptance Criteria

1. THE Shortlist_Module SHALL expose an importable `run(verbose=False, ...) -> dict` entry point whose first parameter is `verbose` defaulting to `False` and whose return value is a dict, matching the entry-point signature used by the other registered pipeline stages.
2. WHEN the Shortlist_Module `run()` completes successfully, THE Shortlist_Module SHALL return a summary dict containing a key for the Shortlist_CSV path, a key for the Shortlist_GeoJSON path, and a key for the Summary_Report path, and each value SHALL be a non-empty filesystem path that exists on disk after the call returns.
3. IF the Shortlist_Module `run()` cannot produce the shortlist outputs or the Summary_Report, THEN THE Shortlist_Module SHALL raise an error indicating the failure cause and SHALL NOT return a summary dict, so that the Pipeline_Orchestrator halts the run with a non-zero exit status.
4. THE Shortlist_Module stage SHALL be registered in the `STAGES` list in `pipeline/config.py` at a position later than the `scoring` stage, so that the scoring producer is scheduled before this consumer.
5. THE Pipeline_Orchestrator SHALL dispatch the Shortlist_Module stage by returning its `run()` function from `_get_runner` and SHALL supply its keyword arguments from `_build_kwargs` in `pipeline/__main__.py`, including the `verbose` flag and the Top_N value.
6. THE shortlist subpackage `__init__.py` docstring SHALL describe the shortlist stage and its position in the pipeline stage sequence.
7. WHERE the shortlist stage introduces a new domain, THE `DOMAINS` list in `pipeline/config.py` SHALL be updated to include the shortlist domain.
8. WHEN the Pipeline_Orchestrator resolves the stages to run, THE resolved execution order SHALL place the Shortlist_Module stage after the `scoring` stage for every invocation that includes both stages, so that every producer runs before its consumers.

### Requirement 11: Provenance for the generated shortlist outputs

**User Story:** As a data-governance reviewer, I want the generated shortlist outputs to carry provenance, so that their origin and derivation are traceable.

#### Acceptance Criteria

1. WHEN the Shortlist_Module writes the shortlist outputs, THE Shortlist_Module SHALL record a Provenance_Record entry for each generated output identifying it as a derived product, listing the Scored_Table and Analysis_Grid inputs, the effective Top_N, and the Run_Timestamp in UTC.
2. THE Shortlist_Module SHALL label the shortlist outputs as derived products in their provenance so that they are not mistaken for custodial source data.
3. THE Shortlist_Module SHALL add a `DATA_PROVENANCE.md` row and a `source_register` entry for the shortlist outputs consistent with the pipeline's provenance convention.
4. WHERE the Shortlist_Module generates the Summary_Report, THE Shortlist_Module SHALL write it using an atomic write and SHALL stamp it with the do-not-edit banner used by other generated pipeline reports.

### Requirement 12: Validation coverage under the no-silent-passes rule

**User Story:** As a quality reviewer, I want the shortlist output validated with explicit pass/fail reporting, so that silent shortlist problems are caught.

#### Acceptance Criteria

1. THE Shortlist_Module validation SHALL confirm that the Shortlist contains no more than the effective Top_N rows and SHALL report the effective Top_N, the observed row count, and an explicit pass or fail result.
2. THE Shortlist_Module validation SHALL confirm that every shortlisted cell is an Eligible_Cell with a non-null `suitability_score` and a non-null `rank`, and SHALL report the count of violating cells and an explicit pass or fail result.
3. THE Shortlist_Module validation SHALL confirm that the Shortlist is ordered by ascending `rank` consistent with the S1-10 ordering, and SHALL report the count of ordering violations and an explicit pass or fail result.
4. THE Shortlist_Module validation SHALL confirm that every shortlisted cell has a non-null `centroid_lat` and `centroid_lon` joined from the Analysis_Grid, and SHALL report the count of missing coordinates and an explicit pass or fail result.
5. THE Shortlist_Module validation SHALL confirm that the Shortlist_CSV and Shortlist_GeoJSON contain the same set of shortlisted `cell_id` values in the same order, and SHALL report the result as an explicit pass or fail.
6. THE Shortlist_Module validation SHALL confirm that each shortlist output and its metadata carry the Preliminary_Disclaimer and the Analysis_Resolution statement, and SHALL report the result as an explicit pass or fail.
7. WHERE cross-domain validation is required, THE cross-domain checks SHALL be placed in `pipeline/validate.py` consistent with the pipeline's validation-tier convention.

### Requirement 13: Unit tests for selection, formatting, and summary logic

**User Story:** As a developer, I want the selection, formatting, and summary logic covered by unit tests, so that the shortlist stays correct as the code evolves.

#### Acceptance Criteria

1. THE unit tests SHALL cover top-N selection using a small synthetic Scored_Table, asserting that the selected cells are the Top_N Eligible_Cells in ascending `rank` order and that Excluded_Cells are omitted.
2. THE unit tests SHALL cover the Top_N-exceeds-eligible-count edge case, asserting that the Shortlist includes every Eligible_Cell without padding when Top_N exceeds the eligible count.
3. THE unit tests SHALL cover the zero-eligible-cells edge case, asserting that an empty Shortlist is produced with headers and the Preliminary_Disclaimer rather than raising an unhandled error.
4. THE unit tests SHALL cover the coordinate join, asserting that `centroid_lat` and `centroid_lon` are joined from the Analysis_Grid on `cell_id` for every shortlisted cell.
5. THE unit tests SHALL cover the output schema and column order, asserting that the Shortlist contains the documented columns from Requirement 4 in the documented order.
6. THE unit tests SHALL cover the Summary_Statistics, asserting that the score distribution (minimum, maximum, mean, standard deviation), the geographic spread, and the confidence distribution equal hand-computed expected values within a documented numeric tolerance for the synthetic input.
7. THE unit tests SHALL assert that the Shortlist_CSV and Shortlist_GeoJSON contain the same shortlisted `cell_id` values in the same order for the synthetic input.

### Requirement 14: Documentation updates

**User Story:** As a project maintainer, I want the data specification and README kept consistent with this new stage and output, so that documentation matches behaviour.

#### Acceptance Criteria

1. WHEN the Shortlist_Module stage and shortlist outputs are added, THE data specification SHALL be updated in section 4 (dataset detail) and section 7 (dataset-to-stage-to-criterion mapping) so that both sections name the shortlist outputs and their columns and reference the Shortlist_Module stage that produces them.
2. WHEN the Shortlist_Module stage is added, THE README stage-order table and CLI documentation SHALL be updated to list the new stage at the same execution position that the pipeline stage configuration resolves at runtime, including the Top_N CLI flag.
3. IF the README stage-order position or stage name for the Shortlist_Module stage does not match the resolved runtime stage configuration, THEN THE documentation SHALL be treated as failing validation and SHALL be corrected to match the runtime configuration before the stage is considered documented.
4. THE documentation SHALL state that the shortlist is a preliminary screening output at the stated Analysis_Resolution and is not a site approval, so that the constraint is explicit in the project documentation.
5. WHERE a frozen decision (Q1-Q7) is affected by this feature, THE change SHALL follow the specification section 8 change-control process AND SHALL be recorded identically in both the data specification section 2 and the README.
