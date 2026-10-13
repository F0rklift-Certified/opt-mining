# S4-07: Validate the Screening Results

**Type:** Task
**Priority:** P1
**Status:** Backlog — acceptance evidence to be reviewed
**Source:** [Client Sprint 4 brief](OPT_MINING_Sprint4_Final_Guidance.md), §4 S4-07

## Objective

Assess whether the model output is geographically and practically plausible without forcing it to reproduce existing developments.

## Required Work

- [ ] Compare selected high-ranked areas against defensible external reference information such as known NSW wind developments and/or NSW Renewable Energy Zones (REZs).
- [ ] Document the comparison method and reference information used.
- [ ] Identify areas of agreement and disagreement.
- [ ] Investigate plausible reasons for disagreement, including data limitations, criteria, exclusions and modelling assumptions.
- [ ] Do not tune results merely to make known developments rank highly.

## Acceptance Criteria

- [ ] The team can explain whether the spatial screening pattern appears credible and clearly document important limitations.
- [ ] The external reference information used (e.g. known NSW wind developments and/or REZs) is named and cited.
- [ ] The comparison method is documented and reproducible.
- [ ] Areas of agreement and disagreement are identified, with plausible reasons for disagreement (data limitations, criteria, exclusions, modelling assumptions).
- [ ] Results are not tuned merely to make known developments rank highly, and this is stated.
- [ ] Supporting outputs are reproducible from documented commands and name the dataset/config version used.

## Deliverable

validation_report.md (or equivalent) plus reproducible supporting outputs.

## Completion Evidence

Record the implementation PR/commit, relevant tests or reproducible outputs, and the review outcome here before closing this task. Refer to the [Sprint 4 Definition of Done](README.md#definition-of-done) for final acceptance.
