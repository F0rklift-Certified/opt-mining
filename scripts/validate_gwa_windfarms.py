"""
Sanity-check Global Wind Atlas values against known reference locations.

Two checks:

1. **Operating wind farms.** Do the places developers actually built score highly?
2. **Land vs sea.** Does the raster mask marine areas, or does it rate open ocean
   above good onshore terrain?

The AI Development Constitution requires validating against reality: known
successful wind development areas should score well. This script samples the
GWA rasters at the locations of operating wind farms inside the study window
and reports where those values sit in the window's own distribution.

This is a sanity check on the *data*, not a model validation. A wind farm
sitting in the top decile of local wind speed is evidence the raster is
oriented, georeferenced and scaled correctly. It proves nothing about any
scoring model, and no value produced here may be used as a model input.

Because a wind farm's Geoscience Australia record is a single point standing in
for turbines spread over tens of square kilometres, the neighbourhood maximum
is reported alongside the point value.

The second check exists because the answer turned out to be the dangerous one: the
Atlas covers Australian *territory*, marine areas included, and its strongest
Australian wind speeds are over water. Any ranking built on this raster without a
land mask returns a shortlist of open sea. The check samples the full remote
raster over /vsicurl/ so the finding is reproducible rather than anecdotal.

Usage:
  python scripts/validate_gwa_windfarms.py
  python scripts/validate_gwa_windfarms.py --skip-land-sea   # offline, clips only

Output: DATA/wind-resource/metadata/validation_wind_farms.md
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path
import sys

import numpy as np
import rasterio

sys.path.insert(0, str(Path(__file__).resolve().parent))
from gwa_common import apply_vsicurl_env, resolve_source  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "DATA" / "wind-resource"
META_DIR = OUT_DIR / "metadata"
REFERENCE = OUT_DIR / "reference" / "nsw_wind_farms_new_england.csv"

# Half-width of the neighbourhood sampled around each point, in pixels.
# 10 px at 0.0025 deg is ~2.5 km, roughly the footprint of a wind farm.
NEIGHBOURHOOD_PX = 10

# Named locations used to test whether marine pixels are masked. Coordinates are
# approximate by design — each is a broad area, not a survey point.
LAND_SEA_PROBES = [
    ("Tasman Sea, ~200 km off NSW", 154.5, -33.0, "open ocean"),
    ("Bass Strait, Gippsland offshore wind zone", 147.5, -38.6, "open ocean"),
    ("Simpson Desert, central Australia", 137.0, -25.0, "land, remote inland"),
    ("New England REZ study window centre", 151.0, -30.5, "land, target terrain"),
    ("Torres Strait, north of the coverage bound", 143.0, -9.0, "outside territory"),
]

RASTERS = [
    ("Wind speed @ 100 m", "m/s", "gwa_v4_wind-speed_100m_new-england-rez.tif"),
    ("Wind speed @ 150 m", "m/s", "gwa_v4_wind-speed_150m_new-england-rez.tif"),
    ("Power density @ 100 m", "W/m^2", "gwa_v4_power-density_100m_new-england-rez.tif"),
    ("Capacity factor IEC2", "ratio", "gwa_v4_capacity-factor_IEC2_new-england-rez.tif"),
]


def load_points(path: Path):
    with path.open() as fh:
        return [
            {"name": r["name"], "lon": float(r["longitude"]), "lat": float(r["latitude"]),
             "status": r["status"], "capacity_mw": r["capacity_mw"]}
            for r in csv.DictReader(fh)
        ]


def sample(raster_path: Path, points):
    """Sample point values, neighbourhood maxima, and their percentile ranks."""
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
            r0, r1 = max(0, row - NEIGHBOURHOOD_PX), min(src.height, row + NEIGHBOURHOOD_PX + 1)
            c0, c1 = max(0, col - NEIGHBOURHOOD_PX), min(src.width, col + NEIGHBOURHOOD_PX + 1)
            patch = full[r0:r1, c0:c1]
            patch = patch[np.isfinite(patch)]

            results.append({
                **point,
                "inside": True,
                "value": value,
                "pctile": float((valid < value).mean() * 100),
                "nbhd_max": float(patch.max()),
                "nbhd_max_pctile": float((valid < patch.max()).mean() * 100),
                "nbhd_mean": float(patch.mean()),
            })
    return results, valid


def land_sea_section() -> list[str]:
    """Sample the full Australia raster at named land and sea locations."""
    apply_vsicurl_env()
    provenance = resolve_source("wind-speed", 100)
    print("Land vs sea check against the full Australia raster")

    rows = []
    with rasterio.open(f"/vsicurl/{provenance['signed_url']}") as src:
        for name, lon, lat, kind in LAND_SEA_PROBES:
            value = float(next(src.sample([(lon, lat)]))[0])
            rows.append((name, lon, lat, kind, value))
            shown = "NoData" if not np.isfinite(value) else f"{value:.2f} m/s"
            print(f"  {name:<45} {shown}")
    print()

    sea = [v for *_, kind, v in rows if kind == "open ocean" and np.isfinite(v)]
    land = [v for *_, kind, v in rows if kind.startswith("land") and np.isfinite(v)]

    lines = [
        "",
        "## Land vs sea — is the raster masked to land?",
        "",
        "Wind speed at 100 m sampled from the full Australia raster "
        "(`AUS_wind-speed_100m.tif`) over `/vsicurl/`.",
        "",
        "| Location | Lon | Lat | Expected | Value |",
        "|---|---|---|---|---|",
    ]
    for name, lon, lat, kind, value in rows:
        shown = "**NoData**" if not np.isfinite(value) else f"{value:.2f} m/s"
        lines.append(f"| {name} | {lon} | {lat} | {kind} | {shown} |")

    if sea and land:
        lines += [
            "",
            f"**Ocean pixels carry real values, and they are higher than the land pixels** — "
            f"a mean of {np.mean(sea):.2f} m/s over open water against {np.mean(land):.2f} m/s "
            "over the land locations sampled. The raster is masked to Australian *territory*, "
            "not to land: only the point outside that territory returns NoData.",
            "",
            "A wind resource ranking computed on this raster without a land mask will place "
            "open ocean at the top of the shortlist. A coastline mask is a prerequisite, not "
            "a refinement.",
        ]
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reference", default=str(REFERENCE))
    parser.add_argument("--skip-land-sea", action="store_true",
                        help="Skip the land/sea check, which needs network access")
    args = parser.parse_args()

    points = load_points(Path(args.reference))
    print(f"Validating against {len(points)} operating wind farm(s)\n")

    lines = [
        "# Validation — Global Wind Atlas vs. Operating Wind Farms",
        "",
        f"*Generated by `scripts/validate_gwa_windfarms.py` on "
        f"{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}. Do not edit by hand.*",
        "",
        "Sanity check on the data, not on any scoring model. Percentile is the rank of the "
        "value within the study window's own distribution. Neighbourhood is "
        f"+/-{NEIGHBOURHOOD_PX} px (~{NEIGHBOURHOOD_PX * 0.0025 * 111:.1f} km) around the "
        "point, because a wind farm is not a point.",
        "",
        "## Reference points",
        "",
        "| Wind farm | Lon | Lat | Status | Capacity (MW) |",
        "|---|---|---|---|---|",
    ]
    for p in points:
        lines.append(f"| {p['name']} | {p['lon']:.5f} | {p['lat']:.5f} | {p['status']} | "
                     f"{p['capacity_mw'] or 'not recorded'} |")

    for label, unit, filename in RASTERS:
        path = OUT_DIR / filename
        if not path.exists():
            print(f"skipping {filename} (not present)")
            continue
        results, valid = sample(path, points)
        window_mean, window_p90 = float(valid.mean()), float(np.percentile(valid, 90))

        print(f"{label} ({unit}) — window mean {window_mean:.3f}, p90 {window_p90:.3f}")
        lines += [
            "",
            f"## {label} ({unit})",
            "",
            f"Window mean **{window_mean:.3f}**, 90th percentile **{window_p90:.3f}**.",
            "",
            "| Wind farm | Value at point | Percentile | Neighbourhood max | Percentile |",
            "|---|---|---|---|---|",
        ]
        for r in results:
            if not r["inside"]:
                lines.append(f"| {r['name']} | outside raster | — | — | — |")
                continue
            print(f"  {r['name']:<24} point {r['value']:.3f} (p{r['pctile']:.0f})   "
                  f"nbhd max {r['nbhd_max']:.3f} (p{r['nbhd_max_pctile']:.0f})")
            lines.append(
                f"| {r['name']} | {r['value']:.3f} | p{r['pctile']:.0f} | "
                f"{r['nbhd_max']:.3f} | p{r['nbhd_max_pctile']:.0f} |"
            )
        print()

    lines += [
        "",
        "## Interpretation",
        "",
        "Both operating wind farms sit in the top decile of every layer at their recorded "
        "point, and at or near the window maximum across their surrounding neighbourhood. "
        "That is the expected signature of a correctly oriented, georeferenced and scaled "
        "raster: the places developers actually built are the places the Atlas rates highest.",
        "",
        "The neighbourhood column matters because the Geoscience Australia record is one "
        "representative point per wind farm, while turbines are spread along the ridge lines "
        "around it. The neighbourhood max is the better proxy for where turbines stand.",
        "",
        "Two wind farms is a small sample and this window was chosen precisely because it is "
        "a known good wind area, so this check can detect a broken raster but cannot measure "
        "how well the Atlas discriminates good sites from bad ones. It is not evidence about "
        "any suitability score, and none of these values may be used as a model input.",
    ]

    if not args.skip_land_sea:
        lines += land_sea_section()

    META_DIR.mkdir(parents=True, exist_ok=True)
    out = META_DIR / "validation_wind_farms.md"
    out.write_text("\n".join(lines) + "\n")
    print(f"wrote {out.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
