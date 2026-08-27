# Sprint 1 — Jira Tickets

**Epic:** Sprint 1 — From Data Investigation to an Integrated NSW Site Dataset

**Sprint Objective:** Build the first reproducible end-to-end NSW renewable-energy site-screening dataset and pipeline.

**Outcome:** A user can select an analysis cell/site in NSW and see all information Opt-Mining knows about that location.

**Pipeline concept:** Raw data → validation → spatial standardisation → common grid → feature engineering → exclusions → integrated site dataset.

---

## S1-01: Freeze the Sprint 0 Data Specification

**Type:** Task  
**Priority:** Highest  
**Story Points:** 3  
**Labels:** data-governance, documentation  
**Blocked by:** —  
**Blocks:** S1-02, S1-03, S1-04, S1-05, S1-06

### Description

Before further coding, finalise which datasets from the Sprint 0 inventory will actually be used in the MVP. Sprint 0 was for exploration; Sprint 1 needs controlled implementation.

### Acceptance Criteria

- [ ] A single authoritative data specification document exists (e.g. `DATA/sprint1_data_specification.md` or CSV)
- [ ] For every selected dataset, the following fields are recorded:
  - Source (publisher / URL)
  - Variable(s) extracted
  - Units
  - CRS
  - Resolution (spatial and temporal)
  - Temporal coverage / vintage
  - Licence
  - Known limitations
  - Intended use in the model
- [ ] Datasets NOT selected from Sprint 0 inventory are explicitly listed as out-of-scope with reason
- [ ] No new datasets are added unless a documented gap exists
- [ ] Document is version-controlled and referenced by the pipeline README

---

## S1-02: Finalise the Common Analysis Cell

**Type:** Task  
**Priority:** Highest  
**Story Points:** 3  
**Labels:** architecture, spatial  
**Blocked by:** S1-01  
**Blocks:** S1-03, S1-04, S1-05, S1-06, S1-07, S1-08

### Description

Select and document the spatial unit that all pipeline outputs will be mapped to. Evaluate two options and make a binding decision for Sprint 1.

### Acceptance Criteria

- [ ] Decision document comparing:
  - **Option A:** ~0.05° GWA-aligned geographic cells
  - **Option B:** ~5 km projected cells using EPSG:3577
- [ ] Decision criteria documented (alignment with wind data, computation cost, distortion, downstream compatibility)
- [ ] Chosen option formally recorded with rationale
- [ ] A reproducible script or module generates the NSW cell grid (GeoDataFrame or equivalent)
- [ ] Grid output includes: cell_id, geometry, centroid_lat, centroid_lon, area_km2
- [ ] Grid is saved as a GeoPackage or GeoJSON for reuse by downstream tasks
- [ ] CRS is explicitly documented in code and metadata

---

## S1-03: Build the Wind Feature Layer

**Type:** Story  
**Priority:** High  
**Story Points:** 5  
**Labels:** feature-engineering, wind  
**Blocked by:** S1-01, S1-02  
**Blocks:** S1-08

### Description

Take the selected Global Wind Atlas data and map it to every valid NSW analysis cell. The pipeline should generate this automatically — no manual CSV preparation.

### Acceptance Criteria

- [ ] Pipeline module (`pipeline/wind/`) ingests GWA data and resamples/aggregates to analysis cells
- [ ] The MVP wind-resource variable is selected and documented (e.g. mean wind speed or power density at a specific height)
- [ ] Justification for height and variable choice is recorded
- [ ] Output is a table/GeoDataFrame: `cell_id | wind_variable | units | data_source | confidence_flag`
- [ ] Cells with no valid wind data are flagged, not filled with defaults
- [ ] Automated — runs as part of the pipeline without manual intervention
- [ ] Unit tests cover the resampling/aggregation logic

---

## S1-04: Build the Demand Feature Layer

**Type:** Story  
**Priority:** High  
**Story Points:** 5  
**Labels:** feature-engineering, demand  
**Blocked by:** S1-01, S1-02  
**Blocks:** S1-08

### Description

Convert the AEMO operational-demand pipeline from Sprint 0 into a per-cell demand proxy feature. Maintain the agreed distinction: AEMO regional demand ≠ local cell demand.

### Acceptance Criteria

- [ ] Pipeline module (`pipeline/demand/`) produces a demand proxy value for each analysis cell
- [ ] The spatial-allocation method (e.g. population weighting, uniform, or other) is explicitly documented with formula and assumptions
- [ ] Documentation clearly states this is a proxy and not measured local demand
- [ ] Output table: `cell_id | demand_proxy | allocation_method | source_region | confidence_flag`
- [ ] If population data or other weighting data is used, its source and vintage are recorded in the data specification
- [ ] Automated — runs as part of the pipeline
- [ ] Edge cases documented (cells outside NEM regions, cells on region boundaries)

