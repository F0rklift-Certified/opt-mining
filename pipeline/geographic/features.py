"""
Geographic feature-builder stage (Sprint 1 task S1-06).

Converts the Sprint-0 geographic/environmental investigation — SRTM elevation,
Horn slope, Riley terrain ruggedness (TRI), ABARES NLUM land use, and CAPAD
terrestrial protected areas — into a per-cell feature table keyed to the common
analysis grid (``DATA/grid/nsw_analysis_grid.gpkg``, 47,311 cells at 0.05 deg).

It emits exactly one row per grid ``cell_id`` with terrain statistics, a
dominant land-use class, a protected-area constraint, a TRI value, and a
per-cell confidence flag, plus an atomically-written do-not-edit method report.
The Feature_Table feeds the suitability model (S1-07) and the exclusion layer
(S1-08).

The stage is a *consumer of the grid*, so — unlike the other ``geographic.*``
stages that run in Sprint-0 order before the grid exists — it is registered in
``config.STAGES`` after the ``grid`` stage (see design section 5).

Contracts reused (verified against the current code):
    - Uniform stage entry point ``run(verbose=False) -> dict``.
    - Strict grid keying: ``cell_id`` reused byte-for-byte from the grid.
    - Explicit, logged CRS boundaries: ``STORAGE_CRS`` (EPSG:4326) storage,
      ``COMPUTATION_CRS`` (EPSG:3577) for distance/area.
    - Atomic writes + do-not-edit banner via ``common/geo``.
    - File naming ``{source}_{dataset}_{year/vintage}_{region}.{ext}``.
    - No silent passes: validation as ``{"name","expected","observed","passed"}``.

Zonal statistics use pure ``rasterio`` + ``numpy`` + ``geopandas``/``shapely``;
``rasterstats`` is deliberately NOT a dependency (see design section Dependencies).

Importable entry point:
    from pipeline.geographic.features import run
    result = run(verbose=False)

Output:
    DATA/geographic/features/optmining_geographic-features_2024_nsw.gpkg
    DATA/geographic/metadata/geographic_features_method.md
"""

from __future__ import annotations

import csv
import os
import time
from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
import shapely
from rasterio.features import geometry_mask
from rasterio.warp import transform_geom
from rasterio.windows import Window, from_bounds

from ..common.geo import atomic_write_text, banner, apply_vsicurl_env
from ..grid.config import STORAGE_CRS, COMPUTATION_CRS
from .. import config as pipeline_config


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = pipeline_config.PROJECT_ROOT

# Grid input (strict cell_id keying, Req 8.1).
GRID_PATH = PROJECT_ROOT / "DATA" / "grid" / "nsw_analysis_grid.gpkg"

# Feature_Table output — new derived product under the geographic domain tree.
# Filename follows {source}_{dataset}_{year/vintage}_{region}.{ext} with region
# slug "nsw" (Req 7.4); source "optmining" (derived project product), vintage
# 2024 (CAPAD vintage).
OUTPUT_DIR = PROJECT_ROOT / "DATA" / "geographic" / "features"
OUTPUT_FILENAME = "optmining_geographic-features_2024_nsw.gpkg"
OUTPUT_PATH = OUTPUT_DIR / OUTPUT_FILENAME

# Do-not-edit method report (Req 2.7).
REPORT_PATH = (
    PROJECT_ROOT / "DATA" / "geographic" / "metadata" / "geographic_features_method.md"
)

# Source datasets read at run time.
ELEVATION_PATH = (
    PROJECT_ROOT / "DATA" / "geographic" / "elevation"
    / "srtm-gl3_elevation_90m_new-england-rez.tif"
)
SLOPE_PATH = (
    PROJECT_ROOT / "DATA" / "geographic" / "elevation"
    / "srtm-gl3_slope-horn_90m_new-england-rez.tif"
)
TRI_PATH = (
    PROJECT_ROOT / "DATA" / "geographic" / "elevation"
    / "srtm-gl1_tri_30m_glen-innes.tif"
)
NLUM_PATH = (
    PROJECT_ROOT / "DATA" / "geographic" / "landuse"
    / "abares_nlum-alumv8_2020-21_new-england-rez.tif"
)
ALUM_CLASS_TABLE_PATH = (
    PROJECT_ROOT / "DATA" / "geographic" / "landuse" / "abares_alumv8_class_table.csv"
)
CAPAD_PATH = (
    PROJECT_ROOT / "DATA" / "geographic" / "protected"
    / "dcceew_capad-terrestrial_2024_nsw.geojson"
)

# Feature_Table schema — exactly these eight columns (Req 7.1), plus geometry.
SCHEMA_COLUMNS = [
    "cell_id",
    "elevation_m",
    "slope_deg",
    "land_use",
    "protected_area",
    "protected_area_name",
    "tri",
    "confidence_flag",
]

# Single consistent delimiter for joined protected-area names (Req 4.3).
PROTECTED_AREA_NAME_DELIMITER = "; "

# Placeholder for CAPAD features with a missing/null name (Req 4.5).
UNNAMED_PROTECTED_AREA = "(unnamed protected area)"

# Rasters that participate in the confidence decision (Req 5). TRI is EXCLUDED
# because it covers only the Glen-Innes sub-window by design — including it would
# flag the entire NSW grid low and destroy the flag's signal (design section 7).
REQUIRED_CONFIDENCE_RASTERS = ("elevation", "slope", "nlum")

# Confidence flag domain (Req 5.4).
CONFIDENCE_HIGH = "high"
CONFIDENCE_LOW = "low"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class CellStat:
    """
    Result of a raster zonal statistic over one cell.

    Invariant: ``n_valid + n_nodata == total pixels in the clipped selection``
    (Req 2.2). ``value`` is ``None`` when ``n_valid == 0`` (Req 1.6, 2.6).
    ``in_coverage`` is ``False`` when the cell centroid is outside the raster
    extent or all sampled pixels fall outside valid data (Req 6.2, 6.3).
    """

    value: float | None
    n_valid: int
    n_nodata: int
    in_coverage: bool


@dataclass
class ModeResult:
    """
    Result of the categorical mode over one cell's valid NLUM pixels.

    ``land_use`` is the mapped ALUM class name or an ``"unmapped:<code>"``
    marker; ``None`` when ``n_valid == 0`` (Req 3.5). ``code`` is the winning
    NLUM code (lowest code wins on a tie, Req 3.2).
    """

    land_use: str | None
    code: int | None
    n_valid: int
    n_nodata: int
    in_coverage: bool


# ---------------------------------------------------------------------------
# CRS boundaries and transformation logging (Req 9)
# ---------------------------------------------------------------------------
#
# CRS-transformation log entry — the accumulation structure consumed by the
# run() assembly (task 11) and the method-report builder (task 10.2).
#
# Every reprojection performed during a run appends exactly one dict of this
# shape to a caller-owned ``list`` (the "log"). The report builder renders one
# report line per entry, and a reviewer reconciles each entry against the
# reprojection events described in the method (Req 9.3, 9.5):
#
#     {
#         "source":      str,   # source dataset identifier (e.g. a filename / slug)
#         "source_crs":  str,   # CRS the data was in before the transform (EPSG string)
#         "target_crs":  str,   # CRS the data was reprojected into (EPSG string)
#         "operation":   str,   # human-readable operation performed
#     }
#
# The log is an ordinary ``list[dict]`` passed by reference into the reprojection
# helpers, which append to it. This keeps accumulation explicit and inspectable
# (no hidden global state); callers create one list per run() invocation and hand
# the same list to every boundary helper.


# Canonical keys of a CRS-transformation log entry (Req 9.3, 9.5). Documented as
# a constant so the report builder (task 10.2) can rely on the exact field names.
CRS_LOG_FIELDS = ("source", "source_crs", "target_crs", "operation")


def _log_crs_transform(
    log: list[dict],
    source: str,
    source_crs: str,
    target_crs: str,
    operation: str,
    verbose: bool = False,
) -> None:
    """
    Append one CRS-transformation entry to the run's transformation log.

    Records a single reprojection event so every CRS boundary crossed during a
    run is captured for the method report (Req 9.3, 9.5). The entry has exactly
    the fields named in :data:`CRS_LOG_FIELDS`
    (``source``, ``source_crs``, ``target_crs``, ``operation``). When ``verbose``
    the entry is also printed, mirroring the other stages' verbose diagnostics.

    Parameters
    ----------
    log : list[dict]
        The caller-owned accumulation list for this run. Mutated in place: the
        new entry is appended. The run() assembly (task 11) and report builder
        (task 10.2) consume this list.
    source : str
        Source dataset identifier (e.g. the raster/vector filename or slug).
    source_crs : str
        CRS the data was in before the transform (EPSG string, e.g. ``EPSG:4326``).
    target_crs : str
        CRS the data was reprojected into (EPSG string, e.g. ``EPSG:3577``).
    operation : str
        Human-readable description of the operation performed at this boundary.
    """
    entry = {
        "source": source,
        "source_crs": source_crs,
        "target_crs": target_crs,
        "operation": operation,
    }
    log.append(entry)
    if verbose:
        print(
            f"    [crs] {entry['source']}: {entry['source_crs']} -> "
            f"{entry['target_crs']} ({entry['operation']})"
        )


