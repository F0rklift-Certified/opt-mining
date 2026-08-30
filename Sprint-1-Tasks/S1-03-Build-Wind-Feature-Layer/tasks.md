# Implementation Plan: Build the Wind Feature Layer (S1-03)

## Overview

This plan implements the `pipeline/wind/features.py` feature-builder stage described in
`design.md`, satisfying all 12 requirements in `requirements.md`. The approach is incremental
and test-driven: scaffold the module, config constants, and `CellStat` dataclass; build each
pure logic function (CRS assertion, grid reader, zonal block statistic, confidence flag) with
its unit tests; assemble the Feature_Table writer, method-report writer, and provenance
recorder; orchestrate `run()`; add `validate()`; register the stage in the pipeline; then
implement the 8 property-based tests, add a full-grid integration test, and update documentation.

Language: **Python** (the design specifies concrete rasterio/numpy/geopandas signatures). Zonal
statistics use pure `rasterio` + `numpy` + `geopandas`/`shapely` (windowed reads,
`geometry_mask`/`rasterize` with `all_touched=False`, `src.scales`) — no `rasterstats`;
`hypothesis` is added test-only. Under Option A each cell is a clean 20×20 native-pixel block, so
there is no reprojection or interpolation of the GWA rasters. Every task builds on prior ones and
wires into `run()` so no code is orphaned.

Reused contracts (per design §Overview): `common/geo.atomic_write_text`, `common/geo.banner`;
`grid/config.STORAGE_CRS` / `COMPUTATION_CRS` (authoritative — not re-hardcoded); the
`{"name","expected","observed","passed"}` check-dict shape from `validate.py` / `wind/validate.py`;
the `{source}_{dataset}_{year/vintage}_{region}.{ext}` naming convention with region slug `nsw`;
the `wind/download.run` manifest/provenance idiom (read-merge-write so the download records are
not clobbered).

## Tasks

- [ ] 1. Add wind feature-builder config constants
  - Add to `pipeline/wind/config.py` beside the existing wind paths/aggregation constants:
    `WIND_FEATURES_DIR = WIND_DIR / "features"`, `WIND_FEATURE_SOURCE`
    (`gwa_v4_wind-speed_100m_new-england-rez.tif`), `WIND_VARIABLE` (`wind_speed_100m`),
    `WIND_VARIABLE_UNITS` (`m/s`), `WIND_DATA_SOURCE` (`GWA v4`), `WIND_AGG_STATISTIC` (`mean`),
    `WIND_PLAUSIBLE_MIN` (0.0), `WIND_PLAUSIBLE_MAX` (25.0), and the enumerated confidence values
    `CONF_VALID` (`valid`) and `CONF_NODATA` (`no_data`).
  - _Requirements: 1.1, 2.2, 4.2, 4.3, 5.1, 10.2_
  - _Design ref: §Components (Wind config additions); §Data Models_

- [ ] 2. Scaffold the feature-builder module and test-only dependency
  - Create `pipeline/wind/features.py` with the module docstring, imports (`rasterio`, `numpy`,
    `geopandas`, `shapely`, `time`, `os`, `hashlib`, `json`, `pathlib.Path`), the reused imports
    `from ..common.geo import atomic_write_text, banner` and
    `from ..grid.config import STORAGE_CRS, COMPUTATION_CRS`, plus `from . import config`.
  - Define the `run(verbose: bool = False) -> dict` skeleton with the full docstring from design
    §Components (returns `feature_table`, `report`, `manifest`, `n_cells`, `n_valid`, `n_nodata`,
    `stats`; raises on halting conditions) — body left as a stub for task 8.
  - Add the `CellStat` dataclass exactly as specified in design §Data Models (`value`, `n_valid`,
    `n_nodata`, `in_coverage`; invariant `n_valid + n_nodata == total block pixels`).
  - Add `hypothesis` (test-only) to `requirements.txt`; do NOT add `rasterstats`.
  - _Requirements: 6.1_
  - _Design ref: §Components (public entry point, CellStat); §Dependencies (test dependency)_

