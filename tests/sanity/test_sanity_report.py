"""Unit tests for the S1-12 sanity-check report renderer, writer, and sidecar.

Covers task 10.3 of the s1-12-validation-sanity-check spec:

  - ``render_report`` output is banner-stamped (contains the ``common.geo``
    do-not-edit banner text), contains all six section headers, the run
    metadata (Pipeline_Version, total/eligible cell counts), the
    Preliminary_Disclaimer, the Analysis_Resolution, and a CRS transform-log
    line (Requirements 7.2, 7.3, 7.5, 7.6).
  - ``write_report`` atomically writes the exact rendered text to a file
    (Requirement 7.7).
  - A forced write failure leaves any pre-existing report/sidecar UNMODIFIED
    and raises — the atomic-write discipline never leaves a partial output
    (Requirement 7.9).
  - ``build_sidecar`` / ``write_sidecar`` produce atomic JSON labelled a
    DERIVED PRODUCT (``product_type == "derived"``) including the
    Known_Wind_Farm_Comparison table (Requirements 7.8, 10.2).

The synthetic check results are produced by running the REAL check functions
over small synthetic frames — the same construction the sibling Property 11
test (``test_sanity_outcomes_p11.py``) uses — so the results fed to the
renderer are genuine, not hand-mocked. This keeps the test honest: it exercises
the renderer/writer against the actual structured results the pipeline builds.

This file does NOT test provenance (``record_provenance``, task 11.2) and only
imports/uses the render/write functions, per the task note.
"""

import json

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point, box

from pipeline.common.geo import banner
from pipeline.sanity import config
from pipeline.sanity.checks import (
    check_distribution,
    check_exclusions,
    check_known_wind_farms,
    check_spot_values,
    select_spot_cells,
)
from pipeline.sanity.geo import CrsTransform
from pipeline.sanity.issues import collect_issues
from pipeline.sanity.report import (
    RunMetadata,
    SanityResults,
    build_sidecar,
    render_report,
    write_report,
    write_sidecar,
)

STORAGE_CRS = config.STORAGE_CRS  # "EPSG:4326"
CONTAINMENT_CRS = config.CONTAINMENT_CRS  # "EPSG:3577"

# Grid origin inside the EPSG:3577 (Australian Albers) valid extent so the
# EPSG:4326 -> EPSG:3577 reprojection is well-defined; 0.1 deg square cells keep
# interior points unambiguous after reprojection (mirrors the P11 test).
ORIGIN_LON = 149.0
ORIGIN_LAT = -33.0
CELL_DEG = 0.1

_CELL_ID = config.REQUIRED_SCORE_COLUMNS[0]  # "cell_id"
_SCORE = config.REQUIRED_SCORE_COLUMNS[1]  # "suitability_score"
_RANK = config.REQUIRED_SCORE_COLUMNS[2]  # "rank"
_NAME = config.REQUIRED_WIND_GENERATOR_ATTR  # "name"
_INT_CELL_ID = config.REQUIRED_INTEGRATED_COLUMNS[0]  # "cell_id"
_INT_WIND_SPEED = config.REQUIRED_INTEGRATED_COLUMNS[1]  # "wind_speed"
_INT_SLOPE = config.REQUIRED_INTEGRATED_COLUMNS[2]  # "slope_deg"
_INT_DIST_TX = config.REQUIRED_INTEGRATED_COLUMNS[3]  # "dist_transmission_km"
_INT_PROTECTED = config.REQUIRED_INTEGRATED_COLUMNS[4]  # "protected_area"
_INT_ELIGIBLE = config.REQUIRED_INTEGRATED_COLUMNS[5]  # "eligible"


def _cell_id(col: int, row: int) -> str:
    return f"c{col}_{row}"