def _resolve_crs_or_halt(crs, source_id: str) -> str:
    """
    Resolve a CRS to an ``EPSG:<code>`` string, or halt naming the source.

    Enforces the "never assume or default a CRS" rule at every read boundary
    (Req 9.4): a source raster or vector must carry a declared CRS that resolves
    to an EPSG code. If the CRS is ``None`` (undeclared) or cannot be resolved to
    an EPSG code, the run halts with a :class:`ValueError` naming the affected
    source, rather than silently assuming a CRS.

    Parameters
    ----------
    crs : rasterio.crs.CRS | pyproj.CRS | str | None
        The declared CRS of the source (e.g. ``src.crs`` for a raster or
        ``gdf.crs`` for a vector).
    source_id : str
        Identifier of the source (filename / slug) used in the error message so a
        reviewer can locate the offending dataset.

    Returns
    -------
    str
        The resolved CRS as an ``EPSG:<code>`` string (e.g. ``"EPSG:4326"``).

    Raises
    ------
    ValueError
        If ``crs`` is ``None`` (undeclared) or has no resolvable EPSG code
        (Req 9.4). The run halts before producing the Feature_Table.
    """
    if crs is None:
        raise ValueError(
            f"Source {source_id!r} has no declared CRS; refusing to assume or "
            f"default a CRS (Req 9.4)."
        )

    # Both rasterio.crs.CRS and pyproj.CRS expose to_epsg(); geopandas CRS is a
    # pyproj.CRS. A plain string is accepted and normalised via pyproj.
    epsg = None
    try:
        epsg = crs.to_epsg()
    except AttributeError:
        # A string/other spec — let pyproj try to interpret it.
        try:
            from pyproj import CRS as _PyprojCRS

            epsg = _PyprojCRS.from_user_input(crs).to_epsg()
        except Exception:  # noqa: BLE001 — any failure means "unresolvable"
            epsg = None

    if epsg is None:
        raise ValueError(
            f"Source {source_id!r} has a CRS that cannot be resolved to an EPSG "
            f"code ({crs!r}); refusing to assume or default a CRS (Req 9.4)."
        )

    return f"EPSG:{epsg}"


def _reproject_cells_to_raster_crs(
    cells: gpd.GeoDataFrame,
    src: rasterio.DatasetReader,
    source_id: str,
    log: list[dict],
    verbose: bool = False,
) -> gpd.GeoDataFrame:
    """
    Reproject cell polygons from ``STORAGE_CRS`` to a raster's declared CRS.

    This is the read-boundary transform for raster sampling (Req 9.3): the grid
    cells are authored in ``STORAGE_CRS`` (EPSG:4326) while each raster is read in
    its own declared CRS, so cell polygons/centroids must be transformed to
    ``src.crs`` before the windowed read and coverage test. The idiom mirrors
    ``validate._sample_raster_at``, which transforms a WGS84 sample point via
    ``rasterio.warp`` before sampling; here whole cell polygons are transformed
    with :func:`rasterio.warp.transform_geom` (the polygon analogue of the point
    ``warp_transform`` call).

    The raster CRS is resolved via :func:`_resolve_crs_or_halt`, so a raster with
    no declared / unresolvable CRS halts the run naming ``source_id`` (Req 9.4).
    When the raster CRS already equals ``STORAGE_CRS`` no transform is needed and
    the cells are returned unchanged **without** logging a (no-op) entry. Otherwise
    exactly one CRS-transformation entry is appended to ``log`` (Req 9.3, 9.5).

    Parameters
    ----------
    cells : gpd.GeoDataFrame
        Cell polygons in ``STORAGE_CRS`` with a ``cell_id`` column (typically the
        output of :func:`read_grid_cells`).
    src : rasterio.DatasetReader
        The open raster whose CRS the cells are transformed into.
    source_id : str
        Identifier of the raster (filename / slug) used in the CRS log entry and
        in any halt message (Req 9.4).
    log : list[dict]
        The run's CRS-transformation accumulation list; appended to in place.
    verbose : bool
        When ``True`` the logged entry is also printed.

    Returns
    -------
    gpd.GeoDataFrame
        A copy of ``cells`` with geometries in the raster's CRS. When the raster
        CRS already matches ``STORAGE_CRS`` the input is returned unchanged.
    """
    raster_crs = _resolve_crs_or_halt(src.crs, source_id)

    # No-op when the raster is already in storage CRS — no boundary is crossed, so
    # nothing is logged (Req 9.5 logs transformations actually applied).
    if raster_crs == STORAGE_CRS:
        return cells

    # transform_geom is the polygon analogue of validate._sample_raster_at's
    # warp_transform(point) call: reproject each cell geometry explicitly at the
    # read boundary (Req 9.3), never converting silently.
    reprojected = cells.copy()
    reprojected["geometry"] = [
        shapely.geometry.shape(
            transform_geom(STORAGE_CRS, raster_crs, shapely.geometry.mapping(geom))
        )
        for geom in cells["geometry"]
    ]
    reprojected = reprojected.set_crs(raster_crs, allow_override=True)

    _log_crs_transform(
        log,
        source=source_id,
        source_crs=STORAGE_CRS,
        target_crs=raster_crs,
        operation="reproject grid cell polygons to raster CRS for windowed sampling",
        verbose=verbose,
    )
    return reprojected


def _reproject_to_computation_crs(
    gdf: gpd.GeoDataFrame,
    source_id: str,
    log: list[dict],
    verbose: bool = False,
) -> gpd.GeoDataFrame:
    """
    Reproject a GeoDataFrame to ``COMPUTATION_CRS`` for distance/area work.

    Used at the protected-area overlap boundary (Req 4.6, 9.2): both the cell
    polygons and the CAPAD features are reprojected to ``COMPUTATION_CRS``
    (EPSG:3577, Australian Albers) before the intersection, because area/distance
    must never be derived from EPSG:4326 degrees. The source CRS is resolved via
    :func:`_resolve_crs_or_halt`, so a layer with no declared / unresolvable CRS
    halts the run naming ``source_id`` (Req 9.4).

    When the source CRS already equals ``COMPUTATION_CRS`` the input is returned
    unchanged and nothing is logged; otherwise exactly one CRS-transformation
    entry is appended to ``log`` (Req 9.3, 9.5).

    Parameters
    ----------
    gdf : gpd.GeoDataFrame
        Layer to reproject (cells or CAPAD features). Must carry a declared CRS.
    source_id : str
        Identifier of the layer (filename / slug) for the CRS log entry and any
        halt message (Req 9.4).
    log : list[dict]
        The run's CRS-transformation accumulation list; appended to in place.
    verbose : bool
        When ``True`` the logged entry is also printed.

    Returns
    -------
    gpd.GeoDataFrame
        A copy of ``gdf`` in ``COMPUTATION_CRS``. When already in
        ``COMPUTATION_CRS`` the input is returned unchanged.
    """
    source_crs = _resolve_crs_or_halt(gdf.crs, source_id)

    # No-op when already in computation CRS — no boundary crossed, nothing logged.
    if source_crs == COMPUTATION_CRS:
        return gdf

    reprojected = gdf.to_crs(COMPUTATION_CRS)

    _log_crs_transform(
        log,
        source=source_id,
        source_crs=source_crs,
        target_crs=COMPUTATION_CRS,
        operation="reproject to computation CRS for protected-area intersection",
        verbose=verbose,
    )
    return reprojected


# ---------------------------------------------------------------------------
# Grid input (strict cell_id keying, Req 8)
# ---------------------------------------------------------------------------


def read_grid_cells(grid_path: Path) -> gpd.GeoDataFrame:
    """
    Read ``cell_id`` + geometry from the common analysis grid GeoPackage.

    The grid is the spatial backbone of the pipeline: every feature layer joins
    to it via ``cell_id``. This reader reuses the grid's ``cell_id`` values
    byte-for-byte and does NOT re-derive, renumber, reformat, or reorder them
    (Req 8.2). The returned GeoDataFrame is in ``STORAGE_CRS`` (EPSG:4326,
    Req 8.1) and carries exactly the ``cell_id`` and ``geometry`` columns in the
    file's native row order.

    Parameters
    ----------
    grid_path : Path
        Path to the analysis-grid GeoPackage
        (``DATA/grid/nsw_analysis_grid.gpkg``).

    Returns
    -------
    gpd.GeoDataFrame
        Columns ``cell_id`` and ``geometry``, CRS ``STORAGE_CRS`` (EPSG:4326).

    Raises
    ------
    FileNotFoundError
        If the grid file is missing or cannot be opened (Req 8.4). The message
        names the offending path.
    ValueError
        If the grid is readable but has no ``cell_id`` column (Req 8.5), or if
        ``cell_id`` contains duplicate values (Req 8.6; the message lists the
        duplicated values). In both cases the run halts before any Feature_Table
        output is written.
    """
    grid_path = Path(grid_path)

    # Req 8.4 — missing file halts before any output, naming the path. Check
    # existence explicitly so a plain missing file always raises FileNotFoundError
    # (rather than a driver-specific error), then treat any read failure the same
    # way per the "missing or cannot be opened" requirement.
    if not grid_path.exists():
        raise FileNotFoundError(
            f"Analysis grid file is missing: {grid_path}"
        )

    try:
        gdf = gpd.read_file(grid_path)
    except Exception as exc:  # unopenable / corrupt / unreadable grid (Req 8.4)
        raise FileNotFoundError(
            f"Analysis grid file could not be opened: {grid_path} ({exc})"
        ) from exc

    # Req 8.5 — readable but no cell_id column halts, naming the absent column.
    if "cell_id" not in gdf.columns:
        raise ValueError(
            f"Analysis grid at {grid_path} has no 'cell_id' column "
            f"(found columns: {list(gdf.columns)})"
        )

    # Req 8.6 — duplicate cell_id halts, listing the duplicated values.
    duplicated_mask = gdf["cell_id"].duplicated(keep=False)
    if duplicated_mask.any():
        duplicated_values = sorted(gdf.loc[duplicated_mask, "cell_id"].unique().tolist())
        raise ValueError(
            f"Analysis grid at {grid_path} contains duplicate 'cell_id' values: "
            f"{duplicated_values}"
        )

    # Ensure the storage CRS is explicit at this boundary (Req 8.1, 9.1). The grid
    # is authored in STORAGE_CRS; if the file declares a different CRS, reproject
    # explicitly rather than assuming. Never convert silently — but the grid is by
    # contract already EPSG:4326, so this is a no-op in the normal case.
    if gdf.crs is None:
        gdf = gdf.set_crs(STORAGE_CRS)
    elif gdf.crs.to_string() != STORAGE_CRS:
        gdf = gdf.to_crs(STORAGE_CRS)

    # Reuse cell_id byte-for-byte, preserving native order (Req 8.2). Return only
    # cell_id + geometry; downstream code copies geometry straight through.
    return gdf[["cell_id", "geometry"]]


