# S2-02: Freeze & Validate the Sprint 1 Integrated Dataset (Input Contract)

**Type:** Story
**Priority:** Highest
**Story Points:** 3
**Labels:** validation, data-quality, decision-engine
**Blocked by:** S2-01
**Blocks:** S2-03, S2-04

---

## Objective

Adopt the completed Sprint 1 integrated NSW dataset as the frozen baseline input to the decision engine and add automated data-quality validation so the application fails clearly (or flags a problem) rather than silently ranking from invalid input.

---

## Context

Guidance Step 1: use the Sprint 1 integrated dataset as the baseline; do not restart data discovery unless a critical defect is found. Sprint 1 produced `DATA/integration/` (S1-08 integrated feature table + S1-09 confidence) and a structural `pipeline/validate.py`. This task defines the **input contract** the decision engine trusts, and extends validation to the guarantees the guidance requires: required columns, unique IDs, valid geometries/coordinates, expected units/ranges, missing-value handling and eligibility fields.

---

## Deliverables

1. A frozen, versioned reference to the Sprint 1 integrated dataset (path + hash/version).
2. A validation component that gates the dataset before scoring.
3. A data-quality report (expected vs observed vs pass/fail).

---

## Acceptance Criteria

- [ ] The Sprint 1 integrated dataset is consumed by the engine reproducibly — path, version and hash recorded (satisfies **AC1**)
- [ ] Automated checks exist for: required columns present; `cell_id` unique and non-null; valid coordinates/geometries; values within expected units/ranges; missing-value counts per feature; eligibility field present and boolean
- [ ] Each check reports **expected vs observed vs pass/fail** (no silent passes)
- [ ] On failure the engine **halts or flags** the data-quality problem — it never emits rankings from invalid input
- [ ] The check reuses/extends the existing `pipeline/validate.py` tier rather than duplicating logic
- [ ] A machine-readable validation result is available to the service layer (for the web app to surface a data-quality banner)
- [ ] Unit tests cover each check with a known-good and a known-bad fixture

---

## Technical Notes

- This is the "Validation / feature preparation" box in the guidance architecture (§3), sitting between the Sprint 1 data and hard exclusions.
- Cross-cutting impact: this defines what S2-03, S2-04 and S2-05 may assume about their input. If the integrated-table schema changes, this contract and its consumers change together.
- Do not re-open Sprint 1 data discovery. A genuine critical defect should be logged as a Sprint 1 bug, not fixed by silently mutating the frozen dataset.
