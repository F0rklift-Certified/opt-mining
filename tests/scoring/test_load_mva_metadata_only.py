"""
Regression: the DISPLAY-ONLY per-cell network-load read-out is METADATA-ONLY.

The S1-08 integrated table carries an informational ``load_within_radius_mva``
column (the raw sum of nearby zone-substation max demand, MVA), and the scoring
stage carries it through verbatim (``scoring.config.CARRIED_CONTEXT_COLUMNS``).
This test pins the invariant that its PRESENCE — and its VALUE — never change
the model: the composite ``suitability_score``, the per-criterion contributions
and the ``rank`` are byte-identical whether or not the column is on the input
frame, and no value of the column shifts the score.

It also pins the wiring itself — the figure IS in ``CARRIED_CONTEXT_COLUMNS`` and
IS NOT a scored feature — so a future edit that accidentally promoted it to a
criterion (and thus into the score) would fail here.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from pipeline.integration import config as icfg
from pipeline.scoring import config as scfg
from pipeline.scoring.score import score_and_rank
from pipeline.scoring.write import build_scored_table

from tests.scoring.test_scoring import simple_config, simple_features


MVA_COL = scfg.DEMAND_LOAD_MVA_COLUMN


def _features_with_mva() -> pd.DataFrame:
    """The shared 4-cell fixture plus a load_within_radius_mva column."""
    frame = simple_features().copy()
    frame[MVA_COL] = [128.4, 0.0, 6826.4, 14.58]
    return frame


def test_mva_is_carried_context_but_not_a_scored_feature():
    assert MVA_COL in scfg.CARRIED_CONTEXT_COLUMNS
    assert MVA_COL not in scfg.CARRIED_COLUMNS
    assert MVA_COL not in icfg.SCORED_FEATURE_COLUMNS


def test_score_and_rank_identical_with_and_without_mva():
    weights = simple_config()
    without = score_and_rank(simple_features(), weights)
    with_mva = score_and_rank(_features_with_mva(), weights)
    for col in (scfg.SCORE_COLUMN, scfg.RANK_COLUMN, "contrib_wind_speed",
                "contrib_dist_transmission_km"):
        a = without[col].to_numpy()
        b = with_mva[col].to_numpy()
        assert np.array_equal(a, b, equal_nan=True), f"{col} changed when the MVA column was present"


def test_mva_value_does_not_shift_the_score():
    """Changing the MVA figure for every cell leaves the score untouched."""
    weights = simple_config()
    frame_a = _features_with_mva()
    frame_b = frame_a.copy()
    frame_b[MVA_COL] = frame_b[MVA_COL] * 1000.0 + 1.0  # arbitrary rescale
    s_a = score_and_rank(frame_a, weights)[scfg.SCORE_COLUMN].to_numpy()
    s_b = score_and_rank(frame_b, weights)[scfg.SCORE_COLUMN].to_numpy()
    assert np.array_equal(s_a, s_b, equal_nan=True)


def test_scored_table_carries_mva_verbatim():
    """The assembled Scored_Table surfaces the MVA column with its values."""
    import geopandas as gpd
    from shapely.geometry import Point

    weights_cfg = simple_config()
    features = _features_with_mva()
    geometry = [Point(x, 0.0) for x in range(len(features))]
    gdf = gpd.GeoDataFrame(features, geometry=geometry, crs=scfg.STORAGE_CRS)
    scored = score_and_rank(features, weights_cfg)
    table = build_scored_table(gdf, scored, weights_cfg)
    assert MVA_COL in table.columns
    assert table[MVA_COL].tolist() == features[MVA_COL].tolist()
