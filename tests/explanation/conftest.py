"""
Shared fixtures for the S2-06a explanation tests.

Builds a tiny, hand-computable Scored_Table on disk by running the REAL scoring
core (score_and_rank + build_scored_table) over a synthetic integrated table,
so the explanation stage is exercised against a genuine S2-05 output rather
than a hand-faked one. This is what lets the reconciliation guard be tested for
real.

Feature: s2-06a-explanation-engine-eligible-cells
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Point

from pipeline.scoring import config as scfg
from pipeline.scoring.score import score_and_rank
from pipeline.scoring.weights import Criterion, WeightsConfig
from pipeline.scoring.write import write_scored_table


def _weights() -> WeightsConfig:
    """Four criteria spanning both directions and a boolean, weights not summing to 1."""
    return WeightsConfig(
        criteria=(
            Criterion("wind_speed", 2.0, scfg.HIGHER_IS_BETTER, "resource"),
            Criterion("dist_transmission_km", 1.0, scfg.LOWER_IS_BETTER, "cost"),
            Criterion("slope_deg", 1.0, scfg.LOWER_IS_BETTER, "terrain"),
            Criterion("inside_rez", 1.0, scfg.HIGHER_IS_BETTER, "policy"),
        ),
        confidence_discount=False,
        confidence_factors={"high": 1.0, "medium": 0.9, "low": 0.8},
        config_id="testtemplatesfixture",
        version="test",
        path=None,
    )


def _integrated() -> gpd.GeoDataFrame:
    """
    Five cells; c5 excluded (extreme values, must not stretch the bounds).

    Eligible bounds (c1..c4): wind [0,8], dist_transmission [2,10], slope [5,25].
    """
    df = gpd.GeoDataFrame(
        {
            "cell_id": ["c1", "c2", "c3", "c4", "c5"],
            "wind_speed": [8.0, 8.0, 4.0, 0.0, 999.0],
            "dist_transmission_km": [2.0, 2.0, 6.0, 10.0, -999.0],
            "slope_deg": [5.0, 5.0, 15.0, 25.0, 999.0],
            "inside_rez": [True, False, True, False, True],
            "eligible": [True, True, True, True, False],
            "data_confidence": ["high", "high", "medium", "low", "high"],
            "confidence_score": [1.0, 1.0, 0.8, 0.6, 1.0],
            # S1-09 confidence_notes: '; '-joined reasons, '—' when none.
            "confidence_notes": ["—", "—", "one feature interpolated", "two features interpolated", "—"],
            # F16 reason forms as carried on the integrated table (Option B):
            # triggered_rules = ", "-joined codes; exclusion_reason = ", "-joined
            # texts; null when eligible. The loader reconstructs the {code, text}
            # pairs from these two.
            "triggered_rules": [None, None, None, None, "protected_area"],
            "exclusion_reason": [None, None, None, None, "Protected area: Test NP"],
            "centroid_lat": [-30.0, -30.1, -30.2, -30.3, -30.4],
            "centroid_lon": [151.0, 151.1, 151.2, 151.3, 151.4],
        },
        geometry=[Point(151.0 + i * 0.1, -30.0 - i * 0.1) for i in range(5)],
        crs=scfg.STORAGE_CRS,
    )
    return df


@pytest.fixture
def scoring_weights() -> WeightsConfig:
    return _weights()


@pytest.fixture
def integrated_table() -> gpd.GeoDataFrame:
    return _integrated()


@pytest.fixture
def scored_table_on_disk(tmp_path: Path, integrated_table, scoring_weights) -> Path:
    """
    Produce a real Scored_Table GeoPackage + CSV under tmp_path from the
    synthetic integrated table, using the actual scoring writer.
    """
    from pipeline.scoring.write import build_scored_table

    scored = score_and_rank(integrated_table, scoring_weights)
    table = build_scored_table(integrated_table, scored, scoring_weights)
    gpkg = tmp_path / "scored.gpkg"
    csv = tmp_path / "scored.csv"
    write_scored_table(table, gpkg, csv)
    return gpkg


@pytest.fixture
def integrated_on_disk(tmp_path: Path, integrated_table) -> Path:
    """Write the synthetic integrated table so the loader can read it back."""
    path = tmp_path / "integrated.gpkg"
    integrated_table.to_file(path, layer=scfg.INTEGRATED_LAYER, driver="GPKG")
    return path


@pytest.fixture
def weights_on_disk(tmp_path: Path, scoring_weights) -> Path:
    """
    Persist the fixture's 4-criterion weights as YAML so the loader uses the
    SAME set the Scored_Table was produced from.
    """
    import yaml

    path = tmp_path / "explanation_test_weights.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "version": "test",
                "criteria": [
                    {"feature": c.feature, "weight": c.weight,
                     "direction": c.direction, "rationale": c.rationale}
                    for c in scoring_weights.criteria
                ],
            }
        ),
        encoding="utf-8",
    )
    return path
