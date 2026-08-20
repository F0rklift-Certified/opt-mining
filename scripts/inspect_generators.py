"""Inspect Geoscience Australia major power stations and isolate wind sites."""

from collections import Counter
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "DATA" / "infrastructure"
SOURCE = DATA / "generators" / "ga_powerstations_2026_australia.geojson"
WIND = DATA / "generators" / "ga_wind_generators_2026_australia.geojson"
NSW = DATA / "generators" / "ga_wind_generators_2026_nsw.geojson"
REPORT = DATA / "metadata" / "ga_generators_2026_inspection.md"


def main() -> None:
    collection = json.loads(SOURCE.read_text(encoding="utf-8"))
    features = collection["features"]
    wind_features = [
        feature
        for feature in features
        if "wind" in (
            str(feature["properties"].get("primary_fuel_type", ""))
            + " "
            + str(feature["properties"].get("technology_type", ""))
        ).lower()
    ]
    nsw_features = [
        feature
        for feature in wind_features
        if str(feature["properties"].get("state", "")).upper() == "NSW"
    ]
    for output, name, selected in (
        (WIND, "Geoscience Australia Wind Generators 2026", wind_features),
        (NSW, "Geoscience Australia Wind Generators 2026 — NSW", nsw_features),
    ):
        derived = {**collection, "name": name, "features": selected}
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(derived, separators=(",", ":")), encoding="utf-8")

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
    states = Counter(str(feature["properties"].get("state")) for feature in wind_features)
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
- Wind feature count: {len(wind_features)}
- NSW wind feature count: {len(nsw_features)}
- Valid point coordinates: {valid_coordinates}/{len(features)}
- Technology values: {dict(technologies)}
- Fuel values: {dict(fuels)}
- Generator status values: {dict(statuses)}
- Wind features by state: {dict(states)}
- Missing values by field: {missing}

## Initial assessment

The layer provides a useful public reference set for existing generation
facilities and can identify wind facilities for later validation. It includes
technology/fuel type, capacity, status and point coordinates. Point locations
may represent a facility or a generalised location, so they should validate
regional ranking rather than exact turbine siting.
"""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
