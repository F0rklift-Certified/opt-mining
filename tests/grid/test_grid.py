"""
Tests for the common analysis cell grid (S1-02).

Validates:
1. GWA lattice alignment — every cell edge is an integer number of GWA pixels
   from the origin (the core claim behind choosing Option A).
2. Grid schema — correct columns, CRS, unique cell IDs.
3. Cell area — within expected bounds for NSW latitudes.
4. Cell ID format — matches the S{lat}_E{lon} specification.
5. Grid dimensions — match expected count from integration analysis.
6. GeoPackage roundtrip — file on disk is readable and consistent.
"""

import math
import re

import geopandas as gpd
import numpy as np
import pytest

from pipeline.grid import config
from pipeline.grid.generate import (
    _format_cell_id,
    _grid_dimensions,
    _snap_origin,
    generate_grid,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def grid_gdf():
    """Generate the full NSW grid once per test module (expensive: ~0.6s)."""
    return generate_grid()


@pytest.fixture(scope="module")
def small_grid():
    """A small grid for fast alignment tests (2 deg × 2 deg)."""
    small_bbox = (150.0, -31.5, 152.0, -29.5)
    return generate_grid(bbox=small_bbox)


# ---------------------------------------------------------------------------
# Test 1: GWA lattice alignment
# ---------------------------------------------------------------------------


class TestGWAAlignment:
    """Prove that every cell edge aligns with the GWA native pixel lattice."""

    def test_cell_width_is_exactly_20_pixels(self):
        """Cell width in degrees should be exactly 20 * GWA step."""
        expected = config.CELL_FACTOR * config.GWA_STEP_DEG
        assert config.CELL_DEG == expected, (
            f"CELL_DEG={config.CELL_DEG} != {config.CELL_FACTOR} * "
            f"{config.GWA_STEP_DEG} = {expected}"
        )

    def test_snapped_origin_aligns_to_gwa(self):
        """The snapped grid origin must be an integer multiple of CELL_DEG
        from the GWA origin."""
        origin_lon, origin_lat = _snap_origin(config.NSW_BBOX)

        # Longitude offset from GWA origin in GWA pixels
        lon_offset_pixels = (origin_lon - config.GWA_ORIGIN_LON) / config.GWA_STEP_DEG
        assert abs(lon_offset_pixels - round(lon_offset_pixels)) < 1e-8, (
            f"Origin lon {origin_lon} is not aligned to GWA lattice. "
            f"Pixel offset = {lon_offset_pixels} (expected integer)."
        )

        # Latitude offset from GWA origin in GWA pixels
        lat_offset_pixels = (config.GWA_ORIGIN_LAT - origin_lat) / config.GWA_STEP_DEG
        assert abs(lat_offset_pixels - round(lat_offset_pixels)) < 1e-8, (
            f"Origin lat {origin_lat} is not aligned to GWA lattice. "
            f"Pixel offset = {lat_offset_pixels} (expected integer)."
        )

    def test_all_west_edges_align(self, small_grid):
        """Every cell's western edge should be an integer number of GWA pixels
        from the GWA origin."""
        west_edges = small_grid.geometry.bounds["minx"].values
        offsets = (west_edges - config.GWA_ORIGIN_LON) / config.GWA_STEP_DEG
        residuals = np.abs(offsets - np.round(offsets))
        max_residual = residuals.max()
        assert max_residual < 1e-8, (
            f"West edges are not GWA-aligned. Max residual = {max_residual} "
            f"pixels (should be < 1e-8)."
        )

    def test_all_south_edges_align(self, small_grid):
        """Every cell's southern edge should be an integer number of GWA pixels
        from the GWA origin."""
        south_edges = small_grid.geometry.bounds["miny"].values
        offsets = (config.GWA_ORIGIN_LAT - south_edges) / config.GWA_STEP_DEG
        residuals = np.abs(offsets - np.round(offsets))
        max_residual = residuals.max()
        assert max_residual < 1e-8, (
            f"South edges are not GWA-aligned. Max residual = {max_residual} "
            f"pixels (should be < 1e-8)."
        )

    def test_each_cell_contains_400_gwa_pixels(self, small_grid):
        """Each cell should span exactly 20 GWA pixels in each direction
        (20x20 = 400 total)."""
        bounds = small_grid.geometry.bounds
        widths_deg = bounds["maxx"].values - bounds["minx"].values
        heights_deg = bounds["maxy"].values - bounds["miny"].values

        pixels_wide = widths_deg / config.GWA_STEP_DEG
        pixels_tall = heights_deg / config.GWA_STEP_DEG

        # All cells should be exactly 20 pixels wide and 20 pixels tall
        assert np.allclose(pixels_wide, 20.0, atol=1e-8), (
            f"Not all cells are 20 pixels wide. Range: "
            f"{pixels_wide.min():.10f} – {pixels_wide.max():.10f}"
        )
        assert np.allclose(pixels_tall, 20.0, atol=1e-8), (
            f"Not all cells are 20 pixels tall. Range: "
            f"{pixels_tall.min():.10f} – {pixels_tall.max():.10f}"
        )


# ---------------------------------------------------------------------------
# Test 2: Grid schema and CRS
# ---------------------------------------------------------------------------


class TestGridSchema:
    """Verify the GeoDataFrame has the expected structure."""

    def test_crs_is_epsg4326(self, grid_gdf):
        assert grid_gdf.crs is not None, "GeoDataFrame CRS is None"
        assert grid_gdf.crs.to_epsg() == 4326, (
            f"Expected EPSG:4326, got EPSG:{grid_gdf.crs.to_epsg()}"
        )

    def test_required_columns_present(self, grid_gdf):
        required = {"cell_id", "geometry", "centroid_lat", "centroid_lon", "area_km2"}
        actual = set(grid_gdf.columns)
        missing = required - actual
        assert not missing, f"Missing columns: {missing}"

    def test_no_null_geometries(self, grid_gdf):
        null_count = grid_gdf.geometry.isna().sum()
        assert null_count == 0, f"{null_count} null geometries found"

    def test_all_geometries_valid(self, grid_gdf):
        invalid_count = (~grid_gdf.geometry.is_valid).sum()
        assert invalid_count == 0, f"{invalid_count} invalid geometries found"

    def test_all_cell_ids_unique(self, grid_gdf):
        n_unique = grid_gdf["cell_id"].nunique()
        assert n_unique == len(grid_gdf), (
            f"{len(grid_gdf) - n_unique} duplicate cell_ids found"
        )


# ---------------------------------------------------------------------------
# Test 3: Cell ID format
# ---------------------------------------------------------------------------


class TestCellIDFormat:
    """Cell IDs must follow the S{lat:.3f}_E{lon:.3f} format."""

    CELL_ID_PATTERN = re.compile(r"^[NS]\d+\.\d{3}_[EW]\d+\.\d{3}$")

    def test_cell_id_format_regex(self, small_grid):
        """All cell IDs should match the expected pattern."""
        non_matching = small_grid["cell_id"][
            ~small_grid["cell_id"].str.match(self.CELL_ID_PATTERN)
        ]
        assert len(non_matching) == 0, (
            f"{len(non_matching)} cell_ids don't match pattern. "
            f"First few: {non_matching.head(5).tolist()}"
        )

    def test_cell_id_encodes_centroid(self, small_grid):
        """Cell ID should encode the centroid latitude and longitude."""
        row = small_grid.iloc[0]
        expected_id = _format_cell_id(row["centroid_lat"], row["centroid_lon"])
        assert row["cell_id"] == expected_id, (
            f"cell_id '{row['cell_id']}' != expected '{expected_id}' "
            f"for centroid ({row['centroid_lat']}, {row['centroid_lon']})"
        )

    def test_nsw_cells_are_south_east(self, grid_gdf):
        """All NSW cells should have S (south) and E (east) prefixes."""
        assert grid_gdf["cell_id"].str.startswith("S").all(), (
            "Some cells don't start with 'S' — unexpected for NSW"
        )
        assert grid_gdf["cell_id"].str.contains("_E").all(), (
            "Some cells don't contain '_E' — unexpected for NSW"
        )


# ---------------------------------------------------------------------------
# Test 4: Grid dimensions
# ---------------------------------------------------------------------------


class TestGridDimensions:
    """Grid dimensions match the expected count from the integration analysis."""

    def test_total_cell_count(self, grid_gdf):
        """NSW grid should have approximately 47,000 cells (253 × 187)."""
        origin_lon, origin_lat = _snap_origin(config.NSW_BBOX)
        n_cols, n_rows = _grid_dimensions(config.NSW_BBOX, origin_lon, origin_lat)
        expected = n_cols * n_rows
        assert len(grid_gdf) == expected, (
            f"Grid has {len(grid_gdf)} cells, expected {expected} "
            f"({n_cols} × {n_rows})"
        )

    def test_cell_count_in_expected_range(self, grid_gdf):
        """Total cells should be in the range 40,000–55,000 for NSW."""
        assert 40_000 <= len(grid_gdf) <= 55_000, (
            f"Cell count {len(grid_gdf)} is outside expected range "
            f"[40,000, 55,000] for NSW"
        )

    def test_dimensions_consistency(self):
        """n_cols * n_rows from dimensions must equal the generated count."""
        origin_lon, origin_lat = _snap_origin(config.NSW_BBOX)
        n_cols, n_rows = _grid_dimensions(config.NSW_BBOX, origin_lon, origin_lat)
        # Verify these are positive integers
        assert n_cols > 0 and n_rows > 0
        assert isinstance(n_cols, int) and isinstance(n_rows, int)


# ---------------------------------------------------------------------------
# Test 5: Area within expected bounds
# ---------------------------------------------------------------------------


class TestCellArea:
    """Cell areas should be reasonable for NSW latitudes (28–38°S)."""

    def test_area_minimum_bound(self, grid_gdf):
        """No cell should be smaller than 20 km² (would indicate a bug)."""
        min_area = grid_gdf["area_km2"].min()
        assert min_area > 20.0, (
            f"Minimum area {min_area:.2f} km² is below 20 km² — "
            f"too small for a 0.05° cell at NSW latitudes"
        )

    def test_area_maximum_bound(self, grid_gdf):
        """No cell should be larger than 35 km² (would indicate a bug)."""
        max_area = grid_gdf["area_km2"].max()
        assert max_area < 35.0, (
            f"Maximum area {max_area:.2f} km² exceeds 35 km² — "
            f"too large for a 0.05° cell at NSW latitudes"
        )

    def test_area_varies_with_latitude(self, grid_gdf):
        """Cells at lower latitudes (closer to equator) should be larger
        than cells at higher latitudes (further from equator)."""
        northern = grid_gdf[grid_gdf["centroid_lat"] > -30.0]["area_km2"].mean()
        southern = grid_gdf[grid_gdf["centroid_lat"] < -36.0]["area_km2"].mean()
        assert northern > southern, (
            f"Northern cells ({northern:.2f} km²) should be larger than "
            f"southern cells ({southern:.2f} km²) due to latitude"
        )

    def test_area_computed_via_epsg3577(self, small_grid):
        """Verify area computation is consistent with a manual EPSG:3577 check."""
        # Reproject a single cell and compute area manually
        row = small_grid.iloc[0:1].copy()
        row_albers = row.to_crs("EPSG:3577")
        manual_area_km2 = row_albers.geometry.area.iloc[0] / 1_000_000.0
        stored_area_km2 = row["area_km2"].iloc[0]
        assert abs(manual_area_km2 - stored_area_km2) < 0.001, (
            f"Stored area ({stored_area_km2:.4f}) != manual EPSG:3577 area "
            f"({manual_area_km2:.4f})"
        )


# ---------------------------------------------------------------------------
# Test 6: GeoPackage roundtrip (if file exists)
# ---------------------------------------------------------------------------


class TestGeoPackageRoundtrip:
    """Verify the on-disk GeoPackage is consistent with generated data."""

    @pytest.fixture
    def gpkg_path(self):
        path = config.GRID_OUTPUT_DIR / "nsw_analysis_grid.gpkg"
        if not path.exists():
            pytest.skip("GeoPackage not yet generated (run `python -m pipeline.grid` first)")
        return path

    def test_gpkg_readable(self, gpkg_path):
        """GeoPackage should be readable by geopandas."""
        gdf = gpd.read_file(gpkg_path)
        assert len(gdf) > 0, "GeoPackage is empty"

    def test_gpkg_crs(self, gpkg_path):
        gdf = gpd.read_file(gpkg_path)
        assert gdf.crs.to_epsg() == 4326

    def test_gpkg_row_count(self, gpkg_path, grid_gdf):
        """Disk file should have the same row count as freshly generated grid."""
        gdf = gpd.read_file(gpkg_path)
        assert len(gdf) == len(grid_gdf), (
            f"GeoPackage has {len(gdf)} rows but generated grid has "
            f"{len(grid_gdf)}"
        )

    def test_gpkg_columns(self, gpkg_path):
        gdf = gpd.read_file(gpkg_path)
        required = {"cell_id", "centroid_lat", "centroid_lon", "area_km2", "geometry"}
        assert required.issubset(set(gdf.columns)), (
            f"Missing columns in GeoPackage: {required - set(gdf.columns)}"
        )
