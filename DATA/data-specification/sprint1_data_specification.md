# Sprint 1 Data Specification

**Version:** 1.0
**Date:** 2026-08-27
**Status:** FROZEN — Sprint 1 baseline
**Blocks:** S1-02, S1-03, S1-04, S1-05, S1-06

---

## 1. Purpose & Governance

This document is the **single source of truth** for Sprint 1 data inputs. It commits to a defined set of datasets, parameters, and processing decisions that the MVP pipeline will implement.

No dataset may enter the pipeline without being listed here. No parameter may be changed without following the change-control process (§8).

Sprint 0 was for exploration. Sprint 1 is for controlled implementation. This specification draws the line between the two.

**Constitution alignment:** This document satisfies the requirement to "record the provenance, licence and vintage of every dataset that enters the platform, and carry attribution through to the interface and the report" (Opt-Mining AI Development Constitution, Architectural Rules).

---

## 2. Team Decisions (Frozen Parameters)

These decisions were made by team consensus on 2026-08-27. Each materially affects scoring outcomes and must be recorded in the scenario configuration wherever results are presented.

| # | Question | Decision | Rationale | Evidence |
|---|----------|----------|-----------|----------|
| Q1 | Wind aggregation statistic (250 m → 5 km cells) | **Mean** | Single stable statistic characterising the general wind climate of each cell. Buries ridge signals but provides consistent, reproducible rankings. | Task 1 §8 issue 2; `DATA/wind-resource/metadata/aggregation_sensitivity.md` |
| Q2 | Primary hub height for scoring | **100 m** | Internal consistency: wind speed, power density, and capacity factor all describe the same 100 m hub. 150 m carried as sensitivity layer only. | Task 1 §9; Task 5 §6 Criterion 1 |
| Q3 | Slope aggregation statistic per cell | **Mean for scoring; P90 in explanation** | Mean slope characterises general terrain difficulty (11.6% of NSW excluded at 10° threshold). P90 flags cells with significant steep sections for user inspection. | Task 4 `metadata/slope_derivation.md`; Task 5 §9 Q3 |
| Q4 | Population data source for demand allocation | **ABS Census 2021 ERP at SA2 level** | Sufficient resolution for a ~5 km grid (~2,500 areas nationally). Simpler to implement than mesh block. Population counts directly published. | Task 5 §6 Criterion 2; §9 Q4 |
| Q5 | Demand metric | **Operational demand** (AEMO NEMWeb) | Measures grid-served load — the electricity that new generation must serve. Total demand includes behind-the-meter generation that new wind cannot displace. | Task 2 §4; Task 5 §9 Q5 |
| Q6 | Protected area exclusion threshold | **Binary** (any CAPAD intersection excludes the cell) | A 5 km cell partially overlapping a national park should not be recommended — the non-protected portion may be too small to develop, and the legal/reputational risk is high. | Task 5 §9 Q6 |
| Q7 | Infrastructure distance hard exclusion | **No hard exclusion** — continuous distance penalty only | Extremely remote cells rank low naturally through scoring weights. The Product Knowledge Base specifies "investigate as penalty, not exclusion." | Task 5 §9 Q7; PKB |

---

## 3. Grid Definition

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Cell size | 0.05° (~5 km at mid-latitudes) | 20 × GWA native pixel; clean aggregation with no fractional overlaps |
| Origin (longitude) | 109.21125° E | GWA raster western edge — ensures pixel alignment |
| Origin (latitude) | -8.86125° S | GWA raster northern edge — ensures pixel alignment |
| Pixels per cell | 20 × 20 = 400 (exact) | Integer ratio eliminates boundary-pixel ambiguity |
| Cell height (constant) | 5.56 km | 0.05° latitude everywhere |
| Cell width (varies) | 4.0 km (44°S) to 5.5 km (10°S); 4.80 km at study window (30°S) | Degrees are not a unit of length; variation must be stated |
| Storage CRS | EPSG:4326 (WGS 84) | Native CRS of largest dataset (GWA); avoids 600 MB reprojections |
| Computation CRS | EPSG:3577 (GDA94 / Australian Albers, equal-area) | All distance and area calculations — degrees are not length |
| Sprint 1 scope | NSW first (~30,500 land cells) | Data proven, highest demand region, manageable iteration speed |
| National scope (deferred) | ~278,000 land cells | Architecturally supported; profiling required before Sprint 2 |

**Grid anchor justification:** The GWA grid origin is 109.21125° E, -8.86125° S with a 0.0025° step. Anchoring the analysis grid on this origin makes every cell a clean 20 × 20 block of native pixels. The existing prototype's offset (112.9, -43.7) puts 5% of cell boundaries on pixel edges — eliminated by this anchor choice.

---

## 4. Selected Datasets

### 4.1 Wind Resource

All wind resource layers are from the **Global Wind Atlas v4** (GWA 4.0), published by DTU Wind Energy in partnership with the World Bank Group. They are long-term climatological means — single static values per pixel, not time series.

**Common properties (all 4 datasets):**

| Property | Value |
|----------|-------|
| Publisher | Technical University of Denmark (DTU Wind Energy) |
| Application URL | https://globalwindatlas.info/ |
| Dataset record / DOI | https://data.dtu.dk/articles/dataset/Global_Wind_Atlas_4/28955267 · DOI [10.11583/DTU.28955267](https://doi.org/10.11583/DTU.28955267) |
| CDN URL pattern | `https://gwa.cdn.nazkamapps.com/country_tifs_v4/AUS_<variable>[_<height>m].tif` |
| Access method | Windowed read over GDAL `/vsicurl/` — full rasters are never downloaded |
| Format | GeoTIFF, single band, float32, internally tiled (512×512), zstd compressed, 6 overview levels |
| CRS | EPSG:4326 (WGS 84) — explicitly declared in the file |
| Native pixel size | 0.0025° × 0.0025° (~250 m nominal; ~241 m E–W at 30°S, ~278 m N–S) |
| Grid size (Australia) | 21,601 × 18,374 pixels |
| Temporal coverage | ERA5 reanalysis 2008–2017 (10-year mean); GWA v4 released June 2025 |
| NoData | NaN (outside Australian territory including marine areas) |
| Embedded metadata | None — only `AREA_OR_POINT=Area`; units must be asserted from provenance, not read from file |
| Licence | CC BY 4.0 |
| Required citation | Floors, R.R.; Davis, N.; Olsen, B.T.; Badger, J.; Hansen, B.O. (2025). *Global Wind Atlas 4.* Technical University of Denmark. Dataset. https://doi.org/10.11583/DTU.28955267.v1 |
| Authentication | None required (no registration, no API key) |
| Access-terms compliance | Per-country windowed reads (~2 MB each) are within terms. Bulk download of all countries prohibited — contact DTU for national multi-layer runs. |

