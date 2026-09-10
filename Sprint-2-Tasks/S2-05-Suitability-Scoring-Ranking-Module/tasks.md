# Implementation Plan: Suitability Scoring & Ranking Module (S2-05)

## Overview

This plan **hardens the existing `pipeline/scoring/` stage** to the combined Sprint 2/3 acceptance bar, following the design. The scoring engine already exists (S1-10); the work is: (1) reconcile the code to the frozen S2-01 Decision_Engine_Spec, (2) confirm each combined-sprint acceptance criterion against the existing guarantees, (3) add a controlled hand-computed ranking test and confirm determinism, (4) confirm the no-silent-passes validation, and (5) keep the README and method report consistent with the frozen spec.

Because the module exists, most tasks are **verify-and-conform** rather than build-from-scratch. Where a task finds a genuine gap against the spec or an acceptance criterion, it closes it. Tasks are ordered so the pure core is confirmed first, then the stage wiring, then validation, then documentation. This feature is blocked by S2-01 (frozen spec) and S2-04 (single normaliser) and blocks S2-06, S2-07 and S2-08.

> **Dependency.** The normalisation component (`pipeline/scoring/normalise.py`) is the same one S2-04 surfaces as a standalone tested component. This plan calls it and must not introduce a second normaliser (Requirement 1.4).

## Tasks

- [ ] 1. Reconcile the implementation to the frozen decision-engine spec
  - [ ] 1.1 Compare `pipeline/scoring/` and `scoring_weights.yaml` against the S2-01 Decision_Engine_Spec
    - Confirm the formula, criteria, directions and default weights match the frozen spec; where they differ, conform the code to the spec and record the reconciliation (1.1, 1.2, 1.3)
    - Confirm the stage uses the single S2-04 normaliser and no second normaliser exists in the codebase (1.4)
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

- [ ] 2. Confirm the weights loader and configurability
  - [ ] 2.1 Verify `pipeline/scoring/weights.py`
    - Confirm weights/directions/rationales load from the Weights_Config at runtime with no weight literal in source (2.1, 2.2)
    - Confirm the `--scoring-weights` flag and `_build_kwargs` threading load an alternative path (2.3)
    - Confirm the enforce/auto-normalise rule is applied and documented (2.4)
    - Confirm halt-before-write on unparsable file, invalid direction, negative/non-numeric weight, zero weight sum (2.5)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5_

  - [ ] 2.2 Property test — weights are data, not code
    - **Property 5: Weights are data** — no weight literal in `pipeline/scoring/`; changing the YAML changes the model output
    - **Validates: Requirements 2.1, 2.2**

- [ ] 3. Confirm the pure scoring function
  - [ ] 3.1 Verify `pipeline/scoring/score.py`
    - Confirm the weighted sum divided by the applied weight sum, bounded to `[0,1]` (3.1, 3.2)
    - Confirm the function is pure (DataFrame + weights in, scored DataFrame out, no file I/O) (3.3)
    - Confirm the wind feature is an input criterion only, never a target (3.5)
    - _Requirements: 3.1, 3.2, 3.3, 3.5_

  - [ ] 3.2 Property test — scores bounded
    - **Property 1: Scores bounded** — every non-null `suitability_score` ∈ `[0,1]`
    - **Validates: Requirements 3.2**

  - [ ] 3.3 Property test — determinism of scoring
    - **Property 4 (scores half): Deterministic scoring** — two runs over identical inputs and weights yield identical scores
    - **Validates: Requirements 3.4**

- [ ] 4. Confirm the eligible-only rule and normalisation bounds
  - [ ] 4.1 Verify eligible/excluded handling
    - Eligible cells get score/rank/contributions; excluded cells get null score/rank/contributions and are absent from ranking (4.1, 4.2)
    - Normalisation bounds computed from the eligible population only, excluding excluded cells (4.3)
    - _Requirements: 4.1, 4.2, 4.3_

  - [ ] 4.2 Property test — eligible-only
    - **Property 3: Eligible-only** — eligible cells scored; excluded cells null and absent from ranking and bounds
    - **Validates: Requirements 4.1, 4.2, 4.3**

