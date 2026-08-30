# Implementation Plan: Geographic & Environmental Features (S1-06)

## Overview

This plan implements the `pipeline/geographic/features.py` feature-builder stage
described in `design.md`, satisfying all 14 requirements in `requirements.md`. The
approach is incremental and test-driven: scaffold the module and dataclasses, build
each pure logic function (grid reader, raster zonal stat, categorical mode, protected
overlap, confidence flag) with its unit tests, assemble the Feature_Table writer and
method report, orchestrate `run()`, add `validate()`, register the stage in the
pipeline, then implement the 15 property-based tests, update documentation, and add a
full-grid integration test.

Language: **Python** (the design specifies concrete rasterio/numpy/geopandas signatures).
Zonal statistics use pure `rasterio` + `numpy` + `geopandas`/`shapely` (no `rasterstats`);
`hypothesis` is added test-only. Every task builds on prior ones and wires into `run()`
so no code is orphaned.

Reused contracts (per design §Overview): `common/geo.atomic_write_text`, `common/geo.banner`,
`common/geo.apply_vsicurl_env`; `grid/config.STORAGE_CRS` / `COMPUTATION_CRS`; the
`{"name","expected","observed","passed"}` check-dict shape; the
`{source}_{dataset}_{year/vintage}_{region}.{ext}` naming convention.

## Tasks

- [x] 1. Scaffold the feature-builder module and test-only dependency
  - Create `pipeline/geographic/features.py` with the module docstring, imports
    (`rasterio`, `numpy`, `geopandas`, `shapely`, `time`, `os`, `pathlib.Path`), and the
    reused imports `from ..common.geo import atomic_write_text, banner, apply_vsicurl_env`
    and `from ..grid.config import STORAGE_CRS, COMPUTATION_CRS`.
  - Define the `run(verbose: bool = False) -> dict` skeleton with the full docstring from
    design §Components (returns `feature_table`, `report`, `n_cells`, `runtime_s`; raises on
    halting conditions) — body left as a stub for task 10.
  - Add the `CellStat` and `ModeResult` dataclasses exactly as specified in design §Data Models
    (`CellStat`: value, n_valid, n_nodata, in_coverage; `ModeResult`: land_use, code, n_valid,
    n_nodata, in_coverage).
  - Declare module-level constants: output dir `DATA/geographic/features/`, output filename
    `optmining_geographic-features_2024_nsw.gpkg`, report path
    `DATA/geographic/metadata/geographic_features_method.md`, the eight-column schema list, the
    `protected_area_name` delimiter `"; "`, and the required-raster set for confidence
    (elevation, slope, NLUM; TRI excluded).
  - Add `hypothesis` (test-only) to `requirements.txt`; do NOT add `rasterstats`.
  - _Requirements: 10.1_
  - _Design ref: §Components (public entry point, dataclasses), §Dependencies_

- [x] 2. Implement the grid reader with halt conditions
  - [x] 2.1 Implement `read_grid_cells(grid_path)`
    - Read `cell_id` + geometry from the grid GeoPackage via `geopandas.read_file` in
      `STORAGE_CRS`; reuse `cell_id` byte-for-byte without reorder/renumber.
    - Raise `FileNotFoundError` (path) when the grid is missing/unopenable (8.4),
      `ValueError` when there is no `cell_id` column (8.5), and `ValueError` listing the
      duplicated values when `cell_id` has duplicates (8.6).
    - _Requirements: 8.1, 8.2, 8.4, 8.5, 8.6_
    - _Design ref: §Components read_grid_cells; §Error Handling_
  - [x] 2.2 Write unit tests for `read_grid_cells`
    - Assert a valid synthetic grid returns cell_id + geometry unchanged; assert the three
      halt conditions each raise the correct error (missing file, no `cell_id`, duplicate `cell_id`).
    - _Requirements: 8.4, 8.5, 8.6_

- [x] 3. Implement the ALUM class-table loader
  - [x] 3.1 Implement `load_alum_class_table(path)`
    - Return `{int(row["Value"]): row["TERTV8"]}` from the ALUM v8 CSV, matching the
      `geographic/inspect._load_class_table` idiom.
    - _Requirements: 3.3, 3.4_
    - _Design ref: §Components load_alum_class_table; §Zonal-statistics (categorical mode)_
  - [x] 3.2 Write unit test for the class-table loader
    - Assert a small synthetic CSV maps codes to names and that integer keys are produced.
    - _Requirements: 3.3_

