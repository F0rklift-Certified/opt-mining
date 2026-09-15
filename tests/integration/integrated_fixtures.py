"""
Schema-driven fixtures for the S2-02 integrated-table input-contract gate.

These helpers build a *tiny* but *schema-faithful* integrated feature table
(a handful of cells) entirely from the Schema_Authority constants — never from
a re-typed column list — so a schema change in `pipeline/integration/config.py`
/ `merge.py` (a renamed or added column, a new scored feature, a changed unit)
propagates into the fixtures rather than letting the tests drift out of sync
(Requirements 13.1, 13.3).

The good fixture (`make_integrated_fixture`) is a valid table:

  * every column of `OUTPUT_COLUMNS`, in order, plus `geometry`;
  * the scored columns of `SCORED_FEATURE_COLUMNS` populated with in-range
    values drawn from `SANITY_RANGES`;
  * the `BOOL_COLUMNS` (`inside_rez`, `protected_area`, `eligible`) typed as
    numpy `bool`;
  * valid `EPSG:4326` polygon geometries whose centroids sit inside the NSW
    analysis bounding box (`grid.config.NSW_BBOX`), with matching
    `centroid_lat` / `centroid_lon`;
  * unique, non-null `cell_id`;
  * consistent `eligible` / `exclusion_reason` (the exact invariant
    `pipeline/integration/merge.py::validate` re-asserts: an eligible cell has
    no exclusion reason, an ineligible cell has one);
  * at least one Eligible_Cell.

The known-bad mutators each take the good GeoDataFrame and inject *exactly one*
defect, so a per-check test can assert that its target check — and only its
target check — flips to ``passed=False`` (Requirement 13.2).

`write_fixture_gpkg` writes a fixture to a temp GeoPackage (layer
`OUTPUT_LAYER`) for the `integrated_path=` override on
`pipeline.validate.run()` / `_run_integrated_input_checks()`.

This module is imported by the later check-test tasks (4.2, 4.4, 4.6, 4.8,
6.2, 7.2 and the property tests 8.x). It contains fixtures/helpers only — no
checks and no `run()` wiring.
"""

from __future__ import annotations

import os
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

gpd = pytest.importorskip("geopandas")
pytest.importorskip("pyogrio")
from shapely.geometry import box  # noqa: E402

# --- Schema_Authority: read the schema, never re-type it. -------------------
from pipeline.integration.config import (  # noqa: E402
    OUTPUT_LAYER,
    SCORED_FEATURE_COLUMNS,
    STORAGE_CRS,
)
from pipeline.integration.merge import (  # noqa: E402
    BOOL_COLUMNS,
    COLUMN_UNITS,
    OUTPUT_COLUMNS,
)
from pipeline.grid.config import NSW_BBOX  # noqa: E402
from pipeline.validate import SANITY_RANGES  # noqa: E402


# ---------------------------------------------------------------------------
# In-range value derivation from the schema constants
# ---------------------------------------------------------------------------

# The per-layer confidence vocabularies the merged table carries. Read from the
# integration config so a vocabulary change flows through; a plausible value is
# picked for the good fixture (validity of these flags is a merge-time concern,
# not an input-contract check, but the columns must be present and populated).
_TEXT_COLUMN_VALUES: dict[str, str] = {
    "wind_confidence": "valid",
    "demand_confidence": "high",
    "infra_confidence": "high",
    "geo_confidence": "high",
    "source_region": "NSW1",
    "rez_name": "New England REZ",
    "protected_area_name": "",
    "land_use": "3.2.0 Grazing modified pastures",
    "triggered_rules": None,
    "data_flags": None,
    "data_confidence": "high",
    "confidence_notes": "\u2014",  # "—" — the CONFIDENCE_NO_NOTES sentinel
}


def _in_range_value(column: str) -> float:
    """
    A value comfortably inside the column's Sanity_Range.

    For a numeric range ``(lo, hi)`` returns the midpoint; for a boolean
    Sanity_Range returns ``False`` (a valid member of ``{False, True}``). Only
    columns with a `SANITY_RANGES` entry are handled here; other scored columns
    (e.g. `dist_connection_km`, `land_use`) get their values elsewhere.
    """
    bound = SANITY_RANGES[column]
    if isinstance(bound, frozenset):
        return False
    lo, hi = bound
    return (lo + hi) / 2.0


