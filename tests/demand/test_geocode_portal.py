"""Tests for the "coordinates already present" PORTAL fast-path in geocode_load.

The Endeavour DAPR portal extract (appended to
``nsw_zone_substation_max_demand.csv``) arrives WITH precise WGS84 coordinates
for every row, so those rows must BYPASS the GA->OSM->Nominatim name-geocoding
and be emitted directly as precise points with ``coord_source="portal"`` and
GA-precise confidence (never the osm/nominatim low-confidence flags). Rows that
arrive WITHOUT coordinates (Essential/Ausgrid, name-only) must continue through
the three name-geocoding tiers exactly as before.

Covers:
(a) a demand row WITH valid coordinates -> ``coord_source="portal"`` and never
    matched against GA/OSM/Nominatim;
(b) a portal row is NOT flagged low-confidence;
(c) regression: coordinate-less rows still flow through GA->OSM->Nominatim;
(d) determinism;
plus the coordinate-validity guards (blank, non-numeric, out-of-NSW-bbox rows
fall back to name-geocoding) and back-compatibility (a load CSV with no
latitude/longitude columns behaves exactly as before).

All fixtures are tiny in-memory GeoDataFrames written to temporary GeoJSON — no
network.
"""

from pathlib import Path

import geopandas as gpd
import pandas as pd
import pytest
from shapely.geometry import Point

from pipeline.demand import config as demand_config
from pipeline.demand.geocode_load import geocode


# ---------------------------------------------------------------------------
# Fixtures (mirror test_geocode_osm.py / test_geocode_nominatim.py)
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


def _portal_row(name, lat, lon, dnsp="endeavour", demand=12.0):
    """A load row that arrives WITH coordinates (the Endeavour portal shape)."""
    return {
        "dnsp": dnsp,
        "substation_name": name,
        "locality": "",
        "latitude": lat,
        "longitude": lon,
        demand_config.LOAD_MVA_COLUMN: demand,
        "max_demand_unit": "MVA",
        "data_year": "2025 summer",
    }


def _name_only_row(name, dnsp="ausgrid", demand=10.0, lat="", lon=""):
    """A name-only load row (Essential/Ausgrid shape): blank lat/lon."""
    return {
        "dnsp": dnsp,
        "substation_name": name,
        "locality": "",
        "latitude": lat,
        "longitude": lon,
        demand_config.LOAD_MVA_COLUMN: demand,
        "max_demand_unit": "MVA",
        "data_year": "2024/25",
    }


# A coordinate comfortably inside the NSW bbox (Greater Western Sydney).
_GWS_LAT, _GWS_LON = -33.75, 150.90


# ---------------------------------------------------------------------------
# (a) present coordinates -> coord_source="portal", bypass name-geocoding
# ---------------------------------------------------------------------------


def test_present_coordinates_emit_portal_and_bypass_name_geocoding(tmp_path):
    # A row carrying coordinates whose NAME *also* exists as a GA/OSM/Nominatim
    # candidate must still be emitted from its OWN coordinates (portal), never
    # relocated to the name-match. The name-match points are placed at a clearly
    # different location so a bypass failure would be visible.
    load = _write_load_csv(tmp_path, [_portal_row("Marsden Park ZS", _GWS_LAT, _GWS_LON)])
    ga = _write_ga(tmp_path, [{"feature_name": "Marsden Park", "locality": "X", "voltage_kv": 132, "lon": 149.0, "lat": -30.0}])
    osm = _write_osm(tmp_path, [{"name": "Marsden Park Zone Substation", "operator": "Endeavour Energy", "substation": "zone", "lon": 149.0, "lat": -30.0}])
    nominatim = _write_nominatim(tmp_path, [])

    matched, unmatched, stats = geocode(load, ga, osm, nominatim)

    row = matched.set_index("substation_name").loc["Marsden Park ZS"]
    assert row["coord_source"] == "portal"
    # Emitted from its OWN coordinates, NOT the GA/OSM candidate at (149, -30).
    assert row["latitude"] == pytest.approx(_GWS_LAT)
    assert row["longitude"] == pytest.approx(_GWS_LON)
    # Geometry matches the portal point.
    assert row.geometry.x == pytest.approx(_GWS_LON)
    assert row.geometry.y == pytest.approx(_GWS_LAT)
    # Counted as portal, and NOT as a GA/OSM/Nominatim match.
    assert stats["matched_portal"] == 1
    assert stats["matched_ga"] == 0
    assert stats["matched_osm"] == 0
    assert stats["matched_nominatim"] == 0
    assert stats["unmatched"] == 0


