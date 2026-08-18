"""Merge and inspect Geoscience Australia Power Lines GeoJSON downloads."""

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "DATA" / "infrastructure"
PARTS = [
    DATA / "transmission-lines" / "ga_power_lines_2026_part_001.geojson",
    DATA / "transmission-lines" / "ga_power_lines_2026_part_002.geojson",
]
MERGED = DATA / "transmission-lines" / "ga_power_lines_2026_australia.geojson"
NSW = DATA / "transmission-lines" / "ga_power_lines_2026_nsw.geojson"
REPORT = DATA / "metadata" / "ga_power_lines_2026_inspection.md"
PREVIEW = DATA / "metadata" / "ga_power_lines_2026_preview.svg"


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
    collections = [json.loads(path.read_text(encoding="utf-8")) for path in PARTS]
    features = [feature for collection in collections for feature in collection["features"]]
    object_ids = [feature["properties"].get("objectid") for feature in features]
    if len(object_ids) != len(set(object_ids)):
        raise RuntimeError("Duplicate OBJECTID values found across downloaded pages")

    merged = {
        "type": "FeatureCollection",
        "name": "Geoscience Australia Power Lines 2026",
        "crs": collections[0].get("crs"),
        "features": features,
    }
    MERGED.write_text(json.dumps(merged, separators=(",", ":")), encoding="utf-8")

    nsw_features = [
        feature
        for feature in features
        if str(feature["properties"].get("state", "")).strip().upper() == "NSW"
    ]
    nsw = {**merged, "name": "Geoscience Australia Power Lines 2026 — NSW"}
    nsw["features"] = nsw_features
    NSW.write_text(json.dumps(nsw, separators=(",", ":")), encoding="utf-8")

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

- Downloaded: {datetime.now(timezone.utc).date().isoformat()}
- Official service: `https://services.ga.gov.au/gis/rest/services/Electricity_Infrastructure/MapServer/2`
- Custodian: Geoscience Australia
- Attribution: © Commonwealth of Australia (Geoscience Australia) 2026
- Format: ArcGIS Feature Service downloaded as GeoJSON
- CRS: EPSG:7844 (GDA2020)
- National feature count: {len(features)}
- NSW feature count: {len(nsw_features)}
- Duplicate OBJECTIDs: {len(object_ids) - len(set(object_ids))}
- Geometry types: {dict(geometry_counts)}
- Bounds: {[round(value, 6) for value in bounds]}
- States: {dict(states)}
- Operational status values: {dict(statuses)}
- Capacity kV values: {dict(sorted(capacities.items()))}
- Missing values by field: {missing}

## Fields

{', '.join(fields)}

## Initial assessment

This national line dataset is suitable for screening-level straight-line
distance-to-transmission calculations and contains voltage, operational status,
state, revision and spatial-confidence attributes. It must not be treated as an
engineering asset register or used instead of asset-safety services. Accuracy,
completeness and currency limitations must remain visible in the final report.
"""
    REPORT.write_text(report, encoding="utf-8")

    # Create a dependency-free SVG preview. This is only visual evidence; the
    # GeoJSON remains the analysis dataset.
    width, height, margin = 1000, 760, 35
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
        stroke_width = 0.55 if voltage < 220 else 0.9
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
<text x="35" y="53" font-family="sans-serif" font-size="14">3,147 national features; colour represents nominal voltage</text>
<g>{''.join(paths)}</g>
<rect x="770" y="55" width="180" height="250" rx="6" fill="white" fill-opacity="0.9" stroke="#cccccc"/>
<g font-family="sans-serif">{''.join(legend_items)}</g>
</svg>"""
    PREVIEW.write_text(svg, encoding="utf-8")


if __name__ == "__main__":
    main()
