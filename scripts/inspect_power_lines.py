"""Merge and inspect Geoscience Australia Power Lines GeoJSON downloads.

Usage:
  python inspect_power_lines.py
  python inspect_power_lines.py --state QLD
  python inspect_power_lines.py --state VIC --width 1200 --height 900
  python inspect_power_lines.py --voltage-threshold 132 --stroke-thin 0.3 --stroke-thick 1.2

Options:
  --state             State filter for subset (default: NSW). Use 'ALL' to skip filtering.
  --width             SVG canvas width in pixels (default: 1000)
  --height            SVG canvas height in pixels (default: 760)
  --margin            SVG canvas margin in pixels (default: 35)
  --stroke-thin       Stroke width for lines below voltage threshold (default: 0.55)
  --stroke-thick      Stroke width for lines at or above voltage threshold (default: 0.9)
  --voltage-threshold Voltage (kV) at which thick stroke kicks in (default: 220)
  --output-dir        Output directory for merged/filtered GeoJSON (default: DATA/infrastructure/transmission-lines)
  --report-dir        Output directory for inspection report and SVG (default: DATA/infrastructure/metadata)
"""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "DATA" / "infrastructure"


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Merge and inspect Geoscience Australia Power Lines GeoJSON downloads.",
        epilog=(
            "Examples:\n"
            "  python inspect_power_lines.py --state QLD\n"
            "  python inspect_power_lines.py --width 1200 --height 900\n"
            "  python inspect_power_lines.py --voltage-threshold 132 --stroke-thin 0.3"
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
        "--width",
        type=int,
        default=1000,
        help="SVG canvas width in pixels (default: 1000)",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=760,
        help="SVG canvas height in pixels (default: 760)",
    )
    parser.add_argument(
        "--margin",
        type=int,
        default=35,
        help="SVG canvas margin in pixels (default: 35)",
    )
    parser.add_argument(
        "--stroke-thin",
        type=float,
        default=0.55,
        help="Stroke width for lines below voltage threshold (default: 0.55)",
    )
    parser.add_argument(
        "--stroke-thick",
        type=float,
        default=0.9,
        help="Stroke width for lines at or above voltage threshold (default: 0.9)",
    )
    parser.add_argument(
        "--voltage-threshold",
        type=int,
        default=220,
        help="Voltage (kV) at which thick stroke is used (default: 220)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Output directory for merged/filtered GeoJSON (default: DATA/infrastructure/transmission-lines)",
    )
    parser.add_argument(
        "--report-dir",
        type=str,
        default=None,
        help="Output directory for inspection report and SVG preview (default: DATA/infrastructure/metadata)",
    )
    return parser.parse_args()


def iter_coordinates(value):
    """Yield coordinate pairs from an arbitrarily nested GeoJSON array."""
    if isinstance(value, list) and len(value) >= 2 and all(
        isinstance(item, (int, float)) for item in value[:2]
    ):
        yield value[0], value[1]
    elif isinstance(value, list):
        for item in value:
            yield from iter_coordinates(item)


