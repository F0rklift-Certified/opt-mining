# Implementation Plan: Validation and Sanity Check (S1-12)

## Overview

This plan implements the `sanity` stage (`Sanity_Module`) as a new terminal subpackage `pipeline/sanity/`, following the design document. The stage consumes the Sprint 1 outputs as **read-only** inputs — the ranked Shortlist (S1-11, resolved as the latest timestamped file under `DATA/shortlist/`), the per-cell Scored_Table (S1-10, `DATA/scoring/optmining_suitability-score_2026_nsw.gpkg`), the Integrated_Feature_Table (S1-08, `DATA/integration/optmining_integrated-features_2026_nsw.gpkg`), the Geoscience Australia Wind_Generators dataset, and the Analysis_Grid — and produces a human-readable Validation_Report (`outputs/sprint1_validation_report.md`) plus an optional machine-readable Results_Sidecar. It runs four plausibility checks (Known Wind Farm Comparison, Exclusion Validation, Feature-Value Spot-Checks, Score-Distribution Plausibility) that ask whether the pipeline's outputs make sense against known reality. It is a **reality-check reporting** step — not a modelling step and not the structural validation step — and is deliberately distinct from the cross-domain `pipeline/validate.py`.

The implementation language is **Python**, matching the existing pipeline and the design's code samples. The four check computations (`checks.py`), the CRS-containment helper (`geo.py`), the deterministic spot-cell selection, and the issue collection (`issues.py`) are **pure functions** over in-memory frames — frames in, structured results out, no filesystem access — so they are independently testable without touching disk and re-runnable against updated pipeline outputs. The stage is **read-only on all inputs** and **never** re-scores, re-ranks, re-weights, or re-tunes the model; surprising results are documented honestly and, where systematic, logged as Sprint2_Issues. The design is a **manual+automated hybrid**: the automated checks (point-in-cell location, Percentile computation, exclusion assertions, distribution statistics, correlation) are scripted with explicit expected-versus-observed pass/fail, while the human-judgement items (independent verification of a spot-checked feature value against its source) are surfaced as report fields left blank for a reviewer. CRS is explicit at every boundary: storage is EPSG:4326 and every containment operation is performed in one explicit, logged CRS, EPSG:3577. Testing uses **pytest** and **Hypothesis** (property-based tests).

Tasks build incrementally: sanity config + input resolver/loader → CRS containment helper → Check 1 (Known Wind Farms) → Check 2 (Exclusion Validation) → Check 3 (Feature-Value Spot-Checks) → Check 4 (Score-Distribution Plausibility) → anomaly/Sprint-2 issues collector → report renderer/writer/sidecar → provenance → no-silent-passes reporter → `run()` wiring → orchestrator registration → full-NSW-grid integration + smoke tests → documentation. The 16 correctness properties sit next to the pure core they validate, each a single Hypothesis test running at least 100 iterations and tagged `# Feature: s1-12-validation-sanity-check, Property {n}: {text}`. Test sub-tasks are marked optional with `*`.

> **Cross-spec dependency.** The `scoring` stage (S1-10) and the `shortlist` stage (S1-11) that produce two of this stage's inputs are introduced by the sibling S1-10/S1-11 specs and are not yet in the live `config.STAGES`. This stage registers `sanity` as the **terminal** entry immediately **after** `shortlist` in `STAGES`; the shortlist producer must be scheduled before this consumer.

## Tasks

