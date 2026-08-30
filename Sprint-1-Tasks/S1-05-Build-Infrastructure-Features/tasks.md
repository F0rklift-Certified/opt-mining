# Implementation Plan: Infrastructure Features (S1-05)

## Overview

This plan implements the `infrastructure.features` stage (`Feature_Builder`) as a new module `pipeline/infrastructure/features.py`, following the design document. For every valid analysis cell in the common grid it derives distance-to-nearest features (`dist_transmission_km`, `dist_substation_km`, `dist_connection_km`), REZ membership features (`inside_rez`, `rez_name`), and a per-cell `confidence_flag`, then writes a per-cell Feature_Table joinable to the grid on `cell_id`.

The implementation language is **Python**, matching the existing pipeline and the design's code samples. Distances are computed with GeoPandas `sjoin_nearest` in **EPSG:3577** (metres → km) and geometry is stored in **EPSG:4326**. All three GA layers (transmission lines, substations, generators) are routed through the shared `pipeline/infrastructure/helpers.py` load-and-filter pattern so there is no divergent per-layer handling. Testing uses **pytest** and **Hypothesis** (property-based tests).

Tasks build incrementally: config → grid/GA/connection/REZ loaders → pure distance & membership core → confidence assignment → assembly/writers → method report + provenance → orchestrator wiring → no-silent-passes validation → documentation. The 13 correctness properties sit next to the pure core they validate, each a single Hypothesis test running at least 100 iterations. Test sub-tasks are marked optional with `*`.

## Tasks

- [ ] 1. Add infrastructure feature-builder config
  - [ ] 1.1 Add feature-builder constants to `pipeline/infrastructure/config.py`
    - Add input paths: `GRID_PATH` (`DATA/grid/nsw_analysis_grid.gpkg`), `TRANSMISSION_SOURCE` and `SUBSTATION_SOURCE` (the GA layers loaded via helpers), `CONNECTION_POINTS_PATH` (`connection-points/aemo_kci_2026.xlsx`), and `REZ_DIR` (`renewable-energy-zones/energyco-nsw/`)
    - Add REZ config: `REZ_NAME_FIELD` (zone-name attribute on the boundary polygons) and `UNNAMED_REZ_PLACEHOLDER = "UNNAMED_REZ"`, `REZ_NAME_DELIMITER = "; "`
    - Add output constants: `FEATURE_TABLE_NAME = "optmining_infra-features_2026_nsw.gpkg"`, `FEATURE_TABLE_LAYER = "infra_features"`, `METHOD_REPORT_NAME = "infrastructure_features_method.md"` (written under `INFRA_META_DIR`)
    - Add `STORAGE_CRS = "EPSG:4326"`, `COMPUTATION_CRS = "EPSG:3577"`, `CONFIDENCE_LEVELS = ("high", "low")`
    - Add REZ boundary files and connection-points file to `EXPECTED_FILES`; reconcile the existing transmission-lines entries (`part_001`/`part_002`) with the source path this stage loads, so `EXPECTED_FILES` names exactly the inputs the stage requires
    - Confirm output filename follows `{source}_{dataset}_{year/vintage}_{region}.{ext}` with region slug `nsw`
    - _Requirements: 5.5, 7.3, 7.5, 5.1_

