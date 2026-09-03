# Implementation Plan: Baseline Suitability Model (S1-10)

## Overview

This plan implements the `scoring` stage (`Scoring_Module`) as a new subpackage `pipeline/scoring/`, following the design document. The stage consumes the S1-08 integrated NSW feature table (`DATA/integration/optmining_integrated-features_2026_nsw.gpkg`, one row per `cell_id` across the 47,311 NSW cells) and produces a per-cell `suitability_score` using a transparent, deterministic weighted MCDA function: for every eligible cell it normalises each configured criterion to `[0, 1]` from the eligible population, applies the user-configured weights to yield a score in `[0, 1]`, records a per-criterion contribution, assigns a dense descending `rank` with a documented tie-break, carries through the S1-09 composite `confidence`, and nulls out every excluded cell. The resulting Scored_Table feeds S1-11.

The implementation language is **Python**, matching the existing pipeline and the design's code samples. Criteria weights are **user inputs loaded from YAML** at runtime (`pipeline/scoring/scoring_weights.yaml`, or `--scoring-weights`), never hard-coded constants. The pure `Scoring_Function` (`score.py`) receives an in-memory DataFrame plus a `WeightsConfig` and returns a scored DataFrame with no file I/O, so it is independently replaceable without touching the data-loading layer. Normalisation uses directional min-max over the eligible population only; a constant criterion (`min == max`) is filled with a documented constant rather than dividing by zero. CRS is explicit at every boundary — geometry is stored in **EPSG:4326**. Testing uses **pytest** and **Hypothesis** (property-based tests).

Tasks build incrementally: scoring config + shipped default weights → weights loader/validator → integrated-table loader → normalisation → pure Scoring_Function → ranking → confidence carry-through/nulling → output writer → method report + provenance → `run()` wiring → orchestrator registration → no-silent-passes validation → full-NSW-grid integration + smoke tests → documentation. The 16 correctness properties sit next to the pure core they validate, each a single Hypothesis test running at least 100 iterations and tagged `# Feature: s1-10-baseline-suitability-model, Property {n}: {text}`. Test sub-tasks are marked optional with `*`.

## Tasks

- [x] 1. Add scoring config and shipped default weights
  - [x] 1.1 Create `pipeline/scoring/config.py` and the default `pipeline/scoring/scoring_weights.yaml`
    - Add scoring constants to `pipeline/scoring/config.py`: default `INTEGRATED_PATH` (`DATA/integration/optmining_integrated-features_2026_nsw.gpkg`), default `WEIGHTS_PATH` (`pipeline/scoring/scoring_weights.yaml`), the output constants `SCORED_TABLE_NAME = "optmining_suitability-score_2026_nsw.gpkg"`, `SCORED_TABLE_LAYER`, `METHOD_REPORT_NAME = "scoring_method.md"` (written under a `SCORING_META_DIR`), `STORAGE_CRS = "EPSG:4326"`, `CONFIDENCE_LEVELS = ("high", "low")`, `RECONCILE_TOLERANCE = 1e-9`, `CONSTANT_CRITERION_VALUE = 1.0`, the required integrated-table columns (`cell_id`, `eligible`, composite `confidence`), and the `contrib_{feature}` contribution-column naming pattern
    - Confirm the output filename follows `{source}_{dataset}_{year/vintage}_{region}.{ext}` with region slug `nsw`
    - Author the shipped default `scoring_weights.yaml` with `confidence_discount: false`, a `confidence_factors` map (`high: 1.0`, `low: 0.8`), and a criterion entry (feature, weight, direction, non-empty rationale) for `wind_speed` (`higher_is_better`), `dist_transmission_km` (`lower_is_better`), `dist_substation_km` (`lower_is_better`), `demand_proxy` (`higher_is_better`), `slope_deg` (`lower_is_better`), and `inside_rez` (`higher_is_better`); each default criterion name must resolve to a real integrated-table `OUTPUT_COLUMNS` column
    - _Requirements: 2.1, 3.1, 3.2, 3.3, 3.4, 6.5_