- [ ] 1. Add sanity config and the input resolver/loader
  - [ ] 1.1 Create `pipeline/sanity/config.py` with the stage constants
    - Add the default input paths: `SCORED_PATH` (`DATA/scoring/optmining_suitability-score_2026_nsw.gpkg`), `SHORTLIST_DIR` (`DATA/shortlist/`), `INTEGRATED_PATH` (`DATA/integration/optmining_integrated-features_2026_nsw.gpkg`), `WIND_GENERATORS_PATH` (`DATA/infrastructure/generators/ga_wind_generators_2026_nsw.geojson`), and `GRID_PATH` (`DATA/grid/nsw_analysis_grid.gpkg`)
    - Add the required-column tuples `REQUIRED_SCORE_COLUMNS = ("cell_id", "suitability_score", "rank")`, `REQUIRED_INTEGRATED_COLUMNS = ("cell_id", "wind_speed", "slope_deg", "dist_transmission_km", "protected", "eligible")`, `REQUIRED_GRID_COLUMNS = ("cell_id", "centroid_lat", "centroid_lon", "geometry")`, and `REQUIRED_WIND_GENERATOR_ATTR = "name"`
    - Add the check constants: the `LANDMARKS` table (Sydney CBD / Newcastle / Wollongong urban, Blue Mountains NP / Kosciuszko NP parks, each a documented EPSG:4326 coordinate + kind), `SPOT_CHECK_MIN = 5` / `SPOT_CHECK_MAX = 10` / `SPOT_CHECK_DEFAULT = 8`, `UPPER_QUARTILE_PERCENTILE = 75.0`, `POOR_SCORE_PERCENTILE = 25.0`, `CLUSTER_EPSILON` and `CLUSTER_FRACTION_THRESHOLD`, the `VERIFY_SOURCES` map (per-feature verification source), `CONTAINMENT_CRS = "EPSG:3577"`, `STORAGE_CRS = "EPSG:4326"`, the fixed report path `outputs/sprint1_validation_report.md`, and the Preliminary_Disclaimer + Analysis_Resolution (~5 km / 0.05 degree) text
    - Confirm the optional Results_Sidecar name follows `{source}_{dataset}_{year/vintage}_{region}.{ext}` with region slug `nsw` (`optmining_validation-results_2026_nsw.json`)
    - _Requirements: 1.6, 2.5, 2.6, 3.1, 3.2, 4.1, 5.2, 7.1, 7.5, 7.6, 10.4_

  - [ ] 1.2 Implement `resolve_shortlist` and `load_inputs` in `pipeline/sanity/load.py`
    - Implement `resolve_shortlist(shortlist_dir) -> Path`: resolve the Shortlist by a documented deterministic rule — the file with the most recent UTC Run_Timestamp in its name under `DATA/shortlist/`; halt (raise) BEFORE any output if no shortlist file is present, and record the resolved path for the report metadata (1.6, 1.4)
    - Implement `load_inputs(paths) -> LoadedFrames`: read the Scored_Table, resolved Shortlist, Integrated_Feature_Table, Wind_Generators, and Analysis_Grid as the stage inputs, all opened READ-ONLY so no input is ever mutated (1.1, 8.1); reuse `cell_id` byte-for-byte and never re-derive/renumber/reformat/reorder (1.2); never re-score or re-rank (1.3)
    - Halt BEFORE any output on: any missing/unreadable input, naming the path (1.4); any required column absent, naming the column and the input it was expected in (1.5); any source with no resolvable CRS, naming the source and never assuming a projection (2.2, 3.5)
    - Split loaded scores into Eligible_Cells (non-null `suitability_score` AND non-null `rank`) and Excluded_Cells; the loader is the only file-reading path and hands fully in-memory frames to the pure checks
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 8.1_

  - [ ]* 1.3 Write unit tests for the resolver and loader error conditions
    - Assert `resolve_shortlist` picks the most recent timestamped file and raises with no output when the directory has no shortlist (1.6, 1.4)
    - Assert missing/unreadable input, an absent required column (naming the column and input), and an unresolvable-CRS source each raise before any write (1.4, 1.5, 2.2, 3.5)
    - Assert loaded `cell_id` values are unchanged (byte-for-byte) and no score/rank is recomputed (1.2, 1.3)
    - _Requirements: 1.2, 1.3, 1.4, 1.5, 1.6, 2.2, 3.5_

- [ ] 2. Implement the CRS containment helper
  - [ ] 2.1 Implement `CrsTransform` and `locate_points_to_cells` in `pipeline/sanity/geo.py`
    - Define the frozen `CrsTransform(source, target, purpose)` dataclass used to record each `EPSG:4326 → EPSG:3577` transform for the report's transform log
    - Implement `locate_points_to_cells(points, grid, containment_crs, transform_log) -> DataFrame`: reproject BOTH points and grid to the single explicit `containment_crs` (EPSG:3577), append the transform to `transform_log` (2.2, 3.5), and perform a point-in-polygon spatial join (`predicate="within"`) (2.1)
    - Return one row per input point with its Containing_Cell `cell_id`, or a `null` `cell_id` when the point lies in NO grid cell (offshore / out-of-extent), reported honestly rather than dropped (2.7); never convert CRS silently
    - _Requirements: 2.1, 2.2, 2.7, 3.5_

  - [ ]* 2.2 Write property test — point-in-cell location is correct in the metric CRS
    - **Property 1: Point-in-cell location is correct in the metric CRS** (each interior point located to exactly its containing cell in EPSG:3577; an out-of-extent point gets a null cell; no point is ever dropped)
    - **Validates: Requirements 2.1, 2.2, 2.7**

