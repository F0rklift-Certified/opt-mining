# S2-09: Backend Unit & Integration Test Suite

**Type:** Story
**Priority:** High
**Story Points:** 2
**Labels:** testing, decision-engine
**Blocked by:** S2-05, S2-06, S2-07
**Blocks:** —

---

## Objective

Provide unit tests for the decision functions and an integration test for the end-to-end backend flow (frozen dataset → exclusions → normalisation → scoring → ranking → explanation → scenarios), plus small controlled test cases where the expected ranking is known.

---

## Context

Guidance Step 11 (controlled test cases) and Step 12 (unit + integration tests). The guidance requires small controlled test cases where the expected ranking is known "so that the scoring code itself can be verified." This ticket consolidates the cross-module test guarantees; individual modules also carry their own unit tests (in S2-03..S2-07).

---

## Deliverables

1. Unit tests for each decision function (normalisation, scoring, ranking, explanation, scenario re-ranking).
2. An end-to-end backend integration test over the frozen dataset.
3. Controlled fixtures with hand-computed expected rankings.

---

## Acceptance Criteria

- [x] Unit tests cover normalisation directions/edge cases, the scoring formula, tie-breaking, explanation content and scenario re-ranking (satisfies **AC4**, **AC6**)
- [x] At least one **controlled test case** with a hand-computed expected ranking verifies the scoring code end-to-end
- [x] An integration test runs the full backend flow on the frozen S2-02 dataset and asserts a stable, deterministic result
- [x] Tests confirm excluded cells never receive a score and never enter normalisation bounds
- [x] Tests confirm per-criterion contributions sum to the total score
- [x] Tests run in CI (`.github/workflows/ci.yml`) and pass from a clean environment
- [x] Determinism is asserted: the same input yields identical scores, ranks and explanations across runs

---

## Technical Notes

- Reuse the existing test layout under `tests/` and the project's pytest configuration (`pytest.ini`).
- The controlled fixture is the guidance's key safeguard against a subtly wrong formula — keep it tiny (a handful of cells) and hand-verify the arithmetic in a comment.
- This ticket is deliberately small because most unit tests are written inside their feature tickets; it exists to own the cross-module integration test and the controlled-ranking fixture and to make the CI gate explicit.

---

## Completion Evidence

Completed by **XINHAO WANG** on 2026-09-14.

- `tests/backend/test_backend_decision_flow.py` owns the S2-09 cross-module gate.
  Its five-cell controlled fixture documents the arithmetic for both beneficial
  and adverse normalisation directions, weighted contributions, deterministic
  `cell_id` tie-breaking, excluded-cell handling, explanation content and a
  hand-computed Wind-led/Grid-led rank reversal.
- The frozen-data fixture reads
  `DATA/integration/optmining_integrated-features_2026_nsw.gpkg` through the real
  scoring loader and pins its SHA-256
  (`b7cd3d261abfdedd613301e0e2fdd07e3381178deb8ce8aff506a066117a1e61`).
  It runs the production normalisation, scoring, ranking, explanation and
  scenario-comparison components over all 47,311 cells without writing to
  tracked `DATA/` outputs.
- The integration assertions pin 1,233 eligible/scored cells, 46,078 excluded
  cells, the reviewed baseline top-five result, both scenario top-five results,
  1,228 scenario rank changes and a digest of all 47,311 explanations.
- Excluded feature values are deliberately replaced with extreme values in a
  rerun; every eligible normalised value, contribution, score and rank remains
  byte-for-byte identical, proving excluded cells do not enter the bounds.
- A repeated run must produce exactly equal score/rank frames, explanation
  structures and scenario-comparison payloads. Per-criterion contributions are
  reconciled to every eligible total score within the production tolerance.
- `.github/workflows/ci.yml` has a named S2-09 backend gate followed by the
  remainder of the project suite, both installed and run from a clean GitHub
  Actions environment on the supported Python 3.13 interpreter.
