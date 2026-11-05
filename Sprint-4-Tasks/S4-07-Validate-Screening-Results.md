# S4-07: Validate the Screening Results

**Type:** Task
**Priority:** P1
**Status:** Done — evidence below (review pending)
**Source:** [Client Sprint 4 brief](OPT_MINING_Sprint4_Final_Guidance.md), §4 S4-07

## Objective

Assess whether the model output is geographically and practically plausible without forcing it to reproduce existing developments.

## Required Work

- [x] Compare selected high-ranked areas against defensible external reference information such as known NSW wind developments and/or NSW Renewable Energy Zones (REZs).
- [x] Document the comparison method and reference information used.
- [x] Identify areas of agreement and disagreement.
- [x] Investigate plausible reasons for disagreement, including data limitations, criteria, exclusions and modelling assumptions.
- [x] Do not tune results merely to make known developments rank highly.

## Acceptance Criteria

- [x] The team can explain whether the spatial screening pattern appears credible and clearly document important limitations.
- [x] The external reference information used (e.g. known NSW wind developments and/or REZs) is named and cited.
- [x] The comparison method is documented and reproducible.
- [x] Areas of agreement and disagreement are identified, with plausible reasons for disagreement (data limitations, criteria, exclusions, modelling assumptions).
- [x] Results are not tuned merely to make known developments rank highly, and this is stated.
- [x] Supporting outputs are reproducible from documented commands and name the dataset/config version used.

## Deliverable

validation_report.md (or equivalent) plus reproducible supporting outputs.

## Completion Evidence

**Branch:** `s4-integration` (from `docs/sprint-4-final-backlog`). **Owner:** Pouya Mousavi. **Verified:** 2026-10-22.

| Acceptance criterion | Evidence |
| --- | --- |
| Credibility explained, limitations documented | Handover pack `01_Validation_Report` §1, §5, §6: 11 of 14 operating NSW wind farms in the upper quartile; all top-20 cells in the New England (13) and Central-West Orana (7) REZs; 6/6 exclusion landmarks excluded. |
| References named and cited | Geoscience Australia Major Power Stations 2026 (wind, NSW), `DATA/infrastructure/generators/ga_wind_generators_2026_nsw.geojson`; EnergyCo NSW REZ boundaries; five urban/park landmarks. |
| Method documented and reproducible | `python -m pipeline --only sanity` (S1-12 stage); thresholds in `pipeline/sanity/config.py`. |
| Agreement / disagreement with reasons | Only 1 of 14 farms in the top 20 (REZ weight; most farms outside REZs); Taralga and Rye Park cells excluded by binary protected-area overlap at ~5 km; Boco Rock (73rd percentile) has lower cell-mean wind, 7.3° slope and no REZ. |
| Not tuned, stated | Report §1 callout; no weight, threshold or rule changed. The reference set was cleaned of a GA solar mislabel and a duplicate farm (QA F-03, commit `100da10`), which changes the denominator, not any score. |
| Reproducible outputs name the dataset/config | `DATA/sanity/optmining_validation-results_2026_nsw.json` records pipeline version `9d72800` (clean tree) and 23,266 eligible of 47,311; integrated table SHA-256 `df7073bd…`. |

**Review outcome:** _pending PR review._

Refer to the [Sprint 4 Definition of Done](README.md#definition-of-done) for final acceptance.
