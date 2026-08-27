"""
Grid generation — produce the common analysis cell grid for NSW.

This module generates a GeoDataFrame of 0.05-degree rectangular cells covering
the NSW bounding box, aligned to the Global Wind Atlas v4 native pixel lattice.
Every cell is exactly 20x20 GWA pixels — no fractional overlaps, no boundary
ambiguity.

The grid is the spatial backbone of the Opt-Mining platform. All feature layers
(wind resource, demand, infrastructure, geographic suitability) join to this
grid via cell_id, enabling integrated scoring.

Public API:
    generate_grid() -> gpd.GeoDataFrame
        Pure computation — no I/O. Returns the full rectangular NSW grid.

    run(verbose=False) -> dict
        Generate, sanity-check, and write to GeoPackage + metadata JSON.

Architecture:
    CRS: EPSG:4326 (storage). Area computed via EPSG:3577 (Australian Albers).
    Cell ID: S{lat:.3f}_E{lon:.3f} using cell centroid coordinates.
    Land-masking: deferred to S1-06/S1-07. This grid is the full bounding box.

Constitution compliance:
    - CRS is explicit at every boundary (EPSG:4326 storage, EPSG:3577 for area)
    - Provenance: grid parameters trace to GWA v4 specification (Task 1)
    - Reproducibility: deterministic from constants — no random seeds, no network
"""

from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
from shapely.geometry import box

from . import config


# ---------------------------------------------------------------------------
# Grid geometry helpers
# ---------------------------------------------------------------------------


def _snap_origin(bbox: tuple[float, float, float, float]) -> tuple[float, float]:
    """
    Snap the grid origin to the GWA lattice.

    Returns (origin_lon, origin_lat) where:
    - origin_lon is the western edge of the first column, snapped UP from bbox west
    - origin_lat is the northern edge of the first row, snapped DOWN from bbox north

    Both are exact multiples of CELL_DEG offset from the GWA origin.
    """
    w, s, e, n = bbox

    # Snap west edge UP to nearest GWA-aligned cell boundary
    offset_lon = (w - config.GWA_ORIGIN_LON) / config.CELL_DEG
    origin_lon = config.GWA_ORIGIN_LON + math.ceil(offset_lon) * config.CELL_DEG

    # Snap north edge DOWN to nearest GWA-aligned cell boundary
    offset_lat = (config.GWA_ORIGIN_LAT - n) / config.CELL_DEG
    origin_lat = config.GWA_ORIGIN_LAT - math.ceil(offset_lat) * config.CELL_DEG

    return (origin_lon, origin_lat)


def _grid_dimensions(
    bbox: tuple[float, float, float, float],
    origin_lon: float,
    origin_lat: float,
) -> tuple[int, int]:
    """
    Compute grid dimensions (n_cols, n_rows) from the snapped origin to bbox extent.

    n_cols: number of complete cells fitting east of origin_lon within bbox east
    n_rows: number of complete cells fitting south of origin_lat within bbox south
    """
    _, s, e, _ = bbox
    n_cols = int(math.floor((e - origin_lon) / config.CELL_DEG))
    n_rows = int(math.floor((origin_lat - s) / config.CELL_DEG))
    return (n_cols, n_rows)


def _format_cell_id(centroid_lat: float, centroid_lon: float) -> str:
    """
    Format a cell ID from centroid coordinates.

    Format: S{lat:.3f}_E{lon:.3f} for Southern/Eastern hemisphere (NSW).
    Uses N/S for latitude, E/W for longitude.
    """
    lat_prefix = "S" if centroid_lat < 0 else "N"
    lon_prefix = "E" if centroid_lon >= 0 else "W"
    return f"{lat_prefix}{abs(centroid_lat):.3f}_{lon_prefix}{abs(centroid_lon):.3f}"


# ---------------------------------------------------------------------------
# Core grid generation
# ---------------------------------------------------------------------------