- [ ] 2. Implement input loaders with fail-fast validation and explicit CRS
  - [ ] 2.1 Create `pipeline/infrastructure/features.py` skeleton, `CrsTransform`/`CrsLog`, and grid loader
    - Create the module with imports (`geopandas`, `pandas`, `pathlib`, `time`, `dataclasses`, `common.geo`, `infrastructure.config`, `infrastructure.helpers`, `grid.config`) and a docstring describing the stage
    - Define the `CrsTransform` dataclass (`source_id`, `source_crs`, `target_crs`, `operation`) and a `CrsLog` accumulator that records one entry per reprojection
    - Implement `_load_grid(grid_path) -> GeoDataFrame`: read the grid GeoPackage; raise `FileNotFoundError`/`RuntimeError` naming the path if missing/unreadable (8.4); raise `ValueError` naming the absent column if no `cell_id` (8.5); raise `ValueError` listing the duplicated values if `cell_id` not unique (8.6); reuse `cell_id` byte-for-byte, never re-derive/renumber/reformat/reorder (8.2); all checks occur before any output is written
    - Derive projected cell centroids in EPSG:3577 for distance computation (logged via `CrsLog`), not from the stored geographic `centroid_lat`/`centroid_lon`
    - _Requirements: 8.1, 8.2, 8.4, 8.5, 8.6, 9.4_

  - [ ] 2.2 Implement `_load_ga_layer` routing all three GA layers through helpers
    - Implement `_load_ga_layer(path, state) -> GeoDataFrame` (or feature list) that calls `helpers.load_geojson` then `helpers.filter_by_state(features, state)` and builds a GeoDataFrame with an explicit source CRS (EPSG:4326), logging the CRS via `CrsLog`
    - Apply the identical `filter_by_state` rule (default `NSW`) to every GA layer — transmission lines, substations, and generators — with no divergent per-layer handling (7.1, 7.2)
    - Load generators via the same helper for context/optional indicators only
    - Raise (halt, no output) if a GA source has no declared CRS or one unresolvable to an EPSG code, naming the source (9.4)
    - _Requirements: 7.1, 7.2, 9.3, 9.4_

  - [ ] 2.3 Implement `_resolve_connection_points` from the AEMO xlsx with explicit CRS
    - Implement `_resolve_connection_points(xlsx_path) -> tuple[GeoDataFrame, int]`: read with `pandas.read_excel`; identify lat/lon columns (documented in the method report); build points with an explicit source CRS of EPSG:4326 before any reprojection (3.3)
    - Exclude records whose coordinates are missing/non-numeric/out-of-range rather than assigning a default location; return the excluded count (3.4)
    - Return an empty result (triggering the missing-source path) if the file is missing, unreadable, or yields zero locatable points (3.5)
    - _Requirements: 3.3, 3.4, 3.5, 9.3_

  - [ ] 2.4 Implement `_load_rez` REZ boundary loader
    - Implement `_load_rez(rez_dir) -> GeoDataFrame | None`: load the NSW EnergyCo REZ boundary polygons with `geopandas.read_file`, exposing the zone-name field from config; return `None` (missing-source path) when the source is missing or unreadable (4.8)
    - Raise (halt, no output) if a loaded REZ source has no declared/resolvable CRS (9.4)
    - _Requirements: 4.8, 9.3, 9.4_

  - [ ]* 2.5 Write unit tests for loader error conditions
    - Assert missing/unreadable grid, missing `cell_id`, duplicate `cell_id` each raise and write no output (8.4, 8.5, 8.6)
    - Assert a source with no declared/resolvable CRS raises naming that source, with no default assumed (9.4)
    - Assert connection-point CRS resolution uses an explicit EPSG:4326 source CRS (3.3) and that invalid records are excluded and counted (3.4)
    - Assert a missing/unreadable REZ or GA source follows the degraded (null feature) path rather than crashing (4.8)
    - _Requirements: 8.4, 8.5, 8.6, 9.4, 3.3, 3.4, 4.8_