- [x] 4. Implement the raster zonal-statistics core
  - [x] 4.1 Implement `_raster_coverage(src, cell_geom)` and `_zonal_raster_stat(src, cell_geom, stat)`
    - `_raster_coverage`: cell-centroid-in-raster-bounds fast-path test (short-circuits
      out-of-coverage cells).
    - `_zonal_raster_stat`: windowed read via `rasterio.windows.from_bounds(...)`, build a
      cell-centre mask with `rasterio.features.geometry_mask`/`rasterize` (`all_touched=False`),
      apply `src.scales[0]` (default 1.0), exclude `src.nodata`/masked pixels, count `n_valid`
      and `n_nodata` (including in-cell positions outside raster data as NoData), compute the
      documented **mean** statistic, and return `CellStat`. `value` is `None` when `n_valid == 0`;
      `in_coverage` is `False` when centroid is outside bounds or all sampled pixels fall
      outside valid data.
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 2.1, 2.2, 2.3, 2.4, 2.6, 6.2, 6.3_
    - _Design ref: §Zonal-statistics method (pixel-inclusion, NoData rule, scaled rasters, coverage test)_
  - [x] 4.2 Write unit tests for the zonal statistic
    - Terrain mean on a synthetic raster + cell equals a hand-computed value within tolerance `1e-9` (12.1).
    - NoData pixels excluded from the statistic and counted separately; assert `n_valid + n_nodata == total` (12.3).
    - Zero-valid-pixel (all-NoData) cell yields `value is None` (12.5).
    - Centroid-inside edge case where sampled pixels fall outside data classifies out-of-coverage.
    - _Requirements: 12.1, 12.3, 12.5, 2.2, 6.3_

- [x] 5. Implement the categorical mode for land use
  - [x] 5.1 Implement `_categorical_mode(src, cell_geom, class_table)`
    - Windowed cell-centre selection (same rule as task 4); `numpy.unique(codes, return_counts=True)`
      over valid pixels, pick max count; tie-break **lowest code wins** (deterministic).
    - Map winning code to `class_table[code]`; unmapped code → `"unmapped:<code>"`; exclude the
      raster nodata before the mode. Return `ModeResult`; `land_use is None` when `n_valid == 0`.
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_
    - _Design ref: §Zonal-statistics (categorical mode for land use)_
  - [x] 5.2 Write unit tests for the categorical mode
    - Known dominant class returns the expected code/name (12.2).
    - Deliberate tie returns the lowest code (12.2).
    - Unmapped code returns the `unmapped:<code>` marker; zero-valid cell returns null `land_use` (3.5).
    - _Requirements: 12.2, 3.4, 3.5_

- [x] 6. Implement the protected-area overlap
  - [x] 6.1 Implement `_protected_overlap(cells_3577, capad_3577)`
    - `geopandas.sjoin` (predicate `intersects`) in `COMPUTATION_CRS`; return per `cell_id`
      `(protected_area, protected_area_name)` where the name is the `"; "`-joined set of
      distinct CAPAD `NAME` values (duplicates collapsed), `""` when no overlap, and the
      `"(unnamed protected area)"` placeholder for features with missing/null names.
    - Add the CAPAD load with a missing/unreadable halt raising `RuntimeError` naming the path (4.7).
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7_
    - _Design ref: §Components _protected_overlap; §CRS handling; §Error Handling_
  - [x] 6.2 Write unit tests for protected-area overlap
    - Cell intersecting a protected polygon → `protected_area == True`; non-intersecting → `False` (12.6).
    - Unnamed feature yields the placeholder in `protected_area_name`.
    - _Requirements: 12.6, 4.5_

- [x] 7. Implement the confidence flag
  - [x] 7.1 Implement `_confidence_flag(per_raster)`
    - Return `"low"` if for any required raster (elevation, slope, NLUM) `in_coverage` is False
      or `n_nodata >= 50%` of `(n_valid + n_nodata)`; else `"high"`. TRI is excluded from the
      decision. Result is always exactly one of `"high"`/`"low"`.
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 6.4_
    - _Design ref: §Zonal-statistics (confidence rule)_
  - [x] 7.2 Write unit tests for the confidence flag
    - >50% NoData → low; exactly 50% NoData → low (boundary); >50% valid and in-coverage → high (12.4).
    - Out-of-coverage on a required raster → low; all-NoData cell → low (12.5).
    - _Requirements: 12.4, 12.5, 5.2_

