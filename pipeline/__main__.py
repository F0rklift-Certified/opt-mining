"""
CLI entry point for the data pipeline.

Runs domain subpackages sequentially:
  wind → geographic → infrastructure → demand → grid → feature layers → exclusions → integration → validate

Usage:
    python -m pipeline                          # run all stages
    python -m pipeline --only wind              # run one domain
    python -m pipeline --only wind.probe        # run a single stage
    python -m pipeline --skip wind              # skip a domain
    python -m pipeline --skip-validate          # skip cross-domain checks
    python -m pipeline --verbose                # detailed logging
    python -m pipeline --bbox 150.0,-31.5,152.0,-29.5 --area-name my-area
"""

import argparse
import sys
import time
from pathlib import Path

from . import config


# ---------------------------------------------------------------------------
# Stage registry — maps stage keys to (import_path, runner_kwargs_fn)
# ---------------------------------------------------------------------------

def _get_runner(stage: str):
    """Lazy-import and return the run() function for a stage."""
    if stage == "wind.probe":
        from .wind.probe import run
        return run
    elif stage == "wind.download":
        from .wind.download import run
        return run
    elif stage == "wind.inspect":
        from .wind.inspect import run
        return run
    elif stage == "wind.validate":
        from .wind.validate import run
        return run
    elif stage == "wind.analyse":
        from .wind.analyse import run
        return run
    elif stage == "geographic.probe":
        from .geographic.probe import run
        return run
    elif stage == "geographic.download":
        from .geographic.download import run
        return run
    elif stage == "geographic.inspect":
        from .geographic.inspect import run
        return run
    elif stage == "geographic.derive":
        from .geographic.derive import run
        return run
    elif stage == "geographic.validate":
        from .geographic.validate import run
        return run
    elif stage == "infrastructure.download":
        from .infrastructure.download import run
        return run
    elif stage == "infrastructure.inspect":
        from .infrastructure.inspect import run
        return run
    elif stage == "demand":
        return None  # handled specially
    elif stage == "grid":
        from .grid.generate import run
        return run
    elif stage == "wind.features":
        from .wind.features import run
        return run
    elif stage == "demand.feature":
        from .demand.feature import run
        return run
    elif stage == "infrastructure.features":
        from .infrastructure.features import run
        return run
    elif stage == "geographic.features":
        from .geographic.features import run
        return run
    elif stage == "exclusions":
        from .exclusions.apply import run
        return run
    elif stage == "integration":
        from .integration.merge import run
        return run
    elif stage == "validate":
        from .validate import run
        return run
    else:
        raise ValueError(f"Unknown stage: {stage}")


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def _projected_crs_arg(value: str) -> str:
    """Argparse validator for CRS values used in metre-based distances."""
    from pyproj import CRS

    try:
        crs = CRS.from_user_input(value)
    except Exception as exc:
        raise argparse.ArgumentTypeError(f"Invalid CRS {value!r}: {exc}") from exc
    if not crs.is_projected:
        raise argparse.ArgumentTypeError(
            f"--infra-features-crs must be projected for metre distances (got {value!r})"
        )
    return value


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="python -m pipeline",
        description=(
            "Opt-Mining Data Pipeline — Wind, Geographic, Infrastructure & Demand.\n\n"
            "Runs domain subpackages sequentially:\n"
            "  wind → geographic → infrastructure → demand → grid → feature layers → exclusions → integration → cross-domain validate"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python -m pipeline\n"
            "  python -m pipeline --only wind\n"
            "  python -m pipeline --only integration\n"
            "  python -m pipeline --only integration --confidence-weights my_weights.yaml\n"
            "  python -m pipeline --only wind.probe\n"
            "  python -m pipeline --skip infrastructure\n"
            "  python -m pipeline --skip-validate\n"
            "  python -m pipeline --bbox 150.0,-31.5,152.0,-29.5\n"
        ),
    )

    # Study area
    parser.add_argument(
        "--bbox",
        type=str,
        default=",".join(str(v) for v in config.DEFAULT_BBOX),
        help=(
            f"Study window as W,S,E,N in EPSG:4326 "
            f"(default: {','.join(str(v) for v in config.DEFAULT_BBOX)})"
        ),
    )
    parser.add_argument(
        "--area-name",
        type=str,
        default=config.DEFAULT_AREA,
        help=f"Short slug for file names (default: {config.DEFAULT_AREA})",
    )

    # Stage control
    parser.add_argument(
        "--only",
        type=str,
        default=None,
        help=(
            "Run only the specified domain or stage. "
            "Examples: 'wind', 'geographic.derive', 'demand', 'infrastructure.features', "
            "'integration', 'validate'"
        ),
    )
    parser.add_argument(
        "--skip",
        type=str,
        action="append",
        default=[],
        help=(
            "Skip a domain or stage (repeatable). "
            "Examples: --skip infrastructure --skip demand"
        ),
    )
    parser.add_argument(
        "--skip-validate",
        action="store_true",
        help="Skip the cross-domain validation stage.",
    )

    # Demand options
    parser.add_argument(
        "--start-date",
        type=str,
        default="2025-07-01",
        help="Start date for demand data YYYY-MM-DD (default: 2025-07-01)",
    )
    parser.add_argument(
        "--end-date",
        type=str,
        default="2026-06-30",
        help="End date for demand data YYYY-MM-DD (default: 2026-06-30)",
    )
    parser.add_argument(
        "--regions",
        type=str,
        default=None,
        help=(
            "Comma-separated NEM region IDs for demand analysis "
            "(default: all 5 — NSW1,QLD1,SA1,TAS1,VIC1)"
        ),
    )
    parser.add_argument(
        "--allocation-method",
        type=str,
        default="uniform",
        choices=["uniform"],
        help="Demand allocation method for demand.feature (default: uniform)",
    )

    # Wind options
    parser.add_argument(
        "--heights",
        type=str,
        default=None,
        help=(
            "Comma-separated hub heights in metres for wind-speed downloads "
            "(default: 50,100,150)"
        ),
    )
    parser.add_argument(
        "--turbine-class",
        type=str,
        default=None,
        help=(
            "Comma-separated IEC turbine classes for capacity-factor layers "
            "(default: IEC2). Valid: IEC1, IEC2, IEC3"
        ),
    )
    parser.add_argument(
        "--agg-factor",
        type=int,
        default=None,
        help=(
            "Aggregation factor: native GWA pixels per analysis cell side. "
            "20 = ~5 km cells (default: 20)"
        ),
    )

    # Infrastructure options
    parser.add_argument(
        "--state",
        type=str,
        default="NSW",
        help="State filter for infrastructure inspection (default: NSW)",
    )
    parser.add_argument(
        "--infra-features-crs",
        type=_projected_crs_arg,
        default="EPSG:3577",
        help="Projected CRS for infrastructure distances (default: EPSG:3577)",
    )
    parser.add_argument(
        "--fuel-type",
        type=str,
        default="wind",
        help="Fuel type for generator inspection (default: wind)",
    )

    # Validation options
    parser.add_argument(
        "--prototype-path",
        type=str,
        default=None,
        help="Path to OptMining prototype for crosscheck (skips gracefully if absent)",
    )
    parser.add_argument(
        "--skip-land-sea",
        action="store_true",
        help="Skip the land/sea check in validate (requires network access)",
    )
    parser.add_argument(
        "--max-slope",
        type=float,
        default=15.0,
        help=(
            "Maximum allowable slope in degrees for wind farm siting checks "
            "(default: 15.0)"
        ),
    )

    # Exclusion layer options
    parser.add_argument(
        "--exclusion-rules",
        type=str,
        default=None,
        help=(
            "Path to a custom exclusion rules YAML for the 'exclusions' stage "
            "(default: pipeline/exclusions/exclusion_rules.yaml)"
        ),
    )
    parser.add_argument(
        "--confidence-weights",
        type=str,
        default=None,
        help=(
            "Path to a custom confidence weights YAML for the 'integration' stage "
            "(S1-09; default: pipeline/integration/confidence_weights.yaml)"
        ),
    )

    # Output
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable detailed logging.",
    )

    return parser.parse_args()


