# Task 12 — Validation / Sanity Check & Sprint Signoff

**Sprint:** 1 (Week 2)
**Assignee:** TBD; whole team reviews
**Status:** Not Started
**Estimated Effort:** 1.5 days

---

## 1. Objective

Prove the end-to-end dataset behaves sensibly against ground truth and Sprint 0's measured figures, and produce the sprint's validation report. House rule: **no silent passes** — every check reports expected / observed / status.

## 2. Context & Frozen Decisions

- Ground truth: the two operational New England wind farms — **White Rock** and **Sapphire** (`DATA/wind-resource/reference/nsw_wind_farms_new_england.csv`). Sprint 0 verified they survive every geographic constraint (23/23 checks); the integrated pipeline must agree.
- Reconciliation anchors: Sprint 0 grid figures (47,311 NSW-bbox cells / ~30,530 land in `DATA/integration/integration_analysis.md`), demand conservation (Task 4), wind statistic ordering (Task 3).
- Check thresholds (percentiles, top-share) are calibrated once during this task and stated in the report — they are sanity bounds, not tuned targets.

## 3. Scope

**In:**
- `pipeline/integration/validate.py` — new stage `integration.validate`
- The sprint validation report + signoff status table

**Out:**
- Fixing what the checks find (failures spawn Decision Log entries / follow-up items; fixes happen in the owning task)

## 4. Inputs

- Full integrated dataset + shortlist + run metadata (Tasks 8–11)
- `GridSpec` for locating ground-truth coordinates
- Sprint 0 references: `integration_analysis.md`, `aggregation_sensitivity.md`, `validation_geographic.md`, `slope_derivation.md`

## 5. Implementation Plan

- [ ] Create `pipeline/integration/validate.py` with `run(area_name="nsw", verbose=False) -> dict`, a registry of named checks (pattern: `pipeline/demand/validate.py`'s `CHECKS` list), each returning (passed, expected, observed, note):
  1. **Wind-farm survival**: White Rock and Sapphire cells are `eligible = True`.
  2. **Wind-farm resource ranking**: both cells' `wind_speed_100m_mean` above the **70th percentile** of eligible cells; overall `rank` within the top **20%** (thresholds stated; Sprint 0 found these sites at p80–p89 on cell means, so 70/20 gives honest headroom — recalibrate once with rationale if needed).
  3. **Exclusion spot checks**: a Kosciuszko NP interior cell → `PROTECTED_AREA`; a Sydney CBD cell → `LANDUSE_URBAN`; an ocean-dominated coastal cell → `NOT_LAND`.
  4. **Grid reconciliation**: bbox cell count = 47,311; land-cell count within ±2% of 30,530; integrated row count = grid land count.
  5. **Demand conservation** (re-run of Task 4's checks on the final table): population and MW mass within 1%.
  6. **Statistic ordering**: `mean ≤ p90 ≤ max` for wind; `slope_mean_deg ≤ slope_p90_deg` for all cells.
  7. **Exclusion integrity**: eligible ⇔ empty reasons; `missing` quality flags ⇔ `NO_DATA` (Task 9 rule re-checked end-to-end).
  8. **Weight sensitivity**: re-score with wind weight 0.8 — top-50 membership changes by a nonzero amount but White Rock/Sapphire stay top-20% (score reacts to weights; ground truth is robust to them).
  9. **Determinism**: re-running assemble + score on unchanged inputs is byte-identical (hash comparison via `.meta.json`).
- [ ] Register stage `integration.validate` in the orchestrator.
- [ ] Write `DATA/integrated/metadata/validation_integration.md` — one row per check, expected/observed/status, plus parameter values and input hashes.
- [ ] **Signoff**: append the sprint status table to `Sprint-1-Tasks/00-Sprint-1-Overview.md` (task → status → deviations) and set each task sheet's `Status:` line; every failed check has a written explanation and a follow-up item before the sprint is called done.

## 6. Outputs

| Output | Path |
|---|---|
| Validation report | `DATA/integrated/metadata/validation_integration.md` |
| Signoff table | appended to `Sprint-1-Tasks/00-Sprint-1-Overview.md` |

## 7. Configuration Parameters

| Parameter | Default | CLI flag | Meaning |
|---|---|---|---|
| `wind_percentile_floor` | 70 | — | check 2 threshold |
| `rank_top_share` | 0.20 | — | check 2 threshold |

## 8. Acceptance Criteria

- [ ] All nine check families run and report expected/observed/status; zero silent passes.
- [ ] Checks 1, 3, 4, 6, 7 pass outright (structural correctness — failures here block signoff).
- [ ] Checks 2, 5, 8 pass, or each failure has a written explanation + follow-up item agreed by the team.
- [ ] The report is committed and referenced from `pipeline/README.md` §Validation Reports.

## 9. Tests

`tests/test_integration_validate_unit.py`: check registry runs on synthetic mini-tables; each check trips correctly on a deliberately broken fixture (farm excluded, count off, mean>p90 injected).

## 10. Risks & Mitigations

- **Ground-truth cells straddle boundaries** (farm coordinates near a cell edge): resolve via `GridSpec.locate`'s documented boundary rule; if a farm's turbines span two cells, check the better cell and note it.
- **Threshold debates**: thresholds are parameters with recorded rationale; the report shows observed percentiles so recalibration is evidence-based.

## 11. Dependencies

**Blocked by:** Tasks 8–11 (check design can be drafted from Day 8 in parallel).
**Blocks:** Sprint signoff.

## 12. Decision Log

| Date | Decision / Surprise | Rationale |
|---|---|---|
