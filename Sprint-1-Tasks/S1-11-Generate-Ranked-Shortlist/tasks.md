# Implementation Plan: Generate Ranked Shortlist (S1-11)

## Overview

This plan implements the `shortlist` stage (`Shortlist_Module`) as a new subpackage `pipeline/shortlist/`, following the design document. The stage consumes the S1-10 Scored_Table (`DATA/scoring/optmining_suitability-score_2026_nsw.gpkg` + CSV sidecar, one row per `cell_id` across the 47,311 NSW cells) as its sole score input, selects the top-N Eligible_Cells (non-null `suitability_score` **and** non-null `rank`) by their existing ascending `rank`, joins each shortlisted cell's `centroid_lat`/`centroid_lon` from the Analysis_Grid on `cell_id` in EPSG:4326, and writes the Sprint 1 headline output: a Shortlist_CSV and a Shortlist_GeoJSON carrying the same `cell_id` set in the same rank order, plus a Summary_Report of descriptive statistics. This stage is a **filtering and formatting** step, not a modelling step — it performs no re-scoring and no re-ranking, and never re-derives the grid.

The implementation language is **Python**, matching the existing pipeline and the design's code samples. The selection and formatting core (`select.py`, `summary.py`) is a set of **pure functions** over in-memory frames — DataFrame in, DataFrame/stats out, no filesystem access — so it is independently testable and replaceable without touching the data-loading layer. Selection is by the existing integer `rank` (not by re-sorting on `suitability_score`), so the shortlist ordering is identical to S1-10 through ties and gaps; the Top_N-over-count case is clamped with no padding, and the zero-eligible case emits headered, disclaimer-carrying empty outputs. CRS is explicit at every boundary: `centroid_lat`/`centroid_lon` are read from the grid in EPSG:4326 and carried unchanged, and the GeoJSON geometry is written in EPSG:4326 with the CRS stated explicitly (no reprojection occurs in this stage). Every output and its metadata carry the Preliminary_Disclaimer and the ~5 km Analysis_Resolution statement. Testing uses **pytest** and **Hypothesis** (property-based tests).

Tasks build incrementally: shortlist config + Top_N resolver → Scored_Table loader → pure selection → coordinate join → assembly/schema → pure summary statistics → timestamped naming → atomic CSV/GeoJSON writers → disclaimer/metadata/provenance/report → `run()` wiring → orchestrator registration → no-silent-passes validation → full-NSW-grid integration + smoke tests → documentation. The 18 correctness properties sit next to the pure core they validate, each a single Hypothesis test running at least 100 iterations and tagged `# Feature: s1-11-generate-ranked-shortlist, Property {n}: {text}`. Test sub-tasks are marked optional with `*`.

> **Cross-spec dependency.** The `scoring` stage (S1-10) that produces the Scored_Table is introduced by the sibling S1-10 spec and is not yet in the live `config.STAGES`. This stage registers `shortlist` immediately **after** `scoring` in `STAGES`; the scoring producer must be scheduled before this consumer.

## Tasks

- [ ] 1. Add shortlist config and the Top_N resolver
  - [ ] 1.1 Create `pipeline/shortlist/config.py` and implement `resolve_top_n`
    - Add shortlist constants: `DEFAULT_TOP_N = 20` (3.1); default `SCORED_PATH` (`DATA/scoring/optmining_suitability-score_2026_nsw.gpkg`), default `GRID_PATH` (`DATA/grid/nsw_analysis_grid.gpkg`); the output directory `SHORTLIST_DIR` (`DATA/shortlist/`) and its `metadata/` subdir; `STORAGE_CRS = "EPSG:4326"`; `CONFIDENCE_LEVELS = ("high", "low")`; the documented `SHORTLIST_COLUMNS = ("rank", "cell_id", "suitability_score", "confidence", "centroid_lat", "centroid_lon")` order (4.1) and `OPTIONAL_CONTEXT_COLUMNS = ("rez", "nearby_wind_farm")` (4.3); the Preliminary_Disclaimer text and the Analysis_Resolution statement (`~5 km (0.05 degree) analysis grid cell`); the default geometry choice `"centroid"`
    - Implement `resolve_top_n(cli_value, config_value) -> int`: effective Top_N precedence CLI value > pipeline-config value > `DEFAULT_TOP_N` (3.1, 3.3); halt (raise) BEFORE any output if the resolved value is not a positive integer (zero, negative, non-integer), identifying the invalid value (3.5)
    - Confirm output filenames follow the `{source}_{dataset}_{year/vintage}_{region}.{ext}` convention with region slug `nsw`
    - _Requirements: 3.1, 3.3, 3.5, 4.1, 4.3, 7.3_

  - [ ]* 1.2 Write property test — invalid Top_N is rejected before any write
    - **Property 4: Invalid Top_N is rejected before any write** (non-positive-integer Top_N halts before writing any output and returns an error identifying the invalid value, leaving no partial output on disk)
    - **Validates: Requirements 3.5**