- [x] 8. Checkpoint - core logic functions complete
  - Ensure all unit tests for tasks 2–7 pass, ask the user if questions arise.

- [x] 9. Implement CRS-boundary helpers and transformation logging
  - Add explicit reprojection at each boundary reusing `STORAGE_CRS`/`COMPUTATION_CRS`:
    transform cell polygons/centroids from `STORAGE_CRS` to each raster's `src.crs` at the read
    boundary (via `rasterio.warp`), and reproject cells + CAPAD to `COMPUTATION_CRS` for the
    overlap.
    - Halt with `ValueError` naming the source when a raster/vector has no declared CRS or a CRS
      that cannot resolve to an EPSG code (9.4).
    - Accumulate one CRS-transformation entry per reprojection (source dataset id, source CRS,
      target CRS, operation) for the method report; print entries when `verbose`.
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_
  - _Design ref: §CRS handling; §Error Handling_

- [x] 10. Implement the Feature_Table writer and method-report writer
  - [x] 10.1 Implement `_write_feature_table(gdf, path)`
    - Atomic GeoPackage write (`to_file(tmp)` + `os.replace`) in `STORAGE_CRS`, mirroring
      `grid/generate.run()`; leave any prior output intact on failure.
    - _Requirements: 7.1, 7.3, 7.5, 7.6, 9.1_
    - _Design ref: §Components _write_feature_table; §Data Models (schema); §Error Handling_
  - [x] 10.2 Implement `_write_report(report_text, path)` and the report builder
    - `atomic_write_text` stamped with `banner("geographic.features")`; assemble the seven report
      sections from design §Data Models (Method report structure): header/banner, method (per-variable
      statistic + partial-cell rule + NoData rule + mode/tie-break + intersection CRS), coverage
      (inside/outside per raster with `inside+outside==total`; New England REZ + Glen-Innes-only
      coverage-gap text), NoData/zero-valid + unmapped-code occurrences, confidence low/high counts,
      CRS transformations, and runtime + cells processed.
    - _Requirements: 1.4, 2.5, 2.7, 3.4, 5.6, 6.5, 6.6, 9.3, 9.5, 13.2_
    - _Design ref: §Data Models (Method report structure); §Zonal-statistics (report contents)_

- [x] 11. Assemble and wire `run()`
  - Orchestrate the full body: `apply_vsicurl_env()`, `read_grid_cells`, `load_alum_class_table`,
    open rasters once each, per-cell `_zonal_raster_stat` (elevation/slope/tri) with the coverage
    short-circuit, `_categorical_mode` (NLUM), vectorised `_protected_overlap`, `_confidence_flag`,
    assemble the one-row-per-`cell_id` Feature_Table (exact eight-column schema + geometry),
    `_write_feature_table`, `_write_report`.
  - Self-time the body with `time.time()`; populate `runtime_s`; ensure the report runtime equals
    `runtime_s`. Return the summary dict `{feature_table, report, n_cells, runtime_s}` only on
    success; on any halting condition raise (no summary dict) so the orchestrator exits non-zero.
    Raise if any cell cannot be processed before completion (13.4).
  - _Requirements: 1.1, 3.1, 4.1, 5.5, 6.1, 7.2, 7.7, 8.3, 10.2, 10.3, 13.1, 13.2, 13.3, 13.4_
  - _Design ref: §Architecture (flow); §Components (public entry point); §Performance; §Error Handling_

- [x] 12. Implement `validate()` with no-silent-passes checks
  - [x] 12.1 Implement `validate(feature_table_path, grid_path)`
    - Read the written table + grid; produce `{"name","expected","observed","passed"}` dicts for:
      row count == grid cell count (11.1); exact `cell_id` set match, missing+extra both 0 (11.2);
      schema columns exactly the eight columns (11.3); `slope_deg` in [0, 90] or null (11.4);
      `confidence_flag` in {high, low} (11.5). Return `{"checks":[...], "passed":int, "total":int}`.
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_
    - _Design ref: §Testing Strategy (validation checks)_
  - [x] 12.2 Write unit tests for `validate()`
    - Assert a correct table passes all checks and that each injected fault (wrong row count,
      missing cell_id, wrong schema, slope>90, bad confidence value) yields `passed == False`
      with expected/observed populated.
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5_

