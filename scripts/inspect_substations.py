"""Inspect Geoscience Australia Substations GeoJSON and create state subset.

Usage:
  python inspect_substations.py
  python inspect_substations.py --state QLD
  python inspect_substations.py --state ALL

Options:
  --state       State filter for subset (default: NSW). Use 'ALL' to skip filtering.
  --output-dir  Output directory for filtered GeoJSON files (default: DATA/infrastructure/substations)
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
        description="Inspect Geoscience Australia Substations GeoJSON and create state subset.",
        epilog=(
            "Examples:\n"
            "  python inspect_substations.py --state QLD\n"
            "  python inspect_substations.py --state ALL"
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
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for filtered GeoJSON files (default: DATA/infrastructure/substations)",
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
    output_dir = Path(args.output_dir) if args.output_dir else DATA / "substations"
    report_dir = Path(args.report_dir) if args.report_dir else DATA / "metadata"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    # Input
    source_path = DATA / "substations" / "ga_substations_2026_australia.geojson"

    # Output paths
    state_label = args.state.lower() if args.state.upper() != "ALL" else "all"
    state_path = output_dir / f"ga_substations_2026_{state_label}.geojson"
    report_path = report_dir / "ga_substations_2026_inspection.md"

    # Load
    collection = json.loads(source_path.read_text(encoding="utf-8"))
    features = collection["features"]

    # State filter
    if args.state.upper() == "ALL":
        state_features = features
    else:
        state_features = [
            feature
            for feature in features
            if str(feature["properties"].get("state", "")).upper() == args.state.upper()
        ]

    # Write filtered output
    state_collection = {
        **collection,
        "name": f"Geoscience Australia Substations 2026 — {args.state.upper()}",
        "features": state_features,
    }
    state_path.write_text(json.dumps(state_collection, separators=(",", ":")), encoding="utf-8")

    # Inspection stats
    fields = sorted({key for feature in features for key in feature["properties"]})
    missing = {
        field: sum(
            feature["properties"].get(field) in (None, "") for feature in features
        )
        for field in fields
    }
    states = Counter(str(feature["properties"].get("state")) for feature in features)
    statuses = Counter(str(feature["properties"].get("status")) for feature in features)
    voltages = Counter(str(feature["properties"].get("voltage_kv")) for feature in features)
    geometry_types = Counter(feature.get("geometry", {}).get("type") for feature in features)
    valid_coordinates = sum(
        feature.get("geometry")
        and feature["geometry"].get("coordinates")
        and len(feature["geometry"]["coordinates"]) >= 2
        for feature in features
    )

    report = f"""# Geoscience Australia Substations 2026 — Inspection

- Source: `https://services.ga.gov.au/gis/rest/services/Electricity_Infrastructure/MapServer/0`
- Custodian: Geoscience Australia
- Attribution: © Commonwealth of Australia (Geoscience Australia) 2026
- Format: ArcGIS Feature Service downloaded as GeoJSON
- CRS: EPSG:7844 (GDA2020)
- National feature count: {len(features)}
- State filter: {args.state.upper()}
- Filtered feature count: {len(state_features)}
- Geometry types: {dict(geometry_types)}
- Valid point coordinates: {valid_coordinates}/{len(features)}
- States: {dict(states)}
- Operational status values: {dict(statuses)}
- Voltage kV values: {dict(sorted(voltages.items()))}
- Missing values by field: {missing}

## Fields

{', '.join(fields)}

## Configuration used

- State filter: {args.state}
- Output directory: {output_dir}
- Report directory: {report_dir}

## Initial assessment

This dataset is suitable for screening-level proximity to transmission
substations. It provides point coordinates, voltage, state, locality, status and
spatial-confidence fields. It is not a complete engineering connection-capacity
register: a substation's voltage does not equal spare connection capacity. The
dataset's official safety and completeness disclaimer must be retained.
"""
    report_path.write_text(report, encoding="utf-8")

    print(f"Filtered {len(state_features)} substations ({args.state.upper()}) → {state_path.name}")
    print(f"Report → {report_path.name}")


if __name__ == "__main__":
    main()