**Aggregation method (all wind layers):** Mean of 400 native pixels (20 × 20 block) per 0.05° analysis cell.

---

#### 4.1.1 GWA v4 Wind Speed @ 100 m

| Field | Value |
|-------|-------|
| **Dataset name** | Global Wind Atlas v4 — Mean Wind Speed at 100 m |
| **File in repository** | `DATA/wind-resource/gwa_v4_wind-speed_100m_new-england-rez.tif` (study window clip) |
| **Remote source file** | `AUS_wind-speed_100m.tif` (618 MB, full Australia) |
| **Variable(s)** | Mean wind speed at 100 m hub height (single band, float32) |
| **Units** | m/s |
| **Value range (study window)** | 0.968 – 10.964 m/s; median 5.344 m/s; mean 5.574 m/s |
| **Role in model** | **Primary scoring input** — Criterion 1 (Wind Resource Potential) |
| **Pipeline step** | `pipeline/wind/download.py` → `pipeline/wind/inspect.py` → Sprint 1 feature builder (cell-level mean) |
| **Aggregation** | Mean of 400 native pixels per cell (frozen decision Q1) |
| **Known limitations** | (1) Ocean pixels carry real values — land mask mandatory before scoring. (2) No seasonal/diurnal breakdown. (3) 10-year mean only — no interannual variability. (4) No embedded units in file. (5) Pixel aspect ratio varies 27% across the continent. |

---

#### 4.1.2 GWA v4 Power Density @ 100 m

| Field | Value |
|-------|-------|
| **Dataset name** | Global Wind Atlas v4 — Mean Power Density at 100 m |
| **File in repository** | `DATA/wind-resource/gwa_v4_power-density_100m_new-england-rez.tif` (study window clip) |
| **Remote source file** | `AUS_power-density_100m.tif` (649 MB, full Australia) |
| **Variable(s)** | Mean wind power density at 100 m (single band, float32) |
| **Units** | W/m² |
| **Value range (study window)** | 1.645 – 1,373.8 W/m²; median 181.3 W/m²; mean 222.6 W/m² |
| **Role in model** | **Primary scoring input** — Criterion 1 (Wind Resource Potential). Separates sites with the same mean speed but different wind-speed distributions (relates to the cube of speed). |
| **Pipeline step** | `pipeline/wind/download.py` → `pipeline/wind/inspect.py` → Sprint 1 feature builder (cell-level mean) |
| **Aggregation** | Mean of 400 native pixels per cell (frozen decision Q1) |
| **Known limitations** | Same as §4.1.1. Additionally: power density is more sensitive to distribution shape than mean speed — cells with identical mean speed can differ substantially in power density. |

---

#### 4.1.3 GWA v4 Capacity Factor IEC2

| Field | Value |
|-------|-------|
| **Dataset name** | Global Wind Atlas v4 — Capacity Factor, IEC Class 2 Turbine |
| **File in repository** | `DATA/wind-resource/gwa_v4_capacity-factor_IEC2_new-england-rez.tif` (study window clip) |
| **Remote source file** | `AUS_capacity-factor_IEC2.tif` (652 MB, full Australia) |
| **Variable(s)** | Modelled capacity factor for IEC class 2 turbine (100 m hub, 136 m rotor diameter) (single band, float32) |
| **Units** | Ratio, 0–1 |
| **Value range (study window)** | 0.001 – 0.618; median 0.213; mean 0.234 |
| **Role in model** | **Presentation / explanation layer only — NOT a scoring input.** Provides the most directly interpretable resource indicator for planners. Converts to indicative AEP as `P_rated × CF × 8760 h` (Constitution: this is indicative only, never bankable). |
| **Pipeline step** | `pipeline/wind/download.py` → `pipeline/wind/inspect.py` → Sprint 1 explanation/map layer |
| **Aggregation** | Mean of 400 native pixels per cell |
| **Known limitations** | (1) Modelled for one specific turbine (IEC2: 100 m hub, 136 m rotor) — not a yield estimate for any real project. (2) Fixed at 100 m hub height — does not reflect taller modern turbines. (3) Same ocean/land mask requirements as other wind layers. |

---

#### 4.1.4 GWA v4 Wind Speed @ 150 m

| Field | Value |
|-------|-------|
| **Dataset name** | Global Wind Atlas v4 — Mean Wind Speed at 150 m |
| **File in repository** | `DATA/wind-resource/gwa_v4_wind-speed_150m_new-england-rez.tif` (study window clip) |
| **Remote source file** | `AUS_wind-speed_150m.tif` (610 MB, full Australia) |
| **Variable(s)** | Mean wind speed at 150 m hub height (single band, float32) |
| **Units** | m/s |
| **Value range (study window)** | 1.900 – 10.624 m/s; median 6.035 m/s; mean 6.213 m/s |
| **Role in model** | **Sensitivity layer only — NOT a scoring input.** Carried to assess the impact of hub height choice. Mean shear from 100 m to 150 m is +0.64 m/s in the study window. |
| **Pipeline step** | `pipeline/wind/download.py` → Sprint 1 sensitivity analysis |
| **Aggregation** | Mean of 400 native pixels per cell |
| **Known limitations** | Same as §4.1.1. Additionally: capacity factor layers do not exist at 150 m — this layer cannot be cross-referenced with CF for consistency. Useful for comparison only. |

### 4.2 Electricity Demand

The demand criterion uses population-weighted allocation to distribute regional demand figures to grid cells. Two datasets are required: the demand time series (AEMO) and the spatial population distribution (ABS).

**Allocation formula:** `cell_demand = region_annual_mean_MW × (cell_population / region_total_population)`

The result must always be labelled "estimated demand indicator" — it is a proxy, not actual local consumption.

---

#### 4.2.1 AEMO Operational Demand (Half-Hourly)

