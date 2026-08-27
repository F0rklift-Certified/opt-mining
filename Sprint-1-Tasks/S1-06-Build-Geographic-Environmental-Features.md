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
