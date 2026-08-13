# Task 2 — Electricity Demand Data Investigation

**Sprint:** 0 (Week 1)  
**Assignee:** _[Name]_  
**Status:** Complete  
**Estimated Effort:** 1–2 days  

---

## 1. Objective

Investigate, document and sample Australian electricity demand data — primarily from AEMO's National Electricity Market (NEM) datasets — to determine what can be used as the demand criterion in the suitability scoring model.

---

## 2. Context

The Product Knowledge Base identifies AEMO NEM demand as a high-priority data source. The platform needs a regional demand indicator derived from approximately 3–5 recent complete years of historical data.

Key challenge: AEMO reports demand at NEM region level (NSW1, QLD1, SA1, TAS1, VIC1), not at local/site level. The platform will need a spatial proxy (e.g. population weighting) to allocate regional demand to ~5km grid cells. This task investigates the raw demand data; the allocation strategy is addressed in Task 5.

Key reference: https://aemo.com.au/energy-systems/electricity/national-electricity-market-nem/data-nem

---

## 3. Investigation Checklist

### Availability & Access
- [x] Identify what demand datasets AEMO publishes (aggregated price and demand, operational demand, forecast demand, etc.)
- [x] Determine which dataset is most appropriate for historical demand analysis
- [x] Check whether data is freely downloadable or requires registration/API access
- [x] Record licensing and usage restrictions (attribution, commercial use)
- [x] Identify the AEMO data portal and navigation path to reach the demand data

### Temporal Properties
- [x] Determine the temporal granularity (5-minute, 30-minute, daily, monthly, annual)
- [x] Identify the available date range (how far back does data go?)
- [x] Confirm that 3–5 recent complete years are available (e.g. 2019–2023 or 2020–2024)
- [x] Check whether data is provided in a single file or split by year/month/region

### Spatial / Regional Properties
- [x] Identify what regions are covered (NEM regions: NSW1, QLD1, SA1, TAS1, VIC1)
- [x] Determine whether sub-regional breakdowns exist (e.g. by zone, by connection point)
- [x] Check whether Western Australia (SWIS) or Northern Territory data is available separately
- [x] Note that NEM does not cover WA or NT — document this coverage gap

### Variables & Metrics
- [x] Identify what demand metrics are available:
  - [x] Total demand (MW)
  - [x] Operational demand
  - [ ] Scheduled demand — not directly in this dataset
  - [x] Maximum demand — derivable from half-hourly data
  - [x] Minimum demand — derivable from half-hourly data
  - [x] Average demand — derivable from half-hourly data
- [x] Determine units (MW, MWh, GWh?)
- [x] Identify whether generation data is co-located with demand data
- [x] Check whether price data is bundled (useful context but not primary)

### Format & Structure
- [x] Identify file formats available (CSV, Excel, API/JSON, etc.)
- [x] Determine file sizes for multi-year downloads
- [x] Check column naming conventions and consistency across years
- [x] Identify any data quality notes or caveats published by AEMO

### Sample Download
- [x] Download a manageable sample (e.g. one full recent year for all NEM regions)
- [x] If data is very large at 5-minute resolution, also try monthly aggregated data
- [x] Store samples in `DATA/electricity-demand/` with a clear naming convention

---

## 4. Data Sources Investigated

| Source Name | URL | Format(s) | Licence | Download Available? | Notes |
|-------------|-----|-----------|---------|---------------------|-------|
| AEMO — Operational Demand (Actual, Half-Hourly) | https://nemweb.com.au/Reports/Archive/Operational_Demand/ACTUAL_DAILY/ | CSV inside nested ZIPs | Public data, free to use with attribution to AEMO | Yes — no auth required | **Recommended dataset.** Monthly archive ZIPs each containing daily ZIPs with half-hourly data per region. |
| AEMO — Operational Demand (5-minute) | https://nemweb.com.au/Reports/Current/Operational_Demand/ACTUAL_5MIN/ | CSV inside ZIPs | Public data, free to use with attribution | Yes | Higher resolution (5-min) but much larger volume; not needed for screening |
| AEMO — Aggregated Price and Demand | https://aemo.com.au/energy-systems/electricity/national-electricity-market-nem/data-nem/aggregated-data | CSV | Public data | Yes (via portal) | Includes RRP (price) alongside demand; 30-min intervals |
| AEMO — Daily Reports | https://nemweb.com.au/Reports/Current/Daily_Reports/ | CSV inside ZIPs (~6 MB each) | Public data | Yes | Comprehensive daily files with price, demand, generation combined |
| AEMO — Data Dashboard | https://aemo.com.au/energy-systems/electricity/national-electricity-market-nem/data-nem | Web interface | Public | Interactive only | Useful for exploration but not bulk download |
| OpenNEM | https://opennem.org.au/ | Web API / JSON | Open source (MIT) | Yes (API) | Community-built visualisation layer over AEMO data; provides convenient API access but no additional raw data beyond AEMO |
| AEMO WA — WEM (Western Australia) | https://aemo.com.au/energy-systems/electricity/wholesale-electricity-market-wem | Various | Public | Separate system | Not part of NEM; would require separate investigation |