def main() -> None:
    args = parse_args()

    # Resolve output directories
    output_dir = Path(args.output_dir) if args.output_dir else DATA / "transmission-lines"
    report_dir = Path(args.report_dir) if args.report_dir else DATA / "metadata"
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)

    # Input parts
    parts = [
        DATA / "transmission-lines" / "ga_power_lines_2026_part_001.geojson",
        DATA / "transmission-lines" / "ga_power_lines_2026_part_002.geojson",
    ]

    # Output paths
    merged_path = output_dir / "ga_power_lines_2026_australia.geojson"
    state_label = args.state.lower() if args.state.upper() != "ALL" else "all"
    state_path = output_dir / f"ga_power_lines_2026_{state_label}.geojson"
    report_path = report_dir / "ga_power_lines_2026_inspection.md"
    preview_path = report_dir / "ga_power_lines_2026_preview.svg"

    # Load and merge
    collections = [json.loads(path.read_text(encoding="utf-8")) for path in parts]
    features = [feature for collection in collections for feature in collection["features"]]
    object_ids = [feature["properties"].get("objectid") for feature in features]
    if len(object_ids) != len(set(object_ids)):
        raise RuntimeError("Duplicate OBJECTID values found across downloaded pages")

    MERGED.parent.mkdir(parents=True, exist_ok=True)
    NSW.parent.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    PREVIEW.parent.mkdir(parents=True, exist_ok=True)

    merged = {
        "type": "FeatureCollection",
        "name": "Geoscience Australia Power Lines 2026",
        "crs": collections[0].get("crs"),
        "features": features,
    }
    merged_path.write_text(json.dumps(merged, separators=(",", ":")), encoding="utf-8")

    # State filter
    if args.state.upper() == "ALL":
        state_features = features
    else:
        state_features = [
            feature
            for feature in features
            if str(feature["properties"].get("state", "")).strip().upper() == args.state.upper()
        ]
    state_collection = {
        **merged,
        "name": f"Geoscience Australia Power Lines 2026 — {args.state.upper()}",
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
    geometry_counts = Counter(
        feature.get("geometry", {}).get("type") if feature.get("geometry") else None
        for feature in features
    )
    states = Counter(str(feature["properties"].get("state")) for feature in features)
    statuses = Counter(
        str(feature["properties"].get("status")) for feature in features
    )
    capacities = Counter(
        str(feature["properties"].get("capacity_kv")) for feature in features
    )
    coordinates = [
        coordinate
        for feature in features
        if feature.get("geometry")
        for coordinate in iter_coordinates(feature["geometry"]["coordinates"])
    ]
    bounds = [
        min(x for x, _ in coordinates),
        min(y for _, y in coordinates),
        max(x for x, _ in coordinates),
        max(y for _, y in coordinates),
    ]

    report = f"""# Geoscience Australia Power Lines 2026 — Inspection

- Report generated: {datetime.now(timezone.utc).date().isoformat()}
- Official service: `https://services.ga.gov.au/gis/rest/services/Electricity_Infrastructure/MapServer/2`
- Custodian: Geoscience Australia
- Attribution: © Commonwealth of Australia (Geoscience Australia) 2026
- Format: ArcGIS Feature Service downloaded as GeoJSON
- CRS: EPSG:7844 (GDA2020)
- National feature count: {len(features)}
- State filter applied: {args.state.upper()}
- Filtered feature count: {len(state_features)}
- Duplicate OBJECTIDs: {len(object_ids) - len(set(object_ids))}
- Geometry types: {dict(geometry_counts)}
- Bounds: {[round(value, 6) for value in bounds]}
- States: {dict(states)}
- Operational status values: {dict(statuses)}
- Capacity kV values: {dict(sorted(capacities.items()))}
- Missing values by field: {missing}

## Fields

{', '.join(fields)}

## Configuration used

- State filter: {args.state}
- SVG dimensions: {args.width}x{args.height} (margin: {args.margin})
- Stroke thin/thick: {args.stroke_thin}/{args.stroke_thick}
- Voltage threshold: {args.voltage_threshold} kV

## Initial assessment

This national line dataset is suitable for screening-level straight-line
distance-to-transmission calculations and contains voltage, operational status,
state, revision and spatial-confidence attributes. It must not be treated as an
engineering asset register or used instead of asset-safety services. Accuracy,
completeness and currency limitations must remain visible in the final report.
"""
    report_path.write_text(report, encoding="utf-8")

    # Create SVG preview
    width, height, margin = args.width, args.height, args.margin
    min_x, min_y, max_x, max_y = bounds
    scale = min(
        (width - 2 * margin) / (max_x - min_x),
        (height - 2 * margin) / (max_y - min_y),
    )
    voltage_colours = {
        500: "#7f0000",
        400: "#b30000",
        330: "#d7301f",
        275: "#ef6548",
        220: "#fc8d59",
        132: "#3182bd",
        110: "#6baed6",
        88: "#9ecae1",
        66: "#c6dbef",
    }

    def project(x, y):
        px = margin + (x - min_x) * scale
        py = height - margin - (y - min_y) * scale
        return px, py

    paths = []
    for feature in sorted(
        features, key=lambda item: int(item["properties"].get("capacity_kv") or 0)
    ):
        voltage = int(feature["properties"].get("capacity_kv") or 0)
        colour = voltage_colours.get(voltage, "#999999")
        coordinates_for_feature = feature["geometry"]["coordinates"]
        points = [project(x, y) for x, y in coordinates_for_feature]
        path_data = " ".join(
            ("M" if index == 0 else "L") + f"{x:.2f},{y:.2f}"
            for index, (x, y) in enumerate(points)
        )
        stroke_width = args.stroke_thin if voltage < args.voltage_threshold else args.stroke_thick
        paths.append(
            f'<path d="{path_data}" fill="none" stroke="{colour}" '
            f'stroke-width="{stroke_width}" stroke-linecap="round"/>'
        )

    legend_items = []
    for index, voltage in enumerate(sorted(voltage_colours, reverse=True)):
        y = 80 + index * 24
        legend_items.append(
            f'<line x1="790" y1="{y}" x2="825" y2="{y}" '
            f'stroke="{voltage_colours[voltage]}" stroke-width="3"/>'
            f'<text x="835" y="{y + 5}" font-size="15">{voltage} kV</text>'
        )
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">
<rect width="100%" height="100%" fill="white"/>
<text x="35" y="30" font-family="sans-serif" font-size="22" font-weight="bold">Geoscience Australia Power Lines 2026</text>
<text x="35" y="53" font-family="sans-serif" font-size="14">{len(features)} national features; colour represents nominal voltage</text>
<g>{''.join(paths)}</g>
<rect x="770" y="55" width="180" height="250" rx="6" fill="white" fill-opacity="0.9" stroke="#cccccc"/>
<g font-family="sans-serif">{''.join(legend_items)}</g>
</svg>"""
    preview_path.write_text(svg, encoding="utf-8")

    print(f"Merged {len(features)} features → {merged_path.name}")
    print(f"Filtered {len(state_features)} features ({args.state.upper()}) → {state_path.name}")
    print(f"Report → {report_path.name}")
    print(f"SVG preview → {preview_path.name}")


if __name__ == "__main__":
    main()