- [ ] 3. Implement the grid reader and CRS boundary assertion
  - [ ] 3.1 Implement `read_grid_cells(grid_path)`
    - Read `cell_id` + geometry from the grid GeoPackage via `geopandas.read_file` in
      `STORAGE_CRS`; reuse `cell_id` byte-for-byte without reorder/renumber.
    - Raise `FileNotFoundError` (naming the path) when the grid is missing/unopenable (6.6),
      `ValueError` when there is no `cell_id` column, and `ValueError` listing the duplicated
      values when `cell_id` has duplicates.
    - _Requirements: 2.3, 2.4, 6.6_
    - _Design ref: §Components read_grid_cells; §Error Handling_
  - [ ] 3.2 Implement `_assert_storage_crs(grid, src)`
    - Assert the grid CRS and raster CRS both resolve to EPSG:4326; raise `ValueError` reporting
      the mismatch when either is `None` or a different EPSG — never silently reproject. Log the
      storage-CRS assertions when `verbose`.
    - _Requirements: 7.1, 7.3, 7.4_
    - _Design ref: §CRS handling; §Error Handling_
  - [ ]* 3.3 Write unit tests for the grid reader and CRS assertion
    - Assert a valid synthetic grid returns `cell_id` + geometry unchanged; assert missing file,
      no `cell_id`, and duplicate `cell_id` each raise the correct error; assert a non-4326
      grid/raster triggers a reported mismatch with no silent reprojection.
    - _Requirements: 6.6, 7.4_

- [ ] 4. Implement the zonal block statistic and coverage test
  - [ ] 4.1 Implement `_cell_in_coverage(src, cell_geom)` and `_zonal_block_stat(src, cell_geom, stat)`
    - `_cell_in_coverage`: cell-centroid-in-raster-bounds fast-path test that short-circuits the
      majority of NSW cells outside the current GWA clip extent.
    - `_zonal_block_stat`: windowed read via `rasterio.windows.from_bounds(...).round_offsets().round_lengths()`,
      build a cell-centre mask with `rasterio.features.geometry_mask`/`rasterize` (`all_touched=False`),
      apply `src.scales[0]` (default 1.0), exclude `src.nodata`/masked pixels, count `n_valid` and
      `n_nodata` (including in-cell positions outside raster data as NoData), compute the documented
      **mean** statistic, and return `CellStat`. `value` is `None` when `n_valid == 0`; deterministic
      pixel set on repeated runs. Under Option A a fully-covered cell is a clean 20×20 = 400 block.
    - _Requirements: 2.1, 2.5, 3.1, 3.2, 3.3, 3.4, 5.3_
    - _Design ref: §Zonal-statistics method (pixel-inclusion, NoData rule, scaled rasters, coverage test)_
  - [ ]* 4.2 Write unit tests for the zonal statistic
    - Aggregation mean on a synthetic raster + cell equals a hand-computed value within tolerance `1e-9` (11.1).
    - NoData pixels excluded from the statistic and counted separately; assert `n_valid + n_nodata == total` (11.3).
    - All-NoData cell yields `value is None` (11.2).
    - _Requirements: 11.1, 11.2, 11.3, 3.2, 3.3_

- [ ] 5. Implement the confidence flag
  - [ ] 5.1 Implement `_confidence_flag(stat)`
    - Return `config.CONF_VALID` (`"valid"`) when `stat.n_valid >= 1`, else `config.CONF_NODATA`
      (`"no_data"`). Result is always exactly one of the enumerated values; out-of-coverage
      (`in_coverage == False`) always yields `"no_data"`.
    - _Requirements: 5.1, 5.2, 5.3_
    - _Design ref: §Zonal-statistics (confidence rule)_
  - [ ]* 5.2 Write unit tests for the confidence flag
    - Cell with >=1 valid pixel → `"valid"`; zero-valid / all-NoData / out-of-coverage cell →
      `"no_data"`; assert the returned value is always in `{valid, no_data}`.
    - _Requirements: 5.1, 5.2, 5.3_