- [x] 13. Register the stage in the pipeline and orchestrator
  - [x] 13.1 Register in config and orchestrator
    - Add `"geographic.features"` to `pipeline/config.py` `STAGES` immediately after `"grid"` and
      before `"validate"`.
    - Add the `_get_runner` dispatch branch for `geographic.features` in `pipeline/__main__.py`
      (after the `grid` branch); confirm `_build_kwargs` needs no change (verbose-only).
    - Add stage 6 (`features`) to the `pipeline/geographic/__init__.py` docstring with the
      "CONSUMES the grid, registered after `grid`" note.
    - Impact note: `--only geographic` now resolves 6 geographic stages, so
      `tests/test_pipeline_structure.py::TestOrchestratorResolution::test_only_domain` asserting
      `len(stages) == 5` must be updated to 6 in task 13.2.
    - _Requirements: 10.4, 10.5, 10.6, 10.7_
    - _Design ref: §Components (config/orchestrator/subpackage additions); §Stage-ordering resolution_
  - [x] 13.2 Add/extend structural tests
    - Extend `tests/test_pipeline_structure.py`: assert `pipeline.geographic.features.run` is
      importable; assert `"geographic.features"` is in `STAGES` and its index is greater than the
      `"grid"` index; update `test_only_domain` to expect 6 geographic stages.
    - _Requirements: 10.4, 10.7_

- [x] 14. Checkpoint - stage integrated and validated
  - Ensure all tests pass, ask the user if questions arise.

- [x] 15. Implement the 15 property-based tests
  - Create `tests/test_geographic_features.py` (repo-root `tests/`, `Test*` classes) using
    `hypothesis` with `@settings(max_examples=100)`. Generators build small synthetic numpy
    rasters (with a chosen nodata), synthetic cell polygons, and synthetic CAPAD-like polygons —
    no network, no real files. Tag each test
    `# Feature: geographic-environmental-features, Property {n}: {text}`.
  - [x] 15.1 Property 1 — zonal statistic equals mean of valid pixels, NoData excluded
    - **Property 1** — **Validates: Requirements 1.1, 1.2, 1.3, 2.3**
  - [x] 15.2 Property 2 — valid + NoData counts partition the clipped selection
    - **Property 2** — **Validates: Requirements 2.2**
  - [x] 15.3 Property 3 — deterministic pixel selection (idempotence)
    - **Property 3** — **Validates: Requirements 2.1, 2.4**
  - [x] 15.4 Property 4 — identical partial-cell rule across co-registered rasters
    - **Property 4** — **Validates: Requirements 1.5**
  - [x] 15.5 Property 5 — zero valid pixels yield null value and low confidence (incl. land_use)
    - **Property 5** — **Validates: Requirements 1.6, 2.6, 3.5**
  - [x] 15.6 Property 6 — dominant land-use is mapped mode with lowest-code tie-break
    - **Property 6** — **Validates: Requirements 3.1, 3.2, 3.3, 3.4**
  - [x] 15.7 Property 7 — protected flag and names match intersecting CAPAD features
    - **Property 7** — **Validates: Requirements 4.1, 4.2, 4.3, 4.4**
  - [x] 15.8 Property 8 — unnamed intersecting features flag true with placeholder
    - **Property 8** — **Validates: Requirements 4.5**
  - [x] 15.9 Property 9 — confidence flag is the coverage/NoData biconditional over required rasters
    - **Property 9** — **Validates: Requirements 5.1, 5.2, 5.3, 5.4, 6.4**
  - [x] 15.10 Property 10 — out-of-coverage cells have null variables
    - **Property 10** — **Validates: Requirements 6.2**
  - [x] 15.11 Property 11 — coverage bookkeeping partitions the grid per raster
    - **Property 11** — **Validates: Requirements 6.5**
  - [x] 15.12 Property 12 — output cell_id set is a bijection with the grid, values preserved
    - **Property 12** — **Validates: Requirements 6.1, 7.2, 8.2, 8.3**
  - [x] 15.13 Property 13 — Feature_Table has exactly the required schema
    - **Property 13** — **Validates: Requirements 7.1**
  - [x] 15.14 Property 14 — regeneration is deterministic
    - **Property 14** — **Validates: Requirements 7.7**
  - [x] 15.15 Property 15 — resolved stage order places the feature builder after the grid
    - **Property 15** — **Validates: Requirements 10.4, 10.7**
  - _Design ref: §Correctness Properties; §Testing Strategy (PBT)_