| Field | Value |
|-------|-------|
| **Dataset name** | AEMO NEM Operational Demand — Actual, Half-Hourly |
| **Publisher** | Australian Energy Market Operator (AEMO) |
| **Source URL** | https://nemweb.com.au/Reports/Archive/Operational_Demand/ACTUAL_DAILY/ |
| **Navigation** | Archive → monthly ZIPs (`PUBLIC_ACTUAL_OPERATIONAL_DEMAND_DAILY_YYYYMM01.zip`) → daily ZIPs → CSV |
| **File in repository** | `DATA/electricity-demand/raw/PUBLIC_ACTUAL_OPERATIONAL_DEMAND_DAILY_*.zip` (raw); `DATA/electricity-demand/demand_annual_summary.csv` (aggregated) |
| **Variable(s)** | `OPERATIONAL_DEMAND` — electricity demand met by scheduled, semi-scheduled, and significant non-scheduled generation (excludes rooftop PV / behind-the-meter) |
| **Units** | MW (megawatts) |
| **CRS** | N/A — tabular, region-level (no geometry) |
| **Spatial resolution** | NEM Region (5 regions: NSW1, QLD1, SA1, TAS1, VIC1) |
| **Temporal resolution** | 30 minutes (half-hourly) |
| **Temporal coverage** | Jul 2025 – Jun 2026 (12 months downloaded; extendable to 3+ years from the archive) |
| **Time zone** | NEM Time (AEST = UTC+10, no daylight saving adjustment) |
| **Row count** | 87,600 rows (17,520 per region) |
| **Completeness** | 100% — no gaps >30 min in any region; 0 null values |
| **Licence** | AEMO public data — free to use with attribution to AEMO |
| **Authentication** | None required |
| **Annual mean demand (scoring input)** | NSW1: 7,566 MW · QLD1: 6,207 MW · SA1: 1,324 MW · TAS1: 1,074 MW · VIC1: 5,134 MW |
| **Role in model** | **Scoring input** — Criterion 2 (Demand Indicator). Aggregated to annual mean MW per NEM region, then allocated to cells via population weighting. |
| **Pipeline step** | `pipeline/demand/download.py` → `pipeline/demand/inspect.py` → `pipeline/demand/aggregate.py` → Sprint 1 demand allocation |
| **Known limitations** | (1) 5 NEM regions only — no WA or NT coverage (platform limitation, documented). (2) No sub-regional spatial breakdown — requires population proxy for cell-level allocation. (3) Negative values occur in SA1 when distributed solar exceeds consumption (99 rows, min -263 MW) — included in annual mean as-is. (4) Operational demand excludes rooftop PV; actual consumption is higher. (5) Single year (2025–2026) — extendable to 3+ years for robustness in future sprints. |

---

#### 4.2.2 ABS Census 2021 Estimated Resident Population (SA2)

| Field | Value |
|-------|-------|
| **Dataset name** | ABS Census 2021 — Estimated Resident Population by Statistical Area Level 2 |
| **Publisher** | Australian Bureau of Statistics (ABS) |
| **Source** | ABS Census 2021 data products (TableBuilder or DataPacks); SA2 geometry from `geo.abs.gov.au` ArcGIS REST |
| **Variable(s)** | Estimated Resident Population (ERP) count per SA2 area |
| **Units** | Persons |
| **CRS** | SA2 geometry: GDA2020 (EPSG:7844), served via EPSG:3857 — must request `outSR=4326` |
| **Spatial resolution** | Statistical Area Level 2 (~2,500 areas nationally; comparable scale to ~5 km grid) |
| **Temporal coverage** | Census 2021 (reference date: 10 August 2021) |
| **Licence** | CC BY 4.0 — attribution: Australian Bureau of Statistics |
| **Role in model** | **Spatial denominator for demand allocation.** Each cell's population is estimated by area-weighting the SA2 polygons it intersects. The cell's demand indicator is then proportional to its share of the total regional population. |
| **Pipeline step** | Sprint 1 demand allocation stage (to be implemented) |
| **Allocation method** | For each grid cell: (1) Identify NEM region membership. (2) Estimate cell population as `sum(SA2_pop × fraction_of_SA2_in_cell)`. (3) Compute `cell_demand = region_mean_MW × (cell_pop / region_total_pop)`. |
| **Known limitations** | (1) 2021 vintage — population has shifted since census (acceptable for screening). (2) Uniform allocation within each SA2 — dense vs sparse parts of an SA2 get the same per-area allocation. (3) Industrial/commercial loads not well captured by population proxy. (4) Result must never be presented as "demand" without "estimated/proxy" qualifier. |
| **STATUS** | **NOT YET ACQUIRED — Sprint 1 must download this dataset.** Geometry (SA2 polygons) is available from the same ABS ArcGIS service used for other ASGS layers. Population counts must be obtained from ABS Census data products (DataPacks or TableBuilder). |

### 4.3 Grid & Infrastructure Accessibility

Infrastructure accessibility measures proximity to the existing transmission network — a practical constraint on connection cost and development feasibility. The scoring model uses **Euclidean (straight-line) distance** in EPSG:3577, not network distance (which would require road/terrain routing data unavailable at sufficient quality for V1).

**Key principle:** Proximity does not equal spare capacity. A nearby substation may be fully committed. These datasets support relative ranking between cells, not absolute connection feasibility assessments.

**Frozen parameter:** Voltage filter ≥ 132 kV (excludes distribution-level lines; appropriate for utility-scale wind).

---

#### 4.3.1 GA Power Lines 2026 (≥132 kV)

| Field | Value |
|-------|-------|
| **Dataset name** | Geoscience Australia — Electricity Infrastructure Power Lines 2026 |
| **Publisher** | Geoscience Australia (Commonwealth of Australia) |
| **Source endpoint** | `https://services.ga.gov.au/gis/rest/services/Electricity_Infrastructure/MapServer/2` |
| **Format** | ArcGIS Feature Service, downloaded as GeoJSON |
| **File in repository** | `DATA/infrastructure/transmission-lines/ga_power_lines_2026_australia.geojson` (national, 16 MB); `DATA/infrastructure/transmission-lines/ga_power_lines_2026_nsw.geojson` (state-filtered) |
| **Variable(s)** | Line geometry, `capacity_kv` (voltage in kV), `state`, `status`, `feature_name`, `spatial_confidence` |
| **Units** | kV (voltage attribute); geometry (line segments) |
| **CRS** | EPSG:7844 (GDA2020) — datum offset to WGS84 ~1.5 m, negligible at 5 km |
| **Spatial resolution** | Vector line geometry (national coverage) |
| **National feature count** | 3,147 lines total; voltage breakdown: 66 kV (1,230), 132 kV (1,050), 220 kV (205), 275 kV (209), 330 kV (178), 500 kV (50), other (225) |
| **Features ≥132 kV (scoring input)** | 1,692 lines nationally; 957 lines in NSW (all voltages) |
| **Temporal coverage** | Current snapshot, downloaded 2026-08-13 |
| **Operational status** | 3,130 Operational; 12 Non-Operational; 5 Under Construction |
| **Licence** | CC BY 4.0 — © Commonwealth of Australia (Geoscience Australia) 2026. Official safety and completeness disclaimer applies. |
| **Authentication** | None required |
| **Role in model** | **Scoring input** — Criterion 3 (Infrastructure Accessibility). Euclidean distance from each cell centroid to the nearest line ≥132 kV, computed in EPSG:3577. |
| **Pipeline step** | `pipeline/infrastructure/download.py` → `pipeline/infrastructure/inspect.py` → Sprint 1 feature builder (distance computation) |
| **Frozen parameters** | Voltage filter: ≥132 kV. Distance metric: Euclidean in EPSG:3577. No hard exclusion threshold (decision Q7). |
| **Known limitations** | (1) Screening-level, not engineering-grade — must not be treated as an asset register. (2) Proximity ≠ spare capacity — a nearby line may be fully committed. (3) Euclidean distance only — actual connection routes follow terrain and roads. (4) `feature_source_date` missing for 2,653 of 3,147 features. (5) Spatial confidence varies — attribute present but not filtered on. |