def _make_grid(n_cols: int, n_rows: int) -> gpd.GeoDataFrame:
    """A rectangular block of adjacent square cells with centroids and ids."""
    cell_ids = []
    geoms = []
    lats = []
    lons = []
    for row in range(n_rows):
        for col in range(n_cols):
            minx = ORIGIN_LON + col * CELL_DEG
            miny = ORIGIN_LAT + row * CELL_DEG
            cell_ids.append(_cell_id(col, row))
            geoms.append(box(minx, miny, minx + CELL_DEG, miny + CELL_DEG))
            lons.append(minx + 0.5 * CELL_DEG)
            lats.append(miny + 0.5 * CELL_DEG)
    return gpd.GeoDataFrame(
        {"cell_id": cell_ids, "centroid_lat": lats, "centroid_lon": lons},
        geometry=geoms,
        crs=STORAGE_CRS,
    )


def _interior_point(col: int, row: int) -> Point:
    """A point at the centre of cell ``(col, row)`` — unambiguously interior."""
    minx = ORIGIN_LON + col * CELL_DEG
    miny = ORIGIN_LAT + row * CELL_DEG
    return Point(minx + 0.5 * CELL_DEG, miny + 0.5 * CELL_DEG)


def _build_synthetic_results() -> tuple[SanityResults, RunMetadata]:
    """Run the real four checks over small synthetic frames and assemble the
    aggregate :class:`SanityResults` + :class:`RunMetadata` the renderer consumes.

    The frames are laid out so every section has content to render: eligible
    and excluded cells (so the distribution and percentile are well-defined),
    several wind-farm points at known cells, the documented landmarks located to
    their own excluded cells, and a deterministic spot-cell sample.
    """
    n_cols, n_rows = 4, 4
    n_cells = n_cols * n_rows
    all_cells = [
        _cell_id(col, row) for row in range(n_rows) for col in range(n_cols)
    ]
    grid = _make_grid(n_cols, n_rows)

    # --- Scored_Table: first 12 cells eligible with a spread of scores; the
    #     final 4 excluded (null score/rank). A spread avoids degenerate
    #     clustering so Check 4 has a non-trivial distribution. ---
    scores = []
    ranks = []
    winds = []
    slopes = []
    dists = []
    protecteds = []
    eligibles = []
    rank_counter = 1
    for i in range(n_cells):
        if i < 12:
            score = i / 20.0  # 0.00 .. 0.55, well spread
            scores.append(score)
            ranks.append(rank_counter)
            rank_counter += 1
            # wind_speed correlated with score so the correlation is positive.
            winds.append(6.0 + score * 4.0)
            slopes.append(2.0 + i * 0.1)
            dists.append(10.0 + i)
            protecteds.append(False)
            eligibles.append(True)
        else:
            scores.append(np.nan)
            ranks.append(np.nan)
            winds.append(np.nan)
            slopes.append(np.nan)
            dists.append(np.nan)
            protecteds.append(True)
            eligibles.append(False)

    scored = pd.DataFrame({_CELL_ID: all_cells, _SCORE: scores, _RANK: ranks})
    integrated = pd.DataFrame(
        {
            _INT_CELL_ID: all_cells,
            _INT_WIND_SPEED: winds,
            _INT_SLOPE: slopes,
            _INT_DIST_TX: dists,
            _INT_PROTECTED: protecteds,
            _INT_ELIGIBLE: eligibles,
        }
    )

    # --- Wind_Generators: three farms at known interior (eligible) cells. ---
    wind_generators = gpd.GeoDataFrame(
        {_NAME: ["Alpha WF", "Bravo WF", "Charlie WF"]},
        geometry=[_interior_point(0, 0), _interior_point(1, 0), _interior_point(2, 0)],
        crs=STORAGE_CRS,
    )

    transform_log: list[CrsTransform] = []

    # Check 1 — Known Wind Farm Comparison.
    wf_result = check_known_wind_farms(
        wind_generators, grid, scored, CONTAINMENT_CRS, transform_log
    )

    # Check 2 — Exclusion Validation: give each documented landmark its own
    # small excluded cell so the assertions have something to locate to.
    _HALF = 0.02
    lm_ids = []
    lm_geoms = []
    lm_scored_rows = []
    lm_integrated_rows = []
    for idx, lm in enumerate(config.LANDMARKS):
        cid = f"landmark_cell_{idx}"
        lm_ids.append(cid)
        lm_geoms.append(
            box(lm.lon - _HALF, lm.lat - _HALF, lm.lon + _HALF, lm.lat + _HALF)
        )
        lm_scored_rows.append(
            {"cell_id": cid, "suitability_score": None, "rank": None}
        )
        lm_integrated_rows.append({"cell_id": cid, "eligible": False})
    lm_grid = gpd.GeoDataFrame(
        {"cell_id": lm_ids}, geometry=lm_geoms, crs=STORAGE_CRS
    )
    lm_scored = pd.DataFrame(
        lm_scored_rows, columns=["cell_id", "suitability_score", "rank"]
    )
    lm_integrated = pd.DataFrame(
        lm_integrated_rows, columns=["cell_id", "eligible"]
    )
    ex_result = check_exclusions(
        config.LANDMARKS,
        lm_grid,
        lm_scored,
        lm_integrated,
        CONTAINMENT_CRS,
        transform_log,
    )

    # Check 3 — Feature-Value Spot-Checks over the eligible population, joined
    # to the grid so centroids are available.
    eligible = scored[scored[_SCORE].notna() & scored[_RANK].notna()].copy()
    eligible = eligible.merge(
        grid[["cell_id", "centroid_lat", "centroid_lon"]],
        on="cell_id",
        how="left",
    )
    spot = select_spot_cells(eligible, config.SPOT_CHECK_MIN)
    spot_result = check_spot_values(spot, integrated)

    # Check 4 — Score-Distribution Plausibility (needs wind_speed joined in).
    eligible_for_dist = eligible.merge(
        integrated[[_INT_CELL_ID, _INT_WIND_SPEED]],
        left_on="cell_id",
        right_on=_INT_CELL_ID,
        how="left",
    )
    dist_result = check_distribution(eligible_for_dist)

    issues = collect_issues(wf_result, ex_result, spot_result, dist_result)

    results = SanityResults(
        wind_farms=wf_result,
        exclusions=ex_result,
        spot_values=spot_result,
        distribution=dist_result,
        issues=issues,
        transform_log=transform_log,
    )
    meta = RunMetadata(
        run_timestamp="2026-01-15T00:00:00Z",
        pipeline_version="test-pipeline-v1.2.3",
        n_cells=n_cells,
        n_eligible=int(eligible.shape[0]),
        resolved_shortlist_path="DATA/shortlist/sprint1_shortlist_2026-01-15.geojson",
    )
    return results, meta


