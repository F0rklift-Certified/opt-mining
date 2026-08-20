# Electricity Demand Data Investigation

## What Was Built

A consolidated dataset of AEMO NEM operational demand at 30-minute resolution, covering one full year (July 2025 – June 2026) across all five NEM regions.

### Outputs

| File | Description | Size |
|------|-------------|------|
| `aemo_operational_demand_daily_2025.csv` | Consolidated 30-min demand for all NEM regions | 5.1 MB, ~87,600 rows |
| `raw/` | 72 original AEMO monthly/daily ZIP archives (gitignored) | 1.1 MB total |

### Consolidated CSV Schema

| Column | Type | Description |
|--------|------|-------------|
| `REGIONID` | string | NEM region identifier |
| `INTERVAL_DATETIME` | datetime | Interval end timestamp (NEM time / AEST) |
| `OPERATIONAL_DEMAND` | float | Operational demand in MW |
| `OPERATIONAL_DEMAND_ADJUSTMENT` | float | Demand adjustment in MW |
| `WDR_ESTIMATE` | float | Wholesale demand response estimate in MW |
| `LASTCHANGED` | datetime | Record last-updated timestamp |

### Coverage

- **Regions:** NSW1, QLD1, SA1, TAS1, VIC1
- **Temporal range:** 2025-07-01 to 2026-07-01
- **Resolution:** 30-minute intervals
- **Time zone:** NEM time (AEST, no daylight saving adjustment)

### Data Source

- **Publisher:** AEMO (Australian Energy Market Operator)
- **Dataset:** Actual Operational Demand — Daily
- **URL:** https://aemo.com.au/energy-systems/electricity/national-electricity-market-nem/data-nem/aggregated-data
- **Licence:** Open data (attribution to AEMO required)

### How It Was Produced

1. Downloaded 72 ZIP archives from the AEMO data portal covering July 2025 through June 2026 (monthly archives for complete months, daily archives for partial/recent periods).
2. Each monthly ZIP contains nested daily ZIPs, each containing a CSV for that day.
3. All daily CSVs were extracted and concatenated into a single consolidated file.

### Known Limitations

- **No spatial coordinates** — demand is reported at NEM region level, not lat/lon. A spatial proxy (e.g. population weighting) is needed to allocate demand to grid cells.
- **NEM coverage only** — Western Australia (SWIS) and Northern Territory are not covered by this dataset.
- **Single year** — only one year (FY25/26) is currently consolidated; the task spec recommends 3–5 years for scoring.

### Reproduction

The raw ZIPs are gitignored. To reproduce, download the monthly archives from the AEMO aggregated data page for the desired date range and re-run the extraction/concatenation process.
