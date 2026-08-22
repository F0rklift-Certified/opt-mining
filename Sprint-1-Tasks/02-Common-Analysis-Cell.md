# Task 2 — Finalise the Common Analysis Cell

**Sprint:** 1 (Week 1)
**Assignee:** TBD
**Status:** Not Started
**Estimated Effort:** 1.5 days

---

## 1. Objective

Document the analysis-grid decision (Option A vs Option B) and build the canonical NSW cell index — the `pipeline/grid/` package whose outputs every feature layer joins onto. After this task, "site" has exactly one definition in code and documentation.

## 2. Context & Frozen Decisions

Task 5 §7 already evaluated grid options quantitatively. The decision to ratify and document:

- **Option A adopted**: 0.05° geographic cells **anchored on the GWA raster origin** (lon 109.21125, lat −8.86125), so every cell covers exactly a 20×20 block of native 0.0025° GWA pixels. Storage CRS **EPSG:4326**.
- **All metric computation in EPSG:3577** (GDA94 Australian Albers) — distances, areas, centroids-for-distance. This captures Option B's advantage (equal-area metric correctness) without resampling the wind data off its native lattice.
- Option B (~5 km projected EPSG:3577 cells) is documented as considered-and-rejected: it would require resampling every GWA read (400 exact pixels per cell becomes an interpolation), while its only benefit (metric correctness) is achieved by computing in 3577.
- Reference figures from `pipeline/integration/analyse.py` (recorded in `DATA/integration/integration_analysis.md`): NSW bbox 47,311 cells, ~30,530 land; cell size 5.56 km N–S constant, 4.82 km E–W at 30°S.

## 3. Scope

**In:**
- §Grid section of `DATA/DATA_SPECIFICATION.md` (Option A vs B comparison + ratified spec)
- New `pipeline/grid/` package (spec + build stage) and its registration in the orchestrator
- The fine (0.0025°) NSW land-mask raster and the NSW cell-index CSV
- Bundled cleanup: promote `GridSpec` out of `pipeline/integration/analyse.py`; register `integration.analyse` as a stage; consolidate duplicated GWA origin constants; dedupe `human_bytes`

**Out:**
- Any feature computation (Tasks 3–6)
- Exclusion logic (Task 7) — this task computes `land_fraction` but does not apply the `min_land_fraction` rule

## 4. Inputs

- `pipeline/integration/analyse.py` — `GridSpec` dataclass, `GWA_ORIGIN_LON/LAT`, `GWA_STEP_DEG`, `CELL_FACTOR`, `NSW_BBOX` candidates (lines 40–69)
- `pipeline/validate.py:141-155` `_anchored_grid(bbox)` — working floor/ceil lattice-snapping returning a rasterio affine; `:158-165` `_mask_from_polygons(path, rows, cols, transform)` — GeoJSON → boolean mask via `rasterio.features.rasterize`
- `DATA/geographic/boundaries/abs_ste_2021_national.geojson` — NSW state polygon (re-fetch via `pipeline.geographic.download` if absent)
- `rasterio.warp.transform` for 4326→3577 centroid coordinates (pattern in `pipeline/geographic/validate.py:58-64`)

## 5. Implementation Plan

- [ ] Write the §Grid section of `DATA/DATA_SPECIFICATION.md`: the Option A/B comparison table, the ratified grid spec (origin, step, cell factor, storage/computation CRS split, `assert`-style CRS discipline), and the cell_id scheme below.
- [ ] Create `pipeline/grid/spec.py`: move `GridSpec` here from `pipeline/integration/analyse.py` and make it the **sole owner** of the GWA lattice constants. Extend with: `cell_id(row, col) -> str`, `parse_cell_id(cell_id) -> (row, col)`, `cell_bounds(row, col)`, `cell_centroid(row, col)`, `locate(lon, lat) -> (row, col)`, `snap_bbox(bbox) -> bbox`. `pipeline/integration/analyse.py` and `pipeline/validate.py` import from here afterwards (delete their local copies of the constants).
- [ ] **cell_id scheme**: `r{row:04d}c{col:04d}` indexed on the Australia-wide GWA-anchored 0.05° lattice (row 0 at −8.86125 southward, col 0 at 109.21125 eastward; ~919 × 1,080 nationally). Deterministic, invertible without a lookup table, stable under bbox changes, nationally extensible. (Sequential "NSW-00001" ids rejected: they break the moment the bbox or land mask changes.)
- [ ] Create `pipeline/grid/config.py`: `DATA/grid` paths; add `NSW_BBOX = (141.0, -37.5, 153.64, -28.15)` and `NSW_AREA = "nsw"` to `pipeline/config.py`.
- [ ] Create `pipeline/grid/build.py` with `run(bbox=NSW_BBOX, area_name="nsw", verbose=False) -> dict`:
  1. Snap bbox to the lattice (`GridSpec.snap_bbox`).
  2. Rasterize the NSW STE polygon onto the 0.0025° subgrid (reuse/generalise `_mask_from_polygons`); write the mask GeoTIFF (uint8, tiled, deflate).
  3. Per-cell `land_fraction` = 20×20 block mean of the mask; keep cells with `land_fraction > 0`.
  4. Centroids in 4326; transform to 3577 (`rasterio.warp.transform`); equal-area `area_km2` per cell.
  5. Write the cell-index CSV + `metadata/grid_manifest.json` (bbox, snap result, counts, mask hash) + `metadata/grid_report.md` (with `banner()`).
