"""
CLI entry point for the electricity demand pipeline.

Usage:
    python -m pipelines.demand                          # run all stages
    python -m pipelines.demand --only download          # run a single stage
    python -m pipelines.demand --skip-download          # skip one stage
    python -m pipelines.demand --skip-download --skip-inspect  # skip multiple
    python -m pipelines.demand --verbose                # detailed logging
    python -m pipelines.demand --start-date 2023-07-01 --end-date 2026-06-30
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

from . import config


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="python -m pipelines.demand",
        description=(
            "AEMO NEM Operational Demand Pipeline.\n\n"
            "Downloads, validates, inspects and aggregates half-hourly demand\n"
            "data from AEMO NEMWeb into a clean annual summary for downstream use."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m pipelines.demand\n"
            "  python -m pipelines.demand --only aggregate\n"
            "  python -m pipelines.demand --skip-download --start-date 2023-07-01\n"
        ),
    )

    # Date range
    parser.add_argument(
        "--start-date",
        type=str,
        default=config.DEFAULT_START_DATE,
        help=f"Start date YYYY-MM-DD (default: {config.DEFAULT_START_DATE})",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default=config.DEFAULT_END_DATE,
        help=f"End date YYYY-MM-DD (default: {config.DEFAULT_END_DATE})",
    )

    # Stage control
    parser.add_argument(
        "--only",
        type=str,
        choices=config.STAGES,
        default=None,
        help="Run only the specified stage.",
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="Skip the download stage (use existing consolidated CSV).",
    )
    parser.add_argument(
        "--skip-validate",
        action="store_true",
        help="Skip the validation stage.",
    )
    parser.add_argument(
        "--skip-inspect",
        action="store_true",
        help="Skip the inspection stage.",
    )
    parser.add_argument(
        "--skip-aggregate",
        action="store_true",
        help="Skip the aggregation stage.",
    )

    # Input override
    parser.add_argument(
        "--input-csv",
        type=str,
        default=None,
        help=(
            "Path to an existing consolidated CSV (skips download and uses this "
            "file for validate/inspect/aggregate). Useful with --skip-download."
        ),
    )

    # Output
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help=f"Output directory (default: {config.OUTPUT_DIR})",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable detailed logging.",
    )

    return parser.parse_args()


def validate_date(date_str: str, label: str) -> str:
    """Validate a date string, return YYYYMMDD format."""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        print(f"ERROR: Invalid {label} format: '{date_str}'. Expected YYYY-MM-DD.")
        sys.exit(1)
    return dt.strftime("%Y%m%d")


def resolve_stages(args: argparse.Namespace) -> list[str]:
    """Determine which stages to run based on CLI flags."""
    if args.only:
        return [args.only]

    stages = list(config.STAGES)
    if args.skip_download:
        stages.remove("download")
    if args.skip_validate:
        stages.remove("validate")
    if args.skip_inspect:
        stages.remove("inspect")
    if args.skip_aggregate:
        stages.remove("aggregate")

    return stages


def main():
    """Orchestrate the demand pipeline."""
    args = parse_args()

    # Validate dates
    start_yyyymmdd = validate_date(args.start_date, "start-date")
    end_yyyymmdd = validate_date(args.end_date, "end-date")

    if start_yyyymmdd >= end_yyyymmdd:
        print(f"ERROR: --start-date ({args.start_date}) must be before --end-date ({args.end_date}).")
        sys.exit(1)

    # Resolve output directory
    output_dir = Path(args.output_dir) if args.output_dir else config.OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = output_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    # Determine stages to run
    stages = resolve_stages(args)

    # Determine consolidated CSV path
    if args.input_csv:
        consolidated_csv = Path(args.input_csv)
        if not consolidated_csv.is_absolute():
            consolidated_csv = Path.cwd() / consolidated_csv
        if not consolidated_csv.exists():
            print(f"ERROR: --input-csv file not found: {consolidated_csv}")
            sys.exit(1)
        csv_filename = consolidated_csv.name
    else:
        csv_filename = config.consolidated_csv_name(start_yyyymmdd, end_yyyymmdd)
        consolidated_csv = output_dir / csv_filename

    # Header
    print("=" * 70)
    print("AEMO NEM OPERATIONAL DEMAND PIPELINE")
    print("=" * 70)
    print(f"  Date range : {args.start_date} to {args.end_date}")
    print(f"  Output dir : {output_dir}")
    print(f"  Stages     : {' → '.join(stages)}")
    print(f"  CSV target : {csv_filename}")
    print("=" * 70)

    pipeline_start = time.time()
    outputs_produced = []

    # --- Stage: Download ---
    if "download" in stages:
        print(f"\n{'─' * 70}")
        print("STAGE 1/4: DOWNLOAD")
        print(f"{'─' * 70}")

        from .download import run as run_download

        try:
            consolidated_csv = run_download(
                start_date=args.start_date,
                end_date=args.end_date,
                output_dir=output_dir,
                raw_dir=raw_dir,
                verbose=args.verbose,
            )
            outputs_produced.append(("Consolidated CSV", consolidated_csv))
        except RuntimeError as e:
            print(f"\n  DOWNLOAD FAILED: {e}")
            sys.exit(1)
        except Exception as e:
            print(f"\n  DOWNLOAD ERROR (unexpected): {e}")
            sys.exit(1)
    else:
        if not consolidated_csv.exists():
            print(f"\nERROR: Download skipped but consolidated CSV not found:")
            print(f"  {consolidated_csv}")
            print("Run without --skip-download, or provide --input-csv pointing to an existing file.")
            sys.exit(1)
        print(f"\n  [skip] Download — using existing: {consolidated_csv.name}")

    # --- Stage: Validate ---
    if "validate" in stages:
        print(f"\n{'─' * 70}")
        print("STAGE 2/4: VALIDATE")
        print(f"{'─' * 70}")

        from .validate import run as run_validate

        try:
            result = run_validate(csv_path=consolidated_csv, verbose=args.verbose)
        except Exception as e:
            print(f"\n  VALIDATE ERROR: {e}")
            sys.exit(1)

        if not result.passed:
            print(f"\n  VALIDATION FAILED — pipeline halted.")
            print(f"  Failed checks:")
            for name, passed, msg in result.details:
                if not passed:
                    print(f"    - {name}: {msg.splitlines()[0]}")
            sys.exit(1)

        print(f"\n  All {len(result.details)} checks passed.")
    else:
        print(f"\n  [skip] Validate")

    # --- Stage: Inspect ---
    if "inspect" in stages:
        print(f"\n{'─' * 70}")
        print("STAGE 3/4: INSPECT")
        print(f"{'─' * 70}")

        from .inspect import run as run_inspect

        try:
            summary_path = run_inspect(
                csv_path=consolidated_csv,
                output_dir=output_dir,
                verbose=args.verbose,
            )
            outputs_produced.append(("Inspection summary", summary_path))
        except Exception as e:
            print(f"\n  INSPECT ERROR: {e}")
            sys.exit(1)
    else:
        print(f"\n  [skip] Inspect")

    # --- Stage: Aggregate ---
    if "aggregate" in stages:
        print(f"\n{'─' * 70}")
        print("STAGE 4/4: AGGREGATE")
        print(f"{'─' * 70}")

        from .aggregate import run as run_aggregate

        try:
            agg_csv, meta_path = run_aggregate(
                csv_path=consolidated_csv,
                output_dir=output_dir,
                start_date=args.start_date,
                end_date=args.end_date,
                verbose=args.verbose,
            )
            outputs_produced.append(("Annual summary CSV", agg_csv))
            outputs_produced.append(("Summary metadata", meta_path))
        except Exception as e:
            print(f"\n  AGGREGATE ERROR: {e}")
            sys.exit(1)
    else:
        print(f"\n  [skip] Aggregate")

    # --- Pipeline Summary ---
    elapsed = time.time() - pipeline_start
    print(f"\n{'=' * 70}")
    print("PIPELINE COMPLETE")
    print(f"{'=' * 70}")
    print(f"  Stages run : {' → '.join(stages)}")
    print(f"  Elapsed    : {elapsed:.1f}s")
    print(f"  Outputs:")
    for label, path in outputs_produced:
        size_kb = path.stat().st_size / 1024 if path.exists() else 0
        print(f"    • {label}: {path.name} ({size_kb:.0f} KB)")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
