"""Tests for the GA-primary + OSM-second two-source geocoder.

Covers findings.md §6d: OSM-suffix normalisation, two-source precedence,
determinism, the operator-agreement gate, and the missing-OSM hard-fail. All
fixtures are tiny in-memory GeoDataFrames written to temporary GeoJSON — no
network.
"""

from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point

from pipeline.demand import config as demand_config
from pipeline.demand.geocode_load import geocode, normalise_substation_name


# ---------------------------------------------------------------------------
# 1. OSM-suffix normalisation (and GA-mode regression)
# ---------------------------------------------------------------------------


def test_osm_suffix_strip_and_abbrev_expansion():
    assert normalise_substation_name("Campsie Zone Substation", strip_site_suffix=True) == "campsie"
    assert normalise_substation_name("Boronia Street ZS", strip_site_suffix=True) == "boronia street"
    assert normalise_substation_name("Mascot Substation", strip_site_suffix=True) == "mascot"
    assert normalise_substation_name("Lidcombe ZSS", strip_site_suffix=True) == "lidcombe"
    # Abbreviation expansion (behind the same flag).
    assert normalise_substation_name("Campbell St", strip_site_suffix=True) == "campbell street"
    assert normalise_substation_name("Dalley Dr", strip_site_suffix=True) == "dalley drive"