# ---------------------------------------------------------------------------
# ALUM class-table loader (Req 3.3, 3.4)
# ---------------------------------------------------------------------------


def load_alum_class_table(path: Path) -> dict[int, str]:
    """
    Load the ABARES ALUM v8 class table mapping NLUM integer codes to names.

    Returns ``{int(row["Value"]): row["TERTV8"]}`` from the ALUM v8 CSV, matching
    the idiom used by ``geographic/inspect._load_class_table``: the ``Value``
    column is the integer NLUM raster code and ``TERTV8`` is the human-readable
    ALUM v8 tertiary class name. This table maps each dominant land-use code to
    its class name for the ``land_use`` output column (Req 3.3); a code absent
    from the returned mapping is treated as unmapped by the caller (Req 3.4).
    Code ``0`` maps to ``"No data/offshore"``.

    Parameters
    ----------
    path : Path
        Path to the ALUM v8 class-table CSV
        (``DATA/geographic/landuse/abares_alumv8_class_table.csv``).

    Returns
    -------
    dict[int, str]
        Mapping from integer NLUM code (``Value``) to ALUM v8 tertiary class
        name (``TERTV8``).
    """
    with open(path) as fh:
        return {int(row["Value"]): row["TERTV8"] for row in csv.DictReader(fh)}


# ---------------------------------------------------------------------------
# Raster zonal statistics (Req 1, 2, 6)
# ---------------------------------------------------------------------------


def _raster_coverage(src: rasterio.DatasetReader, cell_geom) -> bool:
    """
    Fast-path coverage test: is the cell centroid inside the raster bounds?

    Most of the 47,311 NSW cells lie outside the New England REZ / Glen-Innes
    source extents. This centroid-in-bounds test short-circuits those cells in
    O(1) so they never trigger a windowed read (design section Performance,
    Req 6.2, 13). A ``True`` result does NOT guarantee valid data at the cell —
    the cell may still straddle the raster edge and sample only NoData/void
    positions; that edge case is resolved by ``_zonal_raster_stat`` (Req 6.3).

    The cell geometry is expected to already be in the raster's CRS (``src.crs``).
    The CRS transform boundary — reprojecting the cell polygon from ``STORAGE_CRS``
    to ``src.crs`` before calling this — is wired in task 9; until then callers
    must pass a cell polygon already in ``src.crs``.

    Parameters
    ----------
    src : rasterio.DatasetReader
        Open raster, read once per variable (never fully read into memory).
    cell_geom : shapely geometry
        Cell polygon in the raster's CRS.

    Returns
    -------
    bool
        ``True`` if the cell centroid lies within the raster's spatial bounds,
        else ``False`` (out of coverage for this raster, Req 6.2).
    """
    centroid = cell_geom.centroid
    left, bottom, right, top = src.bounds
    return (left <= centroid.x <= right) and (bottom <= centroid.y <= top)


def _zonal_raster_stat(
    src: rasterio.DatasetReader,
    cell_geom,
    stat: str,
) -> CellStat:
    """
    Compute a zonal statistic for one cell over a windowed raster read.

    Pixel-inclusion basis (Req 2.1, 2.4): **cell-centre inclusion** — a pixel
    belongs to the cell iff its centre lies within the cell polygon. This is the
    same deterministic rule the codebase already uses for rasterisation
    (``rasterio.features`` with ``all_touched=False`` in ``validate.py``), applied
    identically to every raster (Req 1.5), so the pixel set is reproducible on
    repeated runs (Req 2.1).

    NoData rule (Req 2.2, 2.3): valid pixels are in-mask pixels that are neither
    the declared ``src.nodata`` nor masked. ``n_nodata`` counts masked/NoData
    pixels *and* in-cell pixel positions that fall outside the raster's data
    extent (Req 6.3, counted as NoData). Invariant:
    ``n_valid + n_nodata == total pixels in the clipped selection`` (Req 2.2).
    NoData is excluded from the statistic (Req 2.3).

    Scaled rasters (Req 1.2, 1.3): the stored ``int16`` values are multiplied by
    ``src.scales[0]`` (defaulting to ``1.0`` when absent), exactly as
    ``validate._sample_raster_at`` does — slope is stored at scale ``0.01`` deg,
    TRI at scale ``0.1`` m.

    Statistic (Req 1.4): the documented aggregation is the **mean** of valid
    pixels for elevation, slope, and TRI (slope mean honours frozen decision Q3).
    Only ``"mean"`` is implemented; any other value raises ``ValueError``.

    The cell geometry is expected to already be in the raster's CRS (``src.crs``);
    the reprojection boundary from ``STORAGE_CRS`` is wired in task 9.

    Parameters
    ----------
    src : rasterio.DatasetReader
        Open raster (band 1 is read), windowed per cell — never read in full.
    cell_geom : shapely geometry
        Cell polygon in the raster's CRS.
    stat : str
        Aggregation statistic; ``"mean"`` per design section Statistic-per-variable.

    Returns
    -------
    CellStat
        ``value`` is the scaled mean of valid pixels, or ``None`` when
        ``n_valid == 0`` (Req 1.6, 2.6). ``in_coverage`` is ``False`` when the
        centroid is outside the raster bounds (fast path, Req 6.2) or when all
        sampled pixels fall outside valid data (Req 6.3).
    """
    if stat != "mean":
        raise ValueError(
            f"_zonal_raster_stat only implements the documented 'mean' statistic; "
            f"got {stat!r}"
        )

    # Fast-path coverage short-circuit (Req 6.2): centroid outside bounds -> the
    # cell is out of coverage for this raster; no windowed read, null value.
    if not _raster_coverage(src, cell_geom):
        return CellStat(value=None, n_valid=0, n_nodata=0, in_coverage=False)

    scale = src.scales[0] if src.scales else 1.0

    # Windowed read over the cell bounds only (never the full mosaic; design
    # section Performance). Round to whole pixels, then clamp to the raster so the
    # window does not extend past the data extent — positions beyond the extent are
    # accounted for separately below as NoData (Req 6.3).
    minx, miny, maxx, maxy = cell_geom.bounds
    window = from_bounds(minx, miny, maxx, maxy, transform=src.transform)
    window = window.round_offsets().round_lengths()

    # Total pixel positions the cell bounds cover on the raster lattice, BEFORE
    # clamping — this is the denominator for the clipped selection so that in-cell
    # positions outside the raster's data extent count as NoData (Req 6.3, 2.2).
    full_window = window
    read_window = full_window.intersection(
        Window(0, 0, src.width, src.height)
    )

    # If the cell bounds intersect no in-bounds pixels at all, the whole clipped
    # selection is out-of-data -> NoData; classify out of coverage (Req 6.3).
    if read_window.width <= 0 or read_window.height <= 0:
        n_positions = int(round(full_window.width)) * int(round(full_window.height))
        return CellStat(
            value=None, n_valid=0, n_nodata=max(n_positions, 0), in_coverage=False
        )

    # Masked read so declared NoData and dataset masks are honoured together.
    data = src.read(1, window=read_window, masked=True)
    window_transform = src.window_transform(read_window)

    # Cell-centre mask over the read window (all_touched=False -> a pixel belongs
    # to the cell iff its centre is inside the polygon). geometry_mask returns True
    # OUTSIDE the geometry, so invert to get an inside mask (Req 2.1, 2.4, 1.5).
    outside_cell = geometry_mask(
        [shapely.geometry.mapping(cell_geom)],
        out_shape=(data.shape[0], data.shape[1]),
        transform=window_transform,
        all_touched=False,
        invert=False,
    )
    inside_cell = ~outside_cell

    # Valid = inside the cell AND not masked/NoData. numpy MaskedArray: getmaskarray
    # is True where masked (NoData or void). Also guard the declared nodata value
    # explicitly in case the band carries no mask but a sentinel value.
    masked = np.ma.getmaskarray(data)
    if src.nodata is not None:
        masked = masked | (np.asarray(data.data) == src.nodata)

    valid_mask = inside_cell & ~masked
    n_valid = int(valid_mask.sum())

    # In-cell positions that were read but are NoData/masked.
    n_nodata_read = int((inside_cell & masked).sum())

    # In-cell pixel positions that fall OUTSIDE the raster's data extent count as
    # NoData too (Req 6.3). These are positions in the full (pre-clamp) window that
    # were not part of the read window. We approximate the count as the difference
    # between the full-window position count and the read-window position count that
    # lie inside the cell polygon. Positions outside the read window cannot have
    # their pixel centres tested against the polygon (they were never read), so they
    # are conservatively counted as in-cell NoData only to the extent the full window
    # exceeds the read window. The dominant real-world case (centroid inside, cell
    # fully covered) yields zero here; the edge case (Req 6.3) yields a positive count.
    full_positions = int(round(full_window.width)) * int(round(full_window.height))
    read_positions = int(read_window.width) * int(read_window.height)
    n_outside_extent = max(full_positions - read_positions, 0)

    n_nodata = n_nodata_read + n_outside_extent

    if n_valid == 0:
        # No valid pixels anywhere in the clipped selection -> null value and out
        # of coverage for this raster (Req 1.6, 2.6, 6.3).
        return CellStat(value=None, n_valid=0, n_nodata=n_nodata, in_coverage=False)

    valid_values = np.asarray(data.data)[valid_mask].astype(np.float64)
    value = float(valid_values.mean()) * scale

    return CellStat(
        value=value, n_valid=n_valid, n_nodata=n_nodata, in_coverage=True
    )