**Navigation path to recommended dataset:**
1. Go to https://nemweb.com.au/Reports/
2. Navigate to `Archive/Operational_Demand/ACTUAL_DAILY/`
3. Monthly ZIP files are named `PUBLIC_ACTUAL_OPERATIONAL_DEMAND_DAILY_YYYYMM01.zip`
4. Each monthly ZIP contains daily ZIPs; each daily ZIP contains a CSV
5. For recent data (last ~60 days), use `Current/Operational_Demand/ACTUAL_DAILY/`

**Licensing:** AEMO publishes NEM data as public information under the National Electricity Rules. Data is free to download and use. Attribution to AEMO is required when publishing derived results.

---

## 5. Sample Data Downloaded

| File Name | Source | Size | Spatial Coverage | Temporal Coverage | Location in Repo |
|-----------|--------|------|------------------|-------------------|------------------|
| aemo_operational_demand_daily_2025.csv | AEMO NEMWeb Archive (Operational_Demand/ACTUAL_DAILY) | 4.49 MB | All 5 NEM regions (NSW1, QLD1, SA1, TAS1, VIC1) | Jul 2025 – Jul 2026 (12 months) | `DATA/electricity-demand/` |
| 12 monthly archive ZIPs (raw) | AEMO NEMWeb Archive | ~75 KB each | All 5 NEM regions | Jul 2025 – Jun 2026 | `DATA/electricity-demand/raw/` |

**Naming convention used:** `aemo_operational_demand_daily_YYYY.csv` where YYYY indicates the primary year of coverage.

**Note:** The Archive at nemweb.com.au contains monthly files going back further. To obtain 3–5 full years, download additional months from the Archive. The same script (`scripts/download_aemo_demand.py`) can be adapted to fetch earlier periods.

---

## 6. Data Inspection Summary

| Dataset | Columns/Variables | Row Count | Missing Values | Region Fields | Units | Date/Time Fields | Usable? |
|---------|-------------------|-----------|----------------|---------------|-------|------------------|---------|
| aemo_operational_demand_daily_2025.csv | 6 (REGIONID, INTERVAL_DATETIME, OPERATIONAL_DEMAND, OPERATIONAL_DEMAND_ADJUSTMENT, WDR_ESTIMATE, LASTCHANGED) | 87,600 | 0 (none) | REGIONID: NSW1, QLD1, SA1, TAS1, VIC1 | MW | INTERVAL_DATETIME (30-min interval end), LASTCHANGED | **Yes** |

**For demand data specifically:**
- **Temporal resolution (interval length):** 30 minutes (half-hourly). Each row represents one 30-minute dispatch interval for one region.
- **Time zone used:** NEM Time (AEST = UTC+10, with no daylight saving adjustment). This is consistent year-round.
- **Region naming convention:** Standard NEM region IDs — NSW1, QLD1, SA1, TAS1, VIC1. Consistent with AEMO's other datasets (infrastructure, generation).
- **Are there header rows or metadata rows to skip?** Yes. Raw AEMO CSVs use an `I/D/C` row format: `C` = comment, `I` = header, `D` = data. The download script handles this automatically.
- **Does the file have consistent formatting across all years?** Yes. Column names and structure are identical across all monthly archives tested (Jul 2025 – Jun 2026). Earlier archives (pre-2025) should be verified but are expected to match.

**Regional demand statistics (MW):**

| Region | Mean | Std Dev | Min | Max | Rows |
|--------|------|---------|-----|-----|------|
| NSW1 | 7,566 | 1,526 | 2,848 | 13,204 | 17,520 |
| QLD1 | 6,207 | 1,138 | 2,790 | 10,504 | 17,520 |
| SA1 | 1,324 | 466 | -263 | 3,124 | 17,520 |
| TAS1 | 1,074 | 141 | 678 | 1,575 | 17,520 |
| VIC1 | 5,134 | 1,149 | 312 | 10,736 | 17,520 |

---

