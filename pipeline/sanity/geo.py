"""
CRS containment helper for the S1-12 sanity-check stage (`sanity`).

Every spatial-containment operation the sanity stage performs — locating a
Wind_Generators point to its Containing_Cell (Check 1) and locating a named
landmark to its cell (Check 2) — is carried out in ONE explicit, logged CRS
(``CONTAINMENT_CRS`` = EPSG:3577, Australian Albers equal-area). Storage is
EPSG:4326; a point-in-polygon test in geographic degrees is unsafe near cell
boundaries because degrees are not isotropic, so the transform to the metric
CRS is made explicit and recorded in a transform log rather than performed
silently. This mirrors the discipline in ``pipeline/infrastructure/features.py``
(``grid {STORAGE_CRS} → {computation_crs}`` transform-log line).

The single public helper :func:`locate_points_to_cells` reprojects BOTH the
points and the grid to the containment CRS, appends the transform to the
supplied ``transform_log``, and performs a ``predicate="within"`` spatial join.
It returns one row per input point with its Containing_Cell ``cell_id`` — or a
null ``cell_id`` when the point lies in NO grid cell (offshore / out-of-extent)
— so an out-of-extent point is reported honestly rather than dropped
(Requirement 2.7). It NEVER converts CRS silently.
"""

from __future__ import annotations

from dataclasses import dataclass

import geopandas as gpd
import pandas as pd


@dataclass(frozen=True)
class CrsTransform:
    """A single ``source -> target`` CRS transform, recorded for the report.

    The sanity stage records one :class:`CrsTransform` for every containment
    operation it performs, so the Validation_Report's transform-log line can
    enumerate each ``EPSG:4326 -> EPSG:3577`` transform verbatim — never a
    silent conversion. ``purpose`` names why the transform was applied, e.g.
    ``"wind-farm containment"`` or ``"landmark containment"``.
    """

    source: str  # e.g. "EPSG:4326"
    target: str  # e.g. "EPSG:3577"
    purpose: str  # e.g. "wind-farm containment" | "landmark containment"


def locate_points_to_cells(
    points: gpd.GeoDataFrame,
    grid: gpd.GeoDataFrame,
    containment_crs: str,
    transform_log: list[CrsTransform],
    *,
    purpose: str = "point containment",
) -> pd.DataFrame:
    """Locate each point to its Containing_Cell in one explicit, logged CRS.

    Both ``points`` and ``grid`` are reprojected to the single explicit
    ``containment_crs`` (EPSG:3577), the ``source -> containment_crs`` transform
    is appended to ``transform_log`` (Requirements 2.2, 3.5), and a
    point-in-polygon spatial join (``predicate="within"``) locates each point to
    the cell whose polygon contains it (Requirement 2.1).

    Returns a plain :class:`pandas.DataFrame` with one row per input point, in
    the input point order, carrying the input point index in ``point_index`` and
    the located Containing_Cell ``cell_id``. A point that lies in NO grid cell
    (offshore / out-of-extent) gets a null (``NA``) ``cell_id`` and is reported
    honestly rather than dropped (Requirement 2.7). CRS is NEVER converted
    silently: an input frame with no resolvable CRS is a fatal error.

    Args:
        points: point features in EPSG:4326 storage (or any resolvable CRS).
        grid: the Analysis_Grid cell polygons in EPSG:4326 storage, carrying
            ``cell_id``.
        containment_crs: the single explicit containment CRS, EPSG:3577.
        transform_log: mutable list the applied transforms are appended to; the
            report renders it verbatim.
        purpose: label recorded on the appended :class:`CrsTransform` describing
            why the containment was performed (e.g. wind-farm vs landmark).

    Returns:
        A DataFrame with columns ``point_index`` (the original index of each
        input point) and ``cell_id`` (the Containing_Cell, or ``NA`` when the
        point is out-of-extent), with exactly one row per input point.

    Raises:
        ValueError: if ``grid`` lacks a ``cell_id`` column, or if either the
            points or the grid has no resolvable CRS (never assume a projection).
    """
    if "cell_id" not in grid.columns:
        raise ValueError("locate_points_to_cells: grid is missing the 'cell_id' column")
    if points.crs is None:
        raise ValueError(
            "locate_points_to_cells: points have no resolvable CRS; refusing to "
            "assume a projection (CRS must be explicit)"
        )
    if grid.crs is None:
        raise ValueError(
            "locate_points_to_cells: grid has no resolvable CRS; refusing to "
            "assume a projection (CRS must be explicit)"
        )

    # Preserve the input point order/identity so no point is ever dropped: the
    # spatial join drops non-matching rows, so we re-index against this later.
    points = points.copy()
    points["point_index"] = points.index

    # Reproject BOTH frames to the single explicit containment CRS and log each
    # transform, mirroring infrastructure/features.py. Record the transform even
    # when a frame is already in the containment CRS so the report is honest
    # about what CRS the containment ran in.
    points_src = points.crs.to_string()
    grid_src = grid.crs.to_string()
    points_c = points.to_crs(containment_crs)
    grid_c = grid.to_crs(containment_crs)
    target = grid_c.crs.to_string()
    transform_log.append(
        CrsTransform(source=points_src, target=target, purpose=f"{purpose} (points)")
    )
    transform_log.append(
        CrsTransform(source=grid_src, target=target, purpose=f"{purpose} (grid)")
    )

    # Point-in-polygon join: each point matches the cell whose polygon contains
    # it. A well-formed interior point matches exactly one cell; an out-of-extent
    # point matches none.
    grid_polygons = grid_c[["cell_id", "geometry"]]
    joined = gpd.sjoin(
        points_c[["point_index", "geometry"]],
        grid_polygons,
        how="left",
        predicate="within",
    )

    # A point that straddles a shared cell boundary could in principle match
    # more than one cell; collapse to the first match deterministically by
    # point_index so the result stays one row per input point.
    joined = joined.sort_values("point_index").drop_duplicates(subset="point_index", keep="first")

    # Re-index against every input point so out-of-extent points survive with a
    # null cell_id (reported honestly, never dropped — Requirement 2.7).
    located = (
        joined.set_index("point_index")["cell_id"]
        .reindex(points["point_index"].to_numpy())
    )
    result = pd.DataFrame(
        {
            "point_index": points["point_index"].to_numpy(),
            "cell_id": located.to_numpy(),
        }
    )
    return result.reset_index(drop=True)
