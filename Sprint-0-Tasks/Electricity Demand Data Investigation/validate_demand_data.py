"""
Validate AEMO NEM Operational Demand data.

A strict pipeline gate that reads a consolidated demand CSV and performs
quality checks. Exits with code 1 if any check fails, code 0 if all pass.

Designed to be reusable: the --dataset-type flag selects validation rules
appropriate for the dataset being checked. Currently supports:
  - aemo-demand (default): AEMO NEM Operational Demand half-hourly data

Usage:
  python validate_demand_data.py aemo_operational_demand_20250701_20260630.csv
  python validate_demand_data.py --dataset-type aemo-demand path/to/file.csv

Checks performed (aemo-demand):
  1. Duplicate detection — no duplicate (REGIONID, INTERVAL_DATETIME) pairs
  2. Timestamp continuity — consecutive intervals exactly 30 min apart per region
  3. Expected interval — all intervals are 30 minutes
  4. Regional completeness — all 5 NEM regions present
  5. Numeric conversion — OPERATIONAL_DEMAND is numeric (int/float)
  6. Non-null demand — no NaN/null values in OPERATIONAL_DEMAND

Exit codes:
  0 — all checks passed
  1 — one or more checks failed
"""

import argparse
import sys
from datetime import timedelta
from pathlib import Path

import pandas as pd


# --- Validation Check Functions ---
# Each returns (passed: bool, message: str)


def check_duplicates(df: pd.DataFrame) -> tuple[bool, str]:
    """Check for duplicate (REGIONID, INTERVAL_DATETIME) pairs."""
    dupes = df.duplicated(subset=["REGIONID", "INTERVAL_DATETIME"])
    n_dupes = dupes.sum()

    if n_dupes == 0:
        return True, "No duplicate (REGIONID, INTERVAL_DATETIME) pairs found."

    # Report sample duplicates
    dupe_rows = df[dupes].head(5)
    sample_str = dupe_rows[["REGIONID", "INTERVAL_DATETIME"]].to_string(index=False)
    return False, (
        f"{n_dupes} duplicate (REGIONID, INTERVAL_DATETIME) pairs found.\n"
        f"  Sample duplicates:\n{sample_str}"
    )


def check_timestamp_continuity(df: pd.DataFrame) -> tuple[bool, str]:
    """Check that consecutive timestamps per region are exactly 30 minutes apart."""
    expected_delta = timedelta(minutes=30)
    issues = []

    for region in sorted(df["REGIONID"].unique()):
        region_df = df[df["REGIONID"] == region].sort_values("INTERVAL_DATETIME")
        diffs = region_df["INTERVAL_DATETIME"].diff().dropna()

        # Find gaps (intervals > 30 min)
        gaps = diffs[diffs > expected_delta]
        if len(gaps) > 0:
            for idx in gaps.index[:5]:  # Report up to 5 gaps per region
                row_pos = region_df.index.get_loc(idx)
                prev_ts = region_df.iloc[row_pos - 1]["INTERVAL_DATETIME"]
                curr_ts = region_df.iloc[row_pos]["INTERVAL_DATETIME"]
                gap_duration = curr_ts - prev_ts
                issues.append(
                    f"  {region}: gap of {gap_duration} between {prev_ts} and {curr_ts}"
                )
            if len(gaps) > 5:
                issues.append(f"  {region}: ... and {len(gaps) - 5} more gaps")

    if not issues:
        return True, "All timestamps are continuous (30-min intervals) across all regions."

    return False, (
        f"Timestamp continuity gaps detected:\n" + "\n".join(issues)
    )


def check_expected_interval(df: pd.DataFrame) -> tuple[bool, str]:
    """Confirm all intervals are 30 minutes (no mixed resolutions)."""
    expected_delta = timedelta(minutes=30)
    issues = []

    for region in sorted(df["REGIONID"].unique()):
        region_df = df[df["REGIONID"] == region].sort_values("INTERVAL_DATETIME")
        diffs = region_df["INTERVAL_DATETIME"].diff().dropna()

        # Find intervals that are not 30 minutes (excluding gaps already caught)
        non_standard = diffs[(diffs != expected_delta) & (diffs > timedelta(0))]
        # Filter to only those shorter than 30 min (indicating mixed resolution)
        shorter = non_standard[non_standard < expected_delta]
        if len(shorter) > 0:
            unique_intervals = shorter.unique()
            issues.append(
                f"  {region}: {len(shorter)} intervals shorter than 30 min "
                f"(found: {[str(i) for i in unique_intervals[:5]]})"
            )

    if not issues:
        return True, "All intervals are 30 minutes (no mixed resolutions detected)."

    return False, (
        f"Non-standard intervals detected:\n" + "\n".join(issues)
    )


def check_regional_completeness(df: pd.DataFrame) -> tuple[bool, str]:
    """Confirm all 5 expected NEM regions are present."""
    expected_regions = {"NSW1", "QLD1", "SA1", "TAS1", "VIC1"}
    actual_regions = set(df["REGIONID"].unique())

    missing = expected_regions - actual_regions
    unexpected = actual_regions - expected_regions

    messages = []
    if missing:
        messages.append(f"  Missing regions: {sorted(missing)}")
    if unexpected:
        messages.append(f"  Unexpected regions: {sorted(unexpected)} (not necessarily an error)")

    if not missing:
        region_counts = df["REGIONID"].value_counts()
        count_info = ", ".join(
            f"{r}: {region_counts[r]:,}" for r in sorted(expected_regions)
        )
        msg = f"All 5 NEM regions present. Row counts: {count_info}"
        if unexpected:
            msg += f"\n  Note: unexpected regions also found: {sorted(unexpected)}"
        return True, msg

    return False, (
        f"Regional completeness check failed:\n" + "\n".join(messages)
    )