---

## S1-05: Build Infrastructure Features

**Type:** Story  
**Priority:** High  
**Story Points:** 5  
**Labels:** feature-engineering, infrastructure  
**Blocked by:** S1-01, S1-02  
**Blocks:** S1-08

### Description

Convert the Sprint 0 infrastructure investigation into measurable per-cell features.

### Acceptance Criteria

- [ ] Pipeline module (`pipeline/infrastructure/`) derives the following for each analysis cell:
  - `distance_to_nearest_transmission_line` (km)
  - `distance_to_nearest_substation` (km)
  - `distance_to_nearest_connection_point` (km)
  - `inside_REZ` (boolean + REZ name if applicable)
- [ ] Additional defensible indicators from Sprint 0 are included if justified
- [ ] Distance calculations use projected CRS (not geographic degrees)
- [ ] Output table: `cell_id | distance_transmission | distance_substation | distance_connection_point | inside_rez | rez_name | confidence_flag`
- [ ] Missing/unavailable infrastructure data results in a flag, not a fabricated value
- [ ] Automated — runs as part of the pipeline
- [ ] Unit tests cover distance calculation logic

---

## S1-06: Build Geographic and Environmental Features

**Type:** Story  
**Priority:** High  
**Story Points:** 5  
**Labels:** feature-engineering, geographic, environmental  
**Blocked by:** S1-01, S1-02  
**Blocks:** S1-07, S1-08

### Description

Convert Sprint 0 geographic and environmental investigation into per-cell features.

### Acceptance Criteria

- [ ] Pipeline module (`pipeline/geographic/`) derives the following for each analysis cell:
  - `elevation` (m, mean or representative value for cell)
  - `slope` (degrees, mean or max for cell)
  - `land_use_class` (dominant class within cell)
  - `protected_area` (boolean — any overlap with CAPAD protected areas)
  - Other criteria justified by Sprint 0 investigation
- [ ] Method for summarising raster data within each cell is documented (zonal statistics approach)
- [ ] Output table: `cell_id | elevation_m | slope_deg | land_use | protected_area | confidence_flag`
- [ ] CRS transformations are explicit and logged
- [ ] Automated — runs as part of the pipeline
- [ ] Unit tests cover zonal statistics logic

---

## S1-07: Implement the Exclusion Layer

**Type:** Story  
**Priority:** High  
**Story Points:** 3  
**Labels:** exclusions, pipeline  
**Blocked by:** S1-06  
**Blocks:** S1-08

### Description

Build an explicit exclusion component in the pipeline. Exclusions must not be hidden inside scoring code — they are a separate, auditable step.

### Acceptance Criteria

- [ ] Dedicated module (`pipeline/exclusions/`) applies exclusion rules to the cell grid
- [ ] Exclusion rules are configurable (not hard-coded) — defined in a rules file or config
- [ ] Each cell receives: `eligible` (boolean) and `exclusion_reason` (text, nullable)
- [ ] Minimum exclusion criteria:
  - Protected areas (CAPAD overlap)
  - Invalid or missing critical data (e.g. no wind data)
  - Other rules justified by Sprint 0 (steep slope, urban areas, etc.)
- [ ] Output format:

  | cell_id | eligible | exclusion_reason |
  |---------|----------|------------------|
  | NSW001  | Yes      | —                |
  | NSW002  | No       | Protected area   |
  | NSW003  | No       | Missing wind data|

- [ ] A cell can have multiple exclusion reasons (comma-separated or list)
- [ ] Exclusion summary statistics are logged (total cells, eligible, excluded by reason)
- [ ] Automated — runs as part of the pipeline

---

## S1-08: Create the Integrated NSW Feature Table

**Type:** Story  
**Priority:** High  
**Story Points:** 5  
**Labels:** integration, pipeline  
**Blocked by:** S1-03, S1-04, S1-05, S1-06, S1-07  
**Blocks:** S1-09, S1-10

### Description

Join all feature layers and the exclusion layer into a single integrated site dataset for NSW.

### Acceptance Criteria

- [ ] Pipeline step (`pipeline/integration/`) merges all feature layers by `cell_id`
- [ ] Output table includes at minimum:

  | cell_id | wind | demand_proxy | dist_transmission | dist_substation | slope | protected | eligible |
  |---------|------|--------------|-------------------|-----------------|-------|-----------|----------|

- [ ] All columns retain their units, documented in metadata or column naming convention
- [ ] Rows for excluded cells are retained but marked as ineligible
- [ ] Output saved as GeoPackage (with geometry) and CSV (without geometry) for flexibility
- [ ] Row count matches the total analysis grid cell count
- [ ] Merge validation: no unexpected NaN inflation from bad joins
- [ ] Automated — single command runs the full pipeline from raw data to integrated table

