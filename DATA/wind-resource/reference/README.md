# Reference points used for validation

## `nsw_wind_farms_new_england.csv`

Operational wind farms whose Geoscience Australia point location falls inside the
Task 1 study window (New England REZ, NSW — bbox `150.0,-31.5,152.0,-29.5`).

| Field | Value |
|---|---|
| **Origin** | Geoscience Australia National Electricity Infrastructure — Power Stations layer |
| **Retrieved by** | Task 3 (Electricity Infrastructure Investigation), branch `task-03-infrastructure-investigation`, file `DATA/infrastructure/generators/ga_wind_generators_2026_nsw.geojson` |
| **Filter applied** | `geometry within study bbox` AND `feature_name contains "Wind Farm"` |
| **CRS** | EPSG:4326 |
| **Purpose** | Validation reference only — never an input to any score |

This file is a **derived extract**, copied here so Task 1's validation check is
reproducible on this branch without depending on the Task 3 branch being merged.
The authoritative copy and its full provenance belong to Task 3.

### Caveat on point geometry

Each record is a **single representative point** for a wind farm that in reality
spreads turbines across tens of square kilometres along ridge lines. The Global
Wind Atlas pixel sampled at that point is therefore not necessarily the pixel a
turbine stands on. The validation reports both the point value and the
distribution of the surrounding neighbourhood for this reason.
