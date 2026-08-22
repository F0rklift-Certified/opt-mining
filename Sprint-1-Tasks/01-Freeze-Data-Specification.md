# Task 1 — Freeze the Sprint 0 Data Specification

**Sprint:** 1 (Week 1, Day 1)
**Assignee:** TBD
**Status:** Not Started
**Estimated Effort:** 1 day

---

## 1. Objective

Convert Sprint 0's exploration into a controlled implementation baseline: record the team's decisions on the seven open questions, write the frozen per-dataset data specification, and clean up the documentation inconsistencies Sprint 0 left behind. After this task, no dataset is added to the MVP without a documented gap, and every downstream task binds to `DATA/DATA_SPECIFICATION.md`.

## 2. Context & Frozen Decisions

The team has decided to adopt the recommendations recorded in `Sprint-0-Tasks/05-Data-Integration-Analysis-and-Site-Definition.md` §9 (mirrored in `pipeline/README.md` §Open Questions). The adopted values — all of which remain configurable parameters in code, never hard-coded:

| # | Question | Frozen decision |
|---|---|---|
| Q1 | Wind aggregation statistic (250 m → 5 km) | **Mean** is the default scoring input; **p90** carried as a feature; **max** reported as "best micro-site" explanation only |
| Q2 | Primary hub height | **100 m** primary (consistent with the fixed-hub capacity-factor layers); **150 m** carried as sensitivity layer |
| Q3 | Slope aggregation statistic | **Mean** slope is the penalty input; **p90** reported in explanations |
| Q4 | Population source for demand allocation | **ABS Census 2021 ERP at SA2 level** |
| Q5 | Demand measure | **Operational Demand** (not PRICE_AND_DEMAND) |
| Q6 | Protected-area exclusion rule | **Binary**: any CAPAD terrestrial intersection excludes the cell |
| Q7 | Infrastructure distance threshold | **No hard exclusion**; distance is a continuous penalty |

One **new** decision must be recorded here (it is not one of the seven): the coastal land rule — a cell is excluded as `NOT_LAND` when `land_fraction < 0.5` (parameter `min_land_fraction`, default 0.5, ABS ASGS outline as the mask). This is distinct from the binary CAPAD rule and must not be smuggled in silently.

## 3. Scope

**In:**
- Decision recording in the two open-questions tables
- `DATA/DATA_SPECIFICATION.md` (new)
- Documentation corrections (see plan)

**Out:**
- Any pipeline code (Tasks 2–12)
- Any data download
- New datasets of any kind — Sprint 0's inventory is the closed universe for the MVP

## 4. Inputs

- `Sprint-0-Tasks/05-Data-Integration-Analysis-and-Site-Definition.md` §4 (24-dataset consolidated inventory), §9 (open questions, `Decision` cells currently `_[Team decision]_`)
- `pipeline/README.md` §Open Questions (Team Decision Required) — table has no Decision column yet
- `DATA/wind-resource/DATA_PROVENANCE.md` — assumption #2 wrongly states 150 m as the representative height
- `DATA/geographic/DATA_PROVENANCE.md`, `DATA/geographic/metadata/source_register.md`/`.csv`, `DATA/infrastructure/metadata/source-register.csv` — existing per-domain registers the specification consolidates
- Sprint 0 task sheets 01–04 (data dictionaries and known-limitations sections)

## 5. Implementation Plan

