# Implementation Plan: Demand Feature Layer (S1-04)

## Overview

This plan implements the `demand.feature` stage (`Demand_Feature_Builder`) as a new module `pipeline/demand/feature.py`, following the design document. The MVP ships with **uniform allocation** (each cell in a NEM region receives `MEAN_DEMAND_MW / N_cells`), per the design's Review decision. The module is structured so `population-weighted` allocation can be added later without changing the `run()` contract or output schema.

The implementation language is **Python**, matching the existing pipeline and the design's code samples. Testing uses **pytest** and **Hypothesis** (property-based tests), consistent with the pipeline stack.

Tasks build incrementally: config → loaders → pure allocation core → assembly/writers → provenance → orchestrator wiring → validation → documentation. Property tests (P1–P11) sit next to the pure core they validate. Test sub-tasks are marked optional with `*`.

## Tasks

- [ ] 1. Add demand feature-builder config
  - [ ] 1.1 Add feature-builder constants to `pipeline/demand/config.py`
    - Add input paths `GRID_PATH` (`DATA/grid/nsw_analysis_grid.gpkg`) and `NEM_REGIONS_PATH` (`DATA/geographic/derived/nem_regions_asgs2021_national.geojson`)
    - Add output constants `FEATURE_TABLE_NAME = "aemo_demand-proxy_2026_nsw.gpkg"`, `FEATURE_TABLE_LAYER = "demand_proxy"`, `METHOD_REPORT_NAME = "demand_feature_method.md"`, `FEATURE_MANIFEST_NAME = "download_manifest.json"`
    - Add `STORAGE_CRS = "EPSG:4326"`, `COMPUTATION_CRS = "EPSG:3577"`, `DEFAULT_ALLOCATION_METHOD = "uniform"`, `CONFIDENCE_LEVELS = ("high", "medium", "low")`, `DEMAND_INPUT_COLUMN = "MEAN_DEMAND_MW"`, `CONSERVATION_TOLERANCE_MW = 1e-6`
    - Add `"feature"` to the demand subpackage `STAGES` list (`["download", "validate", "inspect", "aggregate", "feature"]`)
    - Confirm output filename follows `{source}_{dataset}_{vintage}_{region}.{ext}` with region slug `nsw`
    - _Requirements: 6.4, 8.1, 8.2, 7.1_

- [ ] 2. Implement input loaders with fail-fast validation
  - [ ] 2.1 Create `pipeline/demand/feature.py` module skeleton and loaders
    - Create the module with imports (`geopandas`, `pandas`, `pathlib`, `common.geo`, `demand.config`) and a module docstring describing the stage
    - Implement `load_grid(path) -> GeoDataFrame`: read grid; raise `FileNotFoundError`/`OSError` if missing/unreadable; raise `ValueError` if `cell_id` column absent; raise `ValueError` listing duplicated values if `cell_id` not unique
    - Implement `load_aggregate(path) -> DataFrame`: read CSV; raise `ValueError`/`FileNotFoundError` if missing/unreadable or if `REGIONID` or `MEAN_DEMAND_MW` columns absent
    - Implement `load_nem_regions(path) -> GeoDataFrame`: read polygons; raise `FileNotFoundError`/`OSError` if missing/unreadable; raise `ValueError` naming the source if CRS is absent or cannot be resolved to an EPSG code
    - All loaders validate before any output is written (fail-fast)
    - _Requirements: 7.1, 7.4, 7.5, 7.6, 8.1, 8.3, 8.4, 9.4_

  - [ ]* 2.2 Write unit tests for loader error conditions
    - Assert missing/unreadable grid, missing `cell_id`, duplicate `cell_id` each raise and write no output
    - Assert missing/malformed aggregate (no `REGIONID`/`MEAN_DEMAND_MW`) raises
    - Assert missing/unreadable NEM geometry raises
    - Assert a source with unresolvable CRS raises naming that source (no default assumed)
    - _Requirements: 7.4, 7.5, 7.6, 8.3, 8.4, 9.4_