# ---------------------------------------------------------------------------
# Stage resolution
# ---------------------------------------------------------------------------


def resolve_stages(args: argparse.Namespace) -> list[str]:
    """Determine which stages to run based on CLI flags."""
    all_stages = list(config.STAGES)

    # --only: filter to a domain or a single stage
    if args.only:
        only = args.only
        if only in config.DOMAINS:
            # Run all stages for that domain
            all_stages = [s for s in all_stages if s.startswith(only + ".") or s == only]
        elif only in all_stages:
            all_stages = [only]
        elif only == "validate":
            all_stages = ["validate"]
        else:
            print(f"ERROR: --only '{only}' is not a valid domain or stage.")
            print(f"  Domains: {', '.join(config.DOMAINS)}")
            print(f"  Stages: {', '.join(config.STAGES)}")
            sys.exit(1)

    # --skip: remove domains or stages
    for skip in args.skip:
        if skip in config.DOMAINS:
            all_stages = [s for s in all_stages if not s.startswith(skip + ".") and s != skip]
        elif skip in all_stages:
            all_stages = [s for s in all_stages if s != skip]
        else:
            print(f"WARNING: --skip '{skip}' did not match any domain or stage (ignored).")

    # --skip-validate
    if args.skip_validate:
        all_stages = [s for s in all_stages if s != "validate"]

    return all_stages


# ---------------------------------------------------------------------------
# Stage execution
# ---------------------------------------------------------------------------


