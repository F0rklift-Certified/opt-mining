# Sprint 1 — Out-of-Scope Datasets

**Version:** 1.0
**Date:** 2026-08-27
**Companion to:** `sprint1_data_specification.md`

---

## Purpose

This document records all datasets investigated during Sprint 0 that were **excluded** from the Sprint 1 MVP pipeline, along with the specific reason for exclusion and the conditions under which each might be reconsidered.

**Governance rule:** Adding a dataset from this list to the active specification requires:
1. A documented gap in the current specification that the new dataset fills
2. Full metadata recorded per the format defined in `sprint1_data_specification.md`
3. A version bump to the specification document
4. Approval via the change-control process (specification §8)

---

## 1. Excluded Datasets

These datasets were investigated in Sprint 0 but are **not used** in the Sprint 1 pipeline — neither for scoring nor for validation/context.

| # | Dataset | Domain | Source | Reason for Exclusion | Revisit Condition |
|---|---------|--------|--------|---------------------|-------------------|
| 1 | GWA v4 Wind Speed @ 10/50/200 m | Wind | Global Wind Atlas (DTU) | 100 m is the primary height (capacity factor consistency, decision Q2); 150 m carried as sensitivity. Additional heights add no information for cell-level screening — the mean aggregation across 400 pixels already dominates over height-to-height differences within a cell. | Revisit if the team changes the primary hub height decision, or if height-dependent shear modelling becomes a V2 requirement. |
| 2 | GWA v4 Power Density @ 10/50/150/200 m | Wind | Global Wind Atlas (DTU) | Hub height decision is 100 m (Q2). Power density at other heights is redundant — the relationship between heights is monotonic and already captured by the wind-speed sensitivity layer at 150 m. | Revisit only if multi-height power density profiling becomes a requirement (unlikely for screening). |
| 3 | GWA v4 Air Density (all heights) | Wind | Global Wind Atlas (DTU) | Required only for energy-yield modelling (converting wind speed to power via `P = 0.5 × rho × A × v³`), which is explicitly out of scope for V1 per the Product Knowledge Base. The platform ranks locations, not estimates of annual energy production. | Revisit if V2 introduces indicative AEP estimation beyond the capacity-factor presentation layer. |
| 4 | GWA v4 Weibull A & k (all heights) | Wind | Global Wind Atlas (DTU) | Required only for energy-yield modelling or directional wind analysis, both out of scope for V1. The publisher's own caveat notes that combined Weibull parameters can differ substantially from directional distributions where wind arrives from multiple directions. | Revisit if V2 requires directional analysis or custom power-curve integration. |
| 5 | GWA v4 Capacity Factor IEC1 / IEC3 | Wind | Global Wind Atlas (DTU) | IEC2 is sufficient as the single presentation layer. Additional turbine classes add comparison complexity without improving the screening ranking — the relative ordering between cells is largely preserved across IEC classes (they use the same wind field, just different power curves). | Revisit if the platform supports user-selectable turbine models or IEC class comparison in V2. |
| 6 | GWA v4 Capacity Factor Offshore | Wind | Global Wind Atlas (DTU) | V1 is onshore wind only. Offshore cells are excluded by the land mask (ABS Australia outline). The offshore CF layer also returns HTTP 403 from the per-country API — only available as a 16 GB global file. | Revisit if the platform extends to offshore wind technology in a future version. |
| 7 | GWA v4 RIX / Site Elevation (global files) | Wind / Geographic | Global Wind Atlas (DTU) via DTU Data repository | Terrain data sourced from SRTM GL3 instead, which provides elevation and derived slope at sufficient quality for screening. The GWA global files are 6.1 GB (RIX) and 8.9 GB (elevation), and per-country API access returns HTTP 403. The SRTM-derived slope already serves the terrain penalty criterion. | Revisit only if RIX (a specific ruggedness index related to flow separation risk) becomes a distinct criterion beyond slope — unlikely for V1 screening. |
| 8 | SRTM GL1 (~30 m) / Derived TRI | Geographic | OpenTopography (NASA SRTM) | GL3 (~90 m) is sufficient for screening-scale slope at the 5 km cell level. GL1 adds noise without improving the cell-level statistic: Task 4 quantified that GL1-derived slope runs +1.31° hotter than GL3 at the same footprint due to capturing finer-scale terrain features that average out at the analysis scale. TRI (Terrain Ruggedness Index) from GL1 was a proof-of-concept; slope from GL3 covers the terrain penalty need. | Revisit if a future sprint requires sub-cell terrain characterisation (e.g., micro-siting within candidate areas) or if TRI is added as a distinct criterion. |
| 9 | AEMO Key Connection Information (KCI) 2026 | Infrastructure | AEMO | No geographic coordinates in the workbook. Cannot be used for spatial scoring. Contains project identifiers, proponent names, plant types, text site descriptions, and capacity fields — all useful as planning context but not spatially joinable to grid cells. | Revisit if AEMO publishes a version with lat/lon columns, or if a geocoding exercise links KCI projects to coordinates. |
| 10 | OSM Road Network (Australia) | Geographic | Geofabrik (OpenStreetMap) | Not acquired in Sprint 0 (registered as a 958.7 MB PBF file, probed by HEAD only). Distance-to-road is a secondary priority per Task 4's investigation checklist — the four primary criteria (wind, demand, infrastructure, geographic) are sufficient for V1 screening. Road access affects construction cost but is less discriminating than transmission proximity at the screening stage. | Revisit for V2 if a "construction accessibility" sub-criterion is added, or if the team decides road distance materially improves discrimination between candidate cells. |
| 11 | GA Major Power Stations 2026 | Infrastructure | Geoscience Australia | Validation and context layer only — not a criterion input. Existing generators do not determine where new ones should go (a cell next to an existing wind farm is not inherently better or worse for new development — that depends on wind, grid capacity, and land). The wind generators subset is retained separately as a validation reference (see Context-Only below). | Revisit only if "clustering with existing generation" becomes a criterion — currently not in the Product Knowledge Base. |
| 12 | AEMO / EnergyCo REZ Boundaries | Infrastructure | AEMO ISP 2026 (KMZ); NSW EnergyCo (Shapefile) | Context/validation overlay only — not a scoring input. REZ status is a planning designation, not a physical attribute of the land. A cell inside a REZ is not inherently better for wind development; it means the government has identified the area for coordinated investment. This is a sense-check layer ("do our high-scoring cells fall in or near REZs?"), not a scoring input. | Revisit if the platform adds a "policy alignment" criterion that explicitly rewards REZ membership. |