- [x] 2. Implement the weights loader and validator
  - [x] 2.1 Implement `Criterion`/`WeightsConfig` dataclasses and `load_weights` in `pipeline/scoring/weights.py`
    - Define frozen dataclasses `Criterion(feature, weight, direction, rationale)` and `WeightsConfig(criteria, confidence_discount, confidence_factors, config_id)`
    - Implement `load_weights(path) -> WeightsConfig`: parse the YAML at runtime; read weight, direction, and rationale from the file with no weight literals in `scoring/` source (2.1, 2.2); build one `Criterion` per entry (2.3); compute `config_id = sha256` of the file content (12.2)
    - Halt (raise) BEFORE any scoring on: unparsable/missing file (2.5); a direction not in `{higher_is_better, lower_is_better}`, naming the offending criterion (2.6); a negative or non-numeric weight, naming the offending criterion (2.7); a zero weight sum (2.8)
    - _Requirements: 2.1, 2.2, 2.3, 2.5, 2.6, 2.7, 2.8, 12.2_

  - [x]* 2.2 Write property test — weights come from configuration; invalid configs rejected
    - **Property 12: Weights come from configuration; invalid configurations are rejected** (bad direction / negative or non-numeric weight / zero sum all halt before any write with an identifying error; two distinct valid configs are determined by loaded weights, not constants)
    - **Validates: Requirements 2.2, 2.5, 2.6, 2.7, 2.8**

- [x] 3. Implement the integrated-table loader with fail-fast validation
  - [x] 3.1 Implement `load_integrated` in `pipeline/scoring/load.py`
    - Implement `load_integrated(path, criteria) -> GeoDataFrame`: read the S1-08 integrated table as the SOLE feature input (1.1); reuse `cell_id` byte-for-byte, never re-derive/renumber/reformat/reorder (1.2)
    - Halt BEFORE any output on: missing/unreadable file, naming the path (1.3); no `cell_id` column (1.4); any configured criterion column, the `eligible` column, or the S1-09 composite `confidence` column absent, naming the missing column (1.5, 10.4)
    - Hand a fully in-memory frame to the pure Scoring_Function; this loader is the only file-reading path for feature data
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 10.4_

  - [x]* 3.2 Write unit tests for loader error conditions
    - Assert missing/unreadable table, absent `cell_id`, absent criterion/`eligible`/`confidence` columns each raise (naming the fault) and write no output (1.3, 1.4, 1.5, 10.4)
    - _Requirements: 1.3, 1.4, 1.5, 10.4_

- [x] 4. Implement normalisation
  - [x] 4.1 Implement `compute_bounds` and `normalise` in `pipeline/scoring/normalise.py`
    - Implement `compute_bounds(eligible, criteria) -> dict[str, tuple[float, float]]`: min/max per criterion from the ELIGIBLE population only; excluded-cell values never influence a bound (4.3, 7.3)
    - Implement `normalise(value, lo, hi, direction) -> float`: `higher_is_better` → `(v - lo)/(hi - lo)` (4.1); `lower_is_better` → `1 - (v - lo)/(hi - lo)` (4.2); `lo == hi` → return the documented `CONSTANT_CRITERION_VALUE` and flag the criterion constant for the method report, never dividing by zero (4.5); clamp the result to the inclusive `[0, 1]` range (4.4)
    - Map boolean criteria (e.g. `inside_rez`) `False`→0.0 / `True`→1.0 for `higher_is_better` (inverted for `lower_is_better`) (4.7); keep the function pure and deterministic (4.6)
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 7.3_

  - [x]* 4.2 Write property test — directional normalisation correctness
    - **Property 2: Directional normalisation correctness** (`higher_is_better`/`lower_is_better` formulae and boolean endpoint mapping vs independent recomputation)
    - **Validates: Requirements 4.1, 4.2, 4.7**

  - [x]* 4.3 Write property test — normalised features lie in [0, 1]
    - **Property 3: Normalised features lie in [0, 1]** (every normalised feature within the inclusive `[0, 1]` range)
    - **Validates: Requirements 4.4**

  - [x]* 4.4 Write property test — normalisation bounds come from the eligible population only
    - **Property 4: Normalisation bounds come from the eligible population only** (bounds == eligible min/max; unchanged when excluded-cell values are perturbed)
    - **Validates: Requirements 4.3, 7.3**

