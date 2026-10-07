# S4-09: Complete End-to-End and Failure-Case Testing

**Type:** Task
**Priority:** P0
**Status:** Backlog — acceptance evidence to be reviewed
**Source:** [Client Sprint 4 brief](OPT_MINING_Sprint4_Final_Guidance.md), §4 S4-09

## Objective

Verify the whole product, not only individual backend functions.

## Required Work

- [ ] Test the full workflow from application launch through scenario selection, analysis, map, shortlist, site inspection and rerun.
- [ ] Test invalid weights and extreme weight combinations.
- [ ] Test missing/invalid input and missing criterion values.
- [ ] Test excluded-site selection.
- [ ] Test empty/no-result filters.
- [ ] Test backend/API failure handling where applicable.
- [ ] Ensure failures produce clear user-facing messages rather than silent or misleading results.

## Acceptance Criteria

- [ ] The complete application flow passes documented tests and common failure cases are handled safely.

## Deliverable

Final test report/checklist and automated tests where appropriate.

## Completion Evidence

Record the implementation PR/commit, relevant tests or reproducible outputs, and the review outcome here before closing this task. Refer to the [Sprint 4 Definition of Done](README.md#definition-of-done) for final acceptance.
