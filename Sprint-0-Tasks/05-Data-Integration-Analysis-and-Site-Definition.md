# Task 5 — Data Integration Analysis & Site Definition Proposal

**Sprint:** 0 (Week 1)
**Assignee:** Pouya Mousavi
**Status:** Complete
**Estimated Effort:** 1–2 days (begin after Tasks 1–4 are substantially complete)

---

## 1. Objective

Synthesise the findings from the four data investigation tasks (wind, demand, infrastructure, geographic) into a consolidated data inventory, identify cross-dataset integration challenges, propose the four core criteria for Version 1, and recommend how the system should define a "site."

This is the thinking-and-synthesis task. Its output directly shapes the platform architecture in Sprint 1.

---

## 2. Context

Tasks 1–4 each investigate data in isolation. This task asks: **how do these datasets fit together?**

The Product Knowledge Base already proposes:
- A ~5km grid cell as the site definition
- Four core criteria: wind resource, demand, infrastructure accessibility, geographic/environmental suitability
- NSW-first as a computational fallback if national scale is too expensive

This task validates those proposals against the actual data found, identifies gaps and conflicts, and produces a concrete recommendation the team can implement.

---

## 3. Prerequisites

This task depends on outputs from:
- [x] Task 1 — Wind Resource Data Investigation (findings + integration issues)
- [x] Task 2 — Electricity Demand Data Investigation (findings + integration issues)
- [x] Task 3 — Electricity Infrastructure Data Investigation (findings + integration issues)
- [x] Task 4 — Geographic & Environmental Data Investigation (findings + integration issues)

All four tasks are complete with inspection reports, data dictionaries, and documented integration issues.

---

## 4. Consolidated Data Inventory

*Master reference table compiled from all four investigation tasks.*

| # | Dataset Name | Source | Domain | Format | CRS | Spatial Resolution | Temporal Coverage | Licence | Usable? | Priority |
|---|-------------|--------|--------|--------|-----|-------------------|-------------------|---------|---------|----------|
| 1 | GWA v4 Wind Speed (50/100/150/200 m) | Global Wind Atlas (DTU) | Wind | GeoTIFF (float32, tiled, zstd) | EPSG:4326 | 0.0025° (~250 m) | 2008–2017 mean | CC BY 4.0 | Yes | Highest |
| 2 | GWA v4 Power Density (100 m) | Global Wind Atlas (DTU) | Wind | GeoTIFF (float32, tiled, zstd) | EPSG:4326 | 0.0025° (~250 m) | 2008–2017 mean | CC BY 4.0 | Yes | Highest |
| 3 | GWA v4 Capacity Factor (IEC1/IEC2/IEC3) | Global Wind Atlas (DTU) | Wind | GeoTIFF (float32, tiled, zstd) | EPSG:4326 | 0.0025° (~250 m) | 2008–2017 mean | CC BY 4.0 | Yes | High |
| 4 | GWA v4 Air Density / Weibull A & k | Global Wind Atlas (DTU) | Wind | GeoTIFF (float32, tiled, zstd) | EPSG:4326 | 0.0025° (~250 m) | 2008–2017 mean | CC BY 4.0 | Yes | Low (V1 not needed) |
| 5 | AEMO Operational Demand (Half-Hourly) | AEMO NEMWeb | Demand | CSV (nested ZIPs) | N/A (tabular) | NEM Region (5 regions) | Jul 2025 – Jun 2026 (extendable) | Public (attribution) | Yes | High |
| 6 | GA Power Lines 2026 | Geoscience Australia | Infrastructure | GeoJSON (ArcGIS REST) | EPSG:7844 | Vector (line geometry) | Current (downloaded 2026-08-13) | CC BY 4.0 | Yes | High |
| 7 | GA Substations 2026 | Geoscience Australia | Infrastructure | GeoJSON (ArcGIS REST) | EPSG:7844 | Vector (point geometry) | Current (downloaded 2026-08-15) | CC BY 4.0 | Yes | High |
| 8 | GA Major Power Stations 2026 | Geoscience Australia | Infrastructure | GeoJSON (ArcGIS REST) | EPSG:7844 | Vector (point geometry) | Current (downloaded 2026-08-15) | CC BY 4.0 | Yes | Medium (validation) |
| 9 | AEMO Indicative REZ Boundaries 2026 | AEMO ISP | Infrastructure | KMZ (KML polygons) | EPSG:4326 | Vector (polygon) | 2026 ISP | Public | Yes | Medium (context) |
| 10 | EnergyCo NSW REZ Boundaries | NSW EnergyCo | Infrastructure | Shapefile | EPSG:4283 | Vector (polygon) | Current | Public (NSW Govt) | Yes | Medium (NSW scope) |
| 11 | AEMO Key Connection Info (KCI) | AEMO | Infrastructure | XLSX | N/A (tabular, no coords) | Tabular | Q2 2026 | Public | Conditional | Low (no coords) |
| 12 | SRTM GL3 Elevation (~90 m) | OpenTopography (NASA SRTM) | Geographic | GeoTIFF (int16, via /vsicurl/) | EPSG:4326 | 0.000833° (~90 m) | SRTM mission (2000) | Public domain | Yes | High |
| 13 | SRTM GL1 Elevation (~30 m) | OpenTopography (NASA SRTM) | Geographic | GeoTIFF (int16, via /vsicurl/) | EPSG:4326 | 0.000278° (~30 m) | SRTM mission (2000) | Public domain | Yes | Medium (fine detail) |
| 14 | Derived Horn Slope (from GL3) | This project (derived) | Geographic | GeoTIFF (int16 × 0.01 scale) | EPSG:4326 | ~90 m | Derived | N/A | Yes | High |
| 15 | Derived Riley TRI (from GL1) | This project (derived) | Geographic | GeoTIFF (int16 × 0.1 scale) | EPSG:4326 | ~30 m | Derived | N/A | Yes | Medium |
| 16 | DCCEEW CAPAD 2024 (Terrestrial) | DCCEEW | Geographic | GeoJSON (ArcGIS REST) | EPSG:4283 (native) | Vector (polygon) | CAPAD 2024 | CC BY 4.0 | Yes | High (hard exclusion) |
| 17 | ABARES NLUM v7.1 250m (ALUM v8) | ABARES | Geographic | GeoTIFF (int16, categorical) | EPSG:3577 | 250 m | 2020–21 | CC BY 4.0 | Yes | High (exclusion + penalty) |
| 18 | ABS ASGS 2021 STE (State boundaries) | ABS | Geographic | GeoJSON (ArcGIS REST) | GDA2020 (served via 3857) | Vector (polygon) | 2021 (Ed. 3) | CC BY 4.0 | Yes | High (reference) |
| 19 | ABS ASGS 2021 AUS (Australia outline) | ABS | Geographic | GeoJSON (ArcGIS REST) | GDA2020 (served via 3857) | Vector (polygon) | 2021 (Ed. 3) | CC BY 4.0 | Yes | High (land mask) |
| 20 | ABS ASGS 2021 LGA (Local Govt Areas) | ABS | Geographic | GeoJSON (ArcGIS REST) | GDA2020 (served via 3857) | Vector (polygon) | 2021 (Ed. 3) | CC BY 4.0 | Yes | Medium |
| 21 | ABS ASGS 2021 UCL (Urban Centres) | ABS | Geographic | GeoJSON (ArcGIS REST) | GDA2020 (served via 3857) | Vector (polygon) | 2021 (Ed. 3) | CC BY 4.0 | Yes | High (exclusion) |
| 22 | ABS ASGS 2021 SA2 (Statistical Areas) | ABS | Geographic | GeoJSON (ArcGIS REST) | GDA2020 (served via 3857) | Vector (polygon) | 2021 (Ed. 3) | CC BY 4.0 | Yes | High (demand proxy) |
| 23 | Natural Earth 1:50m Land | Natural Earth | Geographic | GeoJSON | EPSG:4326 | ~50 m coastline | Current | Public domain | Yes | Medium (alt. mask) |
| 24 | Derived NEM Regions | This project (from ABS STE) | Geographic | GeoJSON | EPSG:4326 | Vector (polygon) | Derived (2021 basis) | N/A | Yes | High (demand join) |

