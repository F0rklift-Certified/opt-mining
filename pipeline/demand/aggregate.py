"""
Aggregation stage — compute annual demand summary per NEM region.

Reads the consolidated half-hourly CSV and produces a clean output CSV
with annual statistics suitable for downstream use (Task 5 spatial allocation).

Importable entry point:
    from pipelines.demand.aggregate import run
    agg_csv, meta_path = run(csv_path=Path(...), output_dir=Path(...),
                             start_date="2025-07-01", end_date="2026-06-30")

Standalone usage:
    python -m pipelines.demand.aggregate path/to/file.csv

Output:
    demand_annual_summary.csv — one row per NEM region with:
        REGIONID, MEAN_DEMAND_MW, MAX_DEMAND_MW, MIN_DEMAND_MW, STD_DEMAND_MW,
        SUMMER_MEAN_MW, WINTER_MEAN_MW, START_DATE, END_DATE

    demand_annual_summary.meta.json — provenance metadata.

Units: All demand values are in MW (megawatts).
Metric: AEMO Operational Demand — demand met by scheduled/semi-scheduled
        generation, excludes rooftop PV.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import config


# ---------------------------------------------------------------------------
# Seasonal definitions (Australian seasons, meteorological)
# ---------------------------------------------------------------------------

# Summer: December, January, February
SUMMER_MONTHS = [12, 1, 2]
# Winter: June, July, August
WINTER_MONTHS = [6, 7, 8]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(
    csv_path: Path,
    output_dir: Path,
    start_date: str,
    end_date: str,
    verbose: bool = False,
) -> tuple[Path, Path]:
    """
    Aggregate half-hourly demand data into annual per-region statistics.

    Parameters
    ----------
    csv_path : Path
        Path to the consolidated half-hourly CSV.
    output_dir : Path
        Directory for output files.
    start_date : str
        Pipeline start date (YYYY-MM-DD) — recorded in metadata.
    end_date : str
        Pipeline end date (YYYY-MM-DD) — recorded in metadata.
    verbose : bool
        Print additional detail.

    Returns
    -------
    tuple[Path, Path]
        (path to summary CSV, path to metadata JSON).
    """
    output_csv = output_dir / config.AGGREGATED_CSV_NAME
    output_meta = output_dir / config.AGGREGATED_META_NAME

    print(f"  Input: {csv_path.name}")
    print(f"  Loading...")

    df = pd.read_csv(csv_path)
    df["INTERVAL_DATETIME"] = pd.to_datetime(df["INTERVAL_DATETIME"])

    # Ensure OPERATIONAL_DEMAND is numeric
    df["OPERATIONAL_DEMAND"] = pd.to_numeric(df["OPERATIONAL_DEMAND"], errors="coerce")

    print(f"  Loaded: {len(df):,} rows, {df['REGIONID'].nunique()} regions")

    # Extract month for seasonal grouping
    df["month"] = df["INTERVAL_DATETIME"].dt.month

    # --- Compute per-region statistics ---
    records = []

    for region in sorted(df["REGIONID"].unique()):
        region_df = df[df["REGIONID"] == region]
        demand = region_df["OPERATIONAL_DEMAND"]

        # Core statistics
        mean_mw = demand.mean()
        max_mw = demand.max()
        min_mw = demand.min()
        std_mw = demand.std()

        # Seasonal means
        summer_df = region_df[region_df["month"].isin(SUMMER_MONTHS)]
        winter_df = region_df[region_df["month"].isin(WINTER_MONTHS)]

        summer_mean = summer_df["OPERATIONAL_DEMAND"].mean() if len(summer_df) > 0 else None
        winter_mean = winter_df["OPERATIONAL_DEMAND"].mean() if len(winter_df) > 0 else None

        records.append(
            {
                "REGIONID": region,
                "MEAN_DEMAND_MW": round(mean_mw, 1),
                "MAX_DEMAND_MW": round(max_mw, 1),
                "MIN_DEMAND_MW": round(min_mw, 1),
                "STD_DEMAND_MW": round(std_mw, 1),
                "SUMMER_MEAN_MW": round(summer_mean, 1) if summer_mean is not None else None,
                "WINTER_MEAN_MW": round(winter_mean, 1) if winter_mean is not None else None,
                "START_DATE": start_date,
                "END_DATE": end_date,
            }
        )

    summary_df = pd.DataFrame(records)

    # --- Write CSV ---
    summary_df.to_csv(output_csv, index=False)
    print(f"  Output CSV: {output_csv.name} ({len(summary_df)} rows)")

    if verbose:
        print(f"\n{summary_df.to_string(index=False)}")

    # --- Write provenance metadata ---
    actual_min = df["INTERVAL_DATETIME"].min().isoformat()
    actual_max = df["INTERVAL_DATETIME"].max().isoformat()

    meta = {
        "dataset": "AEMO NEM Operational Demand — Annual Summary",
        "description": (
            "Per-region annual demand statistics derived from half-hourly "
            "AEMO operational demand data. Values are in MW. "
            "These are regional aggregates, not cell-level estimates."
        ),
        "source": "https://nemweb.com.au/Reports/Archive/Operational_Demand/ACTUAL_DAILY/",
        "publisher": "Australian Energy Market Operator (AEMO)",
        "licence": "AEMO public data — free to use with attribution",
        "pipeline": "pipelines.demand (aggregate stage)",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "input_file": csv_path.name,
        "temporal_range": {"start": actual_min, "end": actual_max},
        "requested_range": {"start": start_date, "end": end_date},
        "temporal_resolution_input": "30 minutes (half-hourly)",
        "spatial_resolution": "NEM Region (5 regions: NSW1, QLD1, SA1, TAS1, VIC1)",
        "units": "MW (megawatts)",
        "metric": (
            "Operational demand — electricity demand met by scheduled, "
            "semi-scheduled and significant non-scheduled generation. "
            "Excludes behind-the-meter generation (rooftop PV)."
        ),
        "seasonal_definitions": {
            "summer": "December, January, February (Australian meteorological summer)",
            "winter": "June, July, August (Australian meteorological winter)",
        },
        "columns": {
            "REGIONID": "NEM region identifier (NSW1, QLD1, SA1, TAS1, VIC1)",
            "MEAN_DEMAND_MW": "Annual mean operational demand (MW)",
            "MAX_DEMAND_MW": "Annual maximum (peak) operational demand (MW)",
            "MIN_DEMAND_MW": "Annual minimum operational demand (MW)",
            "STD_DEMAND_MW": "Standard deviation of operational demand (MW)",
            "SUMMER_MEAN_MW": "Mean demand during summer months (Dec-Feb) (MW)",
            "WINTER_MEAN_MW": "Mean demand during winter months (Jun-Aug) (MW)",
            "START_DATE": "Requested pipeline start date",
            "END_DATE": "Requested pipeline end date",
        },
        "limitations": [
            "Regional granularity only — 5 values, not per grid cell.",
            "NEM coverage gap: Western Australia (SWIS) and NT not included.",
            "Operational demand excludes rooftop PV; actual consumption is higher.",
            "Cell-level demand indicators require spatial allocation (Task 5).",
        ],
        "downstream_use": (
            "Input to Task 5 spatial allocation. MEAN_DEMAND_MW is the primary "
            "indicator for suitability scoring. Cell-level values derived from "
            "this are estimated/proxy demand indicators, not actual local consumption."
        ),
    }

    with open(output_meta, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"  Metadata: {output_meta.name}")

    # Console summary
    print(f"\n  Annual Mean Demand by Region:")
    for _, row in summary_df.iterrows():
        print(f"    {row['REGIONID']}: {row['MEAN_DEMAND_MW']:,.1f} MW")

    return output_csv, output_meta


# ---------------------------------------------------------------------------
# Standalone execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Aggregate AEMO demand data into annual regional summary."
    )
    parser.add_argument("input_csv", type=str, help="Path to consolidated CSV.")
    parser.add_argument("--output-dir", type=str, default=None)
    parser.add_argument("--start-date", type=str, default=config.DEFAULT_START_DATE)
    parser.add_argument("--end-date", type=str, default=config.DEFAULT_END_DATE)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input_csv)
    if not input_path.exists():
        print(f"ERROR: File not found: {input_path}")
        sys.exit(1)

    out_dir = Path(args.output_dir) if args.output_dir else input_path.parent
    agg_csv, meta = run(
        csv_path=input_path,
        output_dir=out_dir,
        start_date=args.start_date,
        end_date=args.end_date,
        verbose=args.verbose,
    )
    print(f"\nDone. Output: {agg_csv}")
