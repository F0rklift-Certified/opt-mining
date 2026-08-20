"""
Validation stage — strict pipeline gate for AEMO demand data.

Reads a consolidated demand CSV and performs quality checks.
Returns a result object indicating pass/fail; the orchestrator decides
whether to halt.

Importable entry point:
    from pipelines.demand.validate import run
    result = run(csv_path=Path(...))
    if not result.passed:
        ...

Standalone usage:
    python -m pipelines.demand.validate path/to/file.csv

Checks performed:
    1. Duplicate detection — no duplicate (REGIONID, INTERVAL_DATETIME) pairs
    2. Timestamp continuity — consecutive intervals exactly 30 min apart per region
    3. Expected interval — all intervals are 30 minutes (no mixed resolutions)
    4. Regional completeness — all 5 NEM regions present
    5. Numeric demand — OPERATIONAL_DEMAND is numeric (int/float)
    6. Non-null demand — no NaN/null values in OPERATIONAL_DEMAND
"""

import argparse
import sys
from dataclasses import dataclass, field
from datetime import timedelta
from pathlib import Path

import pandas as pd

from . import config


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    """Outcome of the validation stage."""

    passed: bool
    details: list[tuple[str, bool, str]] = field(default_factory=list)
    """List of (check_name, passed, message) tuples."""


# ---------------------------------------------------------------------------
# Individual check functions
# Each returns (passed: bool, message: str)
# ---------------------------------------------------------------------------


def check_duplicates(df: pd.DataFrame) -> tuple[bool, str]:
    """Check for duplicate (REGIONID, INTERVAL_DATETIME) pairs."""
    dupes = df.duplicated(subset=["REGIONID", "INTERVAL_DATETIME"])
    n_dupes = dupes.sum()

    if n_dupes == 0:
        return True, "No duplicate (REGIONID, INTERVAL_DATETIME) pairs found."

    dupe_rows = df[dupes].head(5)
    sample_str = dupe_rows[["REGIONID", "INTERVAL_DATETIME"]].to_string(index=False)
    return False, (
        f"{n_dupes} duplicate (REGIONID, INTERVAL_DATETIME) pairs found.\n"
        f"  Sample duplicates:\n{sample_str}"
    )


def check_timestamp_continuity(df: pd.DataFrame) -> tuple[bool, str]:
    """Check that consecutive timestamps per region are exactly 30 min apart."""
    expected_delta = timedelta(minutes=30)
    issues = []

    for region in sorted(df["REGIONID"].unique()):
        region_df = df[df["REGIONID"] == region].sort_values("INTERVAL_DATETIME")
        diffs = region_df["INTERVAL_DATETIME"].diff().dropna()

        gaps = diffs[diffs > expected_delta]
        if len(gaps) > 0:
            for idx in gaps.index[:5]:
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

    return False, f"Timestamp continuity gaps detected:\n" + "\n".join(issues)


def check_expected_interval(df: pd.DataFrame) -> tuple[bool, str]:
    """Confirm all intervals are 30 minutes (no mixed resolutions)."""
    expected_delta = timedelta(minutes=30)
    issues = []

    for region in sorted(df["REGIONID"].unique()):
        region_df = df[df["REGIONID"] == region].sort_values("INTERVAL_DATETIME")
        diffs = region_df["INTERVAL_DATETIME"].diff().dropna()

        shorter = diffs[(diffs != expected_delta) & (diffs > timedelta(0)) & (diffs < expected_delta)]
        if len(shorter) > 0:
            unique_intervals = shorter.unique()
            issues.append(
                f"  {region}: {len(shorter)} intervals shorter than 30 min "
                f"(found: {[str(i) for i in unique_intervals[:5]]})"
            )

    if not issues:
        return True, "All intervals are 30 minutes (no mixed resolutions detected)."

    return False, f"Non-standard intervals detected:\n" + "\n".join(issues)


def check_regional_completeness(df: pd.DataFrame) -> tuple[bool, str]:
    """Confirm all 5 expected NEM regions are present."""
    expected_regions = set(config.NEM_REGIONS)
    actual_regions = set(df["REGIONID"].unique())

    missing = expected_regions - actual_regions
    unexpected = actual_regions - expected_regions

    if not missing:
        region_counts = df["REGIONID"].value_counts()
        count_info = ", ".join(
            f"{r}: {region_counts[r]:,}" for r in sorted(expected_regions)
        )
        msg = f"All 5 NEM regions present. Row counts: {count_info}"
        if unexpected:
            msg += f"\n  Note: unexpected regions also found: {sorted(unexpected)}"
        return True, msg

    messages = []
    if missing:
        messages.append(f"  Missing regions: {sorted(missing)}")
    if unexpected:
        messages.append(f"  Unexpected regions: {sorted(unexpected)}")

    return False, f"Regional completeness check failed:\n" + "\n".join(messages)


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

    null_rows = df[df[col].isna()]
    regions_affected = sorted(null_rows["REGIONID"].unique())
    return False, (
        f"{n_null} null/NaN values found in '{col}'.\n"
        f"  Affected regions: {regions_affected}\n"
        f"  First occurrence: row {null_rows.index[0]}"
    )


# ---------------------------------------------------------------------------
# Check registry
# ---------------------------------------------------------------------------

CHECKS = [
    ("Duplicate detection", check_duplicates),
    ("Timestamp continuity", check_timestamp_continuity),
    ("Expected 30-min interval", check_expected_interval),
    ("Regional completeness", check_regional_completeness),
    ("Numeric demand values", check_numeric_demand),
    ("Non-null demand values", check_null_demand),
]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(csv_path: Path, verbose: bool = False) -> ValidationResult:
    """
    Run all validation checks against the consolidated demand CSV.

    Parameters
    ----------
    csv_path : Path
        Path to the consolidated CSV file.
    verbose : bool
        Print detailed check output.

    Returns
    -------
    ValidationResult
        Object with .passed (bool) and .details (list of check results).
    """
    print(f"  Input: {csv_path.name}")
    print(f"  Loading...")

    df = pd.read_csv(csv_path)

    if "INTERVAL_DATETIME" in df.columns:
        df["INTERVAL_DATETIME"] = pd.to_datetime(df["INTERVAL_DATETIME"])

    print(f"  Loaded: {len(df):,} rows, {df.shape[1]} columns\n")

    details: list[tuple[str, bool, str]] = []
    all_passed = True

    for check_name, check_fn in CHECKS:
        passed, message = check_fn(df)
        details.append((check_name, passed, message))

        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {check_name}")
        if verbose or not passed:
            for line in message.split("\n"):
                print(f"         {line}")

        if not passed:
            all_passed = False

    return ValidationResult(passed=all_passed, details=details)


# ---------------------------------------------------------------------------
# Standalone execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Validate AEMO demand data (pipeline gate).")
    parser.add_argument("input_csv", type=str, help="Path to consolidated CSV.")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    input_path = Path(args.input_csv)
    if not input_path.exists():
        print(f"ERROR: File not found: {input_path}")
        sys.exit(1)

    result = run(csv_path=input_path, verbose=args.verbose)

    n_passed = sum(1 for _, p, _ in result.details if p)
    n_total = len(result.details)

    if result.passed:
        print(f"\n  RESULT: ALL CHECKS PASSED ({n_passed}/{n_total})")
        sys.exit(0)
    else:
        n_failed = n_total - n_passed
        print(f"\n  RESULT: VALIDATION FAILED ({n_failed} of {n_total} checks failed)")
        sys.exit(1)