---

## 5. Cross-Dataset Integration Issues

### 5a. Coordinate Reference System (CRS) Alignment

| Dataset | Native CRS | EPSG | Target CRS | Datum Offset to WGS84 | Transformation Required? | Notes |
|---------|-----------|------|------------|----------------------|--------------------------|-------|
| GWA v4 (all layers) | WGS 84 | 4326 | EPSG:4326 | 0 m | No | Native — no transformation |
| SRTM GL1/GL3 | WGS 84 | 4326 | EPSG:4326 | 0 m | No | Native — no transformation |
| Natural Earth land | WGS 84 | 4326 | EPSG:4326 | 0 m | No | Native — no transformation |
| AEMO REZ (KMZ) | WGS 84 (KML) | 4326 | EPSG:4326 | 0 m | No | Native — no transformation |
| GA Power Lines/Substations/Stations | GDA2020 | 7844 | EPSG:4326 | ~1.5 m | Yes (declare explicitly) | Offset negligible at 5 km |
| ABS ASGS 2021 (all layers) | GDA2020 (via 3857) | 7844 | EPSG:4326 | ~1.5 m | Yes (outSR must be explicit) | Service defaults to 3857! |
| DCCEEW CAPAD 2024 | GDA94 | 4283 | EPSG:4326 | ~1.8 m | Yes (declare explicitly) | Offset negligible at 5 km |
| EnergyCo NSW REZ | GDA94 | 4283 | EPSG:4326 | ~1.8 m | Yes (declare explicitly) | Offset negligible at 5 km |
| ABARES NLUM 250m | GDA94 / Albers | 3577 | EPSG:4326 | ~1.8 m + reprojection | Yes (warp required) | Projected CRS — nearest-neighbour resampling |
| AEMO Demand | N/A (tabular) | — | N/A | — | No | Spatial allocation via population proxy |

**Recommendation for project-wide CRS:**

- **Storage CRS:** EPSG:4326 (WGS 84 geographic). Rationale: the largest dataset (GWA, 600+ MB per layer) is natively 4326; reprojecting it to accommodate smaller vector layers is wasteful. All other geographic-CRS datasets have negligible datum offsets (≤ 1.8 m against a ~5,557 m cell).
- **Computation CRS:** EPSG:3577 (GDA94 / Australian Albers, equal-area). Used for all distance calculations (infrastructure proximity) and area computations (exclusion fractions). Degrees are not a unit of length.
- **Enforcement:** Runtime `assert_crs` check at every function boundary that crosses a CRS. Mismatches raise immediately rather than producing silently wrong distances.

### 5b. Spatial Resolution Alignment