@pytest.fixture(scope="module")
def synthetic():
    """Genuine (results, meta) built from the real checks, shared read-only."""
    return _build_synthetic_results()


# ===========================================================================
# render_report — banner, six sections, metadata, disclaimers, transform log
# ===========================================================================


def test_render_report_is_banner_stamped(synthetic):
    """The rendered report carries the common.geo do-not-edit banner (7.7)."""
    results, meta = synthetic
    text = render_report(results, meta)
    # The banner is stage-specific; assert its exact wording appears verbatim.
    assert banner(config.STAGE_NAME).strip() in text
    assert "Do not edit by hand." in text


def test_render_report_contains_all_six_sections(synthetic):
    """All six numbered section headers appear, in order (7.2)."""
    results, meta = synthetic
    text = render_report(results, meta)

    expected_headers = [
        "## 1. Known Wind Farm Comparison",
        "## 2. Exclusion Validation",
        "## 3. Feature Value Spot-Checks",
        "## 4. Score Distribution",
        "## 5. Issues for Sprint 2",
        "## 6. Conclusion",
    ]
    positions = []
    for header in expected_headers:
        assert header in text, f"missing section header: {header!r}"
        positions.append(text.index(header))
    # The six sections appear in the required order (7.2).
    assert positions == sorted(positions), "section headers are out of order"


def test_render_report_contains_run_metadata(synthetic):
    """Run metadata — pipeline version, total + eligible cell counts (7.3)."""
    results, meta = synthetic
    text = render_report(results, meta)

    assert meta.pipeline_version in text
    assert meta.run_timestamp in text
    assert meta.resolved_shortlist_path in text
    # Cell counts are rendered with thousands separators (f"{n:,}").
    assert f"{meta.n_cells:,}" in text
    assert f"{meta.n_eligible:,}" in text


