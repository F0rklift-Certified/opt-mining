# Requirements Document

## Introduction

This feature implements Sprint 1 task S1-04 ("Build the Demand Feature Layer") for the Opt-Mining geospatial pipeline. It adds a new demand **feature-builder** pipeline stage that converts the Sprint 0 demand investigation (AEMO NEM-region operational-demand aggregate, `DATA/electricity-demand/demand_annual_summary.csv`) into a **per-cell electricity-demand proxy feature** on the common analysis grid.

For every analysis cell in the common grid, the stage derives a demand proxy value by spatially allocating regional operational demand to cells, together with the allocation method used, the source NEM region, and a per-cell confidence flag. The core of the feature is a spatial-allocation method that distributes a single AEMO regional demand figure (5 values, one per NEM region) down to individual grid cells. This is explicitly a **proxy**, not a measurement: AEMO regional demand is not the same as local cell demand, and the allocation method and its assumptions must be documented transparently. The resulting per-cell feature table feeds the exclusion/scoring layer (S1-08). It is blocked by the data specification (S1-01) and the common analysis grid (S1-02).

The stage must satisfy the pipeline's established contracts: the uniform `run(verbose=False, ...) -> dict` stage contract, strict keying to the grid's `cell_id`, explicit and logged CRS handling (EPSG:4326 storage / EPSG:3577 computation for any distance or area weighting), atomic writes with a do-not-edit banner on generated reports, the project file-naming convention, full provenance for any new output, and the "no silent passes" validation rule. Per the project Constitution, the stage MUST NOT invent, extrapolate, or hard-code data values to make the pipeline run: every proxy value must be traceable to real AEMO regional demand and, where used, a documented weighting dataset. Because the New England REZ study window and the full NSW grid do not perfectly align with NEM region boundaries, the stage must explicitly define how cells outside NEM regions, cells straddling region boundaries, and cells lacking weighting data are handled rather than silently producing gaps.

This document specifies **requirements only**. Design and tasks are deliberately out of scope here.

## Glossary

- **Demand_Feature_Builder**: The new demand feature-builder pipeline stage specified by this document. It reads the common analysis grid, the NEM-region demand aggregate, the NEM region geometries, and (where the chosen method requires) a weighting dataset, and produces one row of demand-proxy features per analysis cell.
- **Pipeline_Orchestrator**: The pipeline CLI/orchestrator (`pipeline/__main__.py`) that resolves the stage list from `pipeline/config.py` and dispatches each stage's `run()` entry point.
- **Analysis_Grid**: The common analysis cell grid produced by S1-01/S1-02, stored at `DATA/grid/nsw_analysis_grid.gpkg`, keyed by `cell_id` with cell geometry. Cell size is 0.05 degree (~5 km).
- **cell_id**: The unique identifier of an Analysis_Grid cell. Every feature layer in the pipeline joins to the grid via `cell_id`. Demand_Feature_Builder MUST reuse the grid's exact `cell_id` values and MUST NOT re-derive the grid.
- **Demand_Aggregate**: The Sprint 0 AEMO annual regional demand summary, stored at `DATA/electricity-demand/demand_annual_summary.csv` with sidecar `demand_annual_summary.meta.json`, produced by the `pipeline.demand.aggregate` stage. It contains one row per NEM region with `REGIONID`, `MEAN_DEMAND_MW`, `MAX_DEMAND_MW`, `MIN_DEMAND_MW`, `STD_DEMAND_MW`, `SUMMER_MEAN_MW`, `WINTER_MEAN_MW`, `START_DATE`, `END_DATE`. `MEAN_DEMAND_MW` is the primary indicator for downstream scoring.
- **Operational_Demand**: AEMO operational demand — electricity demand met by scheduled, semi-scheduled, and significant non-scheduled generation; excludes behind-the-meter generation (rooftop PV). This is the demand metric used, per frozen decision Q5.
- **NEM_Region**: A National Electricity Market region. Five regions exist (NSW1, QLD1, SA1, TAS1, VIC1). By the project convention, NSW1 covers New South Wales plus the Australian Capital Territory (NSW+ACT), matching the NEM region geometry derivation in `pipeline/geographic/config.py` (`NEM_REGIONS`, state codes NSW="1" plus ACT="8").
- **NEM_Region_Geometry**: The derived NEM region polygon layer `DATA/geographic/derived/nem_regions_asgs2021_national.geojson`, produced by the `geographic.download`/`geographic.derive` path by dissolving ABS state/territory boundaries into NEM regions. It is a derived (not custodial) layer.
- **Source_Region**: The NEM region whose regional demand is allocated to a given cell, recorded per cell as `source_region` (for example `NSW1`).
- **Allocation_Method**: The documented spatial method by which a single regional Operational_Demand figure is distributed across the cells of that region to produce a per-cell Demand_Proxy. Candidate methods are uniform, population-weighted, load-centre proximity, and binary high/low; the chosen method is recorded per cell as `allocation_method`.
- **Demand_Proxy**: The per-cell demand indicator produced by the Allocation_Method, recorded as `demand_proxy`. It is an estimated proxy, not measured local consumption.
- **Weighting_Dataset**: Any dataset (for example an ABS Census 2021 population grid or SA2-level Estimated Resident Population, per frozen decision Q4) used to weight the allocation of regional demand to cells. If used, its source, vintage, licence, and CRS must be recorded in the data specification and carry provenance.
- **Confidence_Flag**: A per-cell quality indicator recorded as `confidence_flag`, reflecting how well-supported that cell's Demand_Proxy is (for example whether the cell lies cleanly inside one NEM region and has supporting weighting data).
- **NoData / Null**: The absence of a valid value. Cells that cannot be assigned a defensible Demand_Proxy (for example cells outside any NEM region) receive a null Demand_Proxy rather than a fabricated value.
- **EPSG:4326**: WGS84 geographic coordinate reference system, the pipeline's storage CRS.
- **EPSG:3577**: GDA94 Australian Albers Equal Area coordinate reference system, the pipeline's computation CRS for distance and area.
- **Feature_Table**: The per-cell output table produced by Demand_Feature_Builder, one row per `cell_id`, containing the demand-proxy, allocation-method, source-region, and confidence columns.
- **Method_Report**: The generated Markdown report documenting the Allocation_Method, its formula, assumptions, limitations, data inputs, edge-case handling, and per-run counts, stamped with the do-not-edit banner.