- [ ] 6. Checkpoint - core logic functions complete
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Implement the Feature_Table writer, method-report writer, and provenance recorder
  - [ ] 7.1 Implement `_write_feature_table(gdf, path)`
    - Atomic GeoPackage write (`to_file(tmp)` + `os.replace`) in `STORAGE_CRS`, mirroring
      `grid/generate.run()`; leave any prior output intact on failure. Filename
      `gwa_v4_wind-feature_2023_nsw.gpkg` following `{source}_{dataset}_{vintage}_{region}` with
      region slug `nsw`. Assemble the exact five-column schema (`cell_id`, `wind_speed_100m`,
      `units`, `data_source`, `confidence_flag`) plus geometry copied from the grid, with null
      (NaN) wind values for no-data cells.
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_
    - _Design ref: §Components _write_feature_table; §Data Models (schema); §Error Handling_
  - [ ] 7.2 Implement `_write_report(report_text, path)` and the report builder
    - `atomic_write_text` stamped with `banner("wind.features")`; assemble the seven report
      sections from design §Data Models (Method report structure): header/banner; variable
      selection (variable, hub height 100 m, units, source raster filename + justification for
      Q1 mean / Q2 100 m); aggregation method (statistic, cell-centre inclusion basis, partial-cell
      boundary rule verbatim, NoData rule); NoData/zero-valid occurrences with `valid + no_data ==
      total`; confidence enum + assignment rule; CRS handling (EPSG:4326 storage, no reprojection
      under Option A, any reprojection event logged); output statistics (min/max/mean over valid cells).
    - _Requirements: 1.2, 1.3, 2.2, 3.4, 3.5, 5.5, 7.3, 9.1, 9.2, 9.3, 9.4_
    - _Design ref: §Data Models (Method report structure); §Zonal-statistics (report contents)_
  - [ ] 7.3 Implement `_record_provenance(table_path, source_raster, manifest_path)`
    - Append a derived-layer row to `DATA/wind-resource/DATA_PROVENANCE.md` naming the source GWA
      dataset (`GWA v4`), the derivation method (mean of 20×20 native pixels per cell), and that
      the output is a derived layer regenerable from the GWA raster + the grid.
    - Read-merge-write `DATA/wind-resource/metadata/download_manifest.json`: load the existing
      manifest, add/replace the feature-table record with SHA-256 hash, byte count, and UTC
      timestamp, and write back atomically so the `wind/download.run` records are not clobbered.
    - _Requirements: 8.1, 8.2, 8.3_
    - _Design ref: §Components _record_provenance; §Cross-component impact (provenance conventions)_

- [ ] 8. Assemble and wire `run()`
  - Orchestrate the full body: `read_grid_cells`, resolve and open the source GWA raster once
    (raise `FileNotFoundError` if missing), `_assert_storage_crs`, per-cell `_zonal_block_stat`
    with the `_cell_in_coverage` short-circuit, `_confidence_flag`, assemble the one-row-per-`cell_id`
    Feature_Table (exact five-column schema + geometry), compute min/max/mean over valid cells and
    valid/no-data counts, `_write_feature_table`, `_write_report`, `_record_provenance`, then
    `validate`.
  - Return the summary dict `{feature_table, report, manifest, n_cells, n_valid, n_nodata, stats}`
    only on success; on any halting condition raise (no summary dict) so the orchestrator exits
    non-zero. Log min/max/mean and valid/no-data counts on completion.
  - _Requirements: 2.1, 2.3, 2.5, 6.1, 6.5, 6.6, 9.1, 9.2_
  - _Design ref: §Architecture (flow); §Components (public entry point); §Error Handling_

- [ ] 9. Implement `validate()` with no-silent-passes checks
  - [ ] 9.1 Implement `validate(feature_table_path, grid_path)`
    - Read the written table + grid; produce `{"name","expected","observed","passed"}` dicts for:
      row count == grid cell count (10.1); every non-null wind value within
      `[WIND_PLAUSIBLE_MIN, WIND_PLAUSIBLE_MAX]` (10.2); every `no_data` cell has a null wind value
      (10.3); `confidence_flag` in `{valid, no_data}` (5.1). Return `{"checks":[...], "passed":int,
      "total":int}`. Any failing check reports expected/observed/`passed=False` — never a silent pass.
    - _Requirements: 5.1, 10.1, 10.2, 10.3, 10.4_
    - _Design ref: §Testing Strategy (validation checks)_
  - [ ]* 9.2 Write unit tests for `validate()` including one-row-per-cell
    - Assert a correct table passes all checks; assert each injected fault (wrong row count,
      out-of-range value, no-data cell with a non-null value, bad confidence value) yields
      `passed == False` with expected/observed populated; assert the output Feature_Table has
      exactly one row per input `cell_id` (11.4).
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 11.4_

