# Opt-Mining – Product Knowledge Base

*Status: Living document. Updated as Sprint 0 resolves data and technical questions.*

*Updated following the client meeting. Unresolved questions are collected under Open Questions.*

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

A "site" is a **grid cell**, at approximately **5 km** resolution.

This is screening-level resolution, chosen deliberately: native raster resolution across Australia will not run on the available hardware. The resolution and its limitations must be documented wherever results are presented.

If national-scale processing proves too computationally expensive, demonstrate on one or several states - NSW first - while keeping the architecture capable of national expansion.

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

Derives a robust regional demand indicator from AEMO historical NEM demand, then allocates it to grid cells. AEMO reports at NEM region level (NSW1, QLD1, SA1, TAS1, VIC1); the allocation proxy from region to cell must be chosen and documented.

### Infrastructure Accessibility

Distance and access measures derived from transmission lines, substations, connection points, generators and renewable energy zones.

### Exclusion and Constraint Filter

A small number of defensible hard exclusions, subject to data availability:

* Protected areas and national parks - hard exclusion.
* Clearly unsuitable geographic areas - hard exclusion.
* Slope and terrain - investigate as a suitability penalty or threshold, not an automatic exclusion.
* Grid proximity - investigate as a suitability penalty or threshold, not an automatic exclusion.

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
* Provenance travels with the data.
* Analyses are reproducible from recorded inputs and versions.
* Results are explainable, not merely presented.
* Data quality is a first-class output, not a footnote.

## Repository and Documentation

* The repository is private.
* All dataset sources and third-party library licences are documented.
* Results must be reproducible and transparent.

## Data Sources

Investigated in Sprint 0 before implementation is locked.

| Source | Use | Priority |
|---|---|---|
| Global Wind Atlas | Mean wind speed, power density, terrain roughness, orography, capacity-factor layers | Highest |
| AEMO - NEM demand | Historical regional demand indicator, ~3–5 recent complete years | High |
| AEMO - network and generation | Substations, transmission lines, connection points, generators | High |
| Geoscience Australia | National DEM, ~30 m SRTM-derived elevation; slope | High |
| Administrative boundaries / NationalMap | Region and state geometry | Medium |
| Protected and environmentally constrained areas | Hard exclusions | Medium |
| Existing renewable energy facilities | Validation reference | Medium |
| Road and accessibility data | Access measures | Secondary |

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

**ML Suitability Indicator (conditional).** Investigate whether publicly available wind-farm and development locations provide sufficient reference examples to train an additional data-driven suitability score based on wind, infrastructure, terrain and other available features. This component complements — not replaces — the transparent weighted suitability model. Proceed with implementation only if suitable training/reference data are confirmed in Sprint 0. If the data is insufficient, document the finding and defer.

**Demand Indicator.** Investigate AEMO NEM historical demand data covering approximately 3–5 recent complete years and recommend the most appropriate dataset. Because AEMO demand is regional (NEM region level), investigate population weighting as the spatial proxy for allocating demand to 5 km cells. Clearly document that the result is an estimated demand indicator, not actual local consumption.

## Known Risks

* **Data integration.** Sources differ in format, resolution, projection, region naming and update cadence. This is the most likely source of silent error, and the reason Sprint 0 exists.
* **Computational cost.** Continental-scale geospatial processing is expensive; the ~5 km grid is the primary mitigation, with state-level demonstration as the fallback.
* **The ML deliverable.** See Open Questions - the mandatory deliverable and the client's data framing are not yet fully reconciled.
* **Demand allocation.** A weak region-to-cell proxy would undermine the demand criterion regardless of how good the other data is.
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