## Requirements

### Requirement 1: Per-cell demand proxy derivation

**User Story:** As a suitability-model developer, I want a demand proxy value for every analysis cell, so that proximity to electricity demand can inform site-suitability scoring.

#### Acceptance Criteria

1. WHEN the Demand_Feature_Builder runs, THE Demand_Feature_Builder SHALL produce exactly one Demand_Proxy value per Analysis_Grid cell by allocating the Source_Region Operational_Demand to that cell using the documented Allocation_Method.
2. THE Demand_Feature_Builder SHALL derive every Demand_Proxy value from the real Demand_Aggregate regional figure for the cell's Source_Region and SHALL NOT invent, extrapolate, or hard-code demand values.
3. THE Demand_Feature_Builder SHALL use the `MEAN_DEMAND_MW` column of the Demand_Aggregate as the regional demand input for the Allocation_Method and SHALL record in the Method_Report which Demand_Aggregate column was used.
4. THE Demand_Feature_Builder SHALL express the Demand_Proxy on a single documented scale for every cell, being either a normalised value in the closed range 0 to 1 or a stated interpretable unit, and SHALL record the chosen scale and its unit in the Method_Report.
5. IF a cell cannot be assigned a defensible Demand_Proxy from real data, THEN THE Demand_Feature_Builder SHALL record a null `demand_proxy` value for that cell and SHALL set that cell's Confidence_Flag to low.

### Requirement 2: Documented spatial-allocation method

**User Story:** As a pipeline reviewer, I want the spatial-allocation method fully documented, so that per-cell proxy values are reproducible and defensible.

#### Acceptance Criteria

1. THE Demand_Feature_Builder SHALL implement exactly one Allocation_Method selected from uniform, population-weighted, load-centre proximity, or binary high/low, and SHALL record the selected method name in the `allocation_method` column of every cell it assigns.
2. THE Demand_Feature_Builder SHALL generate a Method_Report that states the Allocation_Method name, the allocation formula, the assumptions, the limitations, and the data inputs (including any Weighting_Dataset used).
3. THE Method_Report SHALL state explicitly that the Demand_Proxy is a proxy indicator and not measured local demand, and SHALL state that AEMO regional demand is a regional aggregate rather than a per-cell measurement.
4. WHERE the Allocation_Method uses a Weighting_Dataset, THE Method_Report SHALL identify that dataset's source, vintage, and the weighting formula applied.
5. THE Demand_Feature_Builder SHALL apply the Allocation_Method deterministically, such that a repeated run over unchanged inputs produces identical `demand_proxy`, `allocation_method`, `source_region`, and `confidence_flag` values per cell.
6. WHERE the Method_Report is generated, THE Demand_Feature_Builder SHALL write it using an atomic write and SHALL stamp it with the do-not-edit banner used by other generated pipeline reports.

