# Task 2 — Electricity Demand Data Investigation

**Sprint:** 0 (Week 1)
**Assignee:** _[Name]_
**Status:** Not Started
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
- [ ] Identify what demand datasets AEMO publishes (aggregated price and demand, operational demand, forecast demand, etc.)
- [ ] Determine which dataset is most appropriate for historical demand analysis
- [ ] Check whether data is freely downloadable or requires registration/API access
- [ ] Record licensing and usage restrictions (attribution, commercial use)
- [ ] Identify the AEMO data portal and navigation path to reach the demand data

### Temporal Properties
- [ ] Determine the temporal granularity (5-minute, 30-minute, daily, monthly, annual)
- [ ] Identify the available date range (how far back does data go?)
- [ ] Confirm that 3–5 recent complete years are available (e.g. 2019–2023 or 2020–2024)
- [ ] Check whether data is provided in a single file or split by year/month/region

### Spatial / Regional Properties
- [ ] Identify what regions are covered (NEM regions: NSW1, QLD1, SA1, TAS1, VIC1)
- [ ] Determine whether sub-regional breakdowns exist (e.g. by zone, by connection point)
- [ ] Check whether Western Australia (SWIS) or Northern Territory data is available separately
- [ ] Note that NEM does not cover WA or NT — document this coverage gap

### Variables & Metrics
- [ ] Identify what demand metrics are available:
  - [ ] Total demand (MW)
  - [ ] Operational demand
  - [ ] Scheduled demand
  - [ ] Maximum demand
  - [ ] Minimum demand
  - [ ] Average demand
- [ ] Determine units (MW, MWh, GWh?)
- [ ] Identify whether generation data is co-located with demand data
- [ ] Check whether price data is bundled (useful context but not primary)

### Format & Structure
- [ ] Identify file formats available (CSV, Excel, API/JSON, etc.)
- [ ] Determine file sizes for multi-year downloads
- [ ] Check column naming conventions and consistency across years
- [ ] Identify any data quality notes or caveats published by AEMO

### Sample Download
- [ ] Download a manageable sample (e.g. one full recent year for all NEM regions)
- [ ] If data is very large at 5-minute resolution, also try monthly aggregated data
- [ ] Store samples in `DATA/electricity-demand/` with a clear naming convention

---

## 4. Data Sources Investigated

| Source Name | URL | Format(s) | Licence | Download Available? | Notes |
|-------------|-----|-----------|---------|---------------------|-------|
| AEMO — Aggregated Price and Demand | https://aemo.com.au/energy-systems/electricity/national-electricity-market-nem/data-nem/aggregated-data | | | | |
| AEMO — Operational Demand | | | | | |
| AEMO — Data Dashboard | https://aemo.com.au/energy-systems/electricity/national-electricity-market-nem/data-nem | | | | |
| | | | | | |

*If you find alternative or supplementary demand datasets (e.g. OpenNEM, state-level distributors), record them here.*

---

## 5. Sample Data Downloaded

| File Name | Source | Size | Spatial Coverage | Temporal Coverage | Location in Repo |
|-----------|--------|------|------------------|-------------------|------------------|
|           |        |      |                  |                   | `DATA/electricity-demand/` |

---

## 6. Data Inspection Summary

*Open each downloaded sample and record:*

| Dataset | Columns/Variables | Row Count | Missing Values | Region Fields | Units | Date/Time Fields | Usable? |
|---------|-------------------|-----------|----------------|---------------|-------|------------------|---------|
|         |                   |           |                |               |       |                  |         |

**For demand data specifically, also record:**
- Temporal resolution (interval length):
- Time zone used (UTC? AEST? NEM time?):
- Region naming convention:
- Are there header rows or metadata rows to skip?
- Does the file have consistent formatting across all years?

---

## 7. Data Dictionary

**Dataset:** AEMO NEM — [Specific Dataset Name]
**Source:** [URL]
**Format:** [CSV / Excel / etc.]
**CRS:** N/A (tabular, region-level)
**Temporal Range:** [Start date – End date]
**Temporal Resolution:** [5-min / 30-min / daily / monthly]
**Spatial Resolution:** NEM Region (NSW1, QLD1, SA1, TAS1, VIC1)

| Field/Column Name | Data Type | Units | Description | Example Value | Missing Values? |
|-------------------|-----------|-------|-------------|---------------|-----------------|
| REGION | string | — | NEM region identifier | NSW1 | |
| SETTLEMENTDATE | datetime | — | Interval end timestamp | 2023-01-01 00:30:00 | |
| TOTALDEMAND | float | MW | Total region demand | 8542.3 | |
| RRP | float | $/MWh | Regional reference price | 85.42 | |
| | | | | | |

*Note: Column names above are indicative based on known AEMO formats. Update with actual column names from downloaded data.*

---

## 8. Integration Issues Identified

| Issue | Description | Severity (High/Med/Low) | Suggested Resolution | Resolved? |
|-------|-------------|-------------------------|----------------------|-----------|
| No spatial coordinates | Demand data is at NEM region level, not lat/lon | High | Need spatial proxy (population, load centres) to allocate to grid cells | No |
| Coverage gap | NEM does not cover WA or NT | Med | Document as limitation; investigate SWIS data separately if needed | No |
| Temporal granularity | 5-min data for 5 years = millions of rows | Med | Aggregate to monthly/annual means for screening; retain granular for later | No |
| Time zone | AEMO uses NEM time (AEST, no daylight saving) | Low | Document and standardise | No |
| | | | | |

*Also consider:*
- How will regional demand translate to per-cell values? (This is the demand allocation problem)
- Is the region naming consistent with other datasets (e.g. infrastructure data)?
- Are there anomalous periods (COVID demand drops, extreme events) that should be handled?
- Does demand data align temporally with wind resource data (which may be a long-term mean)?

---

## 9. Key Findings & Recommendations

*After completing the investigation, summarise:*

- Which AEMO dataset is most appropriate for the demand criterion?
- What temporal aggregation is recommended (annual mean, seasonal, peak demand)?
- What are the options for spatial allocation of regional demand to grid cells?
- Is population data needed as a proxy? If so, where can it be sourced?
- What years should be used (recommend 3–5 recent complete years)?
- Are there any blockers or concerns?
- How should the "demand indicator" be interpreted — what does it actually tell a planner?

---

## 10. Acceptance Criteria

- [ ] AEMO demand data availability is fully documented (datasets, metrics, resolution, format, licence)
- [ ] The most appropriate dataset for the platform is identified and justified
- [ ] At least one sample dataset is downloaded and stored in `DATA/electricity-demand/`
- [ ] Sample has been opened and inspected (columns, row count, regions, units, time fields, missing values)
- [ ] A data dictionary is completed for the recommended demand dataset
- [ ] Integration issues are identified and documented (at minimum: spatial allocation challenge, coverage gaps)
- [ ] NEM coverage gap (WA, NT) is documented
- [ ] Findings and recommendations section is written
- [ ] Any alternative data sources discovered are noted (e.g. OpenNEM)

---

## 11. References & Links

- AEMO NEM Data: https://aemo.com.au/energy-systems/electricity/national-electricity-market-nem/data-nem
- AEMO Aggregated Data: https://aemo.com.au/energy-systems/electricity/national-electricity-market-nem/data-nem/aggregated-data
- OpenNEM (community visualisation of AEMO data): https://opennem.org.au/
- NEM Regions Explained: https://aemo.com.au/learn/electricity-markets/national-electricity-market
- Product Knowledge Base: see `Opt-Mining - Product Knowledge Base.md`
