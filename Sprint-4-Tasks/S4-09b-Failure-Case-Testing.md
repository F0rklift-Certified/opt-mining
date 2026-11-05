# S4-09b: Complete Failure-Case Testing

**Type:** Task
**Priority:** P0
**Status:** Backlog — acceptance evidence to be reviewed
**Source:** [Client Sprint 4 brief](OPT_MINING_Sprint4_Final_Guidance.md), §4 S4-09
**Blocked by:** S4-09a

---

> **Split note:** Second half of the former **S4-09**. S4-09a verified the happy-path workflow; S4-09b exercises invalid inputs, edge cases and backend/API failures, and confirms they surface safe, clear user-facing messages. This is where the real testing effort sits, so it is isolated for its own review on top of the green S4-09a baseline.

## Objective

Verify the product fails safely: common invalid inputs, edge cases and backend failures produce clear user-facing messages rather than silent or misleading results.

## Required Work

- [ ] Test invalid weights and extreme weight combinations (e.g. all-zero, negative, single-criterion, out-of-range).
- [ ] Test missing/invalid input and missing criterion values.
- [ ] Test excluded-site selection.
- [ ] Test empty/no-result filters (e.g. Top-N or threshold that returns no eligible cells).
- [ ] Test backend/API failure handling where applicable (service down, timeout, malformed response).
- [ ] Ensure failures produce clear user-facing messages rather than silent or misleading results.

## Acceptance Criteria

- [ ] Invalid and extreme weight inputs are rejected or normalised consistently with the decision-engine specification, with a clear user-facing message; the app does not crash or display a misleading ranking.
- [ ] Missing/invalid inputs and missing criterion values are handled with a documented, safe outcome rather than a silent failure.
- [ ] Selecting an excluded site shows its ineligible status and exclusion reason, never a normal suitability rank.
- [ ] An empty/no-result filter shows an explicit "no results" state rather than a blank or stale view.
- [ ] Backend/API failure (down, timeout, malformed response) produces a clear user-facing error and leaves the app in a recoverable state.
- [ ] Each failure case is documented with its trigger, expected message/behaviour and observed result; automated coverage exists where practical.

## Deliverable

Final failure-case test report/checklist and automated tests where appropriate.

## Completion Evidence

Record the implementation PR/commit, relevant tests or reproducible outputs, and the review outcome here before closing this task. Refer to the [Sprint 4 Definition of Done](README.md#definition-of-done) for final acceptance.