- [ ] Fill the `Decision` column in Task 5 §9 with the frozen values above, plus a decision date (Sprint 1 Day 1).
- [ ] Add a `Decision` column to the `pipeline/README.md` §Open Questions table mirroring the same text.
- [ ] Fix `DATA/wind-resource/DATA_PROVENANCE.md` assumption #2: 100 m is primary, 150 m is the sensitivity layer (align with Task 1 §9 and Task 5 §6).
- [ ] Sweep `DATA/**/*.md` for references to deleted `scripts/*.py` files (`geo_fetch_vectors.py`, `download_gwa_sample.py`, `geo_derive_slope.py`, …) and repoint each to its `pipeline.<domain>.<stage>` equivalent. Also fix `pipeline/demand/README.md` (`pipelines.demand` → `pipeline.demand`; stale `Sprint-0-Tasks/Electricity Demand Data Investigation/` path).
- [ ] Delete the stale `scripts/__pycache__/` directory (the `scripts/` dir is gitignored and otherwise empty).
- [ ] Write `DATA/DATA_SPECIFICATION.md` with:
  - One section per MVP dataset: **source → variable(s) → units → CRS → resolution → temporal coverage/vintage → licence → known limitations → intended use in the model.** Datasets: GWA v4 (wind-speed 100/150 m, capacity-factor IEC2), AEMO Operational Demand, ABS SA2 boundaries + Census 2021 ERP, GA Power Lines / Substations / Major Power Stations 2026, AEMO KCI (context only — no coordinates), NSW EnergyCo REZ boundaries, SRTM GL3 (+ GL1 sensitivity), ABARES NLUM 250 m ALUM v8, DCCEEW CAPAD 2024 terrestrial, ABS ASGS 2021 (STE/AUS/UCL/SA2).
  - The **closed-universe rule**: no new datasets in Sprint 1 without a documented gap statement added to this file first.
  - The **known-facts register** (each with its Sprint 0 evidence pointer): GWA ocean pixels carry real values (land mask mandatory, ABS outline not Natural Earth); GWA GeoTIFFs embed no units/metadata — units asserted from provenance; NLUM water = primary class 6, dense urban = 5.4.x; CAPAD areas in hectares, dates in epoch-ms; substation voltage ≠ spare capacity; KCI has no coordinates; NSW1 = NSW + ACT; GWA bulk download forbidden — windowed `/vsicurl/` reads only; Lord Howe Island outside the NSW analysis bbox (documented out of scope).
  - The **frozen-decisions table** (Q1–Q7 + the new `min_land_fraction` rule), each row naming the configuration parameter and default that downstream tasks must bind to.
  - A placeholder §Grid section — completed by Task 2.

## 6. Outputs

| Output | Path |
|---|---|
| Frozen data specification | `DATA/DATA_SPECIFICATION.md` |
| Decision cells filled | `Sprint-0-Tasks/05-Data-Integration-Analysis-and-Site-Definition.md` §9 |
| Decision column added | `pipeline/README.md` §Open Questions |
| Height contradiction fixed | `DATA/wind-resource/DATA_PROVENANCE.md` |
| Stale references repointed | various `DATA/**/*.md`, `pipeline/demand/README.md` |

## 7. Configuration Parameters

This task defines (in prose) the parameter names later tasks implement:

| Parameter | Default | Defined by | Implemented in |
|---|---|---|---|
| `wind_scoring_stat` | `mean` | Q1 | Task 3 / Task 10 |
| `primary_height_m` | `100` | Q2 | Task 3 |
| `slope_penalty_stat` | `mean` | Q3 | Task 6 / Task 10 |
| `erp_year` | `2021` | Q4 | Task 4 |
| `protected_min_fraction` | `0.0` (binary) | Q6 | Task 6 / Task 7 |
| `min_land_fraction` | `0.5` | new decision | Task 7 |

## 8. Acceptance Criteria

- [ ] `grep -r "_\[Team decision\]_" Sprint-0-Tasks/ pipeline/` returns nothing.
- [ ] `grep -rn "scripts/" DATA --include="*.md"` returns no stale references to deleted script files.
- [ ] Every dataset used by Tasks 2–12 has a section in `DATA_SPECIFICATION.md` covering all nine required fields.
- [ ] Every frozen decision names its configuration parameter and default.
- [ ] The `min_land_fraction` land rule is recorded as a new, dated decision.

## 9. Tests

N/A — documentation task. The grep checks above stand in for tests.

## 10. Risks & Mitigations

- **Under-specification** (a later task hits an undocumented fact): mitigated by the known-facts register and by the rule that gaps found later are added to the spec first, then implemented.
- **Spec drift vs code**: every later task sheet's §2 quotes the spec values it binds to, so drift is visible at review.

## 11. Dependencies

**Blocked by:** None (Day 1 task).
**Blocks:** All of Tasks 2–12 (they bind to the spec).

## 12. Decision Log

| Date | Decision / Surprise | Rationale |
|---|---|---|
