"""
Coordinate join for the S1-11 shortlist stage (Requirement 4.2, 4.4, 4.5, 4.6).

After the pure selection core (`select.py`) has chosen the top-N Eligible_Cells
by their existing S1-10 `rank`, this module attaches each shortlisted cell's
map coordinates by joining `centroid_lat` / `centroid_lon` from the S1-02
Analysis_Grid on `cell_id`, in EPSG:4326.

Two rules are load-bearing and named here because a naive implementation would
silently lie about a candidate site's location:

  EXPLICIT CRS. The grid is read in EPSG:4326 and the coordinates are carried
  through unchanged — this stage performs NO reprojection (there is no distance
  or area computation here). The grid's declared CRS is checked against the
  storage CRS rather than assumed, mirroring `integration.merge.read_layer`
  (Constitution: never convert silently) (Requirement 4.2).

  NO FABRICATED COORDINATE. If ANY shortlisted `cell_id` has no matching grid
  row, the join HALTS before any output is written and names the unmatched
  `cell_id` — the stage never emits a shortlist row with a fabricated or null
  coordinate (Requirement 4.5).

`suitability_score`, `confidence` and `rank` come straight from the
Scored_Table (via the selected frame) and are carried through this join without
recomputation (Requirement 4.6). This module reads the grid but never
re-derives it, mirroring the fail-fast, path-naming style of `load.py`.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio
from pyproj import CRS

from . import config

# The coordinate columns joined from the Analysis_Grid on `cell_id`, expressed
# in EPSG:4326 (Requirement 4.2). These are the two grid columns the shortlist
# needs to place a candidate site on a map; everything else (score, confidence,
# rank) is carried through from the selected Scored_Table rows unchanged (4.6).
GRID_COORDINATE_COLUMNS = ("centroid_lat", "centroid_lon")

# Columns the grid must expose for the join: the `cell_id` key plus the two
# coordinate columns. An absent column is a fail-fast condition, named.
GRID_REQUIRED_COLUMNS = ("cell_id", *GRID_COORDINATE_COLUMNS)


def _crs_string(crs) -> str:
    """Normalise a CRS to 'AUTHORITY:CODE' where possible (else its WKT/PROJ string)."""
    parsed = CRS.from_user_input(crs)
    authority = parsed.to_authority()
    if authority:
        return f"{authority[0]}:{authority[1]}"
    return parsed.to_wkt()


def load_grid(
    path: Path | str | None = None,
    *,
    layer: str | None = None,
) -> gpd.GeoDataFrame:
    """
    Read the S1-02 Analysis_Grid as the source of `centroid_lat` /
    `centroid_lon` per cell.

    Halts BEFORE any output on:
      - a missing or unreadable grid file, naming the path                (4.4)
      - a grid with no declared CRS, or a CRS other than the storage CRS,
        rather than silently assuming or reprojecting EPSG:4326           (4.2)
      - any of ``GRID_REQUIRED_COLUMNS`` absent, or a null / duplicate
        ``cell_id`` that would make the join ambiguous

    The grid is read in EPSG:4326 and returned whole; this stage never
    re-derives the grid (Requirement 1.2 spirit / 4.2). Mirrors the fail-fast,
    path-naming discipline of `load.load_scored_table` and the explicit-CRS
    discipline of `integration.merge.read_layer`.
    """
    path = Path(path) if path is not None else config.GRID_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"Analysis_Grid not found: {path}. Run "
            f"`python -m pipeline --only grid` to generate it before the "
            f"shortlist stage."
        )

    layer = layer if layer is not None else config.GRID_LAYER

    # Check the declared CRS before reading geometry — refuse to assume the
    # storage CRS (Constitution: never convert silently) (4.2).
    try:
        declared = pyogrio.read_info(path, layer=layer).get("crs")
    except Exception as exc:  # noqa: BLE001 — any read failure is fatal and named
        raise RuntimeError(f"Could not read Analysis_Grid {path}: {exc}") from exc

    if not declared:
        raise ValueError(
            f"{path} layer {layer!r} has no declared CRS; refusing to assume "
            f"{config.STORAGE_CRS} for the coordinate join (never convert silently)."
        )
    crs = _crs_string(declared)
    if crs != config.STORAGE_CRS:
        raise ValueError(
            f"{path} layer {layer!r} is stored in {crs} but the shortlist storage "
            f"CRS is {config.STORAGE_CRS}; refusing to silently reproject the grid "
            f"coordinates — regenerate the grid with `python -m pipeline --only grid`."
        )

    try:
        grid = gpd.read_file(path, layer=layer)
    except Exception as exc:  # noqa: BLE001 — any read failure is fatal and named
        raise RuntimeError(f"Could not read Analysis_Grid {path}: {exc}") from exc

    missing = [c for c in GRID_REQUIRED_COLUMNS if c not in grid.columns]
    if missing:
        raise ValueError(
            f"{path} layer {layer!r} lacks column(s) {missing} required for the "
            f"coordinate join; the shortlist joins {list(GRID_COORDINATE_COLUMNS)} "
            f"on 'cell_id' and re-derives none of them."
        )

    n_null = int(grid["cell_id"].isna().sum())
    if n_null:
        raise ValueError(
            f"{path} layer {layer!r} has {n_null} null 'cell_id' value(s); "
            f"refusing to join on an ambiguous key."
        )
    duplicates = grid["cell_id"][grid["cell_id"].duplicated()].unique().tolist()
    if duplicates:
        raise ValueError(
            f"{path} layer {layer!r} has {len(duplicates)} duplicate 'cell_id' "
            f"value(s) (e.g. {duplicates[:5]}); refusing to join on an ambiguous key."
        )

    return grid


def join_coordinates(shortlist: pd.DataFrame, grid: pd.DataFrame) -> pd.DataFrame:
    """
    Attach `centroid_lat` / `centroid_lon` to each shortlisted cell by a
    left-join from the Analysis_Grid on `cell_id`, in EPSG:4326 (Requirement
    4.2).

    PURE: takes two in-memory frames, returns a new in-memory frame; no file
    I/O and no mutation of the inputs. The left-join preserves the shortlist's
    rank ordering (row order of ``shortlist``), so the caller's S1-10 ordering
    survives the join.

    ``suitability_score``, ``confidence`` and ``rank`` are carried straight
    through from ``shortlist`` (the selected Scored_Table rows) and are never
    recomputed (Requirement 4.6).

    HALTS before any output — raising ``ValueError`` naming the offending
    ``cell_id`` value(s) — if ANY shortlisted ``cell_id`` has no matching grid
    row. The stage never emits a shortlist row with a fabricated or null
    coordinate (Requirement 4.5).

    An empty shortlist (zero eligible cells, Requirement 3.6) joins to an empty
    result that still carries the coordinate columns, so downstream writers can
    emit headered outputs.
    """
    coord_cols = list(GRID_COORDINATE_COLUMNS)

    # Only the join key and the two coordinate columns come from the grid; the
    # scores/confidence/rank are carried from the shortlist unchanged (4.6). If
    # the grid also happens to carry a column name present on the shortlist
    # (other than the coordinate columns), we do NOT pull it in.
    grid_coords = grid[["cell_id", *coord_cols]]

    joined = shortlist.merge(grid_coords, on="cell_id", how="left", sort=False)

    # Any shortlisted cell_id with no matching grid row now has null coordinates
    # from the left-join. That is a fail-fast condition — never a fabricated or
    # null coordinate in the output (4.5).
    unmatched_mask = joined[coord_cols].isna().any(axis=1)
    if unmatched_mask.any():
        unmatched_ids = joined.loc[unmatched_mask, "cell_id"].tolist()
        raise ValueError(
            f"{len(unmatched_ids)} shortlisted cell_id value(s) have no matching "
            f"row in the Analysis_Grid (e.g. {unmatched_ids[:5]}); refusing to "
            f"emit a shortlist row with a fabricated or null coordinate — "
            f"the grid and Scored_Table must share the same cell_id set."
        )

    return joined
