# Task 9 — Data Quality and Confidence

**Sprint:** 1 (Week 2)
**Assignee:** TBD
**Status:** Not Started
**Estimated Effort:** 0.5 day

---

## 1. Objective

Attach per-domain quality flags to every cell so users (and the query CLI) can see how much to trust each number — and so missing data is visibly excluded, never silently ranked.

## 2. Context & Frozen Decisions

- Constitution: "Where critical data is missing, exclude the cell … never silently assign a normal ranking." The quality layer is the visible counterpart of Task 7's `NO_DATA` rule — the two must agree.
- Numeric confidence already exists as `*_valid_fraction` columns (e.g. `wind_valid_fraction` from Task 3); this task adds the **coarse, human-facing flags** the CLI surfaces.

## 3. Scope

**In:**
- `pipeline/features/quality.py` — annotation module called by `features.assemble`
- `quality_report.md`

**Out:**
- New confidence statistics per feature (valid fractions are Tasks 3/6 outputs)
- Any change to exclusion logic (consistency is checked, not created, here)

## 4. Inputs

- Assembled table pre-flags (Task 8), including `wind_valid_fraction`, `land_fraction`, per-column null patterns
- Task 7 eligibility columns

## 5. Implementation Plan

- [ ] Create `pipeline/features/quality.py` with `annotate(frame) -> frame` adding four flags:

  | Flag | `ok` | `partial` | `missing` |
  |---|---|---|---|
  | q_wind | all wind features present, `wind_valid_fraction ≥ 0.9` | present but `0.5 ≤ wind_valid_fraction < 0.9` (typically coastal) | any wind critical feature null or `wind_valid_fraction < 0.5` |
  | q_demand | population + proxy present | population present but from fallback source (G01) — flag propagated from Task 4 metadata | either null |
  | q_infra | both distances + REZ present | REZ undetermined but distances present | any distance null |
  | q_geo | elevation + slope + landuse + protected present | landuse or protected degraded (warp edge) | elevation/slope null |

- [ ] Wire `annotate` into `features.assemble` (Task 8 left a forwards-compatible call site).
- [ ] Consistency rule implemented as a hard check inside `annotate`: any `missing` flag on a critical domain ⇒ the cell carries `NO_DATA` in `exclusion_reasons` (and vice-versa for critical features). Violation count must be zero; non-zero fails the stage loudly.
- [ ] Write `DATA/integrated/metadata/quality_report.md`: flag counts per domain, cross-tab of flags vs eligibility, and a short spatial-pattern note (e.g. "partial wind flags concentrate on the coastline, as expected from land masking").

## 6. Outputs

| Output | Path |
|---|---|
| `q_wind, q_demand, q_infra, q_geo` columns | appended into `DATA/integrated/optmining_site-screening_0.05deg_nsw.csv` (via assemble) |
| Quality report | `DATA/integrated/metadata/quality_report.md` |

## 7. Configuration Parameters

| Parameter | Default | CLI flag | Meaning |
|---|---|---|---|
| `ok_valid_fraction` | `0.9` | — | ok/partial boundary |
| `min_valid_fraction` | `0.5` | — | partial/missing boundary (matches Task 7 critical rule) |

## 8. Acceptance Criteria

- [ ] `missing` ⇔ `NO_DATA` consistency violations = 0 (stage-enforced).
- [ ] Every cell has all four flags; value set is exactly {ok, partial, missing}.
- [ ] Coastal cells with `0.5 ≤ wind_valid_fraction < 0.9` are `q_wind = partial` (spot check against the map).
- [ ] The query CLI (Task 11) displays the flags — re-checked there.

## 9. Tests

`tests/test_quality_unit.py`: flag boundaries at exactly 0.9/0.5; consistency check trips on a synthetic frame with missing-but-not-excluded cell; fallback-source demand flag propagation.

## 10. Risks & Mitigations

- **Flag semantics debated late**: thresholds are parameters; the report's cross-tab makes their effect visible for cheap iteration.

## 11. Dependencies

**Blocked by:** Tasks 7, 8.
**Blocks:** Tasks 10 (scores only eligible cells, reads flags for reporting), 11, 12.

## 12. Decision Log

| Date | Decision / Surprise | Rationale |
|---|---|---|
