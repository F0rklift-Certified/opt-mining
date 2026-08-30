# Opt-Mining – Product Knowledge Base

*Status: Living document. Version 1.1 — updated 2026-08-30 to reflect the Sprint 1 freeze (2026-08-27).*

*Sprint 0 has resolved the data and technical questions this document originally left open. The authoritative, frozen detail now lives in:*

- *`DATA/data-specification/sprint1_data_specification.md` — frozen dataset list, parameters and CRS/temporal strategy (v1.0, 2026-08-27).*
- *`DATA/data-specification/sprint1_out_of_scope.md` — datasets investigated but excluded, with revisit conditions.*
- *`DATA/grid/decision_analysis_cell.md` — the finalised common analysis cell decision (S1-02).*

*This knowledge base is the product-level summary; where it and the frozen specification differ, the specification governs.*

## Product Definition

A prototype decision-support platform that identifies and ranks locations across Australia by their suitability for future wind energy development, using resource, demand, infrastructure and environmental criteria, and presents the result through an interactive web dashboard and map.

## What "Optimal" Means

Suitability is a **multi-criteria score**, not maximum wind generation.

The four core criteria for Version 1:

1. **Wind resource potential** - derived from Global Wind Atlas.
2. **Electricity demand** - a regional indicator derived from AEMO historical data.
3. **Grid and infrastructure accessibility** - proximity to transmission, substations, connection points.
4. **Geographic and environmental suitability** - terrain, land use, protected areas.

Users can adjust the decision criteria and obtain a re-ranked shortlist. Weighting is a user input, not a hard-coded constant.

## Core Workflow

1. Inventory, inspect and document each source dataset before use.
2. Ingest and validate source data, recording source, licence, vintage and units.
3. Normalise everything onto a common analysis grid and coordinate system.
4. Derive criteria features for each cell - resource, demand, infrastructure, geography.
5. Apply hard exclusions to remove unusable cells.
6. Score each remaining cell against the weighted criteria.
7. Assess data quality per cell and classify it.
8. Rank cells and produce a shortlist - Top 10 or Top 20.
9. Explain each recommendation: which criteria drove the score, and with what confidence.
10. Visualise resource, demand and rankings on an interactive map.
11. Export the shortlist and its configuration.

## Site Definition

A "site" is a **grid cell**. The cell is now finalised (S1-02) as a **0.05° cell anchored to the Global Wind Atlas v4 raster origin** — approximately **4.7 km × 5.56 km** at NSW mid-latitudes (~25 km²). Storage is EPSG:4326 (WGS 84); all distance and area calculations use EPSG:3577 (GDA94 / Australian Albers, equal-area). Each cell is exactly 20 × 20 GWA native pixels, so wind data aggregates cleanly with no boundary ambiguity.

This is screening-level resolution, chosen deliberately: native raster resolution across Australia will not run on the available hardware. Cell width varies ~10% with latitude and cells are not equal-area; both facts must be documented wherever results are presented.

Sprint 1 is scoped to **NSW first (~47,311 cells in the bounding box; land-masking deferred to S1-06/S1-07)**, with the architecture kept capable of national expansion (~278,000 land cells, profiling required before Sprint 2). See `DATA/grid/decision_analysis_cell.md` for the full decision and alignment proof.

## Core Platform Components

### Data Inventory and Dictionary

The Sprint 0 artefact and an ongoing reference: what each dataset contains, its columns, row counts, missing values, coordinate fields, units, date fields, resolution, format, licence and known integration problems.

### Data Integration Pipeline

Fetches, validates, normalises and versions external datasets. Records provenance and licence. The only component permitted to write raw source data into the platform.

### Geospatial Data Store

Holds the analysis grid and all derived criteria layers in a single, explicitly declared coordinate reference system.

### Criteria Feature Builder

Turns each source dataset into a per-cell feature. Wind speed and power density from Global Wind Atlas become features here - **the Atlas is an input, not something the system predicts**.

### Demand Indicator

Derives a robust regional demand indicator from AEMO historical NEM demand, then allocates it to grid cells. AEMO reports at NEM region level (NSW1, QLD1, SA1, TAS1, VIC1). The allocation approach is now frozen (Sprint 1 §2, decisions Q4/Q5): use **operational demand** (grid-served load, excluding behind-the-meter PV that new wind cannot displace), aggregated to **annual mean MW per NEM region**, then allocate to cells by **population weighting using ABS Census 2021 Estimated Resident Population at SA2 level** (`cell_demand = region_annual_mean_MW × cell_population / region_total_population`). The result is always labelled an *estimated demand indicator*, never actual local consumption.

### Infrastructure Accessibility

Distance and access measures derived from transmission lines, substations, connection points, generators and renewable energy zones.

### Exclusion and Constraint Filter

A small number of defensible hard exclusions, now frozen (Sprint 1 §4.4 and decisions Q3/Q6/Q7):