---

## 2. Context-Only Datasets

These datasets are **retained in the repository** for validation, sense-checking, or labelling purposes, but they are **not scoring inputs** and do not feed any criterion in the Sprint 1 pipeline.

| # | Dataset | Domain | Use in Sprint 1 | Why Not a Scoring Input |
|---|---------|--------|-----------------|------------------------|
| 1 | GA Wind Generators 2026 (NSW) | Infrastructure | **Validation** — Confirm that known operational wind farms (White Rock, Sapphire, etc.) score highly in the pipeline output. If a known-good site ranks poorly, the scoring model is suspect. | Existing wind farm locations are validation anchors, not scoring criteria. A cell is not better because it already has a wind farm — that would be circular. |
| 2 | AEMO Indicative REZ Boundaries 2026 | Infrastructure | **Map overlay and sense-check** — Do high-scoring cells cluster in or near designated REZs? Provides planning context for the user without influencing the ranking. | REZ designation is a policy decision, not a physical measurement. The platform scores physical and infrastructure attributes; policy alignment is interpretive context. |
| 3 | EnergyCo NSW REZ Boundaries | Infrastructure | **NSW-specific validation overlay** — Same purpose as AEMO REZ but with official NSW geographical-area boundaries (New England, Central-West Orana, Hunter-Central Coast). Higher fidelity for the NSW-first scope. | Same rationale as AEMO REZ — policy overlay, not physical criterion. |
| 4 | Natural Earth 1:50m Land | Geographic | **Reference for land-mask comparison** — Retained to document why the ABS outline was chosen over NE as the production mask. The `landmask_assessment.md` shows 21 of 28 NE false-land cells carry top-decile wind — the ABS outline prevents those from leaking into results. | Not a mask candidate for production use. 1:50m generalisation smooths the coastline by kilometres in places. Superseded by the ABS outline (§4.4.1). |
| 5 | ABS ASGS 2021 LGA (Local Government Areas) | Geographic | **Labelling layer** — Attach LGA names to output cells for human readability (e.g., "Glen Innes Severn" rather than just coordinates). Also useful for stakeholder communication and report generation. | Administrative boundaries do not measure physical suitability. LGA names add interpretability to results but cannot influence rankings. |

---

## 3. Datasets Not Investigated (Known Gaps)

For completeness, these are data sources identified during Sprint 0 as potentially relevant but not investigated due to time constraints or access limitations. They are recorded here for future reference.

| # | Dataset | Domain | Why Not Investigated | Future Potential |
|---|---------|--------|---------------------|-----------------|
| 1 | ABS Gridded Population Estimates | Demand | SA2-level ERP (decision Q4) was deemed sufficient resolution for ~5 km cells. Gridded products would improve sub-SA2 allocation but add complexity. | V2 refinement of demand allocation if SA2-level proves too coarse. |
| 2 | Mining Leases / Native Title Determinations | Geographic | Not publicly available as a consolidated spatial dataset in a form suitable for automated ingestion. Would be additional hard exclusions in a production system. | V2 if a reliable, Australia-wide spatial dataset becomes available. |
| 3 | AEMO WEM (Western Australia) Demand | Demand | Not part of NEM. Would require separate investigation, different data format, different region structure. | Future version if platform extends beyond NEM coverage to include WA. |
| 4 | DEA Coastlines (Digital Earth Australia) | Geographic | Registered in the source register as a higher-fidelity upgrade path for the coastline/land mask. Not sampled because the ABS outline was assessed as adequate for 5 km cells. | V2 if sub-km coastal analysis becomes relevant (e.g., near-shore wind). |
| 5 | Bureau of Meteorology Station Data | Wind | Rejected in Task 1: point measurements at 10 m, too sparse and too low for utility-scale screening. The GWA already downscales from ERA5 which assimilates BoM observations. | Revisit only if independent measurement-based validation of the GWA is required beyond the wind-farm spot checks already performed. |

---

## Change History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-08-27 | Initial release — Sprint 1 baseline |
