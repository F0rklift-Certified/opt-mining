"""
Scored_Table loader for the S1-11 shortlist stage (Requirement 1).

This is the ONLY file-reading path for score data in the shortlist stage. It
reads the S1-10 Scored_Table as the SOLE per-cell score input and hands a
fully in-memory frame to the pure selection core (`select.py`), which is why
`select.select_shortlist` can be replaced without touching any I/O code.

Every check here halts BEFORE the stage writes anything, and every error
names the offending path or column. Nothing is re-derived, re-scored or
re-ranked: `cell_id`, `suitability_score` and `rank` are reused exactly as
S1-10 wrote them (1.2, 1.3). This mirrors `pipeline/scoring/load.py`, which
plays the identical role for the scoring stage.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd

from . import config

# The columns the shortlist stage reads from the Scored_Table. `cell_id` keys
# every shortlisted row back to the grid; `suitability_score` and `rank` drive
# eligibility and ordering (used exactly as S1-10 produced them, 1.3); and
# `confidence` feeds the shortlist's confidence distribution. Any absent column
# is a fail-fast condition (1.5).
REQUIRED_SCORE_COLUMNS = ("cell_id", "suitability_score", "rank", "confidence")


def load_scored_table(
    path: Path | str | None = None,
    *,
    layer: str | None = None,
) -> gpd.GeoDataFrame:
    """
    Read the S1-10 Scored_Table as the sole per-cell score input (1.1).

    Halts BEFORE any output on:
      - a missing or unreadable file, naming the path                   (1.4)
      - any of ``REQUIRED_SCORE_COLUMNS`` absent, naming the column     (1.5)

    ``cell_id`` values are reused byte-for-byte — never re-derived,
    renumbered, reformatted or reordered (1.2). ``suitability_score`` and
    ``rank`` are read and returned verbatim; this loader never re-scores or
    re-ranks (1.3). The frame is returned whole (row order and geometry
    preserved) so the pure selection core operates on the S1-10 table exactly
    as produced.
    """
    path = Path(path) if path is not None else config.SCORED_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"Scored_Table not found: {path}. Run "
            f"`python -m pipeline --only scoring` to generate it before the "
            f"shortlist stage."
        )

    layer = layer if layer is not None else config.SCORED_LAYER
    try:
        table = gpd.read_file(path, layer=layer)
    except Exception as exc:  # noqa: BLE001 — any read failure is fatal and named
        raise RuntimeError(f"Could not read Scored_Table {path}: {exc}") from exc

    missing = [c for c in REQUIRED_SCORE_COLUMNS if c not in table.columns]
    if missing:
        raise ValueError(
            f"{path} lacks column(s) {missing} required by the shortlist stage. "
            f"The shortlist reads {list(REQUIRED_SCORE_COLUMNS)} from the S1-10 "
            f"Scored_Table and re-derives none of them; regenerate the scored "
            f"table if a column is missing."
        )

    return table
