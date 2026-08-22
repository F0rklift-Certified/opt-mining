# Task 3 — Build the Wind Feature Layer

**Sprint:** 1 (Week 1)
**Assignee:** TBD
**Status:** Not Started
**Estimated Effort:** 2 days

---

## 1. Objective

Map Global Wind Atlas v4 wind information onto every valid NSW analysis cell, generated automatically end-to-end by the pipeline. **No hand-prepared CSVs at any point in the chain** — every number traces from the GWA CDN through recorded code.

## 2. Context & Frozen Decisions

- **Q1**: per-cell statistics mean, p90 and max are all computed; **mean is the default scoring input**, p90 travels as a feature, max is explanation-only ("best micro-site").
- **Q2**: **100 m** is the primary height; **150 m** mean is carried as a sensitivity feature. Capacity factor IEC2 (fixed 100 m hub) is the interpretable presentation layer.
- GWA facts from the spec: EPSG:4326, 0.0025° native, ocean pixels contain real (higher) values → the land mask is mandatory before aggregation; CC BY 4.0; API terms forbid bulk download — windowed `/vsicurl/` reads only (NSW-scale is compliant); no embedded units (m/s asserted from provenance).

## 3. Scope

**In:**
- NSW-window GWA clips (one-time download, persisted locally so later stages are offline)
- `pipeline/features/wind.py` — per-cell aggregation stage
- Bundled cleanup: parameterise the hard-coded `new-england-rez` slugs in `pipeline/wind/analyse.py` and `pipeline/wind/validate.py`

**Out:**
- Scoring/normalisation (Task 10)
- Weibull/air-density layers (registered, not needed for V1)
- Any full-country raster download (forbidden by GWA terms)

## 4. Inputs

- GWA layers via the existing windowed-clip stage `pipeline/wind/download.py` (`_clip_gwa_sample`, provenance manifest): `wind-speed` 100 m, `wind-speed` 150 m, `capacity-factor_IEC2` (optionally `power-density` 100 m, explanation-only)
- Task 2 outputs: cell index CSV + fine land mask `DATA/grid/optmining_landmask_0.0025deg_nsw.tif`
- Aggregation machinery to reuse: `_blockify` + `STATISTICS` (`pipeline/wind/analyse.py:37-54`), `block_stat` (`pipeline/geographic/derive.py:119-131`), the reshape-to-`(rows, 20, cols, 20)` + nan-stat pattern in `pipeline/validate.py:184-200`

## 5. Implementation Plan

- [ ] Run `python -m pipeline --only wind.download --bbox 141.0 -37.5 153.64 -28.15 --area-name nsw --heights 100 150 --turbine-class IEC2` → NSW clips (~5057×3741 px, ~76 MB in memory per layer; load one layer at a time, never concurrently). Clips persist under `DATA/wind-resource/` and are gitignored if >10 MB guardrail requires (regenerable from the manifest).
- [ ] Create `pipeline/features/wind.py` with `run(area_name="nsw", heights=(100, 150), stats=("mean", "p90", "max"), turbine_classes=("IEC2",), verbose=False) -> dict`:
  1. Open the local NSW clip; verify its offsets into the national GWA grid are 20-pixel-aligned with the Task 2 grid (fail loud otherwise).
  2. Apply the fine land mask: ocean subpixels → NaN **before** any statistic.
  3. Reshape to `(n_rows, 20, n_cols, 20)`; compute `np.nanmean` / `np.nanpercentile(…, 90)` / `np.nanmax` vectorised (no per-cell Python loops; the (n_cells × 400) working set is ~19 M floats — fine in memory).
  4. `wind_valid_fraction` = valid (land, non-NaN) subpixels / 400 per cell.
  5. Join onto the Task 2 cell index (land cells only); write CSV + `banner()` report.
- [ ] Cleanup: `pipeline/wind/analyse.py:34` (`RASTER_NAME`) and `pipeline/wind/validate.py:51-62` (`WIND_RASTERS`, `_CROSSCHECK_PAIRS`) take `area_name`/bbox parameters instead of hard-coding `new-england-rez`, so `--area-name nsw` works across the wind domain.

## 6. Outputs

| Output | Path |
|---|---|
| Wind feature table | `DATA/features/optmining_wind-features_0.05deg_nsw.csv` |
| Report | `DATA/features/metadata/wind_features_report.md` |
| NSW GWA clips + manifest | `DATA/wind-resource/gwa_v4_*_nsw.tif`, `metadata/download_manifest.json` |

Feature-table columns:

| Column | dtype | Units | Description |
|---|---|---|---|
| cell_id | str | — | join key (Task 2) |
| wind_speed_100m_mean | float | m/s | default scoring input (Q1/Q2) |
| wind_speed_100m_p90 | float | m/s | carried feature |
| wind_speed_100m_max | float | m/s | explanation only ("best micro-site") |
| wind_speed_150m_mean | float | m/s | sensitivity feature |
| capacity_factor_iec2_mean | float | ratio 0–1 | presentation layer |
| wind_valid_fraction | float | 0–1 | valid land subpixels / 400 (feeds Task 9 quality flag) |

## 7. Configuration Parameters

| Parameter | Default | CLI flag | Meaning |
|---|---|---|---|
| `heights` | `(100, 150)` | `--heights` | GWA heights to aggregate |
| `stats` | `("mean","p90","max")` | — | per-cell statistics computed |
| `turbine_classes` | `("IEC2",)` | `--turbine-class` | capacity-factor layers |

## 8. Acceptance Criteria

- [ ] Row count = Task 2 land-cell count; no NaN in `*_mean` where `wind_valid_fraction ≥ 0.5`.
- [ ] `mean ≤ p90 ≤ max` holds for every cell (vector assertion in the stage, not just tests).
- [ ] For cells inside the New England window, values match Sprint 0's `DATA/wind-resource/metadata/aggregation_sensitivity.md` within float tolerance.
- [ ] The download manifest records the NSW window request (GWA-terms audit trail); no full-country file exists on disk.
- [ ] `grep -rn "new-england-rez" pipeline/wind/` matches only default-value definitions, not logic.

## 9. Tests

`tests/test_features_wind_unit.py`: block-stat invariants on synthetic rasters (constant field → mean=p90=max; single hot pixel → max responds, mean barely); mean≤p90≤max property; `wind_valid_fraction` arithmetic with NaN-injected blocks; 20-pixel alignment guard raises on a deliberately mis-anchored transform.

## 10. Risks & Mitigations

- **`/vsicurl/` flakiness on the large NSW window**: retry env already set (`VSICURL_ENV`); clips persisted once so reruns are offline; window read can fall back to two half-windows merged.
- **Memory**: process one layer at a time; never stack all layers.

## 11. Dependencies

**Blocked by:** Task 1 (spec), Task 2 (grid + land mask).
**Blocks:** Tasks 7, 8, 10, 12.

## 12. Decision Log

| Date | Decision / Surprise | Rationale |
|---|---|---|