def _scored_value(column: str):
    """A valid in-contract value for any scored feature column."""
    if column in SANITY_RANGES:
        return _in_range_value(column)
    if column == "land_use":
        return _TEXT_COLUMN_VALUES["land_use"]
    if column == "dist_connection_km":
        # No Sanity_Range is defined for dist_connection_km (it is not one of
        # the ranged columns in the design's Model 3); a plausible float keeps
        # it non-null so it does not register as a missing value.
        return 10.0
    # Fallback for a newly added scored column with no explicit handling: a
    # neutral float. A schema change that adds a scored column surfaces here.
    return 0.0


# ---------------------------------------------------------------------------
# Good fixture
# ---------------------------------------------------------------------------

DEFAULT_N_CELLS = 4


def _cell_geometry(index: int):
    """
    A 0.05° square cell inside the NSW analysis bounding box.

    Cells march east along a fixed latitude just inside the box's southern
    edge, so every centroid is unambiguously within `NSW_BBOX`.
    """
    west, south, east, north = NSW_BBOX
    size = 0.05
    lon = west + 1.0 + size * index  # 1° in from the western edge
    lat = south + 1.0               # 1° up from the southern edge
    return box(lon - size / 2, lat - size / 2, lon + size / 2, lat + size / 2), lon, lat


def make_integrated_fixture(n_cells: int = DEFAULT_N_CELLS) -> "gpd.GeoDataFrame":
    """
    Build a valid integrated-table GeoDataFrame from the schema constants.

    Every column of ``OUTPUT_COLUMNS`` is present (in order), plus ``geometry``.
    Scored columns are populated with in-range values from ``SANITY_RANGES``;
    ``BOOL_COLUMNS`` are numpy ``bool``; geometries are valid ``EPSG:4326``
    polygons whose centroids lie inside ``NSW_BBOX``; ``cell_id`` is unique and
    non-null; ``eligible`` / ``exclusion_reason`` are consistent; and the first
    cell is an Eligible_Cell.

    The last cell is made ineligible (with a matching exclusion reason) so the
    good fixture exercises both eligibility states while still satisfying the
    "at least one eligible cell" contract.
    """
    if n_cells < 2:
        raise ValueError("need at least two cells to exercise both eligibility states")

    geoms, records = [], []
    for i in range(n_cells):
        geom, lon, lat = _cell_geometry(i)
        geoms.append(geom)
        # Last cell ineligible; the rest eligible.
        eligible = i < (n_cells - 1)
        record: dict[str, object] = {}
        for column in OUTPUT_COLUMNS:
            if column == "cell_id":
                record[column] = f"CELL_{i:03d}"
            elif column == "centroid_lat":
                record[column] = lat
            elif column == "centroid_lon":
                record[column] = lon
            elif column == "area_km2":
                record[column] = 25.0
            elif column == "eligible":
                record[column] = eligible
            elif column == "exclusion_reason":
                record[column] = None if eligible else "Slope exceeds 15\u00b0"
            elif column == "n_missing_features":
                record[column] = 0
            elif column == "confidence_score":
                record[column] = 0.9
            elif column in SCORED_FEATURE_COLUMNS:
                record[column] = _scored_value(column)
            elif column in _TEXT_COLUMN_VALUES:
                record[column] = _TEXT_COLUMN_VALUES[column]
            else:
                # Any unhandled column (a schema addition) gets a neutral, non
                # null placeholder so the fixture stays complete and the gap is
                # visible to whoever added the column.
                record[column] = 0.0
        records.append(record)

    frame = pd.DataFrame.from_records(records, columns=list(OUTPUT_COLUMNS))

    # Type the boolean columns as numpy bool (no nulls in the good fixture),
    # matching merge.py's null-free convention.
    for column in BOOL_COLUMNS:
        frame[column] = frame[column].astype(bool)

    gdf = gpd.GeoDataFrame(frame, geometry=geoms, crs=STORAGE_CRS)
    return gdf


# ---------------------------------------------------------------------------
# GeoPackage writer
# ---------------------------------------------------------------------------


