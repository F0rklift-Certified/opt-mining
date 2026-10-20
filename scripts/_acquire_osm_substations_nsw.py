#!/usr/bin/env python3
"""One-shot acquisition of named NSW power substations from OpenStreetMap.

Makes a single read-only POST to the Overpass API for every named
``power=substation`` node/way inside the NSW state admin area, keeps only the
grid substations (drops ``substation=traction``/``rail``), and atomically writes
``DATA/infrastructure/substations/osm_substations_nsw.geojson`` (EPSG:4326) plus
a ``download_manifest`` entry carrying the exact Overpass query, SHA-256 and the
**ODbL 1.0 — © OpenStreetMap contributors** licence credit.

OSM gives the urban distribution zone substations the Geoscience Australia
transmission-weighted layer lacks (Campsie, City South, Chatswood, Mascot …),
so it is the *second* coordinate source for the name-only DNSP load rows
(``pipeline.demand.geocode_load``). See
``.agents/tasks/osm-substation-geocoding/findings.md`` §2–§6 for the design.

Temporary helper — not part of the pipeline stages. Run once from the repo root::

    python scripts/_acquire_osm_substations_nsw.py
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import requests

from pipeline.demand import config as demand_config
from pipeline.common.geo import atomic_write_json, atomic_write_text, utc_now

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# Exact Overpass query (findings.md §2). Recorded verbatim in the manifest so
# the snapshot is reproducible.
OVERPASS_QUERY = """[out:json][timeout:120];
area["ISO3166-2"="AU-NSW"][admin_level=4]->.nsw;
(
  node["power"="substation"]["name"](area.nsw);
  way["power"="substation"]["name"](area.nsw);
);
out tags center;
"""

# Descriptive User-Agent so the Overpass operators can see who is querying.
USER_AGENT = (
    "opt-mining-nsw/1.0 (NSW zone-substation geocoding; one-shot OSM acquisition; "
    "+https://www.openstreetmap.org/copyright)"
)

LICENCE = "ODbL 1.0 - (c) OpenStreetMap contributors"

OUT_PATH = (
    demand_config.PROJECT_ROOT
    / "DATA"
    / "infrastructure"
    / "substations"
    / "osm_substations_nsw.geojson"
)
MANIFEST_PATH = (
    demand_config.PROJECT_ROOT
    / "DATA"
    / "infrastructure"
    / "metadata"
    / "download_manifest.json"
)

# Substation subtypes that are NOT grid substations and must be dropped.
_EXCLUDE_SUBSTATION = {"traction", "rail"}

# Overpass is a shared, rate-limited service; retry a few times on transient
# failures before giving up (never fabricate the snapshot).
_MAX_ATTEMPTS = 3
_RETRY_DELAY_S = 10


def fetch_overpass() -> dict:
    """POST the query once (with retries on transient failure); return the JSON."""
    last_exc: Exception | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            resp = requests.post(
                OVERPASS_URL,
                data={"data": OVERPASS_QUERY},
                headers={"User-Agent": USER_AGENT},
                timeout=180,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:  # network / 429 / 504 / malformed JSON
            last_exc = exc
            print(f"  Overpass attempt {attempt}/{_MAX_ATTEMPTS} failed: {exc}")
            if attempt < _MAX_ATTEMPTS:
                time.sleep(_RETRY_DELAY_S)
    raise RuntimeError(
        f"Overpass API unavailable after {_MAX_ATTEMPTS} attempts: {last_exc}"
    )


def _element_point(element: dict) -> tuple[float, float] | None:
    """Return (lon, lat) for an element: node lat/lon, way center.lat/center.lon."""
    if element.get("type") == "node":
        lat, lon = element.get("lat"), element.get("lon")
    else:  # way (or relation, if ever returned) — use the computed centre
        centre = element.get("center") or {}
        lat, lon = centre.get("lat"), centre.get("lon")
    if lat is None or lon is None:
        return None
    return float(lon), float(lat)


def build_features(payload: dict) -> list[dict]:
    """Filter to grid substations and build one GeoJSON point per element."""
    features: list[dict] = []
    for element in payload.get("elements", []):
        tags = element.get("tags", {})
        if tags.get("power") != "substation":
            continue
        substation = tags.get("substation")
        if substation in _EXCLUDE_SUBSTATION:
            continue
        name = tags.get("name")
        if not name:
            continue
        point = _element_point(element)
        if point is None:
            continue
        lon, lat = point
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "name": name,
                    "operator": tags.get("operator"),
                    "substation": substation,
                    "voltage": tags.get("voltage"),
                    "osm_type": element.get("type"),
                    "osm_id": element.get("id"),
                },
            }
        )
    # Deterministic order (osm_type, osm_id) so the snapshot bytes are stable.
    features.sort(key=lambda f: (f["properties"]["osm_type"], f["properties"]["osm_id"]))
    return features


def main() -> int:
    print(f"Querying Overpass for named NSW power substations ({OVERPASS_URL})...")
    payload = fetch_overpass()
    n_raw = len(payload.get("elements", []))
    print(f"  Overpass returned {n_raw} elements")

    features = build_features(payload)
    if not features:
        raise SystemExit(
            "Overpass returned no usable grid substations; aborting (not fabricating a file)."
        )
    print(f"  kept {len(features)} grid substations (dropped traction/rail/unnamed)")

    collection = {"type": "FeatureCollection", "features": features}
    text = json.dumps(collection, separators=(",", ":")) + "\n"
    atomic_write_text(OUT_PATH, text)
    nbytes = len(text.encode())
    print(f"  wrote {OUT_PATH} ({nbytes} bytes, {len(features)} features)")

    sha = hashlib.sha256(OUT_PATH.read_bytes()).hexdigest()
    print(f"  sha256={sha}")

    manifest = json.loads(MANIFEST_PATH.read_text()) if MANIFEST_PATH.exists() else {}
    manifest["osm_substations_nsw.geojson"] = {
        "dataset": "OpenStreetMap named power=substation points, NSW",
        "source": OVERPASS_URL,
        "overpass_query": OVERPASS_QUERY,
        "retrieved_utc": utc_now(),
        "features": int(len(features)),
        "local_bytes": int(nbytes),
        "sha256": sha,
        "crs": "EPSG:4326",
        "licence": LICENCE,
        "generated_by": "scripts/_acquire_osm_substations_nsw.py",
    }
    atomic_write_json(MANIFEST_PATH, manifest)
    print(f"  manifest updated: {MANIFEST_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
