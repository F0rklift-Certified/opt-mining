"""
Tests for S2-06a explanation assembly + writers + schema doc.

Assembly is pure; the JSON round-trips to the expected records; both artefacts
are byte-identical across reruns with unchanged inputs; the schema doc lists
every eligible field.

Feature: s2-06a-explanation-engine-eligible-cells
"""

from __future__ import annotations

import json

from pipeline.explanation import config as ecfg
from pipeline.explanation.engine import CellExplanationInput, CriterionView
from pipeline.explanation.templates import load_templates
from pipeline.explanation.write import (
    build_explanations,
    build_schema_doc,
    write_csv,
    write_explanations,
    write_json,
    write_schema_doc,
)
from pipeline.scoring.normalise import Bounds

T = load_templates()


def _bounds(feature, *, boolean=False) -> Bounds:
    return Bounds(
        feature=feature, lo=0.0, hi=1.0 if boolean else 10.0,
        observed_min=0.0, observed_max=1.0 if boolean else 10.0,
        is_boolean=boolean, is_constant=False, n_observed=4,
    )


def _cells() -> list[CellExplanationInput]:
    return [
        CellExplanationInput(
            cell_id="NSW001",
            criteria=(
                CriterionView("wind_speed", 0.4, 0.95, _bounds("wind_speed")),
                CriterionView("inside_rez", 0.2, 1.0, _bounds("inside_rez", boolean=True)),
                CriterionView("slope_deg", 0.05, 0.3, _bounds("slope_deg")),
            ),
        ),
        CellExplanationInput(
            cell_id="NSW002",
            criteria=(
                CriterionView("demand_proxy", 0.15, 0.8, _bounds("demand_proxy")),
                CriterionView("wind_speed", 0.05, 0.2, _bounds("wind_speed")),
            ),
        ),
    ]


def test_build_explanations_one_record_per_cell():
    records = build_explanations(_cells(), T)
    assert [r["cell_id"] for r in records] == ["NSW001", "NSW002"]
    assert all(set(r) == set(ecfg.ELIGIBLE_FIELDS) for r in records)
    assert all(r["eligible"] is True for r in records)


def test_json_round_trips_to_expected_structure(tmp_path):
    records = build_explanations(_cells(), T)
    path = tmp_path / "expl.json"
    write_json(records, path)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    assert loaded == records


def test_json_field_order_is_the_documented_order(tmp_path):
    records = build_explanations(_cells(), T)
    path = tmp_path / "expl.json"
    write_json(records, path)
    first = json.loads(path.read_text(encoding="utf-8"))[0]
    assert list(first.keys()) == list(ecfg.ELIGIBLE_FIELDS)


def test_json_is_byte_stable_across_reruns(tmp_path):
    records = build_explanations(_cells(), T)
    p1 = tmp_path / "a.json"
    p2 = tmp_path / "b.json"
    write_json(records, p1)
    write_json(records, p2)
    assert p1.read_bytes() == p2.read_bytes()


def test_csv_is_byte_stable_and_joins_lists(tmp_path):
    records = build_explanations(_cells(), T)
    p1 = tmp_path / "a.csv"
    p2 = tmp_path / "b.csv"
    write_csv(records, p1)
    write_csv(records, p2)
    assert p1.read_bytes() == p2.read_bytes()
    text = p1.read_text(encoding="utf-8")
    assert "cell_id,eligible,headline,positive_factors,weaknesses" in text
    # The pipe delimiter joins multiple positive factors into one cell.
    assert " | " in text


def test_write_explanations_writes_both(tmp_path):
    records = build_explanations(_cells(), T)
    j = tmp_path / "e.json"
    c = tmp_path / "e.csv"
    write_explanations(records, j, c)
    assert j.exists() and c.exists()


def test_schema_doc_lists_every_field(tmp_path):
    doc = build_schema_doc(T)
    for field in ecfg.ELIGIBLE_FIELDS:
        assert f"`{field}`" in doc
    assert "S2-06b extends" in doc
    assert "get_site_detail" in doc
    # Do-not-edit banner present.
    assert "Do not edit by hand" in doc

    path = tmp_path / "schema.md"
    write_schema_doc(T, path)
    assert path.read_text(encoding="utf-8") == doc
