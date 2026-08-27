# S1-08: Create the Integrated NSW Feature Table

**Type:** Story  
**Priority:** High  
**Story Points:** 5  
**Labels:** integration, pipeline  
**Blocked by:** S1-03, S1-04, S1-05, S1-06, S1-07  
**Blocks:** S1-09, S1-10

---

## Objective

Join all feature layers and the exclusion layer into a single integrated site dataset for NSW. This is the core Sprint 1 deliverable — the table that answers "what does Opt-Mining know about this location?"

---

## Context

By this point, the pipeline has produced:
- Wind features (S1-03)
- Demand proxy features (S1-04)
- Infrastructure features (S1-05)
- Geographic/environmental features (S1-06)
- Exclusion flags (S1-07)

This task merges them all by `cell_id` into a single, comprehensive feature table that serves as the input to scoring and the queryable output of the pipeline.

---

## Deliverables

1. Pipeline step at `pipeline/integration/` that performs the merge
2. Integrated feature table saved as GeoPackage (with geometry) and CSV (without geometry)
3. Merge validation report

---

## Acceptance Criteria

- [ ] Pipeline step (`pipeline/integration/`) merges all feature layers by `cell_id`
- [ ] Output table includes at minimum:

| Column | Source | Units |
|--------|--------|-------|
| cell_id | Grid (S1-02) | — |
| geometry | Grid (S1-02) | — |
| centroid_lat | Grid (S1-02) | degrees |
| centroid_lon | Grid (S1-02) | degrees |
| wind_speed | Wind (S1-03) | m/s |
| demand_proxy | Demand (S1-04) | normalised 0–1 |
| dist_transmission_km | Infrastructure (S1-05) | km |
| dist_substation_km | Infrastructure (S1-05) | km |
| dist_connection_km | Infrastructure (S1-05) | km |
| inside_rez | Infrastructure (S1-05) | boolean |
| elevation_m | Geographic (S1-06) | m |
| slope_deg | Geographic (S1-06) | degrees |
| land_use | Geographic (S1-06) | category |
| protected_area | Geographic (S1-06) | boolean |
| eligible | Exclusion (S1-07) | boolean |
| exclusion_reason | Exclusion (S1-07) | text |
| data_confidence | All layers | flag/score |

- [ ] All columns retain their units, documented in metadata or column naming convention
- [ ] Rows for excluded cells are **retained** but marked as ineligible (do not drop them)
- [ ] Output saved as:
  - GeoPackage (with geometry) for GIS use
  - CSV (without geometry) for tabular analysis
- [ ] Row count matches the total analysis grid cell count (no rows lost or duplicated in join)
- [ ] Merge validation checks:
  - No unexpected NaN inflation from bad joins
  - Row count before and after join is identical
  - No duplicate `cell_id` values
- [ ] Automated — single command runs the full pipeline from raw data to integrated table
- [ ] Output file path and format documented in pipeline README

---

## Example Output

| cell_id | wind_speed | demand_proxy | dist_transmission_km | dist_substation_km | slope_deg | protected | eligible |
|---------|-----------|--------------|---------------------|-------------------|-----------|-----------|----------|
| NSW001  | 7.8       | 0.72         | 4.2                 | 11.3              | 3.1       | No        | Yes      |
| NSW002  | 8.4       | 0.51         | 19.7                | 26.4              | 7.8       | No        | Yes      |
| NSW003  | 9.1       | 0.43         | 5.6                 | 8.9               | 2.4       | Yes       | No       |

---

## Technical Notes

- Use left joins from the grid to each feature layer to ensure no cells are dropped
- Validate: `assert len(integrated) == len(grid)` after each join
- Per the Constitution: keep "data integration, criteria derivation, scoring and presentation in separate layers"
- The integrated table is the boundary between the integration layer and the scoring layer
- Consider adding a `pipeline_version` or `run_timestamp` column for reproducibility

---

## Pipeline Command

The full pipeline should be runnable with a single command, e.g.:

```bash
python -m pipeline run --output outputs/sprint1_integrated_nsw.gpkg
```

This command should execute all steps from raw data through to the integrated table.