def test_render_report_contains_disclaimer_and_resolution(synthetic):
    """The Preliminary_Disclaimer and Analysis_Resolution appear (7.5, 7.6)."""
    results, meta = synthetic
    text = render_report(results, meta)

    assert config.PRELIMINARY_DISCLAIMER in text
    assert config.ANALYSIS_RESOLUTION in text


def test_render_report_contains_transform_log_line(synthetic):
    """A CRS transform-log line is rendered verbatim from the log (2.2, 3.5)."""
    results, meta = synthetic
    text = render_report(results, meta)

    assert "Transform log:" in text
    # The transform log was populated by the containment checks; every recorded
    # EPSG:4326 -> EPSG:3577 transform must be rendered.
    assert results.transform_log, "the synthetic run should record transforms"
    for transform in results.transform_log:
        assert transform.source in text
        assert transform.target in text
    # The single explicit containment CRS must be named (never silently assumed).
    assert CONTAINMENT_CRS in text


def test_render_report_ends_with_newline(synthetic):
    """The rendered report ends in a single trailing newline (clean file)."""
    results, meta = synthetic
    text = render_report(results, meta)
    assert text.endswith("\n")
    assert not text.endswith("\n\n")


# ===========================================================================
# write_report — atomic write of the exact text
# ===========================================================================


def test_write_report_writes_exact_text(tmp_path, synthetic):
    """write_report writes the rendered text byte-for-byte to the path (7.7)."""
    results, meta = synthetic
    text = render_report(results, meta)
    target = tmp_path / "sprint1_validation_report.md"

    write_report(text, path=target)

    assert target.exists()
    assert target.read_text() == text
    # No stray tmp file is left behind by the atomic write.
    assert not (tmp_path / "sprint1_validation_report.md.tmp").exists()


def test_write_report_creates_parent_dir(tmp_path, synthetic):
    """The atomic writer creates missing parent directories (7.7)."""
    results, meta = synthetic
    text = render_report(results, meta)
    target = tmp_path / "nested" / "dir" / "report.md"

    write_report(text, path=target)

    assert target.exists()
    assert target.read_text() == text


# ===========================================================================
# Atomicity — a forced write failure leaves any pre-existing output untouched
# ===========================================================================


def test_write_report_failure_leaves_existing_report_unmodified(
    tmp_path, monkeypatch, synthetic
):
    """A forced write failure raises and leaves the prior report unchanged (7.9).

    A sentinel report is written first; the atomic text writer is then forced to
    raise. The pre-existing file's content must be byte-for-byte unchanged and
    the error must propagate — never a partial/corrupt overwrite.
    """
    results, meta = synthetic
    target = tmp_path / "sprint1_validation_report.md"
    sentinel = "PRE-EXISTING REPORT CONTENT — MUST NOT BE OVERWRITTEN\n"
    target.write_text(sentinel)

    def _boom(path, text):
        raise OSError("forced write failure")

    # Patch the symbol report.py bound at import time.
    monkeypatch.setattr("pipeline.sanity.report.atomic_write_text", _boom)

    text = render_report(results, meta)
    with pytest.raises(OSError, match="forced write failure"):
        write_report(text, path=target)

    # The pre-existing report is untouched.
    assert target.read_text() == sentinel


def test_write_report_real_atomic_write_failure_preserves_sentinel(
    tmp_path, monkeypatch, synthetic
):
    """Exercise the REAL atomic-write path: a failure during the tmp write leaves
    the pre-existing report unmodified and raises (7.9).

    Rather than replacing the writer wholesale, force the underlying tmp-file
    write to fail (via ``pathlib.Path.write_text``), so the genuine
    ``common.geo.atomic_write_text`` tmp + ``os.replace`` discipline is what
    protects the existing file.
    """
    results, meta = synthetic
    target = tmp_path / "sprint1_validation_report.md"
    sentinel = "SENTINEL REPORT\n"
    target.write_text(sentinel)

    import pathlib

    real_write_text = pathlib.Path.write_text

    def _failing_write_text(self, *args, **kwargs):
        # Fail only for the atomic tmp file so the sentinel setup above works and
        # the real failure happens mid-write.
        if str(self).endswith(".tmp"):
            raise OSError("disk full")
        return real_write_text(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "write_text", _failing_write_text)

    text = render_report(results, meta)
    with pytest.raises(OSError, match="disk full"):
        write_report(text, path=target)

    # os.replace never ran, so the pre-existing report is intact and no tmp file
    # is left behind (atomic_write_text cleans it up in its finally block).
    assert target.read_text() == sentinel
    assert not (tmp_path / "sprint1_validation_report.md.tmp").exists()


