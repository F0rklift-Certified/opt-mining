"""
Unit tests for the S3-08 READ-ONLY sanity-engine extensions (FEAT-001).

Covers the additive engine fields the S3-08 ticket adds to the sanity stage, all
of which must be surfaced in the sidecar for the service/panel to read:

  - Check 1 (``check_known_wind_farms``): the top-ranked-band framing
    (``n_in_top_band`` / ``top_band_n`` / ``top_band_outcome``) — in band, out of
    band, a farm on an excluded/null-rank cell NOT counted in band, and an empty
    population.
  - Check 4 (``check_distribution``): the REZ reference outcome's three states —
    (1) REZ column not joined -> honest FAIL, observed "REZ column not joined";
    (2) joined but no top cell inside a REZ -> observed "0 of N ..."; (3) some
    top cells inside a REZ -> real labels and a real proportion.
  - ``run._enrich_eligible``: the LEFT join of rez_name / inside_rez onto a tiny
    eligible/integrated pair.
  - The loader's fail-fast ValueError (NOT a MissingColumnError type) when the
    integrated frame lacks the now-required ``rez_name`` column, naming the
    column and the Integrated_Feature_Table input.
  - A one-line index-pin on ``config.REQUIRED_INTEGRATED_COLUMNS`` so a future
    insert that shifts the positional indices Checks 2/3 bind to fails loudly.

These assert the engine output FEAT-002 must read; the exact sidecar JSON paths
are regenerated and asserted by the run/verification steps.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Point, box

from pipeline.sanity import config
from pipeline.sanity.checks import check_distribution, check_known_wind_farms
from pipeline.sanity.geo import CrsTransform
from pipeline.sanity.load import SanityInputs, load_inputs
from pipeline.sanity.run import _enrich_eligible

STORAGE_CRS = "EPSG:4326"
CONTAINMENT_CRS = "EPSG:3577"

ORIGIN_LON = 149.0
ORIGIN_LAT = -33.0
CELL_DEG = 0.1

_SCORE = config.REQUIRED_SCORE_COLUMNS[1]  # "suitability_score"
_RANK = config.REQUIRED_SCORE_COLUMNS[2]  # "rank"
_NAME = config.REQUIRED_WIND_GENERATOR_ATTR  # "feature_name"


# ===========================================================================
# config: REQUIRED_INTEGRATED_COLUMNS index pinning (design §2, Finding 3)
# ===========================================================================


def test_required_integrated_columns_indices_are_pinned():
    """Checks 2/3 read this tuple POSITIONALLY; rez_name is appended at the TAIL
    (index 6) so the existing indices never shift onto the wrong column."""
    cols = config.REQUIRED_INTEGRATED_COLUMNS
    assert cols[0] == "cell_id"
    assert cols[1:5] == ("wind_speed", "slope_deg", "dist_transmission_km", "protected_area")
    assert cols[5] == "eligible"
    assert cols[6] == "rez_name"
    # inside_rez is deliberately NOT required (optional guarded join).
    assert "inside_rez" not in cols


# ===========================================================================
# Check 1 — top-ranked-band framing
# ===========================================================================


def _make_grid(n: int) -> gpd.GeoDataFrame:
    """A horizontal strip of ``n`` adjacent square cells, ids c0..c(n-1)."""
    ids = [f"c{i}" for i in range(n)]
    geoms = [
        box(ORIGIN_LON + i * CELL_DEG, ORIGIN_LAT,
            ORIGIN_LON + (i + 1) * CELL_DEG, ORIGIN_LAT + CELL_DEG)
        for i in range(n)
    ]
    return gpd.GeoDataFrame({"cell_id": ids}, geometry=geoms, crs=STORAGE_CRS)


def _interior_point(i: int) -> Point:
    minx = ORIGIN_LON + i * CELL_DEG
    return Point(minx + 0.5 * CELL_DEG, ORIGIN_LAT + 0.5 * CELL_DEG)


def _wind(names_cells) -> gpd.GeoDataFrame:
    names = [n for n, _ in names_cells]
    geoms = [_interior_point(i) for _, i in names_cells]
    return gpd.GeoDataFrame({_NAME: names}, geometry=geoms, crs=STORAGE_CRS)


def test_check1_farm_inside_top_band_counts():
    """A farm whose cell has rank <= top_band_n is counted in band and, with a
    majority in band, the top_band_outcome passes with an observed value."""
    grid = _make_grid(3)
    scored = pd.DataFrame(
        {"cell_id": ["c0", "c1", "c2"], _SCORE: [0.9, 0.5, 0.1], _RANK: [1, 2, 3]}
    )
    wind = _wind([("f0", 0), ("f1", 1)])  # ranks 1 and 2

    result = check_known_wind_farms(
        wind, grid, scored, CONTAINMENT_CRS, [], top_band_n=5
    )
    assert result.n_in_top_band == 2
    assert result.top_band_n == 5
    assert result.top_band_outcome.passed is True
    assert "2 of 2" in result.top_band_outcome.observed
    assert "rank <= 5" in result.top_band_outcome.observed


def test_check1_farm_outside_top_band_not_counted():
    """A farm whose cell rank exceeds top_band_n is NOT counted in band."""
    grid = _make_grid(3)
    scored = pd.DataFrame(
        {"cell_id": ["c0", "c1", "c2"], _SCORE: [0.9, 0.5, 0.1], _RANK: [1, 2, 3]}
    )
    wind = _wind([("f0", 2)])  # rank 3

    result = check_known_wind_farms(
        wind, grid, scored, CONTAINMENT_CRS, [], top_band_n=2
    )
    assert result.n_in_top_band == 0
    assert result.top_band_outcome.passed is False


def test_check1_farm_on_excluded_cell_never_in_band():
    """A known farm on an excluded/null-rank cell is NOT counted in band even
    though its rank value is null (AC2)."""
    grid = _make_grid(2)
    scored = pd.DataFrame(
        {"cell_id": ["c0", "c1"], _SCORE: [0.9, np.nan], _RANK: [1, np.nan]}
    )
    wind = _wind([("f0", 1)])  # lands on the excluded cell c1

    result = check_known_wind_farms(
        wind, grid, scored, CONTAINMENT_CRS, [], top_band_n=20
    )
    assert result.n_in_top_band == 0
    assert result.top_band_outcome.passed is False
    # The row is recorded honestly with a null rank, never dropped.
    assert result.rows[0].rank is None


def test_check1_empty_population_records_zero_of_zero():
    """With no known farms the top-band outcome records 0 of 0 and does NOT
    pass (nothing to confirm the expectation against)."""
    grid = _make_grid(2)
    scored = pd.DataFrame(
        {"cell_id": ["c0", "c1"], _SCORE: [0.9, 0.5], _RANK: [1, 2]}
    )
    wind = _wind([])  # no farms

    result = check_known_wind_farms(
        wind, grid, scored, CONTAINMENT_CRS, [], top_band_n=20
    )
    assert result.n_known_farms == 0
    assert result.n_in_top_band == 0
    assert result.top_band_outcome.passed is False
    assert "0 of 0" in result.top_band_outcome.observed


# ===========================================================================
# Check 4 — REZ reference outcome, three states
# ===========================================================================


def _eligible_with_rez(n, inside_flags=None, rez_names=None):
    """An eligible frame of ``n`` cells with descending scores (so cell order ==
    top order) plus optional inside_rez / rez_name columns."""
    data = {
        "cell_id": [f"c{i}" for i in range(n)],
        _SCORE: [1.0 - i * (0.5 / max(n, 1)) for i in range(n)],
    }
    if inside_flags is not None:
        data["inside_rez"] = inside_flags
    if rez_names is not None:
        data["rez_name"] = rez_names
    return pd.DataFrame(data)


def test_check4_rez_state1_column_not_joined_is_honest_fail():
    """State 1 — neither rez_name nor inside_rez present: honest FAIL with
    observed 'REZ column not joined', never a silent pass."""
    eligible = _eligible_with_rez(8)  # no REZ columns
    result = check_distribution(eligible)
    assert result.rez_column_joined is False
    assert result.rez_outcome.passed is False
    assert result.rez_outcome.observed == "REZ column not joined"
    assert result.rez_represented == []
    assert any("REZ column not joined" in note for note in result.notes)


def test_check4_rez_state2_joined_none_inside():
    """State 2 — joined but no top cell inside a REZ: observed '0 of N ...',
    distinct wording from state 1, empty label list."""
    n = 8
    eligible = _eligible_with_rez(
        n, inside_flags=[False] * n, rez_names=[None] * n
    )
    result = check_distribution(eligible)
    assert result.rez_column_joined is True
    assert result.n_top_inside_rez == 0
    assert result.rez_represented == []
    assert result.rez_outcome.observed.startswith("0 of ")
    assert "inside a REZ" in result.rez_outcome.observed
    assert any("no top cell is inside a rez" in note.lower() for note in result.notes)


def test_check4_rez_state3_some_inside_real_labels():
    """State 3 — some top cells inside a REZ: real labels and a real proportion,
    computed over the SAME top_cells frame so they agree."""
    n = 8
    inside = [True, True, False, False, False, False, False, False]
    names = ["REZ Alpha", "REZ Beta", None, None, None, None, None, None]
    eligible = _eligible_with_rez(n, inside_flags=inside, rez_names=names)
    result = check_distribution(eligible)
    assert result.rez_column_joined is True
    # top_n_considered is the decile top_cells count, floored at TOP_CELLS_MIN
    # (5) for a tiny population — NOT the full eligible size.
    assert result.top_n_considered == 5
    # The two inside-REZ cells are the highest-scored, so both are in the top 5.
    assert result.n_top_inside_rez == 2
    assert set(result.rez_represented) == {"REZ Alpha", "REZ Beta"}
    # proportion 2/5 == 0.4 >= the 0.25 plausibility bar -> passes.
    assert result.rez_outcome.passed is True
    assert "2 of" in result.rez_outcome.observed


def test_check4_rez_top_n_uses_decile_not_band():
    """The REZ outcome's top_n_considered is the decile top_cells count, floored
    at TOP_CELLS_MIN — NOT config.TOP_RANKED_BAND_N (design §4.3, Finding 2)."""
    n = 100
    inside = [i < 30 for i in range(n)]  # top 30 cells (by score) are inside
    eligible = _eligible_with_rez(
        n, inside_flags=inside, rez_names=[f"REZ {i}" if i < 30 else None for i in range(n)]
    )
    result = check_distribution(eligible)
    # decile of 100 == 10, not TOP_RANKED_BAND_N (20).
    assert result.top_n_considered == 10
    assert result.top_n_considered != config.TOP_RANKED_BAND_N
    # all 10 top cells are inside the REZ -> proportion 1.0, passes.
    assert result.n_top_inside_rez == 10
    assert result.rez_outcome.passed is True


# ===========================================================================
# run._enrich_eligible — the REZ join
# ===========================================================================


def test_enrich_eligible_joins_rez_name_and_inside_rez():
    """_enrich_eligible LEFT-joins both rez_name and inside_rez from the
    integrated frame onto the eligible frame on cell_id, keeping every eligible
    cell and never mutating the input."""
    eligible = pd.DataFrame(
        {"cell_id": ["a", "b", "c"], _SCORE: [0.9, 0.5, 0.1], _RANK: [1, 2, 3]}
    )
    grid = gpd.GeoDataFrame(
        {"cell_id": ["a", "b", "c"], "centroid_lat": [-33.0, -33.1, -33.2],
         "centroid_lon": [149.0, 149.1, 149.2]},
        geometry=[Point(149.0, -33.0), Point(149.1, -33.1), Point(149.2, -33.2)],
        crs=STORAGE_CRS,
    )
    integrated = pd.DataFrame(
        {
            "cell_id": ["a", "b", "c"],
            "wind_speed": [8.0, 7.0, 6.0],
            "rez_name": ["REZ A", None, "REZ C"],
            "inside_rez": [True, False, True],
        }
    )
    before = eligible.copy()
    enriched = _enrich_eligible(eligible, grid, integrated)

    assert list(enriched["cell_id"]) == ["a", "b", "c"]  # LEFT join keeps all
    assert "rez_name" in enriched.columns
    assert "inside_rez" in enriched.columns
    assert list(enriched["rez_name"]) == ["REZ A", None, "REZ C"]
    assert list(enriched["inside_rez"]) == [True, False, True]
    # input never mutated.
    assert "rez_name" not in before.columns
    assert eligible.equals(before)


def test_enrich_eligible_degrades_when_inside_rez_absent():
    """When only rez_name is present (inside_rez absent), the join still works
    and inside_rez is simply not added — the REZ outcome degrades honestly."""
    eligible = pd.DataFrame(
        {"cell_id": ["a", "b"], _SCORE: [0.9, 0.5], _RANK: [1, 2]}
    )
    grid = gpd.GeoDataFrame(
        {"cell_id": ["a", "b"]},
        geometry=[Point(149.0, -33.0), Point(149.1, -33.1)],
        crs=STORAGE_CRS,
    )
    integrated = pd.DataFrame(
        {"cell_id": ["a", "b"], "rez_name": ["REZ A", None]}
    )
    enriched = _enrich_eligible(eligible, grid, integrated)
    assert "rez_name" in enriched.columns
    assert "inside_rez" not in enriched.columns


# ===========================================================================
# Loader fail-fast — missing rez_name raises a plain ValueError (no new type)
# ===========================================================================


def _write_gpkg(path, frame, layer):
    frame.to_file(path, layer=layer, driver="GPKG")
    return path


def _good_frames(tmp_path):
    """Minimal well-formed inputs for the loader, parameterised so a single
    frame can be swapped for a fail-fast test."""
    scored = gpd.GeoDataFrame(
        {"cell_id": ["c0", "c1"], _SCORE: [0.9, 0.5], _RANK: [1, 2]},
        geometry=[Point(149.0, -33.0), Point(149.1, -33.1)],
        crs=STORAGE_CRS,
    )
    integrated = gpd.GeoDataFrame(
        {
            "cell_id": ["c0", "c1"],
            "wind_speed": [8.0, 7.0],
            "slope_deg": [2.0, 3.0],
            "dist_transmission_km": [5.0, 10.0],
            "protected_area": [False, False],
            "eligible": [True, True],
            "rez_name": ["REZ A", None],
        },
        geometry=[Point(149.0, -33.0), Point(149.1, -33.1)],
        crs=STORAGE_CRS,
    )
    grid = gpd.GeoDataFrame(
        {"cell_id": ["c0", "c1"], "centroid_lat": [-33.0, -33.1],
         "centroid_lon": [149.0, 149.1]},
        geometry=[box(149.0, -33.0, 149.05, -32.95), box(149.1, -33.1, 149.15, -33.05)],
        crs=STORAGE_CRS,
    )
    wind = gpd.GeoDataFrame(
        {_NAME: ["farm"]}, geometry=[Point(149.02, -32.97)], crs=STORAGE_CRS
    )
    shortlist = gpd.GeoDataFrame(
        {"cell_id": ["c0"], _SCORE: [0.9], _RANK: [1]},
        geometry=[Point(149.0, -33.0)], crs=STORAGE_CRS,
    )
    sl_path = tmp_path / "sprint1_shortlist_20260101.geojson"
    shortlist.to_file(sl_path, driver="GeoJSON")
    return {
        "scored": _write_gpkg(tmp_path / "scored.gpkg", scored, config.SCORED_LAYER),
        "integrated": integrated,  # written by the caller (may be mutated for failure)
        "grid": _write_gpkg(tmp_path / "grid.gpkg", grid, config.GRID_LAYER),
        "wind": tmp_path / "wind.geojson",
        "shortlist": sl_path,
        "wind_frame": wind,
    }


def test_loader_missing_rez_name_raises_valueerror_naming_column_and_input(tmp_path):
    """A missing rez_name column raises the loader's plain ValueError (there is
    NO MissingColumnError type) naming rez_name and the Integrated_Feature_Table
    input (AC6)."""
    f = _good_frames(tmp_path)
    f["wind_frame"].to_file(f["wind"], driver="GeoJSON")
    bad_integrated = f["integrated"].drop(columns=["rez_name"])
    bad_path = _write_gpkg(tmp_path / "integrated_bad.gpkg", bad_integrated, config.INTEGRATED_LAYER)

    inputs = SanityInputs(
        scored_path=f["scored"],
        shortlist_path=f["shortlist"],
        integrated_path=bad_path,
        wind_generators_path=f["wind"],
        grid_path=f["grid"],
    )
    with pytest.raises(ValueError) as excinfo:
        load_inputs(inputs)
    message = str(excinfo.value)
    assert "rez_name" in message
    assert "Integrated_Feature_Table" in message


def test_loader_accepts_integrated_with_rez_name(tmp_path):
    """The normal path: an integrated frame carrying rez_name loads cleanly and
    the column is carried through verbatim."""
    f = _good_frames(tmp_path)
    f["wind_frame"].to_file(f["wind"], driver="GeoJSON")
    good_path = _write_gpkg(tmp_path / "integrated.gpkg", f["integrated"], config.INTEGRATED_LAYER)

    inputs = SanityInputs(
        scored_path=f["scored"],
        shortlist_path=f["shortlist"],
        integrated_path=good_path,
        wind_generators_path=f["wind"],
        grid_path=f["grid"],
    )
    loaded = load_inputs(inputs)
    assert "rez_name" in loaded.integrated.columns