* **Protected areas** - hard exclusion. Binary: any CAPAD 2024 terrestrial polygon intersecting a cell excludes the whole cell (decision Q6).
* **Ocean** - hard exclusion. Cells outside the ABS 2021 Australia outline (land mask).
* **Water bodies** - hard exclusion. NLUM class 6 (lakes, reservoirs, rivers).
* **Dense urban** - hard exclusion. NLUM class 5.4.x, cross-checked against ABS UCL polygons.
* **Slope and terrain** - resolved as a **continuous suitability penalty**, not an exclusion (decision Q3): mean slope per cell drives the scoring penalty; P90 slope is reported in the explanation layer.
* **Grid proximity** - resolved as a **continuous distance penalty**, not an exclusion (decision Q7): Euclidean distance (EPSG:3577) to the nearest transmission line ≥132 kV and nearest substation. No hard distance threshold — remote cells rank low naturally.

Deterministic, inspectable rules, kept separate from the scoring model.

### Suitability Scoring Model

Combines the criteria features into a per-cell suitability score using user-adjustable weights. Deterministic and inspectable by default; see Open Questions on where machine learning contributes.

### Data Quality and Confidence

Three cases, applied platform-wide:

| Case | Behaviour |
|---|---|
| Critical data missing | Exclude the cell from ranking |
| Non-critical data missing or low confidence | Retain, and clearly flag |
| Good data coverage | Rank normally |

A simple data-quality or confidence indicator is displayed alongside every suitability score. Poor-quality data is never silently given a normal ranking.

### Explanation

For each recommended site: which criteria drove the score, their relative contribution, the underlying values, and the confidence attached. This is what the primary user does immediately after receiving a shortlist, so it is core, not decoration.

### Validation

Checks that known successful wind development areas receive reasonably high suitability scores, using publicly available operational and existing wind farm data from AEMO and other Australian government sources. No proprietary Opt-Mining dataset is required or expected.

### Scenario Configuration

One scenario at a time for the MVP: the current configuration is saved and displayed alongside its results. Side-by-side comparison of two or more scenarios is a stretch goal and must not delay core functionality.

### Visualisation and Dashboard

Interactive web map and dashboard. A user opens the application, explores potential locations, adjusts decision criteria, and obtains a ranked list of candidate sites.

### API Layer

The single interface through which the dashboard and any external consumer reach data, analyses and results.

## Architectural Principles

* Data, criteria, scoring and presentation are separate concerns.
* The architecture is modular by technology - wind first, with solar and storage addable later.
* Deterministic rules are expressed as inspectable code, not learned from data.
* Coordinate systems, resolutions and units are explicit at every boundary.
* Temporal alignment is explicit: all inputs are long-run indicators, not synchronised time series. The gap between the wind climatology (2008–2017) and the demand window (2025–2026) is disclosed wherever the two criteria are combined.
* Provenance travels with the data.
* Analyses are reproducible from recorded inputs and versions.
* Results are explainable, not merely presented.
* Data quality is a first-class output, not a footnote.

## Repository and Documentation

* The repository is private.
* All dataset sources and third-party library licences are documented.
* Results must be reproducible and transparent.

## Data Sources

Investigated in Sprint 0 and now **frozen** for Sprint 1. The authoritative dataset detail (exact files, vintages, CRS, licences, limitations) is in `DATA/data-specification/sprint1_data_specification.md`; datasets that were investigated but excluded are in `sprint1_out_of_scope.md`.

| Source | Use | Role |
|---|---|---|
| Global Wind Atlas v4 — wind speed @ 100 m, power density @ 100 m | Wind resource (Criterion 1) | Scoring input |
| Global Wind Atlas v4 — capacity factor IEC2 | Interpretable resource indicator | Presentation/explanation only |
| Global Wind Atlas v4 — wind speed @ 150 m | Hub-height sensitivity | Sensitivity only |
| AEMO NEM operational demand (half-hourly, Jul 2025–Jun 2026) | Regional demand indicator (Criterion 2) | Scoring input |
| ABS Census 2021 ERP @ SA2 | Population weighting for demand allocation | Scoring input (spatial denominator) |
| GA power lines 2026 (≥132 kV) | Distance to transmission (Criterion 3) | Scoring input |
| GA substations 2026 | Distance to substation (Criterion 3) | Secondary scoring input |
| SRTM GL3 (~90 m) + derived Horn slope | Terrain penalty (Criterion 4) | Scoring input (penalty) |
| ABARES NLUM v7.1 (land use) | Water/urban exclusion + land-use penalty (Criterion 4) | Exclusion + penalty |
| DCCEEW CAPAD 2024 (terrestrial protected areas) | Hard exclusion (Criterion 4) | Exclusion |
| ABS ASGS 2021 — Australia outline, STE, UCL + derived NEM regions | Land mask, region assignment, urban cross-check | Exclusion / region join |
| GA wind generators 2026; AEMO/EnergyCo REZ boundaries; ABS LGA | Known wind farms, policy overlay, labelling | Validation / context only (not scored) |
| Road and accessibility data (OSM) | Access measures | **Out of scope for V1** — deferred to V2 |