def generate_grid(
    bbox: tuple[float, float, float, float] | None = None,
) -> gpd.GeoDataFrame:
    """
    Generate the common analysis cell grid as a GeoDataFrame.

    Parameters
    ----------
    bbox : tuple of (west, south, east, north), optional
        Bounding box in EPSG:4326. Defaults to config.NSW_BBOX.

    Returns
    -------
    gpd.GeoDataFrame
        Grid with columns: cell_id, geometry, centroid_lat, centroid_lon, area_km2.
        CRS: EPSG:4326.

    Notes
    -----
    - Grid edges are snapped to the GWA v4 lattice so every cell is exactly
      20x20 native pixels (0.05 deg = 20 * 0.0025 deg).
    - area_km2 is computed by reprojecting each cell to EPSG:3577 (Australian
      Albers Equal Area) — the correct CRS for area calculations in Australia.
    - This generates the full rectangular bounding-box grid. Land-masking
      (removing ocean/interstate cells) is deferred to downstream tasks.
    """
    if bbox is None:
        bbox = config.NSW_BBOX

    # 1. Snap origin to GWA lattice
    origin_lon, origin_lat = _snap_origin(bbox)

    # 2. Compute grid dimensions
    n_cols, n_rows = _grid_dimensions(bbox, origin_lon, origin_lat)

    if n_cols <= 0 or n_rows <= 0:
        raise ValueError(
            f"Grid dimensions ({n_cols} cols x {n_rows} rows) are non-positive. "
            f"Check bbox={bbox} against GWA origin."
        )

    total_cells = n_cols * n_rows

    # 3. Generate cell geometries and attributes using vectorised numpy
    # Build arrays of column and row indices
    col_indices = np.arange(n_cols)
    row_indices = np.arange(n_rows)

    # Meshgrid: cols vary along axis=1, rows along axis=0
    cols, rows = np.meshgrid(col_indices, row_indices)
    cols_flat = cols.ravel()
    rows_flat = rows.ravel()

    # Cell edges
    west_edges = origin_lon + cols_flat * config.CELL_DEG
    east_edges = west_edges + config.CELL_DEG
    north_edges = origin_lat - rows_flat * config.CELL_DEG
    south_edges = north_edges - config.CELL_DEG

    # Centroids
    centroid_lons = (west_edges + east_edges) / 2.0
    centroid_lats = (north_edges + south_edges) / 2.0

    # Cell IDs
    cell_ids = [
        _format_cell_id(centroid_lats[i], centroid_lons[i])
        for i in range(total_cells)
    ]

    # Geometries (vectorised shapely box creation)
    geometries = [
        box(west_edges[i], south_edges[i], east_edges[i], north_edges[i])
        for i in range(total_cells)
    ]

    # 4. Build GeoDataFrame in EPSG:4326
    gdf = gpd.GeoDataFrame(
        {
            "cell_id": cell_ids,
            "centroid_lat": centroid_lats,
            "centroid_lon": centroid_lons,
        },
        geometry=geometries,
        crs=config.STORAGE_CRS,
    )

    # 5. Compute area_km2 via projection to EPSG:3577 (Australian Albers)
    gdf_albers = gdf.to_crs(config.COMPUTATION_CRS)
    gdf["area_km2"] = gdf_albers.geometry.area / 1_000_000.0  # m² → km²

    return gdf


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------