# ---------------------------------------------------------------------------
# Categorical mode for land use (Req 3)
# ---------------------------------------------------------------------------


def _categorical_mode(
    src: rasterio.DatasetReader,
    cell_geom,
    class_table: dict[int, str],
) -> ModeResult:
    """
    Compute the dominant (modal) land-use class for one cell over the NLUM raster.

    Pixel selection (Req 3.1) uses the **same windowed cell-centre inclusion rule**
    as ``_zonal_raster_stat``: window the raster to the cell bounds, clamp to the
    data extent, do a masked read, and select pixels whose centre lies within the
    cell polygon (``rasterio.features.geometry_mask`` with ``all_touched=False``).
    The declared ``src.nodata`` value and any dataset mask are excluded before the
    mode is taken (Req 3.1) so the mode is computed over valid pixels only.

    Mode + tie-break (Req 3.2): the dominant code is the most frequent NLUM code
    among the cell's valid pixels, found via ``numpy.unique(codes,
    return_counts=True)`` and selecting the maximum count. When two or more codes
    tie for the highest frequency, the **lowest code wins** — a deterministic,
    reproducible tie-break.

    Mapping (Req 3.3, 3.4): the winning code is mapped to its ALUM class name via
    ``class_table[code]``. A code absent from ``class_table`` is recorded with an
    explicit ``"unmapped:<code>"`` marker so the caller can report it.

    Coverage / NoData bookkeeping mirrors ``_zonal_raster_stat``: ``n_valid`` and
    ``n_nodata`` partition the clipped selection (Req 2.2), with in-cell positions
    outside the raster's data extent counted as NoData (Req 6.3). When
    ``n_valid == 0`` the cell has no valid NLUM pixels: ``land_use`` and ``code``
    are ``None`` and the cell is classified out of coverage (Req 3.5, 6.2, 6.3).

    The cell geometry is expected to already be in the raster's CRS (``src.crs``);
    the reprojection boundary from ``STORAGE_CRS`` is wired in task 9.

    Parameters
    ----------
    src : rasterio.DatasetReader
        Open NLUM categorical raster (band 1 is read), windowed per cell.
    cell_geom : shapely geometry
        Cell polygon in the raster's CRS.
    class_table : dict[int, str]
        ALUM v8 code -> class name mapping from :func:`load_alum_class_table`.

    Returns
    -------
    ModeResult
        ``land_use`` is the mapped class name, an ``"unmapped:<code>"`` marker, or
        ``None`` when ``n_valid == 0`` (Req 3.5). ``code`` is the winning NLUM code
        (lowest on a tie, Req 3.2) or ``None``. ``in_coverage`` is ``False`` when
        the centroid is outside the raster bounds (fast path, Req 6.2) or when all
        sampled pixels fall outside valid data (Req 6.3).
    """
    # Fast-path coverage short-circuit (Req 6.2): centroid outside bounds -> the
    # cell is out of coverage for this raster; no windowed read, null land_use.
    if not _raster_coverage(src, cell_geom):
        return ModeResult(
            land_use=None, code=None, n_valid=0, n_nodata=0, in_coverage=False
        )

    # Windowed read over the cell bounds only (same rule as _zonal_raster_stat).
    minx, miny, maxx, maxy = cell_geom.bounds
    window = from_bounds(minx, miny, maxx, maxy, transform=src.transform)
    window = window.round_offsets().round_lengths()

    full_window = window
    read_window = full_window.intersection(
        Window(0, 0, src.width, src.height)
    )

    # If the cell bounds intersect no in-bounds pixels, the whole clipped selection
    # is out-of-data -> NoData; classify out of coverage (Req 6.3).
    if read_window.width <= 0 or read_window.height <= 0:
        n_positions = int(round(full_window.width)) * int(round(full_window.height))
        return ModeResult(
            land_use=None,
            code=None,
            n_valid=0,
            n_nodata=max(n_positions, 0),
            in_coverage=False,
        )

    # Masked read so declared NoData and dataset masks are honoured together.
    data = src.read(1, window=read_window, masked=True)
    window_transform = src.window_transform(read_window)

    # Cell-centre mask over the read window (all_touched=False). geometry_mask
    # returns True OUTSIDE the geometry, so invert to get an inside mask
    # (identical rule to _zonal_raster_stat; Req 2.1, 2.4, 1.5, 3.1).
    outside_cell = geometry_mask(
        [shapely.geometry.mapping(cell_geom)],
        out_shape=(data.shape[0], data.shape[1]),
        transform=window_transform,
        all_touched=False,
        invert=False,
    )
    inside_cell = ~outside_cell

    # Exclude the raster nodata (and any mask) before the mode (Req 3.1).
    masked = np.ma.getmaskarray(data)
    if src.nodata is not None:
        masked = masked | (np.asarray(data.data) == src.nodata)

    valid_mask = inside_cell & ~masked
    n_valid = int(valid_mask.sum())

    # In-cell positions that were read but are NoData/masked.
    n_nodata_read = int((inside_cell & masked).sum())

    # In-cell positions outside the raster's data extent count as NoData (Req 6.3),
    # mirroring _zonal_raster_stat's bookkeeping.
    full_positions = int(round(full_window.width)) * int(round(full_window.height))
    read_positions = int(read_window.width) * int(read_window.height)
    n_outside_extent = max(full_positions - read_positions, 0)

    n_nodata = n_nodata_read + n_outside_extent

    if n_valid == 0:
        # No valid NLUM pixels -> null land_use and out of coverage (Req 3.5, 6.3).
        return ModeResult(
            land_use=None,
            code=None,
            n_valid=0,
            n_nodata=n_nodata,
            in_coverage=False,
        )

    codes = np.asarray(data.data)[valid_mask]

    # Mode over valid codes: numpy.unique returns unique values in ascending order,
    # so the first index of the maximum count is the LOWEST code among ties — the
    # documented deterministic tie-break (Req 3.2).
    unique_codes, counts = np.unique(codes, return_counts=True)
    winner_idx = int(np.argmax(counts))
    winning_code = int(unique_codes[winner_idx])

    # Map code -> ALUM class name; unmapped code gets an explicit marker (Req 3.3,
    # 3.4).
    if winning_code in class_table:
        land_use = class_table[winning_code]
    else:
        land_use = f"unmapped:{winning_code}"

    return ModeResult(
        land_use=land_use,
        code=winning_code,
        n_valid=n_valid,
        n_nodata=n_nodata,
        in_coverage=True,
    )


# ---------------------------------------------------------------------------
# Protected-area overlap (Req 4)
# ---------------------------------------------------------------------------


def _load_capad(path: Path) -> gpd.GeoDataFrame:
    """
    Load the CAPAD terrestrial protected-areas vector layer.

    Reads the CAPAD GeoJSON via ``geopandas.read_file``, matching how
    ``geographic/validate.py`` sources the same file
    (``DATA/geographic/protected/dcceew_capad-terrestrial_2024_nsw.geojson``).
    The returned GeoDataFrame carries the ``NAME`` attribute (the protected-area
    name field, confirmed against the CAPAD schema) and geometry in the file's
    declared CRS — GeoJSON is EPSG:4326 by convention, which ``geopandas`` reports
    as ``STORAGE_CRS``. The caller reprojects to ``COMPUTATION_CRS`` (EPSG:3577)
    before the intersection; the reprojection wiring/logging lives in task 9.

    Parameters
    ----------
    path : Path
        Path to the CAPAD terrestrial protected-areas GeoJSON.

    Returns
    -------
    gpd.GeoDataFrame
        CAPAD features with at least a ``NAME`` column and geometry.

    Raises
    ------
    RuntimeError
        If the CAPAD source is missing or cannot be read (Req 4.7). The message
        names the missing/unreadable path so the run halts the protected-area
        computation without writing ``protected_area``/``protected_area_name``
        and returns a clear error indication.
    """
    path = Path(path)

    # Req 4.7 — a missing CAPAD source halts, naming the path. Check existence
    # explicitly so a plain missing file always raises RuntimeError (rather than a
    # driver-specific error), then treat any read failure the same way per the
    # "unavailable or cannot be read" requirement.
    if not path.exists():
        raise RuntimeError(
            f"CAPAD protected-area source is missing: {path}"
        )

    try:
        return gpd.read_file(path)
    except Exception as exc:  # unreadable / corrupt CAPAD source (Req 4.7)
        raise RuntimeError(
            f"CAPAD protected-area source could not be read: {path} ({exc})"
        ) from exc