- [x] 5. Implement the pure Scoring_Function
  - [x] 5.1 Implement `score_frame` in `pipeline/scoring/score.py`
    - Implement `score_frame(features, weights) -> DataFrame`: PURE — DataFrame in, DataFrame out, NO file I/O, depends only on its two arguments so it is independently replaceable (5.5) and deterministic (5.6)
    - For each eligible cell: `norm_i = normalise(...)`, pre-discount `contribution_i = (weight_i * norm_i) / sum(weights)`, `raw_score = Σ contribution_i` (5.1), constrained to `[0, 1]` (5.2)
    - Excluded cells (`eligible == False`) receive null score / null rank / null contributions and take no part in bounds or ranking (6.4, 7.2); `wind_speed` participates ONLY as an input criterion, never a prediction target, and no wind prediction column is emitted (5.7)
    - Return a frame keyed on `cell_id` with `suitability_score`, one `contrib_{feature}` column per criterion, and intermediate normalised values (dropped before write)
    - _Requirements: 5.1, 5.2, 5.5, 5.6, 5.7, 6.4, 7.1, 7.2_

  - [x] 5.2 Apply the optional confidence discount to score and contributions
    - When `weights.confidence_discount` is enabled, derive the `Confidence_Factor` from the cell's `confidence` via the documented `confidence_factors` mapping and compute `final_score = raw_score * factor` (5.3); when disabled, `final_score = raw_score` (5.4)
    - Apply the SAME factor to every per-criterion contribution so contributions stay reconcilable with the final score (9.3)
    - _Requirements: 5.3, 5.4, 9.1, 9.2, 9.3_

  - [x]* 5.3 Write property test — weighted-sum scoring correctness
    - **Property 5: Weighted-sum scoring correctness** (score == `Σ(weight_i × norm_i) / Σ weights` prior to any discount, vs independent recomputation)
    - **Validates: Requirements 5.1**

  - [x]* 5.4 Write property test — suitability score lies in [0, 1]
    - **Property 6: Suitability score lies in [0, 1]** (every eligible-cell final score within the inclusive `[0, 1]` range)
    - **Validates: Requirements 5.2, 14.3**

  - [x]* 5.5 Write property test — contributions reconcile to the score
    - **Property 7: Contributions reconcile to the score** (Σ contributions == score within tolerance under both discount-enabled and discount-disabled settings)
    - **Validates: Requirements 9.1, 9.2, 9.3, 14.5**

  - [x]* 5.6 Write property test — confidence discount relation
    - **Property 8: Confidence discount relation** (discount on → final == raw × factor from the documented mapping; discount off → final == raw)
    - **Validates: Requirements 5.3, 5.4, 10.3**

  - [x]* 5.7 Write property test — no circular modelling
    - **Property 13: No circular modelling** (`wind_speed` affects the score only through its own contribution and is never a prediction target; no wind prediction column exists)
    - **Validates: Requirements 5.7**

- [x] 6. Implement ranking
  - [x] 6.1 Implement `assign_ranks` in `pipeline/scoring/rank.py`
    - Implement `assign_ranks(scored) -> Series`: dense rank over ELIGIBLE cells only, descending by final `suitability_score`, `rank` 1 = highest score (8.1)
    - Break ties by the documented deterministic rule — ascending `cell_id` — so repeated runs over identical inputs produce identical ranks (8.2, 8.4); excluded cells receive a null rank and are omitted from the ordering (8.3)
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

  - [x]* 6.2 Write property test — deterministic rank ordering with documented tie-break
    - **Property 10: Deterministic rank ordering with documented tie-break** (contiguous `1..n` descending by score, ties by ascending `cell_id`, no rank on excluded cells, identical across runs)
    - **Validates: Requirements 8.1, 8.2, 8.4, 14.7**