- [ ] 3. Implement the pure distance and REZ-membership core
  - [ ] 3.1 Implement `_nearest_distance_km` via `sjoin_nearest` in EPSG:3577
    - Implement `_nearest_distance_km(centroids_3577, target_3577) -> Series` indexed by `cell_id`: `centroids.sjoin_nearest(target, distance_col="dist_m")` then divide by 1000 for km
    - Returns metre-based (not degree-based) distance to the nearest point on the nearest geometry; for line targets this is the nearest point along the line, not an endpoint
    - When the target layer is missing/unreadable/empty (zero features), return null for every cell (no fabricated/sentinel value) so the caller can set confidence low
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 3.1, 3.2, 9.2_

  - [ ] 3.2 Implement `_compute_rez_membership` in one explicit CRS
    - Implement `_compute_rez_membership(grid_3577, rez_3577, crs_log) -> tuple[Series, Series]` producing `inside_rez` and `rez_name`
    - Intersection in one explicit CRS (EPSG:3577), logged via `CrsLog` (4.7); use `geopandas.sjoin(..., predicate="intersects")` so shared interior area or shared boundary counts (4.1)
    - `inside_rez` true iff the cell intersects ≥1 REZ polygon, else false (4.1, 4.2); single overlap → that zone's name (4.3); multiple → distinct names joined by the config delimiter with duplicates collapsed (4.4); no overlap → null `rez_name` (4.5); intersecting a zone with missing/null name → true + `UNNAMED_REZ` placeholder (4.6)
    - When `rez` is `None` (missing source) → null `inside_rez` and null `rez_name` for every cell (4.8)
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8_

  - [ ] 3.3 Implement `_assign_confidence`
    - Implement `_assign_confidence(feature_df) -> Series`: a cell is `low` if any of `dist_transmission_km`, `dist_substation_km`, `dist_connection_km`, `inside_rez`, `rez_name`-eligible value is null due to missing/unavailable source data (6.2); `high` when every feature was computed from available source data (6.3)
    - `confidence_flag` is exactly one of `high` or `low`, no other value (6.4); null distances are never replaced by a fabricated/default/sentinel value (6.1)
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ] 3.4 Implement `_build_feature_table`
    - Assemble exactly the columns `cell_id`, `dist_transmission_km`, `dist_substation_km`, `dist_connection_km`, `inside_rez`, `rez_name`, `confidence_flag`, plus `geometry` (5.1)
    - Exactly one row per grid `cell_id`, `cell_id` reused byte-for-byte from the grid, joinable on `cell_id` (5.2, 8.3)
    - Store geometry (grid cell polygons carried for join convenience) in EPSG:4326 (5.4, 9.1)
    - Add any additional defensible indicator (e.g. `nearest_line_voltage_kv`) as a named column only if included, recording its definition/source field for the method report (5.3)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 8.3, 9.1_

  - [ ]* 3.5 Write property test — nearest-distance correctness
    - **Property 1: Nearest-distance correctness** (compare `sjoin_nearest` to an independent brute-force nearest-point computation for line and point layers)
    - **Validates: Requirements 1.1, 2.1, 3.1**

  - [ ]* 3.6 Write property test — nearest point on line, not endpoint
    - **Property 2: Nearest point on line, not endpoint** (interior-nearest line: perpendicular distance, ≤ both endpoint distances)
    - **Validates: Requirements 1.2**

  - [ ]* 3.7 Write property test — distances computed in metric EPSG:3577
    - **Property 3: Distances are computed in metric EPSG:3577** (km == EPSG:3577 metres / 1000, never degree-based)
    - **Validates: Requirements 1.3, 2.2, 3.2, 9.2**

  - [ ]* 3.8 Write property test — non-negative distances
    - **Property 4: Non-negative distances** (every non-null distance ≥ 0)
    - **Validates: Requirements 12.4**

  - [ ]* 3.9 Write property test — REZ membership and naming
    - **Property 5: REZ membership and naming** (`inside_rez` iff intersects; `rez_name` == distinct joined names; unnamed → placeholder; none → null)
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5, 4.6**

  - [ ]* 3.10 Write property test — missing source yields null feature and low confidence
    - **Property 6: Missing source yields null feature and low confidence** (each source missing/unreadable/empty → null feature, low confidence, no sentinel)
    - **Validates: Requirements 1.4, 2.3, 3.5, 4.8, 6.1**

  - [ ]* 3.11 Write property test — confidence flag reflects completeness and is two-valued
    - **Property 7: Confidence flag reflects completeness and is two-valued** (low iff any null-due-to-missing; else high; always in {high, low})
    - **Validates: Requirements 6.2, 6.3, 6.4**

  - [ ]* 3.12 Write property test — cell_id preservation and one row per cell
    - **Property 8: Cell_id preservation and one row per cell** (output `cell_id` multiset == grid `cell_id` set exactly, byte-for-byte)
    - **Validates: Requirements 5.2, 8.2, 8.3**

  - [ ]* 3.13 Write property test — Feature_Table stored in EPSG:4326
    - **Property 9: Feature_Table stored in EPSG:4326** (written geometry CRS == EPSG:4326)
    - **Validates: Requirements 5.4, 9.1**

  - [ ]* 3.14 Write property test — unresolvable connection points excluded and counted
    - **Property 10: Unresolvable connection points are excluded and counted** (excluded count == invalid-record count; no default location)
    - **Validates: Requirements 3.4**

  - [ ]* 3.15 Write unit tests for distance and REZ logic (Requirement 13)
    - 13.1 centroid-to-nearest-line vs hand-computed value within a documented tolerance
    - 13.2 centroid-to-nearest-point vs hand-computed value within a documented tolerance
    - 13.3 nearest-point-on-line vs endpoint, using a synthetic line where the two differ
    - 13.4 EPSG:3577 metric distance vs degree-based distance for identical geometries
    - 13.5 REZ membership: intersecting cell → true + correct `rez_name`; non-intersecting → false + null
    - 13.6 missing/empty source → null feature + low confidence, not a fabricated distance
    - Each property test uses ≥100 Hypothesis iterations and is tagged `# Feature: s1-05-build-infrastructure-features, Property {n}: {text}`
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6_