## 7. Data Dictionary

**Dataset:** AEMO NEM — Operational Demand (Actual, Half-Hourly)  
**Source:** https://nemweb.com.au/Reports/Archive/Operational_Demand/ACTUAL_DAILY/  
**Format:** CSV (extracted from nested ZIP archives)  
**CRS:** N/A (tabular, region-level)  
**Temporal Range:** 2025-07-01 to 2026-07-01 (sample); Archive extends further back  
**Temporal Resolution:** 30 minutes (half-hourly, 48 intervals per day)  
**Spatial Resolution:** NEM Region (NSW1, QLD1, SA1, TAS1, VIC1)  

| Field/Column Name | Data Type | Units | Description | Example Value | Missing Values? |
|-------------------|-----------|-------|-------------|---------------|-----------------|
| REGIONID | string | — | NEM region identifier | NSW1 | None (0) |
| INTERVAL_DATETIME | datetime | — | End timestamp of the 30-minute dispatch interval | 2025-07-01 04:30:00 | None (0) |
| OPERATIONAL_DEMAND | integer | MW | Regional operational demand — electricity demand met by scheduled, semi-scheduled and significant non-scheduled generation (excludes rooftop PV contribution) | 7604 | None (0) |
| OPERATIONAL_DEMAND_ADJUSTMENT | integer | MW | Manual adjustment to demand figure (typically 0) | 0 | None (0) |
| WDR_ESTIMATE | integer | MW | Estimated wholesale demand response active in interval | 0 | None (0) |
| LASTCHANGED | datetime | — | Timestamp when this record was last updated by AEMO | 2025/07/01 04:30:02 | None (0) |

**Key notes:**
- "Operational demand" differs from "total demand" — it represents demand that must be met by centrally-dispatched generation, excluding behind-the-meter generation like rooftop solar.
- Negative values occur in SA1 when distributed generation exceeds consumption (99 instances in the sample year, minimum -263 MW).
- OPERATIONAL_DEMAND_ADJUSTMENT is zero for all rows in the sample — it exists for exceptional corrections.
- WDR_ESTIMATE captures wholesale demand response mechanisms (minimal non-zero values observed).

---

## 8. Integration Issues Identified

| Issue | Description | Severity (High/Med/Low) | Suggested Resolution | Resolved? |
|-------|-------------|-------------------------|----------------------|-----------|
| No spatial coordinates | Demand data is at NEM region level (5 regions), not lat/lon or per grid cell | High | Need spatial proxy (population weighting, load centres, substation locations) to allocate regional demand to ~5 km grid cells. Deferred to Task 5. | No — Task 5 |
| Coverage gap — WA and NT | NEM does not cover Western Australia (SWIS/WEM) or Northern Territory | Med | Document as platform limitation. WA has separate AEMO WA data; NT is separate. MVP covers NEM states only (NSW, QLD, SA, TAS, VIC). | Documented |
| Temporal granularity vs. wind data | 30-min demand data for multiple years = large dataset (87,600 rows per year); wind resource data from Global Wind Atlas is a long-term mean | Med | Aggregate demand to annual mean per region for the suitability screening model. Retain half-hourly data for later temporal matching if needed. | Resolved by aggregation |
| Time zone consistency | AEMO uses NEM time (AEST = UTC+10, no DST) consistently | Low | Document and standardise across all datasets. NEM time is stable year-round. | Documented |
| Negative demand values | SA1 occasionally shows negative operational demand (-263 MW min) when distributed solar exceeds regional consumption | Low | Not an error — reflects real grid conditions. For annual mean calculation, include as-is. Consider noting for interpretation. | Documented |
| Operational vs. Total demand | "Operational demand" excludes rooftop PV generation; actual total consumption is higher | Low | Document the definition clearly. For site suitability purposes, operational demand is the relevant metric (represents grid-served load that new generation can supply). | Documented |
| Region naming consistency | Region IDs (NSW1, QLD1, etc.) are standard AEMO identifiers | Low | Should be consistent with infrastructure data (Task 3). Verify during integration (Task 5). | Pending verification |

**Additional considerations:**
- **Demand allocation problem:** The key challenge is converting 5 regional demand values into demand estimates for ~5 km grid cells. Options include population-weighted allocation, proportional to substation capacity, or distance-based decay from load centres. This is addressed in Task 5.
- **COVID anomalies:** The sample period (Jul 2025 – Jun 2026) is post-COVID and reflects current demand patterns. If extending to 3–5 years, the 2020–2021 period had reduced demand; consider excluding or noting.
- **Extreme events:** Summer peaks (Jan 2026: NSW max 13,182 MW, VIC max 10,736 MW) reflect heatwave conditions. These are valid data points, not outliers.
- **Temporal alignment with wind data:** Wind resource data (Global Wind Atlas) is a long-term climatological mean. Demand data is historical actuals. Both will be aggregated to annual/seasonal summaries for the scoring model, which makes them compatible for screening purposes.

