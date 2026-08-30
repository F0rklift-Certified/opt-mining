# Requirements Document

## Introduction

This feature implements Sprint 1 task S1-06 ("Build Geographic and Environmental Features") for the Opt-Mining geospatial pipeline. It adds a new geographic **feature-builder** pipeline stage that converts the Sprint 0 geographic and environmental investigation (elevation, slope, terrain ruggedness, land use, protected areas) into **per-cell features** on the common analysis grid.

For every analysis cell in the common grid, the stage derives terrain variables (elevation, slope, terrain ruggedness), a dominant land-use class, and a protected-area constraint (boolean flag plus overlapping area names), together with a per-cell confidence flag. The resulting per-cell feature table feeds two downstream consumers: the multi-criteria suitability scoring model (S1-07) and the exclusion layer (S1-08). It is blocked by the common analysis grid (S1-01, S1-02).

The stage must satisfy the pipeline's established contracts: the uniform `run(verbose=False, ...) -> dict` stage contract, strict keying to the grid's `cell_id`, explicit and logged CRS handling (EPSG:4326 storage / EPSG:3577 computation), atomic writes with a do-not-edit banner on generated reports, the project file-naming convention, and the "no silent passes" validation rule. Because the source rasters currently cover only the New England REZ (not all of NSW) and the terrain ruggedness raster covers only the tiny Glen-Innes sub-window, the stage must explicitly define how cells outside raster coverage are handled rather than silently producing gaps.

This document specifies **requirements only**. Design and tasks are deliberately out of scope here.

## Glossary

