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

- [x] Hard exclusions are applied **before** suitability scoring; excluded cells are never scored (satisfies **AC2**)
- [x] Each excluded cell retains a **machine-readable** reason code AND a **human-readable** reason string
- [x] A cell can carry multiple exclusion reasons
- [x] A high wind score cannot override a hard exclusion — verified by a controlled test case
- [x] Thresholds/rules remain **configurable** (YAML), not hard-coded; every rule is documented
- [x] Exclusion summary statistics are produced (total, eligible %, excluded by reason)
- [x] The same rule-handling logic is applied consistently across all exclusion layers (no fix-one-leave-others)
- [x] Unit tests cover each rule independently, plus the compensation-guard case

---

## Technical Notes

- Build on `pipeline/exclusions/` — do not create a parallel exclusion path. Extend `exclusion_rules.yaml` and `rules.py`.
- The scoring module (`pipeline/scoring/`) already assigns null score/rank/contributions to ineligible cells; this task verifies that contract end-to-end and adds the machine-readable reason code if only a human string exists today.
- Cross-cutting impact: the reason schema is consumed by the S2-06 explanation generator and surfaced in the S3-05 site-detail view — coordinate the reason-code vocabulary with those tasks.

---

## Completion Notes

Delivered on branch `s2-03` (commit `feat: harden hard-exclusion component with paired reason schema`).

**Approach.** The existing `pipeline/exclusions/` module (S1-07) was **hardened, not rebuilt** — a parallel exclusion path is exactly the cross-component inconsistency the project rules forbid. The rule engine stays data-driven (rules are YAML, not code) and the same rule-handling logic is applied uniformly to every rule, so no rule is fixed while others are left behind. The one substantive addition is a machine+human **paired reason schema** produced from a single rule evaluation, so the human string, the machine code list and the structured pairs can never drift.

**What was built / verified.**

- `pipeline/exclusions/rules.py`
  - `evaluate_cell_detailed(cell_fields, rules) -> (eligible, reasons)` — the single source of the paired reason schema: `reasons` is an ordered list of `{"code": rule_name, "text": human_reason}` pairs. The `code` is the rule `name` (the frozen exclusion reason-code vocabulary), the `text` is the formatted `reason_template`/`description`.
  - `evaluate_cell(...)` re-derived as a thin wrapper over `evaluate_cell_detailed`, so the human-readable `exclusion_reason`, the machine-readable code list, and the structured pairs are all derived from one evaluation and cannot disagree.
  - Rules are evaluated independently and deterministically (rule-config order), so a cell can carry **multiple** exclusion reasons. A malformed rules file raises `RuleConfigError` (loud halt, never a silent partial rule set).
- `pipeline/exclusions/apply.py`
  - The Eligibility_Table now carries the reason in three consistent forms: `exclusion_reason` (human text), `triggered_rules` (machine codes), and `exclusion_reasons` (JSON list of `{code, text}` pairs, null for eligible cells) — the paired form the S2-06 explanation engine consumes directly.
  - `summarise(...)` produces exclusion summary statistics (total, eligible count/%, excluded count/%, and an excluded-by-rule breakdown), surfaced both to the run log and the method report.
  - `validate(...)` extended with a no-silent-passes check that the structured `exclusion_reasons` pairs stay consistent with `eligible` / `triggered_rules` (codes match, texts non-empty, null iff eligible) for every row.
  - The `exclusion_summary.md` report documents every rule verbatim and the reason schema.
- `pipeline/exclusions/config.py`, `__init__.py` — supporting config/docstring for the paired schema.
- **Exclusion → scoring ordering and the compensation guard.** `tests/scoring/test_exclusion_scoring_guard.py` verifies the scoring stage consumes eligibility and never scores an excluded cell — an ineligible cell gets null score/rank/contributions — so a high wind score can never override a hard exclusion.

**Verification.** `tests/exclusions/test_exclusions.py` and `tests/scoring/test_exclusion_scoring_guard.py`: 61 passed (0 failures). Coverage includes each rule independently, the multi-reason case, the paired-schema consistency check, and the wind-cannot-compensate guard.

**Cross-cutting impact.** The `code` values are the frozen exclusion reason-code vocabulary recorded in the decision-engine specification §6 (frozen decision F16) — this branch adds that section to `decision_engine_specification.md`. The reason-code vocabulary is consumed by the S2-06 explanation engine and surfaced in the S3-05 site-detail view; adding or renaming a code follows the spec's change-control process.

**Frozen decisions.** The exclusion thresholds remain configurable in `exclusion_rules.yaml` (not hard-coded). The reason-code vocabulary is newly frozen as F16 in the decision-engine spec on this branch; no pre-existing frozen threshold was changed, so no data-spec §8 change-control process was triggered for a threshold value.