- [ ] 5. Confirm deterministic ranking
  - [ ] 5.1 Verify `pipeline/scoring/rank.py`
    - Descending by score, rank 1 best; ties by ascending `cell_id`; null rank for excluded cells; identical ranks across runs (5.1, 5.2, 5.3, 5.4)
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [ ] 5.2 Property test — deterministic ranking with tie-break
    - **Property 4: Deterministic ranking** — identical ranks across runs; ties resolve by ascending `cell_id`
    - **Validates: Requirements 5.2, 5.4**

- [ ] 6. Confirm explainability contributions
  - [ ] 6.1 Verify `contrib_{feature}` columns
    - One contribution column per criterion for every scored cell (6.1); contributions reconstruct the score within tolerance (6.2); confidence discount applies equally to score and contributions (6.3); contribution columns retained for S2-06/S2-08 (6.4)
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ] 6.2 Property test — contributions reconstruct the score
    - **Property 2: Contributions reconstruct the score** — `Σ contrib_{feature}` equals `suitability_score` within tolerance for every scored cell
    - **Validates: Requirements 6.2**

- [ ] 7. Checkpoint — pure core and ranking confirmed
  - Ensure all tests pass; record any spec reconciliation from task 1; ask the user if questions arise.

- [ ] 8. Add the controlled test case and confirm the test suite
  - [ ] 8.1 Add a controlled hand-computed ranking fixture
    - A tiny synthetic input (a handful of cells) with a hand-computed expected ranking, arithmetic verified in a comment, asserting the end-to-end score and rank (7.3)
    - Confirm unit tests cover the formula, weight re-normalisation, tie-break, eligible-only rule (7.2)
    - Confirm the determinism assertion covers scores, ranks and contributions (7.4)
    - Confirm scoring lives entirely in the backend, not in UI code (7.1)
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [ ] 9. Confirm the stage contract and output schema
  - [ ] 9.1 Verify `pipeline/scoring/run.py` and the Scored_Table schema
    - `run(verbose=False, ...) -> dict` returns existing Scored_Table + method-report paths (8.3); raises (no dict) on fatal conditions so the orchestrator halts non-zero
    - Scored_Table has at least `cell_id`, `suitability_score`, `rank`, `confidence`, one `contrib_{feature}` per criterion (8.1); one row per `cell_id`, joinable to the grid (8.2); schema stable for S2-06/07/08 (8.4)
    - _Requirements: 8.1, 8.2, 8.3, 8.4_

- [ ] 10. Confirm no-silent-passes validation
  - [ ] 10.1 Verify `pipeline/scoring/validate.py`
    - One row per `cell_id` (9.1); scores in `[0,1]` (9.2); eligible↔non-null / excluded↔null (9.3); contributions reconcile (9.4); rank contiguity, no rank on excluded (9.5); every check reports expected vs observed vs pass/fail (9.6)
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6_

  - [ ] 10.2 Unit tests — seeded bad tables fail the right check
    - A seeded out-of-range score, an eligible/excluded violation, a contribution mismatch, and a rank-gap each fail their check
    - _Requirements: 9.2, 9.3, 9.4, 9.5_

- [ ] 11. Sync documentation to the frozen spec
  - [ ] 11.1 Reconcile README and method report to the Decision_Engine_Spec
    - README stage notes and the method report match the spec formula, criteria, directions and default weights (10.1); the method report records the formula, criteria, per-run bounds and eligible/excluded/confidence counts (10.2); correct any divergence (10.3)
    - _Requirements: 10.1, 10.2, 10.3_

- [ ] 12. Checkpoint — Client Checkpoint B (Backend working, scoring half)
  - Full run on the real NSW integrated table; confirm the controlled test case, determinism and validation pass in CI; present the scoring/ranking backend for review. Ask the user if questions arise.

## Notes

- This is a hardening feature over an existing module — most tasks verify and conform rather than build. Genuine gaps against the spec or an acceptance criterion are closed where found.
- Property tests (P1–P7) sit next to the pure core they validate; each is tagged `# Feature: s2-05-suitability-scoring-ranking, Property {n}: {text}`.
- There must be exactly one normaliser (shared with S2-04); introducing a second is the cross-component inconsistency the project rules forbid.
- The controlled hand-computed ranking case is the guidance's key safeguard against a subtly wrong formula — keep it tiny and hand-verify the arithmetic.
- Blocks S2-06 (explanations consume the contributions), S2-07 (scenarios re-run this function with alternate weights) and S2-08 (the service returns this output).
