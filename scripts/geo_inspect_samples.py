"""
Inspect every committed Task 4 sample and write one report per file.

Vector samples (GeoJSON) get feature counts, geometry types, attribute
schema with null counts and examples, and the computed extent. Raster
samples (GeoTIFF) get band/dtype/nodata/pixel size/bounds/CRS plus value
statistics; the NLUM land-use clip additionally gets per-class pixel counts
decoded against the class table shipped in the source zip. These reports
are the source for Sections 6 and 7 of the task document — no figure there
should be typed by hand.

Usage:
  python scripts/geo_inspect_samples.py

Output: DATA/geographic/metadata/<sample-stem>_inspection.md (one per sample)

Source: files under DATA/geographic/ (see download_manifest.json)
Licence: see DATA/geographic/DATA_PROVENANCE.md
"""

from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

import numpy as np
import rasterio

sys.path.insert(0, str(Path(__file__).resolve().parent))
from geo_common import (  # noqa: E402
    GEO_DIR,
    META_DIR,
    REPO_ROOT,
    atomic_write_text,
    banner,
    human_bytes,
)

VECTOR_DIRS = ["boundaries", "derived", "protected", "urban", "coastline"]
RASTER_DIRS = ["elevation", "landuse"]
CLASS_TABLE = GEO_DIR / "landuse" / "abares_alumv8_class_table.csv"


def walk_coords(geometry: dict):
    """Yield every (x, y) pair in a GeoJSON geometry."""
    def rec(coords):
        if coords and isinstance(coords[0], (int, float)):
            yield coords[0], coords[1]
        else:
            for part in coords:
                yield from rec(part)
    yield from rec(geometry["coordinates"])


def inspect_vector(path: Path) -> str:
    collection = json.loads(path.read_text())
    features = collection["features"]

    geom_types: dict[str, int] = {}
    xs_min = ys_min = float("inf")
    xs_max = ys_max = float("-inf")
    ring_vertices = 0
    for feature in features:
        geom = feature.get("geometry")
        if geom is None:
            geom_types["(null)"] = geom_types.get("(null)", 0) + 1
            continue
        geom_types[geom["type"]] = geom_types.get(geom["type"], 0) + 1
        for x, y in walk_coords(geom):
            ring_vertices += 1
            xs_min, xs_max = min(xs_min, x), max(xs_max, x)
            ys_min, ys_max = min(ys_min, y), max(ys_max, y)

    field_stats: dict[str, dict] = {}
    for feature in features:
        for key, value in (feature.get("properties") or {}).items():
            stat = field_stats.setdefault(key, {"nulls": 0, "types": set(), "example": None})
            if value is None or value == "":
                stat["nulls"] += 1
            else:
                stat["types"].add(type(value).__name__)
                if stat["example"] is None:
                    stat["example"] = value

    out = io.StringIO()
    out.write(f"# Inspection: `{path.name}`\n\n")
    out.write(banner("geo_inspect_samples.py"))
    out.write(f"\n- **File:** `{path.relative_to(REPO_ROOT)}` ({human_bytes(path.stat().st_size)})\n")
    out.write("- **Type:** Vector (GeoJSON FeatureCollection)\n")
    out.write("- **CRS:** EPSG:4326 (GeoJSON per RFC 7946; requested explicitly as "
              "`outSR=4326` for ArcGIS sources)\n")
    out.write(f"- **Features:** {len(features)}\n")
    out.write(f"- **Geometry types:** "
              f"{', '.join(f'{k} ({v})' for k, v in sorted(geom_types.items()))}\n")
    out.write(f"- **Total vertices:** {ring_vertices}\n")
    out.write(f"- **Extent (W, S, E, N):** ({xs_min:.5f}, {ys_min:.5f}, "
              f"{xs_max:.5f}, {ys_max:.5f})\n\n")
    out.write("## Attribute fields\n\n")
    out.write("| Field | Type(s) | Nulls/empties | Example |\n|---|---|---|---|\n")
    for key, stat in field_stats.items():
        types = ", ".join(sorted(stat["types"])) or "(all null)"
        example = str(stat["example"])
        if len(example) > 60:
            example = example[:57] + "..."
        out.write(f"| `{key}` | {types} | {stat['nulls']}/{len(features)} | {example} |\n")
    return out.getvalue()