- [x] 7. Implement confidence carry-through and excluded-cell nulling
  - [x] 7.1 Assemble confidence carry-through and excluded-cell nulling in `pipeline/scoring/score.py`
    - Copy `confidence` per-cell from the S1-09 composite confidence flag in the integrated table; fabricate no value (10.1); every scored cell's `confidence` is exactly one of `high` or `low` (10.2)
    - Ensure excluded cells carry null `suitability_score`, null `rank`, and null contributions and are absent from the rank ordering (6.4, 7.2, 8.3)
    - Report the count of eligible cells scored and excluded cells nulled for the method report/summary (7.4)
    - _Requirements: 6.4, 7.1, 7.2, 7.4, 8.3, 10.1, 10.2_

  - [x]* 7.2 Write property test — only eligible cells are scored; excluded cells are null and unranked
    - **Property 9: Only eligible cells are scored; excluded cells are null and unranked** (eligible → non-null score/rank/contrib; excluded → null score/rank/contrib and no part in ordering)
    - **Validates: Requirements 6.4, 7.1, 7.2, 8.3, 14.4**

  - [x]* 7.3 Write property test — confidence carried through and two-valued
    - **Property 11: Confidence carried through and two-valued** (`confidence` == input composite flag for the `cell_id`; always exactly `high` or `low`; never fabricated)
    - **Validates: Requirements 10.1, 10.2, 14.6**

- [x] 8. Checkpoint — pure core verified
  - Ensure all tests pass, ask the user if questions arise.

- [x] 9. Implement the output writer
  - [x] 9.1 Implement `write_scored_table` in `pipeline/scoring/write.py`
    - Assemble the Scored_Table with `cell_id` (reused byte-for-byte), `suitability_score`, `rank`, `confidence`, one `contrib_{feature}` column per criterion, and geometry, exactly one row per integrated-table `cell_id` with no missing/duplicate `cell_id`, joinable to the grid on `cell_id` (6.1, 6.2, 6.3)
    - Atomic write (tmp + `os.replace`) of the GeoPackage via `common/geo`, mirroring `integration.merge.write_gpkg`, with geometry stored in EPSG:4326 (6.6, 6.7); write a `.csv` sidecar the same way; filename `optmining_suitability-score_2026_nsw.gpkg` (6.5)
    - On write failure, leave any pre-existing output unmodified and raise an error indication (6.8); the output is a fully regenerable derived product reproducible from the integrated table + Weights_Config with no manual editing (6.9)
    - _Requirements: 6.1, 6.2, 6.3, 6.5, 6.6, 6.7, 6.8, 6.9_

  - [x]* 9.2 Write property test — cell_id preservation and one row per cell
    - **Property 1: cell_id preservation and one row per cell** (Scored_Table `cell_id` multiset == integrated-table `cell_id` set exactly — each once, none missing/duplicated/extra — reused byte-for-byte)
    - **Validates: Requirements 1.2, 6.3, 14.1, 14.2**