def check_numeric_demand(df: pd.DataFrame) -> tuple[bool, str]:
    """Confirm OPERATIONAL_DEMAND is numeric (int/float), not string."""
    col = "OPERATIONAL_DEMAND"

    if col not in df.columns:
        return False, f"Column '{col}' not found in dataset."

    if pd.api.types.is_numeric_dtype(df[col]):
        return True, f"'{col}' is numeric (dtype: {df[col].dtype})."

    # Attempt conversion
    try:
        converted = pd.to_numeric(df[col], errors="coerce")
        n_failed = converted.isna().sum() - df[col].isna().sum()
        if n_failed == 0:
            return True, (
                f"'{col}' is stored as {df[col].dtype} but converts cleanly to numeric. "
                f"Consider converting in the download step."
            )
        else:
            # Show sample non-numeric values
            mask = pd.to_numeric(df[col], errors="coerce").isna() & df[col].notna()
            samples = df.loc[mask, col].head(5).tolist()
            return False, (
                f"'{col}' contains {n_failed} non-numeric values that cannot be converted.\n"
                f"  Sample non-numeric values: {samples}"
            )
    except Exception as e:
        return False, f"'{col}' numeric conversion failed with error: {e}"


def check_null_demand(df: pd.DataFrame) -> tuple[bool, str]:
    """Confirm no NaN/null values in OPERATIONAL_DEMAND."""
    col = "OPERATIONAL_DEMAND"

    if col not in df.columns:
        return False, f"Column '{col}' not found in dataset."

    n_null = df[col].isna().sum()
    if n_null == 0:
        return True, f"No null/NaN values in '{col}' (all {len(df):,} rows have values)."

    # Report where nulls occur
    null_rows = df[df[col].isna()]
    regions_affected = sorted(null_rows["REGIONID"].unique())
    return False, (
        f"{n_null} null/NaN values found in '{col}'.\n"
        f"  Affected regions: {regions_affected}\n"
        f"  First occurrence: row {null_rows.index[0]}"
    )


# --- Dataset-type registry ---

VALIDATION_CHECKS = {
    "aemo-demand": [
        ("Duplicate detection", check_duplicates),
        ("Timestamp continuity", check_timestamp_continuity),
        ("Expected 30-min interval", check_expected_interval),
        ("Regional completeness", check_regional_completeness),
        ("Numeric demand values", check_numeric_demand),
        ("Non-null demand values", check_null_demand),
    ],
}


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Validate demand data as a strict pipeline gate.",
        epilog=(
            "Example:\n"
            "  python validate_demand_data.py aemo_operational_demand_20250701_20260630.csv\n"
            "  python validate_demand_data.py --dataset-type aemo-demand data.csv"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "input_csv",
        type=str,
        help="Path to the consolidated CSV file to validate.",
    )
    parser.add_argument(
        "--dataset-type",
        type=str,
        default="aemo-demand",
        choices=list(VALIDATION_CHECKS.keys()),
        help="Type of dataset to validate (default: aemo-demand).",
    )
    return parser.parse_args()


def main():
    """Run validation checks and report results."""
    args = parse_args()

    input_path = Path(args.input_csv)
    if not input_path.exists():
        print(f"ERROR: Input file not found: {input_path}")
        sys.exit(1)

    dataset_type = args.dataset_type
    checks = VALIDATION_CHECKS[dataset_type]

    print("=" * 70)
    print(f"DATA VALIDATION — {dataset_type}")
    print(f"Input: {input_path}")
    print("=" * 70)

    # Load data
    print(f"\nLoading {input_path.name}...")
    df = pd.read_csv(input_path)

    # Parse datetime column if present
    if "INTERVAL_DATETIME" in df.columns:
        df["INTERVAL_DATETIME"] = pd.to_datetime(df["INTERVAL_DATETIME"])

    print(f"  Loaded: {len(df):,} rows, {df.shape[1]} columns")
    print(f"\n{'─' * 70}")
    print("VALIDATION CHECKS")
    print(f"{'─' * 70}\n")

    # Run checks
    all_passed = True
    results = []

    for check_name, check_fn in checks:
        passed, message = check_fn(df)
        status = "PASS" if passed else "FAIL"
        results.append((check_name, passed, message))

        print(f"  [{status}] {check_name}")
        # Indent the message details
        for line in message.split("\n"):
            print(f"         {line}")
        print()

        if not passed:
            all_passed = False

    # Summary
    print(f"{'─' * 70}")
    n_passed = sum(1 for _, p, _ in results if p)
    n_failed = sum(1 for _, p, _ in results if not p)

    if all_passed:
        print(f"\nRESULT: ALL CHECKS PASSED ({n_passed}/{len(results)})")
        print("=" * 70)
        sys.exit(0)
    else:
        print(f"\nRESULT: VALIDATION FAILED ({n_failed} of {len(results)} checks failed)")
        print("\nFailed checks:")
        for check_name, passed, message in results:
            if not passed:
                print(f"  - {check_name}")
        print("=" * 70)
        sys.exit(1)


if __name__ == "__main__":
    main()
