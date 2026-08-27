"""
Shared helpers for infrastructure data inspection.

The three GA Electricity Infrastructure layers (transmission lines,
substations, generators) follow an identical load -> filter -> stats -> report
pattern. This module extracts that shared logic so the inspect stage can
handle all three without duplicating code.

Source: https://services.ga.gov.au/gis/rest/services/Electricity_Infrastructure/MapServer
Licence: (c) Commonwealth of Australia (Geoscience Australia) 2026
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_geojson(path: Path) -> dict:
    """Load a GeoJSON FeatureCollection from disk."""
    return json.loads(path.read_text(encoding="utf-8"))


def write_geojson(path: Path, collection: dict) -> None:
    """Write a GeoJSON FeatureCollection compactly."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(collection, separators=(",", ":")), encoding="utf-8")


# ---------------------------------------------------------------------------
# Feature filtering
# ---------------------------------------------------------------------------


def filter_by_state(features: list[dict], state: str) -> list[dict]:
    """Filter features by state property. Use 'ALL' to skip filtering."""
    if state.upper() == "ALL":
        return features
    return [
        f for f in features
        if str(f["properties"].get("state", "")).strip().upper() == state.upper()
    ]


def filter_by_fuel_type(features: list[dict], fuel_type: str) -> list[dict]:
    """
    Filter features by fuel/technology type.

    Matches substring case-insensitively against the concatenation of
    primary_fuel_type and technology_type fields.
    """
    return [
        f for f in features
        if fuel_type.lower() in (
            str(f["properties"].get("primary_fuel_type", ""))
            + " "
            + str(f["properties"].get("technology_type", ""))
        ).lower()
    ]


# ---------------------------------------------------------------------------
# Statistics
# ---------------------------------------------------------------------------


def compute_field_stats(features: list[dict]) -> dict:
    """Compute per-field missing-value counts and list all fields."""
    fields = sorted({key for f in features for key in f["properties"]})
    missing = {
        field: sum(
            f["properties"].get(field) in (None, "") for f in features
        )
        for field in fields
    }
    return {"fields": fields, "missing": missing}


def count_property(features: list[dict], prop: str) -> dict:
    """Count occurrences of each value of a property."""
    return dict(Counter(str(f["properties"].get(prop)) for f in features))


def count_geometry_types(features: list[dict]) -> dict:
    """Count geometry types across features."""
    return dict(Counter(
        f.get("geometry", {}).get("type") if f.get("geometry") else None
        for f in features
    ))


def count_valid_coordinates(features: list[dict]) -> int:
    """Count features with valid point coordinates."""
    return sum(
        f.get("geometry")
        and f["geometry"].get("coordinates")
        and len(f["geometry"]["coordinates"]) >= 2
        for f in features
    )


def iter_coordinates(value) -> list[tuple[float, float]]:
    """Yield every (x, y) pair from an arbitrarily nested GeoJSON coordinate array."""
    results = []

    def _recurse(v):
        if isinstance(v, list) and len(v) >= 2 and all(
            isinstance(item, (int, float)) for item in v[:2]
        ):
            results.append((v[0], v[1]))
        elif isinstance(v, list):
            for item in v:
                _recurse(item)

    _recurse(value)
    return results


def compute_bounds(features: list[dict]) -> list[float] | None:
    """Compute [minx, miny, maxx, maxy] bounding box from all feature geometries."""
    all_coords = []
    for f in features:
        geom = f.get("geometry")
        if geom and geom.get("coordinates"):
            all_coords.extend(iter_coordinates(geom["coordinates"]))
    if not all_coords:
        return None
    return [
        min(x for x, _ in all_coords),
        min(y for _, y in all_coords),
        max(x for x, _ in all_coords),
        max(y for _, y in all_coords),
    ]