def _protected_overlap(
    cells_3577: gpd.GeoDataFrame,
    capad_3577: gpd.GeoDataFrame,
) -> dict[str, tuple[bool, str]]:
    """
    Determine per-cell protected-area overlap against CAPAD features.

    Performs a single vectorised spatial join (``geopandas.sjoin`` with predicate
    ``"intersects"``) in ``COMPUTATION_CRS`` (EPSG:3577, Req 4.6, 9.2) — a shared
    interior area OR a shared boundary counts as an intersection (Req 4.1). Both
    inputs are expected to already be in ``COMPUTATION_CRS``; the reprojection
    boundary and its logging are wired by the caller in task 9. The join runs over
    all cells at once rather than a per-cell loop (design section Performance).

    For each ``cell_id`` the result is ``(protected_area, protected_area_name)``:

    - ``protected_area`` is ``True`` iff the cell intersects one or more CAPAD
      features (Req 4.1), else ``False`` (Req 4.2).
    - ``protected_area_name`` is the :data:`PROTECTED_AREA_NAME_DELIMITER`-joined
      set of *distinct* CAPAD ``NAME`` values for the intersecting features, with
      duplicate names collapsed to one entry (Req 4.3). Names are emitted in a
      deterministic (sorted) order so regeneration is reproducible (Req 7.7).
    - A feature whose ``NAME`` is missing or null contributes the
      :data:`UNNAMED_PROTECTED_AREA` placeholder (Req 4.5).
    - Non-intersecting cells get ``(False, "")`` — an empty, zero-length name
      (Req 4.4).

    Every ``cell_id`` in ``cells_3577`` appears exactly once in the returned dict
    (Req 6.1, 7.2), including cells with no overlap.

    Parameters
    ----------
    cells_3577 : gpd.GeoDataFrame
        Cell polygons with a ``cell_id`` column, reprojected to
        ``COMPUTATION_CRS`` (EPSG:3577).
    capad_3577 : gpd.GeoDataFrame
        CAPAD features with a ``NAME`` column, reprojected to ``COMPUTATION_CRS``.

    Returns
    -------
    dict[str, tuple[bool, str]]
        ``{cell_id: (protected_area, protected_area_name)}`` for every cell.
    """
    # Default every cell to "no overlap" so cells with no intersecting CAPAD
    # feature get (False, "") — an empty, zero-length name (Req 4.2, 4.4). This
    # also guarantees every cell_id appears exactly once (Req 6.1, 7.2).
    result: dict[str, tuple[bool, str]] = {
        cell_id: (False, "") for cell_id in cells_3577["cell_id"]
    }

    # No protected features -> no cell overlaps; return the all-False default.
    if len(capad_3577) == 0:
        return result

    # Reduce CAPAD to the NAME attribute + geometry, normalising missing/null names
    # to the placeholder before the join (Req 4.5). A name is "missing" when the
    # NAME column is absent, or the value is null/NaN, or an empty/whitespace string.
    capad = capad_3577[["geometry"]].copy()
    if "NAME" in capad_3577.columns:
        names = capad_3577["NAME"]
        capad["protected_area_name"] = [
            UNNAMED_PROTECTED_AREA
            if (nm is None or (isinstance(nm, float) and np.isnan(nm))
                or str(nm).strip() == "")
            else str(nm)
            for nm in names
        ]
    else:
        # No NAME attribute at all -> every intersecting feature is unnamed.
        capad["protected_area_name"] = UNNAMED_PROTECTED_AREA

    # Single vectorised intersects-join in EPSG:3577 (Req 4.6, 9.2). Keep only the
    # left cell_id and the joined name; inner join yields one row per intersecting
    # (cell, feature) pair, and non-matching cells simply do not appear (they keep
    # the (False, "") default above).
    cells = cells_3577[["cell_id", "geometry"]]
    joined = gpd.sjoin(cells, capad, how="inner", predicate="intersects")

    # Collapse per cell_id to the distinct, sorted, delimiter-joined name set
    # (Req 4.3). Sorting makes the output deterministic across runs (Req 7.7).
    for cell_id, group in joined.groupby("cell_id"):
        distinct_names = sorted(set(group["protected_area_name"]))
        joined_name = PROTECTED_AREA_NAME_DELIMITER.join(distinct_names)
        result[cell_id] = (True, joined_name)

    return result


# ---------------------------------------------------------------------------
# Per-cell confidence flag (Req 5)
# ---------------------------------------------------------------------------


def _confidence_flag(per_raster: dict[str, CellStat | ModeResult]) -> str:
    """
    Derive the per-cell confidence flag from the required rasters' coverage/NoData.

    The flag is the coverage/NoData biconditional over the **required** source
    rasters (:data:`REQUIRED_CONFIDENCE_RASTERS` = elevation, slope, NLUM). A cell
    is :data:`CONFIDENCE_LOW` if, for **any** required raster, either:

    - the cell is out of coverage (``in_coverage is False``), Req 5.2; or
    - 50% or more of the pixels overlapping the cell are NoData — i.e.
      ``n_nodata >= 0.5 * (n_valid + n_nodata)`` (Req 5.1). The boundary is
      inclusive: **exactly 50% NoData counts as low**. A cell with zero pixels in
      the clipped selection (``n_valid + n_nodata == 0``) has no valid data and is
      likewise low.

    Otherwise the cell is :data:`CONFIDENCE_HIGH` (Req 5.3). The result is always
    exactly one of the two values ``"high"`` / ``"low"`` and no other (Req 5.4).

    TRI is **excluded** from the decision even when present in ``per_raster``:
    the TRI raster covers only the Glen-Innes sub-window by design, so including
    it would flag the entire NSW grid low and destroy the flag's signal (design
    §Confidence rule, Req 6.4). Only the entries named in
    :data:`REQUIRED_CONFIDENCE_RASTERS` are consulted.

    Parameters
    ----------
    per_raster : dict[str, CellStat | ModeResult]
        Per-cell statistics keyed by raster name. Each value carries
        ``in_coverage``, ``n_valid``, and ``n_nodata`` (both :class:`CellStat` and
        :class:`ModeResult` expose these). Keys must include every name in
        :data:`REQUIRED_CONFIDENCE_RASTERS`; extra keys (e.g. ``"tri"``) are
        ignored.

    Returns
    -------
    str
        :data:`CONFIDENCE_LOW` (``"low"``) or :data:`CONFIDENCE_HIGH` (``"high"``).
    """
    for name in REQUIRED_CONFIDENCE_RASTERS:
        stat = per_raster[name]

        # Out of coverage on a required raster -> low (Req 5.2).
        if not stat.in_coverage:
            return CONFIDENCE_LOW

        total = stat.n_valid + stat.n_nodata

        # No pixels at all in the clipped selection -> no valid data -> low. This
        # avoids a divide-by-zero and treats an empty selection as fully NoData.
        if total == 0:
            return CONFIDENCE_LOW

        # >= 50% NoData -> low; the exactly-50% boundary is inclusive (Req 5.1).
        # Compare via cross-multiplication to keep the 50% boundary exact and avoid
        # floating-point rounding: n_nodata / total >= 1/2  <=>  2*n_nodata >= total.
        if 2 * stat.n_nodata >= total:
            return CONFIDENCE_LOW

    # Every required raster is in coverage with >50% valid pixels -> high (Req 5.3).
    return CONFIDENCE_HIGH


# ---------------------------------------------------------------------------
# Feature_Table writer (Req 7)
# ---------------------------------------------------------------------------

# GeoPackage layer name for the Feature_Table. A stable, descriptive layer name
# (the grid uses "nsw_grid") so downstream consumers can address the layer
# explicitly.
OUTPUT_LAYER = "geographic_features"


def _write_feature_table(gdf: gpd.GeoDataFrame, path: Path) -> None:
    """
    Atomically write the Feature_Table as a GeoPackage in ``STORAGE_CRS``.

    Mirrors the atomic-write idiom in ``grid/generate.run()`` exactly: create the
    parent directory, write the GeoDataFrame to a sibling temporary GeoPackage
    (``to_file(tmp, driver="GPKG", layer=...)``), then ``os.replace`` the tmp file
    onto the destination path so the destination only ever appears via an atomic
    rename of a fully-written file (Req 7.5). A crash mid-write therefore cannot
    leave a truncated GeoPackage, and any previously existing output at ``path`` is
    left unmodified until the rename succeeds (Req 7.6). The ``finally`` block
    removes the tmp file on any failure so a failed write leaves no stray temp.

    The table is stored in ``STORAGE_CRS`` (EPSG:4326, Req 7.3, 9.1). The CRS
    boundary is made explicit here rather than assumed: if the GeoDataFrame has no
    declared CRS it is stamped as ``STORAGE_CRS`` (the grid geometry is copied
    straight through in EPSG:4326), and if it declares a different CRS it is
    reprojected to ``STORAGE_CRS`` before writing — never converted silently.

    Parameters
    ----------
    gdf : gpd.GeoDataFrame
        The assembled Feature_Table (one row per ``cell_id``, the eight schema
        columns plus geometry). Geometry is expected to be in ``STORAGE_CRS``
        (copied byte-for-byte from the grid).
    path : Path
        Destination GeoPackage path
        (``DATA/geographic/features/optmining_geographic-features_2024_nsw.gpkg``).

    Raises
    ------
    Exception
        Any underlying write error propagates (Req 7.6); the atomic rename means
        the destination is only replaced on success, so the prior output is intact
        and the tmp file is cleaned up.
    """
    path = Path(path)

    # Make the CRS boundary explicit (Req 7.3, 9.1): store in STORAGE_CRS, never
    # convert silently. Normal case (grid geometry copied through) is a no-op.
    if gdf.crs is None:
        gdf = gdf.set_crs(STORAGE_CRS)
    elif gdf.crs.to_string() != STORAGE_CRS:
        gdf = gdf.to_crs(STORAGE_CRS)

    # Atomic write mirroring grid/generate.run(): mkdir parent, write tmp, replace.
    path.parent.mkdir(parents=True, exist_ok=True)

    # Sibling tmp file next to the destination so os.replace stays on one
    # filesystem (an atomic rename), matching the grid writer's tmp naming.
    tmp_path = path.with_name(path.stem + "_tmp" + path.suffix)

    try:
        gdf.to_file(tmp_path, driver="GPKG", layer=OUTPUT_LAYER)
        os.replace(tmp_path, path)
    finally:
        # Leave any prior output at `path` intact on failure and never leave a
        # stray tmp file behind (Req 7.6).
        if tmp_path.exists():
            tmp_path.unlink()