All sources are public. Licence terms and attribution requirements are recorded with the data and carried through to the interface and exported outputs.

**Not in the MVP:** future climate projections. Begin with historical and current resource and climate information; climate scenario robustness is a later extension and must not become a Sprint 0 blocker.

## MVP Scope

Data Inventory → Ingest and Normalise to ~5 km Grid → Derive Four Criteria → Apply Hard Exclusions → Weighted Suitability Score → Data Quality Classification → Ranked Top 10–20 Shortlist → Explanation → Interactive Map and Dashboard → Export

**MVP Pipeline (priority order):**

1. Data inventory and cleaning
2. Common analysis grid (~5 km)
3. Four criteria derivation (wind resource, demand, infrastructure, geography/environment)
4. Hard exclusions
5. Suitability scoring and ranking
6. Confidence/data-quality assessment
7. Explanation (per-site score breakdown)
8. Interactive map/dashboard
9. Validation against known wind-development areas

Prioritise completing the end-to-end pipeline over adding breadth. Advanced features should not be pursued until this pipeline is complete, tested and validated.

Wind only. Individual site ranking, not portfolio selection. Annual or appropriately aggregated historical indicators, not hourly matching.

Success is a planner producing a defensible, reproducible shortlist in a fraction of the time the equivalent manual screening study would take.

## Expected Deliverables

* A software prototype for renewable energy planning.
* An interactive map.
* A data integration pipeline combining climate and energy datasets.
* A machine learning model for renewable resource estimation - *see Open Questions*.
* An optimisation module for renewable energy site selection - delivered as multi-criteria suitability scoring and ranking for the MVP.
* An interactive web-based dashboard for visualising renewable resource suitability across Australia.
* A technical report documenting the system architecture and algorithms.

## Open Questions

**ML Suitability Indicator (still conditional).** Investigate whether publicly available wind-farm and development locations provide sufficient reference examples to train an additional data-driven suitability score based on wind, infrastructure, terrain and other available features. This component complements — not replaces — the transparent weighted suitability model. Proceed with implementation only if suitable training/reference data are confirmed. Note the constraint surfaced in Sprint 0: existing wind-farm locations are treated as **validation anchors, not scoring or training inputs** — rewarding cells for already hosting a wind farm would be circular. Any ML indicator must avoid that leakage. If the data is insufficient, document the finding and defer.

## Resolved Questions (Sprint 1 freeze, 2026-08-27)

**Demand Indicator — RESOLVED (decisions Q4/Q5).** Use AEMO **operational demand** (not total demand), aggregated to annual mean MW per NEM region, allocated to cells by population weighting using **ABS Census 2021 ERP at SA2 level**. One year (Jul 2025–Jun 2026) is downloaded and complete; extendable to 3+ years for robustness in a later sprint. The result is always labelled an estimated demand indicator. See `sprint1_data_specification.md` §4.2.

**Common analysis cell — RESOLVED (S1-02).** 0.05° GWA-aligned geographic cells, EPSG:4326 storage / EPSG:3577 computation. See `decision_analysis_cell.md`.

**Slope, grid proximity and protected-area handling — RESOLVED (decisions Q3/Q6/Q7).** Slope and grid proximity are continuous penalties; protected areas are a binary hard exclusion. See the Exclusion and Constraint Filter section above.

## Known Risks

* **Data integration.** Sources differ in format, resolution, projection, region naming and update cadence. This is the most likely source of silent error, and the reason Sprint 0 exists.
* **Computational cost.** Continental-scale geospatial processing is expensive; the ~5 km grid is the primary mitigation, with state-level demonstration as the fallback.
* **The ML deliverable.** See Open Questions - the mandatory deliverable and the client's data framing are not yet fully reconciled. Sprint 0 established that existing wind-farm data is a validation anchor, not a training/scoring input, which constrains any future data-driven indicator.
* **Demand allocation.** A weak region-to-cell proxy would undermine the demand criterion regardless of how good the other data is. Mitigated by the frozen SA2 population-weighting approach (decision Q4), but the proxy's limitations (uniform allocation within each SA2, industrial loads not captured) remain and must be disclosed.
* **False precision.** Screening-level output presented with more confidence than the resolution supports.

## Future Capability Areas

These items remain out of scope unless the core MVP pipeline is complete, tested and validated.

In rough order of defensibility as extensions:

* Portfolio selection - choosing sites jointly for total demand coverage, geographic diversity and infrastructure constraints, rather than ranking them individually.
* Solar, battery storage and other technologies.
* Seasonal or temporal resource-and-demand matching.
* Scenario comparison side by side.
* Climate change projections, testing whether suitability holds under future conditions.
* Indicative cost proxy - never presented as a bankable project cost or guaranteed LCOE.
