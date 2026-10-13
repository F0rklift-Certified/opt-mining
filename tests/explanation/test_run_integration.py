"""
End-to-end integration test for the S2-06a explanation stage `run()`.

Runs the full orchestrator on the synthetic Scored_Table fixture, redirecting
outputs under tmp_path, and asserts: the return dict, that every artefact +
report + provenance file exists, that a rerun is byte-stable, and that a fatal
condition (missing Scored_Table) raises.

Feature: s2-06a-explanation-engine-eligible-cells
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.explanation import config as ecfg
from pipeline.explanation.run import run


@pytest.fixture
def redirected_outputs(tmp_path, monkeypatch):
    """Point the stage's output dirs at tmp_path so nothing touches DATA/."""
    out = tmp_path / "DATA_explanation"
    meta = out / "metadata"
    monkeypatch.setattr(ecfg, "EXPLANATION_DIR", out)
    monkeypatch.setattr(ecfg, "EXPLANATION_META_DIR", meta)
    return out, meta


def test_run_end_to_end(
    scored_table_on_disk, integrated_on_disk, weights_on_disk, redirected_outputs
):
    out, meta = redirected_outputs
    summary = run(
        verbose=True,
        scored_table_path=scored_table_on_disk,
        integrated_path=integrated_on_disk,
        weights_path=weights_on_disk,
    )

    # Return dict (4 eligible + 1 excluded = 5 explained).
    assert summary["n_eligible_cells"] == 4
    assert summary["n_excluded_cells"] == 1
    assert summary["n_explained"] == 5
    assert summary["n_excluded_explained"] == 1
    assert summary["validation"]["failed"] == 0
    assert summary["templates_config_id"]
    # The fixture weights do not include demand_proxy, so no proxy caveat is
    # emitted here — the proxy path is exercised by the engine/caveat unit
    # tests. The key is that the count is present and consistent (0 here).
    assert summary["n_with_proxy_caveat"] == 0

    # Every artefact + report + provenance file exists.
    for key in [
        "explanations_path", "csv_path", "schema_path", "method_report_path",
        "validation_report_path", "manifest_path", "provenance_path",
        "source_register_path",
    ]:
        assert Path(summary[key]).exists(), key

    # The JSON has one record per cell; eligible and excluded shapes differ.
    records = json.loads(Path(summary["explanations_path"]).read_text(encoding="utf-8"))
    assert len(records) == 5
    eligible = [r for r in records if r["eligible"] is True]
    excluded = [r for r in records if r["eligible"] is False]
    assert len(eligible) == 4
    assert len(excluded) == 1
    assert all(set(r) == set(ecfg.ELIGIBLE_FIELDS) for r in eligible)
    assert all(r["headline"] for r in eligible)
    # Every record carries exactly one data-quality note (both paths).
    assert all(len(r[ecfg.FIELD_DATA_QUALITY_NOTES]) == 1 for r in records)
    # The excluded cell states its F16 exclusion reason and no factors.
    ex = excluded[0]
    assert set(ex) == set(ecfg.EXCLUDED_FIELDS)
    assert ex[ecfg.FIELD_EXCLUSION_REASONS][0]["code"] == "protected_area"


def test_run_is_byte_stable_across_reruns(
    scored_table_on_disk, integrated_on_disk, weights_on_disk, redirected_outputs
):
    out, _ = redirected_outputs
    kw = dict(
        scored_table_path=scored_table_on_disk,
        integrated_path=integrated_on_disk,
        weights_path=weights_on_disk,
    )
    run(**kw)
    json_path = out / ecfg.OUTPUT_FILENAME
    csv_path = out / ecfg.CSV_FILENAME
    first_json = json_path.read_bytes()
    first_csv = csv_path.read_bytes()

    run(**kw)
    assert json_path.read_bytes() == first_json
    assert csv_path.read_bytes() == first_csv


def test_run_raises_on_missing_scored_table(
    integrated_on_disk, weights_on_disk, redirected_outputs
):
    with pytest.raises(FileNotFoundError, match="Scored_Table not found"):
        run(
            scored_table_path=Path("/no/such/scored.gpkg"),
            integrated_path=integrated_on_disk,
            weights_path=weights_on_disk,
        )


def test_run_provenance_marks_derived_product(
    scored_table_on_disk, integrated_on_disk, weights_on_disk, redirected_outputs
):
    summary = run(
        scored_table_path=scored_table_on_disk,
        integrated_path=integrated_on_disk,
        weights_path=weights_on_disk,
    )
    prov = Path(summary["provenance_path"]).read_text(encoding="utf-8")
    assert "DERIVED PRODUCT" in prov
    assert "explanation.run derived layer" in prov
    manifest = json.loads(Path(summary["manifest_path"]).read_text(encoding="utf-8"))
    assert manifest["derived_features"][0]["product_type"] == "derived"