- [x] 10. Implement the method report and provenance
  - [x] 10.1 Implement `write_method_report` in `pipeline/scoring/report.py`
    - Write `DATA/scoring/metadata/scoring_method.md` via `common.geo.atomic_write_text`, stamped with `common.geo.banner("scoring")` (12.4)
    - Record: the scoring formula and each criterion's weight, direction, and rationale (13.1); per-criterion Normalisation_Bounds (min/max) from the eligible population, and the per-criterion normalisation rule (13.1, 13.2); whether confidence discounting was enabled and, if so, the `Confidence_Factor` mapping (13.3); counts of eligible cells scored, excluded cells nulled, and cells at each `confidence` value (7.4, 13.4); whether normalisation was linear and, where a non-linear rule is applied to a distance criterion, the affected criteria and function (13.5); the `Per_Criterion_Contribution` definition and reconciliation rule (9.4); any criterion flagged constant by normalisation (4.5)
    - _Requirements: 4.5, 7.4, 9.4, 12.4, 13.1, 13.2, 13.3, 13.4, 13.5_

  - [x] 10.2 Implement `record_provenance` in `pipeline/scoring/report.py`
    - Mirror `integration.merge.record_provenance`: append a `DATA/scoring/DATA_PROVENANCE.md` row labelling the Scored_Table a **derived product**, listing the integrated-table input, the Weights_Config used, and the UTC generation timestamp (12.1, 12.3)
    - Write a `scoring_manifest.json` (SHA-256, byte count, UTC timestamp, generation params, integrated-table input, and `weights_config_id`) and a `source_register` entry (12.1, 12.2)
    - _Requirements: 12.1, 12.2, 12.3_

  - [x]* 10.3 Write unit tests for writer, method report, provenance, and naming
    - Atomic write leaves prior output intact on forced write failure (6.8); output filename matches `{source}_{dataset}_{year/vintage}_nsw.{ext}` (6.5); geometry written in EPSG:4326 (6.6); schema has exactly one `contrib_*` column per criterion (6.1, 6.2)
    - Method report is banner-stamped and records formula/weights/directions/rationales, per-criterion bounds, discount setting, eligible/excluded/confidence counts, contribution definition + reconciliation, and any constant criterion (12.4, 13.1, 13.2, 13.3, 13.4, 13.5, 9.4, 4.5)
    - Provenance: `DATA_PROVENANCE.md` derived-product row present; `scoring_manifest.json` has sha256/bytes/utc + `weights_config_id`; `source_register` entry added (12.1, 12.2, 12.3)
    - _Requirements: 4.5, 6.1, 6.2, 6.5, 6.6, 6.8, 9.4, 12.1, 12.2, 12.3, 12.4, 13.1, 13.2, 13.3, 13.4, 13.5_

- [x] 11. Wire the run() entry point
  - [x] 11.1 Implement `run(verbose=False, weights_path=None, integrated_path=None, confidence_discount=None) -> dict` in `pipeline/scoring/run.py`
    - Orchestrate: `load_weights` → `load_integrated` → split eligible/excluded → `compute_bounds` (eligible only) → `score_frame` (pure) → apply optional discount → `assign_ranks` → confidence carry-through + excluded nulling → assemble Scored_Table (reattach `cell_id`, `confidence`, geometry EPSG:4326) → `write_scored_table` → `write_method_report` → `record_provenance` → validation
    - First parameter `verbose` defaults to `False`; return a summary dict with `scored_table_path`, `method_report_path`, `n_cells`, `n_scored`, `n_excluded`, `n_high_confidence`, `n_low_confidence`, `weights_config_id`, `runtime_seconds`; both paths exist on disk after return (11.1, 11.2)
    - Raise (do not return a dict) on missing/unreadable table, absent required columns, invalid Weights_Config, or write failure, so the orchestrator halts non-zero (11.3)
    - _Requirements: 11.1, 11.2, 11.3_

  - [x]* 11.2 Write property + unit tests for the run() contract
    - **Property 14: Regeneration is deterministic (idempotent)** — two runs on a fixed integrated table + Weights_Config produce identical normalised features, scores, ranks, and contributions. **Validates: Requirements 4.6, 5.6, 6.9, 8.4**
    - **Property 15: Successful run returns existing output paths** — returned `scored_table_path`/`method_report_path` exist on disk. **Validates: Requirements 11.2**
    - Unit: signature introspection (`verbose=False` first param, returns dict); a forced fatal condition raises, returns no dict, and writes no output (11.1, 11.3)
    - _Requirements: 4.6, 5.6, 6.9, 8.4, 11.1, 11.2, 11.3_