- [x] 16. Add the full-grid integration test
  - [x] 16.1 Write the opt-in full-grid integration test
    - In `tests/test_geographic_features.py`, run `run()` against the real grid if present and
      assert `n_cells` equals the grid cell count (13.1), the summary dict contains `runtime_s`
      (13.2, 13.3), and the report runtime line equals `runtime_s`. `pytest.skip` when the grid
      GeoPackage is absent (mirroring `TestGeoPackageRoundtrip` in `tests/test_grid.py`).
    - _Requirements: 13.1, 13.2, 13.3_
    - _Design ref: §Testing Strategy (full-grid runtime)_

- [x] 17. Update documentation
  - [x] 17.1 Update `pipeline/README.md`
    - Add `geographic.features` to the Stage Execution Order block and the ASCII flow between
      `grid` and `validate` (matching resolved runtime order); add the Feature_Table row to the
      Geographic expected-outputs table; add a CLI note that `--only geographic` runs `features`
      against a pre-existing grid.
    - _Requirements: 14.2, 14.3_
    - _Design ref: §Cross-component impact (Documentation)_
  - [x] 17.2 Update `DATA/data-specification/sprint1_data_specification.md`
    - §4.4: add a dataset-detail entry for the Feature_Table naming its per-cell columns
      (including `confidence_flag` and `tri`) and the New England REZ / Glen-Innes-only coverage-gap
      description and the out-of-coverage confidence value; §7: add the sources →
      `geographic.features` stage → suitability/exclusion criterion mapping row; note the addition
      under the §8 change-control "Adding a New Dataset" process; record that Q3 (slope=mean) and
      Q6 (any-intersection protected boolean) are *implemented, not changed* (no §8 frozen-parameter
      edit, no dual spec-§2/README change).
    - _Requirements: 14.1, 14.4, 14.5_
    - _Design ref: §Cross-component impact (Documentation, Frozen decisions)_

- [x] 18. Final checkpoint - ensure all tests pass
  - Ensure all unit, property-based, structural, and (when the grid is present) integration tests
    pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional test sub-tasks and can be skipped for a faster MVP; core
  implementation tasks are never optional.
- Each task references specific granular requirement clauses for traceability, plus a `_Design ref:_`
  pointer where useful.
- Checkpoints (tasks 8, 14, 18) ensure incremental validation.
- Property-based tests (task 15) validate the 15 universal correctness properties from the design;
  unit tests (Req 12) are distributed across tasks 2–7 and 12; validation (Req 11) is task 12.
- No deployment, user-testing, or metrics-gathering tasks are included — every task is code, tests,
  or documentation implied by the design.
- Cross-component impact per the holistic-project-awareness rule: registering the stage changes the
  `--only geographic` resolution count (task 13.2), reuses `grid/config` constants (no constant
  duplication), and requires the README + data-specification updates (task 17) for the feature to
  be complete.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1", "3.1"] },
    { "id": 2, "tasks": ["2.2", "3.2", "4.1"] },
    { "id": 3, "tasks": ["4.2", "5.1", "6.1"] },
    { "id": 4, "tasks": ["5.2", "6.2", "7.1"] },
    { "id": 5, "tasks": ["7.2", "9.1"] },
    { "id": 6, "tasks": ["10.1", "10.2"] },
    { "id": 7, "tasks": ["11.1"] },
    { "id": 8, "tasks": ["12.1", "13.1", "17.1", "17.2"] },
    { "id": 9, "tasks": ["12.2", "13.2", "16.1"] },
    { "id": 10, "tasks": ["15.1", "15.2", "15.3", "15.4", "15.5", "15.6", "15.7", "15.8", "15.9", "15.10", "15.11", "15.12", "15.13", "15.14", "15.15"] }
  ]
}
```

Note: leaf tasks 1.1, 2.1, 3.1, etc. correspond to the sub-tasks above; single-subtask parents
(1, 9, 11) contribute their one leaf (`1.1`, `9.1`, `11.1`). Tasks 4.1, 5.1, 9.1, 10.1, 10.2, 11.1
all write to `features.py` and are sequenced across separate waves to avoid write conflicts; the
property tests (15.x) all write `tests/test_geographic_features.py` but run last as a parallel wave
after the module and its writers exist (they share a file, so if executed by separate agents they
must serialize on that file — they are grouped in one wave as independent test additions).
