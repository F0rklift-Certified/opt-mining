# Data Provenance — AEMO NEM Operational Demand

## Dataset

| Field | Value |
|-------|-------|
| **Name** | AEMO NEM Operational Demand (Actual, Half-Hourly) |
| **Publisher** | Australian Energy Market Operator (AEMO) |
| **Source URL** | https://nemweb.com.au/Reports/Archive/Operational_Demand/ACTUAL_DAILY/ |
| **Current data URL** | https://nemweb.com.au/Reports/Current/Operational_Demand/ACTUAL_DAILY/ |
| **Format** | CSV (extracted from nested ZIP archives) |
| **Retrieval method** | `download_aemo_demand.py --start-date YYYY-MM-DD --end-date YYYY-MM-DD` |

## Temporal Coverage

| Field | Value |
|-------|-------|
| **Current sample period** | 2025-07-01 to 2026-06-30 (12 months) |
| **Temporal resolution** | 30 minutes (half-hourly; 48 intervals per day) |
| **Time zone** | NEM Time (AEST = UTC+10, no daylight saving adjustment) |
| **Extensibility** | Pipeline supports arbitrary date ranges via CLI; target is 3–5 recent complete years |

## Spatial Coverage

| Field | Value |
|-------|-------|
| **Spatial resolution** | NEM Region (5 regions) |
| **Regions covered** | NSW1, QLD1, SA1, TAS1, VIC1 |
| **Coordinate reference system** | N/A (tabular, region-level data) |

## Units

| Variable | Unit | Description |
|----------|------|-------------|
| OPERATIONAL_DEMAND | MW (megawatts) | Regional operational demand — electricity demand met by scheduled, semi-scheduled and significant non-scheduled generation |
| OPERATIONAL_DEMAND_ADJUSTMENT | MW | Manual adjustment to demand (typically 0) |
| WDR_ESTIMATE | MW | Wholesale demand response estimate |

## Licence and Attribution

AEMO publishes NEM data as public information under the National Electricity Rules. The data is:

- **Free to download** — no authentication or registration required
- **Free to use** — no commercial restrictions
- **Attribution required** — when publishing derived results, attribute to AEMO

Reference: https://aemo.com.au/energy-systems/electricity/national-electricity-market-nem/data-nem

## Assumptions

1. **Annual mean operational demand per NEM region** is used as the baseline regional demand indicator for the MVP suitability scoring model.
2. "Operational demand" is the appropriate metric for this platform because it represents the demand that grid-connected generation (including new wind) must serve.
3. Negative demand values (occurring in SA1 when distributed solar exceeds consumption) are included in aggregations as-is — they represent real grid conditions.
4. The sample period (post-2025) reflects current demand patterns without COVID-related anomalies.

## Scope and Limitations

**This data represents regional-level AEMO operational demand. It is NOT local electricity consumption at grid-cell level.**

Key limitations:

| Limitation | Impact | Resolution |
|-----------|--------|------------|
| **Regional granularity only** | 5 regional values cannot be directly assigned to ~5 km grid cells | Future cell-level demand indicators will use a spatial allocation proxy (e.g. population weighting). These are **estimated/proxy local demand values**, not actual local consumption. See Section 8 of `02-Electricity-Demand-Data-Investigation.md` for full methodology discussion. |
| **NEM coverage gap** | Western Australia (SWIS/WEM) and Northern Territory are not covered by the NEM | Accepted as an MVP limitation. WA and NT are excluded from the platform's initial coverage. Separate investigation would be required for these jurisdictions. |
| **Operational vs. total demand** | "Operational demand" excludes behind-the-meter generation (e.g. rooftop solar); actual total consumption is higher | Documented. For site suitability, operational demand is the relevant metric — it represents load that new generation can supply. |
| **Single-year sample** | One year may not capture multi-year demand trends or extremes | Pipeline is designed to extend to 3–5 years. Earlier Archive data is available. |

## Data Quality

Validation is performed by `validate_demand_data.py`, which checks:

1. No duplicate (REGIONID, INTERVAL_DATETIME) pairs
2. Timestamp continuity (consecutive 30-min intervals per region)
3. No mixed temporal resolutions
4. All 5 NEM regions present
5. OPERATIONAL_DEMAND is numeric
6. No null/NaN demand values

Current sample (Jul 2025 – Jun 2026): **all 6 checks pass**.

## Pipeline Workflow

```
1. python download_aemo_demand.py --start-date 2025-07-01 --end-date 2026-06-30
2. python validate_demand_data.py aemo_operational_demand_20250701_20260630.csv
3. python inspect_demand_data.py aemo_operational_demand_20250701_20260630.csv
```

## File Inventory

| File | Purpose |
|------|---------|
| `download_aemo_demand.py` | Downloads and consolidates raw AEMO data |
| `validate_demand_data.py` | Strict pipeline gate — validates data quality |
| `inspect_demand_data.py` | Generates statistical summary and inspection report |
| `aemo_operational_demand_*.csv` | Consolidated output (date range in filename) |
| `raw/` | Raw ZIP archives as downloaded from NEMWeb |
| `inspection_summary.txt` | Output of the inspection script |
| `02-Electricity-Demand-Data-Investigation.md` | Full investigation documentation |

## Version History

| Date | Change |
|------|--------|
| 2026-08-15 | Added configurable date range, validation script, provenance documentation |
| 2026-08-01 | Initial Sprint 0 investigation — single year sample (Jul 2025 – Jun 2026) |