- [x] 12. Register the stage in the orchestrator
  - [x] 12.1 Register `scoring` in `pipeline/config.py`
    - Add `"scoring"` to `STAGES` immediately after `"integration"` and before `"validate"`, so the integrated-table producer is scheduled before this consumer (11.4, 11.8)
    - Add `"scoring"` to `DOMAINS` so `--only scoring` / `--skip scoring` resolve (11.7)
    - _Requirements: 11.4, 11.7, 11.8_

  - [x] 12.2 Add dispatch and the CLI flag in `pipeline/__main__.py`
    - In `_get_runner`: add `elif stage == "scoring": from .scoring.run import run; return run`
    - Add a `--scoring-weights` CLI argument (default `pipeline/scoring/scoring_weights.yaml`); in `_build_kwargs`, for `"scoring"` pass `verbose` and `weights_path` (11.5)
    - Update the module docstring stage-order comment to include `scoring` after `integration`, before `validate`
    - _Requirements: 11.5_

  - [x] 12.3 Add the scoring subpackage docstring
    - Author `pipeline/scoring/__init__.py` with a docstring describing the scoring stage and its position after `integration` in the pipeline stage sequence (11.6)
    - _Requirements: 11.6_

  - [x]* 12.4 Write registration and ordering wiring tests
    - **Property 16: Resolved execution order places scoring after integration** — for any resolved stage list containing both, `integration` index < `scoring` index. **Validates: Requirements 11.4, 11.8**
    - Assert `_get_runner('scoring')` returns a callable; `"scoring"` is in `config.STAGES` (after `integration`, before `validate`) and `config.DOMAINS`; the `--scoring-weights` flag exists and is forwarded by `_build_kwargs`; `scoring/__init__` docstring describes the stage
    - _Requirements: 11.4, 11.5, 11.6, 11.7, 11.8_

- [x] 13. Add no-silent-passes validation checks
  - [x] 13.1 Implement `validate(...)` in `pipeline/scoring/validate.py` and cross-domain checks in `pipeline/validate.py`
    - Exactly one row per integrated-table `cell_id`: report expected count, observed row count, pass/fail (14.1)
    - Every `cell_id` present, none missing, none extra: report counts, pass/fail (14.2)
    - Every non-null `suitability_score` in `[0, 1]`: report out-of-range count, pass/fail (14.3)
    - Eligible ↔ non-null score, excluded ↔ null score: report violator count, pass/fail (14.4)
    - Per-criterion contributions reconcile to the score within tolerance for every scored eligible cell: report violator count, pass/fail (14.5)
    - `confidence` ∈ {`high`, `low`} only; any other value fails (14.6); `rank` is a contiguous ordering over scored eligible cells with no rank on an excluded cell (14.7)
    - Each check reports expected vs observed vs explicit pass/fail (no silent passes); place the cross-domain `cell_id`-set-equals-grid/integrated check in the cross-domain `pipeline/validate.py` tier (14.8)
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7, 14.8_

  - [x]* 13.2 Write unit tests for validation checks
    - Assert each check emits expected/observed/pass-fail and that a seeded bad Scored_Table (wrong row count, extra/missing `cell_id`, out-of-range score, eligible-with-null / excluded-with-score, non-reconciling contributions, bad `confidence`, non-contiguous rank or rank on an excluded cell) fails the relevant check
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7, 14.8_

  - [x]* 13.3 Write unit tests for scoring logic with known inputs and outputs (Requirement 15)
    - 15.1 `higher_is_better` normalisation on a small synthetic set vs hand-computed values within a documented tolerance
    - 15.2 `lower_is_better` normalisation vs hand-computed values within tolerance
    - 15.3 Weighted score on a synthetic set with a known Weights_Config vs hand-computed values within tolerance
    - 15.4 Contributions reconstruct the final score within tolerance for the synthetic input
    - 15.5 An excluded cell receives null score, null rank, and null contributions
    - 15.6 Rank ordering is descending by score and the tie-break produces deterministic ranks for equal scores
    - 15.7 A constant criterion (`min == max`) is handled by the documented constant-value rule rather than raising divide-by-zero
    - 15.8 The Scoring_Function returns identical outputs for two runs over identical inputs and config (determinism)
    - _Requirements: 15.1, 15.2, 15.3, 15.4, 15.5, 15.6, 15.7, 15.8_

- [x] 14. Checkpoint — stage runs end-to-end under the orchestrator
  - Ensure all tests pass, ask the user if questions arise.