- [ ] 3. Implement Check 1 — Known Wind Farm Comparison
  - [ ] 3.1 Implement `percentile_over_eligible` and `check_known_wind_farms` in `pipeline/sanity/checks.py`
    - Implement `percentile_over_eligible(score, eligible_scores) -> float`: `100 × (count of eligible scores <= score) / n_eligible`, computed over the Eligible_Cell population ONLY, excluding Excluded_Cell values (2.4)
    - Implement `check_known_wind_farms(wind_generators, grid, scored, containment_crs, transform_log) -> WindFarmCheckResult`: PURE. For each Known_Wind_Farm locate it to its Containing_Cell via `locate_points_to_cells` (EPSG:3577, logged) (2.1, 2.2); look up that cell's `suitability_score`, `rank`, and Percentile over the eligible population (2.3, 2.4); build a results-table row (`Wind Farm | Cell ID | Score | Rank | Percentile | Notes`) (2.3)
    - Report the count and proportion of farms in the Upper_Quartile (Percentile >= `UPPER_QUARTILE_PERCENTILE`) and state the expectation that most operational farms fall there (2.5)
    - Record HONESTLY in the Notes field, with an investigation note distinguishing a likely data issue from a legitimate model result, any farm whose cell scores below `POOR_SCORE_PERCENTILE`, whose cell is an Excluded_Cell (null score), or whose point falls in NO grid cell; the model is NEVER adjusted and the farm is NEVER silently dropped (2.6, 2.7, 6.5, 8.3)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 6.5, 8.3_

  - [ ]* 3.2 Write property test — percentile is computed over the eligible population only
    - **Property 2: Percentile is computed over the eligible population only** (Percentile == `100 × (count of eligible scores <= value) / n_eligible`; unchanged when Excluded_Cell values are perturbed)
    - **Validates: Requirements 2.3, 2.4**

  - [ ]* 3.3 Write property test — upper-quartile count is correct
    - **Property 3: Upper-quartile count is correct** (reported Upper_Quartile count == number of farms with Percentile >= 75; reported fraction == count / n_known_farms)
    - **Validates: Requirements 2.5**

- [ ] 4. Implement Check 2 — Exclusion Validation
  - [ ] 4.1 Implement `check_exclusions` in `pipeline/sanity/checks.py`
    - Implement `check_exclusions(landmarks, grid, scored, integrated, containment_crs, transform_log) -> ExclusionCheckResult`: PURE. For each documented `LANDMARKS` entry (Sydney CBD / Newcastle / Wollongong urban, Blue Mountains NP / Kosciuszko NP parks) locate it to its cell in EPSG:3577 via the documented coordinate rule, logging the CRS (3.5); assert the cell is an Excluded_Cell (ineligible / null `suitability_score`) or absent from the grid (3.1, 3.2)
    - Additionally assert NO offshore/ocean cell exists in the Analysis_Grid (3.3)
    - For each assertion record the expected outcome, the observed outcome, and an explicit pass/fail, NEVER a pass without an observed value (3.4)
    - Report a failing assertion HONESTLY as an Anomaly with an investigation note, and NEVER suppress the failure to make the check pass (3.6, 8.3)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 8.3_

  - [ ]* 4.2 Write property test — exclusion checks report expected-versus-observed honestly
    - **Property 4: Exclusion checks report expected-versus-observed with honest out-of-grid/ineligible handling** (pass iff the located cell is observed ineligible/absent; a fail is recorded honestly, never a pass without an observed value)
    - **Validates: Requirements 3.1, 3.2, 3.3, 3.4**

