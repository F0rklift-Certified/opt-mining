"""
Explanation input loader (S2-06a) — the ONLY file-reading path.

Reads the two inputs the engine needs and assembles, for every ELIGIBLE cell,
the `CellExplanationInput` the pure engine consumes:

  1. the S2-05 Scored_Table — the authoritative per-cell `contrib_{feature}`
     values, score and rank. The engine RANKS factors by these; it never
     recomputes a score.
  2. the S1-08 integrated feature table — read ONLY to recompute the
     eligible-population NORMALISED values the qualitative bands need, because
     the Scored_Table does not persist the `norm_{feature}` intermediates.

NO SECOND NORMALISER. The normalised values are produced by calling the
scoring stage's OWN pure core (`pipeline.scoring.score.score_frame`) with the
SAME weights the scores were produced from. That single call also recomputes
the contributions, which lets this module RECONCILE its recomputed norms
against the persisted contributions within `config.RECONCILE_TOLERANCE`: if the
recomputed contribution for a cell/criterion does not match the value the
Scored_Table carries, the recomputed norms are NOT the ones that produced the
score, and the run halts before any explanation is written. That guard is what
makes it safe to derive the bands from recomputed values rather than from
persisted norms.

Every check here halts BEFORE the stage writes anything, and every error names
the offending path or column (fail before write).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from ..scoring import config as scfg
from ..scoring.load import load_integrated
from ..scoring.normalise import Bounds, compute_bounds
from ..scoring.score import eligible_mask, score_frame
from ..scoring.weights import WeightsConfig, load_weights
from . import config
from .engine import CellExplanationInput, CriterionView


@dataclass(frozen=True)
class ExplanationInputs:
    """The assembled, validated inputs the run() orchestrator hands the engine."""

    cells: tuple[CellExplanationInput, ...]  # one per ELIGIBLE cell, in Scored_Table order
    weights: WeightsConfig
    bounds: dict[str, Bounds]
    n_scored_cells: int  # rows in the Scored_Table with a non-null score
    n_eligible_cells: int  # rows the integrated table marks eligible
    scored_table_path: Path
    integrated_path: Path


def _read_scored_table(path: Path, weights: WeightsConfig) -> gpd.GeoDataFrame:
    """
    Read the S2-05 Scored_Table, halting on a missing file or any missing
    expected column (cell_id, score, rank, confidence, one contrib per
    criterion). Names the offending path/column.
    """
    if not path.exists():
        raise FileNotFoundError(
            f"Scored_Table not found: {path}. Run `python -m pipeline --only scoring` "
            f"to generate it before the explanation stage."
        )
    try:
        table = gpd.read_file(path, layer=config.SCORED_TABLE_LAYER)
    except Exception as exc:  # noqa: BLE001 — any read failure is fatal and named
        raise RuntimeError(f"Could not read Scored_Table {path}: {exc}") from exc

    expected = [
        config.CELL_ID_COLUMN, config.SCORE_COLUMN, config.RANK_COLUMN,
        config.OUTPUT_CONFIDENCE_COLUMN,
    ]
    expected += [c.contribution_column for c in weights.criteria]
    missing = [c for c in expected if c not in table.columns]
    if missing:
        raise ValueError(
            f"{path} lacks column(s) {missing} required by the explanation stage. "
            f"Contribution columns follow the scoring weights; regenerate the "
            f"Scored_Table if the weights changed."
        )
    if int(table[config.CELL_ID_COLUMN].duplicated().sum()):
        raise ValueError(
            f"{path} contains duplicate '{config.CELL_ID_COLUMN}' values; the "
            f"Scored_Table must be one row per cell."
        )
    return table


def _reconcile(
    scored_table: gpd.GeoDataFrame,
    recomputed: pd.DataFrame,
    weights: WeightsConfig,
) -> None:
    """
    Assert the recomputed contributions reproduce the persisted ones.

    Both frames are keyed by `cell_id`. For every scored cell and every
    criterion the recomputed `contrib_{feature}` (from `score_frame` over the
    integrated table with the same weights) must equal the Scored_Table's value
    within `config.RECONCILE_TOLERANCE`. A mismatch means the integrated table,
    the weights, or the persisted scores are out of step, so the recomputed
    norms cannot be trusted to derive the bands — halt before writing.
    """
    persisted = scored_table.set_index(config.CELL_ID_COLUMN)
    recomputed = recomputed.set_index(config.CELL_ID_COLUMN)

    common = persisted.index.intersection(recomputed.index)
    # Only scored cells carry a contribution to reconcile.
    scored_ids = persisted.index[persisted[config.SCORE_COLUMN].notna()]
    check_ids = common.intersection(scored_ids)

    worst_feature = None
    worst_delta = 0.0
    for criterion in weights.criteria:
        col = criterion.contribution_column
        a = pd.to_numeric(persisted.loc[check_ids, col], errors="coerce").to_numpy(dtype=float)
        b = pd.to_numeric(recomputed.loc[check_ids, col], errors="coerce").to_numpy(dtype=float)
        # Treat two nulls as agreeing; a null vs a number is a real mismatch.
        both_nan = np.isnan(a) & np.isnan(b)
        delta = np.where(both_nan, 0.0, np.abs(a - b))
        delta = np.nan_to_num(delta, nan=np.inf)  # null-vs-number -> inf mismatch
        if delta.size and float(delta.max()) > worst_delta:
            worst_delta = float(delta.max())
            worst_feature = col

    if worst_feature is not None and worst_delta > config.RECONCILE_TOLERANCE:
        raise RuntimeError(
            f"explanation reconciliation failed: recomputed contribution "
            f"'{worst_feature}' differs from the persisted Scored_Table value by "
            f"{worst_delta:g} (> tolerance {config.RECONCILE_TOLERANCE:g}). The "
            f"integrated table and weights must be the ones the Scored_Table was "
            f"produced from; regenerate the scoring stage, or pass matching "
            f"--scoring-weights."
        )


def load_explanation_inputs(
    scored_table_path: Path | str | None = None,
    integrated_path: Path | str | None = None,
    weights_path: Path | str | None = None,
) -> ExplanationInputs:
    """
    Load and validate everything the eligible-cell explanation engine needs.

    Steps, all fail-before-write:
      1. load the SAME weights the scores were produced from;
      2. read the Scored_Table (halt on missing file/columns);
      3. read the integrated table via the scoring stage's own loader (halt on
         missing columns / wrong CRS / duplicate cell_id);
      4. recompute eligible-population bounds + norms + contributions with the
         scoring stage's pure core (no second normaliser);
      5. reconcile recomputed contributions against the persisted ones;
      6. assemble one `CellExplanationInput` per ELIGIBLE cell, carrying the
         PERSISTED contribution and the RECOMPUTED norm/bounds per criterion.
    """
    weights = load_weights(weights_path or config.DEFAULT_WEIGHTS_PATH)

    scored_table_path = Path(scored_table_path or config.SCORED_TABLE_PATH)
    scored_table = _read_scored_table(scored_table_path, weights)

    integrated_path = Path(integrated_path or config.INTEGRATED_PATH)
    features = load_integrated(integrated_path, weights.criteria)

    # Bounds and the pure scoring core over the eligible population — the same
    # code the scoring stage runs, so the norms are the ones behind the scores.
    mask = eligible_mask(features)
    bounds = compute_bounds(features.loc[mask], weights.criteria)
    recomputed = score_frame(features, weights, bounds=bounds)
    recomputed[config.CELL_ID_COLUMN] = features[config.CELL_ID_COLUMN].to_numpy()

    _reconcile(scored_table, recomputed, weights)

    # Index the persisted contributions by cell_id for the engine input.
    persisted = scored_table.set_index(config.CELL_ID_COLUMN)
    rec = recomputed.set_index(config.CELL_ID_COLUMN)

    eligible_ids = features.loc[mask, config.CELL_ID_COLUMN].tolist()
    cells: list[CellExplanationInput] = []
    for cell_id in eligible_ids:
        views: list[CriterionView] = []
        for criterion in weights.criteria:
            contrib = persisted.at[cell_id, criterion.contribution_column] \
                if cell_id in persisted.index else None
            norm = rec.at[cell_id, f"norm_{criterion.feature}"]
            views.append(
                CriterionView(
                    feature=criterion.feature,
                    contribution=_as_opt_float(contrib),
                    norm=_as_opt_float(norm),
                    bounds=bounds[criterion.feature],
                )
            )
        cells.append(
            CellExplanationInput(
                cell_id=str(cell_id),
                criteria=tuple(views),
                order=tuple(c.feature for c in weights.criteria),
            )
        )

    return ExplanationInputs(
        cells=tuple(cells),
        weights=weights,
        bounds=bounds,
        n_scored_cells=int(scored_table[config.SCORE_COLUMN].notna().sum()),
        n_eligible_cells=int(mask.sum()),
        scored_table_path=scored_table_path,
        integrated_path=integrated_path,
    )


def _as_opt_float(value: object) -> float | None:
    """Coerce a cell value to float or None (nulls/NaN become None)."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return f