---

#### 4.3.2 GA Substations 2026

| Field | Value |
|-------|-------|
| **Dataset name** | Geoscience Australia — Electricity Infrastructure Substations 2026 |
| **Publisher** | Geoscience Australia (Commonwealth of Australia) |
| **Source endpoint** | `https://services.ga.gov.au/gis/rest/services/Electricity_Infrastructure/MapServer/0` |
| **Format** | ArcGIS Feature Service, downloaded as GeoJSON |
| **File in repository** | `DATA/infrastructure/substations/ga_substations_2026_australia.geojson` (national); `DATA/infrastructure/substations/ga_substations_2026_nsw.geojson` (state-filtered) |
| **Variable(s)** | Point geometry (`latitude`, `longitude`), `voltage_kv`, `state`, `status`, `locality`, `feature_name`, `spatial_confidence` |
| **Units** | kV (voltage attribute); geometry (points) |
| **CRS** | EPSG:7844 (GDA2020) — datum offset to WGS84 ~1.5 m, negligible at 5 km |
| **Spatial resolution** | Vector point geometry (national coverage) |
| **National feature count** | 1,866 substations total; 586 in NSW |
| **Voltage breakdown** | 66 kV (706), 132 kV (637), 220 kV (115), 275 kV (106), 330 kV (97), 500 kV (25), other (132), missing (48) |
| **Temporal coverage** | Current snapshot, downloaded 2026-08-15 |
| **Operational status** | 1,850 Operational; 13 Non-Operational; 3 Under Construction |
| **Licence** | CC BY 4.0 — © Commonwealth of Australia (Geoscience Australia) 2026. Official safety and completeness disclaimer applies. |
| **Authentication** | None required |
| **Role in model** | **Secondary scoring input** — Criterion 3 (Infrastructure Accessibility). Euclidean distance from each cell centroid to the nearest substation, computed in EPSG:3577. Voltage carried as an attribute for explanation (higher-voltage substations indicate stronger grid presence). |
| **Pipeline step** | `pipeline/infrastructure/download.py` → `pipeline/infrastructure/inspect.py` → Sprint 1 feature builder (distance computation) |
| **Known limitations** | (1) Same screening-level caveats as power lines. (2) 48 substations have missing `voltage_kv` — retain for distance but cannot filter by voltage. (3) A substation's voltage does not equal spare connection capacity. (4) `feature_source_date` missing for 1,775 of 1,866 features. |

#### 4.3.3 Derived Infrastructure Feature Table (S1-05)

| Field | Value |
|-------|-------|
| **Dataset name** | Opt-Mining NSW infrastructure accessibility feature table |
| **File in repository** | `DATA/infrastructure/optmining_infra-features_2026_nsw.gpkg`, layer `infra_features` |
| **Coverage** | One row for every cell in `DATA/grid/nsw_analysis_grid.gpkg` (47,311 NSW cells) |
| **Variables** | `cell_id`; nearest-line, nearest-substation and nearest-connection distances (`*_km`); `inside_rez`; `rez_name`; `confidence_flag` |
| **Distance method** | Straight-line distance from the cell centroid to the nearest point on each geometry, computed in EPSG:3577 and stored in kilometres. Line interiors are used, not only endpoints. |
| **REZ method** | Cell polygon intersection with EnergyCo NSW REZ boundaries; multiple names are joined with `; ` and no overlap is stored as null. |
| **Storage CRS** | EPSG:4326 (WGS 84) |
| **Confidence** | `high` only when all required source features resolve; missing, empty or unresolvable sources yield null feature values and `low`. |
| **Reproducibility** | Generated by `pipeline/infrastructure/features.py`; method report and source hashes are in `DATA/infrastructure/metadata/`. |
| **Known limitations** | AEMO KCI 2026 contains no latitude/longitude columns, so connection distance is null and confidence is low for this snapshot. Proximity is a screening indicator, not spare-capacity or connection-feasibility proof. |

### 4.4 Geographic & Environmental Suitability

This criterion determines whether a cell is physically and legally suitable for wind energy development. It combines **hard exclusions** (areas where development is clearly not permitted or physically impossible) with **continuous suitability penalties** (factors that reduce suitability without outright excluding a location).

**Hard exclusions (binary — cell excluded if any applies):**
1. Ocean — cells outside the ABS Australia outline
2. Protected areas — any CAPAD terrestrial polygon intersection (frozen decision Q6)
3. Water bodies — NLUM class 6 (lakes, reservoirs, rivers)
4. Dense urban — NLUM class 5.4.x cross-checked with ABS UCL polygons

**Continuous penalties:**
1. Slope — mean slope per cell (steeper = lower suitability); P90 reported in explanation (frozen decision Q3)
2. Land-use class — grazing (low penalty), cropping (moderate), forestry (higher)

---

#### 4.4.1 ABS ASGS 2021 Australia Outline (Land Mask)

| Field | Value |
|-------|-------|
| **Dataset name** | ABS ASGS Edition 3 (2021) — Australia (AUS) boundary |
| **Publisher** | Australian Bureau of Statistics |
| **Source endpoint** | `https://geo.abs.gov.au/arcgis/rest/services/ASGS2021/AUS/FeatureServer/0`, `f=geojson` |
| **File in repository** | `DATA/geographic/boundaries/abs_aus_2021_national.geojson` (3.3 MB) |
| **Variable(s)** | Single MultiPolygon (165,352 vertices) representing the Australian national boundary including external territories |
| **Units** | `area_albers_sqkm`: 7,688,095 km² (ABS-computed Albers area) |
| **CRS** | GDA2020 (service source SR is EPSG:3857); file stored as EPSG:4326 (requested with `outSR=4326`) |
| **Spatial resolution** | Vector polygon; generalised (~50 m `maxAllowableOffset`) for commit size — adequate for 5 km cells |
| **Temporal coverage** | Static boundary edition, current from 2021 |
| **Features** | 1 (national outline) |
| **Licence** | CC BY 4.0 — attribution: Australian Bureau of Statistics |
| **Authentication** | None required |
| **Role in model** | **Hard exclusion** — Land mask. Rasterised to the analysis grid; cells whose centroid falls outside this polygon are excluded as ocean. Chosen over Natural Earth 1:50m because it has better fidelity at high-wind coastal cells (21 of 28 false-land NE cells carry top-decile wind — see `metadata/landmask_assessment.md`). |
| **Pipeline step** | `pipeline/geographic/download.py` → Sprint 1 grid builder (rasterise to binary land/ocean mask) |
| **Known limitations** | (1) Generalised ~50 m — do not reuse for sub-100 m coastal work. (2) Includes external territories (Christmas Island, Norfolk Island, etc.) — may need filtering for NEM-only scope. (3) Does not distinguish inland water bodies — NLUM class 6 handles that separately. |