- [ ] 4. Checkpoint — pure core verified
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Implement writers, method report, and provenance
  - [ ] 5.1 Implement `_write_feature_table(gdf, path)`
    - Atomic write via `common/geo` helpers: write to a sibling `*.tmp` GeoPackage (layer `infra_features`, EPSG:4326) then `os.replace` onto the target
    - On any exception remove the temp file and leave any pre-existing Feature_Table unmodified; surface an error indication (5.7)
    - Output is a fully regenerable derived product reproducible from sources + grid with no manual editing (5.8)
    - _Requirements: 5.4, 5.6, 5.7, 5.8, 9.1_

  - [ ] 5.2 Implement `_write_method_report(...)`
    - Banner-stamped Markdown via `common.geo.atomic_write_text` + `common.geo.banner("infrastructure.features")` (11.3), written to `INFRA_META_DIR/infrastructure_features_method.md`
    - Record: distance-computation projection (EPSG:3577) and centroid-based distance definition (15.4); one entry per CRS transformation, reconcilable against reprojection events (9.5); connection-point lat/lon columns used and excluded-record count (3.4); confidence low/high counts and per-category reason for each low cell (6.5); any additional indicator's definition/source field (5.3); full-NSW-grid runtime in seconds and cells processed (14.2)
    - _Requirements: 3.4, 5.3, 6.5, 9.5, 11.3, 14.2, 15.4_

  - [ ] 5.3 Implement `_write_provenance(...)`
    - Append/update a `DATA_PROVENANCE.md` row in the infrastructure domain labelling the Feature_Table a **derived product**, listing source datasets, the computation CRS, and the UTC generation timestamp (11.1, 11.2)
    - Write/append a `download_manifest.json` entry for the output (SHA-256, byte count, UTC timestamp, generation params) and a `source_register` entry, consistent with the pipeline convention
    - _Requirements: 11.1, 11.2_

  - [ ]* 5.4 Write unit tests for writers, method report, provenance, and naming
    - Atomic write leaves prior output intact on forced write failure (5.7); output filename matches `{source}_{dataset}_{year/vintage}_nsw.{ext}` (5.5)
    - Method report is banner-stamped and records CRS transforms, excluded count, confidence counts + reasons, EPSG:3577/centroid definition, runtime (9.5, 6.5, 3.4, 15.4, 14.2)
    - Provenance: `DATA_PROVENANCE.md` derived-product row present; manifest entry has sha256/bytes/utc; `source_register` entry added (11.1, 11.2, 11.3)
    - _Requirements: 5.5, 5.7, 6.5, 3.4, 9.5, 11.1, 11.2, 11.3, 14.2, 15.4_

