"""
Scored_Table assembly and atomic writers (S1-10, Requirement 6).

The output is a fully regenerable DERIVED product: delete it, rerun the
stage against the same integrated table and the same weights file, and the
identical table comes back. Nothing here is hand-edited or hand-maintained.

Writes go through a temporary sibling file plus `os.replace`, mirroring
`integration.merge.write_gpkg`. A failed write therefore leaves any
previously written table untouched rather than truncating it — a half-written
scored table that still looked loadable would be worse than no table at all.
"""

from __future__ import annotations

import os
from pathlib import Path

import geopandas as gpd
import pandas as pd

from . import config
from .weights import WeightsConfig


def output_columns(weights: WeightsConfig) -> list[str]:
    """
    The Scored_Table column order, excluding geometry.

    The contribution columns are derived from the weights config, so the
    schema follows the user's criteria: configure a different set of criteria
    and the table gains exactly one `contrib_*` column per configured
    criterion, with no code change.
    """
    return [
        config.CELL_ID_COLUMN,
        *config.CARRIED_COLUMNS,
        config.SCORE_COLUMN,
        config.RANK_COLUMN,
        config.OUTPUT_CONFIDENCE_COLUMN,
        *weights.contribution_columns,
    ]


def build_scored_table(
    features: gpd.GeoDataFrame,
    scored: pd.DataFrame,
    weights: WeightsConfig,
) -> gpd.GeoDataFrame:
    """
    Assemble the output table: one row per integrated-table `cell_id`, in the
    input's own row order, with geometry carried through in the storage CRS.

    `cell_id` is copied straight from the integrated table — never
    renumbered, reformatted or reordered — so the result joins back to the
    analysis grid on `cell_id` without any reconciliation step.
    """
    table = gpd.GeoDataFrame(index=features.index)
    table[config.CELL_ID_COLUMN] = features[config.CELL_ID_COLUMN]

    for column in config.CARRIED_COLUMNS:
        if column in features.columns:
            table[column] = features[column]

    table[config.SCORE_COLUMN] = scored[config.SCORE_COLUMN]
    table[config.RANK_COLUMN] = scored[config.RANK_COLUMN]
    # Presentational rename only: the values are S1-09's composite flag.
    table[config.OUTPUT_CONFIDENCE_COLUMN] = scored[config.CONFIDENCE_COLUMN]

    for column in weights.contribution_columns:
        table[column] = scored[column]

    ordered = [c for c in output_columns(weights) if c in table.columns]
    table = table[ordered]

    geometry = features.geometry
    table = gpd.GeoDataFrame(table, geometry=geometry, crs=features.crs)
    return table


def write_gpkg(table: gpd.GeoDataFrame, path: Path) -> None:
    """
    Atomic GeoPackage write (the tmp file keeps the .gpkg suffix so GDAL
    still infers the driver). Geometry is written in whatever CRS the frame
    declares; `run()` asserts that is the storage CRS before calling.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + "_tmp.gpkg")
    try:
        table.to_file(tmp, driver="GPKG", layer=config.OUTPUT_LAYER)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def write_csv(table: gpd.GeoDataFrame, path: Path) -> None:
    """
    Atomic CSV write without geometry — the deterministic artefact.

    Same conventions as `integration.merge.write_csv`: no index, empty
    strings for nulls, "\\n" line endings, so the file is byte-identical
    across reruns with unchanged inputs. (A GeoPackage's hash drifts with its
    internal `last_change` timestamp, so the CSV is the artefact to compare.)
    """
    path = Path(path)
    frame = pd.DataFrame(table.drop(columns=[table.geometry.name]))
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + "_tmp.csv")
    try:
        frame.to_csv(tmp, index=False, na_rep="", lineterminator="\n", encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def write_scored_table(
    table: gpd.GeoDataFrame,
    gpkg_path: Path,
    csv_path: Path,
) -> None:
    """
    Write both products atomically.

    Raises on any write failure, leaving pre-existing outputs unmodified.
    """
    write_gpkg(table, gpkg_path)
    write_csv(table, csv_path)