### Requirement 3: Source-region assignment from NEM region geometry

**User Story:** As a data analyst, I want each cell tied to the correct NEM region, so that the right regional demand figure is allocated to it.

#### Acceptance Criteria

1. WHEN the Demand_Feature_Builder runs, THE Demand_Feature_Builder SHALL assign each cell a Source_Region by spatially relating the cell to the NEM_Region_Geometry and SHALL record the assigned region in the `source_region` column.
2. THE Demand_Feature_Builder SHALL apply the NSW1 = NSW+ACT convention when assigning Source_Region, consistent with the NEM_Region_Geometry derivation, and SHALL record this convention in the Method_Report.
3. THE Demand_Feature_Builder SHALL match each cell's Source_Region to a `REGIONID` present in the Demand_Aggregate, and SHALL use that region's Operational_Demand as the allocation input for the cell.
4. WHEN the Demand_Feature_Builder performs the cell-to-region spatial relation, THE Demand_Feature_Builder SHALL perform it with an explicit CRS and SHALL log the CRS used for the relation.
5. IF a cell's assigned Source_Region has no matching `REGIONID` in the Demand_Aggregate, THEN THE Demand_Feature_Builder SHALL record a null `demand_proxy` and a null `source_region` for that cell and SHALL set that cell's Confidence_Flag to low.

### Requirement 4: Edge-case handling for region coverage

**User Story:** As a pipeline maintainer, I want cells outside regions, on region boundaries, and without weighting data handled explicitly, so that the output is complete and honest despite imperfect coverage.

#### Acceptance Criteria

1. IF a cell does not intersect any NEM_Region_Geometry, THEN THE Demand_Feature_Builder SHALL classify that cell as outside NEM regions, record a null `demand_proxy` and a null `source_region`, and set that cell's Confidence_Flag to low.
2. IF a cell intersects two or more NEM regions (a region-boundary cell), THEN THE Demand_Feature_Builder SHALL assign the Source_Region using one documented deterministic tie-break rule that yields the same result on repeated runs, and SHALL record the boundary-cell occurrence in the Method_Report.
3. WHERE the Allocation_Method uses a Weighting_Dataset and a cell lies in an area with no Weighting_Dataset coverage, THE Demand_Feature_Builder SHALL apply one documented fallback rule for that cell and SHALL set that cell's Confidence_Flag to low.
4. THE Demand_Feature_Builder SHALL document each edge-case rule (cells outside NEM regions, region-boundary cells, cells with no weighting data) in the Method_Report.
5. THE Demand_Feature_Builder SHALL report, in the Method_Report, the count of cells assigned to each Source_Region, the count of cells outside NEM regions, the count of region-boundary cells, and (where a Weighting_Dataset is used) the count of cells with no weighting data, such that the per-region assigned counts plus the outside-region count equal the total Analysis_Grid `cell_id` count.

### Requirement 5: Per-cell confidence flag

**User Story:** As a downstream consumer, I want cells with weakly-supported proxy values flagged, so that I can weight or exclude low-confidence demand estimates.

#### Acceptance Criteria

1. THE Demand_Feature_Builder SHALL set each cell's Confidence_Flag to exactly one value from a documented enumerated set, and SHALL set no value outside that set.
2. THE Demand_Feature_Builder SHALL document, in the Method_Report, the definition of each Confidence_Flag value and the rule that assigns it.
3. IF a cell lies outside all NEM regions or has a null `demand_proxy`, THEN THE Demand_Feature_Builder SHALL set that cell's Confidence_Flag to the lowest confidence value.
4. THE Demand_Feature_Builder SHALL record the Confidence_Flag as the `confidence_flag` column value for every cell.
5. THE Demand_Feature_Builder SHALL report the count of cells at each Confidence_Flag value in the Method_Report, such that the per-value counts sum to the total Analysis_Grid `cell_id` count.

### Requirement 6: Per-cell output table schema, naming, and format

**User Story:** As a downstream consumer, I want a stable, well-named per-cell demand feature table, so that the exclusion and scoring layers can join it reliably to the grid.

#### Acceptance Criteria

