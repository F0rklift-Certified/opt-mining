# Requirements Document

## Introduction

This feature implements Sprint 1 task S1-05 ("Build Infrastructure Features") for the Opt-Mining geospatial pipeline. It adds a new infrastructure **feature-builder** pipeline stage that converts the Sprint 0 electricity-infrastructure investigation (Geoscience Australia transmission lines, GA substations, AEMO connection points, and Renewable Energy Zone boundaries) into **per-cell features** on the common analysis grid.

For every valid analysis cell in the common grid, the stage derives distance-based indicators (distance to the nearest transmission line, substation, and connection point, in kilometres) and categorical indicators (whether the cell lies inside a Renewable Energy Zone and, if so, the zone's name), together with a per-cell confidence flag. The resulting per-cell feature table feeds the integrated NSW feature table (S1-08), which in turn supports the multi-criteria suitability score. Proximity to grid infrastructure is a key driver of wind-farm connection cost, so these features materially affect siting suitability. This stage is blocked by the common analysis grid (S1-01, S1-02) and blocks the integrated feature table (S1-08).

The stage must satisfy the pipeline's established contracts: the uniform `run(verbose=False, ...) -> dict` stage contract, strict keying to the grid's `cell_id`, explicit and logged CRS handling (EPSG:4326 storage / EPSG:3577 computation for all distances), the consistent GA-layer filtering pattern in `pipeline/infrastructure/helpers.py`, atomic writes with a do-not-edit banner on generated reports, the project file-naming convention, provenance capture, and the "no silent passes" validation rule. Because a connection between analysis and honesty is required, the stage MUST record a flag rather than fabricate a value whenever an infrastructure source is missing, unreadable, or empty.

This document specifies **requirements only**. Design and tasks are deliberately out of scope here.

## Glossary

- **Feature_Builder**: The new infrastructure feature-builder pipeline stage specified by this document (a new module under `pipeline/infrastructure/`). It reads the common analysis grid plus the infrastructure source datasets and produces one row of infrastructure features per analysis cell.
- **Pipeline_Orchestrator**: The pipeline CLI/orchestrator (`pipeline/__main__.py`) that resolves the stage list from `pipeline/config.py` and dispatches each stage's `run()` entry point via `_get_runner` and `_build_kwargs`.
- **Analysis_Grid**: The common analysis cell grid produced by S1-01/S1-02, stored at `DATA/grid/nsw_analysis_grid.gpkg`, with columns `cell_id`, `geometry`, `centroid_lat`, `centroid_lon`, `area_km2`. Cell size is 0.05 degree (~5 km); the full NSW grid contains 47,311 cells.
- **cell_id**: The unique identifier of an Analysis_Grid cell. Every feature layer in the pipeline joins to the grid via `cell_id`. Feature_Builder MUST reuse the grid's exact `cell_id` values and MUST NOT re-derive the grid.
- **Cell_Centroid**: The geometric centroid of an Analysis_Grid cell polygon, from which all Feature_Builder distances are measured.
- **Transmission_Lines**: The Geoscience Australia electricity transmission-line vector layer, `DATA/infrastructure/transmission-lines/ga_power_lines_2026_nsw.geojson` (NSW-filtered), with `ga_power_lines_2026_australia.geojson` as the national source.
- **Substations**: The Geoscience Australia substation vector layer, `DATA/infrastructure/substations/ga_substations_2026_nsw.geojson` (NSW-filtered), with `ga_substations_2026_australia.geojson` as the national source.
- **Connection_Points**: The AEMO key connection information (KCI) dataset, `DATA/infrastructure/connection-points/aemo_kci_2026.xlsx`, describing candidate network connection projects/points.
- **REZ**: Renewable Energy Zone. The NSW EnergyCo REZ boundary polygons under `DATA/infrastructure/renewable-energy-zones/energyco-nsw/` (New England, Central-West Orana, Hunter-Central Coast), with `aemo_indicative_rez_boundaries_2026.kmz` as the national/ISP indicative reference.
- **Generators**: The Geoscience Australia power-station and wind-generator layers (`DATA/infrastructure/generators/ga_powerstations_2026_australia.geojson`, `ga_wind_generators_2026_nsw.geojson`), used for context only in this stage.
- **Infra_Helpers**: The shared infrastructure helper module `pipeline/infrastructure/helpers.py`, which provides the GA-layer load and filter functions applied consistently across all three GA layers (transmission lines, substations, generators).
- **Nearest_Feature_Distance**: The shortest planar distance, computed in EPSG:3577, from a Cell_Centroid to the nearest point on the nearest feature geometry in a target layer (for lines, the nearest point on the line, not a line endpoint).
- **Confidence_Flag**: A per-cell quality indicator with exactly two values, high or low. A cell is flagged low when any required infrastructure source used for that cell is missing, unreadable, or empty, so that a distance could not be computed from real data.
- **EPSG:4326**: WGS84 geographic coordinate reference system, the pipeline's storage CRS.
- **EPSG:3577**: GDA94 Australian Albers Equal Area coordinate reference system, the pipeline's computation CRS for distance and area. Degrees are not a unit of length.
- **Feature_Table**: The per-cell output table produced by Feature_Builder, one row per `cell_id`, containing the distance, REZ, and confidence columns defined in Requirement 5.
- **Provenance_Record**: The set of provenance artefacts the pipeline maintains for every data path: the download manifest, the `DATA_PROVENANCE.md` table, and the `source_register` catalogue.

## Requirements

### Requirement 1: Per-cell distance-to-transmission-line feature

**User Story:** As a suitability-model developer, I want the distance from every cell to the nearest transmission line, so that connection cost can be evaluated per cell.

#### Acceptance Criteria

1. WHEN the Feature_Builder runs, THE Feature_Builder SHALL derive one `dist_transmission_km` value in kilometres per cell as the Nearest_Feature_Distance from the Cell_Centroid to the Transmission_Lines layer.
2. THE Feature_Builder SHALL measure `dist_transmission_km` to the nearest point on the nearest transmission-line geometry, not to a line endpoint.
3. THE Feature_Builder SHALL compute `dist_transmission_km` in EPSG:3577 and SHALL NOT derive the distance from EPSG:4326 coordinates.
4. IF the Transmission_Lines source is missing, unreadable, or contains zero features, THEN THE Feature_Builder SHALL record a null `dist_transmission_km` value for every cell and SHALL set each such cell's Confidence_Flag to low, rather than recording a fabricated distance.

### Requirement 2: Per-cell distance-to-substation feature

**User Story:** As a suitability-model developer, I want the distance from every cell to the nearest substation, so that grid-connection proximity can be scored per cell.

#### Acceptance Criteria

1. WHEN the Feature_Builder runs, THE Feature_Builder SHALL derive one `dist_substation_km` value in kilometres per cell as the Nearest_Feature_Distance from the Cell_Centroid to the Substations layer.
2. THE Feature_Builder SHALL compute `dist_substation_km` in EPSG:3577 and SHALL NOT derive the distance from EPSG:4326 coordinates.
3. IF the Substations source is missing, unreadable, or contains zero features, THEN THE Feature_Builder SHALL record a null `dist_substation_km` value for every cell and SHALL set each such cell's Confidence_Flag to low, rather than recording a fabricated distance.

### Requirement 3: Per-cell distance-to-connection-point feature

**User Story:** As a suitability-model developer, I want the distance from every cell to the nearest connection point, so that proximity to network connection opportunities can be scored per cell.

#### Acceptance Criteria

1. WHEN the Feature_Builder runs, THE Feature_Builder SHALL derive one `dist_connection_km` value in kilometres per cell as the Nearest_Feature_Distance from the Cell_Centroid to the Connection_Points layer.
2. THE Feature_Builder SHALL compute `dist_connection_km` in EPSG:3577 and SHALL NOT derive the distance from EPSG:4326 coordinates.
3. WHEN the Feature_Builder reads the Connection_Points source, THE Feature_Builder SHALL resolve each connection point to a geographic location with an explicit source CRS before reprojecting to EPSG:3577.
4. IF a Connection_Points record cannot be resolved to a valid geographic location, THEN THE Feature_Builder SHALL exclude that record from the distance computation and SHALL report the count of excluded records in the method report, rather than assigning it a default location.
5. IF the Connection_Points source is missing, unreadable, or yields zero locatable points, THEN THE Feature_Builder SHALL record a null `dist_connection_km` value for every cell and SHALL set each such cell's Confidence_Flag to low, rather than recording a fabricated distance.

### Requirement 4: Renewable Energy Zone membership features

**User Story:** As an exclusion- and suitability-model developer, I want to know which cells lie inside a Renewable Energy Zone and its name, so that REZ membership can inform siting priority.

#### Acceptance Criteria

1. IF a cell's geometry spatially intersects (shared interior area or shared boundary) one or more REZ boundary polygons, THEN THE Feature_Builder SHALL set `inside_rez` to true.
2. IF a cell's geometry does not intersect any REZ boundary polygon, THEN THE Feature_Builder SHALL set `inside_rez` to false.
3. IF a cell intersects exactly one REZ boundary polygon, THEN THE Feature_Builder SHALL record that zone's name in `rez_name`.
4. IF a cell intersects two or more REZ boundary polygons, THEN THE Feature_Builder SHALL record the distinct name(s) of the overlapping zones in `rez_name`, with multiple names joined by a single consistent delimiter and duplicate names collapsed to one entry.
5. IF a cell has no REZ overlap, THEN THE Feature_Builder SHALL record a null `rez_name` value.
6. IF a cell intersects a REZ boundary polygon whose name attribute is missing or null, THEN THE Feature_Builder SHALL set `inside_rez` to true and SHALL record a placeholder value indicating an unnamed zone for that feature in `rez_name`.
7. WHEN the Feature_Builder performs the REZ intersection, THE Feature_Builder SHALL perform the intersection in one explicit CRS and SHALL log the CRS used for the intersection.
8. IF the REZ boundary source is missing or unreadable, THEN THE Feature_Builder SHALL record a null `inside_rez` value and a null `rez_name` value for every cell and SHALL set each such cell's Confidence_Flag to low, rather than recording a fabricated membership.

### Requirement 5: Per-cell output table schema, naming, and format

**User Story:** As a downstream consumer, I want a stable, well-named per-cell infrastructure feature table, so that the integrated NSW feature table can join it reliably to the grid.

#### Acceptance Criteria

1. THE Feature_Builder SHALL write a Feature_Table containing exactly the columns `cell_id`, `dist_transmission_km`, `dist_substation_km`, `dist_connection_km`, `inside_rez`, `rez_name`, and `confidence_flag`.
2. THE Feature_Builder SHALL emit exactly one Feature_Table row per Analysis_Grid `cell_id`, with no missing and no duplicate `cell_id`, joinable to the Analysis_Grid on `cell_id`.
3. WHERE any additional defensible indicator from the Sprint 0 investigation (for example transmission-line voltage or substation capacity) is included, THE Feature_Builder SHALL add it as a named, documented column and SHALL record its definition and source field in the method report.
4. THE Feature_Builder SHALL store any geometry in the Feature_Table in EPSG:4326.
5. THE Feature_Builder SHALL name the output file following the `{source}_{dataset}_{year/vintage}_{region}.{ext}` convention using the region slug `nsw`.
6. THE Feature_Builder SHALL write the Feature_Table using an atomic write (temporary file plus `os.replace`) via the shared `common/geo` helpers.
7. IF the Feature_Table write fails, THEN THE Feature_Builder SHALL leave any previously existing Feature_Table output unmodified and SHALL return an error indication.
8. THE Feature_Builder SHALL produce the Feature_Table as a fully regenerable derived product reproducible from the source datasets and the grid without manual editing.

### Requirement 6: Missing data produces a flag, not a fabricated value

**User Story:** As a data-quality reviewer, I want cells with missing or unavailable infrastructure inputs flagged rather than filled with invented numbers, so that downstream scoring stays honest.

#### Acceptance Criteria

1. IF an infrastructure distance for a cell cannot be computed from real source data (because the relevant source is missing, unreadable, or empty), THEN THE Feature_Builder SHALL record a null value for that distance column and SHALL NOT record a fabricated, default, or sentinel numeric distance.
2. IF a cell has a null value in any one of `dist_transmission_km`, `dist_substation_km`, `dist_connection_km`, `inside_rez`, or `rez_name` due to missing or unavailable source data, THEN THE Feature_Builder SHALL set that cell's Confidence_Flag to low.
3. WHEN a cell has a computed value for every distance and REZ feature derived from available source data, THE Feature_Builder SHALL set that cell's Confidence_Flag to high.
4. THE Feature_Builder SHALL set every cell's Confidence_Flag to exactly one of the two values low or high, and SHALL set no other value.
5. THE Feature_Builder SHALL report, in the method report, the count of low-confidence cells, the count of high-confidence cells, and the reason category for each low-confidence cell (which source was missing, unreadable, or empty).

### Requirement 7: Consistent GA-layer handling and configuration

**User Story:** As a pipeline maintainer, I want the GA infrastructure layers loaded and filtered consistently, so that transmission lines, substations, and generators are treated the same way without divergent bugs.

#### Acceptance Criteria

1. THE Feature_Builder SHALL load and filter each Geoscience Australia layer (Transmission_Lines, Substations, Generators) through the shared Infra_Helpers functions, applying the same load-and-filter pattern to all three GA layers.
2. WHERE a state filter is applied to a GA layer, THE Feature_Builder SHALL apply the identical state-filter rule (default `NSW`) across every GA layer through Infra_Helpers.
3. THE Feature_Builder SHALL read its input source paths and default filter values from `pipeline/infrastructure/config.py`, and any new source path or default introduced by this stage SHALL be declared in that config module.
4. WHERE the Feature_Builder introduces a configurable input (for example a state filter, a distance-computation CRS override, or an input source selection), THE Pipeline_Orchestrator SHALL expose a corresponding CLI flag in `pipeline/__main__.py` and SHALL pass its value into the stage via `_build_kwargs`.
5. WHERE the Feature_Builder requires input files that are not already listed in the infrastructure `EXPECTED_FILES` set, THE `EXPECTED_FILES` set in `pipeline/infrastructure/config.py` SHALL be updated to include those required inputs.

### Requirement 8: Strict keying to the grid cell_id

**User Story:** As a pipeline architect, I want infrastructure features keyed strictly to the existing grid cells, so that all feature layers join consistently on `cell_id`.

#### Acceptance Criteria

1. WHEN the Feature_Builder starts, THE Feature_Builder SHALL read the `cell_id` values and cell geometries from the existing Analysis_Grid file (`DATA/grid/nsw_analysis_grid.gpkg`).
2. THE Feature_Builder SHALL reuse the Analysis_Grid `cell_id` values byte-for-byte without modification and SHALL NOT re-derive, renumber, reformat, or reorder the grid `cell_id` values.
3. THE set of `cell_id` values in the Feature_Table SHALL contain every `cell_id` present in the Analysis_Grid, with no `cell_id` present in the Feature_Table that is absent from the Analysis_Grid, and no `cell_id` value appearing more than once in the Feature_Table.
4. IF the Analysis_Grid file is missing or cannot be opened, THEN THE Feature_Builder SHALL halt before writing any Feature_Table output and SHALL report an error indicating the missing or unreadable grid input path.
5. IF the Analysis_Grid file is readable but does not contain a `cell_id` column, THEN THE Feature_Builder SHALL halt before writing any Feature_Table output and SHALL report an error indicating the absent `cell_id` column.
6. IF the Analysis_Grid contains duplicate `cell_id` values, THEN THE Feature_Builder SHALL halt before writing any Feature_Table output and SHALL report an error indicating the duplicated `cell_id` values.

### Requirement 9: Explicit and logged CRS handling

**User Story:** As a geospatial reviewer, I want every CRS boundary made explicit and logged, so that no silent coordinate mismatch corrupts the distances.

#### Acceptance Criteria

1. THE Feature_Builder SHALL store the Feature_Table in EPSG:4326.
2. WHEN the Feature_Builder performs any distance computation, THE Feature_Builder SHALL perform that computation in EPSG:3577 and SHALL NOT derive distance from EPSG:4326 coordinates.
3. WHEN the Feature_Builder reads a source vector whose declared CRS differs from the CRS required for an operation, THE Feature_Builder SHALL reproject explicitly at that read boundary before the operation and SHALL record, for that reprojection, the source dataset identifier, source CRS, target CRS, and the operation performed.
4. IF a source vector has no declared CRS or a CRS that cannot be resolved to an EPSG code, THEN THE Feature_Builder SHALL halt the run without producing the Feature_Table and SHALL emit an error indication identifying the affected source, rather than assuming or defaulting a CRS.
5. WHEN a run completes, THE Feature_Builder SHALL record in the method report one entry for every CRS transformation applied during that run, each entry stating the source dataset identifier, source CRS, target CRS, and operation, such that a reviewer can reconcile every transformation entry against the reprojection events reported under criterion 3.

### Requirement 10: Automated pipeline stage under the run() contract

**User Story:** As a pipeline operator, I want the infrastructure feature builder to run automatically as a registered stage, so that infrastructure features regenerate as part of the standard pipeline run.

#### Acceptance Criteria

1. THE Feature_Builder SHALL expose an importable `run(verbose=False, ...) -> dict` entry point whose first parameter is `verbose` defaulting to `False` and whose return value is a dict, matching the entry-point signature used by the other registered pipeline stages.
2. WHEN the Feature_Builder `run()` completes successfully, THE Feature_Builder SHALL return a summary dict containing a key for the output Feature_Table path and a key for the method report path, and both values SHALL be non-empty filesystem paths that exist on disk after the call returns.
3. IF the Feature_Builder `run()` cannot produce the output Feature_Table or the method report, THEN THE Feature_Builder SHALL raise an error indicating the failure cause and SHALL NOT return a summary dict, so that the Pipeline_Orchestrator halts the run with a non-zero exit status.
4. THE Feature_Builder stage SHALL be registered in the `STAGES` list in `pipeline/config.py` at a position later than the `grid` stage, so that the grid producer is scheduled before this consumer.
5. THE Pipeline_Orchestrator SHALL dispatch the Feature_Builder stage by returning its `run()` function from `_get_runner` and SHALL supply its keyword arguments from `_build_kwargs` in `pipeline/__main__.py`, including the `verbose` flag.
6. THE infrastructure subpackage `__init__.py` docstring SHALL list the Feature_Builder stage within the infrastructure stage sequence.
7. WHEN the Pipeline_Orchestrator resolves the stages to run, THE resolved execution order SHALL place the Feature_Builder stage after the `grid` stage for every invocation that includes both stages, so that every producer runs before its consumers.

### Requirement 11: Provenance for the generated feature output

**User Story:** As a data-governance reviewer, I want the generated infrastructure feature table to carry provenance, so that its origin and derivation are traceable.

#### Acceptance Criteria

1. WHEN the Feature_Builder writes the Feature_Table, THE Feature_Builder SHALL record a Provenance_Record entry for the Feature_Table identifying it as a derived product, listing the source datasets used, the computation CRS, and the retrieval or generation timestamp in UTC.
2. THE Feature_Builder SHALL label the Feature_Table as a derived product in its provenance so that it is not mistaken for custodial source data.
3. WHERE the Feature_Builder generates the method report, THE Feature_Builder SHALL write it using an atomic write and SHALL stamp it with the do-not-edit banner used by other generated pipeline reports.

### Requirement 12: Validation coverage under the no-silent-passes rule

**User Story:** As a quality reviewer, I want the infrastructure feature output validated with explicit pass/fail reporting, so that silent data problems are caught.

#### Acceptance Criteria

1. THE Feature_Builder validation SHALL confirm that the Feature_Table contains exactly one row per Analysis_Grid `cell_id` and SHALL report the expected cell count, the observed row count, and an explicit pass or fail result.
2. THE Feature_Builder validation SHALL confirm that every Analysis_Grid `cell_id` is present in the Feature_Table with no missing and no extra `cell_id`, and SHALL report the counts and an explicit pass or fail result.
3. THE Feature_Builder validation SHALL confirm that the Feature_Table columns exactly match the required schema from Requirement 5 and SHALL report the expected columns, the observed columns, and an explicit pass or fail result.
4. THE Feature_Builder validation SHALL confirm that every non-null distance value in `dist_transmission_km`, `dist_substation_km`, and `dist_connection_km` is greater than or equal to zero and SHALL report the count of negative distance values and an explicit pass or fail result.
5. THE Feature_Builder validation SHALL confirm that `inside_rez` contains only boolean values or null and SHALL report any other value as a fail result, otherwise a pass result.
6. THE Feature_Builder validation SHALL confirm that `confidence_flag` contains only the defined values high or low and SHALL report any other value as a fail result, otherwise a pass result.
7. THE Feature_Builder validation SHALL confirm that every cell with a null distance or REZ value has a low Confidence_Flag and SHALL report the count of violating cells and an explicit pass or fail result.

### Requirement 13: Unit tests for distance-calculation logic

**User Story:** As a developer, I want the distance-calculation logic covered by unit tests, so that per-cell distance computation stays correct as the code evolves.

#### Acceptance Criteria

1. THE unit tests SHALL cover the centroid-to-nearest-line distance using a small synthetic cell and line geometry, asserting the computed distance equals a hand-computed expected value within a documented numeric tolerance.
2. THE unit tests SHALL cover the centroid-to-nearest-point distance using a synthetic cell and a set of point features with a known nearest point, asserting the computed distance equals a hand-computed expected value within a documented numeric tolerance.
3. THE unit tests SHALL assert that the distance to the nearest point on a line geometry is used rather than the distance to a line endpoint, using a synthetic line where the two differ.
4. THE unit tests SHALL assert that distance computation occurs in EPSG:3577 by verifying that identical geometries produce a metre-based distance rather than a degree-based distance.
5. THE unit tests SHALL cover the REZ membership logic by asserting a cell that intersects a REZ polygon is flagged true with the correct `rez_name` and a non-intersecting cell is flagged false with a null `rez_name`.
6. THE unit tests SHALL cover the missing-source behaviour by asserting that an absent or empty source yields a null feature value and a low Confidence_Flag rather than a fabricated distance.

### Requirement 14: Documented full-NSW-grid runtime performance

**User Story:** As a pipeline operator, I want the full-grid runtime documented, so that I can plan pipeline runs across all 47,311 NSW cells.

#### Acceptance Criteria

1. WHEN the Feature_Builder runs over the full NSW Analysis_Grid of all 47,311 cells, THE Feature_Builder SHALL process every cell and complete without any manual intervention or interactive prompt.
2. WHEN a full-NSW-grid run completes, THE Feature_Builder SHALL record the total wall-clock runtime in seconds and report it in the method report together with the number of cells processed.
3. WHEN a full-NSW-grid run completes, THE Feature_Builder `run()` summary dict SHALL include the total stage runtime in seconds, and this value SHALL equal the runtime reported in the method report and match the orchestrator's per-stage timing for the same run within 1 second.
4. IF a full-NSW-grid run fails to process any cell before completion, THEN THE Feature_Builder SHALL halt without reporting a successful runtime and SHALL return an error indication identifying that the full-grid run did not complete.

### Requirement 15: Documentation updates

**User Story:** As a project maintainer, I want the data specification and README kept consistent with this new stage and output, so that documentation matches behaviour.

#### Acceptance Criteria

1. WHEN the Feature_Builder stage and Feature_Table are added, THE data specification SHALL be updated in section 4.3 (infrastructure dataset detail) and section 7 (dataset-to-stage-to-criterion mapping) so that both sections name the Feature_Table output and its per-cell columns and reference the Feature_Builder stage that produces it.
2. WHEN the Feature_Builder stage is added, THE README stage-order table and CLI documentation SHALL be updated to list the new stage at the same execution position that the pipeline stage configuration resolves at runtime.
3. IF the README stage-order position or stage name for the Feature_Builder stage does not match the resolved runtime stage configuration, THEN THE documentation SHALL be treated as failing validation and SHALL be corrected to match the runtime configuration before the stage is considered documented.
4. THE documentation SHALL state the chosen distance-computation projection (EPSG:3577, Australian Albers) and the choice to measure distances from the cell centroid, so that the distance definition is explicit and reproducible.
5. WHERE a frozen decision (Q1-Q7) is affected by this feature, THE change SHALL follow the specification section 8 change-control process AND SHALL be recorded identically in both the data specification section 2 and the README.