- [ ] 5. Implement Check 3 — Feature-Value Spot-Checks
  - [ ] 5.1 Implement `select_spot_cells` and `check_spot_values` in `pipeline/sanity/checks.py`
    - Implement `select_spot_cells(eligible, n) -> DataFrame`: PURE, DETERMINISTIC. Require `SPOT_CHECK_MIN <= n <= SPOT_CHECK_MAX` (else the caller halts, 4.5); order eligible cells ascending by `suitability_score` with a `cell_id` tie-break, then pick `n` evenly-spaced quantile positions spanning the range so the selection ALWAYS includes the top cell, the bottom cell, and `(n-2)` interior quantiles (4.2); the rule is a fixed function of `(sorted eligible scores, n)` so repeated runs pick the SAME cells (12.3)
    - Implement `check_spot_values(spot_cells, integrated) -> SpotCheckResult`: PURE. For each selected cell record `cell_id`, `centroid_lat`/`centroid_lon` (EPSG:4326), `wind_speed`, `slope_deg` (or elevation), `dist_transmission_km`, and the `protected` flag, plus the `VERIFY_SOURCES` entry for each value and an empty `discrepancy` field for the human reviewer (4.3, 4.4); a cell missing a required feature value records it as `MISSING` with a note rather than fabricating one (4.6)
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.6, 12.3_

  - [ ]* 5.2 Write property test — spot-cell selection is deterministic and spans the score range
    - **Property 5: Spot-cell selection is deterministic and spans the score range** (returns exactly `n` distinct eligible cells incl. top + bottom + interior spanning the range; identical set on repeat over identical inputs)
    - **Validates: Requirements 4.1, 4.2**

- [ ] 6. Implement Check 4 — Score-Distribution Plausibility
  - [ ] 6.1 Implement `check_distribution` in `pipeline/sanity/checks.py`
    - Implement `check_distribution(eligible) -> DistributionCheckResult`: PURE, over the Eligible_Cell population ONLY (5.1). Report `min`, `max`, `mean`, `std`, and quartiles (Q1 / median / Q3) of `suitability_score` (5.1)
    - Compute the degenerate-clustering flag: the fraction of eligible scores within `CLUSTER_EPSILON` of 0 or 1; degenerate if that fraction exceeds `CLUSTER_FRACTION_THRESHOLD`; report as an explicit pass/fail with the observed fraction (5.2)
    - Report the geographic diversity of the top-scoring cells (latitude range, longitude range, and REZs represented WHERE available) so a single-region concentration is visible (5.3)
    - Compute the `wind_speed`-versus-`suitability_score` correlation (Spearman default or Pearson) over eligible cells with a documented POSITIVE sign expectation; report (NOT enforce) it, with an honest note if the sign is unexpected (5.4)
    - Report a degenerate distribution or a non-positive correlation HONESTLY as an Anomaly with an investigation note; NEVER adjust the model to alter the distribution (5.5, 8.2, 8.3)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 8.2, 8.3_

  - [ ]* 6.2 Write property test — distribution statistics are computed over eligible cells only
    - **Property 7: Distribution statistics are computed over eligible cells only** (reported min/max/mean/std/quartiles == eligible-only recomputation; unchanged when Excluded_Cell values are perturbed)
    - **Validates: Requirements 5.1**

  - [ ]* 6.3 Write property test — degenerate-clustering flag is correct
    - **Property 8: Degenerate-clustering flag is correct** (flagged degenerate iff the fraction within epsilon of 0/1 exceeds the threshold; the fraction is reported as the observed value alongside the pass/fail)
    - **Validates: Requirements 5.2**

  - [ ]* 6.4 Write property test — wind-versus-score correlation is reported honestly, not enforced
    - **Property 9: Wind-versus-score correlation is reported honestly, not enforced** (correlation + sign reported against the positive expectation; a non-positive result records an honest Anomaly note rather than failing the run or altering the distribution)
    - **Validates: Requirements 5.4, 5.5**

- [ ] 7. Checkpoint — pure check core verified
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 8. Implement the anomaly and Sprint-2 issues collector
  - [ ] 8.1 Implement `Anomaly` and `collect_issues` in `pipeline/sanity/issues.py`
    - Define the frozen `Anomaly(check, description, kind, investigation_note)` dataclass, where `kind` is `"data_issue"` or `"model_result"` (6.4, 6.5)
    - Implement `collect_issues(*check_results) -> list[Anomaly]`: gather every Anomaly recorded by the four checks into the report's "Issues for Sprint 2" section, each recording its description, the check that surfaced it, and whether it is a suspected data issue or a legitimate model result (6.1, 6.3, 6.4, 6.5); Anomalies are NEVER suppressed and NEVER used to auto-adjust the model (6.2, 8.2)
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 8.2_

  - [ ]* 8.2 Write property test — surprising results are recorded honestly as Sprint-2 issues
    - **Property 12: Surprising results are recorded honestly as Sprint-2 issues** (a surprising/failing result is recorded with a data-issue/model-result investigation note, not suppressed, and where systematic logged as a Sprint2_Issue rather than fixed ad hoc)
    - **Validates: Requirements 6.1, 6.3, 6.4, 6.5**