- [ ] 6. Wire the run() entry point
  - [ ] 6.1 Implement `run(verbose=False, state="NSW", grid_path=None, computation_crs="EPSG:3577") -> dict`
    - Orchestrate: `_load_grid` → `_load_ga_layer` (transmission, substation, generators via helpers) → `_resolve_connection_points` → `_load_rez` → reproject all to EPSG:3577 and log every transform → `_nearest_distance_km` per layer → `_compute_rez_membership` → `_assign_confidence` → `_build_feature_table` → `_write_feature_table` → `_write_method_report` → `_write_provenance`
    - Time the run with `time` and include `runtime_seconds` in the summary; halt and raise (not return) if the full-grid run fails to process any cell (14.1, 14.3, 14.4)
    - Return a summary dict with `feature_table_path`, `method_report_path`, `n_cells`, `n_high_confidence`, `n_low_confidence`, `runtime_seconds`; both paths exist on disk after return (10.2)
    - Raise (do not return a dict) on any fatal condition or write failure so the orchestrator halts non-zero (10.3); first parameter `verbose` defaults to `False`; return value is a dict (10.1)
    - _Requirements: 10.1, 10.2, 10.3, 14.1, 14.2, 14.3, 14.4, 9.2, 9.3, 9.5_

  - [ ]* 6.2 Write property + unit tests for the run() contract
    - **Property 11: Regeneration is deterministic (idempotent)** — two runs on fixed inputs produce identical Feature_Tables. **Validates: Requirements 5.8**
    - **Property 12: Successful run returns existing output paths** — returned `feature_table_path`/`method_report_path` exist on disk. **Validates: Requirements 10.2**
    - Unit: signature introspection (`verbose=False` first param, returns dict); forced failure raises, returns no dict, writes no output (10.1, 10.3); summary `runtime_seconds` equals the method-report runtime (14.3)
    - _Requirements: 5.8, 10.1, 10.2, 10.3, 14.3_

- [ ] 7. Register the stage in the orchestrator
  - [ ] 7.1 Register `infrastructure.features` in `pipeline/config.py`
    - Add `"infrastructure.features"` to `STAGES` immediately after `"grid"` (and before `"validate"`), so the grid producer runs first (10.4, 10.7)
    - Leave `DOMAINS` unchanged (infrastructure already present)
    - _Requirements: 10.4, 10.7_

  - [ ] 7.2 Add dispatch and CLI flags in `pipeline/__main__.py`
    - In `_get_runner`: add `elif stage == "infrastructure.features": from .infrastructure.features import run; return run`
    - Add an `--infra-features-crs` CLI argument (distance-computation CRS override, default `EPSG:3577`); reuse the existing `--state` flag
    - In `_build_kwargs`: for `"infrastructure.features"` pass `verbose`, `state`, and `computation_crs` (10.5)
    - Update the module docstring stage-order comment to include `infrastructure.features` after `grid`
    - _Requirements: 7.4, 10.5_

  - [ ] 7.3 Update the infrastructure subpackage docstring
    - Extend `pipeline/infrastructure/__init__.py` to list `features — build per-cell infrastructure features on the common analysis grid` within the infrastructure stage sequence
    - _Requirements: 10.6_

  - [ ]* 7.4 Write registration and ordering wiring tests
    - **Property 13: Resolved execution order places the stage after grid** — for any resolved stage list containing both, grid index < features index. **Validates: Requirements 10.4, 10.7**
    - Assert `_get_runner('infrastructure.features')` returns a callable; `EXPECTED_FILES` lists the required inputs; the `--infra-features-crs` flag exists and is forwarded by `_build_kwargs`; `infrastructure/__init__` docstring lists the stage
    - _Requirements: 7.3, 7.4, 7.5, 10.4, 10.5, 10.6, 10.7_

- [ ] 8. Add no-silent-passes validation checks
  - [ ] 8.1 Implement `validate(...)` for the Feature_Table
    - One row per grid `cell_id` (report expected count, observed count, pass/fail) (12.1)
    - Every grid `cell_id` present, none missing, none extra (report counts, pass/fail) (12.2)
    - Columns exactly match the Requirement 5 schema (report expected/observed columns, pass/fail) (12.3)
    - Every non-null distance ≥ 0 (report count of negatives, pass/fail) (12.4)
    - `inside_rez` is boolean or null only (12.5); `confidence_flag` is `high` or `low` only (12.6)
    - Every cell with a null distance/REZ value has `confidence_flag = low` (report count of violators, pass/fail) (12.7)
    - Each check reports expected vs observed vs explicit pass/fail (no silent passes); make it exercisable from the cross-domain `pipeline/validate.py` tier
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7_

  - [ ]* 8.2 Write unit tests for validation checks
    - Assert each check emits expected/observed/pass-fail and that a seeded bad Feature_Table (wrong row count, extra/missing cell_id, wrong columns, negative distance, non-boolean `inside_rez`, bad `confidence_flag`, null-value-with-high-confidence) fails the relevant check
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7_

