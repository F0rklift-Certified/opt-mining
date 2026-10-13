"""
Explanation input loader (S2-06a + S2-06b) — the ONLY file-reading path.

Reads the inputs the engine needs and assembles, for every ELIGIBLE cell, the
`CellExplanationInput`, and for every EXCLUDED cell, the `ExcludedCellInput`,
that the pure engine consumes:

  1. the S2-05 Scored_Table — the authoritative per-cell `contrib_{feature}`
     values, score and rank. The engine RANKS factors by these; it never
     recomputes a score.
  2. the S1-08 integrated feature table — read to recompute the
     eligible-population NORMALISED values the qualitative bands need (the
     Scored_Table does not persist the `norm_{feature}` intermediates), and
     (S2-06b) to read the columns the scoring loader drops: the F16 exclusion
     reason forms (`triggered_rules` codes + `exclusion_reason` texts, from
     which the {code, text} pairs are reconstructed) and the S1-09 confidence
     level + notes that feed the data-quality caveat.

RECONSTRUCTING THE F16 PAIRS (S2-06b, Option B). The integrated table carries
the two DELIMITED reason forms, not the paired `exclusion_reasons` JSON (that
lives only on the upstream exclusions Eligibility_Table). F16 guarantees the
codes and texts are the ordered split of one rule evaluation, so this module
zips them back into the {code, text} pairs the explanation contract exposes,
using the codes as the authoritative count and halting on any count mismatch.
This keeps S2-06b inside the explanation stage and does not mutate the frozen
S2-02 baseline dataset.

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
from .caveats import CriterionParticipation
from .engine import (
    CellConfidence,
    CellExplanationInput,
    CriterionView,
    ExcludedCellInput,
)


@dataclass(frozen=True)
class ExplanationInputs:
    """The assembled, validated inputs the run() orchestrator hands the engine."""

    cells: tuple[CellExplanationInput, ...]  # one per ELIGIBLE cell, in Scored_Table order
    excluded_cells: tuple[ExcludedCellInput, ...]  # one per EXCLUDED cell (S2-06b)
    weights: WeightsConfig
    bounds: dict[str, Bounds]
    n_scored_cells: int  # rows in the Scored_Table with a non-null score
    n_eligible_cells: int  # rows the integrated table marks eligible
    n_excluded_cells: int  # rows the integrated table marks NOT eligible (S2-06b)
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


def _read_extra_columns(path: Path) -> pd.DataFrame:
    """
    Read the S2-06b input columns the scoring loader drops.

    The scoring stage's `load_integrated` returns a restricted column set
    (cell_id, eligible, data_confidence, criterion features) and does NOT carry
    the F16 reason forms or the `confidence_notes` text. This reads the
    integrated table again for exactly those columns, keyed by cell_id, halting
    (fail before write) with a named column if any is absent.

    Returns a DataFrame indexed by cell_id with columns
    [eligible, triggered_rules, exclusion_reason, data_confidence,
    confidence_notes].
    """
    try:
        table = gpd.read_file(path, layer=config.INTEGRATED_LAYER)
    except Exception as exc:  # noqa: BLE001 — any read failure is fatal and named
        raise RuntimeError(f"Could not read integrated feature table {path}: {exc}") from exc

    needed = [
        config.CELL_ID_COLUMN,
        config.ELIGIBLE_COLUMN,
        config.TRIGGERED_RULES_COLUMN,
        config.EXCLUSION_REASON_COLUMN,
        config.CONFIDENCE_LEVEL_COLUMN,
        config.CONFIDENCE_NOTES_COLUMN,
    ]
    missing = [c for c in needed if c not in table.columns]
    if missing:
        raise ValueError(
            f"{path} lacks column(s) {missing} required by the S2-06b explanation "
            f"stage. '{config.TRIGGERED_RULES_COLUMN}' (F16 machine codes) and "
            f"'{config.EXCLUSION_REASON_COLUMN}' (F16 human texts) are the reason "
            f"forms the integrated table carries (Decision-Engine Spec §6.5); the "
            f"confidence columns are S1-09's composite quality flag. All are "
            f"carried through the integrated table, never fabricated here."
        )
    frame = pd.DataFrame({c: table[c].to_numpy() for c in needed})
    return frame.set_index(config.CELL_ID_COLUMN)


def _parse_reason_pairs(codes_raw: object, texts_raw: object, cell_id: str) -> tuple[dict, ...]:
    """
    Reconstruct one excluded cell's {code, text} pairs from the two F16 forms.

    The integrated table carries the machine codes (`triggered_rules`) and the
    human texts (`exclusion_reason`), each the same rule evaluation joined with
    `config.REASON_DELIMITER` in the SAME rule-config order (F16, Decision-Engine
    Spec §6.5). This zips them back into the paired form the explanation
    contract exposes, using the CODES as the authoritative count (a code never
    contains the delimiter). Any violation of the pairing contract for an
    EXCLUDED cell halts before write with a named cell:
      - a null/empty code string (an excluded cell must carry ≥ 1 reason);
      - a code/text count mismatch (the two forms are out of step);
      - an empty code or text token.
    """
    codes = _split_reasons(codes_raw)
    texts = _split_reasons(texts_raw)

    if not codes:
        raise ValueError(
            f"excluded cell '{cell_id}' has an empty/null "
            f"'{config.TRIGGERED_RULES_COLUMN}'; the F16 pairing contract requires "
            f"at least one reason code for every excluded cell (Decision-Engine "
            f"Spec §6.5)."
        )
    if len(codes) != len(texts):
        raise ValueError(
            f"excluded cell '{cell_id}' has {len(codes)} reason code(s) "
            f"({codes!r}) but {len(texts)} reason text(s) ({texts!r}); the two F16 "
            f"forms must be the ordered split of one evaluation. The integrated "
            f"table's '{config.TRIGGERED_RULES_COLUMN}' and "
            f"'{config.EXCLUSION_REASON_COLUMN}' are out of step."
        )
    pairs: list[dict] = []
    for i, (code, text) in enumerate(zip(codes, texts)):
        if not code:
            raise ValueError(
                f"excluded cell '{cell_id}' reason[{i}] has an empty code"
            )
        if not text:
            raise ValueError(
                f"excluded cell '{cell_id}' reason[{i}] ('{code}') has an empty text"
            )
        pairs.append({config.REASON_CODE_KEY: code, config.REASON_TEXT_KEY: text})
    return tuple(pairs)


def _split_reasons(raw: object) -> list[str]:
    """Split a ", "-joined F16 form into stripped tokens; [] for null/empty."""
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return []
    text = str(raw).strip()
    if not text:
        return []
    return [tok.strip() for tok in text.split(config.REASON_DELIMITER)]


def _participation_for(
    cell_id: str, features: pd.DataFrame, weights: WeightsConfig
) -> tuple[CriterionParticipation, ...]:
    """
    Which criteria the cell had a value for, in configured (weights) order.

    A criterion participated when the integrated table carries a non-null value
    for it. This drives the proxy caveat for BOTH paths — a proxy criterion the
    cell had no value for is not "shown", so it needs no caveat.
    """
    row = features.loc[cell_id]
    out: list[CriterionParticipation] = []
    for criterion in weights.criteria:
        value = row.get(criterion.feature)
        participated = value is not None and not (
            isinstance(value, float) and value != value  # NaN
        )
        out.append(CriterionParticipation(feature=criterion.feature, participated=bool(participated)))
    return tuple(out)


def _confidence_for(cell_id: str, extra: pd.DataFrame) -> CellConfidence:
    """One cell's confidence facts (level + notes) from the extra-columns frame."""
    if cell_id not in extra.index:
        return CellConfidence(None, None)
    row = extra.loc[cell_id]
    level = row.get(config.CONFIDENCE_LEVEL_COLUMN)
    notes = row.get(config.CONFIDENCE_NOTES_COLUMN)
    return CellConfidence(
        level=None if _is_null(level) else str(level),
        notes=None if _is_null(notes) else str(notes),
    )