- [ ] 9. Implement the no-silent-passes reporter
  - [ ] 9.1 Implement the `CheckOutcome` contract in `pipeline/sanity/checks.py`
    - Define `CheckOutcome(expected, observed, passed)` and have every automated check emit its outcome through it, so no check records a `pass` without a recorded observed value (11.1)
    - Ensure Check 1 reports the Upper_Quartile count against the expectation as an explicit pass/fail with the observed count (11.2); each Check 2 assertion reports observed eligibility/grid-membership as pass/fail (11.3); Check 4 reports the clustering and wind-correlation checks as pass/fail with observed statistics (11.4)
    - Ensure a failing check is surfaced and never overwritten or hidden (11.5); do NOT duplicate the cross-domain structural checks that remain in `pipeline/validate.py` (11.6)
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6_

  - [ ]* 9.2 Write property test — every automated check reports an explicit pass/fail with an observed value
    - **Property 11: Every automated check reports an explicit pass/fail with an observed value** (each outcome carries expected + observed + explicit pass/fail; no pass without an observed value; a failing outcome is surfaced, never hidden)
    - **Validates: Requirements 3.4, 11.1, 11.2, 11.3, 11.4, 11.5**

- [ ] 10. Implement the report renderer, writer, and sidecar
  - [ ] 10.1 Implement `render_report`, `write_report`, and `write_sidecar` in `pipeline/sanity/report.py`
    - Implement `render_report(results, meta) -> str`: render the Markdown Validation_Report banner-stamped via `common.geo.banner("sanity")`; sections in order — header/run-metadata (run date, Pipeline_Version, total cell count, eligible cell count) + disclaimers, then `1. Known Wind Farm Comparison`, `2. Exclusion Validation`, `3. Feature Value Spot-Checks`, `4. Score Distribution`, `5. Issues for Sprint 2`, `6. Conclusion` (7.1, 7.2, 7.3); the Conclusion states an overall trustworthy-for-preliminary-screening assessment based on the recorded results (7.4)
    - Include the Preliminary_Disclaimer (a plausibility sanity check, NOT a formal accuracy assessment and NOT a site approval) and the Analysis_Resolution (~5 km / 0.05 degree) with its limitations wherever results are presented (7.5, 7.6); render the transform-log line verbatim from `transform_log`
    - Implement `write_report(text, path=REPORT_PATH)`: atomic write via `common.geo.atomic_write_text` (tmp + `os.replace`); on failure leave any prior report unmodified and raise (7.7, 7.9)
    - Implement `write_sidecar(results, path)`: atomic write of the machine-readable Results_Sidecar (including the Known_Wind_Farm_Comparison table) via `common.geo.atomic_write_json`, labelled a derived product; on failure leave any prior sidecar unmodified and raise (7.8, 7.9, 10.2)
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 10.2_

  - [ ]* 10.2 Write property test — the report contains all required sections and disclaimers
    - **Property 13: The report contains all required sections and disclaimers** (rendered report contains the six sections, the run metadata, the Preliminary_Disclaimer, and the Analysis_Resolution statement)
    - **Validates: Requirements 7.2, 7.3, 7.5, 7.6**

  - [ ]* 10.3 Write unit tests for the renderer, writer, and atomicity
    - Assert the rendered report is banner-stamped and contains the six sections + metadata + disclaimers + resolution + transform-log line (7.2, 7.3, 7.5, 7.6, 7.7)
    - Assert a forced write failure leaves any pre-existing report/sidecar unmodified and raises (7.9); the sidecar is atomic JSON labelled a derived product (7.8, 10.2)
    - _Requirements: 7.2, 7.3, 7.5, 7.6, 7.7, 7.8, 7.9, 10.2_