def run(verbose: bool = False) -> dict:
    """
    Generate the NSW analysis grid, sanity-check, and write to GeoPackage.

    Parameters
    ----------
    verbose : bool
        If True, print additional detail during generation.

    Returns
    -------
    dict
        Keys: 'grid_path', 'metadata_path', 'n_cells', 'n_cols', 'n_rows',
              'origin', 'cell_deg'.
    """
    print("  Generating NSW analysis grid...")
    print(f"    Cell size: {config.CELL_DEG}° "
          f"({config.CELL_FACTOR} native GWA pixels per side)")
    print(f"    GWA origin: ({config.GWA_ORIGIN_LON}, {config.GWA_ORIGIN_LAT})")
    print(f"    NSW bbox: {config.NSW_BBOX}")
    print(f"    Storage CRS: {config.STORAGE_CRS}")
    print(f"    Computation CRS: {config.COMPUTATION_CRS}")

    t0 = time.time()

    # Generate the grid
    gdf = generate_grid()

    elapsed = time.time() - t0
    n_cells = len(gdf)

    # Derive grid dimensions from the data
    origin_lon, origin_lat = _snap_origin(config.NSW_BBOX)
    n_cols, n_rows = _grid_dimensions(config.NSW_BBOX, origin_lon, origin_lat)

    # Representative cell dimensions at mid-latitude
    mid_lat = (config.NSW_BBOX[1] + config.NSW_BBOX[3]) / 2.0
    cell_width_km = (
        config.M_PER_DEG_LON_EQ * math.cos(math.radians(mid_lat)) * config.CELL_DEG
        / 1000.0
    )
    cell_height_km = config.M_PER_DEG_LAT * config.CELL_DEG / 1000.0

    print(f"\n  Grid generated in {elapsed:.1f}s:")
    print(f"    Dimensions: {n_cols} cols × {n_rows} rows = {n_cells:,} cells")
    print(f"    Origin (snapped): ({origin_lon:.5f}, {origin_lat:.5f})")
    print(f"    Cell size at {abs(mid_lat):.1f}°S: "
          f"{cell_width_km:.2f} km × {cell_height_km:.2f} km")
    print(f"    Area range: {gdf['area_km2'].min():.2f} – "
          f"{gdf['area_km2'].max():.2f} km²")

    # --- Sanity checks ---
    _sanity_check(gdf, n_cols, n_rows)

    # --- Write GeoPackage ---
    output_dir = config.GRID_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    grid_path = output_dir / "nsw_analysis_grid.gpkg"
    tmp_path = output_dir / "nsw_analysis_grid_tmp.gpkg"

    try:
        gdf.to_file(tmp_path, driver="GPKG", layer="nsw_grid")
        os.replace(tmp_path, grid_path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()

    file_size_mb = grid_path.stat().st_size / (1024 * 1024)
    print(f"\n  Output: {grid_path.relative_to(config.PROJECT_ROOT)} "
          f"({file_size_mb:.1f} MB)")

    # --- Write metadata sidecar ---
    metadata = {
        "description": "NSW common analysis cell grid for Opt-Mining platform",
        "task": "S1-02",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "crs_storage": config.STORAGE_CRS,
        "crs_computation": config.COMPUTATION_CRS,
        "cell_size_deg": config.CELL_DEG,
        "cell_factor": config.CELL_FACTOR,
        "gwa_origin": [config.GWA_ORIGIN_LON, config.GWA_ORIGIN_LAT],
        "gwa_step_deg": config.GWA_STEP_DEG,
        "grid_origin_snapped": [origin_lon, origin_lat],
        "bbox_nsw": list(config.NSW_BBOX),
        "n_cols": n_cols,
        "n_rows": n_rows,
        "total_cells": n_cells,
        "representative_cell_km": {
            "width_km": round(cell_width_km, 3),
            "height_km": round(cell_height_km, 3),
            "at_latitude": mid_lat,
        },
        "area_km2_range": {
            "min": round(float(gdf["area_km2"].min()), 3),
            "max": round(float(gdf["area_km2"].max()), 3),
            "mean": round(float(gdf["area_km2"].mean()), 3),
        },
        "land_masking": "Deferred to S1-06/S1-07. This grid is the full "
                        "rectangular bounding box.",
        "notes": [
            "Every cell edge aligns exactly with GWA v4 native pixel boundaries.",
            "Cell IDs encode centroid lat/lon for human readability.",
            "area_km2 computed via EPSG:3577 (Australian Albers Equal Area).",
        ],
    }

    metadata_path = output_dir / "nsw_analysis_grid_metadata.json"
    tmp_meta = metadata_path.with_suffix(".json.tmp")
    try:
        tmp_meta.write_text(json.dumps(metadata, indent=2) + "\n")
        os.replace(tmp_meta, metadata_path)
    finally:
        if tmp_meta.exists():
            tmp_meta.unlink()

    print(f"  Metadata: {metadata_path.relative_to(config.PROJECT_ROOT)}")

    if verbose:
        print(f"\n  Sample cells (first 5):")
        print(gdf[["cell_id", "centroid_lat", "centroid_lon", "area_km2"]].head().to_string(index=False))

    return {
        "grid_path": grid_path,
        "metadata_path": metadata_path,
        "n_cells": n_cells,
        "n_cols": n_cols,
        "n_rows": n_rows,
        "origin": (origin_lon, origin_lat),
        "cell_deg": config.CELL_DEG,
    }


# ---------------------------------------------------------------------------
# Sanity checks
# ---------------------------------------------------------------------------


def _sanity_check(gdf: gpd.GeoDataFrame, n_cols: int, n_rows: int) -> None:
    """
    Validate the generated grid against expected properties.

    Raises AssertionError with a descriptive message on failure.
    """
    expected_count = n_cols * n_rows

    # Cell count
    assert len(gdf) == expected_count, (
        f"Cell count mismatch: got {len(gdf)}, expected {expected_count} "
        f"({n_cols} × {n_rows})"
    )

    # CRS
    assert gdf.crs is not None, "GeoDataFrame has no CRS set"
    assert gdf.crs.to_epsg() == 4326, (
        f"Expected EPSG:4326, got EPSG:{gdf.crs.to_epsg()}"
    )

    # No null geometries
    null_geoms = gdf.geometry.isna().sum()
    assert null_geoms == 0, f"{null_geoms} null geometries found"

    # All geometries are valid
    invalid = (~gdf.geometry.is_valid).sum()
    assert invalid == 0, f"{invalid} invalid geometries found"

    # Unique cell IDs
    n_unique = gdf["cell_id"].nunique()
    assert n_unique == len(gdf), (
        f"Duplicate cell_ids: {len(gdf) - n_unique} duplicates found"
    )

    # Area range sanity (NSW spans roughly 28–38°S; cells should be 20–35 km²)
    min_area = gdf["area_km2"].min()
    max_area = gdf["area_km2"].max()
    assert min_area > 15.0, (
        f"Minimum area {min_area:.2f} km² is suspiciously small (< 15 km²)"
    )
    assert max_area < 40.0, (
        f"Maximum area {max_area:.2f} km² is suspiciously large (> 40 km²)"
    )

    # GWA alignment check (sample first cell)
    first_geom = gdf.geometry.iloc[0]
    west_edge = first_geom.bounds[0]  # minx
    offset_pixels = (west_edge - config.GWA_ORIGIN_LON) / config.GWA_STEP_DEG
    assert abs(offset_pixels - round(offset_pixels)) < 1e-8, (
        f"First cell west edge ({west_edge}) is not aligned to GWA lattice. "
        f"Offset = {offset_pixels} pixels (expected integer)."
    )

    print("  ✓ All sanity checks passed")
