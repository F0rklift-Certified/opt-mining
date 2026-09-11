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

- [x] The Sprint 1 integrated dataset is consumed by the engine reproducibly — path, version and hash recorded (satisfies **AC1**)
- [x] Automated checks exist for: required columns present; `cell_id` unique and non-null; valid coordinates/geometries; values within expected units/ranges; missing-value counts per feature; eligibility field present and boolean
- [x] Each check reports **expected vs observed vs pass/fail** (no silent passes)
- [x] On failure the engine **halts or flags** the data-quality problem — it never emits rankings from invalid input
- [x] The check reuses/extends the existing `pipeline/validate.py` tier rather than duplicating logic
- [x] A machine-readable validation result is available to the service layer (for the web app to surface a data-quality banner)
- [x] Unit tests cover each check with a known-good and a known-bad fixture

---

## Technical Notes

- This is the "Validation / feature preparation" box in the guidance architecture (§3), sitting between the Sprint 1 data and hard exclusions.
- Cross-cutting impact: this defines what S2-03, S2-04 and S2-05 may assume about their input. If the integrated-table schema changes, this contract and its consumers change together.
- Do not re-open Sprint 1 data discovery. A genuine critical defect should be logged as a Sprint 1 bug, not fixed by silently mutating the frozen dataset.

---

## Completion Notes

Delivered on branch `sprint-2-and-3-kickoff` (commits `feat(validate): scaffold S2-02 …` through `docs(validate): document S2-02 consumer contract, provenance and README`).

**Approach.** The input contract was built by **extending the existing `pipeline/validate.py` tier**, not by writing a parallel validator — a divergent second validation path is exactly the cross-component inconsistency the project rules forbid. Sprint 1 data discovery was not re-opened; the frozen S1-08 integrated table is treated as strictly read-only and the gate is a **pure reporter** — it computes expected/observed/pass-fail records and writes sidecars, but never mutates the dataset and never decides on its own to halt. The Halt_Or_Flag decision lives at the engine boundary (S2-03+), which reads the machine-readable `all_passed` verdict.

**What was built.**

- `pipeline/validate.py`
  - `freeze_baseline(...)` — records the frozen reference to the S1-08 integrated table: project-relative path, layer, vintage `2026`, SHA-256, byte count, human-readable size, storage CRS `EPSG:4326`, computation CRS `EPSG:3577`, and a UTC freeze timestamp. Read-only on the dataset (satisfies AC1).
  - `_run_integrated_input_checks(...)` — the 12-check input-contract battery, each emitting a `{name, expected, observed, passed}` Check_Record (no silent passes):
    1. baseline hash matches the frozen reference (Hash_Drift → FAIL)
    2. required columns present (read from the schema authority, never re-typed)
    3. scored feature columns present (superset of the S2-01 §2 frozen criteria)
    4. `cell_id` non-null
    5. `cell_id` unique
    6. coordinates valid and inside the NSW envelope
    7. geometry validity AND storage CRS is `EPSG:4326` (never reprojected)
    8. units/ranges per scored column (one record per column with a Sanity_Range)
    9. missing-value counts per feature (all ten scored columns; count reported, never a silent pass)
    10. `eligible` present, boolean, no nulls (re-asserts the `merge.py` production invariant verbatim)
    11. `eligible` / `exclusion_reason` consistency (re-asserts the `merge.py` invariant)
    12. at least one Eligible_Cell (zero eligible cells fails, so a ranking is never emitted from an empty population)
  - `write_validation_result` / `write_validation_report` / `write_validation_outputs` — pure emitters that build the Validation_Result object and render the `banner()`-stamped Validation_Report; atomic writes via `pipeline/common/geo.atomic_write_json`.
  - `run(verbose=False, ...)` — wires the input gate into the stage contract as a pure reporter, exposing `integrated_baseline`, `integrated_input_checks`, `integrated_input_result` (JSON sidecar path) and `all_passed` in the returned dict. `all_passed` is the conjunction of every Check_Record (with the hash match folded in as check 1), and is `False` for an absent table — the empty battery is never a silent pass.
- **Machine-readable outputs** for the service layer (so the web app can surface a data-quality banner):
  - `DATA/integration/metadata/integrated_baseline_manifest.json` (Baseline_Manifest)
  - `DATA/integration/metadata/integrated_input_validation.json` (Validation_Result) + `.md` sibling report
- **Provenance** recorded in `DATA/integration/DATA_PROVENANCE.md` (both JSON artefacts documented as validator-derived, atomic, regenerable via `python -m pipeline --only validate`).
- **Docs**: `pipeline/README.md` updated to document the S2-02 consumer contract.
- **Tests**: known-good/known-bad fixture coverage per check plus property and run() integration tests — `tests/test_freeze_baseline.py`, `tests/test_input_checks_{schema,geometry,ranges,eligibility}.py`, `tests/test_validation_emitter.py`, `tests/test_run_input_contract_integration.py`, `tests/test_input_contract_properties_p1.py`, `tests/test_input_contract_properties_p3.py`, `tests/test_input_contract_properties_p4_p8.py`, plus shared `tests/integration/integrated_fixtures.py`.

**Verification.** The S2-02 input-contract test suite: 54 passed (0 failures).

**Cross-cutting impact.** This defines the input contract S2-03, S2-04 and S2-05 may assume. It re-asserts the `pipeline/integration/merge.py` eligibility/exclusion invariants verbatim rather than reinventing them, so the two gates stay textually aligned. If the integrated-table schema changes, this contract and its consumers change together.

**Frozen decisions.** No frozen parameter was changed and Sprint 1 data discovery was not re-opened — the frozen S1-08 dataset is read-only, so no data-spec §8 change-control process was triggered.
