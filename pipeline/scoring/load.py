"""
Integrated feature table loader (S1-10, Requirement 1 and 10.4).

This is the ONLY file-reading path for feature data in the scoring stage. It
reads the S1-08 integrated table as the sole per-cell feature input and hands
a fully in-memory frame to the pure Scoring_Function, which is why
`score.score_frame` can be replaced without touching any I/O code.

Every check here halts BEFORE the stage writes anything, and every error
names the offending path or column. Nothing is re-derived, back-filled or
reprojected: `cell_id` is reused exactly as the integrated table wrote it.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import geopandas as gpd

from . import config
from .weights import Criterion


def _crs_string(crs) -> str:
    """Human-readable CRS for error messages ('undeclared' when absent)."""
    if crs is None:
        return "undeclared"
    try:
        code = crs.to_string()
    except Exception:  # noqa: BLE001 — a malformed CRS must still print
        return str(crs)
    return code or str(crs)


def required_columns(criteria: Sequence[Criterion]) -> tuple[str, ...]:
    """
    Every column the scoring stage reads, in a stable order.

    The criterion columns come from the weights config, so pointing the stage
    at a different weights file changes what the loader requires — the
    contract follows the user's configuration rather than a fixed list.
    """
    columns = [config.CELL_ID_COLUMN, config.ELIGIBLE_COLUMN, config.CONFIDENCE_COLUMN]
    columns.extend(c.feature for c in criteria)
    return tuple(dict.fromkeys(columns))


def load_integrated(
    path: Path | str | None = None,
    criteria: Sequence[Criterion] = (),
    *,
    layer: str | None = None,
) -> gpd.GeoDataFrame:
    """
    Read the S1-08 integrated feature table as the sole feature input.

    Halts before any output on:
      - a missing or unreadable file, naming the path                    (1.3)
      - no `cell_id` column                                             (1.4)
      - any configured criterion column or `eligible` absent            (1.5)
      - the S1-09 composite confidence column absent                   (10.4)
      - a duplicate `cell_id` (the output must be one row per cell)      (6.3)
      - a CRS that is not the declared storage CRS (never converts silently)

    `cell_id` values are reused byte-for-byte — never renumbered, reformatted
    or reordered (1.2).
    """
    path = Path(path) if path is not None else config.INTEGRATED_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"Integrated feature table not found: {path}. Run "
            f"`python -m pipeline --only integration` to generate it before scoring."
        )

    layer = layer if layer is not None else config.INTEGRATED_LAYER
    try:
        table = gpd.read_file(path, layer=layer)
    except Exception as exc:  # noqa: BLE001 — any read failure is fatal and named
        raise RuntimeError(f"Could not read integrated feature table {path}: {exc}") from exc

    if config.CELL_ID_COLUMN not in table.columns:
        raise ValueError(
            f"{path} has no '{config.CELL_ID_COLUMN}' column; the scoring stage "
            f"keys every output row to the grid cell id and cannot proceed without it"
        )

    missing = [c for c in required_columns(criteria) if c not in table.columns]
    if missing:
        # Name the confidence column's role explicitly: a missing composite
        # confidence must fail rather than be invented (Requirement 10.4).
        detail = ""
        if config.CONFIDENCE_COLUMN in missing:
            detail = (
                f" ('{config.CONFIDENCE_COLUMN}' is the S1-09 composite confidence "
                f"flag; it is carried through, never fabricated)"
            )
        raise ValueError(
            f"{path} lacks column(s) {missing} required by the scoring stage{detail}. "
            f"Criterion columns come from the weights config; check that every "
            f"'feature' name matches a column of the integrated table."
        )

    duplicated = int(table[config.CELL_ID_COLUMN].duplicated().sum())
    if duplicated:
        raise ValueError(
            f"{path} contains {duplicated:,} duplicate '{config.CELL_ID_COLUMN}' "
            f"value(s); the scored table must be one row per cell and joinable "
            f"to the analysis grid"
        )

    crs = _crs_string(table.crs)
    if table.crs is None or crs != config.STORAGE_CRS:
        raise ValueError(
            f"{path} is in CRS {crs}, expected {config.STORAGE_CRS}. The scoring "
            f"stage never reprojects — regenerate the integrated table instead."
        )

    return table