# ---------------------------------------------------------------------------
# Method report (Req 2.5, 2.7, 5.6, 6.5, 6.6, 9.3, 9.5, 13.2)
# ---------------------------------------------------------------------------
#
# The report builder assembles the seven-section method report defined in design
# §Data Models (Method report structure) and the writer stamps it with the
# do-not-edit banner and writes it atomically. The report is the do-not-edit
# provenance artefact for this derived product (design §Cross-component impact),
# so all statistic/tie-break/NoData/CRS/runtime facts a reviewer needs to
# reconcile the Feature_Table live here.
#
# Per-variable aggregation statistic (Req 1.4). Documented once here so the report
# reflects the actual implementation in _zonal_raster_stat (mean; slope=mean
# honours frozen decision Q3) and _categorical_mode (mode + lowest-code tie-break).
REPORT_TERRAIN_VARIABLES = (
    # (column, source raster label, statistic, units)
    ("elevation_m", "Elevation_Raster (SRTM GL3, New England REZ)", "mean of valid pixels", "metres AMSL"),
    ("slope_deg", "Slope_Raster (Horn slope, New England REZ)", "mean of valid pixels", "degrees"),
    ("tri", "TRI (Riley, Glen-Innes sub-window)", "mean of valid pixels", "metres"),
)

# The partial-cell boundary rule, recorded verbatim (Req 2.4, 2.5).
REPORT_PARTIAL_CELL_RULE = (
    "Cell-centre inclusion: a raster pixel belongs to a cell iff the pixel centre "
    "lies within the cell polygon (`rasterio.features.geometry_mask(..., "
    "all_touched=False)`). Applied identically to every raster, deterministic "
    "across repeated runs."
)

# The NoData handling rule, recorded verbatim (Req 2.5).
REPORT_NODATA_RULE = (
    "Valid pixels are in-cell pixels that are neither the raster's declared "
    "`nodata` value nor masked. `n_nodata` counts masked/NoData pixels AND in-cell "
    "positions falling outside the raster's data extent. NoData pixels are excluded "
    "from every statistic; `n_valid + n_nodata` equals the total clipped selection. "
    "A cell with zero valid pixels gets a null value for that variable."
)

# The land-use mode + tie-break rule, recorded verbatim (Req 3.2, 3.4).
REPORT_MODE_RULE = (
    "Land use is the mode (most frequent NLUM code) over the cell's valid pixels, "
    "mapped to its ALUM v8 tertiary class name. Tie-break: the lowest code wins "
    "(deterministic). A code absent from the ALUM class table is recorded as "
    "`unmapped:<code>`."
)


def _build_report(
    *,
    coverage: dict[str, dict[str, int]],
    zero_valid: dict[str, int],
    unmapped_codes: set[int],
    confidence_counts: dict[str, int],
    crs_log: list[dict],
    runtime_s: float,
    n_cells: int,
) -> str:
    """
    Assemble the seven-section geographic-features method report as markdown.

    Builds the do-not-edit method report described in design §Data Models (Method
    report structure), from structured inputs gathered by ``run()`` (task 11). The
    returned string is the full report body; :func:`_write_report` stamps the
    banner and writes it atomically. This function performs no I/O so it is trivial
    to smoke-test with synthetic inputs.

    The seven sections, in order, are:

    1. **Header + banner** — H1 title; the banner is prepended by
       :func:`_write_report` so callers never hand-write it (Req 2.7).
    2. **Method** — per terrain variable the aggregation statistic
       (:data:`REPORT_TERRAIN_VARIABLES`, Req 1.4), the verbatim partial-cell rule
       (Req 2.4, 2.5), the NoData rule (Req 2.5), the land-use mode + tie-break
       rule (Req 3.2), and the protected-area intersection CRS (``COMPUTATION_CRS``,
       Req 4.6, 9.2).
    3. **Coverage** — per source raster, cells inside vs outside coverage with
       ``inside + outside == total`` asserted (Req 6.5), plus the New-England-REZ /
       Glen-Innes-only coverage-gap description (Req 6.6).
    4. **NoData / zero-valid-pixel + unmapped codes** — per-raster count of cells
       with zero valid pixels (Req 2.6) and any unmapped NLUM codes encountered
       (Req 3.4).
    5. **Confidence** — count of low- vs high-confidence cells (Req 5.6).
    6. **CRS transformations** — one row per entry in ``crs_log`` (Req 9.3, 9.5).
    7. **Runtime** — total wall-clock seconds and cells processed (Req 13.2); this
       runtime equals the ``run()`` summary dict ``runtime_s`` (Req 13.3).

    Parameters
    ----------
    coverage : dict[str, dict[str, int]]
        Per-raster coverage bookkeeping. Keyed by raster label (e.g. ``"elevation"``,
        ``"slope"``, ``"tri"``, ``"nlum"``); each value is a dict with integer keys
        ``"inside"``, ``"outside"``, and ``"total"``. The builder asserts
        ``inside + outside == total`` for every raster (Req 6.5) and raises
        ``ValueError`` if the bookkeeping does not partition the grid — a report
        must never silently paper over a coverage-accounting bug.
    zero_valid : dict[str, int]
        Per-raster count of cells that had zero valid pixels (Req 2.6). Keyed by the
        same raster labels as ``coverage``.
    unmapped_codes : set[int]
        Distinct NLUM codes encountered during the run that were absent from the
        ALUM class table (Req 3.4). May be empty.
    confidence_counts : dict[str, int]
        Counts of cells per confidence flag, keyed by :data:`CONFIDENCE_LOW` and
        :data:`CONFIDENCE_HIGH` (Req 5.6).
    crs_log : list[dict]
        The run's CRS-transformation log — a list of entries each shaped per
        :data:`CRS_LOG_FIELDS` (``source``, ``source_crs``, ``target_crs``,
        ``operation``) as produced by :func:`_log_crs_transform` (Req 9.3, 9.5).
        May be empty (no boundaries crossed).
    runtime_s : float
        Total wall-clock seconds for the run body (Req 13.2, 13.3).
    n_cells : int
        Number of grid cells processed (rows written == grid cell_id count).

    Returns
    -------
    str
        The complete markdown report body (without the banner, which
        :func:`_write_report` prepends).

    Raises
    ------
    ValueError
        If any raster's coverage bookkeeping fails ``inside + outside == total``
        (Req 6.5) — the report is not allowed to record an inconsistent partition.
    """
    import io

    out = io.StringIO()

    # --- Section 1: header ---------------------------------------------------
    # The banner is stamped by _write_report so the report carries the same
    # do-not-edit provenance line as every other generated pipeline report.
    out.write("# Geographic & environmental features — method report\n\n")
    out.write(
        "Per-cell geographic/environmental Feature_Table on the common analysis "
        "grid (Sprint 1 task S1-06). One row per grid `cell_id`; terrain "
        "statistics, dominant land use, protected-area constraint, TRI, and a "
        "per-cell confidence flag.\n\n"
    )

    # --- Section 2: method ---------------------------------------------------
    out.write("## Method\n\n")
    out.write("### Aggregation statistic per variable\n\n")
    out.write("| Variable | Source raster | Statistic | Units |\n|---|---|---|---|\n")
    for column, source, statistic, units in REPORT_TERRAIN_VARIABLES:
        out.write(f"| `{column}` | {source} | {statistic} | {units} |\n")
    out.write("\n")
    out.write(f"**Partial-cell boundary rule.** {REPORT_PARTIAL_CELL_RULE}\n\n")
    out.write(f"**NoData rule.** {REPORT_NODATA_RULE}\n\n")
    out.write(f"**Dominant land use.** {REPORT_MODE_RULE}\n\n")
    out.write(
        "**Protected areas.** Overlap is a spatial intersection (shared interior "
        f"OR boundary) computed in `{COMPUTATION_CRS}` (Australian Albers), never "
        f"in `{STORAGE_CRS}` degrees. `protected_area` is the boolean overlap; "
        "`protected_area_name` is the "
        f"`{PROTECTED_AREA_NAME_DELIMITER!r}`-joined set of distinct CAPAD names "
        f"(unnamed features -> `{UNNAMED_PROTECTED_AREA}`).\n\n"
    )

    # --- Section 3: coverage -------------------------------------------------
    out.write("## Coverage\n\n")
    out.write(
        "Per source raster, the count of grid cells inside vs outside coverage. "
        "For every raster `inside + outside == total` (partition of the grid, "
        "Req 6.5).\n\n"
    )
    out.write(
        "| Raster | Cells inside | Cells outside | Total | Partition OK |\n"
        "|---|---|---|---|---|\n"
    )
    for raster in sorted(coverage):
        counts = coverage[raster]
        inside = int(counts["inside"])
        outside = int(counts["outside"])
        total = int(counts["total"])
        # Assert the partition conceptually — a report must never record an
        # inconsistent inside/outside/total (Req 6.5).
        if inside + outside != total:
            raise ValueError(
                f"Coverage bookkeeping for raster {raster!r} does not partition the "
                f"grid: inside ({inside}) + outside ({outside}) != total ({total})."
            )
        out.write(
            f"| {raster} | {inside} | {outside} | {total} | "
            f"{'yes' if inside + outside == total else '**NO**'} |\n"
        )
    out.write("\n")
    out.write(
        "**Coverage gap.** The elevation, slope, and NLUM rasters currently cover "
        "only the New England REZ, and the TRI raster covers only the tiny "
        "Glen-Innes sub-window — not the full NSW grid. Cells whose centroid lies "
        "outside a raster's extent are out of coverage for that raster: their "
        "derived variable is null and (for the required rasters) the cell is "
        "flagged low confidence. TRI is out of coverage for almost the entire grid "
        "by design and is therefore EXCLUDED from the confidence decision so it "
        "does not flag the whole grid low (Req 6.6).\n\n"
    )

    # --- Section 4: NoData / zero-valid + unmapped codes ---------------------
    out.write("## NoData / zero-valid-pixel occurrences\n\n")
    out.write(
        "Per source raster, the count of cells that had zero valid (non-NoData) "
        "pixels — those cells receive a null value for that variable (Req 2.6).\n\n"
    )
    out.write("| Raster | Cells with zero valid pixels |\n|---|---|\n")
    for raster in sorted(zero_valid):
        out.write(f"| {raster} | {int(zero_valid[raster])} |\n")
    out.write("\n")
    if unmapped_codes:
        codes_str = ", ".join(str(c) for c in sorted(unmapped_codes))
        out.write(
            f"**Unmapped NLUM codes encountered (Req 3.4):** {codes_str}. These "
            "were recorded as `unmapped:<code>` in the `land_use` column because "
            "they are absent from the ALUM class table.\n\n"
        )
    else:
        out.write("**Unmapped NLUM codes encountered (Req 3.4):** none.\n\n")

    # --- Section 5: confidence ----------------------------------------------
    out.write("## Confidence\n\n")
    n_low = int(confidence_counts.get(CONFIDENCE_LOW, 0))
    n_high = int(confidence_counts.get(CONFIDENCE_HIGH, 0))
    out.write(
        "Count of cells per confidence flag. A cell is low confidence when, for any "
        "required raster (elevation, slope, NLUM), it is out of coverage or >= 50% "
        "of overlapping pixels are NoData; otherwise high (Req 5.6).\n\n"
    )
    out.write("| Confidence | Cells |\n|---|---|\n")
    out.write(f"| `{CONFIDENCE_HIGH}` | {n_high} |\n")
    out.write(f"| `{CONFIDENCE_LOW}` | {n_low} |\n\n")

    # --- Section 6: CRS transformations -------------------------------------
    out.write("## CRS transformations\n\n")
    out.write(
        "One row per reprojection performed during the run so a reviewer can "
        "reconcile every CRS boundary crossed (Req 9.3, 9.5). Storage CRS "
        f"`{STORAGE_CRS}`; computation CRS `{COMPUTATION_CRS}`.\n\n"
    )
    if crs_log:
        out.write(
            "| Source | Source CRS | Target CRS | Operation |\n|---|---|---|---|\n"
        )
        for entry in crs_log:
            out.write(
                f"| {entry['source']} | {entry['source_crs']} | "
                f"{entry['target_crs']} | {entry['operation']} |\n"
            )
        out.write("\n")
    else:
        out.write("No reprojections were performed during this run.\n\n")

    # --- Section 7: runtime --------------------------------------------------
    out.write("## Runtime\n\n")
    out.write(f"- Cells processed: {int(n_cells)}\n")
    out.write(f"- Total wall-clock runtime: {float(runtime_s):.3f} s\n")

    return out.getvalue()