def test_portal_row_matched_even_when_name_geocoders_are_empty(tmp_path):
    # With all three name-geocoding sources empty, a name-only row would be
    # dropped — but a portal row is still matched from its own coordinates.
    load = _write_load_csv(tmp_path, [_portal_row("Bylong ZS", -32.41, 150.05, demand=0.38)])
    ga = _write_ga(tmp_path, [])
    osm = _write_osm(tmp_path, [])
    nominatim = _write_nominatim(tmp_path, [])

    matched, unmatched, stats = geocode(load, ga, osm, nominatim)
    assert stats["matched_portal"] == 1
    assert stats["unmatched"] == 0
    assert matched.set_index("substation_name").loc["Bylong ZS", "coord_source"] == "portal"


# ---------------------------------------------------------------------------
# (b) a portal row is NOT flagged low-confidence
# ---------------------------------------------------------------------------


def test_portal_row_is_not_low_confidence(tmp_path):
    load = _write_load_csv(tmp_path, [_portal_row("St Marys ZS", -33.76, 150.78, demand=29.38)])
    ga = _write_ga(tmp_path, [])
    osm = _write_osm(tmp_path, [])
    nominatim = _write_nominatim(tmp_path, [])

    matched, _, stats = geocode(load, ga, osm, nominatim)
    row = matched.set_index("substation_name").loc["St Marys ZS"]
    assert bool(row["osm_low_confidence"]) is False
    assert bool(row["nominatim_low_confidence"]) is False
    # Portal matches never count toward the OSM low-confidence tally.
    assert stats["osm_low_confidence"] == 0


# ---------------------------------------------------------------------------
# (c) regression: coordinate-less rows still flow GA -> OSM -> Nominatim
# ---------------------------------------------------------------------------


def test_name_only_rows_still_flow_through_name_geocoding(tmp_path):
    # A mixed CSV: one portal row (coords) + three name-only rows exercising each
    # name-geocoding tier. The name-only rows must behave exactly as before.
    load = _write_load_csv(
        tmp_path,
        [
            _portal_row("Portal Site ZS", _GWS_LAT, _GWS_LON),  # portal
            _name_only_row("Boggabri North", dnsp="ausgrid"),    # GA
            _name_only_row("Campsie", dnsp="ausgrid"),           # OSM (GA miss)
            _name_only_row("Metford", dnsp="ausgrid"),           # Nominatim (GA+OSM miss)
        ],
    )
    ga = _write_ga(tmp_path, [{"feature_name": "Boggabri North", "locality": "HARPARARY", "voltage_kv": 132, "lon": 150.0, "lat": -30.0}])
    osm = _write_osm(tmp_path, [{"name": "Campsie Zone Substation", "operator": "Ausgrid", "substation": "zone", "lon": 151.10, "lat": -33.91}])
    nominatim = _write_nominatim(
        tmp_path,
        [{"queried_name": "Metford", "display_name": "Metford, NSW", "osm_class": "place", "osm_type": "suburb", "importance": 0.4, "needs_review": False, "lon": 151.60, "lat": -32.75}],
    )

    matched, unmatched, stats = geocode(load, ga, osm, nominatim)
    by_name = matched.set_index("substation_name")
    assert by_name.loc["Portal Site ZS", "coord_source"] == "portal"
    assert by_name.loc["Boggabri North", "coord_source"] == "ga"
    assert by_name.loc["Campsie", "coord_source"] == "osm"
    assert by_name.loc["Metford", "coord_source"] == "nominatim"
    assert bool(by_name.loc["Metford", "nominatim_low_confidence"]) is True
    assert stats["matched_portal"] == 1
    assert stats["matched_ga"] == 1
    assert stats["matched_osm"] == 1
    assert stats["matched_nominatim"] == 1
    assert stats["unmatched"] == 0


