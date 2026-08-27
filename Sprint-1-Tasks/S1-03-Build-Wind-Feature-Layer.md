# S1-03: Build the Wind Feature Layer

**Type:** Story  
**Priority:** High  
**Story Points:** 5  
**Labels:** feature-engineering, wind  
**Blocked by:** S1-01, S1-02  
**Blocks:** S1-08

---

## Objective

Take the selected Global Wind Atlas data and map it to every valid NSW analysis cell. The pipeline should generate this automatically — no manual CSV preparation.

---

## Context

The Global Wind Atlas provides modelled wind resource data (wind speed, power density, capacity factor) at multiple heights. During Sprint 0 this data was investigated and its characteristics documented. This task converts that investigation into an automated pipeline step that produces a per-cell wind feature.

The team should determine the most defensible MVP wind-resource variable (e.g. mean wind speed at 100m, or power density at hub height). The key requirement is automation and reproducibility.

---

## Deliverables

1. Pipeline module at `pipeline/wind/` that ingests GWA data and produces per-cell wind features
2. Documentation of variable selection rationale
3. Output table/GeoDataFrame with wind values per cell

---

## Acceptance Criteria

- [ ] Pipeline module (`pipeline/wind/`) ingests GWA data and resamples/aggregates to analysis cells
- [ ] The MVP wind-resource variable is selected and documented (e.g. mean wind speed or power density at a specific height)
- [ ] Justification for height and variable choice is recorded (why this height? why this variable?)
- [ ] Output is a table/GeoDataFrame: `cell_id | wind_variable | units | data_source | confidence_flag`
- [ ] Cells with no valid wind data are flagged (not filled with defaults or fabricated values)
- [ ] Resampling/aggregation method is documented (mean, median, area-weighted, etc.)
- [ ] Automated — runs as part of the pipeline without manual intervention
- [ ] Unit tests cover the resampling/aggregation logic
- [ ] Output statistics are logged: min, max, mean, count of valid/invalid cells

---

## Technical Notes

- If Option A (GWA-aligned grid) was chosen in S1-02, this may be a direct extraction rather than resampling
- If Option B (projected grid) was chosen, document the resampling method carefully
- Per the Constitution: "Never invent, extrapolate or hard-code data values to make a pipeline run"
- Per the Constitution: "Never build a circular model" — wind data is an input feature, not a prediction target

---

## Example Output

| cell_id | wind_speed_100m_ms | power_density_100m_wm2 | data_source | confidence |
|---------|-------------------|----------------------|-------------|------------|
| NSW001  | 7.8               | 285                  | GWA 3.0     | high       |
| NSW002  | 8.4               | 340                  | GWA 3.0     | high       |
| NSW003  | NULL              | NULL                 | —           | no_data    |