1. THE Demand_Feature_Builder SHALL write a Feature_Table containing exactly the columns `cell_id`, `demand_proxy`, `allocation_method`, `source_region`, and `confidence_flag`.
2. THE Demand_Feature_Builder SHALL emit exactly one Feature_Table row per Analysis_Grid `cell_id`, with no missing and no duplicate `cell_id`, joinable to the Analysis_Grid on `cell_id`.
3. WHERE the Feature_Table stores geometry, THE Demand_Feature_Builder SHALL store that geometry in EPSG:4326.
4. THE Demand_Feature_Builder SHALL name the output file following the `{source}_{dataset}_{year/vintage}_{region}.{ext}` convention using the approved region slug `nsw`.
5. THE Demand_Feature_Builder SHALL write the Feature_Table using an atomic write (temporary file plus `os.replace`) via the shared `common/geo` helpers.
6. IF the Feature_Table write fails, THEN THE Demand_Feature_Builder SHALL leave any previously existing Feature_Table output unmodified and SHALL return an error indication.
7. THE Demand_Feature_Builder SHALL produce the Feature_Table as a fully regenerable derived product reproducible from the Demand_Aggregate, the NEM_Region_Geometry, the Analysis_Grid, and any Weighting_Dataset without manual editing.

### Requirement 7: Strict keying to the grid cell_id

**User Story:** As a pipeline architect, I want the demand feature keyed strictly to the existing grid cells, so that all feature layers join consistently on `cell_id`.

#### Acceptance Criteria

1. WHEN the Demand_Feature_Builder starts, THE Demand_Feature_Builder SHALL read the `cell_id` values and cell geometries from the existing Analysis_Grid file (`DATA/grid/nsw_analysis_grid.gpkg`).
2. THE Demand_Feature_Builder SHALL reuse the Analysis_Grid `cell_id` values byte-for-byte without modification and SHALL NOT re-derive, renumber, reformat, or reorder the grid `cell_id` values.
3. THE set of `cell_id` values in the Feature_Table SHALL contain every `cell_id` present in the Analysis_Grid, with no `cell_id` present in the Feature_Table that is absent from the Analysis_Grid, and no `cell_id` value appearing more than once in the Feature_Table.
4. IF the Analysis_Grid file is missing or cannot be opened, THEN THE Demand_Feature_Builder SHALL halt before writing any Feature_Table output and SHALL report an error indicating the missing or unreadable grid input path.
5. IF the Analysis_Grid file is readable but does not contain a `cell_id` column, THEN THE Demand_Feature_Builder SHALL halt before writing any Feature_Table output and SHALL report an error indicating the absent `cell_id` column.
6. IF the Analysis_Grid contains duplicate `cell_id` values, THEN THE Demand_Feature_Builder SHALL halt before writing any Feature_Table output and SHALL report an error indicating the duplicated `cell_id` values.

### Requirement 8: Consumption of the demand aggregate and NEM region geometry inputs

**User Story:** As a pipeline maintainer, I want the demand feature to read only existing pipeline outputs, so that it never fabricates inputs and stays consistent with upstream stages.

#### Acceptance Criteria

1. WHEN the Demand_Feature_Builder starts, THE Demand_Feature_Builder SHALL read the regional demand values from the existing Demand_Aggregate file (`DATA/electricity-demand/demand_annual_summary.csv`).
2. WHEN the Demand_Feature_Builder starts, THE Demand_Feature_Builder SHALL read the region polygons from the existing NEM_Region_Geometry file (`DATA/geographic/derived/nem_regions_asgs2021_national.geojson`).
3. IF the Demand_Aggregate file is missing, cannot be read, or lacks the required `REGIONID` or `MEAN_DEMAND_MW` column, THEN THE Demand_Feature_Builder SHALL halt before writing any Feature_Table output and SHALL report an error identifying the missing or malformed Demand_Aggregate input.
4. IF the NEM_Region_Geometry file is missing or cannot be read, THEN THE Demand_Feature_Builder SHALL halt before writing any Feature_Table output and SHALL report an error identifying the missing or unreadable NEM_Region_Geometry input.
5. WHERE the Allocation_Method uses a Weighting_Dataset, THE Demand_Feature_Builder SHALL read that dataset from its recorded path, and IF that dataset is missing or unreadable, THEN THE Demand_Feature_Builder SHALL halt before writing any Feature_Table output and SHALL report an error identifying the missing or unreadable Weighting_Dataset.

### Requirement 9: Explicit and logged CRS handling

**User Story:** As a geospatial reviewer, I want every CRS boundary made explicit and logged, so that no silent coordinate mismatch corrupts the demand feature.

#### Acceptance Criteria

