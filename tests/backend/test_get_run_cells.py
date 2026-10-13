"""
Tests for the S2-08/S3-03a ``get_run_cells`` read operation
(``pipeline.service.results``) and its ``GET /runs/{run_id}/cells`` transport.

`get_run_cells` reads a materialised Run's S2-05 Scored_Table and returns a
GeoJSON ``CellCollection`` — one Point Feature per cell (eligible AND excluded
alike), carrying the engine's own ``centroid_lon`` / ``centroid_lat`` through
VERBATIM in EPSG:4326 (Requirement 1.7). It performs no scoring, ranking or
reprojection and does not join the integrated table — the no-recompute guarantee
(CONTRACT.md §1, §4.7).

Two layers of coverage:

* Unit tests over a hand-written Scored_Table materialised into a temp Run
  directory — deterministic, no built dataset required. These pin the
  FeatureCollection shape, the ``[lon, lat]`` coordinate order (asserted against
  the fixture frame's OWN centroid column values, never a hand-typed literal),
  the eligible == (score AND rank both non-null) rule, the set-equality with
  ``get_ranked_results`` (CONTRACT.md §7 P1), and the honest-failure behaviour.
* A FastAPI ``TestClient`` transport test confirming the endpoint returns a
  valid FeatureCollection (200) and maps an unknown Run to 404.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import geopandas as gpd
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Point

from pipeline.scoring import config as scoring_config
from pipeline.service import config as service_config
from pipeline.service import get_ranked_results, get_run_cells
from pipeline.service.models import CellCollection
from pipeline.service.runs import EngineOutputError, RunNotFoundError

LAT_COL, LON_COL = scoring_config.CARRIED_COLUMNS  # ("centroid_lat", "centroid_lon")


@pytest.fixture
def runs_store(tmp_path, monkeypatch):
    """Redirect the per-Run materialisation store to a temp directory."""
    store = tmp_path / "runs"
    monkeypatch.setattr(service_config, "RUNS_DIR", store)
    return store


def _materialise_cells_run(store: Path, run_id: str, rows: list[dict]) -> None:
    """
    Write a minimal Scored_Table + manifest for a fake Run so the cells read
    path can be exercised without running the engine.

    Each row dict carries at least `cell_id`, `suitability_score`, `rank`,
    `centroid_lat` and `centroid_lon`; an excluded cell uses None for score and
    rank. The GeoPackage geometry is a throwaway Point distinct from the carried
    centroid columns — the operation must read the CENTROID COLUMNS, never the
    geometry.
    """
    target = store / run_id
    target.mkdir(parents=True, exist_ok=True)

    frame = gpd.GeoDataFrame(
        rows,
        # A geometry deliberately offset from the centroid columns so a test
        # that read the geometry instead of the columns would fail.
        geometry=[Point(0.0, 0.0) for _ in rows],
        crs=scoring_config.STORAGE_CRS,
    )
    gpkg_path = target / service_config.SCORED_GPKG_FILENAME
    frame.to_file(gpkg_path, driver="GPKG", layer=service_config.SCORED_LAYER)

    manifest = {"run_id": run_id, "weights_id": run_id, "scenario": None}
    (target / service_config.RUN_MANIFEST_FILENAME).write_text(
        json.dumps(manifest) + "\n", encoding="utf-8"
    )


# --------------------------------------------------------------------------- #
# FeatureCollection shape + verbatim centroids over a hand-written table.      #
# --------------------------------------------------------------------------- #


def test_returns_feature_collection_one_feature_per_row(runs_store):
    _materialise_cells_run(
        runs_store,
        "runcells00000001",
        [
            {"cell_id": "c1", "suitability_score": 0.9, "rank": 1,
             LAT_COL: -30.1, LON_COL: 150.2},
            {"cell_id": "c2", "suitability_score": 0.4, "rank": 2,
             LAT_COL: -31.3, LON_COL: 151.4},
        ],
    )

    result = get_run_cells("runcells00000001")

    assert isinstance(result, CellCollection)
    payload = result.to_dict()
    assert payload["type"] == "FeatureCollection"
    assert payload["run_id"] == "runcells00000001"
    # One Feature per Scored_Table row, in the table's own row order.
    assert len(payload["features"]) == 2
    assert [f["properties"]["cell_id"] for f in payload["features"]] == ["c1", "c2"]
    assert all(f["type"] == "Feature" for f in payload["features"])
    assert all(f["geometry"]["type"] == "Point" for f in payload["features"])


def test_coordinates_are_lon_lat_from_the_fixture_columns(runs_store):
    """`[lon, lat]` order, asserted against the frame's OWN centroid columns."""
    rows = [
        {"cell_id": "c1", "suitability_score": 0.9, "rank": 1,
         LAT_COL: -30.123, LON_COL: 150.987},
    ]
    _materialise_cells_run(runs_store, "runcellsorder001", rows)

    feature = get_run_cells("runcellsorder001").to_dict()["features"][0]

    # The coordinates come from the fixture's own column values — never a
    # hand-typed float — and are ordered [lon, lat] per GeoJSON.
    expected_lon = rows[0][LON_COL]
    expected_lat = rows[0][LAT_COL]
    assert feature["geometry"]["coordinates"] == [expected_lon, expected_lat]


