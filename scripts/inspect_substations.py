"""Inspect Geoscience Australia Substations GeoJSON and create NSW sample."""

from collections import Counter
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "DATA" / "infrastructure"
SOURCE = DATA / "substations" / "ga_substations_2026_australia.geojson"
NSW = DATA / "substations" / "ga_substations_2026_nsw.geojson"
REPORT = DATA / "metadata" / "ga_substations_2026_inspection.md"


def main() -> None:
    collection = json.loads(SOURCE.read_text(encoding="utf-8"))
    features = collection["features"]
    nsw_features = [
        feature
        for feature in features
        if str(feature["properties"].get("state", "")).upper() == "NSW"
    ]
    nsw = {**collection, "name": "Geoscience Australia Substations 2026 — NSW"}
    nsw["features"] = nsw_features
    NSW.write_text(json.dumps(nsw, separators=(",", ":")), encoding="utf-8")

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
- NSW feature count: {len(nsw_features)}
- Geometry types: {dict(geometry_types)}
- Valid point coordinates: {valid_coordinates}/{len(features)}
- States: {dict(states)}
- Operational status values: {dict(statuses)}
- Voltage kV values: {dict(sorted(voltages.items()))}
- Missing values by field: {missing}

## Fields

{', '.join(fields)}

## Initial assessment

This dataset is suitable for screening-level proximity to transmission
substations. It provides point coordinates, voltage, state, locality, status and
spatial-confidence fields. It is not a complete engineering connection-capacity
register: a substation's voltage does not equal spare connection capacity. The
dataset's official safety and completeness disclaimer must be retained.
"""
    REPORT.write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