- [ ] 3. Implement the pure allocation core
  - [ ] 3.1 Implement `assign_source_region(grid_3577, regions_3577) -> Series`
    - Reproject grid and regions to EPSG:3577 (caller passes 3577 frames); centroid point-in-polygon per cell
    - Deterministic tie-break for boundary cells: region containing centroid; else greatest-area-overlap; else lexicographically smallest `REGIONID`
    - Cells intersecting no region get a null source region
    - _Requirements: 3.1, 3.4, 4.1, 4.2_

  - [ ] 3.2 Implement `allocate_demand(source_region, region_demand, method, weights=None) -> Series`
    - Pure function mapping `cell_id -> raw allocated MW`
    - Uniform method: each of the `N_r` cells in region `r` gets `MEAN_DEMAND_MW_r / N_r`
    - Leave a structured branch for `population-weighted` (weights arg) with a `NotImplementedError` guard until confirmed; keep the contract stable
    - Cells with null/unmatched source region get null allocation
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.5_

  - [ ] 3.3 Implement `normalise_proxy(mw_series) -> Series`
    - Normalise raw MW to the closed range `[0, 1]` per region-max; retain raw MW separately for the conservation check
    - Null cells stay null
    - _Requirements: 1.4_

  - [ ] 3.4 Implement `assign_confidence(source_region, has_weight, proxy) -> Series`
    - Return an enum flag from `{high, medium, low}` per documented rules
    - `low` for outside-region / unmatched-region / null-proxy cells; `medium` for tie-break-assigned or weighted-fallback cells; `high` otherwise
    - _Requirements: 5.1, 5.3, 3.5, 4.1_

  - [ ] 3.5 Implement `build_feature_table(...) -> GeoDataFrame`
    - Assemble exactly the columns `cell_id`, `demand_proxy`, `allocation_method`, `source_region`, `confidence_flag`, plus geometry
    - Exactly one row per grid `cell_id`, `cell_id` values reused byte-for-byte from the grid (never re-derived/renumbered/reordered)
    - Geometry carried from grid in EPSG:4326
    - _Requirements: 1.1, 6.1, 6.2, 7.2, 7.3, 6.3, 9.1_

  - [ ]* 3.6 Write property test — strict cell_id keying
    - **Property 1: Strict cell_id keying**
    - **Validates: Requirements 6.2, 7.2, 7.3**

  - [ ]* 3.7 Write property test — one proxy row per cell with exact schema
    - **Property 2: One proxy row per cell with exact schema**
    - **Validates: Requirements 1.1, 6.1**

  - [ ]* 3.8 Write property test — demand conservation
    - **Property 3: Demand conservation** (sum of raw pre-normalisation MW over a region's cells equals `D` within tolerance)
    - **Validates: Requirements 1.2, 12.7**

  - [ ]* 3.9 Write property test — proxy range
    - **Property 4: Proxy range** (every non-null `demand_proxy` in `[0, 1]`)
    - **Validates: Requirements 1.4**

  - [ ]* 3.10 Write property test — source-region correctness
    - **Property 5: Source-region correctness**
    - **Validates: Requirements 3.1, 3.3**

  - [ ]* 3.11 Write property test — outside-region and unmatched cells
    - **Property 6: Outside-region and unmatched cells** (null proxy, null source_region, `low`)
    - **Validates: Requirements 1.5, 3.5, 4.1, 5.3**

  - [ ]* 3.12 Write property test — determinism and boundary tie-break
    - **Property 7: Determinism and boundary tie-break**
    - **Validates: Requirements 2.5, 4.2, 6.7**

  - [ ]* 3.13 Write property test — confidence enumeration
    - **Property 8: Confidence enumeration** (every flag in `{high, medium, low}`, none missing/outside)
    - **Validates: Requirements 5.1, 5.4**

  - [ ]* 3.14 Write property test — counting conservation
    - **Property 9: Counting conservation** (per-region assigned + outside == total; per-flag counts sum to total)
    - **Validates: Requirements 4.5, 5.5**

  - [ ]* 3.15 Write property test — storage CRS invariant
    - **Property 10: Storage CRS invariant** (Feature_Table geometry stored in EPSG:4326)
    - **Validates: Requirements 6.3, 9.1**

  - [ ]* 3.16 Write property test — constant allocation-method label
    - **Property 11: Constant allocation-method label** (every assigned cell's `allocation_method` equals the selected method)
    - **Validates: Requirements 2.1**

  - [ ]* 3.17 Write unit tests for allocation edge cases
    - Hand-computed uniform allocation on a 4-cell synthetic region (exact per-cell MW within tolerance)
    - Conservation on synthetic region (raw MW sum == regional input)
    - Outside-region cell → null/null/low; boundary cell → single region via tie-break
    - Each property test uses a minimum of 100 Hypothesis iterations and is tagged `# Feature: s1-04-build-demand-feature-layer, Property {n}: {text}`
    - _Requirements: 13.1, 13.2, 13.3, 13.4_

- [ ] 4. Checkpoint — pure core verified
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 5. Implement writers and Method_Report
  - [ ] 5.1 Implement `write_feature_table(gdf, path)`
    - Atomic write: write to sibling `*.tmp` GeoPackage (layer `demand_proxy`, EPSG:4326) then `os.replace` onto target
    - On any exception remove the temp file (`finally`) and leave any prior Feature_Table unmodified
    - _Requirements: 6.3, 6.5, 6.6, 9.1_

  - [ ] 5.2 Implement `write_method_report(stats, path)`
    - Banner-stamped Markdown via `common.geo.atomic_write_text`
    - Sections: method name + formula; assumptions; limitations (explicit "proxy, not measured; regional aggregate not per-cell"); data inputs (incl. any weighting dataset); demand-aggregate column used (`MEAN_DEMAND_MW`); proxy scale + unit; NSW1=NSW+ACT convention; edge-case rules; per-region assigned counts, outside-region count, boundary-cell count, no-weighting count with balance identity; confidence value definitions + per-value counts summing to total; one entry per CRS transform
    - _Requirements: 1.3, 2.2, 2.3, 2.4, 2.6, 3.2, 4.4, 4.5, 5.2, 5.5, 9.3, 9.5_

  - [ ]* 5.3 Write unit tests for Method_Report content and output naming
    - Assert banner present, proxy disclaimer, method/formula/assumptions/limitations, NSW1=NSW+ACT, edge-case rules, counts + balance identity, confidence definitions + counts, CRS transform entries, `MEAN_DEMAND_MW` recorded
    - Assert output filename matches `{source}_{dataset}_{vintage}_nsw.{ext}`
    - _Requirements: 1.3, 2.2, 2.3, 2.4, 2.6, 3.2, 3.4, 4.4, 5.2, 5.5, 6.4, 9.3, 9.5_

- [ ] 6. Implement provenance recording
  - [ ] 6.1 Implement `record_provenance(...)`
    - Append a `DATA_PROVENANCE.md` row in the demand domain stating producing stage, source inputs (Demand_Aggregate, NEM_Region_Geometry, any Weighting_Dataset), the Allocation_Method, and that values are proxy indicators; label the Feature_Table as a derived proxy product
    - Write/append a `download_manifest.json` entry for the output (SHA-256, byte count, UTC timestamp) consistent with the manifest convention
    - For the uniform MVP no Weighting_Dataset is used, so no source-register entry is required; leave a documented hook for the weighted path
    - _Requirements: 11.1, 11.2, 11.4_

  - [ ]* 6.2 Write unit tests for provenance output
    - Assert `DATA_PROVENANCE.md` row added, manifest entry has sha256/bytes/utc, derived-proxy label present
    - Assert weighted-path hook would require a source-register entry (custodian, access, native CRS, licence, vintage) before use
    - _Requirements: 11.1, 11.2, 11.3, 11.4_

- [ ] 7. Wire the run() entry point
  - [ ] 7.1 Implement `run(verbose=False, allocation_method="uniform", grid_path=None, aggregate_path=None, nem_regions_path=None, weighting_path=None) -> dict`
    - Orchestrate: load grid/aggregate/regions → reproject to EPSG:3577 and log transforms → `assign_source_region` → `allocate_demand` → `normalise_proxy` + `assign_confidence` (null outside-region cells) → `build_feature_table` → `write_feature_table` → `write_method_report` → `record_provenance`
    - Return a summary dict with `feature_table_path`, `method_report_path`, `allocation_method`, `n_cells`, `n_outside_region`, `per_region_counts`, `confidence_counts`; both paths exist on disk after return
    - Raise (do not return a dict) on any missing/malformed input or write failure so the orchestrator halts non-zero
    - First parameter `verbose` defaults to `False`; return value is a dict
    - _Requirements: 1.5, 3.5, 4.1, 9.2, 9.3, 9.5, 10.1, 10.2, 10.3_

  - [ ]* 7.2 Write unit tests for the run() contract
    - Introspect signature: `verbose=False` first param, returns dict
    - `run()` on synthetic inputs returns a dict whose `feature_table_path` and `method_report_path` exist on disk
    - Forced input/write failures raise and produce no dict and no output
    - _Requirements: 10.1, 10.2, 10.3, 6.6_

- [ ] 8. Register the stage in the orchestrator
  - [ ] 8.1 Register `demand.feature` in `pipeline/config.py`
    - Add `"demand.feature"` to `STAGES` immediately after `"grid"` (and before `"validate"`), so both `grid` and `demand` producers run first
    - Leave `DOMAINS` unchanged (demand already present)
    - _Requirements: 10.4, 10.7_

  - [ ] 8.2 Add dispatch and CLI flag in `pipeline/__main__.py`
    - In `_get_runner`: add `elif stage == "demand.feature": from .demand.feature import run; return run`
    - Add a `--allocation-method` CLI argument (default `uniform`)
    - In `_build_kwargs`: for `"demand.feature"` pass `verbose` and `allocation_method`
    - Update the module docstring stage-order comment to include `demand.feature`
    - _Requirements: 10.5_

  - [ ] 8.3 Update the demand subpackage docstring
    - Extend `pipeline/demand/__init__.py` stage docstring to list `5. feature — per-cell demand proxy on the common grid`
    - _Requirements: 10.6_

  - [ ]* 8.4 Write registration wiring tests
    - Assert `config.STAGES` places `demand.feature` after `grid`
    - Assert `_get_runner('demand.feature')` returns a callable
    - Assert `demand/__init__` docstring lists the feature stage
    - _Requirements: 10.4, 10.5, 10.6, 10.7_

- [ ] 9. Add no-silent-passes validation checks
  - [ ] 9.1 Extend `pipeline/demand/validate.py` with Feature_Table checks
    - One row per grid `cell_id` (report expected count, observed count, pass/fail)
    - Every grid `cell_id` present, no missing/extra (report counts, pass/fail)
    - Columns exactly match required schema (report expected/observed columns, pass/fail)
    - Every non-null `demand_proxy` in `[0, 1]` (report out-of-range count, pass/fail)
    - `source_region` values null or a `REGIONID` in the aggregate (pass/fail)
    - `confidence_flag` only from documented set (pass/fail)
    - Demand conservation per region within tolerance (report expected total, observed total, pass/fail)
    - Each check reports expected vs observed vs explicit pass/fail (no silent passes)
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7_

  - [ ]* 9.2 Write unit tests for validation checks
    - Assert each check emits expected/observed/pass-fail and that a seeded bad Feature_Table fails the relevant check
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7_

- [ ] 10. Checkpoint — stage runs end-to-end under the orchestrator
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 11. Update documentation to match the new stage
  - [ ] 11.1 Update the data specification
    - Update §4 (dataset detail) and §7 (dataset→stage→criterion) to name the Feature_Table output and its columns (`cell_id`, `demand_proxy`, `allocation_method`, `source_region`, `confidence_flag`) and reference the `demand.feature` stage
    - State that `demand_proxy` is a proxy indicator, not measured local demand, and describe the uniform Allocation_Method, its assumptions and limitations consistently with the Method_Report
    - No Weighting_Dataset is used in the uniform MVP, so no §4 weighting-dataset entry or Q4/Q5 change-control is required for this release; note that the population-weighted upgrade would require the §8 change-control process recorded identically in spec §2 and the README
    - _Requirements: 14.1, 14.2, 14.5, 14.6_

  - [ ] 11.2 Update the README stage order and expected outputs
    - Add `demand.feature` to the README stage-order table and CLI docs at the resolved runtime position (after `grid`, before `validate`)
    - Add the Feature_Table (`aemo_demand-proxy_2026_nsw.gpkg`) to the expected-outputs table
    - Ensure the documented stage name/position matches the runtime `config.STAGES` resolution
    - _Requirements: 14.3, 14.4_

## Notes

- Tasks marked with `*` are optional test tasks and can be skipped for a faster MVP; core implementation tasks are never optional.
- Each task references specific requirements clauses for traceability.
- Property tests (P1–P11) sit directly under the pure-core tasks so invariants are caught early; each is a single Hypothesis test running at least 100 iterations.
- The uniform allocation MVP needs no new dataset, conserves demand exactly, and requires no source-register or frozen-decision (Q4/Q5) change control. The population-weighted upgrade is deferred and would add those obligations.
- Checkpoints (tasks 4 and 10) provide incremental validation before wiring and before documentation.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1", "8.1", "8.3"] },
    { "id": 2, "tasks": ["2.2", "3.1", "3.2", "3.3", "3.4"] },
    { "id": 3, "tasks": ["3.5", "3.6", "3.10", "3.11", "3.12", "3.13", "3.16"] },
    { "id": 4, "tasks": ["3.7", "3.8", "3.9", "3.14", "3.15", "3.17", "5.1", "5.2", "6.1"] },
    { "id": 5, "tasks": ["5.3", "6.2", "7.1"] },
    { "id": 6, "tasks": ["7.2", "8.2", "9.1", "11.1", "11.2"] },
    { "id": 7, "tasks": ["8.4", "9.2"] }
  ]
}
```