---

## 9. Key Findings & Recommendations

### Which dataset is most appropriate?

**AEMO Operational Demand (Actual, Half-Hourly)** from `nemweb.com.au/Reports/Archive/Operational_Demand/ACTUAL_DAILY/` is the recommended dataset. It provides:
- The right metric (operational demand in MW — the demand that grid-connected generation must serve)
- Appropriate resolution (30-minute, easily aggregated to annual means)
- Complete temporal coverage with zero gaps
- Free public access with no authentication required
- Consistent formatting across the available archive

### Recommended temporal aggregation

- **Primary indicator:** Annual mean operational demand per NEM region (MW)
- **Secondary indicators:** Peak demand (annual max), seasonal mean (summer/winter), demand variability (std dev)
- **For MVP screening:** Annual mean is sufficient. It provides a stable, easily interpreted ranking of regional demand magnitude.

### Spatial allocation options (deferred to Task 5)

Regional demand must be allocated to grid cells. The main options are:
1. **Population weighting** — allocate proportionally to population density per cell (requires ABS population grid data)
2. **Load-centre proximity** — weight by inverse distance to major substations/load centres
3. **Flat allocation** — assign uniform demand across all cells in a region (simplest but least realistic)

Population weighting is the most defensible proxy and is recommended. ABS provides gridded population data (Census, Estimated Resident Population).

### Recommended years

- **Current sample:** Jul 2025 – Jun 2026 (1 year, already downloaded)
- **Target:** Extend to 3 full years (e.g. Jul 2023 – Jun 2026) by downloading earlier Archive months
- **Method:** Same download script, earlier monthly ZIPs from the Archive
- **Avoid:** 2020–2021 showed COVID-related demand suppression; recommend 2022 onwards for representativeness

### Blockers and concerns

- **No blockers.** Data is freely available, well-structured, and complete.
- **Main risk:** The spatial allocation proxy (Task 5) could be weak if population doesn't correlate well with industrial/commercial demand centres. This is inherent to working with region-level data.

### Interpretation of the demand indicator

The "demand indicator" for a grid cell tells a planner: *"How much electricity demand exists in this area that new wind generation could serve?"* Higher demand regions are generally more attractive because:
- New generation can serve local load, reducing transmission needs
- Connection to high-demand areas suggests infrastructure capacity
- Revenue potential correlates with demand proximity

It does NOT indicate:
- Actual consumption at the specific cell
- Whether local grid capacity exists to connect new generation
- Future demand growth or decline

---

## 10. Acceptance Criteria

- [x] AEMO demand data availability is fully documented (datasets, metrics, resolution, format, licence)
- [x] The most appropriate dataset for the platform is identified and justified
- [x] At least one sample dataset is downloaded and stored in `DATA/electricity-demand/`
- [x] Sample has been opened and inspected (columns, row count, regions, units, time fields, missing values)
- [x] A data dictionary is completed for the recommended demand dataset
- [x] Integration issues are identified and documented (at minimum: spatial allocation challenge, coverage gaps)
- [x] NEM coverage gap (WA, NT) is documented
- [x] Findings and recommendations section is written
- [x] Any alternative data sources discovered are noted (e.g. OpenNEM)

---

## 11. References & Links

- AEMO NEM Data: https://aemo.com.au/energy-systems/electricity/national-electricity-market-nem/data-nem
- AEMO Aggregated Data: https://aemo.com.au/energy-systems/electricity/national-electricity-market-nem/data-nem/aggregated-data
- NEMWeb Reports (direct download): https://nemweb.com.au/Reports/
- NEMWeb Archive — Operational Demand: https://nemweb.com.au/Reports/Archive/Operational_Demand/ACTUAL_DAILY/
- OpenNEM (community visualisation of AEMO data): https://opennem.org.au/
- NEM Regions Explained: https://aemo.com.au/learn/electricity-markets/national-electricity-market
- Product Knowledge Base: see `Opt-Mining - Product Knowledge Base.md`
- Inspection summary: see `DATA/electricity-demand/inspection_summary.txt`
- Download script: see `scripts/download_aemo_demand.py`
- Inspection script: see `scripts/inspect_demand_data.py`
