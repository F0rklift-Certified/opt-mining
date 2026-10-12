"""
Tests for the S3-08 ``get_sanity_check`` Service_Operation
(``pipeline.service.sanity``).

`get_sanity_check` reads the S1-12 Results_Sidecar the sanity stage
(`pipeline/sanity/`) materialised and projects it VERBATIM into a ``SanityCheck``:
the always-on model-not-trained ``caveat``, the ``preliminary_disclaimer``, the
lineage ``run_metadata``, the six normalised per-check outcomes (incl. the
synthesized exclusion summary), the full ``issues_for_sprint_2`` contradictions,
the known-wind-farm comparison table, the top-ranked band N, and the per-landmark
exclusion assertions — all carried through unchanged (FR2/FR4/FR5, AC3/AC6/AC7).
It performs no sanity check of its own — the no-recompute guarantee (CONTRACT.md
§1). An ABSENT check block surfaces as a visible honest failure
(``passed=False``, ``observed="not available"``), never omitted; a
missing/unreadable sidecar fails HONESTLY (Requirement 7.3).

Mirrors `tests/service/test_quality.py`: unit tests over a hand-written sidecar
written to a temp path (the sanity module's path constant monkeypatched), plus a
path-composition test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pipeline.sanity import config as sanity_config
from pipeline.service import config as service_config
from pipeline.service import get_sanity_check
from pipeline.service.models import (
    SanityCheck,
    SanityCheckItem,
    SanityContradiction,
    SanityRunMetadata,
    SanityWindFarmRow,
)
from pipeline.service.runs import EngineOutputError


@pytest.fixture
def sanity_sidecar(tmp_path, monkeypatch):
    """
    Redirect the S1-12 Results_Sidecar to a temp path.

    The service composes the sidecar path from the producing module's own
    constant (`pipeline.sanity.config.SIDECAR_PATH`), so patching that constant
    exercises the real composition rather than a re-typed literal. Returns a
    writer that materialises a given sidecar object at that path.
    """
    path = tmp_path / "optmining_validation-results_2026_nsw.json"
    monkeypatch.setattr(sanity_config, "SIDECAR_PATH", path, raising=True)

    def write(result: dict) -> Path:
        path.write_text(json.dumps(result), encoding="utf-8")
        return path

    write.path = path  # type: ignore[attr-defined]
    return write


def _outcome(label: str, passed: bool, observed: str = "obs") -> dict:
    return {"label": label, "expected": "exp", "observed": observed, "passed": passed}


def _sidecar(**overrides) -> dict:
    """A minimal Results_Sidecar in the shape report.py::build_sidecar emits."""
    base = {
        "preliminary_disclaimer": "preliminary disclaimer text",
        "caveat": "model not trained to reproduce these locations",
        "run_metadata": {
            "run_timestamp": "2026-10-12T11:05:16+00:00",
            "pipeline_version": "abc123",
            "n_cells": 47311,
            "n_eligible": 32525,
            "resolved_shortlist_path": "DATA/shortlist/sprint1_shortlist.geojson",
        },
        "checks": {
            "known_wind_farm_comparison": {
                "outcome": _outcome("Upper_Quartile count", True),
                "top_band_outcome": _outcome("Known-wind-farm top-ranked band", False),
                "n_in_top_band": 1,
                "top_band_n": 20,
                "table": [
                    {
                        "wind_farm": "Sapphire Wind Farm",
                        "cell_id": "S29.686_E151.436",
                        "score": 0.8838,
                        "rank": 154.0,
                        "percentile": 99.5,
                        "in_upper_quartile": True,
                        "notes": "In Upper_Quartile, as expected.",
                    },
                    {
                        "wind_farm": "Taralga Wind Farm",
                        "cell_id": "S34.436_E149.886",
                        "score": None,
                        "rank": None,
                        "percentile": None,
                        "in_upper_quartile": False,
                        "notes": "Excluded_Cell; recorded honestly.",
                    },
                ],
            },
            "exclusion_validation": {
                "n_passed": 6,
                "n_failed": 0,
                "all_passed": True,
                "assertions": [
                    {
                        "landmark": "Sydney CBD",
                        "kind": "urban",
                        "passed": True,
                    }
                ],
            },
            "score_distribution": {
                "cluster_outcome": _outcome("Degenerate-clustering", True),
                "correlation_outcome": _outcome("Wind-versus-score correlation", True),
                "rez_outcome": _outcome(
                    "REZ representation among top cells",
                    True,
                    observed="1187 of 3253 top cells inside a REZ",
                ),
                "rez_represented": ["New England REZ"],
                "n_top_inside_rez": 1187,
                "top_n_considered": 3253,
            },
        },
        "issues_for_sprint_2": [
            {
                "check": "Known Wind Farm Comparison",
                "description": "Taralga locates to an Excluded_Cell.",
                "kind": "data_issue",
                "investigation_note": "Distinguish a DATA issue from a MODEL result.",
            }
        ],
    }
    base.update(overrides)
    return base


# --------------------------------------------------------------------------- #
# The projection — verbatim, in order, no silent passes.                       #
# --------------------------------------------------------------------------- #


def test_projects_sidecar_verbatim(sanity_sidecar):
    sanity_sidecar(_sidecar())

    sanity = get_sanity_check()

    assert isinstance(sanity, SanityCheck)
    assert sanity.caveat == "model not trained to reproduce these locations"
    assert sanity.preliminary_disclaimer == "preliminary disclaimer text"
    assert sanity.top_band_n == 20

    # Six normalised check items IN ORDER.
    assert all(isinstance(c, SanityCheckItem) for c in sanity.checks)
    assert [c.name for c in sanity.checks] == [
        "Upper_Quartile count",
        "Known-wind-farm top-ranked band",
        "Exclusion validation",
        "Degenerate-clustering",
        "Wind-versus-score correlation",
        "REZ representation among top cells",
    ]
    assert [c.passed for c in sanity.checks] == [True, False, True, True, True, True]


def test_run_metadata_projected(sanity_sidecar):
    sanity_sidecar(_sidecar())

    meta = get_sanity_check().run_metadata

    assert isinstance(meta, SanityRunMetadata)
    assert meta.run_timestamp == "2026-10-12T11:05:16+00:00"
    assert meta.pipeline_version == "abc123"
    assert meta.n_cells == 47311
    assert meta.n_eligible == 32525
    assert meta.resolved_shortlist_path == "DATA/shortlist/sprint1_shortlist.geojson"


def test_exclusion_summary_is_synthesized(sanity_sidecar):
    """The exclusion item is composed from n_passed/n_failed/all_passed."""
    sanity_sidecar(_sidecar())

    item = {c.name: c for c in get_sanity_check().checks}["Exclusion validation"]

    assert item.expected == "all documented landmarks excluded or absent from grid"
    assert item.observed == "6 passed / 0 failed"
    assert item.passed is True


def test_exclusion_summary_fails_when_assertions_fail(sanity_sidecar):
    s = _sidecar()
    s["checks"]["exclusion_validation"] = {
        "n_passed": 4,
        "n_failed": 2,
        "all_passed": False,
        "assertions": [],
    }
    sanity_sidecar(s)

    item = {c.name: c for c in get_sanity_check().checks}["Exclusion validation"]

    assert item.observed == "4 passed / 2 failed"
    assert item.passed is False


def test_contradictions_carried_through(sanity_sidecar):
    sanity_sidecar(_sidecar())

    contradictions = get_sanity_check().contradictions

    assert len(contradictions) == 1
    assert isinstance(contradictions[0], SanityContradiction)
    assert contradictions[0].check == "Known Wind Farm Comparison"
    assert contradictions[0].kind == "data_issue"
    assert "Excluded_Cell" in contradictions[0].description


def test_wind_farm_rows_read_wind_farm_label(sanity_sidecar):
    """Rows read `wind_farm` (NOT `name`); nulls carried for excluded cells."""
    sanity_sidecar(_sidecar())

    rows = get_sanity_check().wind_farms

    assert all(isinstance(r, SanityWindFarmRow) for r in rows)
    assert [r.wind_farm for r in rows] == ["Sapphire Wind Farm", "Taralga Wind Farm"]
    excluded = rows[1]
    assert excluded.score is None and excluded.rank is None
    assert excluded.percentile is None
    assert excluded.in_upper_quartile is False


def test_exclusion_assertions_carried_verbatim(sanity_sidecar):
    sanity_sidecar(_sidecar())

    assertions = get_sanity_check().exclusion_assertions

    assert assertions == [{"landmark": "Sydney CBD", "kind": "urban", "passed": True}]


# --------------------------------------------------------------------------- #
# Honest degradation — absent blocks / missing run_metadata never omit/raise.  #
# --------------------------------------------------------------------------- #


def test_absent_check_block_is_a_visible_failure(sanity_sidecar):
    """An absent outcome block -> passed=False / observed='not available'."""
    s = _sidecar()
    # Drop the REZ and top-band outcomes entirely.
    del s["checks"]["score_distribution"]["rez_outcome"]
    del s["checks"]["known_wind_farm_comparison"]["top_band_outcome"]
    sanity_sidecar(s)

    by_name = {c.name: c for c in get_sanity_check().checks}

    rez = by_name["REZ representation among top cells"]
    assert rez.passed is False and rez.observed == "not available"
    top_band = by_name["Known-wind-farm top-ranked band"]
    assert top_band.passed is False and top_band.observed == "not available"


def test_missing_run_metadata_degrades_to_empty_lineage(sanity_sidecar):
    s = _sidecar()
    del s["run_metadata"]
    sanity_sidecar(s)

    meta = get_sanity_check().run_metadata

    assert meta.run_timestamp == ""
    assert meta.pipeline_version == ""
    assert meta.resolved_shortlist_path == ""
    assert meta.n_cells is None and meta.n_eligible is None


def test_to_dict_matches_contract_shape(sanity_sidecar):
    sanity_sidecar(_sidecar())

    payload = get_sanity_check().to_dict()

    assert set(payload) == {
        "caveat",
        "preliminary_disclaimer",
        "run_metadata",
        "checks",
        "contradictions",
        "wind_farms",
        "top_band_n",
        "exclusion_assertions",
    }
    assert payload["run_metadata"]["n_cells"] == 47311
    assert payload["checks"][0] == {
        "name": "Upper_Quartile count",
        "expected": "exp",
        "observed": "obs",
        "passed": True,
    }


# --------------------------------------------------------------------------- #
# Honest failure — missing / unreadable / non-object names the input (7.3).    #
# --------------------------------------------------------------------------- #


def test_missing_sidecar_raises_naming_the_input(tmp_path, monkeypatch):
    absent = tmp_path / "optmining_validation-results_2026_nsw.json"
    monkeypatch.setattr(sanity_config, "SIDECAR_PATH", absent, raising=True)

    with pytest.raises(EngineOutputError, match="Sanity Results_Sidecar is missing"):
        get_sanity_check()


def test_unreadable_sidecar_raises(sanity_sidecar):
    sanity_sidecar.path.write_text("{ not valid json", encoding="utf-8")

    with pytest.raises(EngineOutputError, match="unreadable"):
        get_sanity_check()


def test_non_object_sidecar_raises(sanity_sidecar):
    sanity_sidecar.path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    with pytest.raises(EngineOutputError, match="not the expected object"):
        get_sanity_check()


# --------------------------------------------------------------------------- #
# The path is composed from the producing module (no re-typed literal).        #
# --------------------------------------------------------------------------- #


def test_path_is_composed_from_the_producing_config():
    assert service_config.sanity_result_path() == sanity_config.SIDECAR_PATH
