# S2-03: Harden the Hard-Exclusion Component (Reasons + Tests)

**Type:** Story
**Priority:** High
**Story Points:** 3
**Labels:** exclusions, decision-engine
**Blocked by:** S2-02
**Blocks:** S2-06

---

## Objective

Confirm and harden the dedicated hard-exclusion component so exclusions are applied **before** scoring, every excluded cell retains a machine-readable and human-readable reason, and a high wind score can never compensate for an exclusion.

---

## Context

Guidance Step 2. Sprint 1 delivered `pipeline/exclusions/` (S1-07) with configurable rules (`exclusion_rules.yaml`), a pure rule engine (`rules.py`) and an Eligibility_Table with reasons. This task raises that module to the combined-sprint acceptance bar rather than rebuilding it: verify reason retention in both machine- and human-readable form, confirm the exclusion→scoring ordering, keep thresholds configurable, and bring test coverage up to standard.

---

## Deliverables

1. Verified exclusion component with per-cell `eligible` + `exclusion_reason` (machine + human readable).
2. Confirmation that scoring consumes eligibility and never scores excluded cells.
3. Rule documentation and independent per-rule tests.

---

## Acceptance Criteria

- [ ] Hard exclusions are applied **before** suitability scoring; excluded cells are never scored (satisfies **AC2**)
- [ ] Each excluded cell retains a **machine-readable** reason code AND a **human-readable** reason string
- [ ] A cell can carry multiple exclusion reasons
- [ ] A high wind score cannot override a hard exclusion — verified by a controlled test case
- [ ] Thresholds/rules remain **configurable** (YAML), not hard-coded; every rule is documented
- [ ] Exclusion summary statistics are produced (total, eligible %, excluded by reason)
- [ ] The same rule-handling logic is applied consistently across all exclusion layers (no fix-one-leave-others)
- [ ] Unit tests cover each rule independently, plus the compensation-guard case

---

## Technical Notes

- Build on `pipeline/exclusions/` — do not create a parallel exclusion path. Extend `exclusion_rules.yaml` and `rules.py`.
- The scoring module (`pipeline/scoring/`) already assigns null score/rank/contributions to ineligible cells; this task verifies that contract end-to-end and adds the machine-readable reason code if only a human string exists today.
- Cross-cutting impact: the reason schema is consumed by the S2-06 explanation generator and surfaced in the S3-05 site-detail view — coordinate the reason-code vocabulary with those tasks.
