# S4-04: Finalise Analysis Controls and Weight Handling

**Type:** Task
**Priority:** P0
**Status:** Backlog — acceptance evidence to be reviewed
**Source:** [Client Sprint 4 brief](OPT_MINING_Sprint4_Final_Guidance.md), §4 S4-04

## Objective

Allow users to configure and run screening scenarios without editing source code.

## Required Work

- [ ] Provide default criterion weights.
- [ ] Provide named scenario presets.
- [ ] Allow custom weights for Wind, Demand Proxy, Infrastructure and Geographic/Environmental criteria.
- [ ] Validate or normalise user-entered weights consistently with the approved decision-engine specification.
- [ ] Provide Reset to Default and Run Analysis actions.
- [ ] Clearly display the currently active scenario/configuration.

## Acceptance Criteria

- [ ] Changing valid weights or selecting a preset and running the analysis invokes the approved backend decision engine and can change the ranking.

## Deliverable

Final analysis-control panel connected to the decision service.

## Completion Evidence

Record the implementation PR/commit, relevant tests or reproducible outputs, and the review outcome here before closing this task. Refer to the [Sprint 4 Definition of Done](README.md#definition-of-done) for final acceptance.