def test_blank_nonnumeric_and_out_of_bbox_coords_fall_back_to_name_geocoding(tmp_path):
    # Rows whose coordinates are blank / non-numeric / outside the NSW bbox are
    # NOT trusted as portal points — they fall back to name-geocoding (and here,
    # with empty name sources, are dropped rather than invented).
    load = _write_load_csv(
        tmp_path,
        [
            _name_only_row("Blank Coords", lat="", lon=""),          # blank -> name path
            _name_only_row("Bad Coords", lat="n/a", lon="n/a"),      # non-numeric -> name path
            _portal_row("Out Of NSW", lat=-10.0, lon=130.0),          # outside bbox -> name path
            _portal_row("Inside NSW", _GWS_LAT, _GWS_LON),            # valid -> portal
        ],
    )
    ga = _write_ga(tmp_path, [])
    osm = _write_osm(tmp_path, [])
    nominatim = _write_nominatim(tmp_path, [])

    matched, unmatched, stats = geocode(load, ga, osm, nominatim)
    assert stats["matched_portal"] == 1
    matched_names = set(matched["substation_name"])
    assert matched_names == {"Inside NSW"}
    dropped = set(unmatched["substation_name"])
    assert dropped == {"Blank Coords", "Bad Coords", "Out Of NSW"}


def test_load_csv_without_coordinate_columns_is_back_compatible(tmp_path):
    # A load CSV that has NO latitude/longitude columns at all (the pre-Endeavour
    # schema) must behave exactly as before: every row goes through name-matching.
    load = _write_load_csv(
        tmp_path,
        [
            {
                "dnsp": "ausgrid",
                "substation_name": "Boggabri North",
                demand_config.LOAD_MVA_COLUMN: 10.0,
                "max_demand_unit": "MVA",
                "data_year": "2024/25",
            }
        ],
    )
    ga = _write_ga(tmp_path, [{"feature_name": "Boggabri North", "locality": "X", "voltage_kv": 132, "lon": 150.0, "lat": -30.0}])
    osm = _write_osm(tmp_path, [])
    nominatim = _write_nominatim(tmp_path, [])

    matched, _, stats = geocode(load, ga, osm, nominatim)
    assert stats["matched_portal"] == 0
    assert stats["matched_ga"] == 1
    assert matched.set_index("substation_name").loc["Boggabri North", "coord_source"] == "ga"


# ---------------------------------------------------------------------------
# (d) determinism
# ---------------------------------------------------------------------------


def test_portal_fast_path_is_deterministic(tmp_path):
    load = _write_load_csv(
        tmp_path,
        [
            _portal_row("Alpha ZS", -34.00, 150.50),
            _portal_row("Beta ZS", -33.50, 150.95),
            _name_only_row("Boggabri North", dnsp="ausgrid"),
        ],
    )
    ga = _write_ga(tmp_path, [{"feature_name": "Boggabri North", "locality": "X", "voltage_kv": 132, "lon": 150.0, "lat": -30.0}])
    osm = _write_osm(tmp_path, [])
    nominatim = _write_nominatim(tmp_path, [])

    first, _, first_stats = geocode(load, ga, osm, nominatim)
    second, _, second_stats = geocode(load, ga, osm, nominatim)
    assert first_stats == second_stats
    pd.testing.assert_frame_equal(
        first.drop(columns="geometry"), second.drop(columns="geometry")
    )
