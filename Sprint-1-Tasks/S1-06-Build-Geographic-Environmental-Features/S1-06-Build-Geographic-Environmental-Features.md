# S1-06: Build Geographic and Environmental Features

**Type:** Story  
**Priority:** High  
**Story Points:** 5  
**Labels:** feature-engineering, geographic, environmental  
**Blocked by:** S1-01, S1-02  
**Blocks:** S1-07, S1-08

---

## Objective

Convert the Sprint 0 geographic and environmental investigation into per-cell features. Derive terrain, land-use, and environmental constraint variables for every analysis cell.

---

## Context

During Sprint 0, geographic datasets were investigated including elevation (SRTM), slope, land use (ABARES NLUM), and protected areas (CAPAD). This task applies zonal statistics and spatial operations to compute summary values for each analysis cell.

Geographic and environmental features serve two purposes:
1. Input to the suitability scoring model (terrain affects construction cost)
2. Input to the exclusion layer (protected areas, extreme slopes)

---

## Deliverables

1. Pipeline module at `pipeline/geographic/` that computes geographic/environmental features per cell
2. Output table/GeoDataFrame with terrain and environmental features
3. Documentation of zonal statistics methods

---

## Acceptance Criteria

- [ ] Pipeline module (`pipeline/geographic/`) derives the following for each analysis cell:
  - `elevation_m` — representative elevation (mean or median within cell)
  - `slope_deg` — representative slope (mean, max, or percentile within cell — document choice)
  - `land_use_class` — dominant land-use class within cell (from ABARES NLUM/ALUM)
  - `protected_area` — boolean flag (any overlap with CAPAD protected areas)
  - `protected_area_name` — name(s) of overlapping protected area(s), if applicable
  - Other criteria justified by Sprint 0 investigation (e.g. terrain ruggedness index)
- [ ] Method for summarising raster data within each cell is documented:
  - Which zonal statistic (mean, median, max, mode)?
  - How are partial cells handled at boundaries?
  - How is NoData within cells handled?
- [ ] Output table: `cell_id | elevation_m | slope_deg | land_use | protected_area | protected_area_name | tri | confidence_flag`
- [ ] CRS transformations are explicit and logged
- [ ] Automated — runs as part of the pipeline
- [ ] Unit tests cover zonal statistics logic
- [ ] Performance is acceptable for full NSW grid (document runtime)

---

## Data Sources (from Sprint 0)

- Elevation: `DATA/geographic/elevation/srtm-gl3_elevation_90m_new-england-rez.tif` (and broader NSW coverage if available)
- Slope: `DATA/geographic/elevation/srtm-gl3_slope-horn_90m_new-england-rez.tif`
- TRI: `DATA/geographic/elevation/srtm-gl1_tri_30m_glen-innes.tif`
- Land use: `DATA/geographic/landuse/abares_nlum-alumv8_2020-21_new-england-rez.tif`
- Land use class table: `DATA/geographic/landuse/abares_alumv8_class_table.csv`
- Protected areas: `DATA/geographic/protected/dcceew_capad-terrestrial_2024_nsw.geojson`
- Urban areas: `DATA/geographic/urban/abs_ucl_2021_new-england-rez.geojson`

---

## Technical Notes

- Use `rasterstats` or `rasterio` with `geopandas` for zonal statistics
- For land use (categorical raster), use mode (most common class) rather than mean
- For protected areas (vector), use spatial intersection/overlay
- Per the Constitution: "Make coordinate reference systems, spatial resolutions and units explicit at every boundary"
- Consider whether current data coverage extends to all of NSW or only the New England REZ area — document gaps
- Slope values should be in degrees (not percent or radians)

---

## Zonal Statistics Method

For each raster input and each cell polygon:

1. Clip/mask raster to cell boundary
2. Compute statistic (mean, max, mode depending on variable)
3. Record count of valid pixels vs NoData pixels
4. Flag cells where >50% pixels are NoData as low confidence

