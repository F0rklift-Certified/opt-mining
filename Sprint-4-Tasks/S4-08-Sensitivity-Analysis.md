# S4-08: Perform Sensitivity Analysis

**Type:** Task
**Priority:** P1
**Status:** Done — evidence below (review pending)
**Source:** [Client Sprint 4 brief](OPT_MINING_Sprint4_Final_Guidance.md), §4 S4-08

## Objective

Show how dependent the shortlist is on decision preferences and weights.

## Required Work

- [x] Run several meaningful weighting scenarios.
- [x] Compare Top-N sites across scenarios.
- [x] Report rank/score changes.
- [x] Identify relatively robust sites and highly weight-sensitive sites.
- [x] Interpret the results rather than only presenting tables.

## Acceptance Criteria

- [x] The team demonstrates how preference changes affect recommendations and identifies important sensitivity in the ranking.
- [x] Several meaningful weighting scenarios are run, and the scenarios used are documented.
- [x] Top-N sites are compared across scenarios with reported rank/score changes.
- [x] Relatively robust sites and highly weight-sensitive sites are identified.
- [x] The report interprets the results (what the sensitivity means for recommendations), not only tables.
- [x] Outputs are reproducible from documented commands and name the dataset/config version used.

## Deliverable

Concise sensitivity-analysis report and reproducible outputs.

## Completion Evidence

**Branch:** `s4-integration`. **Owner:** Pouya Mousavi. **Verified:** 2026-10-22.

| Acceptance criterion | Evidence |
| --- | --- |
| Preference changes shown; important sensitivity identified | `scripts/sensitivity_analysis.py` (tests `tests/scoring/test_sensitivity.py`). ±20% on any one weight keeps Spearman ≥ 0.996 and ≥ 18 of the top 20; wind speed and the demand proxy reshuffle the top most (lowest top-100 Kendall τ 0.717, wind −20%). Wind-led keeps only 50% of the baseline top 20. |
| Several scenarios, documented | 24 one-at-a-time perturbations (each weight −20/−10/+10/+20%) plus the Wind-led and Grid-led presets (`pipeline/scoring/scenarios.yaml`). |
| Top-N compared with rank/score changes | Top-20/top-50 overlap, Spearman, Kendall τ over the top-100 union, rank-1 stability and largest top-20 rank shift per run: `DATA/sensitivity/optmining_sensitivity_2026_nsw.md`. |
| Robust and weight-sensitive sites | Site-stability table: 8 cells stay in the top 20 in all 27 runs; `S32.336_E148.286` (baseline 19) is kept in 70% of runs with ranks 9–116. |
| Interpretation, not only tables | Handover pack `02_Sensitivity_Analysis` §4: recommendations are stable at the level of areas (two REZ clusters); exact positions inside a cluster are not meaningful; the wind weight is the main lever. |
| Reproducible, names dataset/config | `python -m scripts.sensitivity_analysis` (~10 s); output records the integrated SHA-256 and the code commit. |

**Review outcome:** _pending PR review._

Refer to the [Sprint 4 Definition of Done](README.md#definition-of-done) for final acceptance.