- [ ] 9. Checkpoint — stage runs end-to-end under the orchestrator
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 10. Full-NSW-grid integration and smoke tests
  - [ ]* 10.1 Write full-NSW-grid integration test
    - Run over all 47,311 cells; assert every cell is processed with no interactive prompt (14.1); runtime recorded in both the method report and the summary dict and the two agree within 1 second (14.2, 14.3); a forced mid-run failure halts without a success runtime and raises (14.4)
    - _Requirements: 14.1, 14.2, 14.3, 14.4_

  - [ ]* 10.2 Write orchestrator smoke test
    - Assert the stage is in `config.STAGES` after `grid`, required inputs are in `EXPECTED_FILES`, the CLI flag(s) exist and are forwarded by `_build_kwargs`, `_get_runner` returns the stage `run`, and the subpackage `__init__` docstring lists the stage
    - _Requirements: 7.3, 7.5, 10.4, 10.5, 10.6_

- [ ] 11. Update documentation to match the new stage
  - [ ] 11.1 Update the data specification
    - Update §4.3 (infrastructure dataset detail) and §7 (dataset→stage→criterion mapping) to name the Feature_Table output (`optmining_infra-features_2026_nsw.gpkg`) and its per-cell columns and reference the `infrastructure.features` stage that produces it
    - State the EPSG:3577 distance-computation projection and centroid-based distance definition; note that this stage does not change any frozen decision (Q1–Q7), so no §8 change-control is required for this release
    - _Requirements: 15.1, 15.4, 15.5_

  - [ ] 11.2 Update the README stage order and expected outputs
    - Add `infrastructure.features` to the README stage-order table and CLI docs at the resolved runtime position (after `grid`, before `validate`), matching `config.STAGES` exactly (15.2, 15.3)
    - Add the Feature_Table to the expected-outputs table; state the EPSG:3577 distance projection and centroid-based distance definition (15.4)
    - _Requirements: 15.2, 15.3, 15.4_

## Notes

- Tasks marked with `*` are optional test tasks and can be skipped for a faster MVP; core implementation tasks are never optional.
- Each task references specific requirements clauses for traceability.
- Property tests (P1–P13) sit directly under the pure core / wiring they validate so invariants are caught early; each is a single Hypothesis test running at least 100 iterations and tagged `# Feature: s1-05-build-infrastructure-features, Property {n}: {text}`.
- All three GA layers (transmission lines, substations, generators) are loaded and filtered through `pipeline/infrastructure/helpers.py` with the identical `filter_by_state` rule, so there is no divergent per-layer handling.
- CRS is explicit at every boundary: EPSG:4326 storage / EPSG:3577 computation, with one logged `CrsTransform` entry per reprojection, reconcilable in the method report.
- Missing/unreadable/empty target sources are degraded (null feature + low confidence, no sentinel), never fatal; grid and CRS problems are fatal and halt before any output is written.
- Checkpoints (tasks 4 and 9) provide incremental validation before wiring and before documentation.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1", "7.1", "7.3"] },
    { "id": 2, "tasks": ["2.2", "2.3", "2.4", "3.1", "3.2", "3.3"] },
    { "id": 3, "tasks": ["2.5", "3.4", "3.5", "3.6", "3.7", "3.8", "3.9", "3.10", "3.14", "3.15"] },
    { "id": 4, "tasks": ["3.11", "3.12", "3.13", "5.1", "5.2", "5.3"] },
    { "id": 5, "tasks": ["5.4", "6.1", "7.2"] },
    { "id": 6, "tasks": ["6.2", "7.4", "8.1", "11.1", "11.2"] },
    { "id": 7, "tasks": ["8.2", "10.1", "10.2"] }
  ]
}
```
