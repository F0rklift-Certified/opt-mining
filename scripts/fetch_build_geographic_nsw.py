#!/usr/bin/env python3
"""
Full-NSW geographic fetch + build runner.

Re-runs the geographic feature builder over the WHOLE NSW analysis grid instead
of the New-England-REZ study window, to close the S2-02 missing-value coverage
gap for ``elevation_m``, ``slope_deg`` and ``land_use``.

What it does (all with the existing, frozen pipeline code — nothing is
fabricated or hand-edited):

  1. Download step: drives ``pipeline.geographic.download.run`` with the full-NSW
     grid bbox. This clips the SRTM GL3 elevation mosaic (OpenTopography global
     VRT, read via GDAL /vsicurl/) and the ABARES NLUM national land-use raster
     to the NSW extent, writing:
         DATA/geographic/elevation/srtm-gl3_elevation_90m_nsw.tif
         DATA/geographic/landuse/abares_nlum-alumv8_2020-21_nsw.tif
     These are REAL national sources clipped to NSW — the same fetch path that
     produced the New England clips, just with a wider bbox.

  2. Derive step: computes the Horn slope raster from the NSW DEM using the exact
     frozen slope algorithm (``pipeline.geographic.derive.horn_slope_deg``),
     writing:
         DATA/geographic/elevation/srtm-gl3_slope-horn_90m_nsw.tif

  3. Build step: drives ``pipeline.geographic.features.run`` with the NSW raster
     paths (the builder now accepts source-path overrides; defaults are unchanged
     so every other caller is unaffected). It re-writes:
         DATA/geographic/features/optmining_geographic-features_2024_nsw.gpkg
     with elevation_m / slope_deg / land_use populated for every NSW cell that
     the national rasters actually cover. Cells still outside coverage stay null
     and low-confidence — the builder never back-fills.

Honesty guarantees:
  - No coordinates, elevations, slopes or land-use codes are invented. Every
    value comes from a real national raster sampled at the cell.
  - Any cell the national raster genuinely does not cover remains null. If NSW
    is fully covered by SRTM/NLUM (it is — both are national/global products),
    the missing-value counts for these three columns should drop to ~0.
  - TRI is intentionally NOT extended here: it is excluded from the confidence
    decision by design and is not one of the failing scored columns. It keeps
    its existing Glen-Innes sub-window source.

NETWORK: steps 1 downloads from OpenTopography (SRTM VRT) and ABARES (NLUM zip,
~64 MB, cached in DATA/geographic/raw/). A full-NSW GL3 clip is materially larger
than the committed New England sample; it is written under DATA/geographic/ and
is expected to exceed the repo's commit guardrail — treat these NSW rasters as
regenerable local artefacts (gitignore them), not committed samples.

Usage:
    python -m scripts.fetch_build_geographic_nsw            # full: download+derive+build
    python -m scripts.fetch_build_geographic_nsw --skip-download   # reuse existing NSW rasters
    python -m scripts.fetch_build_geographic_nsw --verbose

The grid (DATA/grid/nsw_analysis_grid.gpkg) must already exist; run
``python -m pipeline --only grid`` first if it does not.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import rasterio

from pipeline.common.geo import apply_vsicurl_env
from pipeline.geographic import config as geo_config
from pipeline.geographic import download as geo_download
from pipeline.geographic import features as geo_features
from pipeline.geographic.derive import horn_slope_deg, _write_raster

# The full-NSW analysis-grid extent, snapped to the GWA lattice (identical to the
# bbox documented in pipeline/README.md for the NSW-wide wind clip). This is the
# exact extent of DATA/grid/nsw_analysis_grid.gpkg.
NSW_BBOX = (141.01125, -37.51125, 153.66125, -28.16125)
NSW_AREA = "nsw"

ELEV_DIR = geo_config.GEO_DIR / "elevation"
LANDUSE_DIR = geo_config.GEO_DIR / "landuse"

NSW_ELEVATION_PATH = ELEV_DIR / f"srtm-gl3_elevation_90m_{NSW_AREA}.tif"
NSW_SLOPE_PATH = ELEV_DIR / f"srtm-gl3_slope-horn_90m_{NSW_AREA}.tif"
NSW_NLUM_PATH = LANDUSE_DIR / f"abares_nlum-alumv8_2020-21_{NSW_AREA}.tif"

# TRI keeps its existing sub-window source: it is excluded from the confidence
# decision by design and is not one of the failing scored columns.
DEFAULT_TRI_PATH = geo_features.TRI_PATH
# CAPAD protected areas are already statewide-NSW; reuse the frozen source.
DEFAULT_CAPAD_PATH = geo_features.CAPAD_PATH


def download_nsw_rasters(verbose: bool = False) -> None:
    """Clip the national SRTM GL3 + NLUM rasters to the full-NSW extent.

    Fetches ONLY the two rasters this build needs, by calling the download
    stage's raster helpers directly. It deliberately does NOT run the combined
    ``geo_download.run`` (vectors + rasters): with ``area_name='nsw'`` the vector
    stage's "CAPAD window extract" would write to the same
    ``dcceew_capad-terrestrial_2024_nsw.geojson`` filename as the statewide CAPAD
    fetch and clobber it (and pull a 100 MB+ full-resolution statewide extract).
    The statewide CAPAD file already on disk is the correct protected-area source
    and is left untouched; the GL1 Glen-Innes sub-window and TRI are likewise
    left as-is (not needed for the NSW scored columns).
    """
    print("[1/3] Downloading full-NSW geographic rasters (SRTM GL3 + ABARES NLUM)...")
    print(f"      bbox {NSW_BBOX}  area-name '{NSW_AREA}'")
    print("      NOTE: national sources clipped to NSW; the GL3 clip is much larger")
    print("            than the New England sample — treat as a regenerable artefact.")
    print("      (rasters only — vectors/CAPAD left untouched)")

    apply_vsicurl_env()

    # SRTM GL3 elevation, clipped to the full-NSW extent -> ..._nsw.tif
    geo_download._fetch_srtm(
        geo_config.SRTM_GL3_VRT,
        NSW_BBOX,
        NSW_ELEVATION_PATH,
        "SRTM GL3 elevation, 3 arc-second (~90 m), full NSW",
        verbose,
    )
    if not NSW_ELEVATION_PATH.exists():
        raise SystemExit(
            f"Expected NSW DEM was not produced: {NSW_ELEVATION_PATH}. "
            f"Check the SRTM download output above for a network/source failure."
        )

    # ABARES NLUM land use, clipped to the full-NSW extent -> ..._nsw.tif.
    # _fetch_nlum names its output from area_name, and re-extracts the ALUM class
    # table (idempotent — same table the New England clip used).
    geo_download._fetch_nlum(NSW_BBOX, NSW_AREA, verbose)
    if not NSW_NLUM_PATH.exists():
        raise SystemExit(
            f"Expected NSW NLUM clip was not produced: {NSW_NLUM_PATH}. "
            f"Check the NLUM download output above for a network/source failure."
        )


def derive_nsw_slope(verbose: bool = False) -> None:
    """Compute the Horn slope raster from the NSW DEM (frozen algorithm)."""
    print("[2/3] Deriving full-NSW slope from the NSW DEM (Horn 3x3)...")
    if not NSW_ELEVATION_PATH.exists():
        raise SystemExit(
            f"NSW DEM missing: {NSW_ELEVATION_PATH}. Run the download step first "
            f"(omit --skip-download)."
        )
    with rasterio.open(NSW_ELEVATION_PATH) as src:
        dem = src.read(1)
        profile = src.profile.copy()
        transform = src.transform
    slope = horn_slope_deg(dem, transform)
    # Same int16 storage + 0.01-degree scale factor as the frozen derive stage.
    _write_raster(NSW_SLOPE_PATH, slope, profile, scale=0.01)
    if verbose:
        size = NSW_SLOPE_PATH.stat().st_size
        print(f"      wrote {NSW_SLOPE_PATH.relative_to(geo_config.PROJECT_ROOT)} "
              f"({size:,} bytes)")


def build_nsw_features(verbose: bool = False) -> dict:
    """Re-run the geographic feature builder against the NSW rasters."""
    print("[3/3] Building geographic features over full NSW...")
    for path, label in (
        (NSW_ELEVATION_PATH, "NSW DEM"),
        (NSW_SLOPE_PATH, "NSW slope"),
        (NSW_NLUM_PATH, "NSW NLUM"),
    ):
        if not path.exists():
            raise SystemExit(
                f"{label} missing: {path}. Run the download and derive steps first."
            )
    summary = geo_features.run(
        verbose=verbose,
        elevation_path=NSW_ELEVATION_PATH,
        slope_path=NSW_SLOPE_PATH,
        tri_path=DEFAULT_TRI_PATH,
        nlum_path=NSW_NLUM_PATH,
        capad_path=DEFAULT_CAPAD_PATH,
    )
    print(f"      Feature table re-written: {summary['feature_table']}")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--skip-download", action="store_true",
        help="reuse existing NSW rasters instead of re-fetching them",
    )
    parser.add_argument(
        "--skip-derive", action="store_true",
        help="reuse the existing NSW slope raster instead of re-deriving it",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    grid_path = geo_features.GRID_PATH
    if not Path(grid_path).exists():
        print(
            f"ERROR: analysis grid missing: {grid_path}\n"
            f"Run 'python -m pipeline --only grid' first.",
            file=sys.stderr,
        )
        return 2

    if not args.skip_download:
        download_nsw_rasters(verbose=args.verbose)
    else:
        print("[1/3] Skipping download (reusing existing NSW rasters).")

    if not args.skip_derive:
        derive_nsw_slope(verbose=args.verbose)
    else:
        print("[2/3] Skipping derive (reusing existing NSW slope raster).")

    summary = build_nsw_features(verbose=args.verbose)

    print(
        "\nDone. Full-NSW geographic features written to:\n"
        f"  {summary['feature_table']}\n"
        "Next: rebuild the integrated table and re-freeze/re-validate:\n"
        "  python -m scripts.refreeze_revalidate\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