- [ ] 10. Register the stage in the pipeline and orchestrator
  - [ ] 10.1 Register in config, orchestrator, and subpackage docstring
    - Add `"wind.features"` to `pipeline/config.py` `STAGES` immediately after `"grid"` and before
      `"validate"`.
    - Add the `_get_runner` dispatch branch for `wind.features` in `pipeline/__main__.py` (after the
      `grid` branch); confirm `_build_kwargs` needs no change (verbose-only, and the existing
      `wind.download`/`heights`/`bbox` branches do not match `wind.features`).
    - Add stage 6 (`features`) to the `pipeline/wind/__init__.py` docstring with the "CONSUMES the
      grid, registered in config.STAGES AFTER `grid`, not inline with 1-5" note.
    - _Requirements: 6.2, 6.3, 6.4, 12.1_
    - _Design ref: §Components (config/orchestrator/subpackage additions); §Stage-ordering resolution_
  - [ ]* 10.2 Add/extend structural tests
    - Extend `tests/test_pipeline_structure.py`: assert `pipeline.wind.features.run` is importable;
      assert `"wind.features"` is in `STAGES` and its index is greater than the `"grid"` index; if a
      `--only wind` resolution count is asserted anywhere, update it to include `wind.features`.
    - _Requirements: 6.2, 6.3_

- [ ] 11. Checkpoint - stage integrated and validated
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 12. Implement the 8 property-based tests
  - Create `tests/test_wind_features.py` (repo-root `tests/`, `Test*` classes) using `hypothesis`
    with `@settings(max_examples=100)`. Generators build small synthetic numpy rasters (with a
    chosen nodata), synthetic GWA-lattice-aligned cell polygons, and small synthetic grids — no
    network, no real files. Tag each test
    `# Feature: s1-03-build-wind-feature-layer, Property {n}: {text}`.
  - [ ]* 12.1 Property 1 — zonal statistic equals mean of valid pixels, NoData excluded
    - **Property 1: Zonal statistic equals the mean of valid pixels, NoData excluded**
    - **Validates: Requirements 2.1, 3.3**
  - [ ]* 12.2 Property 2 — valid + NoData counts partition the cell's block
    - **Property 2: Valid and NoData counts partition the cell's block**
    - **Validates: Requirements 3.2**
  - [ ]* 12.3 Property 3 — deterministic pixel selection
    - **Property 3: Deterministic pixel selection**
    - **Validates: Requirements 3.1, 3.4**
  - [ ]* 12.4 Property 4 — zero valid pixels yield null value and no-data flag (no fabrication)
    - **Property 4: Zero valid pixels yield a null value and the no-data flag (no fabrication)**
    - **Validates: Requirements 2.5, 5.3, 5.4**
  - [ ]* 12.5 Property 5 — confidence flag is the valid/no-data biconditional over the enum
    - **Property 5: Confidence flag is the valid/no-data biconditional over the enumerated set**
    - **Validates: Requirements 5.1, 5.2**
  - [ ]* 12.6 Property 6 — output cell_id set is a bijection with the grid, values preserved
    - **Property 6: Output cell_id set is a bijection with the grid, values preserved**
    - **Validates: Requirements 2.3, 2.4**
  - [ ]* 12.7 Property 7 — non-null wind values fall within the plausible range
    - **Property 7: Non-null wind values fall within the plausible range**
    - **Validates: Requirements 10.2**
  - [ ]* 12.8 Property 8 — resolved stage order places the feature builder after the grid
    - **Property 8: Resolved stage order places the feature builder after the grid**
    - **Validates: Requirements 6.3**
  - _Design ref: §Correctness Properties; §Testing Strategy (PBT)_

