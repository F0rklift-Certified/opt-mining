"""
Tests for the self-heal path in ``pipeline.service.runs.materialise_run``.

Root cause these guard (the HTTP 503 the user hit): the Decision-Service writes
each Run to ``DATA/service/runs/{run_id}/`` (a ``.gpkg`` + ``.csv`` + run.json).
When the run store is momentarily read-only, a GeoPackage write can fail PARTWAY
— leaving a TRUNCATED, unreadable ``.gpkg`` on disk while run.json still got
written. The idempotency guard used to reuse a Run whenever its manifest + gpkg
merely EXISTED, so that corrupt artefact wedged every later read behind an
honest-but-permanent 503 and the Run was never re-materialised.

``materialise_run`` now reuses a Run ONLY when its Scored_Table is actually
READABLE (probed via the read path's own ``load_scored_table``). A corrupt gpkg
is treated as a cache MISS and re-materialised over (the writer's tmp-sibling +
``os.replace`` makes the overwrite safe); a healthy Run is still reused without
re-scoring.

The engine needs the integrated feature table, so — like the other fast backend
unit tests — these build a tiny self-contained integrated table in a temp dir
and point ``service.config.INTEGRATED_PATH`` / ``RUNS_DIR`` at temp locations.
No Docker and no built DATA output is required.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Point

from pipeline.scoring import config as scoring_config
from pipeline.service import config as service_config
from pipeline.service import runs as runs_module
from pipeline.service.runs import load_scored_table, materialise_run

LAT_COL, LON_COL = scoring_config.CARRIED_COLUMNS  # ("centroid_lat", "centroid_lon")

# A minimal explicit weights request (same shape scoring_weights.yaml / the
# RunRequest body use). Two criteria keep the engine run tiny while exercising
# the real score/rank/write path.
WEIGHTS_REQUEST = {
    "criteria": [
        {
            "feature": "wind_speed",
            "weight": 0.6,
            "direction": scoring_config.HIGHER_IS_BETTER,
            "rationale": "resource quality",
        },
        {
            "feature": "dist_transmission_km",
            "weight": 0.4,
            "direction": scoring_config.LOWER_IS_BETTER,
            "rationale": "connection distance",
        },
    ]
}


def _write_integrated_table(path: Path) -> None:
    """Materialise a tiny valid S1-08 integrated feature table for the engine."""
    frame = gpd.GeoDataFrame(
        {
            scoring_config.CELL_ID_COLUMN: ["A", "B", "C", "X"],
            "wind_speed": [10.0, 0.0, 5.0, 999.0],
            "dist_transmission_km": [10.0, 0.0, 5.0, -999.0],
            scoring_config.ELIGIBLE_COLUMN: [True, True, True, False],
            scoring_config.CONFIDENCE_COLUMN: ["high", "high", "high", "high"],
            LAT_COL: [-30.0, -31.0, -32.0, -33.0],
            LON_COL: [150.0, 151.0, 152.0, 153.0],
            # S2-06b inputs: each Run now materialises its own explanations.
            "triggered_rules": [None, None, None, "protected_area"],
            "exclusion_reason": [None, None, None, "Inside a protected area"],
            "confidence_notes": ["", "", "", ""],
        },
        geometry=[Point(lon, lat) for lon, lat in
                  zip([150.0, 151.0, 152.0, 153.0], [-30.0, -31.0, -32.0, -33.0])],
        crs=scoring_config.STORAGE_CRS,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_file(path, driver="GPKG", layer=scoring_config.INTEGRATED_LAYER)


@pytest.fixture
def engine_store(tmp_path, monkeypatch):
    """
    Point the engine input and the per-Run store at temp locations.

    Returns the runs store directory so a test can inspect/corrupt a Run's
    materialised artefacts.
    """
    integrated_path = tmp_path / "integrated.gpkg"
    _write_integrated_table(integrated_path)
    monkeypatch.setattr(service_config, "INTEGRATED_PATH", integrated_path)

    store = tmp_path / "runs"
    monkeypatch.setattr(service_config, "RUNS_DIR", store)
    return store


def test_corrupt_scored_table_is_re_materialised_not_reused(engine_store):
    """
    A manifest + gpkg both present but the gpkg TRUNCATED/unreadable must be
    treated as a cache miss: the Run self-heals into a VALID, readable table.
    """
    # First materialisation — healthy.
    handle = materialise_run(weights=WEIGHTS_REQUEST)
    gpkg_path = engine_store / handle.run_id / service_config.SCORED_GPKG_FILENAME
    manifest_path = engine_store / handle.run_id / service_config.RUN_MANIFEST_FILENAME
    assert gpkg_path.exists() and manifest_path.exists()
    # Confirm it is readable to begin with.
    assert len(load_scored_table(handle.run_id)) == 4

    # Simulate the partial write: truncate the .gpkg to a few bytes so it is no
    # longer a valid GeoPackage, leaving run.json intact (the exact on-disk
    # state the read-only-mount bug produced).
    gpkg_path.write_bytes(b"SQLite format 3\x00corrupt")
    with pytest.raises(Exception):
        load_scored_table(handle.run_id)

    # Same request again: must RE-MATERIALISE over the corrupt artefact rather
    # than reuse it, yielding a valid, readable Scored_Table.
    healed = materialise_run(weights=WEIGHTS_REQUEST)
    assert healed.run_id == handle.run_id
    table = load_scored_table(healed.run_id)
    assert len(table) == 4
    assert scoring_config.SCORE_COLUMN in table.columns


def test_healthy_run_is_reused_without_re_scoring(engine_store, monkeypatch):
    """
    A valid existing Run is still reused: the engine/writer are NOT invoked a
    second time, and the materialised file is left byte-for-byte intact.
    """
    handle = materialise_run(weights=WEIGHTS_REQUEST)
    gpkg_path = engine_store / handle.run_id / service_config.SCORED_GPKG_FILENAME
    original_bytes = gpkg_path.read_bytes()

    # If reuse works, _materialise must never be called on the second request.
    def _fail_if_called(*args, **kwargs):  # pragma: no cover - must not run
        raise AssertionError("_materialise was called for a healthy existing Run")

    monkeypatch.setattr(runs_module, "_materialise", _fail_if_called)

    reused = materialise_run(weights=WEIGHTS_REQUEST)
    assert reused.run_id == handle.run_id
    # The healthy artefact is left untouched (not rewritten).
    assert gpkg_path.read_bytes() == original_bytes


def test_run_json_records_a_project_relative_integrated_path(engine_store, monkeypatch):
    """QA F-26: run.json must not pin the host's absolute path."""
    monkeypatch.setattr(service_config, "PROJECT_ROOT", engine_store.parent)
    handle = materialise_run(weights=WEIGHTS_REQUEST)
    manifest = runs_module.load_run_manifest(handle.run_id)
    assert manifest["integrated_path"] == "integrated.gpkg"
    assert len(runs_module.load_integrated_table(handle.run_id)) == 4


def test_stale_absolute_integrated_path_falls_back_to_current_table(engine_store):
    """
    QA F-26: a Run written elsewhere (host vs container) records an absolute
    path that does not exist here; site detail must read the current table
    (the sha256 guard still rejects different content) instead of a 503.
    """
    import json

    handle = materialise_run(weights=WEIGHTS_REQUEST)
    manifest_path = engine_store / handle.run_id / service_config.RUN_MANIFEST_FILENAME
    manifest = json.loads(manifest_path.read_text())
    manifest["integrated_path"] = "/Users/someone-else/opt-mining/DATA/integration/x.gpkg"
    manifest_path.write_text(json.dumps(manifest))

    assert len(runs_module.load_integrated_table(handle.run_id)) == 4