def write_fixture_gpkg(gdf: "gpd.GeoDataFrame", tmp_path: Path,
                       name: str = "integrated_fixture.gpkg") -> Path:
    """
    Write ``gdf`` to a temp GeoPackage (layer ``OUTPUT_LAYER``) and return the
    path, for use with the ``integrated_path=`` override.

    Uses the same atomic tmp-file + ``os.replace`` discipline as the pipeline
    writers so a reader never sees a partial file. Warnings from pyogrio (e.g.
    a mixed/absent CRS injected by a fault-injection mutator) are silenced —
    those defects are exactly what the checks are meant to catch.
    """
    path = Path(tmp_path) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + "_tmp.gpkg")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        gdf.to_file(tmp, driver="GPKG", layer=OUTPUT_LAYER)
        os.replace(tmp, path)
    return path


# ---------------------------------------------------------------------------
# Known-bad mutators — each injects exactly one defect
# ---------------------------------------------------------------------------
#
# Every mutator takes a *good* GeoDataFrame (or a copy of one) and returns a
# new GeoDataFrame carrying a single defect. They never mutate their argument
# in place (a shared good fixture stays clean for the next case).


def _copy(gdf: "gpd.GeoDataFrame") -> "gpd.GeoDataFrame":
    return gdf.copy(deep=True)


def drop_required_column(gdf: "gpd.GeoDataFrame",
                         column: str = "area_km2") -> "gpd.GeoDataFrame":
    """Drop a required (`OUTPUT_COLUMNS`) column — fails the required-columns check."""
    if column not in OUTPUT_COLUMNS:
        raise ValueError(f"{column!r} is not an OUTPUT_COLUMNS member")
    if column in SCORED_FEATURE_COLUMNS:
        raise ValueError(f"{column!r} is a scored column; use drop_scored_column")
    return _copy(gdf).drop(columns=[column])


def drop_scored_column(gdf: "gpd.GeoDataFrame",
                       column: str = "wind_speed") -> "gpd.GeoDataFrame":
    """Drop a scored (`SCORED_FEATURE_COLUMNS`) column — fails the scored-columns check."""
    if column not in SCORED_FEATURE_COLUMNS:
        raise ValueError(f"{column!r} is not a SCORED_FEATURE_COLUMNS member")
    return _copy(gdf).drop(columns=[column])


def null_cell_id(gdf: "gpd.GeoDataFrame") -> "gpd.GeoDataFrame":
    """Null one `cell_id` — fails the cell_id-non-null check."""
    out = _copy(gdf)
    out.loc[out.index[0], "cell_id"] = None
    return out


def duplicate_cell_id(gdf: "gpd.GeoDataFrame") -> "gpd.GeoDataFrame":
    """Duplicate a `cell_id` — fails the cell_id-uniqueness check."""
    out = _copy(gdf)
    out.loc[out.index[1], "cell_id"] = out.loc[out.index[0], "cell_id"]
    return out


def out_of_range_wind_speed(gdf: "gpd.GeoDataFrame",
                            value: float = 999.0) -> "gpd.GeoDataFrame":
    """Set an out-of-range `wind_speed` — fails that column's units/ranges check."""
    out = _copy(gdf)
    out.loc[out.index[0], "wind_speed"] = value
    return out


def out_of_range_centroid_lat(gdf: "gpd.GeoDataFrame",
                              value: float = 91.0) -> "gpd.GeoDataFrame":
    """
    Set a `centroid_lat` outside `[-90, 90]` (and the NSW box) — fails the
    coordinate check. Only the coordinate column is changed; the geometry is
    left valid so this defect targets the coordinate check alone.
    """
    out = _copy(gdf)
    out.loc[out.index[0], "centroid_lat"] = value
    return out


def invalid_geometry_crs(gdf: "gpd.GeoDataFrame") -> "gpd.GeoDataFrame":
    """
    Reproject to a non-`EPSG:4326` CRS — fails the geometry/CRS check.

    The frozen table must be stored in `EPSG:4326`; a table in Australian
    Albers (`EPSG:3577`) is a CRS-mismatch defect. Reprojecting also moves the
    centroids out of the lat/lon envelope, so tests targeting the CRS check
    should assert the CRS observation specifically.
    """
    out = _copy(gdf).to_crs("EPSG:3577")
    return out