- [ ] 13. Add the full-grid integration test
  - [ ]* 13.1 Write the opt-in full-grid integration test
    - In `tests/test_wind_features.py`, run `run()` against the real grid + GWA raster if present
      and assert `n_cells` equals the grid cell count (10.1), the summary dict contains
      `stats`/`n_valid`/`n_nodata` (9.1, 9.2), and the method report exists with the do-not-edit
      banner. `pytest.skip` when the grid GeoPackage or source raster is absent (mirroring
      `TestGeoPackageRoundtrip` in `tests/test_grid.py`).
    - _Requirements: 6.5, 9.1, 9.2, 9.4_

- [ ] 14. Update documentation
  - [ ] 14.1 Update `pipeline/README.md`
    - Add `wind.features` to the Stage Execution Order block and the ASCII flow between `grid` and
      `validate` (matching resolved runtime order); add the Feature_Table row to the Wind Resource
      expected-outputs table; add a CLI note that `--only wind` runs `features` against a
      pre-existing grid.
    - _Requirements: 12.1_
    - _Design ref: §Cross-component impact (Documentation)_
  - [ ] 14.2 Update `DATA/data-specification/sprint1_data_specification.md`
    - §4: add a dataset-detail entry for the wind Feature_Table naming its per-cell columns
      (including `confidence_flag`), the selected variable/hub height (mean wind speed at 100 m),
      and the New-England-REZ coverage gap vs the full NSW grid; §7: add the GWA v4 →
      `wind.features` stage → wind-resource suitability criterion mapping row; note the addition
      under the §8 change-control "Adding a New Dataset" process; record that Q1 (statistic = mean)
      and Q2 (hub height = 100 m) are *implemented, not changed* (no §8 frozen-parameter edit, no
      dual spec-§2/README change).
    - _Requirements: 12.2_
    - _Design ref: §Cross-component impact (Documentation, Frozen decisions)_

- [ ] 15. Final checkpoint - ensure all tests pass
  - Ensure all unit, property-based, structural, and (when the grid + raster are present)
    integration tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional test sub-tasks and can be skipped for a faster MVP; core
  implementation tasks are never optional.
- Each task references specific granular requirement clauses for traceability, plus a `_Design ref:_`
  pointer where useful.
- Checkpoints (tasks 6, 11, 15) ensure incremental validation.
- Property-based tests (task 12) validate the 8 universal correctness properties from the design;
  unit tests (Req 11) are distributed across tasks 4, 5, and 9; validation (Req 10) is task 9.
- No deployment, user-testing, or metrics-gathering tasks are included — every task is code, tests,
  or documentation implied by the design.
- Cross-component impact per the holistic-project-awareness rule: registering the stage changes any
  `--only wind` resolution count (task 10.2), reuses `grid/config` constants (no constant
  duplication), requires the manifest read-merge-write so `download_manifest.json` records are not
  clobbered (task 7.3), and requires the README + data-specification updates (task 14) for the
  feature to be complete.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1"] },
    { "id": 2, "tasks": ["3.1", "3.2"] },
    { "id": 3, "tasks": ["3.3", "4.1"] },
    { "id": 4, "tasks": ["4.2", "5.1"] },
    { "id": 5, "tasks": ["5.2", "7.1"] },
    { "id": 6, "tasks": ["7.2", "7.3"] },
    { "id": 7, "tasks": ["8.1"] },
    { "id": 8, "tasks": ["9.1", "10.1", "14.1", "14.2"] },
    { "id": 9, "tasks": ["9.2", "10.2", "13.1"] },
    { "id": 10, "tasks": ["12.1", "12.2", "12.3", "12.4", "12.5", "12.6", "12.7", "12.8"] }
  ]
}
```

Note: single-subtask parents (1, 2, 8) contribute their one leaf (`1.1`, `2.1`, `8.1`). Tasks that
write to `pipeline/wind/features.py` (3.1, 3.2, 4.1, 5.1, 7.1, 7.2, 7.3, 8.1, 9.1) are sequenced
across separate waves to avoid write conflicts; the property tests (12.x) all write
`tests/test_wind_features.py` and run last as a parallel wave after the module and its writers
exist (they share a file, so if executed by separate agents they must serialize on that file —
they are grouped in one wave as independent test additions). Config (1.1) precedes the module
scaffold (2.1) because `features.py` imports the new `wind/config` constants.
