#!/usr/bin/env python3
"""
Re-freeze + re-validate runner.

After the upstream feature layers have been regenerated over full NSW (the
geographic build via ``scripts.fetch_build_geographic_nsw`` and, optionally, the
infrastructure rebuild once real connection-point geometry is wired in), the
frozen S2-02 baseline and its Validation_Result must be regenerated so the
decision service stops flagging stale missing-value counts.

This runner performs, in order:

  1. Integration (S1-08 + S1-09) — ``pipeline.integration.merge.run`` re-joins
     every current feature layer onto the grid by cell_id and re-writes
     ``DATA/integration/optmining_integrated-features_2026_nsw.gpkg``. Because the
     upstream geographic (and possibly infrastructure) layers now cover NSW, the
     integrated table's elevation_m / slope_deg / land_use (and dist_connection_km
     if wired) are populated for the newly-covered cells. Left joins never
     back-fill, so any genuinely uncovered cell stays null.

  2. Re-freeze — ``pipeline.validate.freeze_baseline(..., write=True)`` records the
     rebuilt GeoPackage's SHA-256 as the NEW frozen reference. This is required:
     the integrated file's hash changed when it was rebuilt, so without a
     re-freeze the "baseline hash matches the frozen reference" check would fail
     on a legitimately-updated dataset. The integrated dataset itself is only
     read; only the sidecar Baseline_Manifest is written.

  3. Re-validate — ``pipeline.validate.run`` re-runs the 28-check input contract
     against the rebuilt, re-frozen table and re-writes
     ``DATA/integration/metadata/integrated_input_validation.json`` — the exact
     sidecar the decision service reads verbatim for its data-quality banner
     (``pipeline.service.data_quality.get_data_quality``). When the coverage gaps
     are closed, the five missing-value checks that were failing should now pass;
     any that remain failing reflect real, still-uncovered cells (never hidden).

It prints a before/after summary of the five previously-failing missing-value
checks so you can see exactly what the fix changed.

Usage:
    python -m scripts.refreeze_revalidate
    python -m scripts.refreeze_revalidate --verbose
    python -m scripts.refreeze_revalidate --skip-integration   # re-freeze/validate only

This runner does NOT run the geographic/infrastructure rebuilds itself — run those
first (see the printed prerequisites) so each step stays inspectable.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from pipeline import validate as pipeline_validate
from pipeline.integration import merge as integration_merge

# The five columns S2-02 Check 9 flagged in the original warning.
WATCHED_COLUMNS = (
    "demand_proxy",
    "dist_connection_km",
    "elevation_m",
    "slope_deg",
    "land_use",
)


def _load_previous_missing() -> dict[str, str]:
    """Read the current (pre-run) missing-value observations, for a before/after."""
    path = Path(pipeline_validate.DEFAULT_VALIDATION_RESULT_PATH)
    if not path.exists():
        return {}
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, str] = {}
    for check in result.get("checks", []):
        name = check.get("name", "")
        if name.startswith("Missing-value count: "):
            col = name.removeprefix("Missing-value count: ")
            out[col] = check.get("observed", "?")
    return out


def _summarise_checks(checks: list[dict]) -> dict[str, tuple[str, bool]]:
    out: dict[str, tuple[str, bool]] = {}
    for check in checks:
        name = check.get("name", "")
        if name.startswith("Missing-value count: "):
            col = name.removeprefix("Missing-value count: ")
            out[col] = (check.get("observed", "?"), bool(check.get("passed")))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--skip-integration", action="store_true",
                        help="skip the S1-08 re-merge (re-freeze + re-validate only)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    before = _load_previous_missing()

    integrated_path = Path(pipeline_validate.DEFAULT_INTEGRATED_PATH)

    if not args.skip_integration:
        print("[1/3] Re-running integration (S1-08 + S1-09)...")
        integration_merge.run(verbose=args.verbose)
    else:
        print("[1/3] Skipping integration re-merge (using existing integrated table).")

    if not integrated_path.exists():
        raise SystemExit(
            f"Integrated table missing: {integrated_path}. Run integration first "
            f"(omit --skip-integration)."
        )

    print("[2/3] Re-freezing the baseline (recording the new SHA-256 reference)...")
    baseline = pipeline_validate.freeze_baseline(integrated_path, write=True)
    print(f"      frozen sha256 = {baseline['sha256']}")
    print(f"      bytes         = {baseline['bytes_human']}")

    print("[3/3] Re-validating the input contract (writes the service's sidecar)...")
    results = pipeline_validate.run(verbose=args.verbose)

    after = _summarise_checks(results.get("integrated_input_checks", []))

    print("\n=== Missing-value checks: before -> after ===")
    for col in WATCHED_COLUMNS:
        prev = before.get(col, "(not recorded)")
        now_obs, now_pass = after.get(col, ("(absent)", False))
        flag = "PASS" if now_pass else "FAIL"
        print(f"  {col:22s} {prev:>26s}  ->  {now_obs:>26s}  [{flag}]")

    all_passed = bool(results.get("all_passed"))
    sidecar = results.get("integrated_input_result")
    print(f"\nValidation_Result written: {sidecar}")
    print(f"Overall all_passed = {all_passed}")
    if all_passed:
        print("The decision service data-quality banner should now clear.")
    else:
        print(
            "Some checks still fail — this reflects real remaining gaps (e.g. cells\n"
            "still outside coverage, or dist_connection_km not yet wired to real\n"
            "geometry). Nothing was fabricated to force a pass. Review the sidecar."
        )
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