- [ ] 11. Implement provenance for the report and sidecar
  - [ ] 11.1 Implement `record_provenance` in `pipeline/sanity/report.py`
    - Mirror `infrastructure/features.py` provenance: append a `DATA_PROVENANCE.md` row labelling the Validation_Report (and, where written, the Results_Sidecar) a **derived product**, listing all five inputs (Shortlist, Scored_Table, Integrated_Feature_Table, Wind_Generators, Analysis_Grid) and the UTC Run_Timestamp (10.1, 10.2, 10.3)
    - Write a `sanity_manifest.json` (SHA-256, byte count, UTC Run_Timestamp, generation params listing all five inputs) via `common.geo.atomic_write_json` and a `source_register` entry (10.1, 10.3)
    - Name the optional sidecar `optmining_validation-results_2026_nsw.json` per the `{source}_{dataset}_{year/vintage}_{region}.{ext}` convention (region slug `nsw`); the report retains its fixed `outputs/sprint1_validation_report.md` path with the naming rule documented (10.4)
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

  - [ ]* 11.2 Write unit tests for provenance content
    - Assert the `DATA_PROVENANCE.md` derived-product row is present and lists all five inputs + UTC Run_Timestamp; `sanity_manifest.json` has sha256/bytes/utc + the five inputs; a `source_register` entry is added; the sidecar name matches the `nsw` convention (10.1, 10.2, 10.3, 10.4)
    - _Requirements: 10.1, 10.2, 10.3, 10.4_

- [ ] 12. Wire the run() entry point
  - [ ] 12.1 Implement `run(...)` in `pipeline/sanity/run.py`
    - Implement `run(verbose=False, spot_cells=8, wind_generators_path=None, shortlist_dir=None, scored_path=None, integrated_path=None, grid_path=None, containment_crs="EPSG:3577", write_sidecar=True) -> dict` with `verbose` as the first parameter defaulting to `False` (9.1)
    - Validate `spot_cells` is within `[5, 10]` and raise before any output if not, naming the invalid count (4.5); orchestrate: `resolve_shortlist` + `load_inputs` → split eligible/excluded → `check_known_wind_farms` / `check_exclusions` / `select_spot_cells` + `check_spot_values` / `check_distribution` → `collect_issues` → `render_report` + `write_report` (+ `write_sidecar` when enabled) → `record_provenance`
    - Return a summary dict with `report_path`, `sidecar_path`, `resolved_shortlist_path`, `n_cells`, `n_eligible`, `n_known_farms`, `n_farms_upper_quartile`, `n_exclusion_checks_passed`, `n_exclusion_checks_failed`, `n_spot_cells`, `check1_pass`, `check2_pass`, `check3_recorded`, `check4_pass`, `run_timestamp`, and `runtime_seconds`; `report_path` (and any `sidecar_path`) exist on disk after return (9.2)
    - Raise (do NOT return a dict) on missing/unreadable input, absent required column, invalid `spot_cells`, an unresolvable CRS, or a write failure, so the orchestrator halts with a non-zero exit status (1.4, 1.5, 4.5, 7.9, 9.3); NEVER write to any input (8.1)
    - _Requirements: 1.4, 1.5, 4.5, 7.9, 8.1, 9.1, 9.2, 9.3, 12.4_

  - [ ]* 12.2 Write property + unit tests for the run() contract
    - **Property 10: Inputs are read-only and the model is never adjusted** — after a run over any inputs and any check outcome, the byte content of every input is unchanged, no score/rank is recomputed, and no criteria weight/normalisation bound/exclusion rule/scoring parameter is altered. **Validates: Requirements 1.3, 8.1, 8.2, 8.3**
    - **Property 14: Regeneration is deterministic (idempotent)** — two runs over fixed inputs produce identical structured results (located cells, percentiles, exclusion pass/fail, selected spot cells, distribution statistics). **Validates: Requirements 12.3**
    - **Property 15: Successful run returns an existing report path** — the returned `report_path` (and any `sidecar_path`) exist on disk after `run()` returns. **Validates: Requirements 9.2**
    - **Property 6: Invalid spot-cell count is rejected before any write** — a `spot_cells` outside `[5, 10]` halts before writing any output, returns an error naming the invalid count, and leaves no partial output on disk. **Validates: Requirements 4.5**
    - Unit: signature introspection (`verbose=False` first param, returns dict); a forced fatal condition raises, returns no dict, and writes no output; supplied `wind_generators_path`/`spot_cells` override the defaults (9.1, 9.3, 12.4)
    - _Requirements: 1.3, 4.5, 8.1, 8.2, 8.3, 9.1, 9.2, 9.3, 12.3, 12.4_