---

#### 4.4.2 DCCEEW CAPAD 2024 (Terrestrial Protected Areas)

| Field | Value |
|-------|-------|
| **Dataset name** | Collaborative Australian Protected Areas Database (CAPAD) 2024 — Terrestrial |
| **Publisher** | Department of Climate Change, Energy, the Environment and Water (DCCEEW) |
| **Source endpoint** | `https://gis.environment.gov.au/gispubmap/rest/services/ogc_services/CAPAD/FeatureServer/0`, `f=geojson` |
| **File in repository** | `DATA/geographic/protected/dcceew_capad-terrestrial_2024_nsw.geojson` (3.3 MB, NSW statewide); `DATA/geographic/protected/dcceew_capad-terrestrial_2024_new-england-rez.geojson` (study window) |
| **Variable(s)** | Protected area polygons with attributes: `NAME`, `TYPE`, `TYPE_ABBR`, `IUCN` category, `GAZ_AREA` (hectares), `GIS_AREA` (hectares), `STATE`, `ENVIRON` ('T' for terrestrial), `GAZ_DATE` (epoch ms) |
| **Units** | `GAZ_AREA` / `GIS_AREA` in hectares — convert to km² at ingestion. `GAZ_DATE` in epoch milliseconds — convert to ISO 8601. |
| **CRS** | Native: EPSG:4283 (GDA94); stored as EPSG:4326 (requested with `outSR=4326`). Datum offset ~1.8 m — negligible at 5 km. |
| **Spatial resolution** | Vector polygon (MultiPolygon + Polygon); 1,018 features in NSW; 14,492 nationally |
| **Temporal coverage** | CAPAD 2024 biennial edition. Reserves gazetted after 2024 may be missing (up to 2-year lag). |
| **IUCN categories present** | Ia, II, and others — 0 nulls in NSW sample |
| **Licence** | CC BY 4.0 — © Commonwealth of Australia (DCCEEW). Some sensitive site boundaries are generalised by custodians before publication. |
| **Authentication** | None required |
| **Role in model** | **Hard exclusion** — Binary: any intersection of a CAPAD terrestrial polygon with a grid cell excludes the entire cell (frozen decision Q6). |
| **Pipeline step** | `pipeline/geographic/download.py` → Sprint 1 exclusion builder (rasterise intersection test per cell) |
| **Known limitations** | (1) Biennial — reserves gazetted 2025–2026 may be missing. (2) Reserve names omit type suffix ("Kosciuszko" not "Kosciuszko National Park") — join with `TYPE` field for full name. (3) NSW statewide sample uses ~50 m generalisation; study-window extract is full resolution. (4) No mining-lease or native-title data — these would be additional hard exclusions in a production system but are not available in V1. |

---

#### 4.4.3 ABARES NLUM v7.1 250 m (Land Use)

| Field | Value |
|-------|-------|
| **Dataset name** | National Land Use Map v7.1, ALUM Classification v8, 2020–21 |
| **Publisher** | ABARES (Department of Agriculture, Fisheries and Forestry) |
| **Source URL** | `https://www.agriculture.gov.au/sites/default/files/documents/NLUM_v7_1_250m_ALUMV8_2020_21_alb_20260814.zip` (64.2 MB national) |
| **File in repository** | `DATA/geographic/landuse/abares_nlum-alumv8_2020-21_new-england-rez.tif` (220.9 KB, study window clip); `DATA/geographic/landuse/abares_alumv8_class_table.csv` (144-class lookup) |
| **Variable(s)** | Categorical int16 ALUM v8 land-use codes (144 classes with tertiary/secondary/primary hierarchy) |
| **Units** | Categorical codes (no continuous units); 0 = "No data/offshore" |
| **CRS** | **EPSG:3577 (GDA94 / Australian Albers)** — requires nearest-neighbour reprojection to EPSG:4326 for overlay with the analysis grid |
| **Native pixel size** | 250 m × 250 m (projected) |
| **Grid (study window)** | 884 × 999 pixels |
| **Temporal coverage** | 2020–21 land-use year (file published 2026-08-14); underlying state mapping vintages vary |
| **Licence** | CC BY 4.0 — attribution: ABARES, National Land Use Map 2020–21 |
| **Authentication** | None required (direct download) |
| **Role in model** | **Hard exclusion + suitability penalty** — Criterion 4 (Geographic Suitability). Exclusion: class 6 (water bodies — 6.1.0 lakes, 6.2.x reservoirs, 6.3.x rivers) and class 5.4.x (dense residential, cross-checked with ABS UCL). Penalty: class hierarchy drives a continuous suitability modifier (grazing land = low penalty; cropping = moderate; forestry = higher). |
| **Pipeline step** | `pipeline/geographic/download.py` → Sprint 1 exclusion + penalty builder (reproject, compute fraction per class per cell) |
| **Dominant classes (study window)** | Grazing modified pastures (46.5%), Grazing native vegetation (13.6%), Cereals (12.1%), Residual native cover (8.2%), National park (3.5%) |
| **Known limitations** | (1) 250 m pixels blur linear features (roads, rivers). (2) Native CRS is EPSG:3577 — requires warp to 4326 with nearest-neighbour resampling (categorical data, no interpolation). (3) Land use changes slowly at this scale but the 2020–21 vintage is 5+ years old. (4) Resolves wind farm footprints as class 5.6.3 "Wind electricity generation" — confirms the classifier works at 250 m. |

---

#### 4.4.4 ABS ASGS 2021 UCL (Urban Centres and Localities)

