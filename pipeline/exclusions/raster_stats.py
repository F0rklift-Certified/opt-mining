"""
Reusable raster zonal-mean helper for the exclusion layer.

Implements the same cell-centre pixel-inclusion rule already used elsewhere
in this codebase (`pipeline.validate._point_in_polygons`'s rasterisation,
`pipeline.geographic.derive`'s windowed reads) so the exclusion layer's
slope/wind sampling is consistent with the rest of the pipeline rather than
inventing a fresh convention. This is the same idiom the S1-06 design
document (`Sprint-1-Tasks/S1-06-.../design.md` §"Zonal-statistics method")
specifies for the (not yet implemented) geographic feature builder — kept
identical here so a future migration to that module's real Feature_Table is
a drop-in replacement, not a behaviour change.

Coverage short-circuit: a cell whose centroid falls outside the raster's
bounds never triggers a windowed read (`in_coverage=False`, value=None).
This matters because the current source rasters cover only a small window
of the full NSW grid.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import rasterio
from rasterio.features import geometry_mask
from rasterio.windows import from_bounds


@dataclass
class CellRasterStat:
    value: float | None
    n_valid: int
    n_nodata: int
    in_coverage: bool


def raster_bounds_contains(src: "rasterio.DatasetReader", lon: float, lat: float) -> bool:
    """Cell-centroid-in-raster-bounds fast coverage test."""
    left, bottom, right, top = src.bounds
    return (left <= lon <= right) and (bottom <= lat <= top)


def _valid_mask(data: np.ndarray, nodata) -> np.ndarray:
    """Boolean mask of pixels that are NOT NoData (handles NaN nodata too)."""
    if nodata is None:
        valid = np.ones(data.shape, dtype=bool)
    elif isinstance(nodata, float) and np.isnan(nodata):
        valid = ~np.isnan(data)
    else:
        valid = data != nodata
    if np.issubdtype(data.dtype, np.floating):
        # Defensive: exclude NaN even if a non-NaN nodata value is also declared.
        valid &= ~np.isnan(data)
    return valid


def zonal_mean(
    src: "rasterio.DatasetReader",
    cell_geom,
    centroid: tuple[float, float],
) -> CellRasterStat:
    """
    Windowed mean of `src`'s band 1 over one cell polygon.

    Parameters
    ----------
    src : open rasterio dataset (band 1 is read)
    cell_geom : shapely polygon, in `src`'s CRS
    centroid : (lon, lat) of the cell centroid, in `src`'s CRS — the caller
        is responsible for reprojecting both `cell_geom` and `centroid` if
        the raster's CRS differs from the storage CRS (see apply.py).

    Pixel inclusion is the cell-centre rule (`all_touched=False`), matching
    `pipeline.validate` / `pipeline.geographic.derive`. NoData pixels
    (declared `src.nodata`, including NaN, plus any other NaN defensively)
    are excluded from the mean. `src.scales[0]` is applied if declared
    (e.g. the 0.01°-scaled int16 slope raster).
    """
    lon, lat = centroid
    if not raster_bounds_contains(src, lon, lat):
        return CellRasterStat(value=None, n_valid=0, n_nodata=0, in_coverage=False)

    window = from_bounds(*cell_geom.bounds, transform=src.transform)
    window = window.round_offsets().round_lengths()
    if window.width <= 0 or window.height <= 0:
        return CellRasterStat(value=None, n_valid=0, n_nodata=0, in_coverage=False)

    data = src.read(1, window=window)
    win_transform = src.window_transform(window)

    # True = pixel centre falls inside the cell polygon (all_touched=False,
    # invert=True gives "inside" rather than geometry_mask's default "outside").
    inside = geometry_mask(
        [cell_geom], out_shape=data.shape, transform=win_transform,
        all_touched=False, invert=True,
    )

    valid = inside & _valid_mask(data, src.nodata)
    n_valid = int(valid.sum())
    n_nodata = int(inside.sum()) - n_valid

    if n_valid == 0:
        # Centroid was in bounds, but no usable pixel inside the cell —
        # classify as out of coverage rather than a spurious zero/None split.
        return CellRasterStat(value=None, n_valid=0, n_nodata=n_nodata, in_coverage=False)

    scale = src.scales[0] if src.scales and src.scales[0] else 1.0
    value = float(data[valid].mean()) * scale
    return CellRasterStat(value=value, n_valid=n_valid, n_nodata=n_nodata, in_coverage=True)