def load_class_table() -> dict[int, str]:
    if not CLASS_TABLE.exists():
        return {}
    with open(CLASS_TABLE) as fh:
        return {int(row["Value"]): row["TERTV8"] for row in csv.DictReader(fh)}


def inspect_raster(path: Path) -> str:
    with rasterio.open(path) as src:
        data = src.read(1)
        info = {
            "bands": src.count,
            "dtype": src.dtypes[0],
            "nodata": src.nodata,
            "pixel": (abs(src.res[0]), abs(src.res[1])),
            "bounds": src.bounds,
            "crs": str(src.crs),
            "width": src.width,
            "height": src.height,
        }

    is_landuse = "landuse" in str(path)
    if info["nodata"] is not None:
        valid = data[data != info["nodata"]]
    else:
        valid = data.ravel()
    nodata_pct = 100.0 * (data.size - valid.size) / data.size

    out = io.StringIO()
    out.write(f"# Inspection: `{path.name}`\n\n")
    out.write(banner("geo_inspect_samples.py"))
    out.write(f"\n- **File:** `{path.relative_to(REPO_ROOT)}` ({human_bytes(path.stat().st_size)})\n")
    out.write("- **Type:** Raster (GeoTIFF)\n")
    out.write(f"- **CRS (declared in file):** {info['crs']}\n")
    out.write(f"- **Bands:** {info['bands']}\n")
    out.write(f"- **Data type:** {info['dtype']}\n")
    out.write(f"- **Grid:** {info['width']} x {info['height']} px\n")
    unit = "deg" if info["crs"].endswith("4326") else "m"
    out.write(f"- **Pixel size:** {info['pixel'][0]:.6f} x {info['pixel'][1]:.6f} {unit}\n")
    out.write(f"- **Bounds (W, S, E, N):** ({info['bounds'].left:.5f}, {info['bounds'].bottom:.5f}, "
              f"{info['bounds'].right:.5f}, {info['bounds'].top:.5f})\n")
    out.write(f"- **NoData value:** {info['nodata']}\n")
    out.write(f"- **NoData share:** {nodata_pct:.2f}% of pixels\n\n")

    if is_landuse:
        classes = load_class_table()
        values, counts = np.unique(data, return_counts=True)
        out.write("## Land-use class counts (window)\n\n")
        out.write("| Code | ALUM v8 tertiary class | Pixels | Share |\n|---|---|---|---|\n")
        order = np.argsort(counts)[::-1]
        for idx in order:
            code, count = int(values[idx]), int(counts[idx])
            label = classes.get(code, "(not in class table)")
            out.write(f"| {code} | {label} | {count} | {100.0 * count / data.size:.2f}% |\n")
    else:
        stats = {
            "min": float(valid.min()),
            "p10": float(np.percentile(valid, 10)),
            "median": float(np.median(valid)),
            "mean": float(valid.mean()),
            "p90": float(np.percentile(valid, 90)),
            "max": float(valid.max()),
        }
        out.write("## Elevation statistics (m above sea level)\n\n")
        out.write("| Min | P10 | Median | Mean | P90 | Max |\n|---|---|---|---|---|---|\n")
        out.write("| " + " | ".join(f"{stats[k]:.1f}" for k in
                                    ["min", "p10", "median", "mean", "p90", "max"]) + " |\n")
        zero_pct = 100.0 * float((data == 0).sum()) / data.size
        out.write(f"\nPixels exactly 0: {zero_pct:.2f}% — SRTM uses 0 for both sea level and "
                  "voids/ocean fill (the mosaic declares nodata=0), so a coastal window "
                  "cannot distinguish true sea-level land from masked ocean without a "
                  "separate land mask.\n")
    return out.getvalue()


def main() -> int:
    reports = []
    for sub in VECTOR_DIRS:
        for path in sorted((GEO_DIR / sub).glob("*.geojson")):
            reports.append((path, inspect_vector(path)))
    for sub in RASTER_DIRS:
        for path in sorted((GEO_DIR / sub).glob("*.tif")):
            reports.append((path, inspect_raster(path)))

    for path, text in reports:
        out_path = META_DIR / f"{path.stem.replace('.', '_')}_inspection.md"
        atomic_write_text(out_path, text)
        print(f"  {out_path.relative_to(REPO_ROOT)}")

    print(f"\nInspected {len(reports)} sample(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
