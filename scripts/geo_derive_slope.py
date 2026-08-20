"""
Derive slope and terrain ruggedness from the sampled DEM clips, and produce
the aggregation evidence Task 5 needs.

This closes a Task 1 hand-off: the Global Wind Atlas publishes no usable
terrain layers for Australia (elevation and RIX return HTTP 403), so terrain
must come from a DEM. Slope is computed with Horn's 3x3 method (the same
operator as gdaldem/ArcGIS Slope) with per-row metre spacing so degrees of
longitude are not silently treated as metres. Ruggedness is Riley's Terrain
Ruggedness Index (TRI), standing in for the Atlas's inaccessible RIX layer.

Two evidence tables are produced, with the DECISIONS deliberately left to
Task 5 (mirroring Task 1's aggregation_sensitivity.md):
  1. GL1 (30 m) vs GL3 (90 m) slope over the same sub-window — is the
     1-second product's extra detail material at screening scale, given GA's
     advice that unsmoothed 1-second SRTM is noisy for slope?
  2. Slope aggregated to the ~5 km (0.05 deg) analysis grid under mean, max
     and p90 — how much does the choice of statistic move the share of cells
     crossing candidate slope thresholds?

Usage:
  python scripts/geo_derive_slope.py

Output: DATA/geographic/elevation/srtm-gl1_slope-horn_30m_glen-innes.tif
        DATA/geographic/elevation/srtm-gl3_slope-horn_90m_new-england-rez.tif
        DATA/geographic/elevation/srtm-gl1_tri_30m_glen-innes.tif
        DATA/geographic/metadata/slope_derivation.md

Source: DEM clips under DATA/geographic/elevation/ (see download_manifest.json)
Licence: see DATA/geographic/DATA_PROVENANCE.md
"""

from __future__ import annotations

import io
import os
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

ELEV_DIR = GEO_DIR / "elevation"
GL3_PATH = ELEV_DIR / "srtm-gl3_elevation_90m_new-england-rez.tif"
GL1_PATH = ELEV_DIR / "srtm-gl1_elevation_30m_glen-innes.tif"

# Metres per degree: N-S is nearly constant; E-W shrinks with latitude.
M_PER_DEG_LAT = 111_132.0
M_PER_DEG_LON_EQ = 111_320.0

# Candidate slope thresholds for the exclusion/penalty discussion (degrees).
# 10-15 deg is the range commonly cited as the practical limit for turbine
# pads and crane access; the exact rule is Task 5's to set.
THRESHOLDS_DEG = [5.0, 10.0, 15.0, 20.0]

CELL_DEG = 0.05  # analysis grid cell (~5 km), per the Product Knowledge Base


def horn_slope_deg(dem: np.ndarray, transform) -> np.ndarray:
    """
    Horn 3x3 slope in degrees on a geographic grid.

    dz/dx and dz/dy use the standard Horn weights; the metre spacing of one
    pixel of longitude is computed per row from that row's latitude, so the
    same code is correct at any latitude in the clip.
    """
    z = dem.astype(np.float64)
    # 8 neighbours via padded shifts (edge pixels replicate — good enough for
    # samples whose edges are trimmed by the aggregation anyway).
    zp = np.pad(z, 1, mode="edge")
    z1, z2, z3 = zp[:-2, :-2], zp[:-2, 1:-1], zp[:-2, 2:]
    z4, _, z6 = zp[1:-1, :-2], zp[1:-1, 1:-1], zp[1:-1, 2:]
    z7, z8, z9 = zp[2:, :-2], zp[2:, 1:-1], zp[2:, 2:]

    xres_deg = transform.a
    yres_deg = -transform.e
    rows = np.arange(z.shape[0])
    lat = transform.f + transform.e * (rows + 0.5)  # centre latitude per row
    xres_m = (M_PER_DEG_LON_EQ * np.cos(np.radians(lat)) * xres_deg)[:, None]
    yres_m = M_PER_DEG_LAT * yres_deg

    dzdx = ((z3 + 2 * z6 + z9) - (z1 + 2 * z4 + z7)) / (8.0 * xres_m)
    dzdy = ((z1 + 2 * z2 + z3) - (z7 + 2 * z8 + z9)) / (8.0 * yres_m)
    return np.degrees(np.arctan(np.hypot(dzdx, dzdy)))


def riley_tri(dem: np.ndarray) -> np.ndarray:
    """Riley TRI: root-sum-square of elevation differences to the 8 neighbours."""
    z = dem.astype(np.float64)
    zp = np.pad(z, 1, mode="edge")
    total = np.zeros_like(z)
    for dr in (-1, 0, 1):
        for dc in (-1, 0, 1):
            if dr == 0 and dc == 0:
                continue
            neigh = zp[1 + dr:zp.shape[0] - 1 + dr, 1 + dc:zp.shape[1] - 1 + dc]
            total += (neigh - z) ** 2
    return np.sqrt(total)