- [ ] 13. Register the stage in the orchestrator
  - [ ] 13.1 Register `sanity` in `pipeline/config.py`
    - Append `"sanity"` to `STAGES` as the terminal entry, after `"shortlist"`, so the shortlist producer is scheduled before this consumer and `sanity` runs last (9.4, 9.9)
    - Add `"sanity"` to `DOMAINS` so `--only sanity` / `--skip sanity` resolve; the name is deliberately distinct from the structural `validate` step (9.5)
    - _Requirements: 9.4, 9.5, 9.9_

  - [ ] 13.2 Add dispatch and CLI flags in `pipeline/__main__.py`
    - In `_get_runner`: add `elif stage == "sanity": from .sanity.run import run; return run`
    - Add `--sanity-spot-cells` (default 8, validated to the inclusive range 5–10) and `--wind-generators` (path override) CLI arguments; in `_build_kwargs`, for `"sanity"` pass `verbose`, `spot_cells`, and `wind_generators_path` (9.6, 9.7)
    - Update the module docstring stage-order comment to include `sanity` as the terminal stage after `shortlist`
    - _Requirements: 9.6, 9.7_

  - [ ] 13.3 Add the sanity subpackage docstring
    - Author `pipeline/sanity/__init__.py` with a docstring describing the sanity-check stage, its distinction from the structural `validate` step, and its terminal position in the pipeline stage sequence (9.8)
    - _Requirements: 9.8_

  - [ ]* 13.4 Write registration and ordering wiring tests
    - **Property 16: Resolved execution order places sanity after shortlist as the terminal stage** — for any resolved stage list containing both, `shortlist` index < `sanity` index and `sanity` is the last entry. **Validates: Requirements 9.4, 9.9**
    - Assert `_get_runner('sanity')` returns a callable; `"sanity"` is the terminal entry in `config.STAGES` (after `shortlist`) and is in `config.DOMAINS`; `--sanity-spot-cells` (default 8, validated 5–10) and `--wind-generators` exist and are forwarded by `_build_kwargs` as `spot_cells`/`wind_generators_path`; the `sanity/__init__` docstring describes the stage, its distinction from `validate`, and its terminal position
    - _Requirements: 9.4, 9.5, 9.6, 9.7, 9.8, 9.9_

- [ ] 14. Checkpoint — stage runs end-to-end under the orchestrator
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 15. Full-NSW-grid integration and smoke tests
  - [ ]* 15.1 Write full-NSW-grid integration test
    - Run over the real 47,311-cell Scored_Table, the latest Shortlist, the integrated table, the GA wind generators, and the grid; assert the report is written to `outputs/sprint1_validation_report.md` with all six sections, the Known_Wind_Farm_Comparison table has one row per generator, and the Upper_Quartile count + distribution statistics are recorded with explicit pass/fail
    - Assert no input file is modified by comparing pre/post SHA-256 of all five inputs, and that a second run reproduces the automated results (deterministic derived product)
    - _Requirements: 1.1, 2.5, 5.1, 8.1, 9.2, 12.3_

  - [ ]* 15.2 Write orchestrator + documentation-consistency smoke tests
    - Assert `sanity` is the terminal entry in `config.STAGES` (after `shortlist`), is in `config.DOMAINS`, `--sanity-spot-cells` (default 8, 5–10) and `--wind-generators` exist and are forwarded by `_build_kwargs` as `spot_cells`/`wind_generators_path`, `_get_runner("sanity")` returns the stage `run`, and the subpackage `__init__` docstring describes the stage, its distinction from `validate`, and its terminal position
    - Assert the README stage-order table/name for `sanity` matches the resolved runtime configuration (including the CLI flags) and that the README/spec state the stage is a preliminary-screening plausibility sanity check distinct from `pipeline/validate.py` (14.2, 14.3, 14.5)
    - _Requirements: 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 14.2, 14.3, 14.5_

  - [ ]* 15.3 Write unit tests for the automated check logic with known inputs and outputs (Requirement 13)
    - 13.1 Point-in-cell location on a small synthetic grid and synthetic wind-farm points: each point is located to the correct Containing_Cell in the documented CRS (EPSG:3577)
    - 13.2 Percentile computation over a small synthetic Eligible_Cell population: computed percentiles equal hand-computed values within a documented tolerance, and Excluded_Cell values are omitted
    - 13.3 Exclusion assertions: a synthetic urban/protected/offshore location is correctly detected as excluded, and a failing assertion is reported as a fail with the observed value
    - 13.4 Distribution statistics: min, max, mean, std, quartiles, the degenerate-clustering flag, and the wind-resource correlation equal hand-computed values within a documented tolerance
    - 13.5 Spot_Check_Cells selection: the selected count lies within `[5, 10]` and the selected cells span the top, middle, and bottom of the synthetic score range
    - 13.6 Determinism: the automated check computations return identical results for two runs over identical inputs
    - Additional example/error-condition tests: latest-Shortlist resolution (1.6), out-of-grid wind-farm honest note (2.7), missing-feature-value `MISSING` note (4.6), the transform-log line content (2.2, 3.5)
    - _Requirements: 1.6, 2.7, 4.6, 13.1, 13.2, 13.3, 13.4, 13.5, 13.6_