| Dataset | Native Resolution | Target (~5 km grid) | Pixels per Cell | Aggregation Method | Notes |
|---------|------------------|--------------------|----|-------|------|
| Global Wind Atlas (wind speed, power density) | 0.0025° (~250 m) | 0.05° cell | 20 × 20 = 400 (exact) | Statistic per cell — open question (see §9) | Grid anchored on GWA origin → clean blocks |
| GWA Capacity Factor (IEC2) | 0.0025° (~250 m) | 0.05° cell | 400 | Mean per cell | Presentation/explanation layer |
| SRTM GL3 (elevation, slope) | 0.000833° (~90 m) | 0.05° cell | ~60 × 60 = ~3,600 | Slope: statistic per cell (§9); Elevation: mean | GL3 preferred — less noise after aggregation |
| ABARES NLUM (land use) | 250 m (EPSG:3577) | 0.05° cell | ~20 × 20 = ~400 | Fraction of cell per class; dominant class | Requires reprojection (nearest-neighbour) |
| CAPAD Protected Areas | Vector (polygon) | 0.05° cell | N/A — rasterise | Binary: cell excluded if protected area intersects | Hard exclusion layer |
| ABS UCL (urban centres) | Vector (polygon) | 0.05° cell | N/A — rasterise | Binary exclusion (dense urban) | Cross-check with NLUM 5.4.x |
| GA Transmission Lines | Vector (line) | 0.05° cell | N/A — distance | Euclidean distance from centroid to nearest (EPSG:3577) | Filter ≥ 132 kV |
| GA Substations | Vector (point) | 0.05° cell | N/A — distance | Euclidean distance from centroid to nearest (EPSG:3577) | Voltage as secondary attribute |
| AEMO Demand | NEM Region (5 regions) | 0.05° cell | N/A — allocation | Population-weighted: cell demand = region × (cell pop / region pop) | Result labelled "estimated indicator" |

### 5c. Temporal Alignment

| Dataset | Temporal Nature | Time Range | Alignment Strategy |
|---------|----------------|------------|--------------------|
| Global Wind Atlas v4 | Long-term climatological mean (static) | 2008–2017 (10-year ERA5 downscaling) | Use as-is — represents the long-run wind climate |
| AEMO Operational Demand | Time series (half-hourly) | Jul 2025 – Jun 2026 (extendable to 3+ years) | Aggregate to annual mean MW per NEM region |
| GA Infrastructure (lines, substations) | Snapshot (current) | Downloaded Aug 2026 | Use as-is — represents the current grid |
| AEMO REZ Boundaries | Snapshot (planning) | 2026 ISP vintage | Use as-is — indicative planning overlay |
| CAPAD Protected Areas | Biennial snapshot | CAPAD 2024 (biennial cycle) | Use as-is — caveat: reserves gazetted after 2024 are missing |
| ABARES NLUM | Periodic snapshot | 2020–21 vintage | Use as-is — land use changes slowly at this scale |
| SRTM Elevation/Slope | Static (geophysical) | SRTM mission 2000 | Use as-is — terrain does not change at screening timescales |
| ABS Boundaries | Census-cycle snapshot | 2021 (Ed. 3) | Use as-is — administrative boundaries are stable |

**Temporal alignment is not a significant concern for this platform.** The scoring model combines long-run indicators (wind climate, annual demand means, current infrastructure, static terrain) — none of them are time-series predictions. The mismatch between the GWA period (2008–2017) and demand period (2025–2026) is acceptable because both represent stable, long-run characterisations of their respective phenomena. This must be stated wherever results combine the two criteria.

### 5d. Naming & Coding Inconsistencies

| Issue | Datasets Affected | Example | Resolution |
|-------|-------------------|---------|------------|
| State naming (abbreviation vs full name vs code) | ABS, CAPAD, GA, AEMO | "NSW" (CAPAD/GA) vs "New South Wales" (ABS) vs "1" (ASGS code) | Controlled lookup table: ASGS `state_code_2021` is the canonical join key |
| NEM region vs state | Demand + Infrastructure + Boundaries | "NSW1" (AEMO) vs "NSW" (GA) vs "1" (ABS) | Mapping table: NSW1 = NSW + ACT; maintain in code as a constant |
| Reserve name format | CAPAD | "Kosciuszko" (no type suffix) vs "Kosciuszko National Park" (common usage) | Document that CAPAD `NAME` field omits the reserve type; join with `TYPE` field |
| Area units | CAPAD vs ABS | CAPAD `GIS_AREA` in hectares; ABS `area_albers_sqkm` in km² | Always convert to km² at ingestion; assert units at boundaries |
| Date formats | CAPAD vs AEMO | CAPAD `GAZ_DATE` as epoch milliseconds; AEMO `INTERVAL_DATETIME` as ISO string | Normalise all timestamps to ISO 8601 UTC at ingestion |
| Voltage naming | GA Power Lines vs GA Substations | `capacity_kv` (lines) vs `voltage_kv` (substations) — same concept, different names | Standardise to `voltage_kv` in the internal schema |

### 5e. Coverage Gaps

| Gap | Affected Criterion | Impact | Mitigation |
|-----|-------------------|--------|------------|
| NEM demand does not cover WA or NT | Demand | Cannot produce demand indicator for WA or NT cells | Document as platform limitation; V1 covers NEM states only (NSW, QLD, SA, TAS, VIC). WA (WEM) data exists separately — future extension |
| AEMO KCI has no coordinates | Infrastructure | Cannot spatially join proposed connection projects | Use GA substations/lines for spatial scoring; KCI retained as planning-context metadata only |
| CAPAD is biennial (2024 vintage) | Geographic | Recently gazetted reserves (2025–2026) may be missing | Caveat in results; re-download when CAPAD 2026 is published |
| GWA terrain layers (RIX, elevation) HTTP 403 | Wind/Geographic | Cannot use Atlas's own terrain data per-country | Resolved: terrain sourced from SRTM (Task 4) — same SRTM lineage as GA's DEM products |
| GA services refuse scripted access for DEM | Geographic | Cannot use GA's own DEM service | Resolved: SRTM GL1/GL3 via OpenTopography S3 — same lineage, scriptable |
| Population data not yet downloaded | Demand | Cannot compute cell-level demand allocation without ABS population grid | Sprint 1 must acquire ABS SA2-level population counts (Census 2021) or gridded ERP |
| Road network not sampled | Geographic | Cannot compute distance-to-road penalty | Deferred: registered (OSM Australia), secondary priority per Task 4. Implement if time allows in Sprint 1 |
| Offshore wind excluded | Wind | GWA carries valid offshore wind values but no offshore infrastructure data | Hard exclusion via land mask. Offshore is out of scope for V1 (onshore wind only) |

