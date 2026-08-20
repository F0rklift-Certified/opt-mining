"""
Geographic inspect stage — examine vector and raster samples.

Reads each GeoJSON and GeoTIFF in the geographic data directories,
computes statistics, and writes per-sample inspection markdown reports.

Importable entry point:
    from pipeline.geographic.inspect import run
    result = run(verbose=False)

Output:
    DATA/geographic/metadata/<sample-stem>_inspection.md
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path

import numpy as np
import rasterio

from . import config
from ..common.geo import atomic_write_text, banner
from ..common.geo import human_bytes


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_VECTOR_DIRS = ["boundaries", "derived", "protected", "urban", "coastline"]
_RASTER_DIRS = ["elevation", "landuse"]


# ---------------------------------------------------------------------------
# Vector inspection
# ---------------------------------------------------------------------------


def _walk_coords(geometry: dict):
    """Yield every (x, y) pair in a GeoJSON geometry."""
    def rec(coords):
        if coords and isinstance(coords[0], (int, float)):
            yield coords[0], coords[1]
        else:
            for part in coords:
                yield from rec(part)
    yield from rec(geometry["coordinates"])


def _inspect_geo_vector(path: Path) -> str:
    """Inspect a geographic vector sample and return markdown."""
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
        for x, y in _walk_coords(geom):
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
    out.write(banner("geographic.inspect"))
    out.write(f"\n- **File:** `{path.relative_to(config.PROJECT_ROOT)}` "
              f"({human_bytes(path.stat().st_size)})\n")
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


# ---------------------------------------------------------------------------
# Raster inspection
# ---------------------------------------------------------------------------


def _load_class_table() -> dict[int, str]:
    """Load the ALUM v8 class table if present."""
    ct_path = config.GEO_DIR / "landuse" / "abares_alumv8_class_table.csv"
    if not ct_path.exists():
        return {}
    with open(ct_path) as fh:
        return {int(row["Value"]): row["TERTV8"] for row in csv.DictReader(fh)}


def _inspect_geo_raster(path: Path) -> str:
    """Inspect a geographic raster sample and return markdown."""
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
    out.write(banner("geographic.inspect"))
    out.write(f"\n- **File:** `{path.relative_to(config.PROJECT_ROOT)}` "
              f"({human_bytes(path.stat().st_size)})\n")
    out.write("- **Type:** Raster (GeoTIFF)\n")
    out.write(f"- **CRS (declared in file):** {info['crs']}\n")
    out.write(f"- **Bands:** {info['bands']}\n")
    out.write(f"- **Data type:** {info['dtype']}\n")
    out.write(f"- **Grid:** {info['width']} x {info['height']} px\n")
    unit = "deg" if "4326" in info["crs"] else "m"
    out.write(f"- **Pixel size:** {info['pixel'][0]:.6f} x {info['pixel'][1]:.6f} {unit}\n")
    out.write(f"- **Bounds (W, S, E, N):** ({info['bounds'].left:.5f}, "
              f"{info['bounds'].bottom:.5f}, {info['bounds'].right:.5f}, "
              f"{info['bounds'].top:.5f})\n")
    out.write(f"- **NoData value:** {info['nodata']}\n")
    out.write(f"- **NoData share:** {nodata_pct:.2f}% of pixels\n\n")

    if is_landuse:
        classes = _load_class_table()
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
                  "voids/ocean fill, so coastal windows cannot distinguish true sea-level "
                  "land from masked ocean without a separate land mask.\n")
    return out.getvalue()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(verbose: bool = False) -> dict:
    """
    Inspect all geographic samples and write inspection reports.

    Returns a summary dict with report paths.
    """
    reports: list[tuple[Path, str]] = []
    for sub in _VECTOR_DIRS:
        for path in sorted((config.GEO_DIR / sub).glob("*.geojson")):
            reports.append((path, _inspect_geo_vector(path)))
    for sub in _RASTER_DIRS:
        for path in sorted((config.GEO_DIR / sub).glob("*.tif")):
            reports.append((path, _inspect_geo_raster(path)))

    outputs = []
    for path, text in reports:
        out_path = config.GEO_META_DIR / f"{path.stem.replace('.', '_')}_inspection.md"
        atomic_write_text(out_path, text)
        if verbose:
            print(f"      {out_path.relative_to(config.PROJECT_ROOT)}")
        outputs.append(out_path)

    print(f"    {len(outputs)} inspection report(s)")
    return {"reports": outputs}
