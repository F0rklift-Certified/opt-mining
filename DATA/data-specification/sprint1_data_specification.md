# Sprint 1 Data Specification

**Version:** 1.6
**Date:** 2026-09-03 (baseline frozen 2026-08-27)
**Status:** FROZEN — Sprint 1 baseline (v1.1–v1.6 amendments via §8 "Adding a New Dataset")
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
| **File in repository** | `DATA/wind-resource/gwa_v4_wind-speed_100m_new-england-rez.tif` (study window clip); `DATA/wind-resource/gwa_v4_wind-speed_100m_nsw.tif` (NSW grid-extent clip, S1-03 — lattice-snapped to bbox 141.01125, −37.51125, 153.66125, −28.16125 so each analysis cell is a clean 20×20 native-pixel block) |
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

---

#### 4.1.5 Wind Feature Table (derived, S1-03)

Added via the §8 "Adding a New Dataset" process (v1.1). **Documented gap:** S1-08's
integrated NSW feature table requires a per-cell wind feature keyed to the S1-02 analysis
grid; no per-cell wind dataset existed. **Integration assessment:** same grid, same storage
CRS (EPSG:4326), exact 20×20 native-pixel alignment — no reprojection or resampling.

| Field | Value |
|-------|-------|
| **Dataset name** | Per-cell wind feature table (derived from §4.1.1) |
| **File in repository** | `DATA/wind-resource/features/gwa_v4_wind-feature_2025_nsw.gpkg` (GeoPackage, layer `wind_features`) |
| **Derived from** | `DATA/wind-resource/gwa_v4_wind-speed_100m_nsw.tif` (§4.1.1 NSW clip) + `DATA/grid/nsw_analysis_grid.gpkg` (§3) |
| **Variable(s)** | `cell_id`, `wind_speed_100m` (mean of the cell's 20×20 native pixels), `units`, `data_source`, `confidence_flag` (`valid`/`no_data`), geometry |
| **Units** | m/s |
| **Coverage** | All 47,311 analysis cells (one row each). GWA carries real values over ocean, so offshore cells hold valid wind speeds — land-masking is deferred to S1-06/S1-07 per the grid decision document, and validity is expressed per cell via `confidence_flag`, never by dropping rows. |
| **Vintage token** | `2025` — GWA 4.0 published June 2025 (download-manifest `Last-Modified` 2025-06-12). The S1-03 design draft's `2023` token failed this check and was corrected. |
| **Role in model** | **Primary scoring input** — Criterion 1 (Wind Resource Potential), implementing frozen decisions Q1 (mean) and Q2 (100 m). Power density (§4.1.2) remains available as an additional Criterion 1 input for later sprints. |
| **Pipeline step** | `wind.features` stage (`pipeline/wind/features.py`), registered after `grid` |
| **Provenance** | SHA-256 + byte count + UTC timestamp in `metadata/download_manifest.json` (`derived_features`); method report `metadata/wind_feature_method.md`; derived-layer section in `DATA_PROVENANCE.md`. Fully regenerable. |
| **Known limitations** | Inherits §4.1.1's limitations (10-year mean, no interannual variability, ocean pixels valid). Cells with zero valid pixels are flagged `no_data` with a null value — never back-filled. |

### 4.2 Electricity Demand

The demand criterion uses the uniform-allocation MVP in S1-04 to distribute regional demand figures to grid cells. The population-weighted approach recorded in frozen decision Q4 is deferred until a later change-controlled release.

**MVP allocation formula:** `cell_demand = region_annual_mean_MW / N_cells_in_region`

The result must always be labelled "estimated demand indicator" — it is a proxy, not actual local consumption. A future population-weighted upgrade would use ABS Census 2021 ERP at SA2 level and require the §8 change-control process.

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

---

#### 4.2.3 Demand Proxy Table (Derived — S1-04)

Added via the §8 "Adding a New Dataset" process (v1.3). This standalone entry documents the S1-04 output in its own right; §4.5 references it only as an input to the integrated table.

| Field | Value |
|-------|-------|
| **Dataset name** | Per-cell Demand Proxy Table — regional AEMO demand allocated to the common analysis grid |
| **Source** | **DERIVED** by `pipeline/demand/feature.py` (the `demand.feature` stage, S1-04) from the demand aggregate (§4.2.1, via `DATA/electricity-demand/demand_annual_summary.csv`, column `MEAN_DEMAND_MW`), the derived NEM region geometry (§4.4.7, `DATA/geographic/derived/nem_regions_asgs2021_national.geojson`) and the common analysis grid (§3) |
| **File in repository** | `DATA/electricity-demand/aemo_demand-proxy_2026_nsw.gpkg` (GeoPackage, one layer, one row per grid `cell_id`) |
| **Variable(s) — per-cell columns** | `cell_id` (str, grid identifier, reused byte-for-byte from §3); `demand_proxy` (float, normalised 0–1 proxy indicator — **not** measured local demand); `allocation_method` (str, `uniform` in this MVP); `source_region` (str, NEM region id — `NSW1`/`QLD1`/`VIC1`, or null when the cell is outside every NEM polygon); `confidence_flag` (str, `high`/`medium`/`low`) |
| **Units** | `demand_proxy` normalised 0–1 (dimensionless); other columns categorical/string |
| **CRS** | EPSG:4326 (storage; geometry copied from the grid). Region allocation is computed in EPSG:3577 (§5); every transform is logged in the method report. |
| **Allocation method** | **Uniform** regional allocation (frozen decision Q4 records population-weighting as the deferred target): `raw_cell_demand_MW = MEAN_DEMAND_MW_region / N_cells_region`, then normalised to 0–1. NSW1 represents **NSW + ACT** under the NEM convention. Choosing uniform (not the Q4 population-weighted method) is an MVP scope decision, not a change to the frozen parameter, so no §2/README dual edit is triggered. |
| **Edge cases** | Cells outside all NEM polygons → null `demand_proxy` + `low` confidence. Boundary cells → centroid containment, then greatest-overlap with lexicographic `REGIONID` tie-break → `medium` confidence. Per-region counts on the 2026-09-03 run: NSW1 30,718; QLD1 3,624; VIC1 6,332; outside-region 6,637 (229 boundary/tie-break). Aggregate regions outside this grid (`SA1`, `TAS1`) are explicitly reported in the method report. |
| **Role in model** | Per-cell input for the Demand criterion; consumed by S1-08 integration (`demand_proxy`, `source_region`, `demand_confidence`). |
| **Pipeline step** | `pipeline/demand/feature.py` (`demand.feature` stage), scheduled in `config.STAGES` after `grid` (it CONSUMES the grid) and after the `demand` aggregate stage → S1-08 integration |
| **DERIVED — not custodial data.** | Fully regenerable from §4.2.1, §4.4.7 and the grid (§3); reproducible and deterministic. Stamped by the do-not-edit method report (`DATA/electricity-demand/demand_feature_method.md`) rather than a download-manifest SHA row, consistent with the other derived products (§4.1.5, §4.4.8). |
| **Known limitations** | (1) **Proxy, not a measurement** — AEMO regional demand ≠ local cell demand; uniform allocation does not represent local load centres or feeder constraints. (2) Cells outside all NEM regions carry null demand + `low` confidence, never a fabricated value. (3) The `2026` vintage token tracks the AEMO 2025-07-01→2026-06-30 demand window. |

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

#### 4.4.8 Geographic & Environmental Feature Table (Derived — S1-06)

| Field | Value |
|-------|-------|
| **Dataset name** | Per-cell Geographic & Environmental Feature Table — derived on the common analysis grid |
| **Source** | **DERIVED** by `pipeline/geographic/features.py` (the `geographic.features` stage, S1-06) from the common analysis grid (§3) and the geographic/environmental sources §4.4.2 (CAPAD), §4.4.3 (NLUM), §4.4.5 (SRTM GL3 elevation), §4.4.6 (derived Horn slope), plus the derived Riley TRI raster (see below) |
| **File in repository** | `DATA/geographic/features/optmining_geographic-features_2024_nsw.gpkg` (GeoPackage, one layer, one row per grid `cell_id`) |
| **Variable(s) — per-cell columns** | `cell_id` (str, grid identifier, reused byte-for-byte from §3); `elevation_m` (float, mean of valid pixels, metres AMSL); `slope_deg` (float, mean of valid pixels, degrees, plausible 0–90); `land_use` (str, ALUM v8 tertiary class name of the modal NLUM code, or `unmapped:<code>`); `protected_area` (bool, any-CAPAD-intersection flag, frozen decision Q6); `protected_area_name` (str, distinct CAPAD names joined by `"; "`, `"(unnamed protected area)"` placeholder for features with no name, `""` when none); `tri` (float, mean of valid pixels, metres, Glen-Innes sub-window only); `confidence_flag` (str, exactly `high` or `low`) |
| **Units** | `elevation_m`/`tri` in metres; `slope_deg` in degrees; other columns categorical/boolean/string |
| **CRS** | EPSG:4326 (storage; geometry copied byte-for-byte from the grid). Protected-area intersection is computed in EPSG:3577 (§5) and raster sampling reprojects cell geometry to each raster's CRS at the read boundary; every transformation is logged in the method report. |
| **Aggregation statistic** | `elevation_m`, `slope_deg`, `tri`: **mean** of valid (non-NoData) pixels per cell (cell-centre pixel-inclusion rule). `land_use`: **mode** of valid NLUM codes, lowest-code tie-break. `slope_deg` mean implements frozen decision Q3 (mean for scoring); `protected_area` boolean implements frozen decision Q6 (any intersection excludes). Neither Q3 nor Q6 is *changed* by this stage — they are *implemented as frozen* (see §2), so no §8 frozen-parameter change is triggered and no §2/README dual edit is required. |
| **Coverage gap** | The full NSW analysis grid contains 47,311 cells, but the current source rasters cover only part of it: elevation, slope, and NLUM cover the **New England REZ** extent, and the TRI raster covers only the **Glen-Innes** sub-window (~30 m). Cells outside a raster's coverage receive a **null** value for each variable derived from that raster. The method report records, per raster, the count of cells inside vs outside coverage (inside + outside = total cell count). |
| **Out-of-coverage confidence** | Any cell that lies outside the coverage of a **required** source raster (elevation, slope, or NLUM), or that has ≥50% NoData pixels for a required raster, is assigned `confidence_flag = low`. TRI is **excluded** from the confidence decision because it covers only Glen-Innes by design; otherwise the entire NSW grid would flag low. Because current coverage is limited to the New England REZ, most NSW cells are `low` confidence — this is expected and honest until source coverage is extended (§8 Sprint 1 Prerequisites). |
| **Role in model** | Per-cell feature inputs for Criterion 4 (Geographic Suitability). Feeds the S1-07 multi-criteria suitability scoring model (terrain penalty, land-use penalty) and the S1-08 exclusion layer (protected-area and land-use hard exclusions). |
| **Pipeline step** | `pipeline/geographic/features.py` (`geographic.features` stage), scheduled in `config.STAGES` immediately after `grid` (it CONSUMES the grid) and before the cross-domain `validate` stage → S1-07 suitability scoring, S1-08 exclusion layer |
| **DERIVED — not custodial data.** | Fully regenerable from the source datasets (§4.4.2, §4.4.3, §4.4.5, §4.4.6, derived TRI) and the grid (§3); reproducible and deterministic. Stamped by the do-not-edit method report (`DATA/geographic/metadata/geographic_features_method.md`) rather than a download-manifest SHA row, consistent with the other derived products (§4.4.6, §4.4.7). |
| **Known limitations** | (1) Coverage gap above — most NSW cells are out of coverage and carry null variables + `low` confidence until source rasters are extended to the full NSW bbox (§8 Prerequisites). (2) TRI is Glen-Innes-only and is excluded from the confidence decision. (3) Inherits all source-raster limitations (SRTM NoData=0 sea-level conflation §4.4.5; slope quantisation §4.4.6; NLUM categorical resampling §4.4.3). (4) The `2024` vintage token tracks the CAPAD 2024 edition, the most recent-vintage source. |

---

### 4.5 Integrated Feature Table (Derived — S1-08)

Added via the §8 "Adding a New Dataset" process (v1.2). **Documented gap:** S1-09 (confidence),
S1-10 (scoring) and S1-11 (shortlist) need one per-cell table holding every feature layer and the
exclusion outcome keyed to the grid `cell_id`; no such dataset existed. **Integration assessment:**
same grid (§3), same storage CRS (EPSG:4326) asserted on every input — no reprojection, no
resampling, no back-filling; every join is one-to-one and the row count is asserted after each.

| Field | Value |
|-------|-------|
| **Dataset name** | Integrated NSW Feature Table — every per-cell layer left-joined onto the common analysis grid |
| **Source** | **DERIVED** by `pipeline/integration/merge.py` (the `integration` stage, S1-08) from the grid (§3) and the wind (§4.1.5), geographic (§4.4.8) and infrastructure (§4.3.3) feature tables, the S1-04 demand-proxy table (`DATA/electricity-demand/aemo_demand-proxy_2026_nsw.gpkg`) and the S1-07 Eligibility_Table (`DATA/exclusions/optmining_exclusions_2024_nsw.gpkg`) |
| **File in repository** | `DATA/integration/optmining_integrated-features_2026_nsw.gpkg` (GeoPackage, layer `integrated_features`, one row per grid `cell_id`) and `DATA/integration/optmining_integrated-features_2026_nsw.csv` (same table without geometry; the deterministic artefact) |
| **Variable(s) — per-cell columns** | `cell_id`, `centroid_lat`, `centroid_lon`, `area_km2` (grid); `wind_speed` (← `wind_speed_100m`, m/s), `wind_confidence` (`valid`/`no_data`); `demand_proxy` (0–1), `source_region`, `demand_confidence` (`high`/`medium`/`low`); `dist_transmission_km`, `dist_substation_km`, `dist_connection_km` (km, EPSG:3577 centroid distances), `inside_rez` (bool), `rez_name`, `infra_confidence` (`high`/`low`); `elevation_m`, `slope_deg`, `tri`, `land_use`, `protected_area` (bool), `protected_area_name`, `geo_confidence` (`high`/`low`); `eligible` (bool), `exclusion_reason`, `triggered_rules`, `data_flags` (S1-07, as-is); `n_missing_features` (int, nulls among the ten scored feature columns); `data_confidence` (`high`/`medium`/`low`), `confidence_score` (float 0–1, 3 dp), `confidence_notes` (text, `'; '`-joined reasons, `—` when none) — the S1-09 confidence layer; geometry |
| **Units** | Retained from each source and tabulated per column (with the source column) in `metadata/integration_method.md` §4 |
| **CRS** | EPSG:4326 (storage; geometry copied byte-for-byte from the grid, asserted identical). Every input's CRS is asserted equal to EPSG:4326 and the stage halts otherwise — nothing is reprojected here (§5). |
| **Method** | Sequential **left joins on `cell_id`** from the grid (wind → geographic → infrastructure → demand → exclusions), each validated one-to-one with the row count asserted unchanged; excluded cells **retained** with `eligible = False`; per-column null counts asserted identical to upstream ("no NaN inflation"). Column names follow the S1-08 ticket; constant upstream columns and S1-07's own recomputed raster fields are dropped (the latter compared in non-fatal WARN checks). |
| **Coverage** | All 47,311 analysis cells (one row each). Nulls are inherited, never filled: on the 2026-09-03 run `dist_connection_km` is null everywhere (§4.3.3 limitation), geographic variables are null outside the New England REZ window (§4.4.8), `demand_proxy` is null outside every NEM region; `n_missing_features` records this per cell (histogram in the method report). |
| **Confidence** | The four upstream confidence flags are carried under per-layer names plus `n_missing_features`. The S1-09 layer (`pipeline/integration/confidence.py`, config `pipeline/integration/confidence_weights.yaml`, applied inside the `integration` stage between the join and validation) derives the composite: `confidence_score = soft × Σ_f w_f · avail_f · resolution_f · limitation_f · flag_f / Σ_f w_f` over the ten scored features (rounded to 3 dp), with `data_confidence` high ≥ 0.8, medium ≥ 0.5, else low. Weights mirror the S1-10 baseline weights (wind 0.35, transmission 0.20, demand 0.15, substation 0.10, slope 0.10, REZ 0.10) plus 0.05 each for elevation, land use, protected area and connection distance; resolution factors are 1.0 except the demand proxy (0.5, allocated from a NEM region); limitation factors sit on a four-point scale citing this specification per feature; upstream flag factors apply only to a layer's present features. Methodology, factors and bases: `DATA/integration/metadata/confidence_method.md`; distribution: `metadata/confidence_summary.md`. Confidence never excludes a cell. |
| **Vintage token** | `2026` — the newest upstream vintage merged (infrastructure and demand 2026; wind 2025; geographic and exclusions 2024). Each input's own vintage, SHA-256 and row count are recorded in the method report and manifest. |
| **Role in model** | The boundary between the integration layer and the scoring layer (Constitution): sole input to S1-09 (confidence), S1-10 (baseline suitability model — only `eligible` cells are scored) and S1-11 (ranked shortlist, which takes `centroid_lat`/`centroid_lon` from here). |
| **Pipeline step** | `integration` stage (`pipeline/integration/merge.py`), registered in `config.STAGES` after `exclusions` and before `validate`; `python -m pipeline` runs raw → integrated table, `python -m pipeline --only integration` re-joins existing layers |
| **Provenance** | SHA-256 of both outputs and of all six inputs, byte counts, UTC timestamp and git commit in `metadata/integration_manifest.json` (`derived_features`); method report `metadata/integration_method.md`; every validation check in `metadata/merge_validation.md`; generated derived-layer block in `DATA/integration/DATA_PROVENANCE.md`. Fully regenerable; the CSV is byte-identical across reruns with unchanged inputs. |
| **Known limitations** | (1) Inherits every upstream limitation and coverage gap; most cells are `low` confidence in the geographic and infrastructure layers. (2) The S1-07 exclusion layer samples the New-England-REZ wind clip while §4.1.5 covers all of NSW, so 45,711 cells are excluded as "Missing wind data" although `wind_speed` is populated for every cell; the WARN cross-layer check documents this (and 73 boundary cells whose wind means differ by > 0.01 m/s) until S1-07 consumes the feature tables. (3) The composite confidence (S1-09) reflects documented judgements — resolution and limitation factors on a fixed scale with a citation per feature — and is tunable by config; under the defaults no cell is `low`, and every eligible cell has the identical profile (0.830, `high`) because the missing evidence sits in low-weight features, so the composite separates the raster-coverage window from the rest of NSW rather than ranking shortlist candidates. The upstream `wind_confidence` (all `valid`) and `infra_confidence` (all `low`) flags carry no information on the current data. |

---

### 4.6 Eligibility Table (Derived — S1-07)

Added via the §8 "Adding a New Dataset" process (v1.3). This standalone entry documents the S1-07 exclusion-layer output in its own right; §4.5 references it only as an input to the integrated table.

| Field | Value |
|-------|-------|
| **Dataset name** | Per-cell Eligibility Table — hard-exclusion outcome per analysis cell |
| **Source** | **DERIVED** by `pipeline/exclusions/apply.py` (the `exclusions` stage, S1-07) from the common analysis grid (§3) and the configurable rules in `pipeline/exclusions/exclusion_rules.yaml`. The stage currently reads raw sources directly — CAPAD (§4.4.2), the derived Horn slope raster (§4.4.6), ABS UCL urban centres (§4.4.4) and the GWA wind-speed raster (§4.1.1) — and recomputes the per-cell fields the rules evaluate. Outstanding follow-up: consume the S1-03 (§4.1.5) and S1-06 (§4.4.8) feature tables instead of recomputing (see `pipeline/exclusions/__init__.py`). |
| **File in repository** | `DATA/exclusions/optmining_exclusions_2024_nsw.gpkg` (GeoPackage, one layer, one row per grid `cell_id`) |
| **Variable(s) — per-cell columns** | `cell_id` (str, grid identifier); `eligible` (bool, no nulls); `exclusion_reason` (str, human-readable reason(s) `"; "`-joined, empty when eligible); `triggered_rules` (str, rule names `"; "`-joined); the raw per-cell fields the rules evaluated — `protected_area` (bool), `protected_area_name` (str), `slope_deg` (float, degrees), `urban_area` (bool), `wind_speed_100m_ms` (float, m/s); `data_flags` (str, non-exclusionary "retain and flag" notes) |
| **Units** | `slope_deg` in degrees; `wind_speed_100m_ms` in m/s; other columns boolean/string |
| **CRS** | EPSG:4326 (storage; geometry copied from the grid). Protected-area and urban overlap computed in EPSG:3577 (§5); raster sampling reprojects cell geometry to each raster's CRS at the read boundary; all transforms logged in the method report. |
| **Rules (configurable, not hard-coded)** | Loaded from `exclusion_rules.yaml`; a cell may trigger several. MVP rules: protected-area overlap (CAPAD, frozen decision Q6), missing wind data, excessive slope (threshold in the rules file, default 15°), urban area. Adding/retuning a rule is a YAML edit — the rule engine (`rules.py`) does not change. |
| **Summary (2026-09-03 run)** | 47,311 cells; eligible **1,233** (2.6%); excluded **46,078**. By reason: missing_wind_data 45,711; protected_area 6,740; urban_area 62; excessive_slope 55 (cells may count under several reasons). |
| **Role in model** | Determines which cells are eligible for scoring; consumed by S1-08 integration (`eligible`, `exclusion_reason`, `triggered_rules`, `data_flags`) and gates S1-10 scoring (only eligible cells are scored). Exclusions are a separate, auditable stage — never hidden inside scoring code. |
| **Pipeline step** | `pipeline/exclusions/apply.py` (`exclusions` stage), scheduled in `config.STAGES` after the feature layers and before `integration` |
| **DERIVED — not custodial data.** | Fully regenerable from the grid (§3), the raw sources above and the rules file; reproducible and deterministic. Stamped by the do-not-edit method report (`DATA/exclusions/metadata/exclusion_summary.md`). |
| **Known limitations** | (1) The raw wind-speed, slope and urban sources currently read cover only the New England REZ window, so most cells are excluded as "Missing wind data" — an artefact of reading the REZ-clipped raster, not of true wind-data availability (the NSW-wide §4.1.5 table has a value for every cell). This resolves when the stage migrates to joining §4.1.5/§4.4.8. (2) Exclusion is hard/binary; graded suitability penalties are S1-10. (3) The `2024` vintage token tracks the CAPAD 2024 edition, the most recent full-NSW source. |

---

### 4.7 Baseline Suitability Score (Derived — S1-10)

Added via the §8 "Adding a New Dataset" process (v1.5). **Documented gap:** S1-11 (ranked shortlist) needs a per-cell suitability score, rank and per-criterion explanation keyed to the grid `cell_id`; no such dataset existed. **Integration assessment:** consumes only the §4.5 Integrated Feature Table and the criteria weights file — same grid (§3), same storage CRS (EPSG:4326), no reprojection, no back-filling, no new external source enters the platform.

| Field | Value |
|-------|-------|
| **Dataset name** | Baseline Suitability Score — per-cell weighted MCDA score, rank and per-criterion contributions |
| **Source** | **DERIVED** by `pipeline/scoring/` (the `scoring` stage, S1-10) from the §4.5 Integrated Feature Table (`DATA/integration/optmining_integrated-features_2026_nsw.gpkg`) and the criteria weights file `pipeline/scoring/scoring_weights.yaml` (a user input, not a dataset) |
| **File in repository** | `DATA/scoring/optmining_suitability-score_2026_nsw.gpkg` (GeoPackage, layer `suitability_score`, one row per grid `cell_id`) and `DATA/scoring/optmining_suitability-score_2026_nsw.csv` (same table without geometry; the deterministic artefact) |
| **Variable(s) — per-cell columns** | `cell_id`, `centroid_lat`, `centroid_lon` (carried from §4.5 so S1-11 can locate a cell without re-joining the grid); `suitability_score` (float 0–1, null for excluded cells); `rank` (int 1..n over scored cells, null for excluded cells); `confidence` (`high`/`medium`/`low`, carried verbatim from §4.5 `data_confidence`); one `contrib_{feature}` column per configured criterion — on the default weights `contrib_wind_speed`, `contrib_dist_transmission_km`, `contrib_demand_proxy`, `contrib_dist_substation_km`, `contrib_slope_deg`, `contrib_inside_rez` (float, additive share of the score, null for excluded cells); geometry |
| **Units** | `suitability_score` and every `contrib_*` column are dimensionless in [0, 1]; `rank` is an ordinal. The criteria's own units (m/s, km, degrees, boolean) are consumed from §4.5 and removed by normalisation — the method report records each criterion's source units and the bounds applied |
| **CRS** | EPSG:4326 (storage; geometry copied from the integrated table). The stage asserts its input is EPSG:4326 and halts otherwise — nothing is reprojected here (§5) |
| **Method** | Weighted **multi-criteria decision analysis (MCDA)**, not a machine-learning model. Per eligible cell and criterion *i*: `norm_i = (v_i − min_i)/(max_i − min_i)` for `higher_is_better`, `1 − (v_i − min_i)/(max_i − min_i)` for `lower_is_better`; `contrib_i = weight_i · norm_i / W_cell`; `score = Σ_i contrib_i`, where `W_cell` is the sum of the weights actually applied to that cell. Normalisation bounds are computed from the **eligible** population on each run, never hard-coded; boolean criteria use their definitional {0, 1} domain; a criterion constant over the eligible population is filled with a documented constant (1.0) and flagged rather than dividing by zero. `rank` is descending by score with ties broken by ascending `cell_id`. An optional confidence discount multiplies both the score and every contribution by the cell's factor (disabled by default) |
| **Criteria weights (configurable, not hard-coded)** | Loaded at runtime from `pipeline/scoring/scoring_weights.yaml` (or `--scoring-weights PATH`). Each criterion declares a feature, a weight, a direction and a written rationale; no weight literal appears in `pipeline/scoring/` source (Constitution: "Criteria weights are user inputs, never hard-coded constants"). Defaults: wind_speed 0.35 (higher), dist_transmission_km 0.20 (lower), demand_proxy 0.15 (higher), dist_substation_km 0.10 (lower), slope_deg 0.10 (lower), inside_rez 0.10 (higher) — the S1-10 ticket values, the same six weights §4.5's confidence layer mirrors. The stage halts before writing on an invalid direction, a negative or non-numeric weight, a duplicate criterion, a missing rationale or weights summing to zero |
| **Coverage / summary (2026-09-03 run)** | All 47,311 analysis cells (one row each). **Scored: 1,233** eligible cells (scores 0.218–0.932, mean 0.646, all `high` confidence); **46,078** excluded cells carry a null score and no rank |
| **Explainability** | Every criterion's additive contribution to every score is written to the table, and the contributions are verified on every run to sum back to the score within 1e-9 for every scored cell. This satisfies the Constitution's "a recommendation the user cannot interrogate is not a recommendation — it is an assertion" |
| **Confidence** | Carried verbatim from §4.5 `data_confidence`; never recomputed or fabricated. The S1-10 ticket assumed a two-value `high`/`low` flag while S1-09 (§4.5) emits three levels; the upstream value is carried through unchanged rather than collapsing `medium` into a neighbour, and validation asserts membership in the S1-09 vocabulary. On the current data every scored cell is `high`, so the scored population is two-valued in practice |
| **Vintage token** | `2026` — tracks the §4.5 integrated table it scores, so the two products are visibly the same generation of the data |
| **Role in model** | The scoring layer of the Constitution's data → criteria → scoring → presentation separation. Sole consumer of §4.5 for ranking purposes; sole input to S1-11 (ranked shortlist) |
| **Pipeline step** | `scoring` stage (`pipeline/scoring/run.py`), registered in `config.STAGES` after `integration` and before `validate`; `python -m pipeline --only scoring` rescores an existing integrated table |
| **DERIVED — not custodial data.** | Fully regenerable from §4.5 and the weights file; deterministic and reproducible with no manual editing. SHA-256 of both outputs, byte counts, UTC timestamp, git commit and the `weights_config_id` (SHA-256 of the weights file that produced the scores) in `metadata/scoring_manifest.json`; method in `metadata/scoring_method.md`; every check in `metadata/scoring_validation.md`; generated derived-layer block in `DATA/scoring/DATA_PROVENANCE.md` |
| **Known limitations** | (1) Inherits every §4.5 limitation and coverage gap, including the S1-07 artefact that restricts eligibility to the New-England-REZ window (§4.6), so the 1,233 scored cells are a raster-coverage window rather than a statewide candidate set. (2) `demand_proxy` is **constant across every eligible cell** on the current data (the §4.2.3 MVP proxy allocates one NEM-region value uniformly), so it contributes a flat 0.15 to every score and **cannot discriminate between cells**; the ranking is effectively driven by the other five criteria until the demand proxy is disaggregated below the NEM region. (3) Normalisation is min-max over the eligible population, so scores are **relative to the candidate set being compared** — a cell's score is not a portable absolute rating and will change if the eligible population changes. (4) Normalisation is linear; a logarithmic transform for distance criteria is defensible but is a modelling judgement left to an explicit future change. (5) The score is a strategic screening indicator only — never a project cost, an LCOE, a yield estimate or an engineering-grade assessment |

---

### 4.8 Ranked Shortlist (Derived — S1-11)

Added via the §8 "Adding a New Dataset" process (v1.6). **Documented gap:** Sprint 1 requires a headline output — a ranked list of the top candidate cells for wind development, exported for both tabular review (CSV) and map visualisation (GeoJSON) with summary statistics — and §4.7 v1.5 explicitly names S1-11 as the awaiting consumer of the score and rank; no such shortlist dataset existed. **Integration assessment:** consumes only the §4.7 Baseline Suitability Score (the sole score input) and the §3 Analysis_Grid (for `centroid_lat`/`centroid_lon`) — same grid (§3), same storage CRS (EPSG:4326), no reprojection (no distance or area computation arises here), no re-scoring, no re-ranking, no back-filling, no new external source enters the platform.

| Field | Value |
|-------|-------|
| **Dataset name** | Preliminary Ranked Shortlist — the top-N eligible cells by their existing S1-10 rank, as a table and a map layer, with summary statistics |
| **Source** | **DERIVED** by `pipeline/shortlist/` (the `shortlist` stage, S1-11) from the §4.7 Baseline Suitability Score (`DATA/scoring/optmining_suitability-score_2026_nsw.gpkg`, the sole per-cell score input) and the §3 common analysis grid (`DATA/grid/nsw_analysis_grid.gpkg`, source of `centroid_lat`/`centroid_lon`) |
| **File in repository** | `DATA/shortlist/sprint1_shortlist_<UTCdate>.csv` (Shortlist_CSV) and `DATA/shortlist/sprint1_shortlist_<UTCdate>.geojson` (Shortlist_GeoJSON, EPSG:4326), where `<UTCdate>` is the UTC Run_Timestamp date reused across both filenames and the metadata; region slug `nsw` where the `{source}_{dataset}_{year/vintage}_{region}.{ext}` convention applies. A colliding resolved name gets a finer-grained UTC time component by a documented deterministic rule (recorded in the Summary_Report), never a silent overwrite |
| **Variable(s) — per-cell columns** | `rank` (int, carried verbatim from §4.7 — the shortlist is ordered ascending by it, rank 1 first), `cell_id` (str, grid identifier, reused byte-for-byte), `suitability_score` (float 0–1, carried from §4.7), `confidence` (`high`/`medium`/`low`, carried from §4.7), `centroid_lat`, `centroid_lon` (EPSG:4326, joined from the §3 grid on `cell_id`) — in that documented column order; where available from an upstream layer, optional context columns (`rez`, `nearby_wind_farm`) are appended as named, documented columns with their definition and source recorded in the Summary_Report |
| **Units** | `suitability_score` dimensionless in [0, 1]; `rank` an ordinal; `centroid_lat`/`centroid_lon` decimal degrees (EPSG:4326); `confidence` categorical |
| **CRS** | EPSG:4326 (storage; `centroid_lat`/`centroid_lon` read from the §3 grid in EPSG:4326 and carried unchanged; the Shortlist_GeoJSON geometry is written in EPSG:4326 and the CRS is stated explicitly). This stage performs **no reprojection** — there is no distance or area computation, so no EPSG:3577 boundary arises (§5) |
| **Method** | **Filtering and formatting only** — not a modelling step. Select the Eligible_Cells (non-null `suitability_score` **and** non-null `rank`) with the smallest `rank` values, up to the effective Top_N, ordered ascending by `rank`; preserve the S1-10 rank ordering exactly through ties and gaps and never re-assign ranks; left-join `centroid_lat`/`centroid_lon` from the §3 grid on `cell_id`. Top_N is a **runtime** value (CLI `--shortlist-top-n` > pipeline-config value > default 20); a non-positive-integer Top_N halts before any write. Top_N over the eligible count includes every Eligible_Cell without padding; zero eligible cells yields headered, disclaimer-carrying empty outputs. The Shortlist_CSV and Shortlist_GeoJSON carry the same `cell_id` set in the same rank order (one feature per cell, centroid Point geometry by default; cell polygon the documented alternative). A Summary_Report records the score distribution over the Eligible_Cell population, the geographic spread and confidence distribution of the top sites, and the eligible/included counts |
| **Preliminary screening disclaimer** | Every output and its metadata carry the Preliminary_Disclaimer: the shortlist is a **preliminary screening output at the ~5 km (0.05 degree) analysis-grid-cell resolution — it indicates where to look next; it is not a site approval, an engineering assessment, or a final recommendation.** The Analysis_Resolution statement (~5 km, 0.05 degree analysis grid cell) is stated wherever results are presented — in the Summary_Report, the metadata sidecar and the GeoJSON file-level metadata; the CSV's disclaimer travels via its co-emitted Summary_Report and metadata sidecar |
| **Coverage / summary** | The top `min(Top_N, n_eligible)` eligible cells for the run. On the committed data §4.7 has **1,233** eligible (scored, ranked) cells, so a default run (Top_N 20) returns the 20 highest-ranked of those; the 46,078 excluded cells (null score, no rank) can never appear |
| **Confidence** | `confidence` is carried verbatim from §4.7 (itself carried from the §4.5 S1-09 `data_confidence`); never recomputed or fabricated. The confidence distribution of the shortlisted cells is reported in the Summary_Report |
| **Vintage token** | The output filenames use the timestamped `sprint1_shortlist_<UTCdate>` form rather than a `{vintage}` token; the shortlist tracks the §4.7 score (vintage `2026`) it selects from, recorded via the `scored_table_id` (path + SHA-256) in the metadata sidecar |
| **Role in model** | The presentation layer of the Constitution's data → criteria → scoring → presentation separation. Sole consumer of §4.7 for shortlisting; the Sprint 1 headline output and the input to the S1-12 mapping/reporting stage |
| **Pipeline step** | `shortlist` stage (`pipeline/shortlist/run.py`), registered in `config.STAGES` after `scoring` and before `validate`; `python -m pipeline --only shortlist` re-shortlists an existing Scored_Table |
| **DERIVED — not custodial data.** | Fully regenerable from §4.7 and the §3 grid; deterministic and reproducible with no manual editing (a rerun on a fixed Scored_Table, grid and Top_N reproduces the selection, ordering and statistics, ignoring the intentionally varying Run_Timestamp). SHA-256 of both outputs, byte counts, UTC Run_Timestamp and generation params (the Scored_Table and grid inputs, effective Top_N) in `metadata/shortlist_manifest.json`; the `scored_table_id` (path + SHA-256) in `metadata/shortlist_metadata.json`; the Summary_Report `metadata/shortlist_summary.md`; a derived-product row in `DATA/shortlist/DATA_PROVENANCE.md` and a `metadata/source_register.csv` entry |
| **Known limitations** | (1) Inherits every §4.7 (and thus §4.5/§4.6) limitation and coverage gap — the eligible population is the New-England-REZ raster-coverage window, so the shortlist is drawn from ~1,233 cells rather than a statewide candidate set. (2) The shortlist reflects the S1-10 ranking exactly and adds no new judgement; because `demand_proxy` is constant across eligible cells (§4.7), the ordering is effectively driven by the other five criteria. (3) The shortlist is a **strategic screening starting point only** — never a site approval, a project cost, a yield estimate or an engineering-grade assessment; its resolution is the ~5 km analysis cell |

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
| GWA Wind Speed 100 m (§4.1.1) | `wind.download` → `wind.features` (S1-03) | Per-cell wind feature table (§4.1.5): mean wind speed (m/s) + confidence flag | 1 — Wind Resource |
| GWA Power Density 100 m (§4.1.2) | `wind.download` → feature builder | Cell-level mean power density (W/m²) | 1 — Wind Resource |
| GWA Capacity Factor IEC2 (§4.1.3) | `wind.download` → explanation layer | Cell-level mean CF (ratio) | 1 — Explanation only |
| GWA Wind Speed 150 m (§4.1.4) | `wind.download` → sensitivity analysis | Cell-level mean wind speed 150 m (m/s) | 1 — Sensitivity only |
| AEMO Operational Demand (§4.2.1) | `demand.download` → `demand.aggregate` | Annual mean MW per NEM region | 2 — Demand Indicator |
| ABS SA2 ERP (§4.2.2) | Sprint 1 acquisition → demand allocation | Cell population estimate (persons) | 2 — Demand Indicator |
| Demand Proxy Table (§4.2.3) | `demand.aggregate` + NEM Regions (§4.4.7) → `demand.feature` (S1-04) | Per-cell `demand_proxy` (0–1), `source_region`, `confidence_flag` | 2 — Demand Indicator |
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
| Geographic Feature Table (§4.4.8) | CAPAD (§4.4.2) + NLUM (§4.4.3) + SRTM GL3 (§4.4.5) + Derived Slope (§4.4.6) + Derived TRI → `geographic.features` (S1-06) | Per-cell `elevation_m`, `slope_deg`, `tri`, `land_use`, `protected_area` (+ names), `confidence_flag` | 4 — Suitability (S1-07) + Exclusion (S1-08) |
| Eligibility Table (§4.6) | Grid (§3) + CAPAD (§4.4.2) + Derived Slope (§4.4.6) + ABS UCL (§4.4.4) + GWA Wind Speed (§4.1.1) + rules file → `exclusions` (S1-07) | Per-cell `eligible`, `exclusion_reason`, `triggered_rules`, evaluated fields, `data_flags` | All — eligibility gate for S1-08/S1-10 |
| Integrated Feature Table (§4.5) | Wind (§4.1.5) + Geographic (§4.4.8) + Infrastructure (§4.3.3) + S1-04 demand proxy + S1-07 Eligibility_Table → `integration` (S1-08) | One row per grid cell: every per-cell feature, per-layer confidence flags, `eligible`/`exclusion_reason`, `n_missing_features`, and the S1-09 composite `data_confidence`/`confidence_score`/`confidence_notes` (GeoPackage + CSV) | All criteria — input to S1-09 confidence, S1-10 scoring, S1-11 shortlist |
| Baseline Suitability Score (§4.7) | Integrated Feature Table (§4.5) + criteria weights (`pipeline/scoring/scoring_weights.yaml`) → `scoring` (S1-10) | Per grid cell: `suitability_score` (0–1, null when excluded), `rank`, `confidence`, and one `contrib_{feature}` column per configured criterion (GeoPackage + CSV) | All criteria — weighted MCDA over criteria 1–4; input to S1-11 shortlist |
| Ranked Shortlist (§4.8) | Baseline Suitability Score (§4.7) + Analysis_Grid (§3, for `centroid_lat`/`centroid_lon`) → `shortlist` (S1-11) | The top-N eligible cells by ascending S1-10 `rank`: `rank`, `cell_id`, `suitability_score`, `confidence`, `centroid_lat`, `centroid_lon` (Shortlist_CSV + Shortlist_GeoJSON, EPSG:4326) + Summary_Report | All criteria — preliminary ranked screening shortlist (headline output); input to S1-12 mapping/reporting |

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

**Applied — Geographic Feature Table (§4.4.8), v1.1:** The per-cell Geographic & Environmental Feature Table was added under this process. (1) *Gap:* S1-06 requires a per-cell feature layer keyed to the grid `cell_id` to feed the S1-07 suitability model and S1-08 exclusion layer — no such output existed. (2) *Metadata:* full §4-format entry at §4.4.8. (3) *Integration:* stored EPSG:4326, computed EPSG:3577 (§5), keyed byte-for-byte to the grid `cell_id` (§3); it is a DERIVED product regenerable from its sources. (4) *Version bump:* 1.0 → 1.1 (below). Note this is a **new derived output**, not a change to a frozen parameter — the stage *implements* frozen decisions Q3 (slope = mean for scoring) and Q6 (any-CAPAD-intersection boolean exclusion) exactly as recorded in §2, so the "Modifying a Frozen Parameter" process below is **not** triggered and no §2/README dual edit is made.

**Applied — Integrated Feature Table (§4.5), v1.2:** The Integrated NSW Feature Table was added under this process. (1) *Gap:* S1-09, S1-10 and S1-11 need one per-cell table holding every feature layer and the exclusion outcome keyed to the grid `cell_id` — no such dataset existed. (2) *Metadata:* full §4-format entry at §4.5. (3) *Integration:* every input is asserted to be stored in EPSG:4326 and keyed byte-for-byte to the grid `cell_id` (§3); the stage reprojects, resamples and back-fills nothing, joins one-to-one with the row count asserted after each join, and is a DERIVED product regenerable from its six inputs with a byte-identical CSV. (4) *Version bump:* 1.1 → 1.2 (below). This is a **new derived output**, not a change to a frozen parameter: no §2 decision is touched, so the "Modifying a Frozen Parameter" process below is **not** triggered and no §2/README dual edit is made. `data_confidence` is deliberately deferred to S1-09.

**Applied — Demand Proxy Table (§4.2.3) & Eligibility Table (§4.6), v1.3:** The S1-04 demand-proxy table and the S1-07 Eligibility Table were given their own standalone §4 entries under this process. (1) *Gap:* both were produced by the pipeline and already merged into the §4.5 integrated table (as inputs), but neither had its own §4 dataset detail section — a documentation gap flagged in the S1-08 completion notes. (2) *Metadata:* full §4-format entries at §4.2.3 and §4.6, plus §7 pipeline-mapping rows. (3) *Integration:* both are stored EPSG:4326, computed EPSG:3577 where distances/overlaps are involved (§5), keyed byte-for-byte to the grid `cell_id` (§3), and are DERIVED products regenerable from their sources. (4) *Version bump:* 1.2 → 1.3 (below). These are **documentation entries for existing derived outputs**, not new datasets or changes to any frozen parameter (Q1–Q7): §2 is unmodified and no §2/README dual edit is triggered.
**Applied — Confidence layer (§4.5 amendment), v1.4:** The S1-09 data-quality and confidence layer adds three columns to the Integrated Feature Table. (1) *Gap:* the Constitution requires a confidence reported alongside every score and S1-10/S1-11 consume it; §4.5 v1.2 deliberately deferred the composite. (2) *Metadata:* §4.5 Variables, Confidence and Known-limitations rows updated; the formula, weights, factors and their bases are in `DATA/integration/metadata/confidence_method.md` and the config file `pipeline/integration/confidence_weights.yaml` (SHA-256 recorded in the manifest and provenance). (3) *Integration:* same table, same grid, same CRS — nothing spatial changes; the columns are derived from values already in the table and the layer never removes a cell. (4) *Version bump:* 1.3 → 1.4. This amends an existing derived dataset; no §2 frozen parameter is touched, so the "Modifying a Frozen Parameter" process is **not** triggered.

**Applied — Baseline Suitability Score (§4.7), v1.5:** The per-cell suitability score was added under this process. (1) *Gap:* S1-11 needs a per-cell score, rank and per-criterion explanation keyed to the grid `cell_id` to produce a ranked shortlist; no such dataset existed, and §4.5 v1.2 explicitly names S1-10 as a consumer awaiting it. (2) *Metadata:* full §4-format entry at §4.7, plus a §7 pipeline-mapping row; the formula, per-criterion weights, directions, rationales and the normalisation bounds used on each run are in `DATA/scoring/metadata/scoring_method.md`, and the weights themselves in the config file `pipeline/scoring/scoring_weights.yaml` (SHA-256 recorded as `weights_config_id` in the manifest and provenance). (3) *Integration:* the sole input is the §4.5 integrated table — no new external dataset enters the platform. The stage asserts its input is stored in EPSG:4326 and halts otherwise, keys byte-for-byte to the grid `cell_id` (§3), reprojects, resamples and back-fills nothing, and is a DERIVED product regenerable from §4.5 plus the weights file with a byte-identical CSV across reruns. (4) *Version bump:* 1.4 → 1.5 (below). (5) *Team review:* pending — the two documented deviations below are the items requiring a reviewer's decision.

This is a **new derived output**, not a change to a frozen parameter. The criteria weights are a **user input** by constitutional requirement ("Criteria weights are user inputs, never hard-coded constants"), held in a runtime config file rather than in §2, so the "Modifying a Frozen Parameter" process below is **not** triggered and no §2/README dual edit is made. Retuning a weight is a config edit, not a specification change.

Two **deviations from the S1-10 ticket** are recorded here rather than resolved silently, because both arise from the data rather than the code and both are reviewer decisions:

- **Confidence vocabulary.** The ticket specifies `confidence` as exactly `high` or `low`. The S1-09 layer this stage consumes (§4.5) emits three levels (`high`/`medium`/`low`). Collapsing `medium` into either neighbour would fabricate a confidence the data does not support — which the ticket itself forbids ("rather than fabricating a confidence value") and the Constitution forbids twice over ("Never let poor data pass as good"; "Report confidence alongside every score"). The upstream value is therefore carried through verbatim, the vocabulary is composed from `integration/config.py` so it cannot drift, and validation asserts membership in it. On the current data every scored cell is `high`, so the ticket's two-value expectation holds observationally for the scored population.
- **Null criterion values.** The ticket does not state what happens when an eligible cell has no value for a configured criterion. The stage excludes that criterion from that cell's weighted average and divides by the weights actually applied — the ticket's own phrase "sum of the applied criterion weights" — leaving the contribution null. Scoring the gap as zero would penalise a cell for a deficiency in the data rather than a property of the land. On the current data no eligible cell is missing a criterion, so every scored cell used the full weight sum; the rule matters only for robustness and for future data.

**Applied — Ranked Shortlist (§4.8), v1.6:** The preliminary ranked shortlist was added under this process. (1) *Gap:* Sprint 1 needs a headline output — a ranked list of the top candidate cells exported as a table (CSV) and a map layer (GeoJSON) with summary statistics — and §4.7 v1.5 explicitly names S1-11 as the awaiting consumer of the score and rank; no such shortlist dataset existed. (2) *Metadata:* full §4-format entry at §4.8, plus a §7 pipeline-mapping row; the selection method, the effective Top_N and eligible/included counts, the geometry choice and the Summary_Statistics are in the generated `DATA/shortlist/metadata/shortlist_summary.md`, and the run metadata (including the `scored_table_id` SHA-256) in `DATA/shortlist/metadata/shortlist_metadata.json`. (3) *Integration:* the sole inputs are the §4.7 Baseline Suitability Score and the §3 grid — no new external dataset enters the platform. The stage is filtering and formatting only: it re-scores and re-ranks nothing, keys byte-for-byte to the grid `cell_id` (§3), stores in EPSG:4326 and performs no reprojection (no distance/area computation arises), and is a DERIVED product regenerable from §4.7 plus the grid (a rerun on fixed inputs and Top_N reproduces the selection, ordering and statistics, ignoring the intentionally varying Run_Timestamp). (4) *Version bump:* 1.5 → 1.6 (below). (5) *Team review:* pending.

This is a **new derived output**, not a change to a frozen parameter. Top_N is a **runtime value** (the `--shortlist-top-n` CLI flag / a pipeline-config value, default 20), not a §2 frozen decision (Q1–Q7): it widens or narrows the screening output and never changes the analysis, so the "Modifying a Frozen Parameter" process below is **not** triggered and no §2/README dual edit is made. Consistent with the constitutional constraint that the shortlist is a preliminary screening starting point, every output and its metadata carry the Preliminary_Disclaimer and the ~5 km (0.05 degree) Analysis_Resolution statement (recorded identically in §4.8 and the README).

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
| Extend GWA windowed reads from study window to NSW bbox | §4.1.1–§4.1.4 | Sprint 1 | **DONE for §4.1.1–§4.1.3** (S1-03, 2026-08-31 — lattice-snapped NSW clips committed); §4.1.4 (150 m) still study-window only |
| Extend SRTM GL3 + slope derivation to NSW bbox | §4.4.5–§4.4.6 | Sprint 1 | Approach proven at study-window scale |
| Extend NLUM clip to NSW bbox | §4.4.3 | Sprint 1 | Approach proven at study-window scale |
| Extend AEMO demand to 3 years (robustness) | §4.2.1 | Sprint 1 (optional) | 1 year downloaded; extendable |

---

## Change History

| Version | Date | Change |
|---------|------|--------|
| 1.6 | 2026-09-03 | S1-11: added §4.8 Ranked Shortlist (derived dataset, per §8 "Adding a New Dataset") and its §7 pipeline-mapping row. The shortlist is a filtering-and-formatting output over §4.7 — it re-scores and re-ranks nothing and stores in EPSG:4326 with no reprojection. Top_N is a runtime CLI/config value (`--shortlist-top-n`, default 20), not a frozen parameter, so no §8 "Modifying a Frozen Parameter" process applies. Every output carries the Preliminary_Disclaimer and the ~5 km (0.05 degree) Analysis_Resolution statement. No frozen parameter (Q1–Q7) changed. |
| 1.0 | 2026-08-27 | Initial release — Sprint 1 baseline. All team decisions frozen. |
| 1.1 | 2026-08-27 | Added §4.4.8 Geographic & Environmental Feature Table (derived, S1-06) and its §7 pipeline-mapping row via the §8 "Adding a New Dataset" process. Frozen decisions Q3 and Q6 are implemented (not changed); §2 unmodified. |
| 1.1 | 2026-08-31 | S1-03: added §4.1.5 wind Feature_Table (derived dataset, per §8 "Adding a New Dataset"); GWA clips extended to the NSW grid extent per the §8 prerequisite (wind-speed 100 m, power-density 100 m, CF IEC2); `WIND_FEATURE_SOURCE` deviates from the S1-03 design.md's New-England-REZ filename to the NSW clip; vintage token `2025` per the download manifest (design draft said `2023`). No frozen parameter (Q1–Q7) changed. |
| 1.2 | 2026-09-03 | S1-08: added §4.5 Integrated Feature Table (derived dataset, per §8 "Adding a New Dataset") and its §7 pipeline-mapping row. Column names follow the S1-08 ticket (`wind_speed` ← `wind_speed_100m`); `data_confidence` deferred to S1-09 (per-layer confidence flags + `n_missing_features` carried instead); S1-07's recomputed raster fields compared in WARN checks, not carried. No frozen parameter (Q1–Q7) changed. |
| 1.3 | 2026-09-03 | Added standalone §4 entries for two already-merged derived outputs that previously lacked their own dataset sections: §4.2.3 Demand Proxy Table (S1-04) and §4.6 Eligibility Table (S1-07), plus their §7 pipeline-mapping rows. Documentation-only (closes a gap flagged in the S1-08 completion notes); no new datasets, no frozen parameter (Q1–Q7) changed. |
| 1.5 | 2026-09-03 | S1-10: added §4.7 Baseline Suitability Score (derived dataset, per §8 "Adding a New Dataset") and its §7 pipeline-mapping row. Criteria weights are a user-input config file (`pipeline/scoring/scoring_weights.yaml`), not a frozen parameter, so no §8 "Modifying a Frozen Parameter" process applies. Two documented deviations from the S1-10 ticket are recorded in §4.7 and the generated method report: `confidence` is carried through with S1-09's three-level vocabulary rather than forced to two values, and a null criterion value is excluded from that cell's weighted average rather than scored as zero. No frozen parameter (Q1–Q7) changed. |
| 1.4 | 2026-09-03 | S1-09: §4.5 amended with the composite confidence columns (`data_confidence`, `confidence_score`, `confidence_notes`) derived inside the `integration` stage from the per-layer flags, feature availability and configured resolution/limitation factors (`pipeline/integration/confidence_weights.yaml`); §7 row updated; §8 Applied paragraph added. No frozen parameter (Q1–Q7) changed. |