- [ ] 2. Implement the Scored_Table loader with fail-fast validation
  - [ ] 2.1 Implement `load_scored_table` in `pipeline/shortlist/load.py`
    - Add `REQUIRED_SCORE_COLUMNS = ("cell_id", "suitability_score", "rank", "confidence")`
    - Implement `load_scored_table(path) -> GeoDataFrame`: read the S1-10 Scored_Table as the SOLE per-cell score input (1.1); reuse `cell_id` byte-for-byte, never re-derive/renumber/reformat/reorder (1.2); never re-score or re-rank — use `suitability_score` and `rank` exactly as produced by S1-10 (1.3)
    - Halt BEFORE any output on: missing/unreadable file, naming the path (1.4); any of `REQUIRED_SCORE_COLUMNS` absent, identifying the missing column (1.5)
    - This loader is the only file-reading path for score data; it hands a fully in-memory frame to the pure selection core
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

  - [ ]* 2.2 Write unit tests for loader error conditions
    - Assert missing/unreadable Scored_Table and each absent required column (`cell_id`/`suitability_score`/`rank`/`confidence`) raise (naming the fault) and write no output (1.4, 1.5)
    - _Requirements: 1.4, 1.5_

- [ ] 3. Implement the pure selection core
  - [ ] 3.1 Implement `eligible_cells` and `select_shortlist` in `pipeline/shortlist/select.py`
    - Implement `eligible_cells(scored) -> DataFrame`: rows with BOTH non-null `suitability_score` AND non-null `rank` (Eligible_Cell) (2.2)
    - Implement `select_shortlist(scored, top_n) -> DataFrame`: PURE — DataFrame in, DataFrame out, no file I/O; filter to Eligible_Cells (2.2), order ascending by `rank` so rank 1 appears first (2.1, 2.3), take the first `min(top_n, n_eligible)` rows; preserve the S1-10 rank ordering exactly through ties and gaps, never re-assigning ranks (2.4); never include an Excluded_Cell and never pad (3.4)
    - `top_n > n_eligible` → include every Eligible_Cell, no padding (3.4); `n_eligible == 0` → return an empty frame with the documented columns so downstream still emits headered outputs (3.6)
    - Expose the eligible count and the included count for the Summary_Report (2.5)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.4, 3.6_

  - [ ]* 3.2 Write property test — top-N selection is eligible-only and rank-ordered
    - **Property 1: Top-N selection is eligible-only and rank-ordered** (Shortlist == the `min(Top_N, n_eligible)` Eligible_Cells with the smallest `rank`; no Excluded_Cell; rank 1 first)
    - **Validates: Requirements 2.1, 2.2, 2.3, 12.2**

  - [ ]* 3.3 Write property test — ordering is consistent with the S1-10 rank ordering
    - **Property 2: Ordering is consistent with the S1-10 rank ordering** (smaller `rank` earlier; upstream ordering preserved through ties and gaps; no rank re-assignment)
    - **Validates: Requirements 2.3, 2.4, 12.3**

  - [ ]* 3.4 Write property test — Top_N exceeding the eligible count includes all eligible cells without padding
    - **Property 3: Top_N exceeding the eligible count includes all eligible cells without padding** (every Eligible_Cell once, no Excluded_Cell/fabricated row; row count == eligible count, never exceeding it)
    - **Validates: Requirements 3.4**

  - [ ]* 3.5 Write property test — zero eligible cells yields a well-formed empty shortlist
    - **Property 5: Zero eligible cells yields a well-formed empty shortlist** (zero Eligible_Cells → empty selection with the documented columns; downstream still emits headered CSV + GeoJSON + disclaimer, no crash)
    - **Validates: Requirements 3.6**

  - [ ]* 3.6 Write property test — row count never exceeds the effective Top_N
    - **Property 8: Row count never exceeds the effective Top_N** (Shortlist row count `<=` effective Top_N for any Scored_Table and positive-integer Top_N)
    - **Validates: Requirements 12.1**

