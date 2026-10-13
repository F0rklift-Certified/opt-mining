# S4-11: Add Results Export

**Type:** Task
**Priority:** P2
**Status:** Backlog — acceptance evidence to be reviewed
**Source:** [Client Sprint 4 brief](OPT_MINING_Sprint4_Final_Guidance.md), §4 S4-11

## Objective

Allow useful downstream use of the screening shortlist if time permits.

## Required Work

- [ ] Provide CSV export of ranked eligible results if technically feasible after P0/P1 functionality is stable.
- [ ] Include useful fields such as cell_id, rank, suitability_score and the four criterion groups or their key values.
- [ ] Ensure exported results correspond to the active scenario.

## Acceptance Criteria

- [ ] The exported file reproduces the currently displayed analysis results and identifies the active scenario/configuration.
- [ ] The CSV contains the named fields (cell_id, rank, suitability_score and the four criterion groups or their key values).
- [ ] The exported rows and values match the on-screen ranked eligible results for the active scenario (no separate recomputation).
- [ ] The active scenario/configuration is identified in the exported file.
- [ ] Export is implemented only after P0/P1 work is stable (per the priority gate below).

## Deliverable

CSV export function.

## Completion Evidence

Record the implementation PR/commit, relevant tests or reproducible outputs, and the review outcome here before closing this task. Refer to the [Sprint 4 Definition of Done](README.md#definition-of-done) for final acceptance.

**Priority gate:** Begin this P2 enhancement only when P0 and P1 work is stable and time remains.
