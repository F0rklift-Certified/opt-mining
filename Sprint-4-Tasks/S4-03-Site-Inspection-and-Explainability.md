# S4-03: Complete Site Inspection and Explainability

**Type:** Task
**Priority:** P0
**Status:** Backlog — acceptance evidence to be reviewed
**Source:** [Client Sprint 4 brief](OPT_MINING_Sprint4_Final_Guidance.md), §4 S4-03

## Objective

Allow a user to understand why a site is eligible, excluded, highly ranked or weakly ranked.

## Required Work

- [ ] For eligible sites show Site/Cell ID, suitability score, rank, wind value/score, demand proxy, infrastructure indicator(s), geographic/environmental indicator(s), criterion contributions, positive factors, weaknesses and data-quality/confidence information.
- [ ] For excluded sites show Site/Cell ID, ineligible status, exclusion reason(s) and relevant data-quality information.
- [ ] Do not assign a normal suitability rank to an excluded site.
- [ ] Use the existing deterministic explanation engine; an LLM is not required.
- [ ] Ensure explanations are derived from the same backend analysis results displayed elsewhere in the application.

## Acceptance Criteria

- [ ] Selecting a site from the map or shortlist opens a consistent, understandable site-detail view with traceable explanations.

## Deliverable

Integrated Site Detail / Why This Site? panel.

## Completion Evidence

Record the implementation PR/commit, relevant tests or reproducible outputs, and the review outcome here before closing this task. Refer to the [Sprint 4 Definition of Done](README.md#definition-of-done) for final acceptance.
