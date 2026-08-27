"""
Wind validate stage — domain-specific validation of wind resource data.

Part 1: Sample GWA rasters at known wind farm locations and report
         percentile rankings.
Part 2: Cross-check windowed clips against independently downloaded rasters.

Cross-domain checks (wind-farm-on-land, wind-farm-outside-CAPAD, slope)
live in the top-level pipeline/validate.py integration stage.

Importable entry point:
    from pipeline.wind.validate import run
    result = run(verbose=False, prototype_path=None, skip_land_sea=False)

Output:
    DATA/wind-resource/metadata/validation_wind_farms.md
    DATA/wind-resource/metadata/crosscheck_prototype.md
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import rasterio
from rasterio.windows import from_bounds

from . import config
from .gwa import apply_vsicurl_env, resolve_source
from ..common.geo import atomic_write_text


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NEIGHBOURHOOD_PX = 10

LAND_SEA_PROBES = [
    ("Tasman Sea, ~200 km off NSW", 154.5, -33.0, "open ocean"),
    ("Bass Strait, Gippsland offshore wind zone", 147.5, -38.6, "open ocean"),
    ("Simpson Desert, central Australia", 137.0, -25.0, "land, remote inland"),
    ("New England REZ study window centre", 151.0, -30.5, "land, target terrain"),
    ("Torres Strait, north of the coverage bound", 143.0, -9.0, "outside territory"),
]

WIND_RASTERS = [
    ("Wind speed @ 100 m", "m/s", "gwa_v4_wind-speed_100m_new-england-rez.tif"),
    ("Wind speed @ 150 m", "m/s", "gwa_v4_wind-speed_150m_new-england-rez.tif"),
    ("Power density @ 100 m", "W/m^2", "gwa_v4_power-density_100m_new-england-rez.tif"),
    ("Capacity factor IEC2", "ratio", "gwa_v4_capacity-factor_IEC2_new-england-rez.tif"),
]

# Crosscheck pairs: (prototype filename, local clip filename)
_CROSSCHECK_PAIRS = [
    ("AUS_wind-speed_100m.tif", "gwa_v4_wind-speed_100m_new-england-rez.tif"),
    ("AUS_power-density_100m.tif", "gwa_v4_power-density_100m_new-england-rez.tif"),
]

# Default prototype location
DEFAULT_PROTOTYPE_PATH = Path.home() / "Documents" / "Projects" / "OptMining"


# ---------------------------------------------------------------------------
# Wind farm sampling
# ---------------------------------------------------------------------------


def _load_wind_farm_points(path: Path) -> list[dict]:
    with path.open() as fh:
        return [
            {"name": r["name"], "lon": float(r["longitude"]), "lat": float(r["latitude"]),
             "status": r["status"], "capacity_mw": r["capacity_mw"]}
            for r in csv.DictReader(fh)
        ]


def _sample_wind_raster(raster_path: Path, points: list[dict]):
    """Sample point values and neighbourhood maxima."""
    with rasterio.open(raster_path) as src:
        full = src.read(1)
        valid = full[np.isfinite(full)]
        results = []
        for point in points:
            row, col = src.index(point["lon"], point["lat"])
            if not (0 <= row < src.height and 0 <= col < src.width):
                results.append({**point, "inside": False})
                continue
            value = float(full[row, col])
            r0 = max(0, row - NEIGHBOURHOOD_PX)
            r1 = min(src.height, row + NEIGHBOURHOOD_PX + 1)
            c0 = max(0, col - NEIGHBOURHOOD_PX)
            c1 = min(src.width, col + NEIGHBOURHOOD_PX + 1)
            patch = full[r0:r1, c0:c1]
            patch = patch[np.isfinite(patch)]
            results.append({
                **point, "inside": True, "value": value,
                "pctile": float((valid < value).mean() * 100),
                "nbhd_max": float(patch.max()),
                "nbhd_max_pctile": float((valid < patch.max()).mean() * 100),
                "nbhd_mean": float(patch.mean()),
            })
    return results, valid


def _land_sea_section(verbose: bool = False) -> list[str]:
    """Sample the full Australia raster at named land and sea locations."""
    apply_vsicurl_env()
    provenance = resolve_source("wind-speed", 100)
    rows = []
    with rasterio.open(f"/vsicurl/{provenance['signed_url']}") as src:
        for name, lon, lat, kind in LAND_SEA_PROBES:
            value = float(next(src.sample([(lon, lat)]))[0])
            rows.append((name, lon, lat, kind, value))
    sea = [v for *_, kind, v in rows if kind == "open ocean" and np.isfinite(v)]
    land = [v for *_, kind, v in rows if kind.startswith("land") and np.isfinite(v)]

    lines = [
        "", "## Land vs sea — is the raster masked to land?", "",
        "Wind speed at 100 m sampled from the full Australia raster over `/vsicurl/`.", "",
        "| Location | Lon | Lat | Expected | Value |", "|---|---|---|---|---|",
    ]
    for name, lon, lat, kind, value in rows:
        shown = "**NoData**" if not np.isfinite(value) else f"{value:.2f} m/s"
        lines.append(f"| {name} | {lon} | {lat} | {kind} | {shown} |")
    if sea and land:
        lines += [
            "",
            f"**Ocean pixels carry real values** — mean {np.mean(sea):.2f} m/s over water "
            f"vs {np.mean(land):.2f} m/s over land. A land mask is mandatory.",
        ]
    return lines


def _run_wind_farm_validation(verbose: bool, skip_land_sea: bool) -> Path:
    """Validate GWA rasters against known wind farms."""
    ref_path = config.WIND_REF_DIR / "nsw_wind_farms_new_england.csv"
    if not ref_path.exists():
        raise FileNotFoundError(f"Reference file not found: {ref_path}")
    points = _load_wind_farm_points(ref_path)

    lines = [
        "# Validation — Global Wind Atlas vs. Operating Wind Farms", "",
        f"*Generated by `pipeline.wind.validate` on "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}. Do not edit by hand.*", "",
        f"Neighbourhood: +/-{NEIGHBOURHOOD_PX} px "
        f"(~{NEIGHBOURHOOD_PX * 0.0025 * 111:.1f} km).", "",
        "## Reference points", "",
        "| Wind farm | Lon | Lat | Status | Capacity (MW) |", "|---|---|---|---|---|",
    ]
    for p in points:
        lines.append(f"| {p['name']} | {p['lon']:.5f} | {p['lat']:.5f} | "
                     f"{p['status']} | {p['capacity_mw'] or 'not recorded'} |")

    for label, unit, filename in WIND_RASTERS:
        path = config.WIND_DIR / filename
        if not path.exists():
            continue
        results, valid = _sample_wind_raster(path, points)
        window_mean = float(valid.mean())
        window_p90 = float(np.percentile(valid, 90))
        lines += [
            "", f"## {label} ({unit})", "",
            f"Window mean **{window_mean:.3f}**, P90 **{window_p90:.3f}**.", "",
            "| Wind farm | Value | Percentile | Nbhd max | Percentile |",
            "|---|---|---|---|---|",
        ]
        for r in results:
            if not r["inside"]:
                lines.append(f"| {r['name']} | outside | — | — | — |")
            else:
                lines.append(
                    f"| {r['name']} | {r['value']:.3f} | p{r['pctile']:.0f} | "
                    f"{r['nbhd_max']:.3f} | p{r['nbhd_max_pctile']:.0f} |"
                )

    if not skip_land_sea:
        lines += _land_sea_section(verbose)

    out = config.WIND_META_DIR / "validation_wind_farms.md"
    config.WIND_META_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out, "\n".join(lines) + "\n")
    return out


# ---------------------------------------------------------------------------
# Crosscheck against prototype
# ---------------------------------------------------------------------------


def _run_crosscheck(prototype_path: Path | None, verbose: bool) -> Path | None:
    """Cross-check windowed clips against independently downloaded rasters."""
    proto = prototype_path or DEFAULT_PROTOTYPE_PATH
    gwa_dir = proto / "data" / "raw" / "gwa"
    out = config.WIND_META_DIR / "crosscheck_prototype.md"

    if not gwa_dir.is_dir():
        print("    Prototype rasters not found — skipping crosscheck (not a failure)")
        return None

    lines = [
        "# Cross-Check — Windowed Reads vs. Independently Downloaded Raster", "",
        f"*Generated by `pipeline.wind.validate` on "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}. Do not edit by hand.*", "",
        f"Reference: `{gwa_dir}`", "",
        "## Checksums", "",
        "| File | Recorded SHA-256 | Verifies? |", "|---|---|---|",
    ]
    for full_name, _ in _CROSSCHECK_PAIRS:
        full = gwa_dir / full_name
        sidecar = gwa_dir / f"{full_name}.sha256.json"
        if not (full.is_file() and sidecar.is_file()):
            continue
        recorded = json.loads(sidecar.read_text())["sha256"]
        digest = hashlib.sha256()
        with full.open("rb") as fh:
            for block in iter(lambda: fh.read(1 << 22), b""):
                digest.update(block)
        ok = digest.hexdigest() == recorded
        lines.append(f"| `{full_name}` | `{recorded[:16]}…` | {'Yes' if ok else '**No**'} |")

    lines += ["", "## Pixel comparison", "",
              "| File | Identical? | Max abs diff |", "|---|---|---|"]
    results = []
    for full_name, clip_name in _CROSSCHECK_PAIRS:
        full, clip = gwa_dir / full_name, config.WIND_DIR / clip_name
        if not (full.is_file() and clip.is_file()):
            continue
        with rasterio.open(full) as src:
            window = from_bounds(*config.DEFAULT_BBOX, transform=src.transform)
            window = window.round_offsets().round_lengths()
            reference = src.read(1, window=window)
        with rasterio.open(clip) as src:
            sampled = src.read(1)
        identical = bool(np.array_equal(reference, sampled, equal_nan=True))
        finite = np.isfinite(reference) & np.isfinite(sampled)
        max_diff = float(np.abs(reference[finite] - sampled[finite]).max()) if finite.any() else 0.0
        results.append(identical)
        lines.append(f"| `{full_name}` | {'**Yes**' if identical else 'No'} | {max_diff:.10g} |")

    all_ok = results and all(results)
    lines += ["", "## Conclusion", "",
              "Two independent retrievals return the same pixels." if all_ok else
              "**Disagreement detected — investigate.**"]

    config.WIND_META_DIR.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out, "\n".join(lines) + "\n")
    return out


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(
    verbose: bool = False,
    prototype_path: Path | None = None,
    skip_land_sea: bool = False,
) -> dict:
    """
    Validate wind resource data against ground truth.

    Returns a summary dict with output paths.
    """
    results: dict[str, Path | None] = {}

    print("  Validating wind rasters against wind farms...")
    results["wind_farms"] = _run_wind_farm_validation(verbose, skip_land_sea)
    print(f"    → {results['wind_farms'].relative_to(config.PROJECT_ROOT)}")

    print("  Cross-checking against prototype...")
    results["crosscheck"] = _run_crosscheck(prototype_path, verbose)
    if results["crosscheck"]:
        print(f"    → {results['crosscheck'].relative_to(config.PROJECT_ROOT)}")

    return results
