"""Tests for the Nominatim (OSM place-geocoding) THIRD coordinate-source tier.

Covers findings.md §6: the third-tier precedence (GA -> OSM -> Nominatim, with
Nominatim NEVER overriding a higher tier), the always-on low-confidence flag, the
pure bbox/class/importance safeguard helper (no network), the missing-snapshot
hard-fail, and determinism including the importance tie-break. All fixtures are
tiny in-memory GeoDataFrames written to temporary GeoJSON — no network.
"""

from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point

from pipeline.demand import config as demand_config
from pipeline.demand.geocode_load import geocode
from scripts._acquire_nominatim_substations_nsw import (
    IMPORTANCE_FLOOR,
    base_name_fallback,
    classify_result,
)


# ---------------------------------------------------------------------------
# Fixtures (mirror test_geocode_osm.py's in-memory style)
# ---------------------------------------------------------------------------


def _write_load_csv(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "load.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _write_ga(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "ga.geojson"
    if rows:
        gdf = gpd.GeoDataFrame(
            [{"feature_name": r["feature_name"], "locality": r.get("locality"), "voltage_kv": r.get("voltage_kv")} for r in rows],
            geometry=[Point(r["lon"], r["lat"]) for r in rows],
            crs="EPSG:4326",
        )
    else:
        gdf = gpd.GeoDataFrame({"feature_name": [], "locality": [], "voltage_kv": []}, geometry=[], crs="EPSG:4326")
    gdf.to_file(path, driver="GeoJSON")
    return path


def _write_osm(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "osm.geojson"
    if rows:
        gdf = gpd.GeoDataFrame(
            [{"name": r["name"], "operator": r.get("operator"), "substation": r.get("substation"), "voltage": r.get("voltage")} for r in rows],
            geometry=[Point(r["lon"], r["lat"]) for r in rows],
            crs="EPSG:4326",
        )
    else:
        gdf = gpd.GeoDataFrame({"name": [], "operator": [], "substation": [], "voltage": []}, geometry=[], crs="EPSG:4326")
    gdf.to_file(path, driver="GeoJSON")
    return path


def _write_nominatim(tmp_path: Path, rows: list[dict]) -> Path:
    """rows: queried_name, display_name, osm_class, osm_type, importance, needs_review, lon, lat."""
    path = tmp_path / "nominatim.geojson"
    cols = ["queried_name", "display_name", "osm_class", "osm_type", "importance", "needs_review"]
    if rows:
        gdf = gpd.GeoDataFrame(
            [{c: r.get(c) for c in cols} for r in rows],
            geometry=[Point(r["lon"], r["lat"]) for r in rows],
            crs="EPSG:4326",
        )
    else:
        gdf = gpd.GeoDataFrame({c: [] for c in cols}, geometry=[], crs="EPSG:4326")
    gdf.to_file(path, driver="GeoJSON")
    return path


def _nom_row(queried_name, lon, lat, importance=0.30, osm_class="boundary", osm_type="administrative", needs_review=False, display_name=None):
    return {
        "queried_name": queried_name,
        "display_name": display_name or f"{queried_name}, NSW, Australia",
        "osm_class": osm_class,
        "osm_type": osm_type,
        "importance": importance,
        "needs_review": needs_review,
        "lon": lon,
        "lat": lat,
    }


def _load_row(name, dnsp="ausgrid", demand=10.0):
    return {
        "dnsp": dnsp,
        "substation_name": name,
        demand_config.LOAD_MVA_COLUMN: demand,
        "max_demand_unit": "MVA",
        "data_year": "2024/25",
    }


# ---------------------------------------------------------------------------
# 1. Third-tier precedence (GA -> OSM -> Nominatim; never overrides)
# ---------------------------------------------------------------------------


def test_nominatim_recovers_ga_and_osm_miss(tmp_path):
    load = _write_load_csv(tmp_path, [_load_row("Metford")])
    ga = _write_ga(tmp_path, [])
    osm = _write_osm(tmp_path, [])
    nominatim = _write_nominatim(tmp_path, [_nom_row("Metford", 151.61, -32.766)])
    matched, unmatched, stats = geocode(load, ga, osm, nominatim)

    row = matched.set_index("substation_name").loc["Metford"]
    assert row["coord_source"] == "nominatim"
    assert bool(row["nominatim_low_confidence"]) is True
    assert bool(row["osm_low_confidence"]) is False
    assert row["longitude"] == pytest.approx(151.61)
    assert row["latitude"] == pytest.approx(-32.766)
    assert stats["matched_nominatim"] == 1
    assert len(unmatched) == 0


def test_ga_hit_is_not_overridden_by_nominatim(tmp_path):
    load = _write_load_csv(tmp_path, [_load_row("Metford")])
    ga = _write_ga(tmp_path, [{"feature_name": "Metford", "locality": "X", "voltage_kv": 132, "lon": 150.0, "lat": -30.0}])
    osm = _write_osm(tmp_path, [])
    # A Nominatim row for the same name must be ignored because GA already hit.
    nominatim = _write_nominatim(tmp_path, [_nom_row("Metford", 151.61, -32.766)])
    matched, _, stats = geocode(load, ga, osm, nominatim)

    row = matched.set_index("substation_name").loc["Metford"]
    assert row["coord_source"] == "ga"
    assert row["longitude"] == pytest.approx(150.0)
    assert bool(row["nominatim_low_confidence"]) is False
    assert stats["matched_nominatim"] == 0


def test_osm_hit_is_not_overridden_by_nominatim(tmp_path):
    load = _write_load_csv(tmp_path, [_load_row("Campsie", dnsp="ausgrid")])
    ga = _write_ga(tmp_path, [])
    osm = _write_osm(tmp_path, [{"name": "Campsie Zone Substation", "operator": "Ausgrid", "substation": "zone", "lon": 151.1, "lat": -33.9}])
    nominatim = _write_nominatim(tmp_path, [_nom_row("Campsie", 151.5, -33.5)])
    matched, _, stats = geocode(load, ga, osm, nominatim)

    row = matched.set_index("substation_name").loc["Campsie"]
    assert row["coord_source"] == "osm"
    assert row["longitude"] == pytest.approx(151.1)
    assert bool(row["nominatim_low_confidence"]) is False
    assert stats["matched_nominatim"] == 0


def test_unmatched_by_all_three_is_dropped_with_reason(tmp_path):
    load = _write_load_csv(tmp_path, [_load_row("Graving Dock No 1")])
    ga = _write_ga(tmp_path, [])
    osm = _write_osm(tmp_path, [])
    nominatim = _write_nominatim(tmp_path, [])  # not a place -> not in snapshot
    matched, unmatched, stats = geocode(load, ga, osm, nominatim)

    assert "Graving Dock No 1" not in set(matched["substation_name"])
    reason = unmatched.set_index("substation_name").loc["Graving Dock No 1", "reason"]
    assert reason == "no GA, OSM or Nominatim match"


# ---------------------------------------------------------------------------
# 2. Low-confidence flag ALWAYS set for Nominatim hits
# ---------------------------------------------------------------------------


def test_nominatim_hits_always_low_confidence(tmp_path):
    load = _write_load_csv(tmp_path, [_load_row("Metford"), _load_row("Edgeworth")])
    ga = _write_ga(tmp_path, [])
    osm = _write_osm(tmp_path, [])
    # One with high importance, one near the floor: both must still be low-confidence.
    nominatim = _write_nominatim(
        tmp_path,
        [
            _nom_row("Metford", 151.61, -32.766, importance=0.45),
            _nom_row("Edgeworth", 151.631, -32.920, importance=0.16, needs_review=True),
        ],
    )
    matched, _, _ = geocode(load, ga, osm, nominatim)
    nom = matched[matched["coord_source"] == "nominatim"]
    assert len(nom) == 2
    assert bool(nom["nominatim_low_confidence"].all()) is True
    assert bool((~nom["osm_low_confidence"]).all()) is True


# ---------------------------------------------------------------------------
# 3. Pure safeguard/parse helper (no network)
# ---------------------------------------------------------------------------


def test_classify_accepts_clean_nsw_admin_place():
    result = {"lat": "-32.766", "lon": "151.61", "class": "boundary", "type": "administrative", "importance": 0.25, "display_name": "Metford"}
    verdict = classify_result(result)
    assert verdict["accepted"] is True
    assert verdict["bbox_pass"] is True
    assert verdict["latitude"] == pytest.approx(-32.766)


def test_classify_rejects_out_of_nsw():
    # In Australia but outside the NSW bbox (e.g. Melbourne).
    result = {"lat": "-37.81", "lon": "144.96", "class": "boundary", "type": "administrative", "importance": 0.6, "display_name": "Melbourne"}
    verdict = classify_result(result)
    assert verdict["accepted"] is False
    assert verdict["bbox_pass"] is False
    assert "bbox" in verdict["reason"]


def test_classify_rejects_highway_and_poi_classes():
    for cls in ("highway", "waterway", "railway", "tourism", "amenity"):
        result = {"lat": "-33.9", "lon": "151.1", "class": cls, "type": "x", "importance": 0.4, "display_name": "road"}
        verdict = classify_result(result)
        assert verdict["accepted"] is False, cls
        assert cls in verdict["reason"]


def test_classify_rejects_below_importance_floor():
    result = {"lat": "-33.9", "lon": "151.1", "class": "place", "type": "suburb", "importance": IMPORTANCE_FLOOR - 0.01, "display_name": "x"}
    verdict = classify_result(result)
    assert verdict["accepted"] is False
    assert "importance" in verdict["reason"]


def test_classify_none_result():
    verdict = classify_result(None)
    assert verdict["accepted"] is False
    assert verdict["reason"] == "no result"


def test_base_name_fallback_strips_trailing_qualifier():
    assert base_name_fallback("Cessnock South") == "Cessnock"
    assert base_name_fallback("Finley Town") == "Finley"
    assert base_name_fallback("Lismore Uni") == "Lismore"
    assert base_name_fallback("Metford") is None


# ---------------------------------------------------------------------------
# 4. Missing-snapshot hard-fail (no silent two-source fallback)
# ---------------------------------------------------------------------------


def test_missing_nominatim_source_raises(tmp_path):
    load = _write_load_csv(tmp_path, [_load_row("Metford")])
    ga = _write_ga(tmp_path, [{"feature_name": "Metford", "locality": "X", "voltage_kv": 132, "lon": 150.0, "lat": -30.0}])
    osm = _write_osm(tmp_path, [])
    missing_nominatim = tmp_path / "does_not_exist.geojson"
    with pytest.raises(FileNotFoundError, match="Nominatim substation layer is missing"):
        geocode(load, ga, osm, missing_nominatim)


# ---------------------------------------------------------------------------
# 5. Determinism incl. importance tie-break (highest importance, then lat/lon)
# ---------------------------------------------------------------------------


def test_duplicate_nominatim_names_resolve_by_importance_then_latlon(tmp_path):
    load = _write_load_csv(tmp_path, [_load_row("Metford")])
    ga = _write_ga(tmp_path, [])
    osm = _write_osm(tmp_path, [])
    # Two rows normalise to "metford"; the higher-importance one wins regardless
    # of order in the file.
    nominatim = _write_nominatim(
        tmp_path,
        [
            _nom_row("Metford", 151.00, -32.00, importance=0.20),
            _nom_row("Metford", 151.61, -32.766, importance=0.45),
        ],
    )
    first, _, _ = geocode(load, ga, osm, nominatim)
    second, _, _ = geocode(load, ga, osm, nominatim)
    chosen = first.set_index("substation_name").loc["Metford"]
    assert chosen["longitude"] == pytest.approx(151.61)
    assert chosen["latitude"] == pytest.approx(-32.766)
    pd.testing.assert_frame_equal(first.drop(columns="geometry"), second.drop(columns="geometry"))


def test_nominatim_importance_tiebreak_latlon_when_equal(tmp_path):
    load = _write_load_csv(tmp_path, [_load_row("Metford")])
    ga = _write_ga(tmp_path, [])
    osm = _write_osm(tmp_path, [])
    # Equal importance -> smallest (lat, lon) wins.
    nominatim = _write_nominatim(
        tmp_path,
        [
            _nom_row("Metford", 151.61, -32.70, importance=0.30),
            _nom_row("Metford", 151.50, -32.90, importance=0.30),
        ],
    )
    matched, _, _ = geocode(load, ga, osm, nominatim)
    chosen = matched.set_index("substation_name").loc["Metford"]
    # smallest latitude is -32.90
    assert chosen["latitude"] == pytest.approx(-32.90)
    assert chosen["longitude"] == pytest.approx(151.50)
