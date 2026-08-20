"""
Assess two candidate land masks on the analysis grid and quantify the
offshore leakage each would permit.

This closes Task 1's highest-severity hand-off. Global Wind Atlas rasters
carry real wind values over the ocean (Tasman Sea ~8.6 m/s vs ~5.6 m/s land
mean), so any cell wrongly classified as land tends to look like a prime
site. The OptMining prototype masks land with Natural Earth 1:50m polygons
under a centroid-in-polygon rule; Task 1 asked whether that generalised
coastline is good enough or whether an authoritative Australian boundary is
needed.

Method: build a 0.05 deg grid over a NSW coastal strip, anchored on the
Global Wind Atlas pixel lattice (per Task 1's grid-alignment recommendation,
one cell = exactly 20 x 20 Atlas pixels). Rasterise (a) Natural Earth 50m
land and (b) the ABS ASGS 2021 Australia outline onto that grid with the
cell-centre rule — the same rule the prototype uses. Read the Atlas
wind-speed 100 m layer over the strip via /vsicurl/, aggregate to the same
cells, and report the wind resource of the cells where the two masks
disagree.

Usage:
  python scripts/geo_landmask_assessment.py

Output: DATA/geographic/metadata/landmask_assessment.md

Source: DATA/geographic/coastline/ne_land-50m_australia.geojson,
        DATA/geographic/boundaries/abs_aus_2021_national.geojson,
        Global Wind Atlas v4 via scripts/gwa_common.py
Licence: see DATA/geographic/DATA_PROVENANCE.md
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.windows import from_bounds

sys.path.insert(0, str(Path(__file__).resolve().parent))
from geo_common import (  # noqa: E402
    GEO_DIR,
    META_DIR,
    REPO_ROOT,
    apply_geo_vsicurl_env,
    atomic_write_text,
    banner,
)
from gwa_common import resolve_source  # noqa: E402

NE_LAND = GEO_DIR / "coastline" / "ne_land-50m_australia.geojson"
ABS_AUS = GEO_DIR / "boundaries" / "abs_aus_2021_national.geojson"

# Global Wind Atlas pixel lattice (Task 1, §8 "On grid alignment"): origin
# 109.21125 E, -8.86125 S, 0.0025 deg pixels. 0.05 deg cells anchored here
# cover exactly 20 x 20 Atlas pixels each.
GWA_ORIGIN_LON = 109.21125
GWA_ORIGIN_LAT = -8.86125
GWA_PIXEL_DEG = 0.0025
CELL_DEG = 0.05
PX_PER_CELL = int(round(CELL_DEG / GWA_PIXEL_DEG))  # 20

# NSW coastal strip: spans the coastline so the grid contains land, ocean and
# the disputed fringe. Extends the study window east past the coast.
STRIP_BBOX = (150.0, -33.0, 154.0, -28.0)


def anchored_grid(bbox):
    """Snap a bbox outward onto the Atlas-anchored 0.05 deg lattice."""
    w, s, e, n = bbox
    import math
    k_w = math.floor((w - GWA_ORIGIN_LON) / CELL_DEG)
    k_e = math.ceil((e - GWA_ORIGIN_LON) / CELL_DEG)
    k_n = math.floor((GWA_ORIGIN_LAT - n) / CELL_DEG)  # cells count southward
    k_s = math.ceil((GWA_ORIGIN_LAT - s) / CELL_DEG)
    west = GWA_ORIGIN_LON + k_w * CELL_DEG
    east = GWA_ORIGIN_LON + k_e * CELL_DEG
    north = GWA_ORIGIN_LAT - k_n * CELL_DEG
    south = GWA_ORIGIN_LAT - k_s * CELL_DEG
    cols = k_e - k_w
    rows = k_s - k_n
    transform = from_origin(west, north, CELL_DEG, CELL_DEG)
    return (west, south, east, north), rows, cols, transform


def load_geometries(path: Path) -> list[dict]:
    collection = json.loads(path.read_text())
    return [f["geometry"] for f in collection["features"] if f.get("geometry")]


def mask_from_polygons(path: Path, rows: int, cols: int, transform) -> np.ndarray:
    """
    Rasterise polygons with the default cell-centre rule (all_touched=False):
    a cell is land iff its centre falls inside a polygon — the same
    centroid-in-polygon rule the OptMining prototype applies.
    """
    return rasterize(
        ((geom, 1) for geom in load_geometries(path)),
        out_shape=(rows, cols),
        transform=transform,
        fill=0,
        all_touched=False,
        dtype="uint8",
    ).astype(bool)


def gwa_wind_cells(grid_bounds, rows: int, cols: int) -> np.ndarray:
    """
    Windowed /vsicurl/ read of GWA wind-speed 100 m over the strip, averaged
    to the 0.05 deg cells. Because the grid is anchored on the Atlas lattice,
    each cell is exactly PX_PER_CELL^2 native pixels — no resampling.
    """
    provenance = resolve_source("wind-speed", 100)
    with rasterio.open(f"/vsicurl/{provenance['signed_url']}") as src:
        window = from_bounds(*grid_bounds, transform=src.transform)
        window = window.round_offsets().round_lengths()
        data = src.read(1, window=window, masked=True).filled(np.nan)

    expected = (rows * PX_PER_CELL, cols * PX_PER_CELL)
    if data.shape != expected:
        raise RuntimeError(f"window shape {data.shape} != expected {expected}; "
                           "grid is not aligned to the Atlas lattice")
    blocks = data.reshape(rows, PX_PER_CELL, cols, PX_PER_CELL).transpose(0, 2, 1, 3)
    blocks = blocks.reshape(rows, cols, -1)
    with np.errstate(invalid="ignore"):
        return np.nanmean(blocks, axis=2)


def wind_stats(wind: np.ndarray, mask: np.ndarray) -> dict:
    vals = wind[mask]
    vals = vals[~np.isnan(vals)]
    if vals.size == 0:
        return {"n": 0}
    return {"n": int(vals.size), "mean": float(vals.mean()),
            "p90": float(np.percentile(vals, 90)), "max": float(vals.max())}


def fmt(stats: dict) -> str:
    if stats["n"] == 0:
        return "0 | — | — | —"
    return (f"{stats['n']} | {stats['mean']:.2f} | {stats['p90']:.2f} "
            f"| {stats['max']:.2f}")


def main() -> int:
    apply_geo_vsicurl_env()
    grid_bounds, rows, cols, transform = anchored_grid(STRIP_BBOX)
    print(f"Assessment strip : {STRIP_BBOX}")
    print(f"Anchored grid    : {grid_bounds}  ({rows} x {cols} cells of {CELL_DEG} deg)")

    ne_land = mask_from_polygons(NE_LAND, rows, cols, transform)
    abs_land = mask_from_polygons(ABS_AUS, rows, cols, transform)

    both = ne_land & abs_land
    ne_only = ne_land & ~abs_land   # NE keeps, ABS drops -> leakage candidates
    abs_only = abs_land & ~ne_land  # ABS keeps, NE drops -> land lost by NE
    neither = ~ne_land & ~abs_land

    print(f"land (both masks): {both.sum()}  NE-only: {ne_only.sum()}  "
          f"ABS-only: {abs_only.sum()}  ocean (both): {neither.sum()}")

    print("Reading GWA wind-speed 100 m over the strip (windowed /vsicurl/) ...")
    wind = gwa_wind_cells(grid_bounds, rows, cols)

    s_land = wind_stats(wind, both)
    s_ne_only = wind_stats(wind, ne_only)
    s_abs_only = wind_stats(wind, abs_only)
    s_ocean = wind_stats(wind, neither)

    # Leakage severity: how many disputed cells beat the p90 of agreed land?
    land_p90 = s_land["p90"]
    ne_only_vals = wind[ne_only]
    ne_only_vals = ne_only_vals[~np.isnan(ne_only_vals)]
    ne_only_hot = int((ne_only_vals > land_p90).sum())

    out = io.StringIO()
    out.write("# Land-mask assessment: Natural Earth 1:50m vs ABS ASGS boundary\n\n")
    out.write(banner("geo_landmask_assessment.py"))
    out.write(
        f"\nGrid: {rows} x {cols} cells of {CELL_DEG} deg over strip "
        f"{STRIP_BBOX} (W, S, E, N), anchored on the Global Wind Atlas lattice "
        f"(origin {GWA_ORIGIN_LON}, {GWA_ORIGIN_LAT}; one cell = "
        f"{PX_PER_CELL} x {PX_PER_CELL} Atlas pixels). Both masks rasterised "
        "under the cell-centre rule the OptMining prototype uses. The ABS ASGS "
        "2021 Australia outline (server-generalised to ~50 m, see manifest) is "
        "treated as the reference; Natural Earth 1:50m is the prototype's mask.\n\n"
    )
    out.write("## Cell classification\n\n")
    out.write("| Class | Cells | Share of strip |\n|---|---|---|\n")
    total = rows * cols
    for label, mask in [("Land under both masks", both),
                        ("Natural-Earth-only land (NE keeps, ABS drops)", ne_only),
                        ("ABS-only land (NE loses real land)", abs_only),
                        ("Ocean under both masks", neither)]:
        out.write(f"| {label} | {int(mask.sum())} | {100.0 * mask.sum() / total:.2f}% |\n")

    out.write("\n## GWA wind-speed 100 m of each class\n\n")
    out.write("| Class | Cells with wind data | Mean (m/s) | P90 (m/s) | Max (m/s) |\n")
    out.write("|---|---|---|---|---|\n")
    out.write(f"| Land under both masks | {fmt(s_land)} |\n")
    out.write(f"| Natural-Earth-only land | {fmt(s_ne_only)} |\n")
    out.write(f"| ABS-only land | {fmt(s_abs_only)} |\n")
    out.write(f"| Ocean under both masks | {fmt(s_ocean)} |\n")

    out.write(
        f"\n## Leakage\n\n"
        f"- Cells the Natural Earth mask keeps but the ABS boundary rejects: "
        f"**{int(ne_only.sum())}** ({100.0 * ne_only.sum() / max(both.sum(), 1):.2f}% "
        "of agreed land).\n"
        f"- Of those, **{ne_only_hot}** exceed the P90 wind speed of agreed land "
        f"({land_p90:.2f} m/s) — cells that would surface near the top of a "
        "shortlist purely through coastline error.\n"
        f"- Cells the Natural Earth mask wrongly drops (ABS-only land): "
        f"**{int(abs_only.sum())}**.\n"
        f"- Ocean cells still carry wind values "
        f"(mean {s_ocean['mean']:.2f} m/s vs land mean {s_land['mean']:.2f} m/s), "
        "confirming Task 1's finding that an explicit land mask is mandatory — "
        "without one, the shortlist goes offshore regardless of which mask wins.\n"
    )
    out.write(
        "\n## Notes\n\n"
        "- The ABS outline used here carries the ~50 m server-side generalisation "
        "recorded in the download manifest; at 0.05 deg cells the residual "
        "boundary error is two orders of magnitude below cell size.\n"
        "- Neither mask removes inland water bodies; NLUM class 6 (Water) or the "
        "DEA Waterbodies polygons cover that exclusion separately.\n"
    )

    report_path = META_DIR / "landmask_assessment.md"
    atomic_write_text(report_path, out.getvalue())
    print(f"\nReport: {report_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