### 5f. Full Integration Issues Register

*Master list — all issues from Tasks 1–4 consolidated with new cross-domain issues.*

| # | Issue | Source | Severity | Resolution Strategy | Owner | Status |
|---|-------|--------|----------|--------------------:|-------|--------|
| 1 | Ocean pixels carry real wind values — unmasked grid ranks offshore first | Task 1 | High | Apply ABS ASGS Australia outline as land mask before any scoring | Geographic/Sprint 1 | Resolution identified |
| 2 | 250 m → 5 km aggregation discards ridge signal; statistic choice is consequential | Task 1 | High | Configurable parameter (mean/max/p90); document choice in scenario config | Task 5 / Sprint 1 | Open — team decision needed |
| 3 | No spatial coordinates in demand data — 5 regions for all of NEM | Task 2 | High | Population-weighted allocation to grid cells via ABS population data | Sprint 1 | Strategy defined |
| 4 | AEMO KCI workbook has no coordinates | Task 3 | High | Do not use for spatial scoring; retain as planning-context metadata | Task 3 | Documented |
| 5 | AEMO connection data is not spare capacity | Task 3 | High | Use GA substations/lines for proximity only; never claim connection feasibility | Task 3 | Documented |
| 6 | Land mask selection (NE 1:50m vs ABS outline) | Task 4 | High | Use ABS ASGS outline — better fidelity at high-wind coastal cells | Geographic/Sprint 1 | Resolved |
| 7 | Mixed CRS across datasets (4326, 7844, 4283, 3577) | Tasks 1–4 | High | EPSG:4326 storage / EPSG:3577 computation; declare + transform explicitly | Sprint 1 | Strategy defined |
| 8 | NEM coverage gap — WA and NT excluded | Task 2 | Med | Document as V1 limitation; NEM states only | Task 2 | Documented |
| 9 | GWA terrain layers (RIX, elevation) return HTTP 403 | Task 1 | Med | Terrain sourced from SRTM GL3 instead (Task 4 delivered this) | Task 4 | Resolved |
| 10 | GWA access terms prohibit bulk API download | Task 1 | Med | NSW-scale windowed reads within terms; contact DTU for full-national runs | Sprint 1 | Flagged |
| 11 | No embedded units/version in GWA files | Task 1 | Med | Assert units in code from DATA_PROVENANCE; never infer from filename | Sprint 1 | Partly resolved |
| 12 | Pixels square in degrees, not metres — aspect ratio varies 27% | Task 1 | Med | Make assumption explicit; use EPSG:3577 for area/distance | Sprint 1 | Strategy defined |
| 13 | DEM noise: GL1 slope runs +1.31° hotter than GL3 at same footprint | Task 4 | Med | Use GL3 for screening-scale slope; GL1 for sensitivity only | Task 4 | Resolved |
| 14 | Slope aggregation statistic dominates outcome (11.6% vs 42.1% vs 85.7% excluded) | Task 4 | Med | Configurable parameter; evidence table in slope_derivation.md | Task 5 / Sprint 1 | Open — team decision needed |
| 15 | Datum landscape (GDA94 vs GDA2020 vs WGS84, ≤ 1.8 m offset) | Task 4 | Med | Negligible at 5 km; declare and transform explicitly per Constitution | Sprint 1 | Strategy defined |
| 16 | ABS service default SR is EPSG:3857 (Web Mercator) | Task 4 | Med | Always pass outSR explicitly in queries | Pipeline code | Resolved |
| 17 | CAPAD area units are hectares (not km²); dates are epoch milliseconds | Task 4 | Med | Convert at ingestion; assert units at boundaries | Pipeline code | Resolved |
| 18 | Inconsistent DEM nodata (GL3: 0, GL1: −32768) | Task 4 | Med | Pair DEM with land mask at coast; never trust nodata alone in coastal cells | Sprint 1 | Documented |
| 19 | NSW REZ source selection (AEMO national vs EnergyCo state) | Task 3 | Med | EnergyCo for NSW screening; AEMO for national/ISP comparison | Sprint 1 | Strategy defined |
| 20 | Temporal mismatch: GWA 2008–2017 vs AEMO demand 2025–2026 | Task 1 | Low | Acceptable for screening (both are long-run indicators); state wherever combined | Documentation | Documented |
| 21 | GWA height layers not monotonic (0.51% of pixels) | Task 1 | Low | Do not assume taller=faster in code; validate edge cases | Sprint 1 | Documented |
| 22 | Negative demand values in SA1 (distributed solar exceeds consumption) | Task 2 | Low | Include in annual mean as-is; document for interpretation | Task 2 | Documented |
| 23 | Operational vs Total demand distinction | Task 2 | Low | Operational demand is the correct metric (grid-served load); document clearly | Task 2 | Documented |
| 24 | Region naming consistency (NSW1 vs NSW) | Tasks 2–3 | Low | Lookup table: NEM region → state code → state name | Sprint 1 | Strategy defined |
| 25 | Data currency — infrastructure is a snapshot | Task 3 | Low | Document vintage; accept for screening purposes | Task 3 | Documented |
| 26 | State naming variants ("NSW" vs "New South Wales" vs "1") | Task 4 | Low | state_code_2021 is canonical join key; 5-row lookup for CAPAD STATE field | Sprint 1 | Strategy defined |
| 27 | Raster CRS split: NLUM is Albers (3577) while DEM/wind are geographic (4326) | Task 4 | Low | Warp NLUM to 4326 with nearest-neighbour (categorical); do once at ingestion | Sprint 1 | Strategy defined |
| 28 | Committed vectors carry ~50 m generalisation (maxAllowableOffset) | Task 4 | Low | Adequate for 5 km cells; do not reuse for sub-100 m work | Documented | Documented |
| 29 | NEM regions not authoritative (derived from ABS STE) | Task 4 | Low | File flagged derived-not-authoritative; NSW+ACT→NSW1 rule documented | Task 4 | Resolved |
| 30 | Population data needed for demand allocation — not yet acquired | New (Task 5) | Med | Sprint 1 must download ABS SA2 population (Census 2021 or ERP) | Sprint 1 | Open |
| 31 | Prototype uses PRICE_AND_DEMAND; this project uses Operational Demand | New (Task 5) | Med | Use Operational Demand (Task 2's recommendation) — it measures grid-served load | Sprint 1 | Resolved |
| 32 | GWA grid origin alignment (prototype off by half a pixel) | New (Task 5) | Low | Anchor grid on GWA origin (109.21125, -8.86125) — eliminates boundary ambiguity | Sprint 1 | Strategy defined |

---

## 6. Proposed Core Criteria (Version 1)

*Based on the data actually available, the four criteria for Version 1.*

### Criterion 1: Wind Resource Potential

| Aspect | Proposal |
|--------|----------|
| What it measures | Long-term wind energy extraction potential at hub height |
| Data source | Global Wind Atlas v4 (DTU), CC BY 4.0 |
| Variable(s) used | **Primary:** wind speed at 100 m (m/s) and power density at 100 m (W/m²). **Presentation:** capacity factor IEC2 (ratio) |
| Per-cell computation | Aggregate 400 native pixels (20×20 block) per cell using a configurable statistic (mean, max, or p90). Both wind speed and power density are aggregated independently |
| Units of the derived feature | Wind speed: m/s; Power density: W/m²; Capacity factor: ratio 0–1 |
| Known limitations | (1) Long-term mean only — no seasonal/diurnal breakdown. (2) Aggregation statistic choice materially affects rankings (Task 1 §8 issue 2: two validation wind farms rank differently under mean vs max). (3) Fixed at 100 m hub — modern turbines trend taller; carry 150 m as sensitivity layer. (4) Power density separates sites that share a mean speed but differ in distribution — both variables are needed |

**Why two variables (wind speed + power density)?** Wind speed alone is insufficient for screening. Power density relates to the cube of speed-distribution, so two cells with the same mean speed can differ materially in extractable energy. Carrying both costs one additional raster read and separates sites that a mean-speed-only ranking would tie.

**Aggregation statistic — open question for team (§9, Question 1):**
- **Mean:** Characterises the general wind climate of the cell; smooths over within-cell variability; known to bury ridge signals (White Rock drops from p93 native to p80 under mean).
- **Max:** Captures the best micro-site within the cell; inflated by single-pixel terrain artefacts; White Rock ranks p95 under max but Sapphire drops to p82.
- **P90:** Compromise between mean and max; less sensitive to single-pixel outliers while preserving the ridge signal.
- Evidence: `DATA/wind-resource/metadata/aggregation_sensitivity.md`

### Criterion 2: Electricity Demand Indicator

| Aspect | Proposal |
|--------|----------|
| What it measures | Relative electricity demand intensity at the grid-cell level — how much grid-served load exists nearby that new generation could serve |
| Data source | AEMO Operational Demand (Half-Hourly) from NEMWeb |
| Variable(s) used | Annual mean operational demand per NEM region (MW) |
| Per-cell computation | Population-weighted allocation: `cell_demand = region_annual_mean × (cell_population / region_total_population)` |
| Spatial allocation method | ABS Census 2021 population at SA2 level. Each cell's population is estimated by area-weighting the SA2 polygons it intersects. The cell's demand indicator is then proportional to its share of the total regional population |
| Units of the derived feature | Estimated MW (proxy indicator) — must be labelled "estimated demand indicator" in all outputs |
| Known limitations | (1) Proxy, not actual local consumption — industrial/commercial loads not well captured by population. (2) NEM regions only (no WA/NT). (3) Uniform within an SA2 — dense vs sparse parts of an SA2 get the same per-area allocation. (4) Labelling critical: must never be presented as "demand" without the "estimated/proxy" qualifier |

**Why population weighting?** Of the available proxies (population, substation proximity, flat allocation), population weighting is the most defensible for an initial implementation:
- Electricity consumption correlates with population density at regional scales
- ABS provides authoritative population data at fine spatial resolution (SA2, mesh block)
- The resulting indicator is interpretable: higher-population cells have higher estimated demand
- Alternative (substation proximity) conflates infrastructure proximity with demand — those are separate criteria in this platform

**Mechanism:**
1. Compute annual mean operational demand per NEM region from the half-hourly data
2. Obtain ABS SA2 population counts (Census 2021 Estimated Resident Population)
3. For each grid cell: identify which NEM region it belongs to (from derived NEM region polygons)
4. For each grid cell: estimate cell population as `sum(SA2_pop × fraction_of_SA2_in_cell)` for all SA2s intersecting the cell
5. Compute cell demand indicator: `region_mean_demand × (cell_population / sum_of_all_cell_populations_in_region)`

### Criterion 3: Grid & Infrastructure Accessibility

| Aspect | Proposal |
|--------|----------|
| What it measures | Proximity to existing transmission network infrastructure — a practical constraint on connection cost and feasibility |
| Data source(s) | GA Power Lines 2026 (national), GA Substations 2026 (national) |
| Variable(s) used | **Primary:** distance to nearest transmission line ≥ 132 kV (km). **Secondary:** distance to nearest substation (km), with voltage as an attribute |
| Per-cell computation | (1) Reproject cell centroids and infrastructure geometries to EPSG:3577. (2) Compute Euclidean distance from each cell centroid to the nearest line segment ≥ 132 kV. (3) Compute Euclidean distance from each cell centroid to the nearest substation point |
| Distance metric (Euclidean / network?) | Euclidean (straight-line) in EPSG:3577. Network distance requires road/terrain routing data not available at sufficient quality for V1 |
| Units of the derived feature | Kilometres (km) |
| Known limitations | (1) Euclidean, not network distance — actual connection routes follow terrain and roads. (2) Proximity ≠ spare capacity — a nearby substation may be fully committed. (3) GA data is screening-level, not engineering-level — use for relative ranking, not absolute feasibility. (4) Voltage filter at 132 kV excludes distribution lines; this is appropriate for utility-scale wind |

**Why Euclidean distance?** Network distance would require high-quality road/terrain routing data and substantially more computation. For a screening tool that ranks cells *relative to each other*, Euclidean distance preserves the ordering: cells closer to infrastructure rank higher, and the relative ordering is largely maintained whether measured as straight-line or network distance. The Constitution requires stating this simplification wherever results are presented.

### Criterion 4: Geographic & Environmental Suitability

| Aspect | Proposal |
|--------|----------|
| What it measures | Whether a cell is physically and legally suitable for wind energy development |
| Data source(s) | CAPAD 2024 (protected areas), ABARES NLUM 250m (land use), ABS ASGS outline (land mask), ABS UCL (urban centres), SRTM GL3 + derived slope |
| Hard exclusions (list) | (1) Ocean — cells outside the ABS Australia outline. (2) Protected areas — any CAPAD terrestrial polygon intersection. (3) Water bodies — NLUM class 6 (lakes, reservoirs, rivers). (4) Dense urban — NLUM class 5.4.x (residential) cross-checked with ABS UCL polygons |
| Suitability penalties (list) | (1) Slope — steeper terrain increases construction cost (continuous penalty, not binary exclusion per PKB). (2) TRI (terrain ruggedness) — complements slope for complex terrain. (3) Agricultural land use classes — grazing land is where wind farms actually get built (low penalty); cropping land (moderate penalty); forestry (higher penalty) |
| Per-cell computation | (1) Apply hard exclusions: mark cells as excluded (binary). (2) For remaining cells: compute slope statistic per cell from GL3-derived slope raster. (3) Compute land-use composition (fraction per class). (4) Combine into a continuous suitability score (0–1) where 1 = fully suitable, 0 = excluded |
| Units of the derived feature | Composite score: 0 (excluded) to 1 (fully suitable). Individual layers retain native units for explanation (slope in degrees, protected area fraction as %) |
| Known limitations | (1) CAPAD is biennial — recent gazettal may be missing. (2) Slope statistic choice is consequential (see §9). (3) Land-use penalties are judgement-based — user-adjustable in the scoring model. (4) No mining-lease or native-title data in V1 — these would be additional hard exclusions in a production system |

### Criteria Summary Table

| # | Criterion | Primary Data Source | Feature Type | Hard Exclusion Component? |
|---|-----------|--------------------:|:------------:|:-------------------------:|
| 1 | Wind Resource | GWA v4 (wind speed + power density @ 100m) | Continuous | No |
| 2 | Demand Indicator | AEMO Operational Demand + ABS Population | Continuous (proxy) | No |
| 3 | Infrastructure Access | GA Power Lines + Substations 2026 | Distance-based (km) | No (possible threshold in future) |
| 4 | Geographic Suitability | CAPAD + NLUM + ABS outline + SRTM slope | Composite (0–1) | Yes (ocean, protected, water, urban) |

---

## 7. Site Definition Recommendation

*The Product Knowledge Base proposes a ~5 km grid cell. Evaluated independently against the actual data.*

### Options Considered

| Option | Description | Pros | Cons |
|--------|-------------|------|------|
| **A — Geographic grid (~5 km)** | Divide Australia into uniform 0.05° cells anchored on the GWA raster origin | Consistent; all data maps to it; clean 20:1 ratio with GWA pixels; resolution-agnostic scoring; simple to implement and explain | Arbitrary boundaries unrelated to land parcels; cells straddle features (rivers, roads); cell width varies with latitude (4.82 km at 30°S to 4.00 km at 44°S) |
| **B — Existing towns/locations** | Analyse predefined settlement locations | Fewer points; human-interpretable place names | Misses remote high-resource areas entirely; biased toward population; not a screening tool |
| **C — Predefined regions (SA2, LGA)** | Use ABS statistical areas | Official boundaries; links directly to census population data; variable number of features | Wildly irregular sizes — urban SA2s are < 1 km², rural SA2s are > 10,000 km²; cannot differentiate wind resource within a single large rural SA2 |
| **D — Hexagonal grid (H3)** | Hexagonal cells at resolution 5 (~5 km equivalent) | Equal-area globally; better spatial adjacency (6 neighbours vs 4/8); no polar distortion | More complex tooling (requires h3-py); less familiar to stakeholders; no data-driven advantage over geographic grid at screening scale; cannot align cleanly to the GWA raster lattice |

### Recommendation

**Option A — Geographic grid at 0.05° cell size, anchored on the GWA raster origin.**

Justification:

1. **Data alignment.** The GWA raster has a 0.0025° pixel at origin (109.21125, -8.86125). A 0.05° cell is exactly 20 native pixels per side — no fractional overlaps, no interpolation, no boundary-pixel ambiguity. This is the strongest data-driven argument: the wind resource raster is the platform's largest and finest dataset, and clean alignment to it eliminates an entire class of aggregation artefact.

2. **Resolution is appropriate.** Every raster dataset (GWA ~250 m, SRTM ~90 m, NLUM ~250 m) is finer than the cell. The grid always aggregates, never interpolates — the correct direction for a screening tool that summarises, not fabricates.

3. **Feasibility.** The integration analysis script (`pipeline/integration/analyse.py`) computes:
   - Australia: ~549,310 total cells → ~278,000 land cells
   - NSW: ~47,311 total cells → ~30,500 land cells
   - Study window: ~1,521 total cells → ~1,445 land cells
   
   All scopes are computationally feasible on standard hardware (16 GB RAM, SSD).

4. **~5 km is validated by the data.** At 30°S (the study window), cell dimensions are 4.80 km E–W × 5.56 km N–S. This matches the PKB's "approximately 5 km" proposal. The variation with latitude (4.0–5.5 km E–W from Tasmania to Queensland) is acceptable for a screening tool — it must be stated wherever results are presented but does not affect relative rankings.

5. **Simplicity.** A regular geographic grid is the simplest to implement, explain, visualise (direct Leaflet/web-map tile alignment), and extend. H3 hexagons would require additional tooling for marginal benefit at this scale.

**Grid specification:**

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Cell size | 0.05° | 20 × GWA native pixel; ~5 km at mid-latitudes |
| Origin (longitude) | 109.21125° E | GWA raster western edge — ensures pixel alignment |
| Origin (latitude) | -8.86125° S | GWA raster northern edge — ensures pixel alignment |
| Storage CRS | EPSG:4326 | Native CRS of largest dataset |
| Computation CRS | EPSG:3577 | Equal-area for distance and area calculations |

**Grid anchor justification vs the existing prototype:**
The existing prototype anchors at (112.9, -43.7), which is offset from the GWA lattice by a fractional pixel (specifically, 0.50 of a pixel in the relevant dimension). This puts 5% of cell boundaries exactly on a native pixel edge — a tie-breaking artefact. Shifting to the GWA origin costs ~1.2 km of boundary movement and eliminates the issue entirely.

### Computational Feasibility

| Scope | Grid Cells (total) | Est. Land Cells | Cell Dimensions (at mid-lat) | Feasible on Standard Hardware? | Notes |
|-------|---------------------|-----------------|------|------|-------|
| All of Australia | ~549,000 | ~278,000 | 4.96 × 5.56 km | Yes (profile first) | Largest raster reads: ~50 MB per GWA layer via /vsicurl/ |
| NSW only | ~47,000 | ~30,500 | 4.68 × 5.56 km | Yes — comfortably | Recommended Sprint 1 scope |
| New England REZ | ~1,500 | ~1,445 | 4.80 × 5.56 km | Trivial | Already demonstrated in Tasks 1–4 |

---

## 8. Recommended Scope for Sprint 1

*Based on the data, feasibility, and integration issues above:*

### Scope Decision

- [x] **Start with NSW** — all four criteria, end-to-end pipeline
- [ ] Full national coverage (defer to Sprint 2 after profiling)
- [ ] Start with fewer criteria (all four are feasible and data is available)

### Justification for NSW-First

1. **Data already sampled:** The New England REZ study window used in Tasks 1–4 is in NSW. All data layers have been proven to work in this region.
2. **AEMO demand covers NSW1:** The NEM region NSW1 is the highest-demand region (mean 7,566 MW) — a meaningful demand signal.
3. **Infrastructure coverage is strong:** GA data shows 957 transmission lines and 586 substations in NSW.
4. **Cell count is manageable:** ~30,500 land cells — well within hardware constraints, fast iteration.
5. **REZ boundaries available:** EnergyCo provides official NSW REZ boundary files for context/validation.
6. **Validation data present:** Task 1 validated against White Rock and Sapphire wind farms (both in NSW).
7. **National expansion is architectural, not structural:** The grid, CRS strategy, and pipeline design work at any scale. NSW-first is a scoping decision, not a design limitation.

### Integration Issues for Sprint 1 (must resolve)

| # | Issue | Resolution Required |
|---|-------|---------------------|
| 1 | Land mask — apply ABS outline before scoring | Implement rasterisation of ABS outline to grid |
| 7 | CRS alignment — enforce 4326/3577 split | Implement assert_crs checks; reproject infrastructure vectors |
| 3 | Demand spatial allocation — acquire population data | Download ABS SA2 population; implement weighted allocation |
| 2 | Wind aggregation statistic — team decision | Implement as configurable parameter; document default choice |
| 27 | NLUM reprojection (3577 → 4326) | Implement nearest-neighbour warp at ingestion |
| 30 | Population data acquisition | Download ABS Census 2021 SA2-level ERP for NSW |

### Integration Issues Deferred (Sprint 2+)

| # | Issue | Reason for Deferral |
|---|-------|---------------------|
| 8 | WA/NT coverage gap | V1 is NEM-only by design |
| 10 | GWA bulk access terms for national runs | NSW within terms; national needs DTU files or permission |
| 12 | Pixel aspect ratio documentation | Low severity; document in technical report |
| 21 | Non-monotonic height layers | Edge case; document, don't fix |

### Minimum Data for End-to-End Pipeline Demo

| Layer | Source | Already Available? | Sprint 1 Action |
|-------|--------|-------------------|-----------------|
| Wind speed 100m (NSW) | GWA v4 via /vsicurl/ | Study window clip exists | Extend windowed read to NSW bbox |
| Power density 100m (NSW) | GWA v4 via /vsicurl/ | Study window clip exists | Extend windowed read to NSW bbox |
| Annual mean demand (NSW1) | AEMO | 1 year downloaded | Use existing; extend to 3 years |
| ABS SA2 population (NSW) | ABS Census 2021 | Not yet downloaded | Download |
| GA Power Lines (NSW) | GA | Downloaded | Use existing |
| GA Substations (NSW) | GA | Downloaded | Use existing |
| Land mask (national) | ABS ASGS outline | Downloaded | Rasterise to grid |
| CAPAD protected areas (NSW) | DCCEEW | Downloaded | Rasterise to grid |
| NLUM land use (NSW) | ABARES | Study window clip | Extend windowed read to NSW bbox |
| SRTM GL3 slope (NSW) | OpenTopography | Study window clip | Extend windowed read + derive slope |
| NEM region polygons | Derived (ABS STE) | Available | Use existing |

---

## 9. Open Questions for Team Discussion

| # | Question | Options | Recommendation | Decision |
|---|----------|---------|----------------|----------|
| 1 | Wind aggregation statistic for 250m → 5km cells? | (a) Mean — stable, characterises general climate, buries ridges. (b) Max — captures best micro-site, noisy. (c) P90 — compromise. (d) Report multiple, let user choose. | Report mean + p90 as features; use mean as the default scoring input; present max as a "best micro-site" indicator in explanation. Evidence: `aggregation_sensitivity.md` | _[Team decision]_ |
| 2 | Primary hub height for scoring? | (a) 100 m — internally consistent with CF layers. (b) 150 m — closer to modern turbine heights. | Use 100 m for V1 (CF consistency); carry 150 m as sensitivity layer. Cross-reference AEMO generator register for actual Australian hub heights before finalising. | _[Team decision]_ |
| 3 | Slope aggregation statistic per cell? | (a) Mean slope — general terrain difficulty. (b) P90 — flags cells with significant steep sections. (c) Max — most conservative (flags any steep pixel). | Use mean slope as the penalty input; report p90 in explanation for context. Evidence: slope exclusion varies 11.6% (mean) to 42.1% (p90) to 85.7% (max) at 10° threshold. | _[Team decision]_ |
| 4 | Population data source for demand allocation? | (a) ABS Census 2021 ERP at SA2 level (~2,500 areas). (b) ABS Census 2021 at mesh block (~360,000 areas). (c) ABS gridded population estimates. | SA2 level — sufficient resolution for a ~5 km grid (SA2s are comparable scale), simpler to implement, and population counts are directly published. Mesh block available as future refinement. | _[Team decision]_ |
| 5 | Should the demand criterion use operational demand or total demand? | (a) Operational demand (AEMO NEMWeb) — grid-served load. (b) PRICE_AND_DEMAND (prototype's source) — includes price. | Operational demand (Task 2's recommendation). It measures the load that new generation must serve, which is the relevant metric for siting. Total demand includes behind-the-meter generation that new wind cannot displace. | _[Team decision]_ |
| 6 | Hard exclusion threshold for protected areas? | (a) Binary — any overlap with CAPAD polygon excludes the cell. (b) Fractional — exclude only if > X% of cell is protected. | Binary exclusion (any intersection). A 5 km cell partially overlapping a national park should not be recommended — the non-protected portion may be too small to develop, and the reputational/legal risk is high. | _[Team decision]_ |
| 7 | Should infrastructure distance have a hard exclusion threshold? | (a) No — continuous distance feature only (PKB says "investigate as penalty, not exclusion"). (b) Yes — exclude cells > 100 km from any transmission line. | No hard exclusion for V1 (per PKB guidance). Distance is a continuous penalty in the suitability score. Extremely remote cells will rank low naturally through the infrastructure criterion. | _[Team decision]_ |

---

## 10. Acceptance Criteria

- [x] Consolidated data inventory table is complete (all datasets from Tasks 1–4) — §4, 24 datasets
- [x] Cross-dataset integration issues are documented in a single register — §5f, 32 issues
- [x] CRS alignment recommendation is made — §5a, EPSG:4326 storage / EPSG:3577 computation
- [x] Spatial resolution alignment strategy is documented for each dataset → 5 km cell — §5b
- [x] Temporal alignment strategy is documented — §5c
- [x] Four core criteria are proposed with data source, computation method, and limitations — §6
- [x] Site definition options are evaluated and a recommendation is made — §7
- [x] Computational feasibility is estimated (cell counts for national vs state scope) — §7
- [x] Sprint 1 scope recommendation is provided — §8
- [x] Open questions for team discussion are listed — §9

---

## 11. References

- Product Knowledge Base: see `Opt-Mining - Product Knowledge Base.md`
- AI Development Constitution: see `Opt-Mining - AI Development Constitution.md`
- Task 1 findings: see `01-Wind-Resource-Data-Investigation.md`
- Task 2 findings: see `02-Electricity-Demand-Data-Investigation.md`
- Task 3 findings: see `03-Electricity-Infrastructure-Data-Investigation.md`
- Task 4 findings: see `04-Geographic-Environmental-Data-Investigation.md`
- Integration analysis script: see `pipeline/integration/analyse.py`
- Integration analysis report: see `DATA/integration/integration_analysis.md`

---

## 12. Supporting Artefacts

| Path | Contents |
|------|----------|
| `pipeline/integration/__init__.py` | Subpackage docstring |
| `pipeline/integration/analyse.py` | Grid geometry, CRS alignment, resolution mapping, feasibility (programmatic evidence) |
| `DATA/integration/integration_analysis.md` | Generated report with tables backing §5–§7 |

Reproduce:

```bash
.venv/bin/python -m pipeline.integration.analyse --verbose
```

Every quantitative claim in this document (cell counts, datum offsets, pixel ratios, cell dimensions) is computed by `pipeline/integration/analyse.py` and recorded in the generated report. None was typed by hand.