- [ ] Register stages: add `"grid.build"` and `"integration.analyse"` to `STAGES` in `pipeline/config.py`; extend `_get_runner()` and `_build_kwargs()` in `pipeline/__main__.py`; add `"grid"` to `DOMAINS`.
- [ ] Dedupe `human_bytes` (keep `pipeline/common/geo.py`; `pipeline/wind/gwa.py` imports it; keep the parity test green by deletion, not divergence).

## 6. Outputs

| Output | Path |
|---|---|
| NSW cell index | `DATA/grid/optmining_grid-cells_0.05deg_nsw.csv` |
| Fine land mask (gitignored, regenerable) | `DATA/grid/optmining_landmask_0.0025deg_nsw.tif` |
| Manifest + report | `DATA/grid/metadata/grid_manifest.json`, `grid_report.md` |
| Grid section | `DATA/DATA_SPECIFICATION.md` §Grid |

Cell-index CSV columns:

| Column | dtype | Units | Description |
|---|---|---|---|
| cell_id | str | — | `r{row:04d}c{col:04d}` on the national GWA lattice |
| grid_row, grid_col | int | — | lattice indices |
| centroid_lon, centroid_lat | float | deg EPSG:4326 | cell centre |
| centroid_x_3577, centroid_y_3577 | float | m EPSG:3577 | cell centre, projected |
| lon_min, lat_min, lon_max, lat_max | float | deg EPSG:4326 | cell bounds |
| area_km2 | float | km² (EPSG:3577) | equal-area cell area |
| land_fraction | float | 0–1 | share of the 400 subpixels inside the ABS NSW polygon |

## 7. Configuration Parameters

| Parameter | Default | CLI flag | Meaning |
|---|---|---|---|
| `bbox` | `NSW_BBOX` | `--bbox` | analysis window (snapped to lattice) |
| `area_name` | `nsw` | `--area-name` | output filename slug |

## 8. Acceptance Criteria

- [ ] Total in-bbox cell count = **47,311**; land cells (land_fraction > 0) within ±2% of **30,530** (reconciles with `DATA/integration/integration_analysis.md`).
- [ ] `parse_cell_id(cell_id(r, c)) == (r, c)` and `locate(*cell_centroid(r, c)) == (r, c)` property tests pass.
- [ ] Grid origin constants exist in exactly one module (`pipeline/grid/spec.py`); `grep -rn "109.21125" pipeline/ --include="*.py"` matches only `grid/spec.py`.
- [ ] `python -m pipeline --only grid.build` and `--only integration.analyse` both run from the orchestrator.
- [ ] §Grid of `DATA_SPECIFICATION.md` presents both options and the ratification rationale.

## 9. Tests

`tests/test_grid_unit.py`: cell_id round-trip; `snap_bbox` idempotency (snapping a snapped bbox is a no-op); `land_fraction` block arithmetic on synthetic masks (all-ones → 1.0, checkerboard → 0.5); `locate()` boundary rule (a point exactly on a cell edge belongs to one cell, documented which).

## 10. Risks & Mitigations

- **Half-pixel anchor mistakes** (the prototype's origin was half a native pixel off): acceptance check that the snapped NSW window's offsets into the national GWA grid are exact multiples of 20 pixels.
- **STE polygon detail**: the committed national STE file carries ~50 m generalisation (`maxAllowableOffset`) — acceptable at 250 m subpixels; noted in the grid report.

## 11. Dependencies

**Blocked by:** Task 1 (spec file must exist to receive §Grid).
**Blocks:** Tasks 3, 4, 5, 6 (all join onto the cell index), 7–12 transitively.

## 12. Decision Log

| Date | Decision / Surprise | Rationale |
|---|---|---|
