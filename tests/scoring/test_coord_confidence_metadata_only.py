"""
Regression: the demand coordinate-confidence tier is METADATA-ONLY.

The S1-08 integrated table carries an informational ``demand_coord_confidence``
column, and the scoring stage carries it through verbatim
(``scoring.config.CARRIED_COLUMNS``). This test pins the invariant that its
PRESENCE never changes the model: the composite ``suitability_score``, the
per-criterion contributions and the ``rank`` are byte-identical whether or not
the column is on the input frame.

It also pins the wiring itself — the tier IS in ``CARRIED_COLUMNS`` and IS NOT
a scored feature — so a future edit that accidentally promoted it to a
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


COORD_COL = scfg.DEMAND_COORD_CONFIDENCE_COLUMN


def _features_with_tier() -> pd.DataFrame:
    """The shared 4-cell fixture plus a demand_coord_confidence column."""
    frame = simple_features().copy()
    frame[COORD_COL] = ["low", "high", "n/a", "low"]
    return frame


def test_tier_is_carried_but_not_a_scored_feature():
    # Carried as informational context, NOT as a grid coordinate column (which
    # the decision service unpacks as exactly two), and never a scored feature.
    assert COORD_COL in scfg.CARRIED_CONTEXT_COLUMNS
    assert COORD_COL not in scfg.CARRIED_COLUMNS
    assert len(scfg.CARRIED_COLUMNS) == 2
    assert COORD_COL not in icfg.SCORED_FEATURE_COLUMNS


def test_score_and_rank_identical_with_and_without_tier():
    weights = simple_config()
    without = score_and_rank(simple_features(), weights)
    with_tier = score_and_rank(_features_with_tier(), weights)

    # Compare the decision-relevant columns cell-by-cell (same input order).
    for col in (scfg.SCORE_COLUMN, scfg.RANK_COLUMN, "contrib_wind_speed",
                "contrib_dist_transmission_km"):
        a = without[col].to_numpy()
        b = with_tier[col].to_numpy()
        assert np.array_equal(a, b, equal_nan=True), f"{col} changed when the tier was present"


def test_tier_value_does_not_shift_the_score():
    """Flipping the tier value for every cell leaves the score untouched."""
    weights = simple_config()
    frame_low = _features_with_tier()
    frame_high = frame_low.copy()
    frame_high[COORD_COL] = "high"  # overwrite all tiers
    s_low = score_and_rank(frame_low, weights)[scfg.SCORE_COLUMN].to_numpy()
    s_high = score_and_rank(frame_high, weights)[scfg.SCORE_COLUMN].to_numpy()
    assert np.array_equal(s_low, s_high, equal_nan=True)


def test_scored_table_carries_tier_verbatim():
    """The assembled Scored_Table surfaces the tier column with its values."""
    import geopandas as gpd
    from shapely.geometry import Point

    weights_cfg = simple_config()
    features = _features_with_tier()
    geometry = [Point(x, 0.0) for x in range(len(features))]
    gdf = gpd.GeoDataFrame(features, geometry=geometry, crs=scfg.STORAGE_CRS)
    scored = score_and_rank(features, weights_cfg)
    table = build_scored_table(gdf, scored, weights_cfg)
    assert COORD_COL in table.columns
    # Values are carried through unchanged, in input order.
    assert table[COORD_COL].tolist() == features[COORD_COL].tolist()
