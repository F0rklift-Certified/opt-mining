# S4-09a: Complete End-to-End Workflow Testing (Happy Path)

**Type:** Task
**Priority:** P0
**Status:** Backlog — acceptance evidence to be reviewed
**Source:** [Client Sprint 4 brief](OPT_MINING_Sprint4_Final_Guidance.md), §4 S4-09
**Blocked by:** S4-02, S4-03, S4-04, S4-05, S4-06, S4-10
**Blocks:** S4-09b

---

> **Split note:** First half of the former **S4-09** (End-to-End and Failure-Case Testing). S4-09a proves the happy-path workflow passes end-to-end; S4-09b exercises the failure and edge cases. Splitting lets the core workflow be verified and signed off before the (larger) failure-case effort, and keeps a green end-to-end baseline that the failure tests can build on.

## Objective

Verify the whole product on the intended end-to-end workflow, not only individual backend functions.

## Required Work

- [ ] Test the full workflow from application launch through scenario selection, analysis, map, shortlist, site inspection and rerun.
- [ ] Confirm the frontend exercises the approved backend decision engine throughout (no UI-side scoring).
- [ ] Capture the test as a repeatable script/checklist, run against a clean checkout of the Sprint 4 baseline.
- [ ] Record the environment, dataset/config version and commands used so the run is reproducible.

## Acceptance Criteria

- [ ] A documented end-to-end test exercises launch → scenario/weights → run analysis → NSW map → eligible/excluded cells → ranked shortlist → site inspection → change scenario → rerun → compare, and passes on a clean checkout.
- [ ] Map, shortlist and site-detail views show consistent cell IDs, scores and ranks sourced from the same backend analysis output.
- [ ] A rerun with changed weights produces an observably different ranking (confirming the UI calls the engine rather than caching/recomputing).
- [ ] The test is reproducible from documented commands and names the dataset/config version used.
- [ ] Automated coverage exists where practical; any step verified manually is explicitly recorded as a manual check with its rationale.

## Deliverable

End-to-end (happy-path) test script/checklist plus evidence of a passing run, and automated tests where appropriate.

## Completion Evidence

Record the implementation PR/commit, relevant tests or reproducible outputs, and the review outcome here before closing this task. Refer to the [Sprint 4 Definition of Done](README.md#definition-of-done) for final acceptance.