def _is_null(value: object) -> bool:
    return value is None or (isinstance(value, float) and value != value)


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

    # S2-06b inputs the scoring loader drops: the F16 exclusion_reasons and the
    # confidence_notes text. Read once here, indexed by cell_id.
    extra = _read_extra_columns(integrated_path)

    # Bounds and the pure scoring core over the eligible population — the same
    # code the scoring stage runs, so the norms are the ones behind the scores.
    mask = eligible_mask(features)
    bounds = compute_bounds(features.loc[mask], weights.criteria)
    recomputed = score_frame(features, weights, bounds=bounds)
    recomputed[config.CELL_ID_COLUMN] = features[config.CELL_ID_COLUMN].to_numpy()

    _reconcile(scored_table, recomputed, weights)

    # Index the persisted contributions and the feature values by cell_id.
    persisted = scored_table.set_index(config.CELL_ID_COLUMN)
    rec = recomputed.set_index(config.CELL_ID_COLUMN)
    feat_by_id = features.set_index(config.CELL_ID_COLUMN)

    # --- Eligible cells: factors + caveats ---------------------------------
    eligible_ids = features.loc[mask, config.CELL_ID_COLUMN].tolist()
    cells: list[CellExplanationInput] = []
    for cell_id in eligible_ids:
        participation = _participation_for(cell_id, feat_by_id, weights)
        participated_by_feature = {p.feature: p.participated for p in participation}
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
                    participated=participated_by_feature[criterion.feature],
                )
            )
        cells.append(
            CellExplanationInput(
                cell_id=str(cell_id),
                criteria=tuple(views),
                order=tuple(c.feature for c in weights.criteria),
                confidence=_confidence_for(cell_id, extra),
            )
        )

    # --- Excluded cells: F16 reasons + caveats -----------------------------
    excluded_ids = features.loc[~mask, config.CELL_ID_COLUMN].tolist()
    excluded_cells: list[ExcludedCellInput] = []
    for cell_id in excluded_ids:
        codes_raw = extra.at[cell_id, config.TRIGGERED_RULES_COLUMN] \
            if cell_id in extra.index else None
        texts_raw = extra.at[cell_id, config.EXCLUSION_REASON_COLUMN] \
            if cell_id in extra.index else None
        reasons = _parse_reason_pairs(codes_raw, texts_raw, str(cell_id))
        excluded_cells.append(
            ExcludedCellInput(
                cell_id=str(cell_id),
                exclusion_reasons=reasons,
                participation=_participation_for(cell_id, feat_by_id, weights),
                confidence=_confidence_for(cell_id, extra),
            )
        )

    return ExplanationInputs(
        cells=tuple(cells),
        excluded_cells=tuple(excluded_cells),
        weights=weights,
        bounds=bounds,
        n_scored_cells=int(scored_table[config.SCORE_COLUMN].notna().sum()),
        n_eligible_cells=int(mask.sum()),
        n_excluded_cells=int((~mask).sum()),
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
