"""
Output writers for the S1-11 shortlist stage (Requirements 5, 8.3).

This module turns the assembled in-memory Shortlist frame (the documented
``config.SHORTLIST_COLUMNS`` in order, plus any optional context column) into
the two Sprint 1 headline artefacts:

  * the Shortlist_CSV — a tabular export for spreadsheet review (5.1); and
  * the Shortlist_GeoJSON — one feature per shortlisted cell for map
    visualisation, in EPSG:4326 with the CRS stated explicitly (5.2, 5.3).

Both writers draw from the SAME in-memory frame, so by construction the CSV and
the GeoJSON carry the same ``cell_id`` set in the same rank order (5.5) — the
row order of ``shortlist`` (the S1-10 ascending-``rank`` ordering the earlier
stages preserved) is written verbatim in both.

Two rules are load-bearing and named here:

  ATOMIC, ALL-OR-NOTHING. Every file is written via ``common.geo`` using a
  sibling temporary file plus ``os.replace`` (5.6). ``os.replace`` is atomic on
  the same filesystem, so a reader never sees a half-written file and — if the
  write fails partway — any pre-existing output for that path is left
  unmodified and the error propagates (5.7). The CSV reuses
  ``common.geo.atomic_write_text``; the GeoJSON serialises a FeatureCollection
  dict and reuses ``common.geo.atomic_write_text`` too, so both share one
  audited tmp+rename path.

  EXPLICIT CRS, NO REPROJECTION. ``centroid_lat`` / ``centroid_lon`` arrive from
  the grid in EPSG:4326 and are written unchanged; the GeoJSON declares its CRS
  explicitly rather than leaving it implied (5.3). This stage performs NO
  reprojection — there is no distance or area computation here.

The Shortlist_GeoJSON also carries the Preliminary_Disclaimer and the
Analysis_Resolution statement as file-level foreign members on the
FeatureCollection (8.3), so a consumer who opens only the GeoJSON still sees
that this is a preliminary screening layer at the ~5 km resolution and never a
site approval. (The CSV has no metadata rows, so its disclaimer travels via the
Summary_Report and the metadata sidecar — task 10 — per 8.4.)

Design reference: design.md §7 "Output writers".
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

import pandas as pd

from ..common.geo import atomic_write_text
from ..grid import config as _grid_config
from . import config

# The half-cell offset (degrees) used to build the cell polygon from the
# centroid for the "polygon" geometry choice. Reused from the authoritative
# grid config (``CELL_DEG`` = 0.05, the ~5 km analysis cell) rather than
# hardcoded, so a change to the grid cell size propagates here (5.4).
HALF_CELL_DEG = _grid_config.CELL_DEG / 2.0

# The GeoJSON is written in the storage CRS. RFC 7946 fixes GeoJSON to WGS84
# (EPSG:4326); we ALSO state the CRS explicitly as a foreign member rather than
# leaving it implied (5.3, Constitution: never assume an unstated CRS).
_GEOJSON_CRS = config.STORAGE_CRS  # "EPSG:4326"


# ---------------------------------------------------------------------------
# CSV writer (Requirement 5.1, 5.6, 5.7; 3.6)
# ---------------------------------------------------------------------------


def write_csv(shortlist: pd.DataFrame, path: Path | str) -> None:
    """
    Atomically write the Shortlist_CSV to ``path`` (Requirement 5.1, 5.6, 5.7).

    The columns are written in the documented order — ``config.SHORTLIST_COLUMNS``
    followed by any optional context column present on ``shortlist`` — exactly
    as the assembled frame carries them (5.1). Writing is atomic: the CSV text
    is materialised in memory, then written via ``common.geo.atomic_write_text``
    (sibling tmp file + ``os.replace``), so a reader never sees a partial file
    and a failed write leaves any pre-existing output unmodified (5.6, 5.7).

    An EMPTY shortlist (zero eligible cells, Requirement 3.6) still writes a
    header row for the documented columns, so the CSV is always well-formed and
    headered rather than a zero-byte file.

    Formatting matches ``integration.merge.write_csv`` for cross-stage
    consistency: ``index=False``, nulls rendered empty, ``"\\n"`` line endings,
    UTF-8 — so the output is byte-stable across reruns with unchanged inputs.

    Raises
    ------
    KeyError
        If ``shortlist`` is missing any of the documented core
        ``config.SHORTLIST_COLUMNS`` — a fail-fast condition (the assembler
        guarantees these, so their absence means an upstream contract break)
        raised BEFORE any file is written.
    """
    frame = _ordered_frame(shortlist)

    # Serialise to a CSV string first so the tmp+rename in atomic_write_text is
    # the only filesystem mutation — an all-or-nothing write (5.6, 5.7). Headers
    # are always emitted, so an empty shortlist yields a headered file (3.6).
    text = frame.to_csv(index=False, na_rep="", lineterminator="\n")
    atomic_write_text(Path(path), text)


# ---------------------------------------------------------------------------
# GeoJSON writer (Requirement 5.2, 5.3, 5.4, 5.6, 5.7; 8.3)
# ---------------------------------------------------------------------------


def write_geojson(
    shortlist: pd.DataFrame,
    path: Path | str,
    geometry: str = config.DEFAULT_GEOMETRY,
) -> None:
    """
    Atomically write the Shortlist_GeoJSON to ``path`` (Requirement 5.2, 5.3,
    5.4, 5.6, 5.7, 8.3).

    Produces a GeoJSON ``FeatureCollection`` with one feature per shortlisted
    cell, in the ``shortlist`` row order (the S1-10 ascending-``rank`` ordering),
    so the GeoJSON carries the same ``cell_id`` set in the same order as the CSV
    (5.5). Each feature carries the documented columns
    (``config.SHORTLIST_COLUMNS`` + any optional context column) as feature
    ``properties`` (5.2).

    Geometry follows the documented choice ``geometry`` (5.4):
      * ``"centroid"`` (default) — a ``Point`` at ``(centroid_lon, centroid_lat)``;
      * ``"polygon"`` — the cell ``Polygon`` built from the centroid using the
        grid ``CELL_DEG`` half-cell offsets (``HALF_CELL_DEG``), reusing the
        authoritative grid cell size rather than hardcoding it.
    The chosen geometry type is recorded for the Summary_Report by the caller
    (which passes the same ``geometry`` value to the report writer).

    CRS is stated EXPLICITLY as a file-level foreign member (EPSG:4326); the
    coordinates are written unchanged from the grid — no reprojection (5.3).

    File-level foreign members also carry the Preliminary_Disclaimer and the
    Analysis_Resolution statement, so a consumer who opens only the GeoJSON sees
    the screening disclaimer and the ~5 km resolution (8.3).

    Writing is atomic: the FeatureCollection is serialised to a JSON string,
    then written via ``common.geo.atomic_write_text`` (sibling tmp file +
    ``os.replace``), so a failed write leaves any pre-existing output unmodified
    (5.6, 5.7).

    An EMPTY shortlist (Requirement 3.6) writes a FeatureCollection with an
    empty ``features`` array that still carries the CRS, disclaimer, and
    resolution foreign members — a well-formed, disclaimer-carrying output
    rather than a crash.

    Raises
    ------
    ValueError
        If ``geometry`` is not one of ``config.GEOMETRY_CHOICES`` — raised
        BEFORE any file is written, naming the invalid choice.
    KeyError
        If ``shortlist`` is missing any documented core column — a fail-fast
        contract check raised before any write.
    """
    if geometry not in config.GEOMETRY_CHOICES:
        raise ValueError(
            f"Unknown GeoJSON geometry choice {geometry!r}; expected one of "
            f"{config.GEOMETRY_CHOICES} (see config.DEFAULT_GEOMETRY)."
        )

    frame = _ordered_frame(shortlist)
    property_columns = list(frame.columns)

    features = [
        _feature(row, property_columns, geometry)
        for _, row in frame.iterrows()
    ]

    collection = {
        "type": "FeatureCollection",
        # Explicit CRS statement (5.3). RFC 7946 fixes GeoJSON to WGS84; the
        # legacy "crs" member names it unambiguously for consumers that read it,
        # and "crs_statement" states it in plain text so it is never implied.
        "crs": {
            "type": "name",
            "properties": {"name": f"urn:ogc:def:crs:{_GEOJSON_CRS.replace(':', '::')}"},
        },
        "crs_statement": _GEOJSON_CRS,
        # File-level disclaimer + resolution so the GeoJSON alone carries them
        # (8.3). These are GeoJSON foreign members (allowed by RFC 7946 §6.1).
        "geometry_type": geometry,
        "preliminary_disclaimer": config.PRELIMINARY_DISCLAIMER,
        "analysis_resolution": config.ANALYSIS_RESOLUTION,
        "features": features,
    }

    # Serialise fully in memory, THEN write via the audited tmp+os.replace path
    # so the write is all-or-nothing and a failure leaves any prior file intact
    # (5.6, 5.7). Compact separators match the pipeline's other GeoJSON writers.
    text = json.dumps(collection, separators=(",", ":")) + "\n"
    atomic_write_text(Path(path), text)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _ordered_frame(shortlist: pd.DataFrame) -> pd.DataFrame:
    """
    Return ``shortlist`` with the documented columns first, in order, followed
    by any optional context column present, so both writers emit the SAME
    documented column order (5.1, 5.2).

    The assembler (``assemble.assemble_shortlist``) already produces this order,
    but reselecting here makes each writer independently correct and fail-fast:
    a missing core column raises ``KeyError`` naming it, before any write.
    """
    core = list(config.SHORTLIST_COLUMNS)
    missing = [c for c in core if c not in shortlist.columns]
    if missing:
        raise KeyError(
            f"Shortlist frame is missing documented column(s) {missing}; the "
            f"writers require {core} in that order. An absent core column means "
            f"an upstream stage broke the shortlist schema contract."
        )
    optional = [c for c in config.OPTIONAL_CONTEXT_COLUMNS if c in shortlist.columns]
    return shortlist.loc[:, core + optional]


def _json_scalar(value):
    """
    Coerce a pandas/numpy scalar to a JSON-serialisable Python scalar for a
    feature property.

    A null (``NaN`` / ``None`` / ``pd.NA``) becomes JSON ``null`` rather than a
    non-conformant ``NaN`` token; numpy integers/floats/bools become their
    Python equivalents; everything else is stringified defensively so the
    serialisation can never fail on an exotic dtype.
    """
    if value is None:
        return None
    # pd.isna raises on array-likes; feature properties are scalars, so this is
    # safe and treats NaN/NaT/pd.NA uniformly as JSON null.
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, (int,)):
        return int(value)
    if isinstance(value, float):
        return float(value)
    # numpy scalar types expose .item(); fall back to a str otherwise.
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return item()
        except (TypeError, ValueError):
            pass
    return str(value)


def _point_geometry(lon: float, lat: float) -> dict:
    """A GeoJSON ``Point`` at the cell centroid, in EPSG:4326 (5.3, 5.4)."""
    return {"type": "Point", "coordinates": [lon, lat]}


def _polygon_geometry(lon: float, lat: float) -> dict:
    """
    A GeoJSON ``Polygon`` for the cell, built from the centroid using the grid
    ``CELL_DEG`` half-cell offsets (``HALF_CELL_DEG``), in EPSG:4326 (5.3, 5.4).

    The ring is closed (first coordinate repeated last) and wound
    counter-clockwise (RFC 7946 §3.1.6 exterior-ring convention) starting at the
    south-west corner.
    """
    h = HALF_CELL_DEG
    west, east = lon - h, lon + h
    south, north = lat - h, lat + h
    ring = [
        [west, south],
        [east, south],
        [east, north],
        [west, north],
        [west, south],
    ]
    return {"type": "Polygon", "coordinates": [ring]}


def _feature(row: pd.Series, property_columns: list[str], geometry: str) -> dict:
    """
    Build one GeoJSON ``Feature`` for a shortlisted cell (5.2, 5.4).

    Properties carry the documented columns (``property_columns``) with null
    coerced to JSON ``null``; the geometry is the centroid Point or the cell
    Polygon per ``geometry``. The centroid coordinates come from the grid join
    (EPSG:4326) and are written unchanged — no reprojection (5.3).
    """
    lat = float(row["centroid_lat"])
    lon = float(row["centroid_lon"])
    if math.isnan(lat) or math.isnan(lon):
        # Defensive: coords.join_coordinates already halts on any unmatched
        # cell_id, so a null coordinate here means an upstream contract break.
        raise ValueError(
            f"Shortlisted cell {row.get('cell_id')!r} has a null centroid "
            f"coordinate; the coordinate join must halt before a row reaches "
            f"the writers (Requirement 4.5)."
        )

    if geometry == "polygon":
        geom = _polygon_geometry(lon, lat)
    else:
        geom = _point_geometry(lon, lat)

    properties = {col: _json_scalar(row[col]) for col in property_columns}
    return {"type": "Feature", "properties": properties, "geometry": geom}
