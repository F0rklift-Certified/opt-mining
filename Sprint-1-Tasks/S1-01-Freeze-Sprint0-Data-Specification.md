# S1-01: Freeze the Sprint 0 Data Specification

**Type:** Task  
**Priority:** Highest  
**Story Points:** 3  
**Labels:** data-governance, documentation  
**Blocked by:** —  
**Blocks:** S1-02, S1-03, S1-04, S1-05, S1-06

---

## Objective

Before further coding, finalise which datasets from the Sprint 0 inventory will actually be used in the MVP. Sprint 0 was for exploration; Sprint 1 needs controlled implementation. Do not keep adding datasets unless there is a clear gap.

---

## Context

Sprint 0 investigated a broad range of potential data sources across wind resource, demand, infrastructure, geographic and environmental domains. This task draws a line under that exploration and commits to a defined set of inputs for the Sprint 1 pipeline.

This is a governance gate — nothing downstream should begin until the data specification is locked.

---

## Deliverables

1. A single authoritative data specification document (e.g. `DATA/sprint1_data_specification.md` or equivalent structured format)
2. An out-of-scope list documenting datasets considered but excluded

---

## Acceptance Criteria

- [ ] A single authoritative data specification document exists and is version-controlled
- [ ] For every selected dataset, the following fields are recorded:
  - **Source** (publisher / URL / file path in repository)
  - **Variable(s)** extracted
  - **Units**
  - **CRS** (coordinate reference system)
  - **Resolution** (spatial and temporal)
  - **Temporal coverage / vintage**
  - **Licence**
  - **Known limitations**
  - **Intended use in the model** (which pipeline step consumes it)
- [ ] Datasets NOT selected from the Sprint 0 inventory are explicitly listed as out-of-scope with reason for exclusion
- [ ] No new datasets are added unless a documented gap exists and is justified
- [ ] Document is referenced by the pipeline README
- [ ] Document follows the Constitution's requirement to "record the provenance, licence and vintage of every dataset"

---

## Suggested Format

| Dataset | Source | Variable(s) | Units | CRS | Spatial Res. | Temporal Coverage | Licence | Limitations | Pipeline Use |
|---------|--------|-------------|-------|-----|--------------|-------------------|---------|-------------|--------------|
| Global Wind Atlas | globalwindatlas.info | wind speed, power density | m/s, W/m² | EPSG:4326 | ~250m | Climatology (10yr) | CC-BY-4.0 | Modelled, not measured | Wind feature layer |
| ... | ... | ... | ... | ... | ... | ... | ... | ... | ... |

---

## Notes

- Refer to `DATA/geographic/metadata/source_register.md` and inspection files from Sprint 0 as starting points
- The Constitution requires: "Record the provenance, licence and vintage of every dataset that enters the platform"
- This document becomes the single source of truth for Sprint 1 data inputs