def _write_report(report_text: str, path: Path) -> None:
    """
    Atomically write the method report, stamped with the do-not-edit banner.

    Prepends the standard ``banner("geographic.features")`` provenance line
    (matching every other generated pipeline report) immediately after the report's
    H1 title, then writes the whole document via
    :func:`common.geo.atomic_write_text` — a tmp file + ``os.replace`` so a crash
    mid-write cannot leave a truncated report and any prior report is left intact
    until the rename succeeds (Req 2.7).

    The banner is inserted here rather than in :func:`_build_report` so the builder
    stays a pure, easily-testable string assembler and every report is guaranteed
    to carry the stamp regardless of who calls the builder.

    Parameters
    ----------
    report_text : str
        The report body produced by :func:`_build_report`. Expected to start with a
        single ``# `` H1 title line; the banner is inserted directly after it.
    path : Path
        Destination report path
        (``DATA/geographic/metadata/geographic_features_method.md``).
    """
    stamp = banner("geographic.features")

    # Insert the banner right after the H1 title so the report reads
    # "# Title\n\n*Generated by ...*\n" exactly like the other reports
    # (geographic.validate / geographic.derive stamp the banner after the H1).
    lines = report_text.split("\n", 1)
    if lines and lines[0].startswith("# "):
        title = lines[0]
        rest = lines[1] if len(lines) > 1 else ""
        stamped = f"{title}\n\n{stamp}\n{rest}"
    else:
        # No recognisable H1 — stamp at the very top so the banner is never lost.
        stamped = f"{stamp}\n{report_text}"

    atomic_write_text(Path(path), stamped)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(verbose: bool = False) -> dict:
    """
    Build per-cell geographic/environmental features on the common analysis grid.

    Reads the grid (cell_id + geometry) and the Sprint-0 geographic sources, derives
    one Feature_Table row per cell_id, writes it atomically as a GeoPackage, and
    writes a do-not-edit method report.

    Returns
    -------
    dict with keys:
        "feature_table" : Path   # output GeoPackage (exists on disk after return)
        "report"        : Path   # method report (exists on disk after return)
        "n_cells"       : int    # rows written == grid cell_id count
        "runtime_s"     : float  # total wall-clock seconds (Req 13.2, 13.3)

    Raises
    ------
    FileNotFoundError / ValueError / RuntimeError on any halting condition
        (missing grid, missing cell_id column, duplicate cell_id, missing/unreadable
        CAPAD, undeclared source CRS, write failure) — see design section Error
        Handling. On any raise the run returns no summary dict so the orchestrator
        halts with a non-zero exit (Req 10.3).
    """
    print("  Building geographic/environmental features (S1-06)...")
    print(f"    Grid: {GRID_PATH}")
    print(f"    Storage CRS: {STORAGE_CRS}")
    print(f"    Computation CRS: {COMPUTATION_CRS}")

    # GDAL env for any /vsicurl/ reads, matching validate.py (design §Performance).
    apply_vsicurl_env()

    t0 = time.time()

    # One CRS-transformation log for the whole run (Req 9.3, 9.5).
    crs_log: list[dict] = []

    # --- Read the grid (strict cell_id keying, Req 8) ------------------------
    cells = read_grid_cells(GRID_PATH)
    n_cells = len(cells)
    cell_ids = list(cells["cell_id"])
    print(f"    Grid cells: {n_cells:,}")

    # --- Load the ALUM class table (Req 3.3) ---------------------------------
    class_table = load_alum_class_table(ALUM_CLASS_TABLE_PATH)

    # --- Raster sources: open once each, reproject cells to each raster CRS --
    # (raster label, path, statistic-or-None-for-categorical)
    raster_specs = [
        ("elevation", ELEVATION_PATH, "mean"),
        ("slope", SLOPE_PATH, "mean"),
        ("tri", TRI_PATH, "mean"),
        ("nlum", NLUM_PATH, None),  # categorical (mode)
    ]

    # Per-cell stats keyed by raster label, aligned to cell_ids order. Each is a
    # list of CellStat / ModeResult, one entry per cell in native grid order.
    per_cell: dict[str, list] = {label: [] for label, _, _ in raster_specs}

    # Coverage / zero-valid bookkeeping (labels match _build_report expectations).
    coverage: dict[str, dict[str, int]] = {
        label: {"inside": 0, "outside": 0, "total": n_cells}
        for label, _, _ in raster_specs
    }
    zero_valid: dict[str, int] = {label: 0 for label, _, _ in raster_specs}
    unmapped_codes: set[int] = set()

    for label, path, stat in raster_specs:
        if verbose:
            print(f"    Sampling raster '{label}': {Path(path).name}")

        with rasterio.open(path) as src:
            # Reproject the whole cells GeoDataFrame to this raster's CRS ONCE
            # (vectorised) at the read boundary (Req 9.3); halts if CRS undeclared
            # / unresolvable (Req 9.4). Cells stay in native grid order.
            cells_in_crs = _reproject_cells_to_raster_crs(
                cells, src, source_id=Path(path).name, log=crs_log, verbose=verbose
            )
            geoms = list(cells_in_crs["geometry"])

            inside = 0
            zeros = 0
            if stat is None:
                # Categorical land-use mode (NLUM).
                results = per_cell[label]
                for geom in geoms:
                    res = _categorical_mode(src, geom, class_table)
                    results.append(res)
                    if res.in_coverage:
                        inside += 1
                    if res.n_valid == 0:
                        zeros += 1
                    if (
                        res.land_use is not None
                        and res.land_use.startswith("unmapped:")
                        and res.code is not None
                    ):
                        unmapped_codes.add(int(res.code))
            else:
                # Continuous terrain statistic (elevation / slope / tri).
                results = per_cell[label]
                for geom in geoms:
                    res = _zonal_raster_stat(src, geom, stat)
                    results.append(res)
                    if res.in_coverage:
                        inside += 1
                    if res.n_valid == 0:
                        zeros += 1

            coverage[label]["inside"] = inside
            coverage[label]["outside"] = n_cells - inside
            zero_valid[label] = zeros

        if verbose:
            print(
                f"      inside coverage: {inside:,} / {n_cells:,}; "
                f"zero-valid cells: {zeros:,}"
            )

    # --- Protected-area overlap (vectorised, Req 4) --------------------------
    if verbose:
        print(f"    Protected-area overlap (CAPAD): {Path(CAPAD_PATH).name}")

    capad = _load_capad(CAPAD_PATH)  # raises RuntimeError if missing/unreadable (4.7)
    cells_3577 = _reproject_to_computation_crs(
        cells, source_id="nsw_analysis_grid.gpkg", log=crs_log, verbose=verbose
    )
    capad_3577 = _reproject_to_computation_crs(
        capad, source_id=Path(CAPAD_PATH).name, log=crs_log, verbose=verbose
    )
    protected = _protected_overlap(cells_3577, capad_3577)

    # --- Assemble the one-row-per-cell_id Feature_Table (Req 7.1, 6.1) -------
    elevation_col: list[float | None] = []
    slope_col: list[float | None] = []
    tri_col: list[float | None] = []
    land_use_col: list[str | None] = []
    protected_area_col: list[bool] = []
    protected_area_name_col: list[str] = []
    confidence_col: list[str] = []

    confidence_counts: dict[str, int] = {CONFIDENCE_HIGH: 0, CONFIDENCE_LOW: 0}

    for i, cell_id in enumerate(cell_ids):
        elev = per_cell["elevation"][i]
        slope = per_cell["slope"][i]
        tri = per_cell["tri"][i]
        nlum = per_cell["nlum"][i]

        # Req 13.4 — every cell must be processed before completion; a missing
        # per-raster result means a cell was not processed -> halt (no summary).
        if elev is None or slope is None or tri is None or nlum is None:
            raise RuntimeError(
                f"Full-grid run did not process cell_id {cell_id!r} for every "
                f"required raster; halting without a successful runtime (Req 13.4)."
            )

        # Confidence over the required rasters (elevation, slope, NLUM); TRI is
        # excluded by _confidence_flag itself (Req 5, 6.4).
        confidence = _confidence_flag(
            {"elevation": elev, "slope": slope, "nlum": nlum}
        )
        confidence_counts[confidence] += 1

        prot_flag, prot_name = protected[cell_id]

        elevation_col.append(elev.value)
        slope_col.append(slope.value)
        tri_col.append(tri.value)
        land_use_col.append(nlum.land_use)
        protected_area_col.append(prot_flag)
        protected_area_name_col.append(prot_name)
        confidence_col.append(confidence)

    feature_gdf = gpd.GeoDataFrame(
        {
            "cell_id": cell_ids,
            "elevation_m": elevation_col,
            "slope_deg": slope_col,
            "land_use": land_use_col,
            "protected_area": protected_area_col,
            "protected_area_name": protected_area_name_col,
            "tri": tri_col,
            "confidence_flag": confidence_col,
        },
        geometry=list(cells["geometry"]),  # copied byte-for-byte from grid (Req 7.3)
        crs=STORAGE_CRS,
    )
    # Enforce exact schema column order (Req 7.1) plus geometry.
    feature_gdf = feature_gdf[SCHEMA_COLUMNS + ["geometry"]]

    # --- Write the Feature_Table atomically (Req 7.5) ------------------------
    _write_feature_table(feature_gdf, OUTPUT_PATH)
    print(f"    Feature table: {OUTPUT_PATH.relative_to(PROJECT_ROOT)}")

    # --- Build + write the method report (Req 2.5, 5.6, 6.5, 9.5, 13.2) ------
    runtime_s = time.time() - t0

    report_text = _build_report(
        coverage=coverage,
        zero_valid=zero_valid,
        unmapped_codes=unmapped_codes,
        confidence_counts=confidence_counts,
        crs_log=crs_log,
        runtime_s=runtime_s,
        n_cells=n_cells,
    )
    _write_report(report_text, REPORT_PATH)
    print(f"    Method report: {REPORT_PATH.relative_to(PROJECT_ROOT)}")

    print(
        f"\n  Done in {runtime_s:.1f}s — {n_cells:,} cells; "
        f"confidence high={confidence_counts[CONFIDENCE_HIGH]:,}, "
        f"low={confidence_counts[CONFIDENCE_LOW]:,}"
    )

    # Summary dict returned ONLY on success (Req 10.2, 10.3, 13.2, 13.3). Keys
    # are the on-disk output paths that exist after return.
    return {
        "feature_table": OUTPUT_PATH,
        "report": REPORT_PATH,
        "n_cells": n_cells,
        "runtime_s": runtime_s,
    }