def _build_kwargs(stage: str, args: argparse.Namespace, bbox: tuple) -> dict:
    """Build the keyword arguments for a stage's run() function."""
    kwargs: dict = {"verbose": args.verbose}

    if stage in ("wind.download", "geographic.download"):
        kwargs["bbox"] = bbox
        kwargs["area_name"] = args.area_name

    if stage == "wind.download":
        # Parse heights
        if args.heights:
            kwargs["heights"] = [int(h.strip()) for h in args.heights.split(",")]
        # Parse turbine classes
        if args.turbine_class:
            kwargs["turbine_classes"] = [
                tc.strip().upper() for tc in args.turbine_class.split(",")
            ]

    if stage == "wind.analyse":
        if args.agg_factor is not None:
            kwargs["agg_factor"] = args.agg_factor

    if stage == "wind.validate":
        kwargs["prototype_path"] = Path(args.prototype_path) if args.prototype_path else None
        kwargs["skip_land_sea"] = args.skip_land_sea

    if stage == "infrastructure.inspect":
        kwargs["state"] = args.state
        kwargs["fuel_type"] = args.fuel_type

    if stage == "validate":
        kwargs["skip_land_sea"] = args.skip_land_sea
        kwargs["max_slope"] = args.max_slope

    if stage == "demand.feature":
        kwargs["allocation_method"] = args.allocation_method
    if stage == "infrastructure.features":
        kwargs["state"] = args.state
        kwargs["computation_crs"] = args.infra_features_crs
    if stage == "exclusions":
        if args.exclusion_rules:
            kwargs["rules_path"] = Path(args.exclusion_rules)
    if stage == "integration" and args.confidence_weights:
        kwargs["weights_path"] = Path(args.confidence_weights)

    return kwargs


def _run_demand(args: argparse.Namespace) -> None:
    """Run the demand sub-pipeline."""
    from .demand.__main__ import main as demand_main_fn

    original_argv = sys.argv
    demand_args = ["python -m pipeline.demand"]
    demand_args += ["--start-date", args.start_date, "--end-date", args.end_date]
    if args.regions:
        demand_args += ["--regions", args.regions]
    if args.verbose:
        demand_args.append("--verbose")

    try:
        sys.argv = demand_args
        demand_main_fn()
    except SystemExit as e:
        if e.code and e.code != 0:
            raise RuntimeError(f"Demand pipeline exited with code {e.code}")
    finally:
        sys.argv = original_argv


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    """Orchestrate the data pipeline."""
    args = parse_args()

    # Parse bbox
    try:
        bbox = tuple(float(v) for v in args.bbox.split(","))
        if len(bbox) != 4:
            raise ValueError
    except ValueError:
        print(f"ERROR: --bbox must be W,S,E,N (got '{args.bbox}')")
        sys.exit(1)

    # Determine stages
    stages = resolve_stages(args)
    if not stages:
        print("No stages to run.")
        sys.exit(0)

    # Header
    print("=" * 70)
    print("OPT-MINING DATA PIPELINE")
    print("=" * 70)
    print(f"  Study area : {args.area_name}")
    print(f"  Bbox       : {bbox}")
    print(f"  Stages     : {' → '.join(stages)}")
    print(f"  State      : {args.state}")
    print(f"  Fuel type  : {args.fuel_type}")
    print(f"  Heights    : {args.heights or '50,100,150 (default)'}")
    print(f"  Turbine    : {args.turbine_class or 'IEC2 (default)'}")
    print(f"  Agg factor : {args.agg_factor or '20 (default)'}")
    print(f"  Max slope  : {args.max_slope}°")
    print(f"  Regions    : {args.regions or 'all (NSW1,QLD1,SA1,TAS1,VIC1)'}")
    print("=" * 70)

    pipeline_start = time.time()
    stage_times: list[tuple[str, float]] = []

    for i, stage in enumerate(stages, 1):
        print(f"\n{'─' * 70}")
        print(f"STAGE {i}/{len(stages)}: {stage.upper()}")
        print(f"{'─' * 70}")
        t0 = time.time()

        try:
            if stage == "demand":
                _run_demand(args)
            else:
                runner = _get_runner(stage)
                kwargs = _build_kwargs(stage, args, bbox)
                runner(**kwargs)
        except Exception as e:
            print(f"\n  {stage.upper()} ERROR: {e}")
            sys.exit(1)

        stage_times.append((stage, time.time() - t0))

    # --- Pipeline Summary ---
    elapsed = time.time() - pipeline_start
    print(f"\n{'=' * 70}")
    print("PIPELINE COMPLETE")
    print(f"{'=' * 70}")
    print(f"  Stages run : {' → '.join(stages)}")
    print(f"  Elapsed    : {elapsed:.1f}s")
    if stage_times:
        print(f"  Timings:")
        for name, dt in stage_times:
            print(f"    • {name}: {dt:.1f}s")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