| Field | Value |
|-------|-------|
| **Dataset name** | ABS ASGS Edition 3 (2021) — Urban Centres and Localities (UCL) |
| **Publisher** | Australian Bureau of Statistics |
| **Source endpoint** | `https://geo.abs.gov.au/arcgis/rest/services/ASGS2021/UCL/FeatureServer/0`, `f=geojson` |
| **File in repository** | `DATA/geographic/urban/abs_ucl_2021_new-england-rez.geojson` (640.5 KB) |
| **Variable(s)** | Urban centre/locality boundary polygons with attributes: `ucl_name_2021`, `sosr_name_2021` (size class), `sos_name_2021` (section of state), `area_albers_sqkm` |
| **Units** | `area_albers_sqkm` in km² |
| **CRS** | GDA2020 (service source SR is EPSG:3857); stored as EPSG:4326 (requested with `outSR=4326`) |
| **Spatial resolution** | Vector polygon; 1,837 features nationally; 28 in study window |
| **Temporal coverage** | Static boundary edition, current from 2021 |
| **Licence** | CC BY 4.0 — attribution: Australian Bureau of Statistics |
| **Authentication** | None required |
| **Role in model** | **Cross-check for urban exclusion.** Validates NLUM class 5.4.x (dense residential) identification. Cells overlapping a "Major Urban" or "Other Urban" UCL polygon that also carry NLUM residential codes are hard-excluded. |
| **Pipeline step** | Sprint 1 exclusion builder (overlay test) |
| **Known limitations** | (1) Defines urban boundaries by population density from 2021 census — may not capture very recent urban expansion. (2) Size classification (`sosr_name_2021`) ranges from "200 to 999" to "1,000,000 and over" — only larger classes warrant hard exclusion. |

---

#### 4.4.5 SRTM GL3 Elevation (~90 m)

| Field | Value |
|-------|-------|
| **Dataset name** | NASA SRTM GL3 (3 arc-second, ~90 m) — elevation |
| **Publisher** | NASA/USGS; mirrored by OpenTopography (public S3) |
| **Source URL** | `https://opentopography.s3.sdsc.edu/raster/SRTM_GL3/SRTM_GL3_srtm.vrt` (VRT mosaic of tiles) |
| **File in repository** | `DATA/geographic/elevation/srtm-gl3_elevation_90m_new-england-rez.tif` (5.9 MB, study window) |
| **Variable(s)** | Elevation — single band, int16 |
| **Units** | Metres above sea level |
| **CRS** | EPSG:4326 (WGS 84) |
| **Native pixel size** | 0.000833° (~90 m) |
| **Grid (study window)** | 2,400 × 2,400 pixels |
| **NoData value** | 0 (conflates sea level — coastal use requires separate land mask) |
| **Elevation range (study window)** | 211 – 1,512 m; median 690 m; mean 722 m |
| **Temporal coverage** | Single epoch — SRTM mission, February 2000. Terrain does not change at screening timescales. |
| **Licence** | US public domain. OpenTopography requests acknowledgment: "SRTM data hosted by OpenTopography, https://opentopography.org/" |
| **Authentication** | None required (public S3 bucket, supports `/vsicurl/` windowed reads) |
| **Role in model** | **Source for slope derivation** — NOT directly used in scoring. Slope is derived from this DEM using Horn's 3×3 method (see §4.4.6). |
| **Pipeline step** | `pipeline/geographic/download.py` → `pipeline/geographic/derive.py` (slope derivation) |
| **Why GL3 not GL1** | GL3 (~90 m) preferred over GL1 (~30 m) for screening scale: less noise after aggregation to 5 km cells, and GL1 slope runs +1.31° hotter than GL3 at the same footprint (documented in `metadata/slope_derivation.md`). GL1 available as future sensitivity layer if needed. |
| **Known limitations** | (1) NoData value 0 conflates with sea level — never trust nodata alone in coastal cells, pair with land mask. (2) Single epoch (2000) — terrain is stable but land-cover changes (mining, construction) not reflected. (3) Unsmoothed — noisier than GA's DEM-S product, but GA services return HTTP 403 to scripted clients. |

---

#### 4.4.6 Derived Horn Slope (from SRTM GL3)

| Field | Value |
|-------|-------|
| **Dataset name** | Horn Slope — derived from SRTM GL3 elevation |
| **Source** | **DERIVED** by `pipeline/geographic/derive.py` from §4.4.5 (SRTM GL3) using Horn's 3×3 method |
| **File in repository** | `DATA/geographic/elevation/srtm-gl3_slope-horn_90m_new-england-rez.tif` |
| **Variable(s)** | Slope in degrees (stored as int16 with scale factor ×0.01°; actual values = pixel_value × 0.01) |
| **Units** | Degrees |
| **CRS** | EPSG:4326 (inherits from source DEM) |
| **Native pixel size** | 0.000833° (~90 m, same as source) |
| **Derivation method** | Horn's 3×3 finite-difference operator with per-row metre spacing: 111,132 m/° N–S; 111,320 × cos(lat) m/° E–W. Edge pixels use replicated padding. |
| **Temporal coverage** | Inherits from SRTM (2000 mission epoch) |
| **Licence** | Inherits US public domain from SRTM source |
| **Role in model** | **Continuous terrain penalty** — Criterion 4 (Geographic Suitability). Per-cell aggregation: **mean slope** used as the scoring penalty input (frozen decision Q3); **P90 slope** reported in the explanation layer for cells with significant steep sections. |
| **Pipeline step** | `pipeline/geographic/derive.py` → Sprint 1 feature builder (aggregate per cell: mean + P90) |
| **Aggregation** | ~3,600 native slope pixels per 0.05° cell (60 × 60). Mean computed for scoring; P90 for explanation. |
| **DERIVED — not custodial data.** | Regenerate from source (§4.4.5) rather than treating as an independent dataset. The derivation script is reproducible and deterministic. |
| **Known limitations** | (1) Inherits SRTM noise (bounded in `metadata/slope_derivation.md`). (2) Edge pixels use replicated padding — marginal effect on interior cells. (3) Quantisation (int16 × 0.01) introduces ≤0.005° error — negligible against method uncertainty. (4) GL3-derived slope is systematically lower than GL1-derived slope by ~1.31° at the same footprint — consistent with the smoothing effect of the coarser DEM. |

---

#### 4.4.7 ABS ASGS 2021 STE (State Boundaries) + Derived NEM Regions

