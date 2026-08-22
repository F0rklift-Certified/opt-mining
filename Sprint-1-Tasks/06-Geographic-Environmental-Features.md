# Task 6 — Geographic and Environmental Features

**Sprint:** 1 (Week 1–2)
**Assignee:** TBD
**Status:** Not Started
**Estimated Effort:** 2 days

---

## 1. Objective

Derive per-cell terrain and constraint features across all of NSW: elevation, slope (mean + p90), land-use composition (water/urban fractions, dominant class), and protected-area coverage.

## 2. Context & Frozen Decisions

- **Q3**: **mean slope** is the penalty input; **p90** is reported in explanations. Sprint 0 evidence for why the statistic matters: at a 10° threshold the excluded share is 11.6% (mean) vs 42.1% (p90) vs 85.7% (max).
- **Q6**: protected = **binary** — any CAPAD terrestrial intersection (`protected_min_fraction = 0.0`, kept as a parameter).
- DEM: **SRTM GL3 (~90 m)** for screening (GL1 sensitivity only — GL1-derived slope runs +1.31° hotter; Sprint 0 `slope_derivation.md`). GA DEM services are 403 to scripts; OpenTopography S3 VRT is the working route.
- Slope is computed on **native 90 m resolution BEFORE aggregation** — never from aggregated elevation (aggregation-then-slope systematically understates terrain).
- NLUM is the only native-EPSG:3577 raster (250 m); warp decision from Task 5 §5b: nearest-neighbour to the 4326 subgrid.

## 3. Scope

**In:**
- Elevation + slope from SRTM GL3, NSW-wide
- NLUM land-use fractions and dominant class
- CAPAD protected fraction + binary flag
- Bundled cleanup: give `pipeline/geographic/derive.py` `run()` proper `bbox`/`area_name` parameters (currently hard-coded to the New England / Glen Innes areas)

**Out:**
- TRI at NSW scale (New England TRI exists from Sprint 0; NSW-wide deferred unless slope proves insufficient — record in Decision Log if pulled in)
- Roads/OSM (deferred in Sprint 0, stays deferred)
- GL1 30 m processing beyond the existing Glen Innes sensitivity sample

## 4. Inputs

- SRTM GL3 via `/vsicurl/` VRT: `https://opentopography.s3.sdsc.edu/raster/SRTM_GL3/SRTM_GL3_srtm.vrt` (existing `_fetch_srtm` in `pipeline/geographic/download.py`); **NoData for GL3 is 0** (conflates sea level — mask via the land mask, not the NoData value)
- NLUM: `DATA/geographic/raw/NLUM_v7_1_250m_ALUMV8_2020_21_alb_20260814.zip` (present locally; `/vsizip/` read via `_fetch_nlum` pattern) + class table `DATA/geographic/landuse/abares_alumv8_class_table.csv`
- CAPAD: `DATA/geographic/protected/dcceew_capad-terrestrial_2024_nsw.geojson` (1,018 NSW features, committed)
- Horn slope + `block_stat` in `pipeline/geographic/derive.py:119-131`; rasterize pattern `pipeline/validate.py:158-165`
- Task 2 cell index + fine land mask

## 5. Implementation Plan

- [ ] Create `pipeline/features/geographic.py` with `run(area_name="nsw", slope_stats=("mean", "p90"), strip_cell_rows=10, verbose=False) -> dict`:
  1. **SRTM strip processing.** Full-NSW GL3 is 15,168 × 11,220 px ≈ 680 MB as float32 — never load whole. Read horizontal strips of `strip_cell_rows` cell-rows (10 cell-rows = 600 DEM rows ≈ 36 MB) with 1-px overlap for the 3×3 Horn kernel; per strip: Horn slope on native 90 m, then per-cell `block_stat` (60×60 GL3 px per 0.05° cell) for elevation mean and slope mean/p90. Cache strips under `DATA/geographic/raw/` (gitignored) so reruns are resumable.
  2. Document (report + docstring) the half-pixel registration offset between the SRTM and GWA lattices (~45 m) as negligible at 5 km cells.
  3. **NLUM**: `rasterio.warp.reproject` (nearest) from native 3577/250 m onto the NSW 0.0025° subgrid; per-cell from the 20×20 block: `water_fraction` (primary class 6), `urban_fraction` (5.4.x tertiary codes), dominant class code + label from the class table.
  4. **CAPAD**: rasterize NSW terrestrial polygons onto the subgrid → `protected_fraction` = block mean; `protected = protected_fraction > protected_min_fraction` (default 0.0 → any intersection, Q6).
  5. Join onto the cell index; write CSV + `banner()` report (report includes the slope-statistic threshold table reproducing the Sprint 0 ordering as a self-check).
