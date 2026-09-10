# Implementation Plan: Decision-Engine Specification & Frozen Configuration (S2-01)

## Overview

This plan authors the single authoritative decision-engine specification at `Sprint-2-Tasks/decision_engine_specification.md`, following the design. It is a **documentation and governance** deliverable — no pipeline code is written. Tasks build the document section by section (§1 purpose → §2 feature contract → §3 formula → §4 default weights → §5 normalisation → §6 frozen decisions → §7 traceability → §8 reconciliation), reconcile every parameter against the existing implementation (`pipeline/scoring/scoring_weights.yaml`, `pipeline/scoring/`), verify criterion column names against the integrated-table schema, add the README and data-specification cross-references, and gate the result with the two documentation-consistency checks (P1, P2) before Checkpoint A.

Because this is the Checkpoint-A artefact, the plan ends at a client checkpoint rather than a code merge. Any frozen-decision change discovered during reconciliation is applied across all recording locations under the data-specification section-8 process.

## Tasks

- [ ] 1. Scaffold the specification document and record its status
  - [ ] 1.1 Create `Sprint-2-Tasks/decision_engine_specification.md` with the §1–§8 section skeleton
    - Write §1: state that this is the single authoritative decision design and the Client Checkpoint A artefact; add placeholders for the Jira/PR references; commit to Screening_Language
    - Add the cross-reference stubs to be completed in task 7 (README + data specification)
    - _Requirements: 1.1, 1.3, 1.4_

- [ ] 2. Author §2 — the criteria feature contract
  - [ ] 2.1 Write the four Criteria_Group tables
    - One table per group (wind, demand proxy, infrastructure, geographic/environmental); columns: Criterion, integrated-table column, units, source, Direction, notes
    - Wind: name the GWA resource variable and justify the hub height/variable choice (2.3)
    - Demand: label the Demand_Proxy allocated below the AEMO region; never "measured local demand" (2.4)
    - Infrastructure: list distance-to-transmission, distance-to-substation, REZ membership; no undefined "infrastructure score" (2.5)
    - Geographic/environmental: list slope and any agreed non-hard-constraint feature (2.6)
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [ ] 2.2 Verify every Criterion column name against the integrated schema
    - Confirm each `column` in §2 is a member of `pipeline/integration/config.py` `OUTPUT_COLUMNS` / `SCORED_FEATURE_COLUMNS`; correct any mismatch (2.7)
    - **Property 1: Every criterion resolves to a real column** — every §2 `column` exists in the integrated feature table schema
    - _Requirements: 2.7_

- [ ] 3. Author §3 — the scoring formula
  - [ ] 3.1 Write the formula and its rules
    - State `S_i = Σ_k w_k · n_k(i)` with the weight-normalisation rule (division by the applied weight sum) (3.1, 3.2)
    - State the eligible-only rule and null score for excluded cells (3.3)
    - State the not-circular guarantee (wind is an input only) (3.4)
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [ ] 4. Author §4 — the default weights
  - [ ] 4.1 Reproduce the default weights as documented assumptions
    - Table of the six default criteria with weight, Direction and a non-empty rationale each (4.1)
    - Label the set as documented assumptions, not objectively correct business values (4.2)
    - **Property 3: Every default weight carries a rationale** — every §4 rationale is non-empty
    - _Requirements: 4.1, 4.2_

- [ ] 5. Author §5 — the normalisation method and policies
  - [ ] 5.1 Write the normalisation and outlier/missing/constant/boolean rules
    - Directional linear min-max per Criterion (5.1); bounds from the eligible population, fixed per run, not per UI filter (5.2); outlier policy (5.3); missing-value policy — never bias-imputed (5.4); constant-criterion rule, no divide-by-zero (5.5); boolean definitional mapping (5.6)
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

- [ ] 6. Author §6 — frozen decisions and change control
  - [ ] 6.1 Enumerate frozen decisions and their recording locations
    - Mark which parameters are Frozen_Decisions (6.1); state the data-specification section-8 process governs changes (6.2); enumerate every recording location — this spec, `pipeline/scoring/scoring_weights.yaml`, data-specification §4.5 (6.3)
    - **Property 4: Frozen decisions are fully enumerated** — every frozen parameter lists at least the three recording locations
    - _Requirements: 6.1, 6.2, 6.3_

- [ ] 7. Author §7 traceability and the §1 cross-references
  - [ ] 7.1 Build the traceability matrix and wire the cross-references
    - Map each Criterion → AC3, the default weights + normalisation rule → AC5, the four groups → guidance Step 3 (7.1, 7.2, 7.3)
    - Add the reference to the Decision_Engine_Spec from the pipeline README and the data specification (1.2)
    - **Property 5: Screening language only** — no absolute "best site" claim describes model output
    - _Requirements: 1.2, 7.1, 7.2, 7.3_

- [ ] 8. Author §8 — the reconciliation log against the existing implementation
  - [ ] 8.1 Reconcile every parameter against `pipeline/scoring/`
    - For each criterion in `scoring_weights.yaml`, add a reconciliation row: spec value vs implementation value vs status (`consistent`|`resolved`) vs resolution (4.3)
    - Where consistent, state so explicitly (4.4)
    - **Property 2: Reconciliation is complete** — every criterion in `scoring_weights.yaml` has a §8 row
    - _Requirements: 4.3, 4.4_

  - [ ] 8.2 Apply any frozen-decision change across all locations
    - IF reconciliation changes a frozen value, apply it in this spec, `scoring_weights.yaml`, and the data specification under the section-8 process, so no location is stale (6.4)
    - _Requirements: 6.4_

- [ ] 9. Checkpoint — Client Checkpoint A (Decision design)
  - Run the two documentation-consistency checks (P1 column-name, P2 reconciliation completeness); confirm §1–§8 complete; record the Jira/PR references in §1; present for client sign-off. Ask the user if questions arise.

## Notes

- This is a documentation deliverable; there are no code modules, no `run()` stage, and no CI test suite beyond the two documentation-consistency checks (P1, P2), which are run manually or as a lightweight doc check.
- The specification formalises an already-implemented design; §8 reconciliation is the core intellectual work — it makes the code and the document agree and records where they differed.
- Frozen decisions are the governance backbone: the enumeration in §6 is what lets a later weight change be applied consistently across the three recording locations instead of drifting.
- Blocks S2-04, S2-05 and S2-06: those specs build against the feature contract, formula and normalisation method frozen here, so this document should reach Checkpoint A sign-off before they start.