| Field | Value |
|-------|-------|
| **Dataset name** | ABS ASGS Edition 3 (2021) — State and Territory (STE) boundaries + Derived NEM Region geometries |
| **Publisher** | Australian Bureau of Statistics (STE layer); NEM regions **DERIVED** by pipeline |
| **Source endpoint** | `https://geo.abs.gov.au/arcgis/rest/services/ASGS2021/STE/FeatureServer/0`, `f=geojson` |
| **Files in repository** | `DATA/geographic/boundaries/abs_ste_2021_national.geojson` (STE, 9 features); `DATA/geographic/derived/nem_regions_asgs2021_national.geojson` (5 NEM regions) |
| **Variable(s) — STE** | State/territory boundary polygons with `state_code_2021`, `state_name_2021`, `area_albers_sqkm` |
| **Variable(s) — NEM regions** | NEM region polygons: NSW1 (NSW+ACT), QLD1, SA1, TAS1, VIC1. WA, NT, Other Territories excluded (not in the NEM). |
| **Units** | `area_albers_sqkm` in km² |
| **CRS** | GDA2020 (service source SR is EPSG:3857); stored as EPSG:4326 (requested with `outSR=4326`) |
| **Spatial resolution** | Vector polygon; generalised (~50 m) for commit size |
| **Temporal coverage** | Static boundary edition, current from 2021 |
| **Licence** | CC BY 4.0 — attribution: Australian Bureau of Statistics |
| **Authentication** | None required |
| **Role in model** | (1) **Region assignment** — each grid cell is assigned to a NEM region for demand allocation (cell must know which region's demand total to draw from). (2) **Spatial scope** — STE boundaries define the NSW-first scope filter. |
| **Pipeline step** | `pipeline/geographic/download.py` (STE); `pipeline/geographic/derive.py` (NEM regions) → Sprint 1 grid builder (point-in-polygon assignment) |
| **NEM region derivation** | Re-grouping of STE polygons: NSW+ACT → NSW1; VIC → VIC1; QLD → QLD1; SA → SA1; TAS → TAS1. Polygons collected into MultiPolygon per region without geometric dissolve. Identical behaviour for point-in-polygon and rasterisation. |
| **DERIVED — NEM regions are NOT authoritative AEMO boundaries.** | AEMO publishes maps only, not GIS layers. These are derived from ABS STE and must be labelled accordingly. The NSW1 = NSW+ACT convention must be restated wherever regions are used. |
| **Known limitations** | (1) Generalised ~50 m — do not reuse for sub-100 m work. (2) External territories included in STE extent — filter for NEM scope. (3) NEM region boundaries are derived, not authoritative — they approximate AEMO's definition using ABS administrative boundaries. |

---

## 5. CRS Alignment Strategy

**Project-wide rule:** EPSG:4326 for storage, EPSG:3577 for distance/area computation. Enforce with runtime `assert_crs` checks at every function boundary that crosses a CRS. Mismatches raise immediately rather than producing silently wrong distances.

| # | Dataset | Native CRS | EPSG | Datum Offset to WGS84 | Transformation Required | Notes |
|---|---------|-----------|------|----------------------|------------------------|-------|
| 1 | GWA v4 Wind Speed @ 100 m | WGS 84 | 4326 | — | No | Native — no transformation |
| 2 | GWA v4 Power Density @ 100 m | WGS 84 | 4326 | — | No | Native — no transformation |
| 3 | GWA v4 Capacity Factor IEC2 | WGS 84 | 4326 | — | No | Native — no transformation |
| 4 | GWA v4 Wind Speed @ 150 m | WGS 84 | 4326 | — | No | Native — no transformation |
| 5 | AEMO Operational Demand | N/A (tabular) | — | — | No | No geometry — spatial allocation via population proxy |
| 6 | ABS Census 2021 SA2 ERP | GDA2020 (via 3857) | 7844 | ~1.5 m | Yes (declare explicitly; request outSR=4326) | Datum offset negligible at 5 km |
| 7 | GA Power Lines 2026 | GDA2020 | 7844 | ~1.5 m | Yes (declare explicitly; reproject to 3577 for distance) | Distance computed in EPSG:3577 |
| 8 | GA Substations 2026 | GDA2020 | 7844 | ~1.5 m | Yes (declare explicitly; reproject to 3577 for distance) | Distance computed in EPSG:3577 |
| 9 | ABS ASGS 2021 AUS outline | GDA2020 (via 3857) | 7844 | ~1.5 m | Yes (request outSR=4326) | Service defaults to EPSG:3857 — outSR must be explicit |
| 10 | DCCEEW CAPAD 2024 | GDA94 | 4283 | ~1.8 m | Yes (declare explicitly; request outSR=4326) | Datum offset negligible at 5 km |
| 11 | ABARES NLUM v7.1 250 m | GDA94 / Australian Albers | 3577 | ~1.8 m + reprojection | Yes (warp to 4326, nearest-neighbour) | Projected CRS — categorical data requires nearest-neighbour resampling |
| 12 | ABS ASGS 2021 UCL | GDA2020 (via 3857) | 7844 | ~1.5 m | Yes (request outSR=4326) | Service defaults to EPSG:3857 — outSR must be explicit |
| 13 | SRTM GL3 Elevation | WGS 84 | 4326 | — | No | Native — no transformation |
| 14 | Derived Horn Slope | WGS 84 | 4326 | — | No | Inherits CRS from SRTM source |
| 15 | ABS ASGS 2021 STE + NEM Regions | GDA2020 (via 3857) | 7844 | ~1.5 m | Yes (request outSR=4326) | Service defaults to EPSG:3857 — outSR must be explicit |

**Maximum datum offset across all datasets:** ~1.8 m (GDA94 to WGS84). This is negligible against the ~5,000 m cell size but must be declared and transformed explicitly per the Constitution — the risk is undocumented assumptions, not the magnitude of the error.

**Datasets requiring reprojection for distance/area computations:**
- GA Power Lines → EPSG:3577 (for Euclidean distance from cell centroids)
- GA Substations → EPSG:3577 (for Euclidean distance from cell centroids)
- Cell centroids → EPSG:3577 (for all distance and area calculations)

**Dataset requiring format reprojection:**
- ABARES NLUM → Warp from EPSG:3577 to EPSG:4326 using nearest-neighbour resampling (one-time at ingestion; categorical data must not be interpolated)

---

## 6. Temporal Alignment Strategy

All inputs to this platform are **long-run indicators** — none are time-series predictions. The scoring model combines stable, long-run characterisations of wind climate, annual demand, current infrastructure, and static terrain.

| # | Dataset | Temporal Nature | Time Range | Alignment Strategy |
|---|---------|----------------|------------|--------------------|
| 1 | GWA v4 (all wind layers) | Long-term climatological mean (static) | 2008–2017 (10-year ERA5 downscaling) | Use as-is — represents the long-run wind climate |
| 2 | AEMO Operational Demand | Time series (half-hourly) | Jul 2025 – Jun 2026 | Aggregate to annual mean MW per NEM region |
| 3 | ABS Census 2021 SA2 ERP | Census snapshot | Reference date: 10 Aug 2021 | Use as-is — population distribution changes slowly at regional scale |
| 4 | GA Power Lines 2026 | Snapshot (current) | Downloaded Aug 2026 | Use as-is — represents the current grid |
| 5 | GA Substations 2026 | Snapshot (current) | Downloaded Aug 2026 | Use as-is — represents the current grid |
| 6 | ABS ASGS 2021 AUS outline | Static boundary edition | 2021 (Ed. 3) | Use as-is — national boundary does not change |
| 7 | DCCEEW CAPAD 2024 | Biennial snapshot | CAPAD 2024 edition | Use as-is — caveat: reserves gazetted 2025–2026 may be missing |
| 8 | ABARES NLUM v7.1 | Periodic snapshot | 2020–21 vintage | Use as-is — land use changes slowly at this scale |
| 9 | SRTM GL3 + Derived Slope | Static (geophysical) | SRTM mission Feb 2000 | Use as-is — terrain does not change at screening timescales |
| 10 | ABS ASGS 2021 STE / UCL | Static boundary edition | 2021 (Ed. 3) | Use as-is — administrative boundaries are stable between census cycles |

**Key temporal gap:** The GWA wind climatology covers 2008–2017; AEMO demand data covers 2025–2026. This ~8-year offset is **acceptable for screening** because:
- Wind climate is a long-run characterisation, not a forecast — the ERA5-based 10-year mean is representative of the underlying climate regime
- Annual mean demand is likewise a long-run indicator of regional electricity consumption patterns
- Both describe stable phenomena at the timescales relevant to infrastructure planning decisions (decades)

**Mandatory disclosure:** This temporal gap must be stated wherever wind and demand criteria are combined in results, reports, or the user interface. The platform does not claim temporal synchronisation between these inputs.

---

## 7. Pipeline Mapping

Summary of how each dataset flows through the pipeline to produce the four scoring criteria.

| Dataset (§ ref) | Pipeline Stage | Output | Criterion |
|-----------------|---------------|--------|-----------|
| GWA Wind Speed 100 m (§4.1.1) | `wind.download` → feature builder | Cell-level mean wind speed (m/s) | 1 — Wind Resource |
| GWA Power Density 100 m (§4.1.2) | `wind.download` → feature builder | Cell-level mean power density (W/m²) | 1 — Wind Resource |
| GWA Capacity Factor IEC2 (§4.1.3) | `wind.download` → explanation layer | Cell-level mean CF (ratio) | 1 — Explanation only |
| GWA Wind Speed 150 m (§4.1.4) | `wind.download` → sensitivity analysis | Cell-level mean wind speed 150 m (m/s) | 1 — Sensitivity only |
| AEMO Operational Demand (§4.2.1) | `demand.download` → `demand.aggregate` | Annual mean MW per NEM region | 2 — Demand Indicator |
| ABS SA2 ERP (§4.2.2) | Sprint 1 acquisition → demand allocation | Cell population estimate (persons) | 2 — Demand Indicator |
| GA Power Lines ≥132 kV (§4.3.1) | `infrastructure.download` → feature builder | Distance to nearest line (km, EPSG:3577) | 3 — Infrastructure |
| GA Substations (§4.3.2) | `infrastructure.download` → feature builder | Distance to nearest substation (km, EPSG:3577) | 3 — Infrastructure |
| Derived infrastructure features (§4.3.3) | `infrastructure.features` | Per-cell distance, REZ membership and confidence fields | 3 — Infrastructure |
| ABS AUS Outline (§4.4.1) | `geographic.download` → grid builder | Binary land mask (cell in/out) | 4 — Hard exclusion |
| CAPAD 2024 (§4.4.2) | `geographic.download` → exclusion builder | Binary protected-area mask (cell in/out) | 4 — Hard exclusion |
| ABARES NLUM (§4.4.3) | `geographic.download` → exclusion + penalty builder | Water/urban exclusion + land-use penalty score | 4 — Exclusion + penalty |
| ABS UCL (§4.4.4) | `geographic.download` → exclusion builder | Urban cross-check mask | 4 — Hard exclusion |
| SRTM GL3 (§4.4.5) | `geographic.download` → `geographic.derive` | Source DEM for slope derivation | 4 — Intermediate |
| Derived Slope (§4.4.6) | `geographic.derive` → feature builder | Cell-level mean slope (°) + P90 slope (°) | 4 — Continuous penalty |
| ABS STE + NEM Regions (§4.4.7) | `geographic.download` + `geographic.derive` → grid builder | NEM region assignment per cell | 2 — Region join |

---

## 8. Change Control

This specification is **frozen** as of 2026-08-27. Changes follow this process:

### Adding a New Dataset

No new dataset may be added to this specification without:

1. **Documented gap** — A specific deficiency in the current specification that the new dataset fills, referenced to a pipeline requirement or user story
2. **Full metadata** — All fields documented per the format in §4 (source, variables, units, CRS, resolution, temporal coverage, licence, limitations, pipeline use)
3. **Integration assessment** — CRS alignment, temporal alignment, and spatial resolution compatibility verified against the grid definition (§3)
4. **Version bump** — This document's version number incremented and date updated
5. **Team review** — At least one team member reviews the addition

### Modifying a Frozen Parameter

Frozen parameters (team decisions in §2) may only be changed by:

1. **Team consensus** — The change is discussed and agreed by the team
2. **Documented rationale** — Why the original decision no longer holds, with evidence
3. **Impact assessment** — What downstream pipeline stages and results are affected
4. **Version bump** — Document version incremented

### Removing a Dataset

Datasets may be moved to the out-of-scope document (`sprint1_out_of_scope.md`) with:

1. **Documented reason** — Why it is no longer needed
2. **Downstream check** — Confirm no pipeline stage depends on it without a replacement
3. **Version bump**

### Sprint 1 Prerequisites (actions required before implementation)

| Action | Dataset | Owner | Status |
|--------|---------|-------|--------|
| Download ABS Census 2021 SA2 ERP (population counts) | §4.2.2 | Sprint 1 | NOT YET ACQUIRED |
| Extend GWA windowed reads from study window to NSW bbox | §4.1.1–§4.1.4 | Sprint 1 | Approach proven at study-window scale |
| Extend SRTM GL3 + slope derivation to NSW bbox | §4.4.5–§4.4.6 | Sprint 1 | Approach proven at study-window scale |
| Extend NLUM clip to NSW bbox | §4.4.3 | Sprint 1 | Approach proven at study-window scale |
| Extend AEMO demand to 3 years (robustness) | §4.2.1 | Sprint 1 (optional) | 1 year downloaded; extendable |

---

## Change History

| Version | Date | Change |
|---------|------|--------|
| 1.0 | 2026-08-27 | Initial release — Sprint 1 baseline. All team decisions frozen. |
