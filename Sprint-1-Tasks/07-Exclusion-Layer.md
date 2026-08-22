# Task 7 — Implement the Exclusion Layer

**Sprint:** 1 (Week 2)
**Assignee:** TBD
**Status:** Not Started
**Estimated Effort:** 1 day

---

## 1. Objective

Make exclusion an explicit, inspectable pipeline stage — never logic buried inside scoring. Every cell gets an eligibility verdict and, when ineligible, machine-readable reason codes plus a human-readable reason. Reference output shape (from the sprint brief):

| Site | Eligible | Exclusion Reason |
|---|---|---|
| A | Yes | — |
| B | No | Protected area |
| C | No | Invalid/missing data |

## 2. Context & Frozen Decisions

- **Q6**: binary protected-area exclusion (any CAPAD intersection; `protected_min_fraction=0.0`).
- **Q7 + PKB**: slope and infrastructure distance are **penalties, not exclusions** — the slope exclusion rule exists but ships **disabled** by default.
- New Task 1 decision: `NOT_LAND` when `land_fraction < min_land_fraction` (default 0.5).
- Constitution: "Where critical data is missing, exclude the cell … never silently assign a normal ranking" → the `NO_DATA` rule.

## 3. Scope

**In:**
- `pipeline/exclusions/` package (rules + reason-code registry)
- Per-cell eligibility output + exclusion waterfall report

**Out:**
- Scoring of any kind (Task 10)
- New exclusion criteria beyond the register below (mining leases, native title are documented production-system gaps, not Sprint 1 scope)

## 4. Inputs

- Task 2 cell index (`land_fraction`)
- Tasks 3–6 feature CSVs under `DATA/features/`
- Frozen parameters from `DATA/DATA_SPECIFICATION.md`

## 5. Implementation Plan

- [ ] Create `pipeline/exclusions/config.py`:
  - `REASON_CODES` — ordered precedence list with human labels (used verbatim by the Task 11 query CLI):

    | Order | Code | Human label | Rule |
    |---|---|---|---|
    | 1 | `NO_DATA` | Invalid/missing data | any critical feature null/invalid (critical set: wind_speed_100m_mean, land_fraction, dist_transmission_km, slope_mean_deg) |
    | 2 | `NOT_LAND` | Outside NSW land area | `land_fraction < min_land_fraction` (default 0.5) |
    | 3 | `PROTECTED_AREA` | Protected area | `protected == True` (Q6 binary) |
    | 4 | `LANDUSE_WATER` | Water body | NLUM dominant class in primary class 6 |
    | 5 | `LANDUSE_URBAN` | Dense urban area | NLUM dominant class in 5.4.x |
    | 6 | `SLOPE_EXCEEDS_MAX` | Slope above threshold | only when `--exclusion-max-slope` is set; **disabled by default** |

- [ ] Create `pipeline/exclusions/apply.py` with `run(area_name="nsw", min_land_fraction=0.5, protected_min_fraction=0.0, max_slope_deg=None, verbose=False) -> dict`:
  1. Load cell index + the four feature CSVs (pandas), evaluate every rule for every cell — **all applicable reasons are recorded** (semicolon-joined in precedence order), not just the first; `exclusion_primary` = first by precedence; `eligible = (no reasons)`.
  2. Write the eligibility CSV.
  3. Write `exclusion_summary.md`: counts per reason code (non-exclusive), cumulative waterfall (cells remaining after each rule in precedence order), and the parameter values used.
- [ ] Register stage `exclusions.apply` (STAGES + `_get_runner` + `_build_kwargs`; new flags `--min-land-fraction`, `--exclusion-max-slope`).

## 6. Outputs

| Output | Path |
|---|---|
| Eligibility table | `DATA/integrated/optmining_exclusions_0.05deg_nsw.csv` |
| Waterfall report | `DATA/integrated/metadata/exclusion_summary.md` |

Eligibility-table columns:

| Column | dtype | Units | Description |
|---|---|---|---|
| cell_id | str | — | join key |
| eligible | bool | — | no exclusion rule fired |
| exclusion_reasons | str | — | semicolon-joined codes in precedence order; empty when eligible |
| exclusion_primary | str, nullable | — | first code by precedence; null when eligible |

## 7. Configuration Parameters

| Parameter | Default | CLI flag | Meaning |
|---|---|---|---|
| `min_land_fraction` | `0.5` | `--min-land-fraction` | NOT_LAND threshold (Task 1 decision) |
| `protected_min_fraction` | `0.0` | — | Q6 binary at default |
| `max_slope_deg` | `None` (disabled) | `--exclusion-max-slope` | optional hard slope rule |

## 8. Acceptance Criteria

- [ ] Every ineligible cell has ≥1 reason code; every eligible cell has none; `exclusion_primary` is always the precedence-first member of `exclusion_reasons`.
- [ ] With defaults, no cell is excluded by `SLOPE_EXCEEDS_MAX` (rule disabled).
- [ ] Waterfall totals reconcile: eligible + ineligible = land-cell count.
- [ ] White Rock and Sapphire cells are **eligible** (ground-truth survival — both sit outside CAPAD on agricultural land; Sprint 0 verified 23/23).
- [ ] Reason labels match the query CLI's display strings exactly (single source: `exclusions/config.py`).

## 9. Tests

`tests/test_exclusions_unit.py`: rule precedence on synthetic frames (cell violating protected+water lists both, primary=PROTECTED_AREA); NO_DATA fires on injected nulls in each critical feature; disabled slope rule fires nothing at default, fires correctly when set; reason-string formatting round-trips.

## 10. Risks & Mitigations

- **Semantics creep** (someone "just adds" an exclusion inside scoring later): the Task 10 sheet explicitly forbids reading exclusion inputs other than the `eligible` flag; validation Task 12 re-checks.
- **Dominant-class vs fraction ambiguity** for water/urban: default is dominant-class (documented); fraction thresholds noted as future parameters in Decision Log if wanted.

## 11. Dependencies

**Blocked by:** Tasks 2, 3, 4, 5, 6 (needs all features).
**Blocks:** Tasks 8, 9, 10, 12.

## 12. Decision Log

| Date | Decision / Surprise | Rationale |
|---|---|---|