# ---------------------------------------------------------------------------
# Validation (Req 11) — no silent passes
# ---------------------------------------------------------------------------


def validate(feature_table_path: Path, grid_path: Path) -> dict:
    """
    Validate a written Feature_Table against the analysis grid — no silent passes.

    Reads the written Feature_Table GeoPackage and the analysis grid, then emits
    one ``{"name", "expected", "observed", "passed"}`` check dict per requirement,
    exactly the shape used by ``pipeline/validate.py`` and
    ``pipeline/geographic/validate.py`` (expected/observed are human-readable
    strings; ``passed`` is a plain ``bool``). Every check reports expected vs
    observed vs pass/fail so nothing passes silently.

    Checks (design §Testing Strategy, validation checks):
        - Row count == grid cell count (Req 11.1): expected = grid ``cell_id``
          count; observed = Feature_Table row count.
        - Exact ``cell_id`` set match (Req 11.2): expected = grid ``cell_id`` set;
          observed = missing count + extra count (both 0 to pass).
        - Schema columns match Req 7 (Req 11.3): expected = the eight
          :data:`SCHEMA_COLUMNS`; observed = the actual non-geometry columns.
        - ``slope_deg`` in [0, 90] or null (Req 11.4): observed = count of
          out-of-range non-null cells (0 to pass).
        - ``confidence_flag`` in {high, low} (Req 11.5): observed = count of any
          other value (0 to pass).

    Parameters
    ----------
    feature_table_path : Path
        Path to the written Feature_Table GeoPackage
        (``DATA/geographic/features/optmining_geographic-features_2024_nsw.gpkg``).
    grid_path : Path
        Path to the analysis-grid GeoPackage (``DATA/grid/nsw_analysis_grid.gpkg``).

    Returns
    -------
    dict
        ``{"checks": [ {name, expected, observed, passed}, ... ], "passed": int,
        "total": int}`` — ``passed`` is the count of passing checks and ``total``
        the total number of checks, mirroring the summary shape of the other
        validate stages.
    """
    checks: list[dict] = []

    def check(name, expected, observed, passed):
        checks.append({"name": name, "expected": expected,
                       "observed": observed, "passed": bool(passed)})

    # Read the grid via the strict cell_id reader (Req 8 keying) and the written
    # Feature_Table via geopandas, matching how validate.py sources gpkg layers.
    grid = read_grid_cells(grid_path)
    table = gpd.read_file(feature_table_path)

    grid_cell_ids = list(grid["cell_id"])
    grid_count = len(grid_cell_ids)
    table_count = len(table)

    # --- Row count == grid cell count (Req 11.1) -----------------------------
    check(
        "Row count == grid cell count",
        f"{grid_count} rows",
        f"{table_count} rows",
        table_count == grid_count,
    )

    # --- Exact cell_id set match (Req 11.2) ----------------------------------
    grid_set = set(grid_cell_ids)
    table_set = set(table["cell_id"]) if "cell_id" in table.columns else set()
    missing = grid_set - table_set   # in grid but absent from the table
    extra = table_set - grid_set     # in table but not in the grid
    check(
        "Exact cell_id set match",
        "0 missing, 0 extra",
        f"{len(missing)} missing, {len(extra)} extra",
        len(missing) == 0 and len(extra) == 0,
    )

    # --- Schema columns match Req 7 (Req 11.3) -------------------------------
    # Compare the non-geometry columns against the exact eight SCHEMA_COLUMNS.
    actual_columns = [c for c in table.columns if c != "geometry"]
    check(
        "Schema columns match Req 7",
        f"{SCHEMA_COLUMNS}",
        f"{actual_columns}",
        actual_columns == SCHEMA_COLUMNS,
    )

    # --- slope_deg in [0, 90] or null (Req 11.4) -----------------------------
    if "slope_deg" in table.columns:
        slope = table["slope_deg"]
        non_null = slope.notna()
        out_of_range = int(((slope < 0) | (slope > 90))[non_null].sum())
    else:
        out_of_range = table_count  # column absent -> every cell is out of range
    check(
        "slope_deg in [0, 90] or null",
        "0 out-of-range non-null cells",
        f"{out_of_range} out-of-range non-null cells",
        out_of_range == 0,
    )

    # --- confidence_flag in {high, low} (Req 11.5) ---------------------------
    allowed = {CONFIDENCE_HIGH, CONFIDENCE_LOW}
    if "confidence_flag" in table.columns:
        bad_confidence = int((~table["confidence_flag"].isin(allowed)).sum())
    else:
        bad_confidence = table_count  # column absent -> every cell is invalid
    check(
        "confidence_flag in {high, low}",
        "0 invalid values",
        f"{bad_confidence} invalid values",
        bad_confidence == 0,
    )

    passed = sum(1 for c in checks if c["passed"])
    return {"checks": checks, "passed": passed, "total": len(checks)}