- [x] 15. Full-NSW-grid integration and smoke tests
  - [x]* 15.1 Write full-NSW-grid integration test
    - Run over all 47,311 cells; assert one row per `cell_id`, the eligible/excluded counts match the integrated table's `eligible` flag, `runtime_seconds` is recorded, and a second run reproduces the Scored_Table byte-identically (regenerable derived product)
    - _Requirements: 6.3, 6.9, 7.4, 14.1, 14.2_

  - [x]* 15.2 Write orchestrator + default-config smoke tests
    - Assert `scoring` is in `config.STAGES` immediately after `integration` and before `validate`, is in `config.DOMAINS`, `--scoring-weights` exists and is forwarded by `_build_kwargs`, `_get_runner("scoring")` returns the stage `run`, and the subpackage `__init__` docstring describes the stage and its position
    - Assert `scoring_weights.yaml` ships and loads with a weight, valid direction, and a non-empty rationale for every default criterion, each resolving to a real integrated-table column (3.1, 3.2, 3.3, 3.4)
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 11.4, 11.5, 11.6, 11.7, 11.8_

- [x] 16. Update documentation to match the new stage
  - [x] 16.1 Update the data specification and README
    - Update the data specification §4 (dataset detail) and §7 (dataset→stage→criterion mapping) to name the Scored_Table output (`optmining_suitability-score_2026_nsw.gpkg`) and its columns and reference the `scoring` stage that produces it
    - Add `scoring` to the README stage-order table and CLI docs at the resolved runtime position (after `integration`, before `validate`), matching `config.STAGES` exactly; add the Scored_Table to the expected-outputs table (16.1, 16.2, 16.3)
    - State the scoring formula, the source of the criteria weights (the Weights_Config), the normalisation rule, and the eligible-only scoring rule (16.4); note that this stage does not change any frozen decision (Q1–Q7) — the criteria weights are user config, not a frozen parameter — so no §8 change-control is required for this release (16.5)
    - _Requirements: 16.1, 16.2, 16.3, 16.4, 16.5_

## Notes

- Tasks marked with `*` are optional test tasks and can be skipped for a faster MVP; core implementation tasks are never optional.
- Each task references specific requirements clauses for traceability.
- Property tests (P1–P16) sit directly under the pure core / wiring they validate so invariants are caught early; each is a single Hypothesis test running at least 100 iterations and tagged `# Feature: s1-10-baseline-suitability-model, Property {n}: {text}`.
- The pure `Scoring_Function` (`score.py`) receives an in-memory DataFrame plus a `WeightsConfig` and performs no file I/O, so it is independently replaceable without changing the data-loading layer.
- Criteria weights are user inputs loaded from `scoring_weights.yaml` (or `--scoring-weights`) at runtime — never hard-coded constants; the model is never circular (`wind_speed` is only an input criterion).
- All halt conditions (missing input, absent required column, invalid Weights_Config, write failure) occur before any Scored_Table output is written; a constant criterion (`min == max`) is the single handled numeric edge, filled with the documented constant rather than dividing by zero.
- Only eligible cells are scored and ranked; excluded cells carry null score/rank/contributions and take no part in the normalisation bounds or the rank ordering. CRS is explicit: geometry is stored in EPSG:4326.
- Checkpoints (tasks 8 and 14) provide incremental validation before the writers and before documentation.

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["2.1", "3.1", "4.1", "12.1", "12.3"] },
    { "id": 2, "tasks": ["2.2", "3.2", "4.2", "4.3", "4.4", "5.1"] },
    { "id": 3, "tasks": ["5.2", "5.3", "5.4", "5.7", "6.1"] },
    { "id": 4, "tasks": ["5.5", "5.6", "6.2", "7.1"] },
    { "id": 5, "tasks": ["7.2", "7.3", "9.1"] },
    { "id": 6, "tasks": ["9.2", "10.1", "10.2", "12.2"] },
    { "id": 7, "tasks": ["10.3", "11.1", "12.4"] },
    { "id": 8, "tasks": ["11.2", "13.1"] },
    { "id": 9, "tasks": ["13.2", "13.3", "15.1", "15.2", "16.1"] }
  ]
}
```
