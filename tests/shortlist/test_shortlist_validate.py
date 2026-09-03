"""
Unit tests for the S1-11 shortlist validation checks (task 13.2).

These are example-based unit tests over ``tmp_path``. They exercise the
shortlist's OWN "no silent passes" validation tier
(``pipeline.shortlist.validate``) and the cross-domain tier helpers in
``pipeline.validate`` (Requirement 12.7).

The governing rule is *no silent passes*: every check must carry a name, a
non-empty ``expected`` and a non-empty ``observed`` string and an explicit
boolean ``passed`` — a check that only speaks up when it fails is a check
nobody can audit. So the well-formed case asserts EVERY check is present with
that shape and all pass, and each BAD case violates exactly one invariant and
asserts (a) the corresponding check FAILs, (b) every other check still passes,
and (c) the rendered report still LISTS the failed check with a FAIL marker.

Conventions follow ``tests/test_shortlist_writers.py`` and
``tests/test_shortlist_report.py`` (tmp_path, synthetic frames, real artefacts
written via the shortlist writers / report sidecar).
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from pipeline import validate as cross_validate
from pipeline.shortlist import config
from pipeline.shortlist.report import write_metadata_sidecar
from pipeline.shortlist.validate import (
    build_validation_report,
    summarise_checks,
    validate,
)
from pipeline.shortlist.write import write_csv, write_geojson

# Fixed run identity so the artefacts are deterministic regardless of wall clock.
FIXED_TS = "2026-03-14T09:30:15+00:00"
FIXED_VERSION = "abc1234-dirty"
EFFECTIVE_TOP_N = 20


# ---------------------------------------------------------------------------
# Fixtures / builders
# ---------------------------------------------------------------------------


def _shortlist_frame(n: int = 3) -> pd.DataFrame:
    """A well-formed assembled shortlist with the documented columns in order."""
    return pd.DataFrame(
        {
            "rank": list(range(1, n + 1)),
            "cell_id": [f"C{i:04d}" for i in range(1, n + 1)],
            "suitability_score": [0.90 - 0.10 * i for i in range(n)],
            "confidence": (["high", "low"] * n)[:n],
            "centroid_lat": [-30.0 - 0.05 * i for i in range(n)],
            "centroid_lon": [151.0 + 0.05 * i for i in range(n)],
        },
        columns=list(config.SHORTLIST_COLUMNS),
    )


def _write_artefacts(tmp_path, shortlist: pd.DataFrame):
    """
    Write the CSV / GeoJSON / metadata sidecar for ``shortlist`` and return the
    three paths, so ``validate()`` reads what actually landed on disk.
    """
    csv_path = tmp_path / "sprint1_shortlist_20260314.csv"
    geojson_path = tmp_path / "sprint1_shortlist_20260314.geojson"
    sidecar_path = tmp_path / config.METADATA_SIDECAR_FILENAME

    write_csv(shortlist, csv_path)
    write_geojson(shortlist, geojson_path, geometry="centroid")

    scored = tmp_path / "scored_input.gpkg"
    scored.write_bytes(b"synthetic scored table bytes \x00\x01\x02")
    write_metadata_sidecar(
        sidecar_path,
        scored_path=scored,
        effective_top_n=EFFECTIVE_TOP_N,
        n_shortlisted=int(len(shortlist)),
        geometry="centroid",
        pipeline_version=FIXED_VERSION,
        run_timestamp=FIXED_TS,
    )
    return csv_path, geojson_path, sidecar_path


def _run_validate(tmp_path, shortlist, *, effective_top_n=EFFECTIVE_TOP_N):
    csv_path, geojson_path, sidecar_path = _write_artefacts(tmp_path, shortlist)
    return validate(
        shortlist,
        effective_top_n=effective_top_n,
        csv_path=csv_path,
        geojson_path=geojson_path,
        metadata_sidecar_path=sidecar_path,
    ), (csv_path, geojson_path, sidecar_path)


def _find_check(result: dict, needle: str) -> dict:
    """The single check whose name contains ``needle`` (case-insensitive)."""
    matches = [c for c in result["checks"] if needle.lower() in c["name"].lower()]
    assert len(matches) == 1, (
        f"expected exactly one check matching {needle!r}, got "
        f"{[c['name'] for c in matches]}"
    )
    return matches[0]


def _assert_only_failure(result: dict, failed_needle: str) -> dict:
    """
    Assert the check matching ``failed_needle`` FAILs and every OTHER check
    passes — the bad frame violates exactly one invariant.
    """
    failed = _find_check(result, failed_needle)
    assert failed["passed"] is False
    others = [c for c in result["checks"] if c is not failed]
    still_passing = [c["name"] for c in others if not c["passed"]]
    assert still_passing == [], f"unexpected extra failures: {still_passing}"
    return failed


def _assert_report_lists_fail(result: dict, name: str) -> None:
    """The rendered report lists the named check on a row carrying a FAIL marker."""
    report = build_validation_report(result, FIXED_TS, FIXED_VERSION)
    assert name in report
    fail_rows = [
        line for line in report.splitlines()
        if name in line and "FAIL" in line
    ]
    assert fail_rows, f"report does not show a FAIL row for {name!r}:\n{report}"


# ---------------------------------------------------------------------------
# Well-formed shortlist: every check present, all pass, no silent passes
# ---------------------------------------------------------------------------


class TestWellFormedShortlist:
    def test_all_checks_pass(self, tmp_path):
        result, _ = _run_validate(tmp_path, _shortlist_frame())
        assert result["failed"] == 0
        assert result["failed_names"] == []
        assert result["passed"] == result["total"]
        assert result["total"] >= 7  # every documented invariant is present

    def test_every_check_has_the_audit_shape_no_silent_passes(self, tmp_path):
        """
        Each check carries a name, a NON-EMPTY expected and observed, a boolean
        ``passed`` and a severity — the "no silent passes" contract: the
        evidence is always on the page whether the check passed or not.
        """
        result, _ = _run_validate(tmp_path, _shortlist_frame())
        for check in result["checks"]:
            assert isinstance(check["name"], str) and check["name"].strip()
            assert isinstance(check["expected"], str) and check["expected"].strip()
            assert isinstance(check["observed"], str) and check["observed"].strip()
            assert isinstance(check["passed"], bool)
            assert check["severity"] == "fatal"

    def test_all_documented_invariants_are_present(self, tmp_path):
        """Every Requirement-12 invariant surfaces as its own named check."""
        result, _ = _run_validate(tmp_path, _shortlist_frame())
        for needle in (
            "row count",
            "SHORTLIST_COLUMNS",
            "Eligible_Cell",
            "ascending rank",
            "non-null centroid",
            "same cell_id",
            "Preliminary_Disclaimer",
            "Metadata sidecar records",
        ):
            _find_check(result, needle)

    def test_summarise_checks_tallies_match(self, tmp_path):
        result, _ = _run_validate(tmp_path, _shortlist_frame())
        recomputed = summarise_checks(result["checks"])
        assert recomputed["total"] == result["total"]
        assert recomputed["passed"] == result["passed"]
        assert recomputed["failed"] == result["failed"]

    def test_report_lists_every_check_as_pass(self, tmp_path):
        result, _ = _run_validate(tmp_path, _shortlist_frame())
        report = build_validation_report(result, FIXED_TS, FIXED_VERSION)
        # Every check name appears in the rendered table.
        for check in result["checks"]:
            assert check["name"] in report
        # An all-pass report never carries a FAIL marker.
        assert "FAIL" not in report
        assert f"{result['passed']}/{result['total']} checks passed" in report
        assert FIXED_VERSION in report


# ---------------------------------------------------------------------------
# BAD shortlists: each violates exactly one invariant
# ---------------------------------------------------------------------------


class TestBadShortlists:
    def test_row_count_over_top_n_fails(self, tmp_path):
        """More rows than the effective Top_N fails the row-count check (12.1)."""
        shortlist = _shortlist_frame(5)
        result, _ = _run_validate(tmp_path, shortlist, effective_top_n=3)

        failed = _assert_only_failure(result, "row count")
        assert "5" in failed["observed"]
        assert "3" in failed["expected"]
        _assert_report_lists_fail(result, failed["name"])

    def test_null_score_row_fails_eligibility(self, tmp_path):
        """A null-score row is an Excluded_Cell and fails eligibility (12.2)."""
        shortlist = _shortlist_frame()
        shortlist.loc[1, "suitability_score"] = np.nan
        result, _ = _run_validate(tmp_path, shortlist)

        failed = _assert_only_failure(result, "Eligible_Cell")
        assert "1" in failed["observed"]
        _assert_report_lists_fail(result, failed["name"])

    def test_null_rank_row_fails_eligibility(self, tmp_path):
        """A null-rank row is also ineligible (12.2). rank is kept nullable."""
        shortlist = _shortlist_frame()
        shortlist["rank"] = shortlist["rank"].astype("Int64")
        shortlist.loc[2, "rank"] = pd.NA
        result, _ = _run_validate(tmp_path, shortlist)

        # A null rank breaks eligibility; the ordering check tolerates the NA
        # (adjacent-decrease comparison against NA is False), so eligibility is
        # the single failure we assert on here.
        failed = _find_check(result, "Eligible_Cell")
        assert failed["passed"] is False
        _assert_report_lists_fail(result, failed["name"])

    def test_out_of_order_rank_fails_ordering(self, tmp_path):
        """A descending adjacent rank pair fails the ascending-order check (12.3)."""
        shortlist = _shortlist_frame(4)
        # Swap ranks so row 1 > row 2 (3, 1, 2, 4) — one adjacent decrease.
        shortlist["rank"] = [3, 1, 2, 4]
        result, _ = _run_validate(tmp_path, shortlist)

        failed = _assert_only_failure(result, "ascending rank")
        assert failed["observed"].startswith("1") or " 1 " in failed["observed"]
        _assert_report_lists_fail(result, failed["name"])

    def test_null_coordinate_fails_coordinate_check(self, tmp_path):
        """A null centroid coordinate fails the non-null coordinate check (12.4).

        The disk writers halt on a null coordinate (Requirement 4.5), so the
        artefacts are written from a well-formed frame and the null-coordinate
        frame is handed to ``validate()`` in memory — the coordinate check reads
        the in-memory ``shortlist`` argument.
        """
        good = _shortlist_frame()
        csv_path, geojson_path, sidecar_path = _write_artefacts(tmp_path, good)

        bad = good.copy()
        bad.loc[0, "centroid_lon"] = np.nan
        result = validate(
            bad,
            effective_top_n=EFFECTIVE_TOP_N,
            csv_path=csv_path,
            geojson_path=geojson_path,
            metadata_sidecar_path=sidecar_path,
        )
        failed = _assert_only_failure(result, "non-null centroid")
        assert "1" in failed["observed"]
        _assert_report_lists_fail(result, failed["name"])

    def test_csv_geojson_cell_id_mismatch_fails(self, tmp_path):
        """
        Rewriting the CSV so its cell_id sequence differs from the GeoJSON fails
        the CSV/GeoJSON equality check (12.5).
        """
        shortlist = _shortlist_frame()
        csv_path, geojson_path, sidecar_path = _write_artefacts(tmp_path, shortlist)

        # Tamper the CSV: change the first cell_id so the ordered sequences differ.
        text = csv_path.read_text()
        tampered = text.replace("C0001", "C9999", 1)
        assert tampered != text
        csv_path.write_text(tampered)

        result = validate(
            shortlist,
            effective_top_n=EFFECTIVE_TOP_N,
            csv_path=csv_path,
            geojson_path=geojson_path,
            metadata_sidecar_path=sidecar_path,
        )
        failed = _assert_only_failure(result, "same cell_id")
        assert "differs" in failed["observed"].lower()
        _assert_report_lists_fail(result, failed["name"])

    def test_missing_disclaimer_in_geojson_fails_disclaimer_check(self, tmp_path):
        """
        Tampering the GeoJSON to drop the disclaimer foreign member fails the
        disclaimer/resolution check (12.6).
        """
        shortlist = _shortlist_frame()
        csv_path, geojson_path, sidecar_path = _write_artefacts(tmp_path, shortlist)

        collection = json.loads(geojson_path.read_text())
        del collection["preliminary_disclaimer"]
        geojson_path.write_text(json.dumps(collection))

        result = validate(
            shortlist,
            effective_top_n=EFFECTIVE_TOP_N,
            csv_path=csv_path,
            geojson_path=geojson_path,
            metadata_sidecar_path=sidecar_path,
        )
        failed = _assert_only_failure(result, "Preliminary_Disclaimer")
        assert "GeoJSON MISSING" in failed["observed"]
        _assert_report_lists_fail(result, failed["name"])

    def test_missing_resolution_in_sidecar_fails_disclaimer_check(self, tmp_path):
        """A sidecar missing the resolution statement fails the 12.6 check."""
        shortlist = _shortlist_frame()
        csv_path, geojson_path, sidecar_path = _write_artefacts(tmp_path, shortlist)

        record = json.loads(sidecar_path.read_text())
        del record["analysis_resolution"]
        sidecar_path.write_text(json.dumps(record))

        result = validate(
            shortlist,
            effective_top_n=EFFECTIVE_TOP_N,
            csv_path=csv_path,
            geojson_path=geojson_path,
            metadata_sidecar_path=sidecar_path,
        )
        failed = _assert_only_failure(result, "Preliminary_Disclaimer")
        assert "sidecar MISSING" in failed["observed"]
        _assert_report_lists_fail(result, failed["name"])

    def test_sidecar_missing_pipeline_version_fails_reproducibility_check(self, tmp_path):
        """
        A sidecar without pipeline_version fails the reproducibility-fields check
        (9.x) while every other check still passes.
        """
        shortlist = _shortlist_frame()
        csv_path, geojson_path, sidecar_path = _write_artefacts(tmp_path, shortlist)

        record = json.loads(sidecar_path.read_text())
        del record["pipeline_version"]
        sidecar_path.write_text(json.dumps(record))

        result = validate(
            shortlist,
            effective_top_n=EFFECTIVE_TOP_N,
            csv_path=csv_path,
            geojson_path=geojson_path,
            metadata_sidecar_path=sidecar_path,
        )
        failed = _assert_only_failure(result, "Metadata sidecar records")
        assert "pipeline_version MISSING" in failed["observed"]
        _assert_report_lists_fail(result, failed["name"])

    def test_schema_mismatch_fails_schema_check(self, tmp_path):
        """A shortlist missing a documented column fails the schema check (4.1).

        The writers reject a frame missing a core column (fail-fast KeyError),
        so the artefacts are written from a well-formed frame and the
        schema-broken frame is validated in memory — the schema check reads the
        in-memory ``shortlist`` columns and must FAIL rather than crash.
        """
        good = _shortlist_frame()
        csv_path, geojson_path, sidecar_path = _write_artefacts(tmp_path, good)

        bad = good.drop(columns=["confidence"])
        result = validate(
            bad,
            effective_top_n=EFFECTIVE_TOP_N,
            csv_path=csv_path,
            geojson_path=geojson_path,
            metadata_sidecar_path=sidecar_path,
        )
        failed = _find_check(result, "SHORTLIST_COLUMNS")
        assert failed["passed"] is False
        assert "confidence" in failed["observed"]
        _assert_report_lists_fail(result, failed["name"])


# ---------------------------------------------------------------------------
# Cross-domain tier: _close null-aware behaviour (pipeline/validate.py)
# ---------------------------------------------------------------------------


class TestCloseNullAware:
    def test_both_null_is_equal(self):
        a = pd.Series([np.nan, np.nan])
        b = pd.Series([np.nan, np.nan])
        assert cross_validate._close(a, b).tolist() == [True, True]

    def test_null_vs_value_is_not_equal(self):
        a = pd.Series([np.nan, 1.0])
        b = pd.Series([1.0, np.nan])
        assert cross_validate._close(a, b).tolist() == [False, False]

    def test_within_tolerance_is_equal(self):
        a = pd.Series([1.0, 2.0])
        b = pd.Series([1.0 + 1e-12, 2.0 - 1e-12])
        assert cross_validate._close(a, b).tolist() == [True, True]

    def test_outside_tolerance_is_not_equal(self):
        a = pd.Series([1.0])
        b = pd.Series([1.1])
        assert cross_validate._close(a, b).tolist() == [False]

    def test_equal_values_are_equal(self):
        a = pd.Series([1.0, -30.5, 151.25])
        b = pd.Series([1.0, -30.5, 151.25])
        assert cross_validate._close(a, b).tolist() == [True, True, True]


# ---------------------------------------------------------------------------
# Cross-domain tier: empty-output early return + subset mismatch
# ---------------------------------------------------------------------------


class TestShortlistCrossChecks:
    def test_returns_empty_when_no_shortlist_output_exists(self, tmp_path, monkeypatch):
        """
        With no shortlist output on disk the cross-checks return [] so a partial
        pipeline run does not fail on a stage that has not been run.
        """
        empty_dir = tmp_path / "shortlist"
        empty_dir.mkdir()
        monkeypatch.setattr(config, "SHORTLIST_DIR", empty_dir)

        assert cross_validate._run_shortlist_cross_checks() == []

    def test_returns_empty_when_shortlist_dir_absent(self, tmp_path, monkeypatch):
        """A missing shortlist directory also yields [] (nothing to check yet)."""
        monkeypatch.setattr(config, "SHORTLIST_DIR", tmp_path / "does-not-exist")
        assert cross_validate._run_shortlist_cross_checks() == []

    def test_latest_shortlist_outputs_none_when_absent(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config, "SHORTLIST_DIR", tmp_path / "missing")
        csv_path, geojson_path = cross_validate._latest_shortlist_outputs(config)
        assert csv_path is None and geojson_path is None

    def test_subset_mismatch_scenario_fails_subset_check(self, tmp_path, monkeypatch):
        """
        A shortlisted cell_id absent from the Scored_Table fails the subset
        cross-check, with no re-scoring assumed. Uses a synthetic Scored_Table
        GeoPackage and a shortlist CSV whose cell_id is not present in it.
        """
        gpd = pytest.importorskip("geopandas")
        from shapely.geometry import Point

        out_dir = tmp_path / "shortlist"
        out_dir.mkdir()
        # Shortlist CSV carrying a cell_id (C9999) absent from the scored table.
        csv_path = out_dir / f"{config.OUTPUT_PREFIX}_20260314.csv"
        pd.DataFrame(
            {
                "rank": [1],
                "cell_id": ["C9999"],
                "suitability_score": [0.5],
                "confidence": ["high"],
                "centroid_lat": [-30.0],
                "centroid_lon": [151.0],
            }
        ).to_csv(csv_path, index=False)
        # Pair a geojson so _latest_shortlist_outputs finds the pair.
        (out_dir / f"{config.OUTPUT_PREFIX}_20260314.geojson").write_text("{}")

        # Synthetic Scored_Table GeoPackage with a DIFFERENT cell_id (C0001).
        scored_path = tmp_path / "scored.gpkg"
        scored = gpd.GeoDataFrame(
            {
                "cell_id": ["C0001"],
                "suitability_score": [0.5],
                "rank": [1],
            },
            geometry=[Point(151.0, -30.0)],
            crs="EPSG:4326",
        )
        scored.to_file(scored_path, layer=config.SCORED_LAYER, driver="GPKG")

        monkeypatch.setattr(config, "SHORTLIST_DIR", out_dir)
        monkeypatch.setattr(config, "SCORED_PATH", scored_path)
        # Point the grid at a non-existent path so only the scored checks run.
        monkeypatch.setattr(config, "GRID_PATH", tmp_path / "no-grid.gpkg")

        checks = cross_validate._run_shortlist_cross_checks()
        subset = [c for c in checks if "subset of the Scored_Table" in c["name"]]
        assert len(subset) == 1
        assert subset[0]["passed"] is False
        assert "1" in subset[0]["observed"]  # one cell absent

    def test_passing_cross_check_scenario(self, tmp_path, monkeypatch):
        """
        A shortlist whose cell_id / scores / ranks / coordinates match the
        synthetic Scored_Table and grid passes every cross-check.
        """
        gpd = pytest.importorskip("geopandas")
        from shapely.geometry import Point

        out_dir = tmp_path / "shortlist"
        out_dir.mkdir()
        csv_path = out_dir / f"{config.OUTPUT_PREFIX}_20260314.csv"
        pd.DataFrame(
            {
                "rank": [1, 2],
                "cell_id": ["C0001", "C0002"],
                "suitability_score": [0.9, 0.8],
                "confidence": ["high", "low"],
                "centroid_lat": [-30.0, -30.05],
                "centroid_lon": [151.0, 151.05],
            }
        ).to_csv(csv_path, index=False)
        (out_dir / f"{config.OUTPUT_PREFIX}_20260314.geojson").write_text("{}")

        scored_path = tmp_path / "scored.gpkg"
        gpd.GeoDataFrame(
            {
                "cell_id": ["C0001", "C0002", "C0003"],
                "suitability_score": [0.9, 0.8, 0.7],
                "rank": [1, 2, 3],
            },
            geometry=[Point(151.0, -30.0), Point(151.05, -30.05), Point(151.1, -30.1)],
            crs="EPSG:4326",
        ).to_file(scored_path, layer=config.SCORED_LAYER, driver="GPKG")

        grid_path = tmp_path / "grid.gpkg"
        gpd.GeoDataFrame(
            {
                "cell_id": ["C0001", "C0002", "C0003"],
                "centroid_lat": [-30.0, -30.05, -30.1],
                "centroid_lon": [151.0, 151.05, 151.1],
            },
            geometry=[Point(151.0, -30.0), Point(151.05, -30.05), Point(151.1, -30.1)],
            crs="EPSG:4326",
        ).to_file(grid_path, layer=config.GRID_LAYER, driver="GPKG")

        monkeypatch.setattr(config, "SHORTLIST_DIR", out_dir)
        monkeypatch.setattr(config, "SCORED_PATH", scored_path)
        monkeypatch.setattr(config, "GRID_PATH", grid_path)

        checks = cross_validate._run_shortlist_cross_checks()
        assert checks, "expected cross-checks to run against synthetic inputs"
        failed = [c["name"] for c in checks if not c["passed"]]
        assert failed == [], f"unexpected cross-check failures: {failed}"
        # All four documented cross-checks are present.
        names = " ".join(c["name"] for c in checks)
        assert "subset of the Scored_Table" in names
        assert "subset of the Analysis_Grid" in names
        assert "scores and ranks equal the Scored_Table" in names
        assert "coordinates equal the Analysis_Grid" in names
