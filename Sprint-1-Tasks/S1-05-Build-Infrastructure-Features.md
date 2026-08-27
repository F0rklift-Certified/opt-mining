# S1-05: Build Infrastructure Features

**Type:** Story  
**Priority:** High  
**Story Points:** 5  
**Labels:** feature-engineering, infrastructure  
**Blocked by:** S1-01, S1-02  
**Blocks:** S1-08

---

## Objective

Convert the Sprint 0 infrastructure investigation into measurable per-cell features. Derive distance-based and categorical infrastructure indicators for every analysis cell.

---

## Context

During Sprint 0, infrastructure datasets were investigated including transmission lines, substations, connection points, and Renewable Energy Zones (REZs). This task takes those investigated datasets and computes actual numeric features that describe each cell's relationship to grid infrastructure.

Proximity to infrastructure is a key factor in wind farm viability — sites far from transmission are more expensive to connect.

---

## Deliverables

1. Pipeline module at `pipeline/infrastructure/` that computes infrastructure features per cell
2. Output table/GeoDataFrame with distance and categorical features
3. Documentation of calculation methods and data sources

---

## Acceptance Criteria

- [ ] Pipeline module (`pipeline/infrastructure/`) derives the following for each analysis cell:
  - `distance_to_nearest_transmission_line` (km)
  - `distance_to_nearest_substation` (km)
  - `distance_to_nearest_connection_point` (km)
  - `inside_REZ` (boolean)
  - `rez_name` (string, nullable — name of REZ if inside one)
- [ ] Additional defensible indicators from Sprint 0 are included if justified (e.g. transmission line voltage, substation capacity)
- [ ] Distance calculations use a **projected CRS** (not geographic degrees) — document which projection
- [ ] Distances are measured from cell centroid to nearest feature (document this choice)
- [ ] Output table: `cell_id | dist_transmission_km | dist_substation_km | dist_connection_km | inside_rez | rez_name | confidence_flag`
- [ ] Missing or unavailable infrastructure data results in a flag, not a fabricated value
- [ ] Automated — runs as part of the pipeline
- [ ] Unit tests cover distance calculation logic
- [ ] Performance is acceptable for full NSW grid (document runtime)

---

## Data Sources (from Sprint 0)

- Transmission lines: `DATA/infrastructure/` (Geoscience Australia power lines)
- Substations: `DATA/infrastructure/` (Geoscience Australia substations)
- Connection points: `DATA/infrastructure/connection-points/aemo_kci_2026.xlsx`
- REZ boundaries: `DATA/infrastructure/rez/`
- Generators (for context): `DATA/infrastructure/generators/`

---

## Technical Notes

- Use `geopandas.sjoin_nearest` or equivalent for distance calculations in projected space
- Per the Constitution: "Make coordinate reference systems, spatial resolutions and units explicit at every boundary"
- Consider using EPSG:3577 (Australian Albers) for distance calculations regardless of the analysis cell CRS
- For transmission lines, distance should be to the nearest point on the line geometry, not to line endpoints

---

## Example Output

| cell_id | dist_transmission_km | dist_substation_km | dist_connection_km | inside_rez | rez_name | confidence |
|---------|---------------------|-------------------|-------------------|------------|----------|------------|
| NSW001  | 4.2                 | 11.3              | 15.7              | Yes        | New England | high    |
| NSW002  | 19.7                | 26.4              | 32.1              | No         | —        | high       |
| NSW003  | 5.6                 | 8.9               | 12.3              | Yes        | Central-West | high  |