def invalid_geometry(gdf: "gpd.GeoDataFrame") -> "gpd.GeoDataFrame":
    """
    Replace one geometry with a self-intersecting (invalid) polygon in
    `EPSG:4326` — fails the geometry-validity check while keeping the CRS.
    """
    from shapely.geometry import Polygon

    out = _copy(gdf)
    _, lon, lat = _cell_geometry(0)
    s = 0.02
    # A "bowtie" polygon self-intersects and is therefore invalid.
    bowtie = Polygon([
        (lon - s, lat - s), (lon + s, lat + s),
        (lon + s, lat - s), (lon - s, lat + s), (lon - s, lat - s),
    ])
    geom = out.geometry.copy()
    geom.iloc[0] = bowtie
    out = out.set_geometry(geom)
    return out


def eligible_as_int(gdf: "gpd.GeoDataFrame") -> "gpd.GeoDataFrame":
    """Retype `eligible` to int — fails the eligibility-dtype (boolean) check."""
    out = _copy(gdf)
    out["eligible"] = out["eligible"].astype("int64")
    return out


def eligible_with_nulls(gdf: "gpd.GeoDataFrame") -> "gpd.GeoDataFrame":
    """Null one `eligible` value — fails the eligibility-null check."""
    out = _copy(gdf)
    out["eligible"] = out["eligible"].astype("boolean")
    out.loc[out.index[0], "eligible"] = pd.NA
    return out


def inconsistent_eligible_reason(gdf: "gpd.GeoDataFrame") -> "gpd.GeoDataFrame":
    """
    Make an eligible cell carry an exclusion reason — fails the
    eligible/exclusion_reason consistency check.

    The invariant (`merge.py::validate`): an eligible cell must have an empty
    `exclusion_reason`. Setting a reason on an eligible row is inconsistent.
    """
    out = _copy(gdf)
    eligible_mask = out["eligible"].astype(bool)
    first_eligible = out.index[eligible_mask][0]
    out.loc[first_eligible, "exclusion_reason"] = "Protected area: injected"
    return out


def zero_eligible_cells(gdf: "gpd.GeoDataFrame") -> "gpd.GeoDataFrame":
    """
    Make every cell ineligible (each with a reason, so the consistency check
    still passes) — fails only the eligible-population check.
    """
    out = _copy(gdf)
    out["eligible"] = False
    out["exclusion_reason"] = "Slope exceeds 15\u00b0"
    return out


def hash_drift_baseline(gdf: "gpd.GeoDataFrame") -> "gpd.GeoDataFrame":
    """
    Return a byte-different copy of the good fixture — a hash-drift baseline.

    Used by the hash-match check test: freeze a baseline over one written
    GeoPackage, then point the validator at a GeoPackage written from this
    mutated frame so the observed SHA-256 differs from the recorded one. The
    single changed value keeps every *content* check passing while the hash
    check flips.
    """
    out = _copy(gdf)
    # Nudge one in-range scored value; still inside its Sanity_Range so only
    # the file bytes (and hence the hash) change.
    out.loc[out.index[0], "wind_speed"] = float(out.loc[out.index[0], "wind_speed"]) + 0.1
    return out


# A registry mapping each known-bad mutator to the check it is meant to flip.
# The value is a short tag the check-test tasks can use to look up the target
# Check_Record name once the checks exist (task 4.x). Kept here so the mutator
# set and its intent stay in one place.
KNOWN_BAD_MUTATORS = {
    "dropped_required_column": drop_required_column,
    "dropped_scored_column": drop_scored_column,
    "null_cell_id": null_cell_id,
    "duplicate_cell_id": duplicate_cell_id,
    "out_of_range_wind_speed": out_of_range_wind_speed,
    "out_of_range_centroid_lat": out_of_range_centroid_lat,
    "invalid_geometry_crs": invalid_geometry_crs,
    "invalid_geometry": invalid_geometry,
    "eligible_as_int": eligible_as_int,
    "eligible_with_nulls": eligible_with_nulls,
    "inconsistent_eligible_reason": inconsistent_eligible_reason,
    "zero_eligible_cells": zero_eligible_cells,
    "hash_drift_baseline": hash_drift_baseline,
}