def write_raster(path: Path, data: np.ndarray, template_profile: dict, scale: float) -> None:
    """
    Write a derived raster as scaled int16 (value = pixel * scale).

    Integer storage deflates several times smaller than float32 for these
    fields; the scale factor is recorded in the GeoTIFF so readers that
    honour band scales recover the physical units directly. Quantisation
    error (scale/2) is far below the method error of Horn slope on SRTM.
    """
    profile = template_profile.copy()
    profile.update(dtype="int16", nodata=None, compress="deflate", predictor=2,
                   tiled=True, blockxsize=256, blockysize=256)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tif.tmp")
    try:
        with rasterio.open(tmp, "w", **profile) as dst:
            dst.write(np.round(data / scale).astype(np.int16), 1)
            dst.scales = (scale,)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)
    print(f"  wrote  : {path.relative_to(REPO_ROOT)} ({human_bytes(path.stat().st_size)})")


def block_stat(arr: np.ndarray, block: int, stat: str) -> np.ndarray:
    """Aggregate a 2D array into block x block cells under one statistic."""
    rows = (arr.shape[0] // block) * block
    cols = (arr.shape[1] // block) * block
    trimmed = arr[:rows, :cols].reshape(rows // block, block, cols // block, block)
    stacked = trimmed.transpose(0, 2, 1, 3).reshape(rows // block, cols // block, -1)
    if stat == "mean":
        return stacked.mean(axis=2)
    if stat == "max":
        return stacked.max(axis=2)
    if stat == "p90":
        return np.percentile(stacked, 90, axis=2)
    raise ValueError(stat)


def dist_row(label: str, arr: np.ndarray) -> str:
    flat = arr.ravel()
    return (f"| {label} | {flat.mean():.2f} | {np.median(flat):.2f} "
            f"| {np.percentile(flat, 90):.2f} | {flat.max():.2f} |")


def main() -> int:
    out = io.StringIO()
    out.write("# Slope and ruggedness derivation\n\n")
    out.write(banner("geo_derive_slope.py"))
    out.write(
        "\nCloses the Task 1 hand-off: terrain layers sourced from the sampled DEM\n"
        "clips instead of the Atlas's inaccessible per-country RIX/elevation.\n"
        "Method: Horn 3x3 slope with per-row metre spacing "
        f"(N-S {M_PER_DEG_LAT:,.0f} m/deg; E-W {M_PER_DEG_LON_EQ:,.0f} x cos(lat) m/deg); "
        "Riley TRI for ruggedness.\n"
        "The choice of aggregation statistic and of any threshold is deliberately\n"
        "left to Task 5 — the tables below are evidence, not decisions.\n\n"
    )

    # --- Derive from GL3 over the full study window -------------------------
    print("GL3 (90 m) slope over the study window")
    with rasterio.open(GL3_PATH) as src:
        gl3 = src.read(1)
        gl3_profile = src.profile.copy()
        gl3_transform = src.transform
    gl3_slope = horn_slope_deg(gl3, gl3_transform)
    write_raster(ELEV_DIR / "srtm-gl3_slope-horn_90m_new-england-rez.tif",
                 gl3_slope, gl3_profile, scale=0.01)

    # --- Derive from GL1 over the wind-farm sub-window -----------------------
    print("GL1 (30 m) slope + TRI over the wind-farm sub-window")
    with rasterio.open(GL1_PATH) as src:
        gl1 = src.read(1)
        gl1_profile = src.profile.copy()
        gl1_transform = src.transform
        gl1_bounds = src.bounds
    gl1_slope = horn_slope_deg(gl1, gl1_transform)
    gl1_tri = riley_tri(gl1)
    write_raster(ELEV_DIR / "srtm-gl1_slope-horn_30m_glen-innes.tif",
                 gl1_slope, gl1_profile, scale=0.01)
    write_raster(ELEV_DIR / "srtm-gl1_tri_30m_glen-innes.tif",
                 gl1_tri, gl1_profile, scale=0.1)

    out.write("## Derived rasters\n\n")
    out.write("| File | Source DEM | Variable | Units |\n|---|---|---|---|\n")
    out.write("| `srtm-gl3_slope-horn_90m_new-england-rez.tif` | GL3 ~90 m | Horn slope | degrees |\n")
    out.write("| `srtm-gl1_slope-horn_30m_glen-innes.tif` | GL1 ~30 m | Horn slope | degrees |\n")
    out.write("| `srtm-gl1_tri_30m_glen-innes.tif` | GL1 ~30 m | Riley TRI | metres |\n\n")

    # --- Evidence 1: GL1 vs GL3 slope over the same ground --------------------
    # Crop the GL3 slope to the GL1 sub-window and compare against GL1 slope
    # aggregated 3x3 to the same ~90 m footprint.
    from rasterio.windows import from_bounds
    win = from_bounds(*gl1_bounds, transform=gl3_transform).round_offsets().round_lengths()
    r0, c0 = int(win.row_off), int(win.col_off)
    gl3_sub_slope = gl3_slope[r0:r0 + int(win.height), c0:c0 + int(win.width)]
    gl1_slope_at90 = block_stat(gl1_slope, 3, "mean")
    n = min(gl3_sub_slope.shape[0], gl1_slope_at90.shape[0])
    m = min(gl3_sub_slope.shape[1], gl1_slope_at90.shape[1])
    a, b = gl1_slope_at90[:n, :m], gl3_sub_slope[:n, :m]
    diff = a - b

    out.write("## Evidence 1 — GL1 (30 m) vs GL3 (90 m) slope, wind-farm sub-window\n\n")
    out.write("GL1 slope was computed at 30 m then averaged 3x3 to the GL3 footprint;\n"
              "GL3 slope was computed directly at 90 m. GA advises that unsmoothed\n"
              "1-second SRTM is noisy for terrain attributes; this measures what that\n"
              "means at screening scale.\n\n")
    out.write("| Product | Mean | Median | P90 | Max |\n|---|---|---|---|---|\n")
    out.write(dist_row("GL1 slope aggregated to 90 m", a) + "\n")
    out.write(dist_row("GL3 slope computed at 90 m", b) + "\n")
    out.write(f"\nPer-pixel difference (GL1-at-90m minus GL3): mean {diff.mean():+.2f} deg, "
              f"mean absolute {np.abs(diff).mean():.2f} deg, P95 absolute "
              f"{np.percentile(np.abs(diff), 95):.2f} deg.\n\n")

    # --- Evidence 2: aggregation statistic to the 0.05 deg analysis grid ------
    block = int(round(CELL_DEG / gl3_transform.a))  # GL3 pixels per cell edge
    out.write("## Evidence 2 — slope aggregated to the 0.05 deg (~5 km) analysis grid\n\n")
    out.write(f"GL3 slope aggregated in {block} x {block}-pixel blocks over the full\n"
              "study window (40 x 40 cells; the sample grid is offset from the exact\n"
              "0.05-degree lattice by half a GL3 pixel, ~46 m, immaterial as evidence).\n\n")
    cells = {stat: block_stat(gl3_slope, block, stat) for stat in ("mean", "max", "p90")}
    out.write("| Statistic | Cell mean | Cell median | Cell P90 | Cell max |\n"
              "|---|---|---|---|---|\n")
    for stat, arr in cells.items():
        out.write(dist_row(f"{stat} of 90 m slope per cell", arr) + "\n")
    out.write("\n### Share of cells crossing candidate thresholds\n\n")
    out.write("| Threshold | mean | max | p90 |\n|---|---|---|---|\n")
    for thr in THRESHOLDS_DEG:
        shares = [100.0 * float((cells[s] > thr).mean()) for s in ("mean", "max", "p90")]
        out.write(f"| > {thr:.0f} deg | " + " | ".join(f"{s:.1f}%" for s in shares) + " |\n")
    out.write(
        "\nReading: a max-based rule excludes far more cells than a mean-based rule at\n"
        "the same threshold — the statistic is as consequential as the threshold\n"
        "itself. Decision deferred to Task 5.\n\n"
    )

    # --- Caveats ---------------------------------------------------------------
    out.write("## Caveats\n\n")
    out.write("- SRTM GL1/GL3 are unsmoothed; GA's DEM-S (smoothed) is the recommended\n"
              "  base for terrain attributes but is not scriptably accessible (HTTP 403,\n"
              "  see source register). Evidence 1 bounds the consequence at screening scale.\n")
    out.write("- Slope rasters are stored as int16 with a 0.01-degree scale factor and\n"
              "  TRI with a 0.1-metre scale factor (declared in the GeoTIFF band scales);\n"
              "  quantisation error is far below the method error.\n")
    out.write("- The GL3 mosaic declares nodata=0, which conflates sea level with voids;\n"
              "  this inland window contains no zero pixels (see inspection reports).\n")

    report_path = META_DIR / "slope_derivation.md"
    atomic_write_text(report_path, out.getvalue())
    print(f"\nReport: {report_path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
