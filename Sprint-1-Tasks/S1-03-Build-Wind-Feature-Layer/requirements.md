# Requirements Document

## Introduction

This feature implements Sprint 1 task S1-03 ("Build the Wind Feature Layer") for the Opt-Mining geospatial pipeline. It adds a new wind **feature-builder** pipeline stage that converts the Sprint 0 Global Wind Atlas (GWA) investigation — clipped wind-speed, power-density, and capacity-factor rasters — into a **per-cell wind feature** on the common analysis grid.

For every valid analysis cell in the common grid, the stage derives one representative wind-resource value (plus its units, data source, and a per-cell confidence flag) by aggregating the native GWA raster pixels that fall within that cell. The S1-02 decision selected **Option A** (0.05° GWA-aligned geographic cells, EPSG:4326), so each analysis cell is exactly 20×20 native GWA pixels and the operation is a clean block extraction with no reprojection or interpolation of the GWA rasters. The resulting per-cell feature table feeds the integrated NSW feature table (S1-08) and, through it, the multi-criteria suitability scoring model (S1-07). It is blocked by the common analysis grid (S1-01, S1-02).

Two project-constitution rules constrain this feature. First, "Never invent, extrapolate or hard-code data values to make a pipeline run": cells with no valid GWA coverage MUST be flagged, never back-filled with defaults or fabricated values. Second, "Never build a circular model": the wind data is an input feature and MUST NOT be derived from, or fitted to, any suitability score or prediction target.

The stage must satisfy the pipeline's established contracts: the uniform `run(verbose=False, ...) -> dict` stage contract, registration in `pipeline/config.py` and dispatch in `pipeline/__main__.py`, strict keying to the grid's `cell_id`, explicit and logged CRS handling (EPSG:4326 storage / EPSG:3577 computation), the project file-naming convention, atomic writes with a do-not-edit banner on generated reports, full provenance for any new output (download manifest, `DATA_PROVENANCE.md`, source register), and the "no silent passes" validation rule.

This document specifies **requirements only**. Design and tasks are deliberately out of scope here.

## Glossary