# ===========================================================================
# build_sidecar / write_sidecar — atomic JSON labelled a derived product
# ===========================================================================


def test_build_sidecar_is_labelled_derived_product(synthetic):
    """The sidecar payload is labelled a derived product (10.2)."""
    results, meta = synthetic
    payload = build_sidecar(results, meta)

    assert payload["product_type"] == "derived"
    assert payload["stage"] == config.STAGE_NAME
    # A derived product is self-describing about what it is.
    assert "derived" in payload["description"].lower()


def test_build_sidecar_includes_wind_farm_comparison_table(synthetic):
    """The sidecar includes the Known_Wind_Farm_Comparison table (7.8)."""
    results, meta = synthetic
    payload = build_sidecar(results, meta)

    wind_farms = payload["checks"]["known_wind_farm_comparison"]
    assert "table" in wind_farms
    # One row per known wind farm, with the reported columns.
    assert len(wind_farms["table"]) == results.wind_farms.n_known_farms
    assert len(wind_farms["table"]) == 3  # the three synthetic farms
    first = wind_farms["table"][0]
    for key in ("wind_farm", "cell_id", "score", "rank", "percentile", "notes"):
        assert key in first


def test_build_sidecar_records_run_metadata(synthetic):
    """Run metadata travels in the sidecar so it is self-describing (7.3)."""
    results, meta = synthetic
    payload = build_sidecar(results, meta)

    run_meta = payload["run_metadata"]
    assert run_meta["pipeline_version"] == meta.pipeline_version
    assert run_meta["n_cells"] == meta.n_cells
    assert run_meta["n_eligible"] == meta.n_eligible


def test_write_sidecar_writes_atomic_json(tmp_path, synthetic):
    """write_sidecar atomically writes valid, derived-labelled JSON (7.8, 10.2)."""
    results, meta = synthetic
    target = tmp_path / "optmining_validation-results_2026_nsw.json"

    write_sidecar(results, path=target, meta=meta)

    assert target.exists()
    # Round-trips as JSON and carries the derived-product label + wind-farm table.
    loaded = json.loads(target.read_text())
    assert loaded["product_type"] == "derived"
    assert "known_wind_farm_comparison" in loaded["checks"]
    assert loaded["checks"]["known_wind_farm_comparison"]["table"]
    # No stray tmp file is left behind.
    assert not (tmp_path / "optmining_validation-results_2026_nsw.json.tmp").exists()


def test_write_sidecar_failure_leaves_existing_sidecar_unmodified(
    tmp_path, monkeypatch, synthetic
):
    """A forced sidecar write failure raises and leaves the prior sidecar (7.9).

    A sentinel JSON sidecar is written first; the underlying tmp write is forced
    to fail, so the real ``atomic_write_json`` tmp + ``os.replace`` discipline is
    what protects the existing file. The pre-existing content must be unchanged.
    """
    results, meta = synthetic
    target = tmp_path / "optmining_validation-results_2026_nsw.json"
    sentinel = json.dumps({"product_type": "derived", "sentinel": True}) + "\n"
    target.write_text(sentinel)

    import pathlib

    real_write_text = pathlib.Path.write_text

    def _failing_write_text(self, *args, **kwargs):
        if str(self).endswith(".tmp"):
            raise OSError("disk full")
        return real_write_text(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "write_text", _failing_write_text)

    with pytest.raises(OSError, match="disk full"):
        write_sidecar(results, path=target, meta=meta)

    # The pre-existing sidecar is intact and no tmp file remains.
    assert target.read_text() == sentinel
    assert not (tmp_path / "optmining_validation-results_2026_nsw.json.tmp").exists()