def test_eligible_true_only_when_both_score_and_rank_present(runs_store):
    _materialise_cells_run(
        runs_store,
        "runcellselig0001",
        [
            {"cell_id": "cBoth", "suitability_score": 0.8, "rank": 1,
             LAT_COL: -30.0, LON_COL: 150.0},
            {"cell_id": "cScoreOnly", "suitability_score": 0.5, "rank": None,
             LAT_COL: -30.1, LON_COL: 150.1},
            {"cell_id": "cRankOnly", "suitability_score": None, "rank": 2,
             LAT_COL: -30.2, LON_COL: 150.2},
            {"cell_id": "cNeither", "suitability_score": None, "rank": None,
             LAT_COL: -30.3, LON_COL: 150.3},
        ],
    )

    by_cell = {
        f["properties"]["cell_id"]: f["properties"]
        for f in get_run_cells("runcellselig0001").to_dict()["features"]
    }

    # eligible == true EXACTLY when both score and rank are non-null.
    assert by_cell["cBoth"]["eligible"] is True
    # A non-null score but null rank (and vice versa) is eligible:false.
    assert by_cell["cScoreOnly"]["eligible"] is False
    assert by_cell["cRankOnly"]["eligible"] is False
    assert by_cell["cNeither"]["eligible"] is False


def test_excluded_rows_carry_null_score_and_rank(runs_store):
    _materialise_cells_run(
        runs_store,
        "runcellsexcl0001",
        [
            {"cell_id": "c1", "suitability_score": 0.9, "rank": 1,
             LAT_COL: -30.0, LON_COL: 150.0},
            {"cell_id": "cX", "suitability_score": None, "rank": None,
             LAT_COL: -31.0, LON_COL: 151.0},
        ],
    )

    by_cell = {
        f["properties"]["cell_id"]: f["properties"]
        for f in get_run_cells("runcellsexcl0001").to_dict()["features"]
    }

    # The excluded cell is still a Feature, but carries null score/rank.
    assert by_cell["cX"]["suitability_score"] is None
    assert by_cell["cX"]["rank"] is None
    assert by_cell["cX"]["eligible"] is False
    # The eligible cell carries its score/rank verbatim.
    assert by_cell["c1"]["suitability_score"] == 0.9
    assert by_cell["c1"]["rank"] == 1


def test_eligible_cell_id_set_equals_ranked_results(runs_store):
    """CONTRACT.md §7 P1 — the map-eligible set equals get_ranked_results'."""
    _materialise_cells_run(
        runs_store,
        "runcellsp1000001",
        [
            {"cell_id": "c2", "suitability_score": 0.4, "rank": 2,
             LAT_COL: -31.0, LON_COL: 151.0},
            {"cell_id": "c1", "suitability_score": 0.9, "rank": 1,
             LAT_COL: -30.0, LON_COL: 150.0},
            {"cell_id": "cX", "suitability_score": None, "rank": None,
             LAT_COL: -32.0, LON_COL: 152.0},
        ],
    )

    eligible_from_cells = {
        f["properties"]["cell_id"]
        for f in get_run_cells("runcellsp1000001").to_dict()["features"]
        if f["properties"]["eligible"]
    }
    ranked_set = {r.cell_id for r in get_ranked_results("runcellsp1000001")}

    assert eligible_from_cells == ranked_set == {"c1", "c2"}


