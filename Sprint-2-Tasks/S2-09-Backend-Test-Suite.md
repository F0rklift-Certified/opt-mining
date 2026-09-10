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

- [ ] Unit tests cover normalisation directions/edge cases, the scoring formula, tie-breaking, explanation content and scenario re-ranking (satisfies **AC4**, **AC6**)
- [ ] At least one **controlled test case** with a hand-computed expected ranking verifies the scoring code end-to-end
- [ ] An integration test runs the full backend flow on the frozen S2-02 dataset and asserts a stable, deterministic result
- [ ] Tests confirm excluded cells never receive a score and never enter normalisation bounds
- [ ] Tests confirm per-criterion contributions sum to the total score
- [ ] Tests run in CI (`.github/workflows/ci.yml`) and pass from a clean environment
- [ ] Determinism is asserted: the same input yields identical scores, ranks and explanations across runs

---

## Technical Notes

- Reuse the existing test layout under `tests/` and the project's pytest configuration (`pytest.ini`).
- The controlled fixture is the guidance's key safeguard against a subtly wrong formula — keep it tiny (a handful of cells) and hand-verify the arithmetic in a comment.
- This ticket is deliberately small because most unit tests are written inside their feature tickets; it exists to own the cross-module integration test and the controlled-ranking fixture and to make the CI gate explicit.