- [ ] 4. Implement the coordinate join
  - [ ] 4.1 Implement `load_grid` and `join_coordinates` in `pipeline/shortlist/coords.py`
    - Implement `load_grid(path) -> GeoDataFrame`: read the Analysis_Grid; halt BEFORE any output if missing/unreadable, naming the grid path (4.4)
    - Implement `join_coordinates(shortlist, grid) -> DataFrame`: left-join `centroid_lat`/`centroid_lon` from the grid on `cell_id` in EPSG:4326 (4.2); if ANY shortlisted `cell_id` has no matching grid row, HALT before any write and raise identifying the unmatched `cell_id` — never emit a fabricated or null coordinate (4.5); carry `suitability_score`, `confidence`, and `rank` straight from the Scored_Table without recomputation (4.6)
    - _Requirements: 4.2, 4.4, 4.5, 4.6_

  - [ ]* 4.2 Write property test — coordinate-join correctness and halt on unmatched cell_id
    - **Property 6: Coordinate-join correctness and halt on unmatched cell_id** (joined lat/lon == grid values for the `cell_id` in EPSG:4326; an unmatched shortlisted `cell_id` halts before any write, naming it, with no fabricated/null coordinate)
    - **Validates: Requirements 4.2, 4.5, 12.4**

  - [ ]* 4.3 Write property test — scores, confidence, and rank are carried through unchanged
    - **Property 7: Scores, confidence, and rank are carried through unchanged** (each shortlisted cell's `suitability_score`, `confidence`, and `rank` equal the Scored_Table values for that `cell_id`; no recomputation, no re-ranking)
    - **Validates: Requirements 1.3, 4.6**

- [ ] 5. Implement shortlist assembly and schema
  - [ ] 5.1 Implement `assemble_shortlist` in `pipeline/shortlist/assemble.py`
    - Assemble the Shortlist frame with `SHORTLIST_COLUMNS` in the documented order (`rank`, `cell_id`, `suitability_score`, `confidence`, `centroid_lat`, `centroid_lon`) (4.1)
    - Where an optional context column (`rez`, `nearby_wind_farm`) is available from an upstream layer, append it as a named, documented column and record its definition and source for the Summary_Report (4.3)
    - Only Eligible_Cells appear; no Excluded_Cell and no fabricated/padded row (2.2, 3.4)
    - _Requirements: 4.1, 4.3_

  - [ ]* 5.2 Write property test — output schema and documented column order
    - **Property 11: Output schema and documented column order** (Shortlist_CSV columns and GeoJSON feature properties contain at least `rank`, `cell_id`, `suitability_score`, `confidence`, `centroid_lat`, `centroid_lon`, in that documented order)
    - **Validates: Requirements 4.1**

- [ ] 6. Implement the pure summary statistics
  - [ ] 6.1 Implement `SummaryStats` and `compute_summary` in `pipeline/shortlist/summary.py`
    - Define the frozen `SummaryStats` dataclass: `score_dist` (`min`/`max`/`mean`/`std`), `lat_range`, `lon_range`, `rez_represented`, `confidence_dist` (`{"high": n, "low": n}`), `n_cells`, `n_eligible`, `n_scored`
    - Implement `compute_summary(scored, shortlist) -> SummaryStats`: PURE — no file I/O; score distribution (`min`/`max`/`mean`/`std` of `suitability_score`) computed over the ELIGIBLE_Cell population only, excluding Excluded_Cell values (6.1, 6.6); latitude and longitude ranges of the shortlisted `centroid_lat`/`centroid_lon` (6.2); represented REZs among the top sites WHERE available (6.3); confidence distribution counting shortlisted cells at each `confidence` value (`high`, `low`) (6.4); total, eligible, and scored cell counts for the run (6.5)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6_

  - [ ]* 6.2 Write property test — score distribution is computed over eligible cells only
    - **Property 12: Score distribution is computed over eligible cells only** (reported `min`/`max`/`mean`/`std` == eligible-only recomputation; unchanged when Excluded_Cell values are perturbed)
    - **Validates: Requirements 6.1, 6.6**

  - [ ]* 6.3 Write property test — confidence distribution matches the shortlisted cells
    - **Property 13: Confidence distribution matches the shortlisted cells** (per-`confidence` counts == shortlisted counts; the two counts sum to the shortlist row count)
    - **Validates: Requirements 6.4**

- [ ] 7. Checkpoint — pure core verified
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Implement timestamped, versioned filenames
  - [ ] 8.1 Implement `run_timestamp` and `resolve_output_paths` in `pipeline/shortlist/naming.py`
    - Implement `run_timestamp() -> str`: a single UTC Run_Timestamp for the run, derived once via `common.geo.utc_now()` (7.2)
    - Implement `resolve_output_paths(out_dir, ts) -> tuple[Path, Path]`: timestamped/versioned names `sprint1_shortlist_<UTCdate>.csv` and `sprint1_shortlist_<UTCdate>.geojson` (7.1); use the SAME Run_Timestamp in both filenames and the metadata (7.2); region slug `nsw` wherever the `{source}_{dataset}_{year/vintage}_{region}.{ext}` convention applies (7.3); if a resolved name already exists, append a finer-grained UTC time component by a documented deterministic rule rather than silently overwriting, and surface the collision outcome for the Summary_Report (7.4)
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [ ] 9. Implement the CSV and GeoJSON output writers
  - [ ] 9.1 Implement `write_csv` and `write_geojson` in `pipeline/shortlist/write.py`
    - Implement `write_csv(shortlist, path)`: atomic write via `common.geo` (tmp + `os.replace`) of the Shortlist_CSV with `SHORTLIST_COLUMNS` in documented order (5.1, 5.6); emit headers even for an empty shortlist (3.6); on failure leave any pre-existing output unmodified and raise (5.7)
    - Implement `write_geojson(shortlist, path, geometry)`: atomic write of the Shortlist_GeoJSON, one feature per shortlisted cell, `SHORTLIST_COLUMNS` carried as feature properties (5.2), geometry in EPSG:4326 stated explicitly (5.3), geometry per the documented choice — `"centroid"` Point (default) or cell `"polygon"` — noted for the Summary_Report (5.4); carry the Preliminary_Disclaimer and Analysis_Resolution in file-level metadata/properties (8.3); on failure leave any pre-existing output unmodified and raise (5.7)
    - Both writers draw from the same in-memory Shortlist frame, so the CSV and GeoJSON contain the same `cell_id` set in the same rank order (5.5)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 8.3_

  - [ ]* 9.2 Write property test — CSV and GeoJSON carry the same cell_id set in the same order
    - **Property 9: CSV and GeoJSON carry the same cell_id set in the same order** (the ordered `cell_id` sequence in the CSV equals, element-for-element, the ordered `cell_id` sequence in the GeoJSON)
    - **Validates: Requirements 5.5, 12.5**

  - [ ]* 9.3 Write property test — GeoJSON geometry is stored in EPSG:4326
    - **Property 10: GeoJSON geometry is stored in EPSG:4326** (written GeoJSON geometry CRS == EPSG:4326, stated explicitly rather than assumed)
    - **Validates: Requirements 5.3**

  - [ ]* 9.4 Write unit tests for writers, naming, and atomicity
    - Atomic write leaves prior output intact on forced write failure (5.7); output filenames match `sprint1_shortlist_<UTCdate>.{csv,geojson}` with region slug `nsw` (7.1, 7.3); the same Run_Timestamp appears in both filenames (7.2); an empty shortlist still emits headered CSV + GeoJSON (3.6); the name-collision rule appends a finer-grained UTC component and records the outcome (7.4); the documented geometry choice is stated for the report (5.4)
    - _Requirements: 3.6, 5.4, 5.7, 7.1, 7.2, 7.3, 7.4_

- [ ] 10. Implement the disclaimer, metadata, provenance, and Summary_Report
  - [ ] 10.1 Implement `write_summary_report` and `write_metadata_sidecar` in `pipeline/shortlist/report.py`
    - Implement `write_summary_report(...)`: write `DATA/shortlist/metadata/shortlist_summary.md` via `common.geo.atomic_write_text`, stamped with `common.geo.banner("shortlist")` (11.4); record the Summary_Statistics (6), the effective Top_N and the eligible-vs-included counts (2.5), the geometry choice (5.4), any optional context-column definitions (4.3), the collision outcome if any (7.4), the Preliminary_Disclaimer (8.1), and the Analysis_Resolution statement (8.2)
    - Implement `write_metadata_sidecar(...)`: write a JSON sidecar via `common.geo.atomic_write_json` recording `pipeline_version` and UTC `run_timestamp` (9.1), `effective_top_n` and `n_shortlisted` (9.2), `scored_table_id` (Scored_Table path + `common.geo.sha256_file` digest, so the exact scores are traceable) (9.3), `geometry` (5.4), the Preliminary_Disclaimer and Analysis_Resolution statement (8.1, 8.2, 8.4); record Pipeline_Version and Run_Timestamp identically across the Summary_Report and sidecar (9.4)
    - NEVER emit any output that omits BOTH the disclaimer and the resolution statement: the GeoJSON carries them in file-level metadata/properties (8.3); the CSV's disclaimer travels via the Summary_Report and sidecar (8.4, 8.5)
    - _Requirements: 2.5, 4.3, 5.4, 7.4, 8.1, 8.2, 8.3, 8.4, 8.5, 9.1, 9.2, 9.3, 9.4, 11.4_

  - [ ] 10.2 Implement `record_provenance` in `pipeline/shortlist/report.py`
    - Mirror `integration.merge.record_provenance`: append a `DATA/shortlist/DATA_PROVENANCE.md` row labelling each shortlist output a **derived product**, listing the Scored_Table and Analysis_Grid inputs, the effective Top_N, and the UTC Run_Timestamp (11.1, 11.2, 11.3)
    - Write a `shortlist_manifest.json` (SHA-256, byte count, UTC Run_Timestamp, generation params — the Scored_Table and Analysis_Grid inputs and the effective Top_N) and a `source_register` entry (11.1, 11.3)
    - _Requirements: 11.1, 11.2, 11.3_

  - [ ]* 10.3 Write property test — every output carries the disclaimer and resolution statement
    - **Property 14: Every output carries the disclaimer and resolution statement** (no output omits both; GeoJSON carries them in file-level metadata/properties; the CSV's disclaimer travels via the Summary_Report and metadata sidecar)
    - **Validates: Requirements 8.1, 8.2, 8.3, 8.4, 8.5, 12.6**

  - [ ]* 10.4 Write property test — Run_Timestamp is reused across filenames and metadata
    - **Property 15: Run_Timestamp is reused across filenames and metadata** (the single UTC Run_Timestamp appears in both the resolved filenames and the metadata; Pipeline_Version and Run_Timestamp recorded identically across the Summary_Report and the sidecar)
    - **Validates: Requirements 7.2, 9.4**

  - [ ]* 10.5 Write unit tests for report, metadata, and provenance content
    - Summary_Report is banner-stamped and records the Summary_Statistics, effective Top_N + eligible/included counts, geometry choice, optional-context definitions, collision outcome, disclaimer, and resolution (2.5, 4.3, 5.4, 7.4, 8.1, 8.2, 11.4); metadata sidecar carries `pipeline_version`, `run_timestamp`, `effective_top_n`, `n_shortlisted`, `scored_table_id` (path + sha256), geometry, disclaimer, and resolution (9.1, 9.2, 9.3, 9.4); provenance: `DATA_PROVENANCE.md` derived-product row present, `shortlist_manifest.json` has sha256/bytes/utc + generation params, `source_register` entry added (11.1, 11.2, 11.3)
    - _Requirements: 2.5, 4.3, 5.4, 7.4, 8.1, 8.2, 9.1, 9.2, 9.3, 9.4, 11.1, 11.2, 11.3, 11.4_

- [ ] 11. Wire the run() entry point
  - [ ] 11.1 Implement `run(verbose=False, top_n=None, scored_path=None, grid_path=None, geometry="centroid") -> dict` in `pipeline/shortlist/run.py`
    - Orchestrate: `resolve_top_n` → `load_scored_table` → `eligible_cells`/`select_shortlist` (pure) → `load_grid` → `join_coordinates` → `assemble_shortlist` → `compute_summary` (pure) → `run_timestamp` + `resolve_output_paths` → `write_csv` + `write_geojson` → `write_summary_report` + `write_metadata_sidecar` → `record_provenance` → validation
    - First parameter `verbose` defaults to `False`; return a summary dict with `shortlist_csv_path`, `shortlist_geojson_path`, `summary_report_path`, `effective_top_n`, `n_shortlisted`, `n_eligible`, `n_scored`, `n_cells`, `run_timestamp`, `runtime_seconds`; the three path values exist on disk after return (10.1, 10.2); reuse the single UTC Run_Timestamp across filenames and metadata (7.2)
    - Raise (do not return a dict) on missing/unreadable Scored_Table or grid, absent required column, non-positive-integer Top_N, an unmatched shortlisted `cell_id`, or a write failure, so the orchestrator halts with a non-zero exit status (10.3)
    - _Requirements: 10.1, 10.2, 10.3_

  - [ ]* 11.2 Write property + unit tests for the run() contract
    - **Property 16: Regeneration is deterministic (idempotent)** — two runs on a fixed Scored_Table, grid, and Top_N produce identical selections, orderings, and Summary_Statistics (ignoring the intentionally varying Run_Timestamp). **Validates: Requirements 1.3, 2.4**
    - **Property 17: Successful run returns existing output paths** — returned `shortlist_csv_path`/`shortlist_geojson_path`/`summary_report_path` exist on disk. **Validates: Requirements 10.2**
    - Unit: signature introspection (`verbose=False` first param, returns dict); a forced fatal condition raises, returns no dict, and writes no output (10.1, 10.3)
    - _Requirements: 1.3, 2.4, 10.1, 10.2, 10.3_

- [ ] 12. Register the stage in the orchestrator
  - [ ] 12.1 Register `shortlist` in `pipeline/config.py`
    - Insert `"shortlist"` into `STAGES` immediately after `"scoring"` and before `"validate"`, so the Scored_Table producer is scheduled before this consumer (10.4, 10.8)
    - Add `"shortlist"` to `DOMAINS` so `--only shortlist` / `--skip shortlist` resolve (10.7)
    - _Requirements: 10.4, 10.7, 10.8_

  - [ ] 12.2 Add dispatch and the CLI flag in `pipeline/__main__.py`
    - In `_get_runner`: add `elif stage == "shortlist": from .shortlist.run import run; return run`
    - Add a `--shortlist-top-n` CLI argument (default 20); in `_build_kwargs`, for `"shortlist"` pass `verbose` and `top_n` (3.2, 10.5)
    - Update the module docstring stage-order comment to include `shortlist` after `scoring`, before `validate`
    - _Requirements: 3.2, 10.5_

  - [ ] 12.3 Add the shortlist subpackage docstring
    - Author `pipeline/shortlist/__init__.py` with a docstring describing the shortlist stage and its position after `scoring` in the pipeline stage sequence (10.6)
    - _Requirements: 10.6_

  - [ ]* 12.4 Write registration and ordering wiring tests
    - **Property 18: Resolved execution order places shortlist after scoring** — for any resolved stage list containing both, `scoring` index < `shortlist` index. **Validates: Requirements 10.4, 10.8**
    - Assert `_get_runner('shortlist')` returns a callable; `"shortlist"` is in `config.STAGES` (after `scoring`, before `validate`) and `config.DOMAINS`; the `--shortlist-top-n` flag exists (default 20) and is forwarded as `top_n` by `_build_kwargs`; the `shortlist/__init__` docstring describes the stage
    - _Requirements: 3.2, 10.4, 10.5, 10.6, 10.7, 10.8_

- [ ] 13. Add no-silent-passes validation checks
  - [ ] 13.1 Implement `validate(...)` in `pipeline/shortlist/validate.py` and cross-domain checks in `pipeline/validate.py`
    - Shortlist row count ≤ effective Top_N: report effective Top_N, observed row count, pass/fail (12.1)
    - Every shortlisted cell is an Eligible_Cell (non-null `suitability_score` AND `rank`): report violator count, pass/fail (12.2)
    - Ordering is ascending `rank` consistent with the S1-10 ordering: report ordering-violation count, pass/fail (12.3)
    - Every shortlisted cell has non-null `centroid_lat`/`centroid_lon`: report missing-coordinate count, pass/fail (12.4)
    - The Shortlist_CSV and Shortlist_GeoJSON contain the same `cell_id` set in the same order: pass/fail (12.5)
    - Each output and its metadata carry the Preliminary_Disclaimer and the Analysis_Resolution statement: pass/fail (12.6)
    - Each check reports expected vs observed vs explicit pass/fail (no silent passes); place the cross-domain checks (shortlisted `cell_id` set ⊆ Scored_Table/grid `cell_id` set, ordering consistent with S1-10, CSV/GeoJSON equality, disclaimer/resolution presence) in the cross-domain `pipeline/validate.py` tier (12.7)
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7_

  - [ ]* 13.2 Write unit tests for validation checks
    - Assert each check emits expected/observed/pass-fail and that a seeded bad shortlist (row count over Top_N, an Excluded_Cell included, out-of-order `rank`, a missing coordinate, CSV/GeoJSON `cell_id`-set or order mismatch, an output missing the disclaimer/resolution) fails the relevant check
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7_

- [ ] 14. Checkpoint — stage runs end-to-end under the orchestrator
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 15. Full-NSW-grid integration and smoke tests
  - [ ]* 15.1 Write full-NSW-grid integration test
    - Run over the full 47,311-cell Scored_Table; assert the shortlist has `min(Top_N, n_eligible)` rows in ascending `rank` order, every shortlisted `cell_id` resolves to a grid coordinate, the total/eligible/scored counts match the Scored_Table, `runtime_seconds` is recorded, and a second run reproduces the selection and statistics (regenerable derived product, ignoring the intentional Run_Timestamp variation)
    - _Requirements: 6.5, 10.2_

  - [ ]* 15.2 Write orchestrator + documentation-consistency smoke tests
    - Assert `shortlist` is in `config.STAGES` immediately after `scoring` and before `validate`, is in `config.DOMAINS`, `--shortlist-top-n` exists (default 20) and is forwarded by `_build_kwargs` as `top_n`, `_get_runner("shortlist")` returns the stage `run`, and the subpackage `__init__` docstring describes the stage and its position
    - Assert the README stage-order table/name for `shortlist` matches the resolved runtime stage configuration, including the `--shortlist-top-n` flag (14.2, 14.3)
    - _Requirements: 10.4, 10.5, 10.6, 10.7, 10.8, 14.2, 14.3_

  - [ ]* 15.3 Write unit tests for selection, formatting, and summary logic (Requirement 13)
    - 13.1 Top-N selection on a small synthetic Scored_Table: selected cells are the Top_N Eligible_Cells in ascending `rank` order and Excluded_Cells are omitted
    - 13.2 Top_N-exceeds-eligible-count: the Shortlist includes every Eligible_Cell without padding
    - 13.3 Zero-eligible-cells: an empty Shortlist is produced with headers and the Preliminary_Disclaimer rather than raising an unhandled error
    - 13.4 Coordinate join: `centroid_lat`/`centroid_lon` are joined from the Analysis_Grid on `cell_id` for every shortlisted cell
    - 13.5 Output schema and column order: the Shortlist contains the documented Requirement 4 columns in the documented order
    - 13.6 Summary_Statistics: the score distribution (`min`/`max`/`mean`/`std`), the geographic spread, and the confidence distribution equal hand-computed expected values within a documented numeric tolerance for the synthetic input
    - 13.7 CSV/GeoJSON consistency: the two exports contain the same shortlisted `cell_id` values in the same order for the synthetic input
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7_

- [ ] 16. Update documentation to match the new stage
  - [ ] 16.1 Update the data specification and README
    - Update the data specification §4 (dataset detail) and §7 (dataset→stage→criterion mapping) to name the shortlist outputs (`sprint1_shortlist_<UTCdate>.csv` / `.geojson`), their columns, and reference the `shortlist` stage that produces them, via the §8 change-control process (14.1)
    - Add `shortlist` to the README stage-order table and CLI docs at the resolved runtime position (after `scoring`, before `validate`), matching `config.STAGES` exactly, including the `--shortlist-top-n` flag and the timestamped-output naming; add the shortlist outputs to the expected-outputs table (14.2, 14.3)
    - State in both the data specification and the README that the shortlist is a preliminary screening output at the stated Analysis_Resolution (~5 km) and is not a site approval (14.4); note that this stage does not change any frozen decision (Q1–Q7) — Top_N is a runtime CLI/config value, not a frozen parameter — so no §8 change-control of a frozen decision is required for this release (14.5)
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5_

## Notes

- Tasks marked with `*` are optional test tasks and can be skipped for a faster MVP; core implementation tasks are never optional.
- Each task references specific requirements clauses for traceability.
- Property tests (P1–P18) sit directly under the pure core / wiring they validate so invariants are caught early; each is a single Hypothesis test running at least 100 iterations and tagged `# Feature: s1-11-generate-ranked-shortlist, Property {n}: {text}`.
- The selection and summary core (`select.py`, `summary.py`) is a set of pure functions over in-memory frames with no file I/O, so it is independently testable and replaceable without changing the data-loading layer.
- This stage is filtering and formatting only: it performs no re-scoring and no re-ranking, selects by the existing integer `rank` so the ordering is identical to S1-10 through ties and gaps, and never re-derives the grid.
- Halt conditions (missing/unreadable Scored_Table or grid, absent required column, non-positive-integer Top_N, unmatched shortlisted `cell_id`, write failure) occur before any output is written; the Top_N-over-count and zero-eligible cases are handled (non-fatal) and emit honest, headered, disclaimer-carrying outputs.
- CRS is explicit: `centroid_lat`/`centroid_lon` are read and carried in EPSG:4326, and the GeoJSON geometry is written in EPSG:4326 with the CRS stated explicitly. No reprojection occurs in this stage.
- Every output and its metadata carry the Preliminary_Disclaimer and the ~5 km Analysis_Resolution statement; a single UTC Run_Timestamp is reused across filenames and metadata.
- Checkpoints (tasks 7 and 14) provide incremental validation before the writers and before documentation.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1", "3.1", "8.1", "12.1", "12.3"] },
    { "id": 2, "tasks": ["2.2", "3.2", "3.3", "3.4", "3.5", "3.6", "4.1"] },
    { "id": 3, "tasks": ["4.2", "4.3", "5.1", "6.1"] },
    { "id": 4, "tasks": ["5.2", "6.2", "6.3", "9.1"] },
    { "id": 5, "tasks": ["9.2", "9.3", "9.4", "10.1", "10.2"] },
    { "id": 6, "tasks": ["10.3", "10.4", "10.5", "11.1", "12.2"] },
    { "id": 7, "tasks": ["11.2", "12.4", "13.1"] },
    { "id": 8, "tasks": ["13.2", "15.1", "15.2", "15.3", "16.1"] }
  ]
}
```