1. THE Demand_Feature_Builder SHALL store any Feature_Table geometry in EPSG:4326.
2. WHEN the Demand_Feature_Builder performs a distance or area computation (for example load-centre proximity weighting or area-weighted allocation), THE Demand_Feature_Builder SHALL perform that computation in EPSG:3577 and SHALL NOT derive distance or area from EPSG:4326 coordinates.
3. WHEN the Demand_Feature_Builder reads a source dataset whose declared CRS differs from the CRS required for an operation, THE Demand_Feature_Builder SHALL reproject explicitly at that read boundary before the operation and SHALL record, for that reprojection, the source dataset identifier, source CRS, target CRS, and the operation performed.
4. IF a source dataset has no declared CRS or a CRS that cannot be resolved to an EPSG code, THEN THE Demand_Feature_Builder SHALL halt the run without producing the Feature_Table and SHALL emit an error indication identifying the affected source, rather than assuming or defaulting a CRS.
5. WHEN a run completes, THE Demand_Feature_Builder SHALL record in the Method_Report one entry for every CRS transformation applied during that run, each entry stating the source dataset identifier, source CRS, target CRS, and operation.

### Requirement 10: Automated pipeline stage under the run() contract

**User Story:** As a pipeline operator, I want the demand feature builder to run automatically as a registered stage, so that the demand feature regenerates as part of the standard pipeline run.

#### Acceptance Criteria

1. THE Demand_Feature_Builder SHALL expose an importable `run(verbose=False, ...) -> dict` entry point whose first parameter is `verbose` defaulting to `False` and whose return value is a dict, matching the entry-point signature used by the other registered pipeline stages.
2. WHEN the Demand_Feature_Builder `run()` completes successfully, THE Demand_Feature_Builder SHALL return a summary dict containing a key for the output Feature_Table path and a key for the Method_Report path, and both values SHALL be non-empty filesystem paths that exist on disk after the call returns.
3. IF the Demand_Feature_Builder `run()` cannot produce the output Feature_Table or the Method_Report, THEN THE Demand_Feature_Builder SHALL raise an error indicating the failure cause and SHALL NOT return a summary dict, so that the Pipeline_Orchestrator halts the run with a non-zero exit status.
4. THE Demand_Feature_Builder stage SHALL be registered in the `STAGES` list in `pipeline/config.py` at a position later than the `grid` stage, so that the grid producer is scheduled before this consumer.
5. THE Pipeline_Orchestrator SHALL dispatch the Demand_Feature_Builder stage by returning its `run()` function from `_get_runner` and SHALL supply its keyword arguments from `_build_kwargs` in `pipeline/__main__.py`, including the `verbose` flag.
6. THE demand subpackage `__init__.py` docstring SHALL list the Demand_Feature_Builder stage within the demand stage sequence.
7. WHEN the Pipeline_Orchestrator resolves the stages to run, THE resolved execution order SHALL place the Demand_Feature_Builder stage after both the `grid` stage and the demand aggregate stage for every invocation that includes them, so that every producer runs before this consumer.

### Requirement 11: Provenance for the demand feature output

**User Story:** As a data governance reviewer, I want the demand feature output to carry full provenance, so that its origin, method, and any weighting inputs are traceable.

#### Acceptance Criteria

1. WHEN the Demand_Feature_Builder writes the Feature_Table, THE Demand_Feature_Builder SHALL record a provenance entry for the Feature_Table in the demand domain `DATA_PROVENANCE.md`, stating the producing stage, the source inputs (Demand_Aggregate, NEM_Region_Geometry, and any Weighting_Dataset), the Allocation_Method, and the fact that values are proxy indicators.
2. WHEN the Demand_Feature_Builder writes the Feature_Table, THE Demand_Feature_Builder SHALL record a download-manifest-style entry for the output (SHA-256 hash, byte count, and UTC timestamp) consistent with the manifest convention used by other pipeline stages.
3. WHERE the Allocation_Method uses a Weighting_Dataset not already recorded in the pipeline, THE Weighting_Dataset SHALL be registered in the source register with its custodian, access method, native CRS, licence, and vintage before the Demand_Feature_Builder relies on it.
4. THE Demand_Feature_Builder SHALL label the Feature_Table as a derived proxy product in its provenance record, distinguishing it from custodial measured data.

### Requirement 12: Validation coverage under the no-silent-passes rule

**User Story:** As a quality reviewer, I want the demand feature output validated with explicit pass/fail reporting, so that silent data problems are caught.