---

## Example Output

| cell_id | elevation_m | slope_deg | land_use | protected_area | protected_area_name | confidence |
|---------|-------------|-----------|----------|----------------|---------------------|------------|
| NSW001  | 842         | 3.1       | Grazing  | No             | —                   | high       |
| NSW002  | 1105        | 7.8       | Forestry | No             | —                   | high       |
| NSW003  | 654         | 2.4       | Grazing  | Yes            | Oxley Wild Rivers NP| high       |

---

## How to Complete This Task

This ticket is now backed by a full spec. Three companion documents sit in this
same folder and should be read in this order before writing any code:

1. **`requirements.md`** — the authoritative, testable definition of "done".
   Every acceptance criterion above is expanded into EARS-format requirements
   with precise, verifiable clauses. When this ticket and `requirements.md`
   appear to disagree, `requirements.md` wins.
2. **`design.md`** — how the stage is built: the new
   `pipeline/geographic/features.py` module, its `run(verbose=False) -> dict`
   entry point, the zonal-statistics method (elevation/slope/TRI), the
   categorical land-use mode (NLUM code → ALUM name), CAPAD protected-area
   overlap in EPSG:3577, the output schema, provenance, and the Correctness
   Properties the tests must uphold. Read this to understand *how* the
   requirements are satisfied.
3. **`tasks.md`** — the actual build order. This is the checklist you execute:
   a dependency-ordered plan (with a Task Dependency Graph) that goes config →
   grid/raster/vector loaders → the pure zonal/mode/overlap core → confidence →
   writers → provenance → `run()` → stage registration → no-silent-passes
   validation → property/unit tests → documentation.

### Working the plan

- Open `tasks.md` and execute tasks top-to-bottom. Each task lists the specific
  requirement clauses it satisfies (`_Requirements: ...`) and, where useful, a
  `_Design ref:_` pointer — use those to jump back into `requirements.md` /
  `design.md` for detail.
- Tasks marked with `*` are optional test sub-tasks; core implementation tasks
  are never optional. Do not skip the no-silent-passes validation or the stage
  registration.
- Stop at the checkpoints, run the test suite, and confirm green before moving on.

### Things the spec pins down (don't diverge silently)

- **Zonal statistics on pure rasterio/numpy/geopandas** — the design deliberately
  does **not** add `rasterstats`; it reuses the established windowed-read +
  cell-centre-mask idiom already used in `validate.py` / `derive.py`. Keep that
  consistency.
- **CRS explicit at every boundary** — EPSG:4326 storage, EPSG:3577 for
  area/overlap computation (CAPAD protected-area intersection). Log every
  transform; never convert silently.
- **Categorical land use uses mode** (most common ALUM class), not mean, with a
  documented tie-break; NLUM codes are mapped to names via the ALUM class table.
- **Coverage gap is real** — several source rasters cover only the New England
  REZ / Glen Innes windows, not all of NSW. Cells with insufficient valid pixels
  are flagged low confidence, never back-filled (Constitution: "never invent
  data").

### Cross-component impact (must ship together)

Finishing this task is not just writing `features.py`. To keep the pipeline
consistent you must also: register `geographic.features` in `pipeline/config.py`
`STAGES` **after `grid`**; add the `_get_runner` dispatch in
`pipeline/__main__.py`; update the `pipeline/geographic/__init__.py` docstring;
add the no-silent-passes checks; record provenance (`DATA_PROVENANCE.md` +
`download_manifest.json` + `source_register`); document the full-NSW-grid
runtime; and update `pipeline/README.md` (stage order + expected outputs) and the
data specification §4.4.6/§4.4.7 + §7.

> Note: this file is a documentation snapshot. The `requirements.md` / `design.md` /
> `tasks.md` that Kiro's task runner uses live in the workspace spec store; the
> copies in this folder are for reading alongside the ticket and may drift if the
> spec is later edited.
