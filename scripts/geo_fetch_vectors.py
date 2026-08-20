"""
Fetch the Task 4 vector samples into DATA/geographic/.

Sources are ArcGIS REST FeatureServer layers (ABS ASGS 2021 boundaries,
DCCEEW CAPAD 2024 protected areas) queried as GeoJSON with an explicit
outSR=4326, plus the Natural Earth 1:50m land polygons used by the OptMining
prototype's land mask. National layers that would exceed the commit-size
guardrail are re-requested with server-side generalisation
(maxAllowableOffset), and the offset is recorded in the manifest. NEM
electricity-market regions have no public GIS layer (AEMO publishes PDF maps
only), so they are DERIVED here from ABS state boundaries and flagged as
derived, not authoritative.

Usage:
  python scripts/geo_fetch_vectors.py

Output: DATA/geographic/{boundaries,protected,urban,coastline,derived}/*.geojson
        DATA/geographic/metadata/download_manifest.json (vector section)

Source: https://geo.abs.gov.au/ (ABS), https://gis.environment.gov.au/ (DCCEEW),
        https://github.com/nvkelso/natural-earth-vector (Natural Earth)
Licence: see DATA/geographic/DATA_PROVENANCE.md
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from geo_common import (  # noqa: E402
    ABS_ASGS_BASE,
    CAPAD_BASE,
    DEFAULT_AREA,
    DEFAULT_BBOX,
    GEO_DIR,
    META_DIR,
    REPO_ROOT,
    TIMEOUT,
    atomic_write_json,
    atomic_write_text,
    feature_collection_bytes,
    human_bytes,
    query_layer_geojson,
    utc_now,
)

# Guardrail for files committed to git; national rasters/archives stay in raw/.
MAX_COMMIT_BYTES = 10 * 10**6
# ~50 m at the equator: screening-grade generalisation for national layers,
# two orders of magnitude below the ~5 km analysis cell.
GENERALISE_OFFSET_DEG = 0.0005

NE_LAND_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector"
    "/master/geojson/ne_50m_land.geojson"
)
# Generous Australia bbox for filtering Natural Earth landmasses.
AUS_BBOX = (112.0, -44.5, 154.5, -9.0)

# ASGS 2021 state codes. NEM regions map onto states: NSW+ACT form NSW1;
# WA, NT and Other Territories are outside the NEM.
NEM_REGIONS = {
    "NSW1": ["1", "8"],
    "VIC1": ["2"],
    "QLD1": ["3"],
    "SA1": ["4"],
    "TAS1": ["6"],
}


def write_geojson(path: Path, collection: dict) -> int:
    """Write a FeatureCollection compactly; return bytes written."""
    text = json.dumps(collection, separators=(",", ":")) + "\n"
    atomic_write_text(path, text)
    return len(text.encode())


def record(records: list, dataset: str, source: str, path: Path, collection: dict,
           **extra) -> None:
    size = path.stat().st_size
    print(f"  wrote  : {path.relative_to(REPO_ROOT)} "
          f"({len(collection['features'])} features, {human_bytes(size)})")
    records.append({
        "dataset": dataset,
        "source": source,
        "output_file": str(path.relative_to(REPO_ROOT)),
        "features": len(collection["features"]),
        "local_bytes": size,
        "crs": "EPSG:4326 (GeoJSON, outSR explicit)",
        **extra,
    })


def fetch_with_size_guardrail(layer_url: str, **query_kwargs) -> tuple[dict, float | None]:
    """
    Query at full resolution; if the result would blow the commit guardrail,
    re-query with server-side generalisation. Returns (collection, offset_used).
    """
    collection = query_layer_geojson(layer_url, **query_kwargs)
    if feature_collection_bytes(collection) <= MAX_COMMIT_BYTES:
        return collection, None
    collection = query_layer_geojson(
        layer_url, max_allowable_offset=GENERALISE_OFFSET_DEG, **query_kwargs)
    return collection, GENERALISE_OFFSET_DEG


def derive_nem_regions(ste: dict) -> dict:
    """
    Build NEM region geometries from state polygons.

    Each region is the collection of its member states' polygons as one
    MultiPolygon feature. No geometric dissolve is performed: for
    point-in-polygon tests and rasterisation, a MultiPolygon of adjacent
    state polygons behaves identically to their union, and avoiding the
    dissolve keeps this file honestly labelled as a re-grouping of ABS
    geometry rather than new geometry.
    """
    by_code: dict[str, dict] = {}
    for feature in ste["features"]:
        code = str(feature["properties"].get("state_code_2021"))
        by_code[code] = feature

    features = []
    for region, codes in NEM_REGIONS.items():
        polygons: list = []
        member_names, member_area = [], 0.0
        for code in codes:
            feature = by_code.get(code)
            if feature is None or feature.get("geometry") is None:
                raise RuntimeError(f"state code {code} missing from STE layer")
            geom = feature["geometry"]
            if geom["type"] == "Polygon":
                polygons.append(geom["coordinates"])
            elif geom["type"] == "MultiPolygon":
                polygons.extend(geom["coordinates"])
            else:
                raise RuntimeError(f"unexpected geometry {geom['type']} for state {code}")
            member_names.append(feature["properties"].get("state_name_2021"))
            member_area += float(feature["properties"].get("area_albers_sqkm") or 0)
        features.append({
            "type": "Feature",
            "geometry": {"type": "MultiPolygon", "coordinates": polygons},
            "properties": {
                "nem_region": region,
                "member_states": member_names,
                "member_state_codes": codes,
                "area_albers_sqkm_sum": round(member_area, 4),
                "derivation": ("DERIVED from ABS ASGS 2021 STE polygons; "
                               "not an authoritative AEMO boundary"),
            },
        })
    return {"type": "FeatureCollection", "features": features}


def fetch_natural_earth_australia() -> dict:
    """Download NE 1:50m land and keep landmasses whose bbox touches Australia."""
    resp = requests.get(NE_LAND_URL, timeout=TIMEOUT)
    resp.raise_for_status()
    land = resp.json()
    w, s, e, n = AUS_BBOX

    def bbox_intersects(geom: dict) -> bool:
        coords = geom["coordinates"]
        if geom["type"] == "Polygon":
            coords = [coords]
        xs, ys = [], []
        for poly in coords:
            for x, y in poly[0]:  # exterior ring is enough for a bbox test
                xs.append(x)
                ys.append(y)
        return min(xs) <= e and max(xs) >= w and min(ys) <= n and max(ys) >= s

    kept = [f for f in land["features"] if f.get("geometry") and bbox_intersects(f["geometry"])]
    return {"type": "FeatureCollection", "features": kept}


def main() -> int:
    bbox = DEFAULT_BBOX
    print(f"Study window : {bbox}  ({DEFAULT_AREA})")
    records: list[dict] = []
    failures: list[dict] = []

    jobs = []

    # --- ABS boundaries ----------------------------------------------------
    def fetch_ste():
        url = f"{ABS_ASGS_BASE}/STE/FeatureServer/0"
        collection, offset = fetch_with_size_guardrail(
            url, where="state_name_2021 <> 'Outside Australia'")
        path = GEO_DIR / "boundaries" / "abs_ste_2021_national.geojson"
        write_geojson(path, collection)
        record(records, "ABS ASGS 2021 State/Territory (STE)", url, path, collection,
               max_allowable_offset_deg=offset,
               filter="state_name_2021 <> 'Outside Australia'")
        return collection

    def fetch_aus():
        url = f"{ABS_ASGS_BASE}/AUS/FeatureServer/0"
        collection, offset = fetch_with_size_guardrail(
            url, where="aus_code_2021 = 'AUS'")
        path = GEO_DIR / "boundaries" / "abs_aus_2021_national.geojson"
        write_geojson(path, collection)
        record(records, "ABS ASGS 2021 Australia outline (AUS)", url, path, collection,
               max_allowable_offset_deg=offset, filter="aus_code_2021 = 'AUS'")

    def fetch_lga():
        url = f"{ABS_ASGS_BASE}/LGA/FeatureServer/0"
        collection, offset = fetch_with_size_guardrail(url, geometry_bbox=bbox)
        path = GEO_DIR / "boundaries" / f"abs_lga_2021_{DEFAULT_AREA}.geojson"
        write_geojson(path, collection)
        record(records, "ABS ASGS 2021 Local Government Areas (window extract)", url,
               path, collection, max_allowable_offset_deg=offset,
               spatial_filter=f"envelope {bbox} EPSG:4326")

    def fetch_ucl():
        url = f"{ABS_ASGS_BASE}/UCL/FeatureServer/0"
        collection, offset = fetch_with_size_guardrail(url, geometry_bbox=bbox)
        path = GEO_DIR / "urban" / f"abs_ucl_2021_{DEFAULT_AREA}.geojson"
        write_geojson(path, collection)
        record(records, "ABS ASGS 2021 Urban Centres and Localities (window extract)",
               url, path, collection, max_allowable_offset_deg=offset,
               spatial_filter=f"envelope {bbox} EPSG:4326")

    # --- CAPAD protected areas ----------------------------------------------
    def fetch_capad_nsw():
        url = f"{CAPAD_BASE}/0"
        collection, offset = fetch_with_size_guardrail(
            url, where="STATE = 'NSW'", page_size=1000)
        path = GEO_DIR / "protected" / "dcceew_capad-terrestrial_2024_nsw.geojson"
        write_geojson(path, collection)
        record(records, "CAPAD 2024 terrestrial, NSW", url, path, collection,
               max_allowable_offset_deg=offset, filter="STATE = 'NSW'")

    def fetch_capad_window():
        url = f"{CAPAD_BASE}/0"
        collection = query_layer_geojson(url, geometry_bbox=bbox, page_size=1000)
        path = GEO_DIR / "protected" / f"dcceew_capad-terrestrial_2024_{DEFAULT_AREA}.geojson"
        write_geojson(path, collection)
        record(records, "CAPAD 2024 terrestrial, study-window extract (full resolution)",
               url, path, collection, max_allowable_offset_deg=None,
               spatial_filter=f"envelope {bbox} EPSG:4326")

    # --- Natural Earth land (prototype land-mask source) ---------------------
    def fetch_ne_land():
        collection = fetch_natural_earth_australia()
        path = GEO_DIR / "coastline" / "ne_land-50m_australia.geojson"
        write_geojson(path, collection)
        record(records, "Natural Earth 1:50m land, Australia-region landmasses",
               NE_LAND_URL, path, collection,
               filter=f"landmass bbox intersects {AUS_BBOX}")

    # --- Derived NEM regions --------------------------------------------------
    ste_collection: dict | None = None

    def fetch_nem():
        if ste_collection is None:
            raise RuntimeError("STE fetch failed; cannot derive NEM regions")
        collection = derive_nem_regions(ste_collection)
        path = GEO_DIR / "derived" / "nem_regions_asgs2021_national.geojson"
        write_geojson(path, collection)
        record(records, "NEM regions (derived from ABS STE; not authoritative)",
               f"{ABS_ASGS_BASE}/STE/FeatureServer/0", path, collection,
               derivation="see scripts/geo_fetch_vectors.py derive_nem_regions()")

    jobs = [
        ("ABS STE", fetch_ste),
        ("ABS AUS outline", fetch_aus),
        ("ABS LGA (window)", fetch_lga),
        ("ABS UCL (window)", fetch_ucl),
        ("CAPAD NSW", fetch_capad_nsw),
        ("CAPAD window extract", fetch_capad_window),
        ("Natural Earth land", fetch_ne_land),
        ("NEM regions (derived)", fetch_nem),
    ]

    for label, job in jobs:
        print(f"\n{label}")
        try:
            result = job()
            if label == "ABS STE":
                ste_collection = result
        except Exception as exc:  # a missing layer is a finding, not a crash
            print(f"  FAILED: {exc}")
            failures.append({"dataset": label, "error": str(exc)})

    manifest_path = META_DIR / "download_manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    manifest.setdefault("study_window", {"name": DEFAULT_AREA, "bbox_epsg4326": list(bbox)})
    manifest["vectors"] = {
        "retrieved_utc": utc_now(),
        "generated_by": "scripts/geo_fetch_vectors.py",
        "commit_guardrail_bytes": MAX_COMMIT_BYTES,
        "samples": records,
        "failures": failures,
    }
    atomic_write_json(manifest_path, manifest)
    print(f"\nManifest: {manifest_path.relative_to(REPO_ROOT)}")
    print(f"Retrieved {len(records)} sample(s); {len(failures)} failure(s).")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