- **Wind_Feature_Builder**: The new wind feature-builder pipeline stage specified by this document. It reads the common analysis grid plus the clipped GWA source rasters and produces one row of wind features per analysis cell.
- **Pipeline_Orchestrator**: The pipeline CLI/orchestrator (`pipeline/__main__.py`) that resolves the stage list from `pipeline/config.py` and dispatches each stage's `run()` entry point.
- **Analysis_Grid**: The common analysis cell grid produced by S1-01/S1-02, stored at `DATA/grid/nsw_analysis_grid.gpkg`, with columns `cell_id`, `geometry`, `centroid_lat`, `centroid_lon`, `area_km2`. Cell size is 0.05 degree (~5 km); each cell is exactly 20×20 native GWA pixels (Option A). The full NSW grid contains 47,311 cells.
- **cell_id**: The unique identifier of an Analysis_Grid cell. Every feature layer in the pipeline joins to the grid via `cell_id`. Wind_Feature_Builder MUST reuse the grid's exact `cell_id` values and MUST NOT re-derive the grid.
- **GWA**: Global Wind Atlas v4 (DTU), the modelled wind resource dataset, licensed CC BY 4.0. Native pixel size is 0.0025 degree (~250 m).
- **GWA_Raster**: A clipped GWA raster produced by the Sprint 0 `wind.download` stage, e.g. `DATA/wind-resource/gwa_v4_wind-speed_100m_new-england-rez.tif`. Stored in EPSG:4326.
- **Wind_Variable**: The selected MVP wind-resource variable that the Wind_Feature_Builder derives per cell (for example mean wind speed at 100 m in m/s). Exactly one Wind_Variable is chosen and documented.
- **Zonal_Statistics**: The operation of summarising the GWA raster pixel values that fall within a cell polygon into a single representative value per cell, together with a count of valid versus NoData pixels. Under Option A this is a 20×20 native-pixel block per cell.
- **Aggregation_Statistic**: The single documented statistic (for example mean) applied to a cell's valid GWA pixels to produce the cell's Wind_Variable value.
- **NoData**: GWA raster pixels that carry no valid measurement (masked, void, or set to the raster's declared nodata value). Excluded from statistics and counted separately.
- **Confidence_Flag**: A per-cell quality indicator recorded in the `confidence_flag` output column. Its allowed values and the rule assigning them are defined in Requirement 5.
- **EPSG:4326**: WGS84 geographic coordinate reference system, the pipeline's storage CRS.
- **EPSG:3577**: GDA94 Australian Albers Equal Area coordinate reference system, the pipeline's computation CRS for distance and area.
- **Feature_Table**: The per-cell output table produced by Wind_Feature_Builder, one row per `cell_id`, containing the wind variable, units, data source, and confidence columns.
- **Method_Report**: The generated Markdown report documenting variable selection, aggregation method, CRS handling, and output statistics for a Wind_Feature_Builder run.

## Requirements

### Requirement 1: MVP wind-resource variable selection and documentation

**User Story:** As a suitability-model developer, I want a single defensible wind-resource variable selected and justified, so that the wind feature is meaningful, reproducible, and comparable across cells.

#### Acceptance Criteria

1. THE Wind_Feature_Builder SHALL derive exactly one Wind_Variable per cell.
2. THE Wind_Feature_Builder SHALL record, in the Method_Report, the selected Wind_Variable, its hub height (where applicable), its units, and the source GWA_Raster filename used to derive it.
3. THE Wind_Feature_Builder SHALL record, in the Method_Report, a written justification for the chosen hub height and the chosen variable.
4. THE Wind_Feature_Builder SHALL derive the Wind_Variable exclusively from GWA_Raster inputs and SHALL NOT derive it from any suitability score, ranking, or prediction target.

### Requirement 2: Per-cell wind feature derivation

**User Story:** As a suitability-model developer, I want a representative wind value for every valid analysis cell, so that wind resource can be scored per cell.

#### Acceptance Criteria

1. WHEN the Wind_Feature_Builder runs, THE Wind_Feature_Builder SHALL derive one Wind_Variable value per cell from the source GWA_Raster using Zonal_Statistics over that cell's valid (non-NoData) pixels.
2. THE Wind_Feature_Builder SHALL apply exactly one Aggregation_Statistic to produce the per-cell Wind_Variable value and SHALL record the chosen Aggregation_Statistic in the Method_Report.
3. THE Wind_Feature_Builder SHALL emit exactly one Feature_Table row per `cell_id` present in the Analysis_Grid.
4. THE Wind_Feature_Builder SHALL reuse each Analysis_Grid `cell_id` value byte-for-byte and SHALL NOT re-derive, renumber, or reorder the grid cells.
5. IF a cell has no valid (non-NoData) GWA pixels, THEN THE Wind_Feature_Builder SHALL record a null Wind_Variable value for that cell and SHALL set that cell's Confidence_Flag to the no-data value defined in Requirement 5.

### Requirement 3: Documented aggregation method

**User Story:** As a pipeline reviewer, I want the aggregation method documented and deterministic, so that per-cell wind values are reproducible and defensible.

#### Acceptance Criteria

1. THE Wind_Feature_Builder SHALL select the GWA pixels for each cell using a single deterministic pixel-inclusion basis that produces identical pixel sets on repeated runs for the same raster and cell.
2. THE Wind_Feature_Builder SHALL count, per cell, the number of valid pixels (pixels within the cell's selection that are not NoData) and the number of NoData pixels, such that valid pixels plus NoData pixels equals the total number of pixels in the cell's selection.
3. THE Wind_Feature_Builder SHALL exclude NoData pixels from the computed Aggregation_Statistic.
4. THE Wind_Feature_Builder SHALL apply one deterministic boundary rule for partial cells (cells whose selection includes pixels partially overlapping a cell edge) that produces the same per-cell pixel selection on repeated runs, and SHALL record that rule verbatim in the Method_Report.
5. THE Wind_Feature_Builder SHALL record, in the Method_Report, the Aggregation_Statistic, the pixel-inclusion basis, the partial-cell boundary rule, and the NoData handling rule.

### Requirement 4: Output schema, naming, and format

**User Story:** As a downstream feature-table integrator (S1-08), I want a well-defined, conventionally named output, so that the wind feature joins cleanly to the integrated NSW feature table.

#### Acceptance Criteria

1. THE Wind_Feature_Builder SHALL produce a Feature_Table containing at least the columns `cell_id`, the Wind_Variable value column, `units`, `data_source`, and `confidence_flag`.
2. THE Wind_Feature_Builder SHALL populate the `units` column with the units of the selected Wind_Variable (for example `m/s` for wind speed or `W/m^2` for power density).
3. THE Wind_Feature_Builder SHALL populate the `data_source` column with an identifier that names the GWA dataset and vintage used (for example `GWA v4`).
4. THE Wind_Feature_Builder SHALL name each output file using the `{source}_{dataset}_{year/vintage}_{region}.{ext}` convention with the region slug `nsw`.
5. THE Wind_Feature_Builder SHALL store any geospatial Feature_Table output in EPSG:4326.
6. WHERE the Feature_Table is written to disk, THE Wind_Feature_Builder SHALL write it using an atomic write (temporary file followed by `os.replace`).

### Requirement 5: Confidence flag for cells without valid data

**User Story:** As a pipeline reviewer, I want cells without valid wind data flagged rather than filled, so that no fabricated values enter the scoring model (per the project constitution).

#### Acceptance Criteria

1. THE Wind_Feature_Builder SHALL populate a `confidence_flag` column for every Feature_Table row using values drawn from a documented, enumerated set.
2. IF a cell has one or more valid GWA pixels, THEN THE Wind_Feature_Builder SHALL assign that cell a confidence value indicating valid data.
3. IF a cell has zero valid GWA pixels or lies outside GWA_Raster coverage, THEN THE Wind_Feature_Builder SHALL assign that cell the no-data confidence value AND SHALL leave the Wind_Variable value null.
4. THE Wind_Feature_Builder SHALL NOT substitute a default, interpolated, extrapolated, or hard-coded numeric value for any cell that has zero valid GWA pixels.
5. THE Wind_Feature_Builder SHALL record, in the Method_Report, the enumerated confidence values and the rule used to assign each.

### Requirement 6: Pipeline integration under the stage contract

**User Story:** As a pipeline operator, I want the wind feature built automatically as a registered stage, so that it runs without manual intervention.

#### Acceptance Criteria

1. THE Wind_Feature_Builder SHALL expose a `run(verbose: bool = False, ...) -> dict` entry point that returns a summary dict of its output paths and run statistics.
2. THE Wind_Feature_Builder SHALL be registered in the `STAGES` list in `pipeline/config.py`.
3. THE Wind_Feature_Builder SHALL be scheduled to run after the `grid` stage, because it consumes the Analysis_Grid.
4. THE Pipeline_Orchestrator SHALL dispatch the Wind_Feature_Builder stage via `pipeline/__main__.py` using the same runner-dispatch and keyword-argument mechanism as other stages.
5. WHEN the full pipeline runs without manual intervention, THE Pipeline_Orchestrator SHALL invoke the Wind_Feature_Builder and produce the Feature_Table.
6. IF the Analysis_Grid file (`DATA/grid/nsw_analysis_grid.gpkg`) is absent when the Wind_Feature_Builder runs, THEN THE Wind_Feature_Builder SHALL raise an explicit error identifying the missing grid input and SHALL NOT produce a partial Feature_Table.

### Requirement 7: Explicit CRS handling

**User Story:** As a pipeline reviewer, I want CRS boundaries made explicit and logged, so that no silent reprojection corrupts the join to the grid.

#### Acceptance Criteria

1. THE Wind_Feature_Builder SHALL treat EPSG:4326 as the storage CRS for the Analysis_Grid, the GWA_Raster inputs, and the Feature_Table output.
2. WHERE the Wind_Feature_Builder performs any distance or area computation, THE Wind_Feature_Builder SHALL perform that computation in EPSG:3577.
3. WHEN the Wind_Feature_Builder reprojects any layer between EPSG:4326 and EPSG:3577, THE Wind_Feature_Builder SHALL log the source and target CRS of that reprojection.
4. IF a GWA_Raster or the Analysis_Grid has a CRS other than EPSG:4326, THEN THE Wind_Feature_Builder SHALL report the mismatch rather than silently reprojecting.

### Requirement 8: Provenance

**User Story:** As a data steward, I want every new output tracked with provenance, so that the wind feature's origin, licence, and vintage are auditable.

#### Acceptance Criteria

1. WHEN the Wind_Feature_Builder writes the Feature_Table, THE Wind_Feature_Builder SHALL record a provenance entry for the output in `DATA/wind-resource/DATA_PROVENANCE.md` identifying the source GWA dataset, the derivation method, and the fact that the output is a derived layer.
2. WHEN the Wind_Feature_Builder writes the Feature_Table, THE Wind_Feature_Builder SHALL record the output in the wind download manifest (`DATA/wind-resource/metadata/download_manifest.json`) with a SHA-256 hash, byte count, and UTC timestamp.
3. THE Wind_Feature_Builder SHALL label the Feature_Table as a derived layer, distinct from custodial GWA source data, and SHALL document that it is regenerable from the GWA_Raster inputs and the Analysis_Grid.

### Requirement 9: Output statistics logging

**User Story:** As a pipeline operator, I want run statistics logged, so that I can confirm coverage and spot anomalies at a glance.

#### Acceptance Criteria

1. WHEN the Wind_Feature_Builder completes a run, THE Wind_Feature_Builder SHALL log the minimum, maximum, and mean of the Wind_Variable across all cells with valid data.
2. WHEN the Wind_Feature_Builder completes a run, THE Wind_Feature_Builder SHALL log the count of cells with valid data and the count of cells flagged as no-data.
3. THE Wind_Feature_Builder SHALL record the statistics from acceptance criteria 1 and 2 in the Method_Report.
4. WHERE the Method_Report is generated, THE Wind_Feature_Builder SHALL write it using an atomic write and SHALL stamp it with the do-not-edit banner used by other generated pipeline reports.

### Requirement 10: Validation with no silent passes

**User Story:** As a pipeline reviewer, I want the wind feature validated with explicit results, so that data-integrity issues fail loudly.

#### Acceptance Criteria

1. THE Wind_Feature_Builder SHALL validate that the Feature_Table contains exactly one row per Analysis_Grid `cell_id`, reporting the expected cell count, the observed row count, and a pass/fail result.
2. THE Wind_Feature_Builder SHALL validate that every non-null Wind_Variable value falls within the plausible range for the selected variable, reporting the expected range, the observed extremes, and a pass/fail result.
3. THE Wind_Feature_Builder SHALL validate that every cell with a no-data Confidence_Flag has a null Wind_Variable value, reporting expected versus observed and a pass/fail result.
4. IF any validation check fails, THEN THE Wind_Feature_Builder SHALL report the failure with its expected value, observed value, and fail status rather than passing silently.

### Requirement 11: Unit tests for aggregation logic

**User Story:** As a maintainer, I want the aggregation logic covered by unit tests, so that regressions in per-cell derivation are caught automatically.

#### Acceptance Criteria

1. THE Wind_Feature_Builder test suite SHALL include a unit test that verifies the Aggregation_Statistic produces the expected per-cell value for a known synthetic raster-and-cell input.
2. THE Wind_Feature_Builder test suite SHALL include a unit test that verifies a cell with all-NoData pixels produces a null Wind_Variable value and the no-data Confidence_Flag.
3. THE Wind_Feature_Builder test suite SHALL include a unit test that verifies NoData pixels are excluded from the computed Aggregation_Statistic.
4. THE Wind_Feature_Builder test suite SHALL include a unit test that verifies the output Feature_Table has exactly one row per input `cell_id`.

### Requirement 12: Documentation

**User Story:** As a project maintainer, I want documentation updated when the wind feature stage is added, so that the pipeline's expected outputs and stage order stay accurate.

#### Acceptance Criteria

1. WHEN the Wind_Feature_Builder stage is added, THE project maintainer SHALL update the README stage-order table and expected-outputs table to include the new stage and its Feature_Table output.
2. WHEN the Wind_Feature_Builder stage is added, THE project maintainer SHALL update the data specification to record the derived wind feature output and its source-to-stage-to-criterion mapping.
