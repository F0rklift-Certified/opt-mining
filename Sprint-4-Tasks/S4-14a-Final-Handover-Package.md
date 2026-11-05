# S4-14a: Assemble the Final Handover Package

**Type:** Task
**Priority:** P0
**Status:** Backlog — acceptance evidence to be reviewed
**Source:** [Client Sprint 4 brief](OPT_MINING_Sprint4_Final_Guidance.md), §4 S4-14
**Blocked by:** S4-01, S4-02, S4-03, S4-04, S4-05, S4-06, S4-07, S4-08, S4-09a, S4-09b, S4-10, S4-12a, S4-12b, S4-13
**Blocks:** S4-14b

---

> **Split note:** First half of the former **S4-14** (Final Client Demonstration and Handover). S4-14a assembles and tags the reproducible handover package (repo, docs, tests, reports, diagrams, demo material); S4-14b is the live demonstration. Splitting lets the package be assembled and verified as a gate while any late P1 work finishes, so the demo runs against a frozen, reproducible release rather than a moving target.

## Objective

Produce a complete, reproducible handover package: the final release of the MVP with all supporting material.

## Required Work

- [ ] Create the final release/tag of the Sprint 4 baseline.
- [ ] Hand over the final repository, documentation, tests, reports (validation + sensitivity), diagrams and presentation/demo material.
- [ ] Confirm the released build runs the documented end-to-end workflow against the real integrated NSW dataset.
- [ ] Cross-check the handover against the [Final Handover Checklist](README.md#final-handover-checklist).

## Acceptance Criteria

- [ ] A final release/tag exists and corresponds to the verified Sprint 4 baseline (dataset/config version recorded).
- [ ] The package contains the working web application, repository, setup + methodology documentation, automated tests + E2E evidence, validation report, sensitivity-analysis results, architecture/data-flow diagram, and presentation/demo material (export included if S4-11 was done).
- [ ] Every item on the README Final Handover Checklist is present and linked, or explicitly marked not-done with a reason.
- [ ] The client can reproduce the documented end-to-end workflow from the handed-over package without modifying source code.

## Deliverable

Final release/handover package.

## Completion Evidence

Record the implementation PR/commit, relevant tests or reproducible outputs, and the review outcome here before closing this task. Refer to the [Sprint 4 Definition of Done](README.md#definition-of-done) for final acceptance.
