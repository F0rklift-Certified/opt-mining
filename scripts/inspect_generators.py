"""Inspect Geoscience Australia major power stations and isolate by fuel type.

Usage:
  python inspect_generators.py
  python inspect_generators.py --state QLD
  python inspect_generators.py --fuel-type solar
  python inspect_generators.py --fuel-type gas --state VIC

Options:
  --state       State filter for subset (default: NSW). Use 'ALL' to skip filtering.
  --fuel-type   Fuel/technology type to isolate (default: wind). Matched case-insensitively
                against primary_fuel_type and technology_type fields.
  --output-dir  Output directory for filtered GeoJSON files (default: DATA/infrastructure/generators)
  --report-dir  Output directory for inspection report (default: DATA/infrastructure/metadata)
"""

import argparse
from collections import Counter
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "DATA" / "infrastructure"


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Inspect Geoscience Australia major power stations and isolate by fuel type.",
        epilog=(
            "Examples:\n"
            "  python inspect_generators.py --state QLD\n"
            "  python inspect_generators.py --fuel-type solar\n"
            "  python inspect_generators.py --fuel-type gas --state VIC"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--state",
        type=str,
        default="NSW",
        help="State to filter for the subset file (default: NSW). Use 'ALL' to skip state filtering.",
    )
    parser.add_argument(
        "--fuel-type",
        type=str,
        default="wind",
        help=(
            "Fuel or technology type to isolate (default: wind). "
            "Matched case-insensitively against primary_fuel_type and technology_type fields. "
            "Examples: wind, solar, gas, coal, hydro, battery."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for filtered GeoJSON files (default: DATA/infrastructure/generators)",
    )
    parser.add_argument(
        "--report-dir",
        type=str,
        default=None,
        help="Output directory for inspection report (default: DATA/infrastructure/metadata)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Resolve output directories
    output_dir = Path(args.output_dir) if args.output_dir else DATA / "generators"
    report_dir = Path(args.report_dir) if args.report_dir else DATA / "metadata"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    # Input
    source_path = DATA / "generators" / "ga_powerstations_2026_australia.geojson"

    # Output paths (named by fuel type and state)
    fuel_label = args.fuel_type.lower().replace(" ", "_")
    state_label = args.state.lower() if args.state.upper() != "ALL" else "all"
    fuel_national_path = output_dir / f"ga_{fuel_label}_generators_2026_australia.geojson"
    fuel_state_path = output_dir / f"ga_{fuel_label}_generators_2026_{state_label}.geojson"
    report_path = report_dir / "ga_generators_2026_inspection.md"

    # Load
    collection = json.loads(source_path.read_text(encoding="utf-8"))
    features = collection["features"]

    # Filter by fuel/technology type
    fuel_features = [
        feature
        for feature in features
        if args.fuel_type.lower() in (
            str(feature["properties"].get("primary_fuel_type", ""))
            + " "
            + str(feature["properties"].get("technology_type", ""))
        ).lower()
    ]

    # Filter by state
    if args.state.upper() == "ALL":
        state_features = fuel_features
    else:
        state_features = [
            feature
            for feature in fuel_features
            if str(feature["properties"].get("state", "")).upper() == args.state.upper()
        ]

    # Write outputs
    for output_path, name, selected in (
        (fuel_national_path, f"Geoscience Australia {args.fuel_type.title()} Generators 2026", fuel_features),
        (fuel_state_path, f"Geoscience Australia {args.fuel_type.title()} Generators 2026 — {args.state.upper()}", state_features),
    ):
        derived = {**collection, "name": name, "features": selected}
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(derived, separators=(",", ":")), encoding="utf-8")

    # Inspection stats
    fields = sorted({key for feature in features for key in feature["properties"]})
    missing = {
        field: sum(
            feature["properties"].get(field) in (None, "") for feature in features
        )
        for field in fields
    }
    technologies = Counter(
        str(feature["properties"].get("technology_type")) for feature in features
    )
    fuels = Counter(
        str(feature["properties"].get("primary_fuel_type")) for feature in features
    )
    statuses = Counter(str(feature["properties"].get("status")) for feature in features)
    fuel_states = Counter(str(feature["properties"].get("state")) for feature in fuel_features)
    valid_coordinates = sum(
        feature.get("geometry")
        and feature["geometry"].get("coordinates")
        and len(feature["geometry"]["coordinates"]) >= 2
        for feature in features
    )

    report = f"""# Geoscience Australia Generators 2026 — Inspection

- Source: `https://services.ga.gov.au/gis/rest/services/Electricity_Infrastructure/MapServer/1`
- Custodian: Geoscience Australia
- Attribution: © Commonwealth of Australia (Geoscience Australia) 2026
- Format: ArcGIS Feature Service downloaded as GeoJSON
- CRS: EPSG:7844 (GDA2020)
- National feature count: {len(features)}
- Fuel type filter: {args.fuel_type}
- Filtered feature count (national): {len(fuel_features)}
- State filter: {args.state.upper()}
- Filtered feature count (state): {len(state_features)}
- Valid point coordinates: {valid_coordinates}/{len(features)}
- Technology values: {dict(technologies)}
- Fuel values: {dict(fuels)}
- Generator status values: {dict(statuses)}
- {args.fuel_type.title()} features by state: {dict(fuel_states)}
- Missing values by field: {missing}

## Configuration used

- Fuel type filter: {args.fuel_type}
- State filter: {args.state}
- Output directory: {output_dir}
- Report directory: {report_dir}

## Initial assessment

The layer provides a useful public reference set for existing generation
facilities and can identify {args.fuel_type} facilities for later validation. It includes
technology/fuel type, capacity, status and point coordinates. Point locations
may represent a facility or a generalised location, so they should validate
regional ranking rather than exact turbine siting.
"""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")

    print(f"National {args.fuel_type} generators: {len(fuel_features)} features → {fuel_national_path.name}")
    print(f"{args.state.upper()} {args.fuel_type} generators: {len(state_features)} features → {fuel_state_path.name}")
    print(f"Report → {report_path.name}")


if __name__ == "__main__":
    main()