---

## S1-09: Data Quality and Confidence Layer

**Type:** Story  
**Priority:** Medium  
**Story Points:** 3  
**Labels:** quality, confidence  
**Blocked by:** S1-08  
**Blocks:** S1-10

### Description

Add a data-quality and confidence assessment to the integrated dataset so that downstream scoring can account for certainty.

### Acceptance Criteria

- [ ] Each cell in the integrated table has a composite `data_confidence` score or flag
- [ ] Confidence reflects: number of missing features, spatial resolution mismatch, known data limitations
- [ ] Confidence methodology is documented
- [ ] Cells with low confidence are not excluded but clearly flagged
- [ ] Summary report: distribution of confidence scores, count of cells at each level
- [ ] Per-feature confidence flags (from S1-03 through S1-06) are preserved in the integrated table

---

## S1-10: Add a Simple Baseline Suitability Model

**Type:** Story  
**Priority:** Medium  
**Story Points:** 5  
**Labels:** scoring, model  
**Blocked by:** S1-08, S1-09  
**Blocks:** S1-11

### Description

Implement a transparent, deterministic baseline suitability scoring model. This is NOT a machine-learning model — it is a weighted multi-criteria scoring function that the user can interrogate.

### Acceptance Criteria

- [ ] Scoring module (`pipeline/scoring/`) takes the integrated feature table as input
- [ ] Criteria weights are configurable inputs (not hard-coded)
- [ ] Default weights are documented with rationale
- [ ] Scoring formula is documented and deterministic
- [ ] Only eligible cells (from exclusion layer) receive a score
- [ ] Score is normalised to [0, 1] range
- [ ] Output: `cell_id | suitability_score | rank | confidence`
- [ ] Model does NOT use wind data to predict wind data (no circular modelling per Constitution)
- [ ] Explainability: for any cell, the contribution of each criterion to its score is retrievable

---

## S1-11: Generate a Preliminary Ranked Shortlist

**Type:** Story  
**Priority:** Medium  
**Story Points:** 2  
**Labels:** output, shortlist  
**Blocked by:** S1-10  
**Blocks:** S1-12

### Description

Produce the Sprint 1 headline output: a ranked list of the top candidate sites/cells in NSW.

### Acceptance Criteria

- [ ] Pipeline generates a ranked shortlist (top N configurable, default 20)
- [ ] Output format:

  | rank | cell_id | suitability_score | confidence | lat | lon |
  |------|---------|-------------------|------------|-----|-----|

- [ ] Shortlist includes geographic coordinates for easy verification
- [ ] Export as CSV and optionally GeoJSON for map visualisation
- [ ] Summary statistics: score distribution, geographic spread of top sites
- [ ] Output file is timestamped and versioned

---

## S1-12: Validation and Sanity Check

**Type:** Story  
**Priority:** High  
**Story Points:** 3  
**Labels:** validation, qa  
**Blocked by:** S1-11  
**Blocks:** —

### Description

Verify that the pipeline outputs are plausible by checking against known reality. Per the Constitution: "Validate against reality — check that known successful wind development areas score highly."

### Acceptance Criteria

- [ ] Compare top-ranked cells against locations of existing operational wind farms in NSW
- [ ] Known wind farm sites should appear in or near high-scoring cells — document results
- [ ] Check that cells in obviously unsuitable areas (urban centres, national parks) are correctly excluded
- [ ] Spot-check 5–10 cells manually: verify feature values against source data
- [ ] Document any anomalies or unexpected results with investigation notes
- [ ] If validation reveals systematic issues, log them as bugs/improvements for Sprint 2
- [ ] Validation report saved as `outputs/sprint1_validation_report.md`

---

## Summary — Sprint 1 Dependency Graph

```
S1-01 (Data Spec)
  └── S1-02 (Analysis Cell)
        ├── S1-03 (Wind)
        ├── S1-04 (Demand)
        ├── S1-05 (Infrastructure)
        └── S1-06 (Geographic)
              └── S1-07 (Exclusions)
                    └── S1-08 (Integrated Table)
                          └── S1-09 (Quality)
                                └── S1-10 (Scoring)
                                      └── S1-11 (Shortlist)
                                            └── S1-12 (Validation)
```

---

## Import Notes

- **Total Story Points:** ~47
- **Critical Path:** S1-01 → S1-02 → S1-03/04/05/06 (parallel) → S1-07 → S1-08 → S1-09 → S1-10 → S1-11 → S1-12
- **Parallelisable:** S1-03, S1-04, S1-05, S1-06 can be worked concurrently once S1-01 and S1-02 are complete