#### Acceptance Criteria

1. THE Demand_Feature_Builder validation SHALL confirm that the Feature_Table contains exactly one row per Analysis_Grid `cell_id` and SHALL report the expected cell count, the observed row count, and an explicit pass or fail result.
2. THE Demand_Feature_Builder validation SHALL confirm that every Analysis_Grid `cell_id` is present in the Feature_Table with no missing and no extra `cell_id`, and SHALL report the counts and an explicit pass or fail result.
3. THE Demand_Feature_Builder validation SHALL confirm that the Feature_Table columns exactly match the required schema from Requirement 6 and SHALL report the expected columns, the observed columns, and an explicit pass or fail result.
4. WHERE the Demand_Proxy is normalised to the range 0 to 1, THE Demand_Feature_Builder validation SHALL confirm that every non-null `demand_proxy` value falls within the closed range 0 to 1 and SHALL report the count of out-of-range cells and an explicit pass or fail result.
5. THE Demand_Feature_Builder validation SHALL confirm that `source_region` values are either null or one of the `REGIONID` values present in the Demand_Aggregate, and SHALL report any other value as a fail result, otherwise a pass result.
6. THE Demand_Feature_Builder validation SHALL confirm that `confidence_flag` contains only values from the documented enumerated set, and SHALL report any other value as a fail result, otherwise a pass result.
7. THE Demand_Feature_Builder validation SHALL confirm demand conservation, such that where the Allocation_Method distributes a region's Operational_Demand across its cells, the sum of allocated demand across a region's cells equals that region's input demand within a documented numeric tolerance, and SHALL report the expected regional total, the observed allocated total, and an explicit pass or fail result.

### Requirement 13: Unit tests for allocation logic

**User Story:** As a developer, I want the spatial-allocation logic covered by unit tests, so that per-cell allocation stays correct as the code evolves.

#### Acceptance Criteria

1. THE unit tests SHALL cover the Allocation_Method using a small synthetic region with a known cell set and a known regional demand figure, asserting the computed per-cell `demand_proxy` values equal hand-computed expected values within a documented numeric tolerance.
2. THE unit tests SHALL cover demand conservation by asserting that the sum of allocated `demand_proxy` (in interpretable units, before any normalisation) across a synthetic region's cells equals the region's input demand within the documented tolerance.
3. THE unit tests SHALL cover the outside-region edge case by asserting a cell that intersects no NEM region receives a null `demand_proxy`, a null `source_region`, and the lowest Confidence_Flag value.
4. THE unit tests SHALL cover the region-boundary edge case by asserting a cell intersecting two regions is assigned a single Source_Region per the documented deterministic tie-break rule.
5. WHERE a Weighting_Dataset is used, THE unit tests SHALL cover the no-weighting-data fallback by asserting that a cell with no weighting coverage receives the documented fallback value and the lowest Confidence_Flag value.

### Requirement 14: Documentation updates

**User Story:** As a project maintainer, I want the data specification and README kept consistent with this new stage and output, so that documentation matches behaviour.

#### Acceptance Criteria

1. WHEN the Demand_Feature_Builder stage and Feature_Table are added, THE data specification SHALL be updated in section 4 (dataset detail) and section 7 (dataset-to-stage-to-criterion mapping) so that both sections name the Feature_Table output and its per-cell columns (`cell_id`, `demand_proxy`, `allocation_method`, `source_region`, `confidence_flag`) and reference the Demand_Feature_Builder stage that produces it.
2. WHERE the Allocation_Method uses a Weighting_Dataset, THE data specification section 4 SHALL record that dataset's source and vintage, and its addition SHALL follow the specification section 8 change-control process.
3. WHEN the Demand_Feature_Builder stage is added, THE README stage-order table and CLI documentation SHALL be updated to list the new stage at the same execution position that the pipeline stage configuration resolves at runtime.
4. IF the README stage-order position or stage name for the Demand_Feature_Builder stage does not match the resolved runtime stage configuration, THEN THE documentation SHALL be treated as failing validation and SHALL be corrected to match the runtime configuration before the stage is considered documented.
5. WHERE a frozen decision (Q1-Q7) is affected by this feature (in particular Q4 population data source and Q5 operational demand), THE change SHALL follow the specification section 8 change-control process AND SHALL be recorded identically in both the data specification section 2 and the README.
6. THE documentation SHALL state that the Demand_Proxy is a proxy indicator and not measured local demand, and SHALL describe the Allocation_Method, its assumptions, and its limitations consistently with the Method_Report.