def test_ga_mode_normalisation_is_unchanged_regression():
    # Flag off (GA mode) must be byte-identical to the pre-OSM behaviour: no
    # suffix strip, no abbreviation expansion.
    assert normalise_substation_name("Campsie Zone Substation") == "campsie zone substation"
    assert normalise_substation_name("Campbell St") == "campbell st"
    assert normalise_substation_name("Terranora 110/66kV") == "terranora"
    assert normalise_substation_name("OLYMPIC PARK") == "olympic park"
    assert normalise_substation_name(None) == ""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _write_load_csv(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "load.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _write_ga(tmp_path: Path, rows: list[dict]) -> Path:
    """rows: feature_name, locality, voltage_kv, lon, lat."""
    path = tmp_path / "ga.geojson"
    if rows:
        gdf = gpd.GeoDataFrame(
            [{"feature_name": r["feature_name"], "locality": r.get("locality"), "voltage_kv": r.get("voltage_kv")} for r in rows],
            geometry=[Point(r["lon"], r["lat"]) for r in rows],
            crs="EPSG:4326",
        )
    else:
        gdf = gpd.GeoDataFrame(
            {"feature_name": [], "locality": [], "voltage_kv": []},
            geometry=[], crs="EPSG:4326",
        )
    gdf.to_file(path, driver="GeoJSON")
    return path


def _write_osm(tmp_path: Path, rows: list[dict]) -> Path:
    """rows: name, operator, substation, lon, lat."""
    path = tmp_path / "osm.geojson"
    if rows:
        gdf = gpd.GeoDataFrame(
            [{"name": r["name"], "operator": r.get("operator"), "substation": r.get("substation"), "voltage": r.get("voltage")} for r in rows],
            geometry=[Point(r["lon"], r["lat"]) for r in rows],
            crs="EPSG:4326",
        )
    else:
        gdf = gpd.GeoDataFrame(
            {"name": [], "operator": [], "substation": [], "voltage": []},
            geometry=[], crs="EPSG:4326",
        )
    gdf.to_file(path, driver="GeoJSON")
    return path


def _write_nominatim(tmp_path: Path, rows: list[dict]) -> Path:
    """rows: queried_name, display_name, osm_class, osm_type, importance, needs_review, lon, lat.

    The two-source regression tests pass an EMPTY Nominatim layer so the third
    tier never fires; the geocoder still requires the (now third) source to exist.
    """
    path = tmp_path / "nominatim.geojson"
    cols = ["queried_name", "display_name", "osm_class", "osm_type", "importance", "needs_review"]
    if rows:
        gdf = gpd.GeoDataFrame(
            [{c: r.get(c) for c in cols} for r in rows],
            geometry=[Point(r["lon"], r["lat"]) for r in rows],
            crs="EPSG:4326",
        )
    else:
        gdf = gpd.GeoDataFrame(
            {c: [] for c in cols},
            geometry=[], crs="EPSG:4326",
        )
    gdf.to_file(path, driver="GeoJSON")
    return path


def _load_row(name, dnsp="ausgrid", demand=10.0):
    return {
        "dnsp": dnsp,
        "substation_name": name,
        demand_config.LOAD_MVA_COLUMN: demand,
        "max_demand_unit": "MVA",
        "data_year": "2024/25",
    }


# ---------------------------------------------------------------------------
# 2. Two-source precedence
# ---------------------------------------------------------------------------


def test_two_source_precedence_ga_first_osm_second_drop_rest(tmp_path):
    load = _write_load_csv(
        tmp_path,
        [
            _load_row("Boggabri North"),   # in GA (and OSM) -> GA wins
            _load_row("Campsie"),          # GA-missing, in OSM -> OSM
            _load_row("Nowhere Town"),     # in neither -> dropped
        ],
    )
    ga = _write_ga(tmp_path, [{"feature_name": "Boggabri North", "locality": "HARPARARY", "voltage_kv": 132, "lon": 150.0, "lat": -30.0}])
    osm = _write_osm(
        tmp_path,
        [
            {"name": "Boggabri North Zone Substation", "operator": "Ausgrid", "substation": "zone", "lon": 150.5, "lat": -30.5},
            {"name": "Campsie Zone Substation", "operator": "Ausgrid", "substation": "zone", "lon": 151.1, "lat": -33.9},
        ],
    )
    nominatim = _write_nominatim(tmp_path, [])
    matched, unmatched, stats = geocode(load, ga, osm, nominatim)

    by_name = matched.set_index("substation_name")
    # GA takes precedence for the row present in both (GA coords, not OSM's).
    assert by_name.loc["Boggabri North", "coord_source"] == "ga"
    assert by_name.loc["Boggabri North", "longitude"] == pytest.approx(150.0)
    # GA-missing row recovered from OSM.
    assert by_name.loc["Campsie", "coord_source"] == "osm"
    assert by_name.loc["Campsie", "longitude"] == pytest.approx(151.1)
    # Neither source -> dropped and listed.
    assert "Nowhere Town" not in by_name.index
    assert "Nowhere Town" in set(unmatched["substation_name"])
    assert stats["matched_ga"] == 1
    assert stats["matched_osm"] == 1
    assert stats["unmatched"] == 1


# ---------------------------------------------------------------------------
# 3. Determinism (duplicate OSM names via the (operator, lat, lon) tie-break)
# ---------------------------------------------------------------------------


def test_duplicate_osm_names_resolve_deterministically(tmp_path):
    load = _write_load_csv(tmp_path, [_load_row("Campsie")])
    ga = _write_ga(tmp_path, [])
    # Two OSM elements normalise to "campsie"; tie-break is (operator, lat, lon).
    # Both Ausgrid, so the smaller (lat, lon) wins: (-33.95, 151.05).
    osm = _write_osm(
        tmp_path,
        [
            {"name": "Campsie Zone Substation", "operator": "Ausgrid", "substation": "zone", "lon": 151.10, "lat": -33.90},
            {"name": "Campsie Substation", "operator": "Ausgrid", "substation": "zone", "lon": 151.05, "lat": -33.95},
        ],
    )
    nominatim = _write_nominatim(tmp_path, [])
    first, _, _ = geocode(load, ga, osm, nominatim)
    second, _, _ = geocode(load, ga, osm, nominatim)
    chosen = first.set_index("substation_name").loc["Campsie"]
    assert chosen["latitude"] == pytest.approx(-33.95)
    assert chosen["longitude"] == pytest.approx(151.05)
    # Identical output across two runs.
    pd.testing.assert_frame_equal(
        first.drop(columns="geometry"), second.drop(columns="geometry")
    )


# ---------------------------------------------------------------------------
# 4. Operator-agreement gate
# ---------------------------------------------------------------------------


def test_operator_disagreement_is_rejected_not_trusted(tmp_path):
    # An Ausgrid load row whose only OSM candidate is operated by Essential
    # Energy must be rejected (operator gate), dropped, and listed with reason.
    load = _write_load_csv(tmp_path, [_load_row("Someplace", dnsp="ausgrid")])
    ga = _write_ga(tmp_path, [])
    osm = _write_osm(
        tmp_path,
        [{"name": "Someplace Zone Substation", "operator": "Essential Energy", "substation": "zone", "lon": 149.0, "lat": -32.0}],
    )
    nominatim = _write_nominatim(tmp_path, [])
    matched, unmatched, stats = geocode(load, ga, osm, nominatim)
    assert "Someplace" not in set(matched["substation_name"])
    assert stats["matched_osm"] == 0
    row = unmatched[unmatched["substation_name"] == "Someplace"].iloc[0]
    assert "operator" in row["reason"].lower()


def test_absent_operator_is_accepted_but_flagged_low_confidence(tmp_path):
    load = _write_load_csv(tmp_path, [_load_row("Someplace", dnsp="ausgrid")])
    ga = _write_ga(tmp_path, [])
    osm = _write_osm(
        tmp_path,
        [{"name": "Someplace Zone Substation", "operator": None, "substation": "zone", "lon": 149.0, "lat": -32.0}],
    )
    nominatim = _write_nominatim(tmp_path, [])
    matched, _, stats = geocode(load, ga, osm, nominatim)
    row = matched.set_index("substation_name").loc["Someplace"]
    assert row["coord_source"] == "osm"
    assert bool(row["osm_low_confidence"]) is True
    assert stats["osm_low_confidence"] == 1


def test_matching_operator_is_high_confidence(tmp_path):
    load = _write_load_csv(tmp_path, [_load_row("Campsie", dnsp="ausgrid")])
    ga = _write_ga(tmp_path, [])
    osm = _write_osm(
        tmp_path,
        [{"name": "Campsie Zone Substation", "operator": "Ausgrid", "substation": "zone", "lon": 151.1, "lat": -33.9}],
    )
    nominatim = _write_nominatim(tmp_path, [])
    matched, _, stats = geocode(load, ga, osm, nominatim)
    row = matched.set_index("substation_name").loc["Campsie"]
    assert row["coord_source"] == "osm"
    assert bool(row["osm_low_confidence"]) is False
    assert stats["osm_low_confidence"] == 0


# ---------------------------------------------------------------------------
# 5. Missing-OSM hard-fail (no silent GA-only fallback)
# ---------------------------------------------------------------------------


def test_missing_osm_source_raises(tmp_path):
    load = _write_load_csv(tmp_path, [_load_row("Boggabri North")])
    ga = _write_ga(tmp_path, [{"feature_name": "Boggabri North", "locality": "X", "voltage_kv": 132, "lon": 150.0, "lat": -30.0}])
    missing_osm = tmp_path / "does_not_exist.geojson"
    nominatim = _write_nominatim(tmp_path, [])
    with pytest.raises(FileNotFoundError, match="OSM substation layer is missing"):
        geocode(load, ga, missing_osm, nominatim)