- **Feature_Builder**: The new geographic feature-builder pipeline stage specified by this document. It reads the common analysis grid plus the geographic/environmental source datasets and produces one row of features per analysis cell.
- **Pipeline_Orchestrator**: The pipeline CLI/orchestrator (`pipeline/__main__.py`) that resolves the stage list from `pipeline/config.py` and dispatches each stage's `run()` entry point.
- **Analysis_Grid**: The common analysis cell grid produced by S1-01/S1-02, stored at `DATA/grid/nsw_analysis_grid.gpkg`, with columns `cell_id`, `geometry`, `centroid_lat`, `centroid_lon`, `area_km2`. Cell size is 0.05 degree (~5 km); the full NSW grid contains 47,311 cells.
- **cell_id**: The unique identifier of an Analysis_Grid cell. Every feature layer in the pipeline joins to the grid via `cell_id`. Feature_Builder MUST reuse the grid's exact `cell_id` values and MUST NOT re-derive the grid.
- **Zonal_Statistics**: The operation of summarising raster pixel values that fall within a cell polygon into a single representative value per cell (for example mean, median, max, or mode), together with a count of valid versus NoData pixels.
- **Elevation_Raster**: The SRTM elevation raster(s), e.g. `DATA/geographic/elevation/srtm-gl3_elevation_90m_new-england-rez.tif`.
- **Slope_Raster**: The derived Horn slope raster (degrees), `DATA/geographic/elevation/srtm-gl3_slope-horn_90m_new-england-rez.tif`, produced by the existing `geographic.derive` stage.
- **TRI**: Terrain Ruggedness Index (Riley), a measure of local terrain variability in metres. The derived raster is `DATA/geographic/elevation/srtm-gl1_tri_30m_glen-innes.tif`, which covers only the Glen-Innes sub-window at 30 m.
- **NLUM**: ABARES National Land Use of Australia raster (`DATA/geographic/landuse/abares_nlum-alumv8_2020-21_new-england-rez.tif`), a categorical raster whose integer codes map to ALUM land-use classes.
- **ALUM**: Australian Land Use and Management Classification. The class lookup table is `DATA/geographic/landuse/abares_alumv8_class_table.csv`, mapping NLUM integer codes to human-readable land-use class names.
- **CAPAD**: Collaborative Australian Protected Areas Database. The terrestrial protected-areas vector layer is `DATA/geographic/protected/dcceew_capad-terrestrial_2024_nsw.geojson`.
- **NoData**: Raster pixels that carry no valid measurement (masked, void, or set to the raster's declared nodata value). Excluded from statistics and counted separately.
- **Confidence_Flag**: A per-cell quality indicator. A cell is flagged low confidence when more than 50% of the pixels overlapping the cell are NoData, or when the cell lies outside the coverage of a required source raster.
- **EPSG:4326**: WGS84 geographic coordinate reference system, the pipeline's storage CRS.
- **EPSG:3577**: GDA94 Australian Albers Equal Area coordinate reference system, the pipeline's computation CRS for distance and area.
- **Feature_Table**: The per-cell output table produced by Feature_Builder, one row per `cell_id`, containing the terrain, land-use, protected-area, TRI, and confidence columns.

## Requirements

### Requirement 1: Per-cell terrain feature derivation

**User Story:** As a suitability-model developer, I want representative terrain values for every analysis cell, so that terrain-driven construction cost and exclusion rules can be evaluated per cell.

#### Acceptance Criteria

1. WHEN the Feature_Builder runs, THE Feature_Builder SHALL derive one `elevation_m` value in metres per cell from the Elevation_Raster using Zonal_Statistics over that cell's valid (non-NoData) pixels.
2. WHEN the Feature_Builder runs, THE Feature_Builder SHALL derive one `slope_deg` value in degrees per cell from the Slope_Raster using Zonal_Statistics over that cell's valid pixels.
3. WHEN the Feature_Builder runs, THE Feature_Builder SHALL derive one `tri` value in metres per cell from the TRI raster using Zonal_Statistics over that cell's valid pixels.
4. THE Feature_Builder SHALL apply one documented aggregation statistic per terrain variable (`elevation_m`, `slope_deg`, `tri`) and SHALL record the chosen statistic for each variable in the generated method report.
5. THE Feature_Builder SHALL apply the documented partial-cell boundary rule identically when selecting pixels for each terrain variable.
6. IF a cell has no valid (non-NoData) pixels for a given terrain variable, THEN THE Feature_Builder SHALL record a null value for that variable and SHALL set the cell's Confidence_Flag to low.

### Requirement 2: Documented zonal-statistics method

**User Story:** As a pipeline reviewer, I want the zonal-statistics method documented and consistent, so that per-cell values are reproducible and defensible.

#### Acceptance Criteria

1. THE Feature_Builder SHALL clip each source raster to each cell polygon before computing that cell's statistic, using a single deterministic pixel-inclusion basis that produces identical pixel sets on repeated runs for the same raster and cell.
2. THE Feature_Builder SHALL count, per cell and per raster, the number of valid pixels (pixels within the clipped selection that are not NoData) and the number of NoData pixels, such that valid pixels plus NoData pixels equals the total number of pixels in the clipped selection.
3. THE Feature_Builder SHALL exclude NoData pixels from every computed statistic.
4. THE Feature_Builder SHALL apply one deterministic boundary rule for partial cells (pixels partially overlapping a cell edge) that is identical across all raster inputs, produces the same per-cell pixel selection on repeated runs, and SHALL record that rule verbatim in the method report.
5. THE Feature_Builder SHALL generate a method report that states, for each raster variable, the aggregation statistic used, the partial-cell boundary rule, the NoData handling rule, and the per-cell valid-pixel and NoData-pixel counts.
6. IF a cell has zero valid pixels for a given raster, THEN THE Feature_Builder SHALL assign that cell a NoData value for that raster's statistic, SHALL record the zero-valid-pixel occurrence in the method report, and SHALL NOT compute a numeric statistic from NoData pixels.
7. WHERE the method report is generated, THE Feature_Builder SHALL write it using an atomic write and SHALL stamp it with the do-not-edit banner used by other generated pipeline reports.

### Requirement 3: Dominant land-use class extraction

**User Story:** As a suitability-model developer, I want the dominant land-use class per cell, so that land use can inform siting suitability and exclusions.

#### Acceptance Criteria

1. WHEN the Feature_Builder runs, THE Feature_Builder SHALL derive one dominant land-use code per cell from the NLUM raster using the mode (most frequent class) over that cell's valid (non-NoData) pixels.
2. IF two or more land-use codes tie for the highest frequency within a cell, THEN THE Feature_Builder SHALL select the dominant code using one documented deterministic tie-break rule that yields the same result on repeated runs.
3. THE Feature_Builder SHALL map each dominant land-use code to its human-readable class name using the ALUM class table and SHALL populate the `land_use` output column with the mapped class name.
4. IF a dominant land-use code is absent from the ALUM class table, THEN THE Feature_Builder SHALL record the raw code with an explicit unmapped marker in `land_use` and SHALL report the unmapped code in the method report.
5. IF a cell has no valid (non-NoData) NLUM pixels, THEN THE Feature_Builder SHALL record a null `land_use` value and SHALL set the cell's Confidence_Flag to low.

### Requirement 4: Protected-area overlap constraint

**User Story:** As an exclusion-layer developer, I want to know which cells overlap protected areas and their names, so that protected land can be excluded from siting.

#### Acceptance Criteria

1. IF a cell's geometry spatially intersects (shared interior area or shared boundary) one or more CAPAD protected-area features, THEN THE Feature_Builder SHALL set `protected_area` to true.
2. IF a cell's geometry does not intersect any CAPAD protected-area feature, THEN THE Feature_Builder SHALL set `protected_area` to false.
3. IF a cell intersects one or more CAPAD protected-area features, THEN THE Feature_Builder SHALL record the distinct name(s) of the overlapping protected area(s) in `protected_area_name`, with multiple names joined by a single consistent delimiter and duplicate names collapsed to one entry.
4. IF a cell has no protected-area overlap, THEN THE Feature_Builder SHALL record an empty (zero-length) `protected_area_name` value.
5. IF a cell intersects a CAPAD protected-area feature whose name attribute is missing or null, THEN THE Feature_Builder SHALL set `protected_area` to true and SHALL record a placeholder value indicating an unnamed protected area for that feature in `protected_area_name`.
6. WHEN the Feature_Builder runs, THE Feature_Builder SHALL perform the protected-area intersection in EPSG:3577 and SHALL log the CRS used for the intersection.
7. IF the CAPAD protected-area source data is unavailable or cannot be read, THEN THE Feature_Builder SHALL halt the protected-area computation without writing `protected_area` or `protected_area_name` values and SHALL return an error indication identifying the missing or unreadable CAPAD source.

### Requirement 5: Per-cell confidence flag

**User Story:** As a downstream consumer, I want cells with poor data coverage flagged, so that I can weight or exclude low-quality feature values.

#### Acceptance Criteria

1. IF 50% or more of the pixels overlapping a cell are NoData for any one required source raster, where pixels lying partially or wholly outside that raster's coverage extent are counted as NoData, THEN THE Feature_Builder SHALL set that cell's Confidence_Flag to low.
2. IF a cell lies entirely outside the coverage extent of any one required source raster, THEN THE Feature_Builder SHALL set that cell's Confidence_Flag to low.
3. WHEN a cell has more than 50% valid (non-NoData) pixels for every required source raster and lies within the coverage extent of every required source raster, THE Feature_Builder SHALL set that cell's Confidence_Flag to high.
4. THE Feature_Builder SHALL set every cell's Confidence_Flag to exactly one of the two values low or high, and SHALL set no other value.
5. THE Feature_Builder SHALL record the Confidence_Flag as the `confidence_flag` column value for every cell.
6. THE Feature_Builder SHALL report the count of low-confidence cells and the count of high-confidence cells in the method report.

### Requirement 6: Cells outside current raster coverage

**User Story:** As a pipeline maintainer, I want cells outside the current New England REZ raster coverage handled explicitly, so that the full NSW grid produces a complete, honest output despite partial source coverage.

#### Acceptance Criteria

1. THE Feature_Builder SHALL produce exactly one Feature_Table row for every `cell_id` present in the Analysis_Grid, such that the Feature_Table row count equals the Analysis_Grid `cell_id` count and every `cell_id` appears exactly once (no missing and no duplicate `cell_id`), including cells outside the current source-raster coverage.
2. IF a cell's centroid lies outside the coverage extent of a source raster, THEN THE Feature_Builder SHALL classify that cell as outside coverage for that raster and record a null value for each variable derived from that raster.
3. IF a cell's centroid lies inside the coverage extent of a source raster but the cell overlaps the raster edge such that one or more sample points fall outside valid raster data, THEN THE Feature_Builder SHALL record a null value for each affected variable derived from that raster and classify the cell as outside coverage for that raster.
4. WHERE cells lie outside source-raster coverage, THE Feature_Builder SHALL set those cells' Confidence_Flag to low per Requirement 5.
5. THE Feature_Builder SHALL report, in the method report, the count of cells inside and the count of cells outside the coverage extent of each source raster, such that for each source raster the inside count plus the outside count equals the total Analysis_Grid `cell_id` count and both counts are non-negative integers.
6. THE Feature_Builder SHALL document the current coverage gap (New England REZ raster extent and Glen-Innes-only TRI extent versus the full NSW grid) in the method report and in the data specification.

### Requirement 7: Per-cell output table schema, naming, and format

**User Story:** As a downstream consumer, I want a stable, well-named per-cell feature table, so that the suitability model and exclusion layer can join it reliably to the grid.

#### Acceptance Criteria

1. THE Feature_Builder SHALL write a Feature_Table containing exactly the columns `cell_id`, `elevation_m`, `slope_deg`, `land_use`, `protected_area`, `protected_area_name`, `tri`, and `confidence_flag`.
2. THE Feature_Builder SHALL emit exactly one Feature_Table row per Analysis_Grid `cell_id`, with no missing and no duplicate `cell_id`, joinable to the Analysis_Grid on `cell_id`.
3. THE Feature_Builder SHALL store any geometry in the Feature_Table in EPSG:4326.
4. THE Feature_Builder SHALL name the output file following the `{source}_{dataset}_{year/vintage}_{region}.{ext}` convention using one of the approved region slugs (`national`, `nsw`, `new-england-rez`, or `glen-innes`).
5. THE Feature_Builder SHALL write the Feature_Table using an atomic write (temporary file plus `os.replace`) via the shared `common/geo` helpers.
6. IF the Feature_Table write fails, THEN THE Feature_Builder SHALL leave any previously existing Feature_Table output unmodified and SHALL return an error indication.
7. THE Feature_Builder SHALL produce the Feature_Table as a fully regenerable derived product reproducible from the source datasets and the grid without manual editing.

### Requirement 8: Strict keying to the grid cell_id

**User Story:** As a pipeline architect, I want features keyed strictly to the existing grid cells, so that all feature layers join consistently on `cell_id`.

#### Acceptance Criteria

1. WHEN the Feature_Builder starts, THE Feature_Builder SHALL read the `cell_id` values and cell geometries from the existing Analysis_Grid file (`DATA/grid/nsw_analysis_grid.gpkg`).
2. THE Feature_Builder SHALL reuse the Analysis_Grid `cell_id` values byte-for-byte without modification and SHALL NOT re-derive, renumber, reformat, or reorder the grid `cell_id` values.
3. THE set of `cell_id` values in the Feature_Table SHALL contain every `cell_id` present in the Analysis_Grid, with no `cell_id` present in the Feature_Table that is absent from the Analysis_Grid, and no `cell_id` value appearing more than once in the Feature_Table.
4. IF the Analysis_Grid file is missing or cannot be opened, THEN THE Feature_Builder SHALL halt before writing any Feature_Table output and SHALL report an error indicating the missing or unreadable grid input path.
5. IF the Analysis_Grid file is readable but does not contain a `cell_id` column, THEN THE Feature_Builder SHALL halt before writing any Feature_Table output and SHALL report an error indicating the absent `cell_id` column.
6. IF the Analysis_Grid contains duplicate `cell_id` values, THEN THE Feature_Builder SHALL halt before writing any Feature_Table output and SHALL report an error indicating the duplicated `cell_id` values.

### Requirement 9: Explicit and logged CRS handling

**User Story:** As a geospatial reviewer, I want every CRS boundary made explicit and logged, so that no silent coordinate mismatch corrupts the features.

#### Acceptance Criteria

1. THE Feature_Builder SHALL store the Feature_Table in EPSG:4326.
2. WHEN the Feature_Builder performs a distance or area computation, THE Feature_Builder SHALL perform that computation in EPSG:3577 and SHALL NOT derive distance or area from EPSG:4326 coordinates.
3. WHEN the Feature_Builder reads a source raster or vector whose declared CRS differs from the CRS required for an operation, THE Feature_Builder SHALL reproject explicitly at that read boundary before the operation and SHALL record, for that reprojection, the source dataset identifier, source CRS, target CRS, and the operation performed.
4. IF a source raster or vector has no declared CRS or a CRS that cannot be resolved to an EPSG code, THEN THE Feature_Builder SHALL halt the run without producing the Feature_Table and SHALL emit an error indication identifying the affected source, rather than assuming or defaulting a CRS.
5. WHEN a run completes, THE Feature_Builder SHALL record in the method report one entry for every CRS transformation applied during that run, each entry stating the source dataset identifier, source CRS, target CRS, and operation, such that a reviewer can reconcile every transformation entry against the reprojection events reported under criterion 3.

### Requirement 10: Automated pipeline stage under the run() contract

**User Story:** As a pipeline operator, I want the feature builder to run automatically as a registered stage, so that features regenerate as part of the standard pipeline run.

#### Acceptance Criteria

1. THE Feature_Builder SHALL expose an importable `run(verbose=False, ...) -> dict` entry point whose first parameter is `verbose` defaulting to `False` and whose return value is a dict, matching the entry-point signature used by the other registered pipeline stages.
2. WHEN the Feature_Builder `run()` completes successfully, THE Feature_Builder SHALL return a summary dict containing a key for the output Feature_Table path and a key for the method report path, and both values SHALL be non-empty filesystem paths that exist on disk after the call returns.
3. IF the Feature_Builder `run()` cannot produce the output Feature_Table or the method report, THEN THE Feature_Builder SHALL raise an error indicating the failure cause and SHALL NOT return a summary dict, so that the Pipeline_Orchestrator halts the run with a non-zero exit status.
4. THE Feature_Builder stage SHALL be registered in the `STAGES` list in `pipeline/config.py` at a position later than the `grid` stage, so that the grid producer is scheduled before this consumer.
5. THE Pipeline_Orchestrator SHALL dispatch the Feature_Builder stage by returning its `run()` function from `_get_runner` and SHALL supply its keyword arguments from `_build_kwargs` in `pipeline/__main__.py`, including the `verbose` flag.
6. THE geographic subpackage `__init__.py` docstring SHALL list the Feature_Builder stage within the geographic stage sequence.
7. WHEN the Pipeline_Orchestrator resolves the stages to run, THE resolved execution order SHALL place the Feature_Builder stage after the `grid` stage for every invocation that includes both stages, so that every producer runs before its consumers.

### Requirement 11: Validation coverage under the no-silent-passes rule

**User Story:** As a quality reviewer, I want the feature output validated with explicit pass/fail reporting, so that silent data problems are caught.

#### Acceptance Criteria

1. THE Feature_Builder validation SHALL confirm that the Feature_Table contains exactly one row per Analysis_Grid `cell_id` and SHALL report the expected cell count, the observed row count, and an explicit pass or fail result.
2. THE Feature_Builder validation SHALL confirm that every Analysis_Grid `cell_id` is present in the Feature_Table with no missing and no extra `cell_id`, and SHALL report the counts and an explicit pass or fail result.
3. THE Feature_Builder validation SHALL confirm that the Feature_Table columns exactly match the required schema from Requirement 7 and SHALL report the expected columns, the observed columns, and an explicit pass or fail result.
4. THE Feature_Builder validation SHALL confirm that `slope_deg` values fall within the documented plausible range of 0 to 90 degrees and SHALL report the count of out-of-range cells and an explicit pass or fail result.
5. THE Feature_Builder validation SHALL confirm that `confidence_flag` contains only the defined values high or low and SHALL report any other value as a fail result, otherwise a pass result.

### Requirement 12: Unit tests for zonal-statistics logic

**User Story:** As a developer, I want the zonal-statistics logic covered by unit tests, so that per-cell aggregation stays correct as the code evolves.

#### Acceptance Criteria

1. THE unit tests SHALL cover the terrain aggregation statistic using a small synthetic raster and cell polygon, asserting the computed value equals a hand-computed expected value within a documented numeric tolerance.
2. THE unit tests SHALL cover the categorical mode statistic for land-use extraction using a synthetic categorical raster with a known dominant class, including one case exercising the documented tie-break rule.
3. THE unit tests SHALL cover NoData handling by asserting that NoData pixels are excluded from the computed statistic and are counted separately from valid pixels.
4. THE unit tests SHALL cover the confidence-flag threshold by asserting that a cell with more than 50% NoData pixels is flagged low, a cell exactly at 50% NoData is flagged low, and a cell with more than 50% valid pixels is flagged high.
5. THE unit tests SHALL cover the all-NoData / zero-valid-pixel cell by asserting a null statistic value and a low Confidence_Flag.
6. THE unit tests SHALL cover the protected-area overlap logic by asserting a cell that intersects a protected-area polygon is flagged true and a non-intersecting cell is flagged false.

### Requirement 13: Documented full-NSW-grid runtime performance

**User Story:** As a pipeline operator, I want the full-grid runtime documented, so that I can plan pipeline runs across all 47,311 NSW cells.

#### Acceptance Criteria

1. WHEN the Feature_Builder runs over the full NSW Analysis_Grid of all 47,311 cells, THE Feature_Builder SHALL process every cell and complete without any manual intervention or interactive prompt.
2. WHEN a full-NSW-grid run completes, THE Feature_Builder SHALL record the total wall-clock runtime in seconds and report it in the method report together with the number of cells processed.
3. WHEN a full-NSW-grid run completes, THE Feature_Builder `run()` summary dict SHALL include the total stage runtime in seconds, and this value SHALL equal the runtime reported in the method report and match the orchestrator's per-stage timing for the same run within 1 second.
4. IF a full-NSW-grid run fails to process any cell before completion, THEN THE Feature_Builder SHALL halt without reporting a successful runtime and SHALL return an error indication identifying that the full-grid run did not complete.

### Requirement 14: Documentation updates

**User Story:** As a project maintainer, I want the data specification and README kept consistent with this new stage and output, so that documentation matches behaviour.

#### Acceptance Criteria

1. WHEN the Feature_Builder stage and Feature_Table are added, THE data specification SHALL be updated in section 4 (dataset detail) and section 7 (dataset-to-stage-to-criterion mapping) so that both sections name the Feature_Table output and its per-cell columns (including the Confidence_Flag and TRI columns) and reference the Feature_Builder stage that produces it.
2. WHEN the Feature_Builder stage is added, THE README stage-order table and CLI documentation SHALL be updated to list the new stage at the same execution position that the pipeline stage configuration resolves at runtime.
3. IF the README stage-order position or stage name for the Feature_Builder stage does not match the resolved runtime stage configuration, THEN THE documentation SHALL be treated as failing validation and SHALL be corrected to match the runtime configuration before the stage is considered documented.
4. WHERE a frozen decision (Q1-Q7) is affected by this feature, THE change SHALL follow the specification section 8 change-control process AND SHALL be recorded identically in both the data specification section 2 and the README.
5. THE documentation SHALL describe the current source-raster coverage extents (New England REZ extent for slope-derived layers and Glen-Innes-only extent for TRI), the analysis cells that fall outside those extents, and the Confidence_Flag value that the Feature_Builder assigns to such out-of-coverage cells.