- [ ] Cleanup: refactor `pipeline/geographic/derive.py` `run()` to accept `bbox`/`area_name` like its sibling stages (Sprint 0 outputs regenerate identically when called with the old defaults — verify once).

## 6. Outputs

| Output | Path |
|---|---|
| Geographic feature table | `DATA/features/optmining_geographic-features_0.05deg_nsw.csv` |
| Report | `DATA/features/metadata/geographic_features_report.md` |

Feature-table columns:

| Column | dtype | Units | Description |
|---|---|---|---|
| cell_id | str | — | join key |
| elevation_mean_m | float | m ASL | GL3 block mean |
| slope_mean_deg | float | degrees | penalty input (Q3); Horn slope on native 90 m |
| slope_p90_deg | float | degrees | reported in explanations (Q3) |
| landuse_dominant_class | int | ALUM v8 tertiary code | modal class of the cell |
| landuse_dominant_label | str | — | decoded from the class table |
| water_fraction | float | 0–1 | NLUM primary class 6 share |
| urban_fraction | float | 0–1 | NLUM 5.4.x share |
| protected_fraction | float | 0–1 | CAPAD terrestrial coverage share |
| protected | bool | — | `protected_fraction > protected_min_fraction` (Q6 binary at default) |

## 7. Configuration Parameters

| Parameter | Default | CLI flag | Meaning |
|---|---|---|---|
| `slope_stats` | `("mean","p90")` | — | per-cell slope statistics |
| `strip_cell_rows` | `10` | — | SRTM strip height (memory/IO trade-off) |
| `protected_min_fraction` | `0.0` | — | Q6 binary rule; >0 would switch to fractional |

## 8. Acceptance Criteria

- [ ] Armidale and Glen Innes spot elevations match Sprint 0 `validation_geographic.md` ground truth within its stated tolerance.
- [ ] Every cell overlapping Kosciuszko National Park has `protected = True`; state-wide protected share is plausible against CAPAD's published NSW terrestrial coverage (~9–10%).
- [ ] Slope exclusion shares at a 10° threshold reproduce the Sprint 0 ordering: mean < p90 (< max if computed) — report table, gate on ordering only.
- [ ] White Rock / Sapphire cells: agricultural dominant land use, slope consistent with Sprint 0 point samples (7.0° / 4.3° at point scale — cell means will differ; report both).
- [ ] Row count = land-cell count; strips stitch without seams (no NaN bands at strip boundaries — assert in stage).

## 9. Tests

`tests/test_features_geographic_unit.py`: strip-overlap correctness (slope of a synthetic ramp is identical computed whole vs in strips); fraction arithmetic on synthetic class rasters; dominant-class tie rule (documented, deterministic); protected binary vs fractional switch behaviour.

## 10. Risks & Mitigations

- **OpenTopography throughput** over ~170 M px: resumable strip cache; run overnight if needed; GL3 window sizes already proven in Sprint 0 at smaller scale.
- **NLUM warp artefacts** at 250 m→subgrid: nearest-neighbour only (categorical); fractions computed post-warp are approximations — stated in the report.

## 11. Dependencies

**Blocked by:** Task 1 (spec), Task 2 (cell index + land mask).
**Blocks:** Tasks 7, 8, 10, 12.

## 12. Decision Log

| Date | Decision / Surprise | Rationale |
|---|---|---|