def test_empty_table_returns_empty_but_valid_collection(runs_store):
    _materialise_cells_run(
        runs_store,
        "runcellsempty001",
        [
            {"cell_id": "cX", "suitability_score": None, "rank": None,
             LAT_COL: -30.0, LON_COL: 150.0},
        ],
    )

    payload = get_run_cells("runcellsempty001").to_dict()

    # One excluded cell is still a Feature — the collection is never "empty" of
    # excluded cells; but the eligible subset is empty-but-valid, not an error.
    assert payload["type"] == "FeatureCollection"
    assert [f["properties"]["eligible"] for f in payload["features"]] == [False]


# --------------------------------------------------------------------------- #
# Honest failure (Requirement 7.1, 7.3).                                      #
# --------------------------------------------------------------------------- #


def test_missing_run_raises_naming_the_run(runs_store):
    with pytest.raises(RunNotFoundError, match="nope000000000000"):
        get_run_cells("nope000000000000")


def test_missing_scored_table_raises_naming_the_input(runs_store):
    target = runs_store / "runcellsnotable0"
    target.mkdir(parents=True, exist_ok=True)
    manifest = {"run_id": "runcellsnotable0", "weights_id": "x", "scenario": None}
    (target / service_config.RUN_MANIFEST_FILENAME).write_text(
        json.dumps(manifest) + "\n", encoding="utf-8"
    )

    with pytest.raises(EngineOutputError, match="Scored_Table is missing"):
        get_run_cells("runcellsnotable0")


def test_dropped_centroid_column_raises_naming_it(runs_store):
    """A Scored_Table missing a centroid column -> EngineOutputError naming it."""
    # Write a table that carries centroid_lat but NOT centroid_lon.
    target = runs_store / "runcellsnocol001"
    target.mkdir(parents=True, exist_ok=True)
    frame = gpd.GeoDataFrame(
        [{"cell_id": "c1", "suitability_score": 0.9, "rank": 1, LAT_COL: -30.0}],
        geometry=[Point(150.0, -30.0)],
        crs=scoring_config.STORAGE_CRS,
    )
    frame.to_file(
        target / service_config.SCORED_GPKG_FILENAME,
        driver="GPKG",
        layer=service_config.SCORED_LAYER,
    )
    manifest = {"run_id": "runcellsnocol001", "weights_id": "x", "scenario": None}
    (target / service_config.RUN_MANIFEST_FILENAME).write_text(
        json.dumps(manifest) + "\n", encoding="utf-8"
    )

    with pytest.raises(EngineOutputError, match=LON_COL):
        get_run_cells("runcellsnocol001")


# --------------------------------------------------------------------------- #
# Transport — GET /runs/{run_id}/cells via FastAPI TestClient.                #
#                                                                             #
# app/api/app.py is launched with app/api/ as the working dir, so it does     #
# sibling imports (`import settings`, `from models import ...`). We reproduce  #
# that by putting app/api/ on sys.path before importing it, mirroring the     #
# other backend transport tests.                                              #
# --------------------------------------------------------------------------- #

REPO_ROOT = Path(__file__).resolve().parents[2]
API_DIR = REPO_ROOT / "app" / "api"


def _load_app_module():
    api_dir = str(API_DIR)
    if api_dir not in sys.path:
        sys.path.insert(0, api_dir)
    if "app" in sys.modules:
        return importlib.reload(sys.modules["app"])
    return importlib.import_module("app")


def test_endpoint_returns_200_with_valid_feature_collection(runs_store, monkeypatch):
    _materialise_cells_run(
        runs_store,
        "runcellshttp0001",
        [
            {"cell_id": "c1", "suitability_score": 0.9, "rank": 1,
             LAT_COL: -30.0, LON_COL: 150.0},
            {"cell_id": "cX", "suitability_score": None, "rank": None,
             LAT_COL: -31.0, LON_COL: 151.0},
        ],
    )

    app_module = _load_app_module()
    with TestClient(app_module.app) as client:
        response = client.get("/runs/runcellshttp0001/cells")

    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert body["run_id"] == "runcellshttp0001"
    assert len(body["features"]) == 2
    first = body["features"][0]
    assert first["type"] == "Feature"
    assert first["geometry"]["type"] == "Point"
    assert first["geometry"]["coordinates"] == [150.0, -30.0]


def test_endpoint_unknown_run_returns_404(runs_store):
    app_module = _load_app_module()
    with TestClient(app_module.app) as client:
        response = client.get("/runs/nope000000000000/cells")

    assert response.status_code == 404
