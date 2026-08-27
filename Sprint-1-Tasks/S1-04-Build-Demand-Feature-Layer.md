# S1-04: Build the Demand Feature Layer

**Type:** Story  
**Priority:** High  
**Story Points:** 5  
**Labels:** feature-engineering, demand  
**Blocked by:** S1-01, S1-02  
**Blocks:** S1-08

---

## Objective

Use the AEMO operational-demand pipeline developed during Sprint 0 to produce a per-cell demand proxy feature. Maintain the agreed distinction: AEMO regional demand ≠ local cell demand.

---

## Context

AEMO publishes operational demand at the NEM region level (e.g. NSW1). This is aggregate demand for an entire state/region — it does not tell us about demand at a specific cell location. To produce a per-cell demand feature, we need a spatial-allocation method that distributes regional demand to cells.

This is explicitly a **proxy**, not a measurement. The allocation method and its assumptions must be documented transparently.

---

## Deliverables

1. Pipeline module at `pipeline/demand/` that produces a demand proxy per analysis cell
2. Documentation of the spatial-allocation formula and assumptions
3. Output table/GeoDataFrame with demand proxy values per cell

---

## Acceptance Criteria

- [ ] Pipeline module (`pipeline/demand/`) produces a demand proxy value for each analysis cell
- [ ] The spatial-allocation method is explicitly documented with:
  - Formula
  - Assumptions
  - Limitations
  - Data inputs (e.g. population grid, if used)
- [ ] Documentation clearly states this is a **proxy** and not measured local demand
- [ ] Output table: `cell_id | demand_proxy | allocation_method | source_region | confidence_flag`
- [ ] If population data or other weighting data is used, its source and vintage are recorded in the data specification (S1-01)
- [ ] Automated — runs as part of the pipeline
- [ ] Edge cases are documented:
  - Cells outside NEM regions
  - Cells on region boundaries
  - Cells in areas with no population data

---

## Allocation Options to Consider

| Method | Description | Pros | Cons |
|--------|-------------|------|------|
| Uniform | Divide regional demand equally across all cells | Simple | Unrealistic |
| Population-weighted | Allocate proportional to population density | More realistic | Requires population data |
| Load-centre proximity | Weight by distance to known load centres | Captures spatial pattern | Requires load centre data |
| Binary (high/low) | Classify cells as near/far from demand | Simple, avoids false precision | Loses nuance |

---

## Technical Notes

- The Sprint 0 demand pipeline already extracts and summarises AEMO operational demand data
- AEMO data lives in `DATA/electricity-demand/`
- Per the Constitution: "Never invent, extrapolate or hard-code data values to make a pipeline run"
- The demand proxy should be normalised (0–1) or expressed in interpretable units — document which

---

## Example Output

| cell_id | demand_proxy | allocation_method | source_region | confidence |
|---------|-------------|-------------------|---------------|------------|
| NSW001  | 0.72        | population_weight  | NSW1          | medium     |
| NSW002  | 0.51        | population_weight  | NSW1          | medium     |
| NSW003  | 0.03        | population_weight  | NSW1          | low        |
