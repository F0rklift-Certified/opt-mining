"""
Tests for the S2-06a explanation loader.

The loader reads a real Scored_Table + integrated table, recomputes norms via
the scoring stage's own core, and reconciles the recomputed contributions
against the persisted ones. A tampered Scored_Table must fail the guard.

Feature: s2-06a-explanation-engine-eligible-cells
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pytest

from pipeline.explanation import config as ecfg
from pipeline.explanation.load import load_explanation_inputs


def test_eligible_cells_and_norms_attached(
    scored_table_on_disk, integrated_on_disk, weights_on_disk
):
    inputs = load_explanation_inputs(
        scored_table_path=scored_table_on_disk,
        integrated_path=integrated_on_disk,
        weights_path=weights_on_disk,
    )
    # Four eligible cells (c5 excluded).
    assert len(inputs.cells) == 4
    assert inputs.n_eligible_cells == 4
    assert inputs.n_scored_cells == 4
    assert {c.cell_id for c in inputs.cells} == {"c1", "c2", "c3", "c4"}

    # c1: wind 8 (max -> 1.0), dist 2 (min, lower_is_better -> 1.0),
    # slope 5 (min, lower_is_better -> 1.0), inside_rez True -> 1.0.
    c1 = next(c for c in inputs.cells if c.cell_id == "c1")
    norms = {v.feature: v.norm for v in c1.criteria}
    assert norms["wind_speed"] == pytest.approx(1.0)
    assert norms["dist_transmission_km"] == pytest.approx(1.0)
    assert norms["slope_deg"] == pytest.approx(1.0)
    assert norms["inside_rez"] == pytest.approx(1.0)

    # c4: wind 0 -> 0.0, dist 10 (max, lower_is_better) -> 0.0,
    # slope 25 (max, lower_is_better) -> 0.0, inside_rez False -> 0.0.
    c4 = next(c for c in inputs.cells if c.cell_id == "c4")
    norms4 = {v.feature: v.norm for v in c4.criteria}
    assert norms4["wind_speed"] == pytest.approx(0.0)
    assert norms4["inside_rez"] == pytest.approx(0.0)

    # Persisted contributions are carried (not None) for a scored cell.
    assert all(v.contribution is not None for v in c1.criteria)

    # Confidence facts attached to eligible cells (S2-06b).
    assert c1.confidence.level == "high"
    c3 = next(c for c in inputs.cells if c.cell_id == "c3")
    assert c3.confidence.level == "medium"
    assert c3.confidence.notes == "one feature interpolated"


def test_excluded_cells_assembled_with_reasons_and_caveats(
    scored_table_on_disk, integrated_on_disk, weights_on_disk
):
    inputs = load_explanation_inputs(
        scored_table_path=scored_table_on_disk,
        integrated_path=integrated_on_disk,
        weights_path=weights_on_disk,
    )
    # One excluded cell (c5).
    assert inputs.n_excluded_cells == 1
    assert len(inputs.excluded_cells) == 1
    ex = inputs.excluded_cells[0]
    assert ex.cell_id == "c5"
    # F16 pairs parsed from the integrated table's exclusion_reasons JSON.
    assert ex.exclusion_reasons == (
        {"code": "protected_area", "text": "Protected area: Test NP"},
    )
    # Confidence facts attached on the excluded path too.
    assert ex.confidence.level == "high"
    # Participation is per-criterion (c5 has a value for every criterion here).
    assert all(p.participated for p in ex.participation)


def test_excluded_cell_with_null_codes_halts(
    scored_table_on_disk, integrated_table, weights_on_disk, tmp_path
):
    # An excluded cell whose triggered_rules is null violates the F16 pairing
    # contract (an excluded cell must carry ≥ 1 reason) and must halt.
    bad = integrated_table.copy()
    bad.loc[bad["cell_id"] == "c5", "triggered_rules"] = None
    path = tmp_path / "bad_integrated.gpkg"
    bad.to_file(path, layer=ecfg.INTEGRATED_LAYER, driver="GPKG")

    with pytest.raises(ValueError, match="empty/null 'triggered_rules'"):
        load_explanation_inputs(
            scored_table_path=scored_table_on_disk,
            integrated_path=path,
            weights_path=weights_on_disk,
        )


def test_excluded_cell_code_text_count_mismatch_halts(
    scored_table_on_disk, integrated_table, weights_on_disk, tmp_path
):
    # Codes and texts out of step must halt before write (the two F16 forms
    # must be the ordered split of one evaluation).
    bad = integrated_table.copy()
    bad.loc[bad["cell_id"] == "c5", "triggered_rules"] = "protected_area, excessive_slope"
    bad.loc[bad["cell_id"] == "c5", "exclusion_reason"] = "Protected area: Test NP"
    path = tmp_path / "mismatch_integrated.gpkg"
    bad.to_file(path, layer=ecfg.INTEGRATED_LAYER, driver="GPKG")

    with pytest.raises(ValueError, match="out of step"):
        load_explanation_inputs(
            scored_table_path=scored_table_on_disk,
            integrated_path=path,
            weights_path=weights_on_disk,
        )


def test_excluded_cell_multiple_reasons_reconstructed(
    scored_table_on_disk, integrated_table, weights_on_disk, tmp_path
):
    # Two rules -> two paired reasons, in order, reconstructed from the two forms.
    bad = integrated_table.copy()
    bad.loc[bad["cell_id"] == "c5", "triggered_rules"] = "protected_area, urban_area"
    bad.loc[bad["cell_id"] == "c5", "exclusion_reason"] = "Protected area: Test NP, Urban area"
    path = tmp_path / "multi_integrated.gpkg"
    bad.to_file(path, layer=ecfg.INTEGRATED_LAYER, driver="GPKG")

    inputs = load_explanation_inputs(
        scored_table_path=scored_table_on_disk,
        integrated_path=path,
        weights_path=weights_on_disk,
    )
    ex = inputs.excluded_cells[0]
    assert ex.exclusion_reasons == (
        {"code": "protected_area", "text": "Protected area: Test NP"},
        {"code": "urban_area", "text": "Urban area"},
    )


def test_missing_scored_table_raises(integrated_on_disk):
    with pytest.raises(FileNotFoundError, match="Scored_Table not found"):
        load_explanation_inputs(
            scored_table_path=Path("/no/such/scored.gpkg"),
            integrated_path=integrated_on_disk,
        )


def test_reconciliation_guard_fails_on_tampered_contributions(
    scored_table_on_disk, integrated_on_disk, weights_on_disk, tmp_path
):
    # Tamper the persisted Scored_Table: corrupt one contribution column.
    table = gpd.read_file(scored_table_on_disk, layer=ecfg.SCORED_TABLE_LAYER)
    table["contrib_wind_speed"] = table["contrib_wind_speed"] + 0.25
    tampered = tmp_path / "tampered.gpkg"
    table.to_file(tampered, layer=ecfg.SCORED_TABLE_LAYER, driver="GPKG")

    with pytest.raises(RuntimeError, match="reconciliation failed"):
        load_explanation_inputs(
            scored_table_path=tampered,
            integrated_path=integrated_on_disk,
            weights_path=weights_on_disk,
        )


def test_missing_column_in_scored_table_raises(
    scored_table_on_disk, integrated_on_disk, weights_on_disk, tmp_path
):
    table = gpd.read_file(scored_table_on_disk, layer=ecfg.SCORED_TABLE_LAYER)
    table = table.drop(columns=["contrib_slope_deg"])
    broken = tmp_path / "broken.gpkg"
    table.to_file(broken, layer=ecfg.SCORED_TABLE_LAYER, driver="GPKG")

    with pytest.raises(ValueError, match="lacks column"):
        load_explanation_inputs(
            scored_table_path=broken,
            integrated_path=integrated_on_disk,
            weights_path=weights_on_disk,
        )
