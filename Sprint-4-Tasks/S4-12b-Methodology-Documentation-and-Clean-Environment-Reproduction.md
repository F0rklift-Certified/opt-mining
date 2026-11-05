# S4-12b: Methodology Documentation and Clean-Environment Reproduction

**Type:** Task
**Priority:** P0
**Status:** Backlog — acceptance evidence to be reviewed
**Source:** [Client Sprint 4 brief](OPT_MINING_Sprint4_Final_Guidance.md), §4 S4-12
**Blocked by:** S4-12a, S4-07, S4-08, S4-09a, S4-09b, S4-10, S4-13

---

> **Split note:** Second half of the former **S4-12**. S4-12a documented install/run; S4-12b documents the methodology (data, CRS, exclusions, scoring, demand proxy, explainability, scenario analysis, validation, testing, limitations) and performs the clean-environment reproduction test. The clean-env reproduction is itself the key verifiable deliverable for the Sprint 4 Definition of Done and is isolated so it is reviewed as evidence, not buried in a checkbox.

## Objective

Document the methodology and known limitations, and prove the final system reproduces from a clean environment with no undocumented manual steps.

## Required Work

- [ ] Document data sources, data pipeline and CRS/spatial methodology.
- [ ] Document hard exclusions, criteria/features, normalisation, weighting/scoring and ranking.
- [ ] Document the demand-proxy methodology, explainability, scenario analysis, validation, testing and known limitations.
- [ ] Test the full install-and-run instructions from a clean environment (fresh checkout, no pre-existing build artefacts or local state).

## Acceptance Criteria

- [ ] Methodology documentation covers data sources, data pipeline and CRS/spatial handling, consistent with the implementation.
- [ ] Hard exclusions, criteria/features, normalisation, weighting/scoring and ranking are documented and match the approved decision-engine specification.
- [ ] Demand-proxy methodology, explainability, scenario analysis, validation, testing and known limitations are documented, with the demand proxy clearly described as a spatial proxy (not measured local consumption).
- [ ] A clean-environment reproduction is performed and recorded: environment, dataset/config version, commands run, and the resulting application state.
- [ ] The reproduction succeeds without undocumented manual intervention; any gap found is fixed in the docs and re-tested, or recorded as a known limitation.

## Deliverable

Supporting technical/methodology documentation plus a recorded clean-environment reproduction result.

## Completion Evidence

Record the implementation PR/commit, relevant tests or reproducible outputs, and the review outcome here before closing this task. Refer to the [Sprint 4 Definition of Done](README.md#definition-of-done) for final acceptance.
