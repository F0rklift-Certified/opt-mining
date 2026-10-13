# S4-01: Complete Outstanding Sprint 3 Integration

**Type:** Task
**Priority:** P0
**Status:** Backlog — acceptance evidence to be reviewed
**Source:** [Client Sprint 4 brief](OPT_MINING_Sprint4_Final_Guidance.md), §4 S4-01

## Objective

Create one stable application baseline before adding any final-sprint enhancements.

## Required Work

- [ ] Merge approved Sprint 2 and Sprint 3 work in the correct dependency order.
- [ ] Complete any remaining web-to-decision-service integration.
- [ ] Complete outstanding analysis controls, map rendering, click-to-inspect and ranked-results integration.
- [ ] Resolve merge conflicts, failed checks and integration defects.
- [ ] Confirm that the frontend uses the approved backend decision engine; do not duplicate scoring logic in the UI.
- [ ] Record the final integrated dataset/configuration version used for the Sprint 4 baseline.

## Acceptance Criteria

- [ ] A clean checkout can start the integrated application and execute the core analysis flow without manually running intermediate scripts.
- [ ] Approved Sprint 2 and Sprint 3 work is merged in dependency order with no outstanding merge conflicts and all CI checks green.
- [ ] The remaining web↔decision-service integration (analysis controls, map rendering, click-to-inspect, ranked results) is wired to the backend engine.
- [ ] The frontend uses the approved backend decision engine; there is no duplicated scoring/normalisation logic in the UI.
- [ ] The integrated dataset and configuration version used for the baseline is recorded in the repository.
- [ ] A release branch or tag marks the stable Sprint 4 baseline.

## Deliverable

Stable Sprint 4 baseline/release branch or tag, with all required Sprint 2-3 components integrated.

## Completion Evidence

Record the implementation PR/commit, relevant tests or reproducible outputs, and the review outcome here before closing this task. Refer to the [Sprint 4 Definition of Done](README.md#definition-of-done) for final acceptance.