- [ ] 16. Update documentation to match the new stage
  - [ ] 16.1 Update the data specification and README
    - Update the data specification §4 (dataset detail) and §7 (dataset→stage→criterion mapping) to name the Validation_Report (`outputs/sprint1_validation_report.md`) and any Results_Sidecar and reference the `sanity` stage that produces them, via the §8 change-control process (14.1)
    - Add `sanity` to the README stage-order table and CLI docs at the resolved terminal runtime position (after `shortlist`), matching `config.STAGES` exactly, including the `--sanity-spot-cells` and `--wind-generators` flags; add the Validation_Report to the expected-outputs table (14.2, 14.3)
    - State in both the data specification and the README that the validation is a preliminary-screening plausibility sanity check at the stated Analysis_Resolution (~5 km) and is not a formal accuracy assessment and not a site approval (14.4), and that this `sanity` stage is distinct from the structural `pipeline/validate.py` step (14.5)
    - Note that this stage does not change any frozen decision (Q1–Q7) — the Spot_Check_Cells count and Wind_Generators path are runtime CLI/config values, not frozen parameters — so no §8 change-control of a frozen decision is required for this release (14.6)
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6_

## Notes

- Tasks marked with `*` are optional test tasks and can be skipped for a faster MVP; core implementation tasks are never optional.
- Each task references specific requirements clauses for traceability.
- Property tests (P1–P16) sit directly under the pure core / wiring they validate so invariants are caught early; each is a single Hypothesis test running at least 100 iterations and tagged `# Feature: s1-12-validation-sanity-check, Property {n}: {text}`.
- The four check computations (`checks.py`), the CRS-containment helper (`geo.py`), and the issue collector (`issues.py`) are pure functions over in-memory frames with no file I/O, so they are independently testable and re-runnable against updated pipeline outputs.
- This stage is a reality-check reporting step, not a modelling step: it treats all inputs as read-only, never re-scores/re-ranks/re-derives the grid, and NEVER adjusts the model to make a check pass. It is distinct from the structural `pipeline/validate.py` tier and does not duplicate it.
- Halt conditions (missing/unreadable input, absent required column, unresolvable CRS, invalid `spot_cells`, write failure) occur before any output is written; handled conditions (out-of-grid wind farm, poorly-scoring farm, failing exclusion assertion, missing feature value, degenerate/non-positive distribution) are reported honestly and continue, recorded as Anomalies / Sprint2_Issues rather than crashing, suppressed, or used to auto-adjust the model.
- CRS is explicit: storage is EPSG:4326 and every point-in-polygon containment operation (Check 1 wind farms, Check 2 landmarks) is performed in one explicit, logged containment CRS (EPSG:3577).
- Checkpoints (tasks 7 and 14) provide incremental validation before the writers and before documentation.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "2.1"] },
    { "id": 2, "tasks": ["1.3", "2.2", "3.1", "4.1", "5.1", "6.1"] },
    { "id": 3, "tasks": ["3.2", "3.3", "4.2", "5.2", "6.2", "6.3", "6.4", "8.1", "9.1"] },
    { "id": 4, "tasks": ["8.2", "9.2", "10.1", "13.1", "13.3"] },
    { "id": 5, "tasks": ["10.2", "10.3", "11.1"] },
    { "id": 6, "tasks": ["11.2", "12.1", "13.2"] },
    { "id": 7, "tasks": ["12.2", "13.4"] },
    { "id": 8, "tasks": ["15.1", "15.2", "15.3", "16.1"] }
  ]
}
```
