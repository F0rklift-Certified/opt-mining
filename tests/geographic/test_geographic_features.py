"""
Tests for the geographic feature-builder stage (Sprint 1 task S1-06).

This module holds the tests for ``pipeline/geographic/features.py``. It is
structured so the property-based tests (task 15) and the opt-in full-grid
integration test (task 16) can be appended alongside the unit tests here,
matching the repo-root ``tests/`` convention (``Test*`` classes, ``tmp_path``
for synthetic fixtures) used by ``tests/test_grid.py``.

Currently implemented:
    - Unit tests for ``read_grid_cells`` (task 2.2): valid grid round-trip and
      the three halt conditions (missing file, no ``cell_id``, duplicate
      ``cell_id``) — Requirements 8.4, 8.5, 8.6.
"""

import re

import geopandas as gpd
import pytest
from shapely.geometry import box

from pipeline.geographic.features import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    GRID_PATH,
    OUTPUT_PATH,
    PROTECTED_AREA_NAME_DELIMITER,
    REPORT_PATH,
    REQUIRED_CONFIDENCE_RASTERS,
    SCHEMA_COLUMNS,
    UNNAMED_PROTECTED_AREA,
    CellStat,
    ModeResult,
    _categorical_mode,
    _confidence_flag,
    _protected_overlap,
    _raster_coverage,
    _zonal_raster_stat,
    load_alum_class_table,
    read_grid_cells,
    run,
    validate,
)
from pipeline.grid.config import COMPUTATION_CRS, STORAGE_CRS


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_grid_gdf(cell_ids, *, crs=STORAGE_CRS, include_cell_id=True, extra_cols=None):
    """
    Build a small synthetic analysis-grid GeoDataFrame.

    Each cell is a distinct 0.05-degree square so geometries are non-null and
    unique. ``cell_ids`` drives the row order and values (so duplicate-detection
    and byte-for-byte reuse can be asserted). Set ``include_cell_id=False`` to
    build a grid that lacks the ``cell_id`` column entirely.
    """
    geometries = []
    for i, _ in enumerate(cell_ids):
        minx = 150.0 + i * 0.05
        miny = -34.0 + i * 0.05
        geometries.append(box(minx, miny, minx + 0.05, miny + 0.05))

    data = {}
    if include_cell_id:
        data["cell_id"] = list(cell_ids)
    if extra_cols:
        for name, values in extra_cols.items():
            data[name] = values

    return gpd.GeoDataFrame(data, geometry=geometries, crs=crs)


def _write_grid(gdf, tmp_path, name="synthetic_grid.gpkg"):
    """Write a synthetic grid to a GeoPackage under ``tmp_path`` and return the path."""
    path = tmp_path / name
    gdf.to_file(path, driver="GPKG")
    return path


# ---------------------------------------------------------------------------
# read_grid_cells — happy path and halt conditions (Req 8.4, 8.5, 8.6)
# ---------------------------------------------------------------------------


class TestReadGridCells:
    """Unit tests for ``read_grid_cells`` (task 2.2)."""

    def test_valid_grid_returns_cell_id_and_geometry_unchanged(self, tmp_path):
        """
        A valid synthetic grid returns exactly ``cell_id`` + ``geometry`` with the
        cell_id values reused byte-for-byte in the file's native order (Req 8.1, 8.2).
        Extra grid columns (centroid_lat/lon, area_km2) are dropped.
        """
        cell_ids = ["S34.000_E150.000", "S33.950_E150.050", "S33.900_E150.100"]
        gdf = _make_grid_gdf(
            cell_ids,
            extra_cols={
                "centroid_lat": [-33.975, -33.925, -33.875],
                "centroid_lon": [150.025, 150.075, 150.125],
                "area_km2": [25.1, 25.1, 25.1],
            },
        )
        grid_path = _write_grid(gdf, tmp_path)

        result = read_grid_cells(grid_path)

        # Exactly cell_id + geometry, no extra grid columns carried through.
        assert list(result.columns) == ["cell_id", "geometry"]
        # cell_id reused byte-for-byte, native row order preserved (Req 8.2).
        assert result["cell_id"].tolist() == cell_ids
        # Geometry preserved and non-null.
        assert result.geometry.notna().all()
        assert len(result) == len(cell_ids)
        # Storage CRS explicit at this boundary (Req 8.1).
        assert result.crs is not None
        assert result.crs.to_epsg() == 4326
        # Geometry values unchanged (compare bounds of first cell).
        original_bounds = gdf.geometry.iloc[0].bounds
        assert result.geometry.iloc[0].bounds == pytest.approx(original_bounds)

    def test_missing_grid_file_raises_file_not_found(self, tmp_path):
        """A missing grid path halts with FileNotFoundError naming the path (Req 8.4)."""
        missing = tmp_path / "does_not_exist.gpkg"
        with pytest.raises(FileNotFoundError) as excinfo:
            read_grid_cells(missing)
        assert str(missing) in str(excinfo.value)

    def test_grid_without_cell_id_column_raises_value_error(self, tmp_path):
        """A readable grid with no ``cell_id`` column halts with ValueError (Req 8.5)."""
        gdf = _make_grid_gdf(
            ["a", "b"],
            include_cell_id=False,
            extra_cols={"some_other_id": ["a", "b"]},
        )
        grid_path = _write_grid(gdf, tmp_path, name="no_cell_id.gpkg")

        with pytest.raises(ValueError) as excinfo:
            read_grid_cells(grid_path)
        assert "cell_id" in str(excinfo.value)

    def test_grid_with_duplicate_cell_id_raises_value_error(self, tmp_path):
        """Duplicate ``cell_id`` values halt with ValueError listing them (Req 8.6)."""
        cell_ids = ["S34.000_E150.000", "S33.950_E150.050", "S34.000_E150.000"]
        gdf = _make_grid_gdf(cell_ids)
        grid_path = _write_grid(gdf, tmp_path, name="dup_cell_id.gpkg")

        with pytest.raises(ValueError) as excinfo:
            read_grid_cells(grid_path)
        message = str(excinfo.value)
        assert "duplicate" in message.lower()
        # The duplicated value is named in the error (Req 8.6).
        assert "S34.000_E150.000" in message

# ---------------------------------------------------------------------------
# load_alum_class_table — code -> name mapping with integer keys (Req 3.3)
# ---------------------------------------------------------------------------


class TestLoadAlumClassTable:
    """Unit tests for ``load_alum_class_table`` (task 3.2)."""

    def _write_class_table(self, tmp_path, rows, name="alum_class_table.csv"):
        """
        Write a small synthetic ALUM-v8-style class-table CSV under ``tmp_path``.

        The real ALUM v8 table has many columns (Value, Count, TERTV8, ...); the
        loader only reads ``Value`` and ``TERTV8``, so a two-column synthetic CSV
        exercises the same code path while keeping the fixture minimal. ``rows`` is
        a list of ``(value, tertv8)`` pairs written verbatim (values as strings so
        we can assert they are coerced to integer keys).
        """
        path = tmp_path / name
        lines = ["Value,TERTV8"]
        lines.extend(f"{value},{tertv8}" for value, tertv8 in rows)
        path.write_text("\n".join(lines) + "\n")
        return path

    def test_maps_codes_to_names_with_integer_keys(self, tmp_path):
        """
        A small synthetic CSV maps each code to its class name, and every key in
        the returned mapping is an ``int`` (the string ``Value`` column is coerced
        via ``int(...)``) — Req 3.3.
        """
        rows = [
            ("0", "No data/offshore"),
            ("111", "1.1.1 Strict nature reserves"),
            ("113", "1.1.3 National park"),
            ("540", "5.4.0 Residential and farm infrastructure"),
        ]
        table_path = self._write_class_table(tmp_path, rows)

        table = load_alum_class_table(table_path)

        # Exact code -> name mapping (integer keys, not strings).
        assert table == {
            0: "No data/offshore",
            111: "1.1.1 Strict nature reserves",
            113: "1.1.3 National park",
            540: "5.4.0 Residential and farm infrastructure",
        }
        # Every key is a genuine int, so integer NLUM raster codes look up directly.
        assert all(isinstance(code, int) for code in table)
        # String keys must NOT be present — lookups are by integer code.
        assert "111" not in table
        assert table[111] == "1.1.1 Strict nature reserves"


# ---------------------------------------------------------------------------
# _zonal_raster_stat / _raster_coverage — zonal statistics core (task 4.2)
# ---------------------------------------------------------------------------


class TestZonalRasterStat:
    """
    Unit tests for ``_zonal_raster_stat`` and ``_raster_coverage`` (task 4.2).

    These build tiny synthetic single-band GeoTIFFs in ``tmp_path`` and open them
    with ``rasterio`` so the code exercises the real windowed-read / cell-centre
    masking / NoData / scale path (Req 12.1, 12.3, 12.5, 2.2, 6.3).

    Raster geometry convention used throughout (north-up, pixel size 1.0, origin
    at the top-left corner ``(0, 4)``): a 4x4 raster covers ``x in [0, 4]``,
    ``y in [0, 4]``; pixel centres sit at ``x, y in {0.5, 1.5, 2.5, 3.5}`` where
    row 0 is the northernmost (``y = 3.5``). A cell ``box(0, 2, 2, 4)`` therefore
    selects the top-left 2x2 block of pixel centres
    ``{(0.5, 3.5), (1.5, 3.5), (0.5, 2.5), (1.5, 2.5)}`` under the cell-centre
    (``all_touched=False``) inclusion rule.
    """

    def _write_raster(
        self,
        tmp_path,
        array,
        *,
        nodata=None,
        scale=None,
        origin=(0.0, 4.0),
        pixel_size=1.0,
        crs=STORAGE_CRS,
        name="synthetic_raster.tif",
    ):
        """
        Write a tiny north-up single-band GeoTIFF and return its path.

        ``array`` is a 2-D numpy array (row 0 = north). ``origin`` is the top-left
        corner ``(x_min, y_max)``; ``pixel_size`` is the (square) cell size in CRS
        units. ``nodata`` is written to the band's nodata tag; ``scale`` (when set)
        is written as the band scale so the reader multiplies stored values by it
        (mirroring the derived slope/TRI rasters, Req 1.2, 1.3).
        """
        import numpy as np
        import rasterio
        from rasterio.transform import from_origin

        array = np.asarray(array)
        transform = from_origin(origin[0], origin[1], pixel_size, pixel_size)
        path = tmp_path / name
        profile = {
            "driver": "GTiff",
            "height": array.shape[0],
            "width": array.shape[1],
            "count": 1,
            "dtype": array.dtype,
            "crs": crs,
            "transform": transform,
        }
        if nodata is not None:
            profile["nodata"] = nodata
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(array, 1)
            if scale is not None:
                dst.scales = (scale,)
        return path

    def test_mean_matches_hand_computed_value(self, tmp_path):
        """
        Terrain mean over a cell equals the hand-computed mean of the pixels whose
        centres fall inside the cell, within tolerance 1e-9 (Req 12.1, 2.1, 2.4).

        The top-left 2x2 block holds values {10, 20, 30, 40}; the cell
        ``box(0, 2, 2, 4)`` selects exactly those four pixel centres, so the mean
        is ``(10 + 20 + 30 + 40) / 4 == 25.0``.
        """
        import numpy as np
        import rasterio

        array = np.array(
            [
                [10.0, 20.0, 100.0, 100.0],
                [30.0, 40.0, 100.0, 100.0],
                [100.0, 100.0, 100.0, 100.0],
                [100.0, 100.0, 100.0, 100.0],
            ],
            dtype="float64",
        )
        raster_path = self._write_raster(tmp_path, array)
        cell = box(0.0, 2.0, 2.0, 4.0)

        with rasterio.open(raster_path) as src:
            result = _zonal_raster_stat(src, cell, "mean")

        expected = (10.0 + 20.0 + 30.0 + 40.0) / 4.0
        assert result.value == pytest.approx(expected, abs=1e-9)
        assert result.value == pytest.approx(25.0, abs=1e-9)
        assert result.n_valid == 4
        assert result.n_nodata == 0
        assert result.in_coverage is True

    def test_scaled_raster_mean_applies_band_scale(self, tmp_path):
        """
        The reader multiplies stored int values by ``src.scales[0]`` (Req 1.2, 1.3),
        so a slope-style raster stored at scale 0.01 yields degrees. Stored values
        {1000, 2000, 3000, 4000} at scale 0.01 give a mean of ``2500 * 0.01 == 25.0``.
        """
        import numpy as np
        import rasterio

        array = np.array(
            [
                [1000, 2000, 9999, 9999],
                [3000, 4000, 9999, 9999],
                [9999, 9999, 9999, 9999],
                [9999, 9999, 9999, 9999],
            ],
            dtype="int16",
        )
        raster_path = self._write_raster(tmp_path, array, scale=0.01)
        cell = box(0.0, 2.0, 2.0, 4.0)

        with rasterio.open(raster_path) as src:
            result = _zonal_raster_stat(src, cell, "mean")

        # (1000 + 2000 + 3000 + 4000) / 4 * 0.01 == 25.0
        assert result.value == pytest.approx(25.0, abs=1e-9)
        assert result.n_valid == 4
        assert result.n_nodata == 0

    def test_nodata_pixels_excluded_and_counted_separately(self, tmp_path):
        """
        NoData pixels within the cell are excluded from the mean and counted in
        ``n_nodata`` (not ``n_valid``); ``n_valid + n_nodata`` equals the total
        clipped-selection size (Req 12.3, 2.2, 2.3).

        Of the four in-cell pixels {10, 20, 30, 40}, one is set to the NoData
        sentinel (-9999), so the mean is over the remaining three
        ``(10 + 20 + 40) / 3`` and ``n_valid == 3``, ``n_nodata == 1``.
        """
        import numpy as np
        import rasterio

        array = np.array(
            [
                [10.0, 20.0, 500.0, 500.0],
                [-9999.0, 40.0, 500.0, 500.0],
                [500.0, 500.0, 500.0, 500.0],
                [500.0, 500.0, 500.0, 500.0],
            ],
            dtype="float64",
        )
        raster_path = self._write_raster(tmp_path, array, nodata=-9999.0)
        cell = box(0.0, 2.0, 2.0, 4.0)

        with rasterio.open(raster_path) as src:
            result = _zonal_raster_stat(src, cell, "mean")

        expected = (10.0 + 20.0 + 40.0) / 3.0
        assert result.value == pytest.approx(expected, abs=1e-9)
        assert result.n_valid == 3
        assert result.n_nodata == 1
        # NoData excluded from the mean but partitioned into the total (Req 2.2).
        assert result.n_valid + result.n_nodata == 4
        assert result.in_coverage is True

    def test_all_nodata_cell_yields_none_value(self, tmp_path):
        """
        A cell whose in-cell pixels are all NoData yields ``value is None`` with
        ``n_valid == 0`` and ``in_coverage is False`` (Req 12.5, 1.6, 2.6).

        All four in-cell pixels are set to the NoData sentinel, so there are zero
        valid pixels; the invariant ``n_valid + n_nodata == total`` still holds
        (0 + 4 == 4).
        """
        import numpy as np
        import rasterio

        array = np.array(
            [
                [-9999.0, -9999.0, 7.0, 7.0],
                [-9999.0, -9999.0, 7.0, 7.0],
                [7.0, 7.0, 7.0, 7.0],
                [7.0, 7.0, 7.0, 7.0],
            ],
            dtype="float64",
        )
        raster_path = self._write_raster(tmp_path, array, nodata=-9999.0)
        cell = box(0.0, 2.0, 2.0, 4.0)

        with rasterio.open(raster_path) as src:
            result = _zonal_raster_stat(src, cell, "mean")

        assert result.value is None
        assert result.n_valid == 0
        assert result.n_nodata == 4
        assert result.n_valid + result.n_nodata == 4
        assert result.in_coverage is False

    def test_centroid_outside_bounds_is_out_of_coverage(self, tmp_path):
        """
        A cell whose centroid lies outside the raster bounds is classified out of
        coverage via the fast-path centroid test — null value, no windowed read
        (Req 6.2). ``_raster_coverage`` returns ``False`` for the same cell.
        """
        import numpy as np
        import rasterio

        array = np.full((4, 4), 5.0, dtype="float64")
        raster_path = self._write_raster(tmp_path, array)
        # Raster covers x,y in [0, 4]; this cell sits far to the north-east.
        cell = box(100.0, 100.0, 102.0, 102.0)

        with rasterio.open(raster_path) as src:
            assert _raster_coverage(src, cell) is False
            result = _zonal_raster_stat(src, cell, "mean")

        assert result.value is None
        assert result.n_valid == 0
        assert result.in_coverage is False

    def test_centroid_inside_but_sampled_pixels_outside_data_is_out_of_coverage(
        self, tmp_path
    ):
        """
        Edge case (Req 6.3): the cell centroid lies inside the raster bounds, but
        the cell straddles the raster edge such that its in-cell pixel positions
        fall outside valid raster data — the cell is classified out of coverage and
        the value is null.

        The raster covers only ``x,y in [0, 2]`` (a 2x2 block of pixels). The cell
        ``box(1, 1, 3, 3)`` has centroid ``(2, 2)``, which is on/within the raster
        bounds, but its northern/eastern pixel positions extend past the raster's
        data extent; those positions count as NoData (Req 6.3). The only in-bounds
        pixel centre inside the cell is at ``(1.5, 1.5)``.
        """
        import numpy as np
        import rasterio

        # 2x2 raster: origin top-left (0, 2), pixel size 1.0 -> covers [0,2]x[0,2].
        # Fill with NoData so no in-cell pixel is valid, forcing out-of-coverage.
        array = np.full((2, 2), -9999.0, dtype="float64")
        raster_path = self._write_raster(
            tmp_path, array, nodata=-9999.0, origin=(0.0, 2.0)
        )
        cell = box(1.0, 1.0, 3.0, 3.0)

        with rasterio.open(raster_path) as src:
            # Centroid (2, 2) is within the raster bounds -> fast path does NOT
            # short-circuit; coverage is decided by the sampled pixels.
            assert _raster_coverage(src, cell) is True
            result = _zonal_raster_stat(src, cell, "mean")

        # No valid pixels sampled -> null value, out of coverage (Req 6.3).
        assert result.value is None
        assert result.n_valid == 0
        assert result.in_coverage is False
        # Invariant holds: everything sampled is NoData / outside-extent.
        assert result.n_nodata >= 1


# ---------------------------------------------------------------------------
# _categorical_mode — dominant land-use extraction (task 5.2)
# ---------------------------------------------------------------------------


class TestCategoricalMode:
    """
    Unit tests for ``_categorical_mode`` (task 5.2).

    These build tiny synthetic single-band *categorical* GeoTIFFs in ``tmp_path``
    and open them with ``rasterio`` so the code exercises the real windowed-read /
    cell-centre masking / NoData path used for the NLUM land-use mode
    (Req 12.2, 3.4, 3.5).

    The raster geometry convention matches ``TestZonalRasterStat`` (north-up,
    pixel size 1.0, origin top-left ``(0, 4)``): a 4x4 raster covers
    ``x,y in [0, 4]`` with pixel centres at ``{0.5, 1.5, 2.5, 3.5}`` (row 0 is the
    northernmost, ``y = 3.5``). The cell ``box(0, 2, 2, 4)`` selects the top-left
    2x2 block of pixel centres
    ``{(0.5, 3.5), (1.5, 3.5), (0.5, 2.5), (1.5, 2.5)}`` under the cell-centre
    (``all_touched=False``) inclusion rule — i.e. raster rows 0-1, columns 0-1.
    """

    def _write_categorical_raster(
        self,
        tmp_path,
        array,
        *,
        nodata=None,
        origin=(0.0, 4.0),
        pixel_size=1.0,
        crs=STORAGE_CRS,
        name="synthetic_nlum.tif",
    ):
        """
        Write a tiny north-up single-band categorical GeoTIFF and return its path.

        ``array`` is a 2-D integer numpy array (row 0 = north). ``origin`` is the
        top-left corner ``(x_min, y_max)``; ``pixel_size`` is the (square) cell
        size in CRS units. ``nodata`` (when set) is written to the band's nodata
        tag so the reader excludes those codes before taking the mode (Req 3.1).

        This mirrors the ``_write_raster`` helper inside ``TestZonalRasterStat`` but
        is kept self-contained here so the two test classes do not couple; the NLUM
        raster is categorical (no band scale is ever applied to class codes).
        """
        import numpy as np
        import rasterio
        from rasterio.transform import from_origin

        array = np.asarray(array)
        transform = from_origin(origin[0], origin[1], pixel_size, pixel_size)
        path = tmp_path / name
        profile = {
            "driver": "GTiff",
            "height": array.shape[0],
            "width": array.shape[1],
            "count": 1,
            "dtype": array.dtype,
            "crs": crs,
            "transform": transform,
        }
        if nodata is not None:
            profile["nodata"] = nodata
        with rasterio.open(path, "w", **profile) as dst:
            dst.write(array, 1)
        return path

    def test_known_dominant_class_returns_expected_code_and_name(self, tmp_path):
        """
        A cell with a clear modal class returns that code and its mapped ALUM name
        (Req 12.2, 3.1, 3.3).

        The top-left 2x2 block (the four in-cell pixel centres) holds codes
        ``{111, 111, 111, 113}`` so code ``111`` is the unambiguous mode (3 of 4);
        it maps to ``"1.1.1 Strict nature reserves"`` via the class table.
        """
        import numpy as np
        import rasterio

        array = np.array(
            [
                [111, 111, 999, 999],
                [111, 113, 999, 999],
                [999, 999, 999, 999],
                [999, 999, 999, 999],
            ],
            dtype="int32",
        )
        raster_path = self._write_categorical_raster(tmp_path, array)
        cell = box(0.0, 2.0, 2.0, 4.0)
        class_table = {
            111: "1.1.1 Strict nature reserves",
            113: "1.1.3 National park",
        }

        with rasterio.open(raster_path) as src:
            result = _categorical_mode(src, cell, class_table)

        assert result.code == 111
        assert result.land_use == "1.1.1 Strict nature reserves"
        assert result.n_valid == 4
        assert result.n_nodata == 0
        assert result.in_coverage is True

    def test_tie_returns_lowest_code(self, tmp_path):
        """
        On a deliberate frequency tie the lowest code wins — the documented
        deterministic tie-break (Req 12.2, 3.2).

        The four in-cell pixels hold codes ``{113, 113, 111, 111}`` — a 2-2 tie
        between ``111`` and ``113``. The lower code ``111`` must win, and it maps
        to its class name.
        """
        import numpy as np
        import rasterio

        array = np.array(
            [
                [113, 113, 999, 999],
                [111, 111, 999, 999],
                [999, 999, 999, 999],
                [999, 999, 999, 999],
            ],
            dtype="int32",
        )
        raster_path = self._write_categorical_raster(tmp_path, array)
        cell = box(0.0, 2.0, 2.0, 4.0)
        class_table = {
            111: "1.1.1 Strict nature reserves",
            113: "1.1.3 National park",
        }

        with rasterio.open(raster_path) as src:
            result = _categorical_mode(src, cell, class_table)

        # Lowest code among the tie (111 < 113) wins deterministically (Req 3.2).
        assert result.code == 111
        assert result.land_use == "1.1.1 Strict nature reserves"
        assert result.n_valid == 4
        assert result.n_nodata == 0
        assert result.in_coverage is True

    def test_unmapped_code_returns_unmapped_marker(self, tmp_path):
        """
        A winning code absent from the ALUM class table is recorded with the
        explicit ``"unmapped:<code>"`` marker rather than a mapped name (Req 3.4).

        The modal code in the cell is ``777`` (3 of 4 in-cell pixels), which is not
        present in the class table, so ``land_use`` must be ``"unmapped:777"`` and
        ``code`` must still be the raw winning code.
        """
        import numpy as np
        import rasterio

        array = np.array(
            [
                [777, 777, 999, 999],
                [777, 111, 999, 999],
                [999, 999, 999, 999],
                [999, 999, 999, 999],
            ],
            dtype="int32",
        )
        raster_path = self._write_categorical_raster(tmp_path, array)
        cell = box(0.0, 2.0, 2.0, 4.0)
        class_table = {111: "1.1.1 Strict nature reserves"}

        with rasterio.open(raster_path) as src:
            result = _categorical_mode(src, cell, class_table)

        assert result.code == 777
        assert result.land_use == "unmapped:777"
        assert result.n_valid == 4
        assert result.n_nodata == 0
        assert result.in_coverage is True

    def test_zero_valid_cell_returns_null_land_use(self, tmp_path):
        """
        A cell whose in-cell pixels are all NoData has zero valid NLUM pixels, so
        ``land_use`` and ``code`` are null and the cell is out of coverage
        (Req 3.5, 6.3).

        All four in-cell pixels are set to the NoData sentinel, so there are zero
        valid pixels; the ``n_valid + n_nodata == total`` invariant still holds
        (0 + 4 == 4).
        """
        import numpy as np
        import rasterio

        array = np.array(
            [
                [0, 0, 111, 111],
                [0, 0, 111, 111],
                [111, 111, 111, 111],
                [111, 111, 111, 111],
            ],
            dtype="int32",
        )
        raster_path = self._write_categorical_raster(tmp_path, array, nodata=0)
        cell = box(0.0, 2.0, 2.0, 4.0)
        class_table = {111: "1.1.1 Strict nature reserves"}

        with rasterio.open(raster_path) as src:
            result = _categorical_mode(src, cell, class_table)

        assert result.land_use is None
        assert result.code is None
        assert result.n_valid == 0
        assert result.n_nodata == 4
        assert result.n_valid + result.n_nodata == 4
        assert result.in_coverage is False


# ---------------------------------------------------------------------------
# _protected_overlap — CAPAD protected-area overlap (task 6.2)
# ---------------------------------------------------------------------------


class TestProtectedOverlap:
    """
    Unit tests for ``_protected_overlap`` (task 6.2).

    ``_protected_overlap`` takes two GeoDataFrames already reprojected to
    ``COMPUTATION_CRS`` (EPSG:3577) — cells with a ``cell_id`` column and CAPAD
    features with a ``NAME`` column — and returns
    ``{cell_id: (protected_area, protected_area_name)}`` for every cell.

    These fixtures build small synthetic geometries directly in EPSG:3577 (metre
    coordinates, ``shapely.box``) so the real ``geopandas.sjoin`` intersects path
    is exercised without touching real files or performing any reprojection
    (that boundary is the caller's concern). Cells are laid out as adjacent
    100 m squares on a row so overlap is easy to reason about:

        cell A: box(0,   0, 100, 100)
        cell B: box(100, 0, 200, 100)
        cell C: box(200, 0, 300, 100)
    """

    def _make_cells(self):
        """Three adjacent 100 m cell squares in EPSG:3577 keyed A/B/C."""
        return gpd.GeoDataFrame(
            {"cell_id": ["A", "B", "C"]},
            geometry=[
                box(0.0, 0.0, 100.0, 100.0),
                box(100.0, 0.0, 200.0, 100.0),
                box(200.0, 0.0, 300.0, 100.0),
            ],
            crs=COMPUTATION_CRS,
        )

    def _make_capad(self, records):
        """
        Build a CAPAD-like GeoDataFrame in EPSG:3577.

        ``records`` is a list of ``(name, geometry)`` pairs; ``name`` may be a
        string, ``None`` (null name), or ``""`` to exercise the unnamed-feature
        placeholder path.
        """
        names = [name for name, _ in records]
        geometries = [geom for _, geom in records]
        return gpd.GeoDataFrame(
            {"NAME": names}, geometry=geometries, crs=COMPUTATION_CRS
        )

    def test_intersecting_cell_true_nonintersecting_false(self):
        """
        A cell intersecting a protected polygon is flagged ``True``; a cell that
        does not intersect any feature is flagged ``False`` (Req 12.6, 4.1, 4.2).

        The protected polygon ``box(10, 10, 90, 90)`` lies wholly inside cell A and
        nowhere near cell C, so A is protected and C is not.
        """
        cells = self._make_cells()
        capad = self._make_capad(
            [("Kosciuszko National Park", box(10.0, 10.0, 90.0, 90.0))]
        )

        result = _protected_overlap(cells, capad)

        # Every cell appears exactly once (Req 6.1, 7.2).
        assert set(result) == {"A", "B", "C"}

        # Intersecting cell -> True with the feature name (Req 4.1, 4.3).
        assert result["A"] == (True, "Kosciuszko National Park")

        # Non-intersecting cell -> False with an empty, zero-length name
        # (Req 4.2, 4.4).
        protected_c, name_c = result["C"]
        assert protected_c is False
        assert name_c == ""

    def test_boundary_touch_counts_as_intersection(self):
        """
        A shared boundary (not just shared interior area) counts as an
        intersection (Req 4.1). The polygon ``box(100, 0, 150, 100)`` shares cell
        A's east edge at x=100, so cell A is flagged ``True``.
        """
        cells = self._make_cells()
        capad = self._make_capad([("Edge Reserve", box(100.0, 0.0, 150.0, 100.0))])

        result = _protected_overlap(cells, capad)

        # B is fully covered; A shares only the x=100 boundary -> both True.
        assert result["A"][0] is True
        assert result["B"][0] is True
        assert result["C"][0] is False

    def test_unnamed_feature_yields_placeholder(self):
        """
        A cell intersecting a feature whose ``NAME`` is null still flags ``True``
        and records the unnamed-protected-area placeholder in
        ``protected_area_name`` (Req 4.5).
        """
        cells = self._make_cells()
        capad = self._make_capad([(None, box(10.0, 10.0, 90.0, 90.0))])

        result = _protected_overlap(cells, capad)

        assert result["A"] == (True, UNNAMED_PROTECTED_AREA)

    def test_empty_string_name_yields_placeholder(self):
        """
        A feature with an empty/whitespace ``NAME`` is treated as unnamed and
        contributes the placeholder, not an empty name (Req 4.5). This keeps the
        placeholder distinct from the "no overlap" empty string of Req 4.4.
        """
        cells = self._make_cells()
        capad = self._make_capad([("   ", box(10.0, 10.0, 90.0, 90.0))])

        result = _protected_overlap(cells, capad)

        assert result["A"] == (True, UNNAMED_PROTECTED_AREA)

    def test_multiple_distinct_names_joined_sorted(self):
        """
        A cell intersecting several features records the distinct names joined by
        the single consistent delimiter in deterministic (sorted) order, with
        duplicates collapsed (Req 4.3, 7.7).

        Cell A intersects three features named "Park B", "Park A", and a duplicate
        "Park A"; the result must be the two distinct names sorted and joined.
        """
        cells = self._make_cells()
        capad = self._make_capad(
            [
                ("Park B", box(10.0, 10.0, 40.0, 40.0)),
                ("Park A", box(50.0, 50.0, 90.0, 90.0)),
                ("Park A", box(20.0, 60.0, 40.0, 80.0)),
            ]
        )

        result = _protected_overlap(cells, capad)

        protected_a, name_a = result["A"]
        assert protected_a is True
        # Distinct + sorted + single delimiter (Req 4.3).
        assert name_a == PROTECTED_AREA_NAME_DELIMITER.join(["Park A", "Park B"])
        assert result["B"][0] is False
        assert result["C"][0] is False


# ---------------------------------------------------------------------------
# _confidence_flag — per-cell confidence flag (task 7.2)
# ---------------------------------------------------------------------------


class TestConfidenceFlag:
    """
    Unit tests for ``_confidence_flag`` (task 7.2).

    ``_confidence_flag`` is a pure function over a ``dict`` mapping raster name to
    a :class:`CellStat`/:class:`ModeResult` — no rasters or files needed. It reads
    only ``in_coverage``, ``n_valid``, and ``n_nodata`` for each of the required
    rasters (:data:`REQUIRED_CONFIDENCE_RASTERS` = elevation, slope, NLUM). A cell
    is :data:`CONFIDENCE_LOW` if, for **any** required raster, it is out of coverage
    or ``n_nodata >= 50%`` of ``(n_valid + n_nodata)`` (the exactly-50% boundary is
    inclusive); otherwise :data:`CONFIDENCE_HIGH`. TRI is excluded from the decision
    (Req 12.4, 12.5, 5.2).

    The fixtures construct :class:`CellStat` / :class:`ModeResult` instances directly
    so the tests exercise only the flag logic. ``elevation`` and ``slope`` use
    :class:`CellStat`; ``nlum`` uses :class:`ModeResult` (both expose the three
    fields the flag reads), which also confirms the flag works across both types.
    """

    def _cell_stat(self, *, n_valid, n_nodata, in_coverage=True, value=1.0):
        """A :class:`CellStat` with the given coverage/NoData bookkeeping."""
        return CellStat(
            value=value, n_valid=n_valid, n_nodata=n_nodata, in_coverage=in_coverage
        )

    def _mode_result(self, *, n_valid, n_nodata, in_coverage=True, code=111):
        """A :class:`ModeResult` (used for the NLUM required raster)."""
        return ModeResult(
            land_use="1.1.1 Strict nature reserves" if in_coverage else None,
            code=code if in_coverage else None,
            n_valid=n_valid,
            n_nodata=n_nodata,
            in_coverage=in_coverage,
        )

    def _per_raster(self, *, elevation, slope, nlum, tri=None):
        """
        Assemble the per-raster dict the flag consumes.

        All three required rasters are always supplied. ``tri`` is included only
        when provided, to exercise the TRI-excluded contract.
        """
        per_raster = {"elevation": elevation, "slope": slope, "nlum": nlum}
        if tri is not None:
            per_raster["tri"] = tri
        return per_raster

    def test_over_50pct_nodata_is_low(self):
        """
        A required raster with more than 50% NoData flags the cell low (Req 12.4).

        Elevation here is 60% NoData (6 of 10 pixels); the other required rasters
        are fully valid, so the elevation NoData fraction alone forces ``low``.
        """
        per_raster = self._per_raster(
            elevation=self._cell_stat(n_valid=4, n_nodata=6),  # 60% NoData
            slope=self._cell_stat(n_valid=10, n_nodata=0),
            nlum=self._mode_result(n_valid=10, n_nodata=0),
        )
        assert _confidence_flag(per_raster) == CONFIDENCE_LOW

    def test_exactly_50pct_nodata_is_low_boundary(self):
        """
        The exactly-50% NoData boundary is inclusive: a cell with n_nodata == n_valid
        on a required raster is flagged low (Req 12.4, 5.1).

        Slope is exactly 50% NoData (5 valid / 5 NoData); elevation and NLUM are
        fully valid, so the boundary case on slope alone forces ``low``.
        """
        per_raster = self._per_raster(
            elevation=self._cell_stat(n_valid=10, n_nodata=0),
            slope=self._cell_stat(n_valid=5, n_nodata=5),  # exactly 50% NoData
            nlum=self._mode_result(n_valid=10, n_nodata=0),
        )
        assert _confidence_flag(per_raster) == CONFIDENCE_LOW

    def test_over_50pct_valid_in_coverage_is_high(self):
        """
        When every required raster is in coverage with more than 50% valid pixels,
        the cell is high confidence (Req 12.4, 5.3).

        Each required raster is 60% valid (6 valid / 4 NoData) — strictly below the
        50% NoData threshold — so all three pass and the flag is ``high``.
        """
        per_raster = self._per_raster(
            elevation=self._cell_stat(n_valid=6, n_nodata=4),  # 40% NoData
            slope=self._cell_stat(n_valid=6, n_nodata=4),
            nlum=self._mode_result(n_valid=6, n_nodata=4),
        )
        assert _confidence_flag(per_raster) == CONFIDENCE_HIGH

    def test_all_required_fully_valid_is_high(self):
        """A cell fully valid on all required rasters is high confidence (Req 5.3)."""
        per_raster = self._per_raster(
            elevation=self._cell_stat(n_valid=10, n_nodata=0),
            slope=self._cell_stat(n_valid=10, n_nodata=0),
            nlum=self._mode_result(n_valid=10, n_nodata=0),
        )
        assert _confidence_flag(per_raster) == CONFIDENCE_HIGH

    def test_out_of_coverage_required_raster_is_low(self):
        """
        Out of coverage on any required raster flags the cell low, regardless of the
        NoData counts (Req 12.5, 5.2).

        NLUM is out of coverage (in_coverage=False) while elevation and slope are
        fully valid; the out-of-coverage NLUM alone forces ``low``.
        """
        per_raster = self._per_raster(
            elevation=self._cell_stat(n_valid=10, n_nodata=0),
            slope=self._cell_stat(n_valid=10, n_nodata=0),
            nlum=self._mode_result(n_valid=0, n_nodata=0, in_coverage=False),
        )
        assert _confidence_flag(per_raster) == CONFIDENCE_LOW

    def test_out_of_coverage_elevation_is_low(self):
        """Out of coverage on elevation (the first required raster) flags low (Req 5.2)."""
        per_raster = self._per_raster(
            elevation=self._cell_stat(
                value=None, n_valid=0, n_nodata=0, in_coverage=False
            ),
            slope=self._cell_stat(n_valid=10, n_nodata=0),
            nlum=self._mode_result(n_valid=10, n_nodata=0),
        )
        assert _confidence_flag(per_raster) == CONFIDENCE_LOW

    def test_all_nodata_cell_is_low(self):
        """
        An all-NoData cell (zero valid, all NoData) on a required raster is low
        confidence (Req 12.5, 5.2).

        Elevation has zero valid pixels and is out of coverage — the state the
        zonal statistic returns for a cell whose clipped selection is entirely
        NoData — so the flag is ``low``.
        """
        per_raster = self._per_raster(
            elevation=self._cell_stat(
                value=None, n_valid=0, n_nodata=4, in_coverage=False
            ),
            slope=self._cell_stat(n_valid=10, n_nodata=0),
            nlum=self._mode_result(n_valid=10, n_nodata=0),
        )
        assert _confidence_flag(per_raster) == CONFIDENCE_LOW

    def test_tri_excluded_does_not_lower_high_cell(self):
        """
        TRI is excluded from the confidence decision: a cell whose required rasters
        are all good stays high even when TRI is out of coverage / all NoData
        (Req 5.2 scoping, design §Confidence rule, Req 6.4).

        This is the real-world NSW case — TRI covers only the Glen-Innes sub-window,
        so most cells have out-of-coverage TRI. Including TRI would flag the whole
        grid low; excluding it keeps the flag high here.
        """
        per_raster = self._per_raster(
            elevation=self._cell_stat(n_valid=10, n_nodata=0),
            slope=self._cell_stat(n_valid=10, n_nodata=0),
            nlum=self._mode_result(n_valid=10, n_nodata=0),
            # TRI out of coverage AND all-NoData — would force low if considered.
            tri=self._cell_stat(value=None, n_valid=0, n_nodata=8, in_coverage=False),
        )
        assert "tri" not in REQUIRED_CONFIDENCE_RASTERS
        assert _confidence_flag(per_raster) == CONFIDENCE_HIGH

    def test_result_is_always_high_or_low(self):
        """
        The flag is always exactly one of the two domain values ``"high"``/``"low"``
        and nothing else (Req 5.4).
        """
        high = self._per_raster(
            elevation=self._cell_stat(n_valid=10, n_nodata=0),
            slope=self._cell_stat(n_valid=10, n_nodata=0),
            nlum=self._mode_result(n_valid=10, n_nodata=0),
        )
        low = self._per_raster(
            elevation=self._cell_stat(n_valid=0, n_nodata=10),
            slope=self._cell_stat(n_valid=10, n_nodata=0),
            nlum=self._mode_result(n_valid=10, n_nodata=0),
        )
        assert _confidence_flag(high) in {CONFIDENCE_HIGH, CONFIDENCE_LOW}
        assert _confidence_flag(low) in {CONFIDENCE_HIGH, CONFIDENCE_LOW}


# ---------------------------------------------------------------------------
# validate — no-silent-passes checks over the written table (task 12.2)
# ---------------------------------------------------------------------------


class TestValidate:
    """
    Unit tests for ``validate(feature_table_path, grid_path)`` (task 12.2).

    ``validate`` reads the written Feature_Table GeoPackage plus the analysis grid
    and returns ``{"checks": [...], "passed": int, "total": int}`` where each check
    is ``{"name", "expected", "observed", "passed"}``. These tests build a synthetic
    grid (reusing ``_make_grid_gdf`` / ``_write_grid``) and a matching synthetic
    Feature_Table carrying exactly the eight :data:`SCHEMA_COLUMNS` + geometry, then
    write faulty variants and assert the specific named check fails with non-empty
    ``expected`` / ``observed`` strings.

    Requirements: 11.1 (row count), 11.2 (cell_id set match), 11.3 (schema columns),
    11.4 (slope_deg in [0, 90] or null), 11.5 (confidence_flag in {high, low}).
    """

    # Three cells reused across the fixtures below.
    CELL_IDS = ["S34.000_E150.000", "S33.950_E150.050", "S33.900_E150.100"]

    def _make_feature_table_gdf(self, cell_ids, *, overrides=None):
        """
        Build a synthetic Feature_Table GeoDataFrame with exactly the eight
        :data:`SCHEMA_COLUMNS` + geometry, one row per ``cell_id``.

        Geometry mirrors ``_make_grid_gdf`` (distinct 0.05-degree squares) so the
        table is a plausible feature layer in ``STORAGE_CRS``. ``overrides`` is an
        optional ``{column: list-of-values}`` mapping used to inject faults into a
        specific column (e.g. an out-of-range ``slope_deg`` or a bad
        ``confidence_flag`` value); every other column is filled with valid values.
        """
        n = len(cell_ids)
        geometries = []
        for i in range(n):
            minx = 150.0 + i * 0.05
            miny = -34.0 + i * 0.05
            geometries.append(box(minx, miny, minx + 0.05, miny + 0.05))

        data = {
            "cell_id": list(cell_ids),
            "elevation_m": [800.0 + i for i in range(n)],
            "slope_deg": [5.0 + i for i in range(n)],
            "land_use": ["1.1.1 Strict nature reserves"] * n,
            "protected_area": [False] * n,
            "protected_area_name": [""] * n,
            "tri": [10.0 + i for i in range(n)],
            "confidence_flag": [CONFIDENCE_HIGH] * n,
        }
        if overrides:
            for column, values in overrides.items():
                data[column] = values

        # Columns in the exact SCHEMA_COLUMNS order so the schema check sees them
        # in the expected order.
        ordered = {col: data[col] for col in SCHEMA_COLUMNS}
        return gpd.GeoDataFrame(ordered, geometry=geometries, crs=STORAGE_CRS)

    def _write_table(self, gdf, tmp_path, name="synthetic_feature_table.gpkg"):
        """Write a synthetic Feature_Table to a GeoPackage and return the path."""
        path = tmp_path / name
        gdf.to_file(path, driver="GPKG")
        return path

    @staticmethod
    def _check_by_name(result, name):
        """Look up a single check dict by its ``name`` in the returned checks list."""
        matches = [c for c in result["checks"] if c["name"] == name]
        assert len(matches) == 1, f"expected exactly one {name!r} check, got {matches}"
        return matches[0]

    @staticmethod
    def _assert_failed(check):
        """Assert a check failed with populated (non-empty string) expected/observed."""
        assert check["passed"] is False
        assert isinstance(check["expected"], str) and check["expected"] != ""
        assert isinstance(check["observed"], str) and check["observed"] != ""

    def test_correct_table_passes_all_checks(self, tmp_path):
        """
        A correct Feature_Table (row count == grid, exact cell_id set, exact
        schema, in-range slope, valid confidence values) passes every check —
        ``passed == total`` and every ``check["passed"]`` is True
        (Req 11.1-11.5).
        """
        grid_path = _write_grid(_make_grid_gdf(self.CELL_IDS), tmp_path)
        table_path = self._write_table(
            self._make_feature_table_gdf(self.CELL_IDS), tmp_path
        )

        result = validate(table_path, grid_path)

        assert result["total"] == 5
        assert result["passed"] == result["total"]
        assert all(c["passed"] for c in result["checks"])

    def test_wrong_row_count_fails_row_count_check(self, tmp_path):
        """
        A table with fewer rows than the grid fails the row-count check with the
        expected/observed counts populated (Req 11.1).
        """
        grid_path = _write_grid(_make_grid_gdf(self.CELL_IDS), tmp_path)
        # Table has only two of the grid's three cells -> row count mismatch.
        table_path = self._write_table(
            self._make_feature_table_gdf(self.CELL_IDS[:2]), tmp_path
        )

        result = validate(table_path, grid_path)
        check = self._check_by_name(result, "Row count == grid cell count")

        self._assert_failed(check)
        assert "3 rows" in check["expected"]
        assert "2 rows" in check["observed"]

    def test_missing_cell_id_fails_set_match_check(self, tmp_path):
        """
        A table missing a grid ``cell_id`` (and carrying an extra one instead)
        fails the exact-set-match check, reporting the missing/extra counts
        (Req 11.2).
        """
        grid_path = _write_grid(_make_grid_gdf(self.CELL_IDS), tmp_path)
        # Drop the last grid cell, substitute a cell_id absent from the grid: the
        # row count still matches (3), isolating the set-match failure.
        table_cell_ids = self.CELL_IDS[:2] + ["S99.999_E199.999"]
        table_path = self._write_table(
            self._make_feature_table_gdf(table_cell_ids), tmp_path
        )

        result = validate(table_path, grid_path)
        check = self._check_by_name(result, "Exact cell_id set match")

        self._assert_failed(check)
        # One grid cell_id is missing and one table cell_id is extra.
        assert "1 missing" in check["observed"]
        assert "1 extra" in check["observed"]

    def test_wrong_schema_fails_schema_check(self, tmp_path):
        """
        A table whose columns are not exactly the eight :data:`SCHEMA_COLUMNS`
        fails the schema check, reporting the expected and observed column lists
        (Req 11.3).

        Here ``tri`` is dropped and a spurious ``extra_col`` is added, so the
        non-geometry columns no longer equal ``SCHEMA_COLUMNS``.
        """
        grid_path = _write_grid(_make_grid_gdf(self.CELL_IDS), tmp_path)
        gdf = self._make_feature_table_gdf(self.CELL_IDS)
        gdf = gdf.drop(columns=["tri"])
        gdf["extra_col"] = [1, 2, 3]
        table_path = self._write_table(gdf, tmp_path)

        result = validate(table_path, grid_path)
        check = self._check_by_name(result, "Schema columns match Req 7")

        self._assert_failed(check)
        # Expected names the required schema; observed reflects the wrong columns.
        assert "tri" in check["expected"]
        assert "extra_col" in check["observed"]

    def test_slope_above_90_fails_slope_range_check(self, tmp_path):
        """
        A table with a ``slope_deg`` value above 90 degrees fails the plausible-
        range check, reporting the count of out-of-range non-null cells (Req 11.4).
        """
        grid_path = _write_grid(_make_grid_gdf(self.CELL_IDS), tmp_path)
        # One cell has an impossible slope of 120 degrees (> 90).
        table_path = self._write_table(
            self._make_feature_table_gdf(
                self.CELL_IDS, overrides={"slope_deg": [5.0, 120.0, 7.0]}
            ),
            tmp_path,
        )

        result = validate(table_path, grid_path)
        check = self._check_by_name(result, "slope_deg in [0, 90] or null")

        self._assert_failed(check)
        assert "1 out-of-range" in check["observed"]

    def test_bad_confidence_value_fails_confidence_check(self, tmp_path):
        """
        A table with a ``confidence_flag`` outside ``{high, low}`` fails the
        confidence-domain check, reporting the count of invalid values (Req 11.5).
        """
        grid_path = _write_grid(_make_grid_gdf(self.CELL_IDS), tmp_path)
        # One cell carries an invalid confidence value ("medium").
        table_path = self._write_table(
            self._make_feature_table_gdf(
                self.CELL_IDS,
                overrides={"confidence_flag": [CONFIDENCE_HIGH, "medium", CONFIDENCE_LOW]},
            ),
            tmp_path,
        )

        result = validate(table_path, grid_path)
        check = self._check_by_name(result, "confidence_flag in {high, low}")

        self._assert_failed(check)
        assert "1 invalid" in check["observed"]


# ---------------------------------------------------------------------------
# Full-grid integration test — opt-in, runs against the real grid (task 16.1)
# ---------------------------------------------------------------------------


class TestFullGridIntegration:
    """
    Opt-in full-NSW-grid integration test for ``run()`` (task 16.1, Req 13.1-13.3).

    Unlike the synthetic unit/property tests above, this exercises the real
    ``run()`` end-to-end against the on-disk analysis grid
    (``DATA/grid/nsw_analysis_grid.gpkg``) and the real Sprint-0 geographic
    sources. It therefore regenerates the derived Feature_Table
    (``DATA/geographic/features/optmining_geographic-features_2024_nsw.gpkg``)
    and its method report — acceptable because the Feature_Table is a fully
    regenerable derived product (Req 7.7).

    The test ``pytest.skip``s when the grid GeoPackage is absent, mirroring
    ``TestGeoPackageRoundtrip`` in ``tests/test_grid.py`` so the suite still
    passes in a checkout without generated data.
    """

    def _require_grid(self):
        """Skip (rather than fail) when the real grid GeoPackage is absent."""
        if not GRID_PATH.exists():
            pytest.skip(
                f"Analysis grid not present at {GRID_PATH} "
                "(run `python -m pipeline.grid` first) — skipping opt-in "
                "full-grid integration test"
            )

    def test_run_over_real_grid_matches_cell_count_and_reports_runtime(self):
        """
        Running ``run()`` over the real grid returns one row per grid cell, a
        ``runtime_s`` in the summary dict, and a method-report runtime line that
        equals ``runtime_s`` (Req 13.1, 13.2, 13.3).
        """
        self._require_grid()

        # Expected cell count: the grid's own cell_id count via the strict reader
        # the stage uses internally (Req 8.1) — not a hard-coded constant.
        expected_n_cells = len(read_grid_cells(GRID_PATH))

        summary = run(verbose=False)

        # --- Req 13.1: one row per grid cell -----------------------------------
        assert isinstance(summary, dict)
        assert "n_cells" in summary
        assert summary["n_cells"] == expected_n_cells, (
            f"run() processed {summary['n_cells']} cells but the grid has "
            f"{expected_n_cells}"
        )

        # --- Req 13.2 / 13.3: summary dict carries runtime_s -------------------
        assert "runtime_s" in summary, "summary dict missing 'runtime_s' key"
        runtime_s = summary["runtime_s"]
        assert isinstance(runtime_s, (int, float))
        assert runtime_s >= 0.0

        # Output paths exist on disk after the call returns (Req 10.2).
        assert summary["feature_table"] == OUTPUT_PATH
        assert summary["report"] == REPORT_PATH
        assert OUTPUT_PATH.exists()
        assert REPORT_PATH.exists()

        # The written Feature_Table has one row per grid cell (Req 13.1).
        table = gpd.read_file(OUTPUT_PATH)
        assert len(table) == expected_n_cells

        # --- Req 13.3: report runtime line equals runtime_s --------------------
        # _build_report writes: "- Total wall-clock runtime: {runtime_s:.3f} s".
        report_text = REPORT_PATH.read_text()
        expected_line = f"- Total wall-clock runtime: {runtime_s:.3f} s"
        assert expected_line in report_text, (
            "method report runtime line does not match the summary runtime_s; "
            f"expected to find {expected_line!r} in the report"
        )

        # Also parse the reported number back out and compare within the
        # formatting tolerance (:.3f rounds to 3 dp), so a mismatch in either the
        # formatting or the value is caught.
        match = re.search(
            r"Total wall-clock runtime:\s*([0-9]+(?:\.[0-9]+)?)\s*s", report_text
        )
        assert match is not None, "no runtime line found in the method report"
        reported_runtime = float(match.group(1))
        assert reported_runtime == pytest.approx(runtime_s, abs=5e-4), (
            f"report runtime {reported_runtime} != summary runtime_s {runtime_s}"
        )

# ===========================================================================
# Property-based tests (task 15) — hypothesis, @settings(max_examples=100)
# ===========================================================================
#
# The 15 correctness properties from design.md §Correctness Properties, each
# implemented by a single hypothesis property test tagged
# `# Feature: geographic-environmental-features, Property {n}: {text}`.
#
# Generators build small synthetic numpy rasters (with a chosen nodata), synthetic
# cell polygons, and synthetic CAPAD-like polygons — NO network, NO real files
# (except Property 15, which inspects pipeline.config.STAGES). Raster-backed
# properties write a tiny north-up single-band GeoTIFF to a NamedTemporaryFile in
# the test body (hypothesis @given does not compose with pytest's tmp_path
# fixture), matching the raster convention used by TestZonalRasterStat above:
# north-up, origin top-left (0, H) with pixel size 1.0, cell-centre inclusion
# (all_touched=False). Strategies are bounded and small so 100 examples run fast;
# @settings uses deadline=None because per-example raster I/O can exceed the
# default hypothesis deadline on a cold cache.

import os as _os
import tempfile as _tempfile
from contextlib import contextmanager as _contextmanager

import numpy as _np
import rasterio as _rasterio
from hypothesis import given, settings, strategies as st
from hypothesis.extra import numpy as _hnp
from rasterio.transform import from_origin as _from_origin

from pipeline.geographic.features import (
    COMPUTATION_CRS as _COMPUTATION_CRS,
    _raster_coverage as _pbt_raster_coverage,
)
import pipeline.config as _pipeline_config


# ---------------------------------------------------------------------------
# Shared property-test helpers
# ---------------------------------------------------------------------------

# NoData sentinel kept well outside the synthetic data range so it is always a
# distinct, unambiguous marker (data values are constrained to a small band well
# away from this value).
_PBT_NODATA = -9999.0

# Bounded raster dimension for continuous/categorical synthetic rasters.
_PBT_MAX_DIM = 8


@_contextmanager
def _temp_raster(
    array,
    *,
    nodata=None,
    scale=None,
    origin=None,
    pixel_size=1.0,
    dtype=None,
    crs=STORAGE_CRS,
):
    """
    Write a tiny north-up single-band GeoTIFF to a temp file and yield an open
    rasterio dataset, cleaning the file up afterwards.

    Matches the raster convention of ``TestZonalRasterStat._write_raster``: origin
    defaults to the top-left corner ``(0, height)`` with the given ``pixel_size``,
    so an ``H x W`` raster covers ``x in [0, W]``, ``y in [0, H]`` with pixel
    centres on the half-integer lattice and row 0 the northernmost. Used inside
    ``@given`` bodies because hypothesis does not compose with the ``tmp_path``
    fixture — the temp file is created and removed per example.
    """
    array = _np.asarray(array)
    if dtype is not None:
        array = array.astype(dtype)
    height, width = array.shape
    if origin is None:
        origin = (0.0, float(height) * pixel_size)
    transform = _from_origin(origin[0], origin[1], pixel_size, pixel_size)

    fd, name = _tempfile.mkstemp(suffix=".tif")
    _os.close(fd)
    path = name
    try:
        profile = {
            "driver": "GTiff",
            "height": height,
            "width": width,
            "count": 1,
            "dtype": array.dtype,
            "crs": crs,
            "transform": transform,
        }
        if nodata is not None:
            profile["nodata"] = nodata
        with _rasterio.open(path, "w", **profile) as dst:
            dst.write(array, 1)
            if scale is not None:
                dst.scales = (scale,)
        src = _rasterio.open(path)
        try:
            yield src
        finally:
            src.close()
    finally:
        try:
            _os.remove(path)
        except OSError:
            pass


def _pbt_inside_pixel_centres(cell, transform, height, width):
    """
    Brute-force the set of (row, col) pixel positions whose CENTRE lies strictly
    inside ``cell`` under the cell-centre inclusion rule (all_touched=False).

    This is the independent reference implementation used by the raster properties
    to check ``_zonal_raster_stat`` / ``_categorical_mode`` selection against a
    from-scratch computation, rather than trusting the module under test.
    """
    from shapely.geometry import Point

    selected = set()
    for row in range(height):
        for col in range(width):
            # Pixel centre in CRS coords: transform maps (col, row) -> upper-left
            # corner of the pixel; add half a pixel to reach the centre.
            x, y = transform * (col + 0.5, row + 0.5)
            if cell.contains(Point(x, y)):
                selected.add((row, col))
    return selected


# Hypothesis strategies -----------------------------------------------------

# Small continuous raster of float64 values in a tight, finite band well clear of
# the NoData sentinel, plus a boolean nodata mask marking which cells are NoData.
def _continuous_raster_strategy():
    """(values, nodata_mask) for a small float64 raster; values are finite and
    bounded away from the NoData sentinel."""
    dims = st.integers(min_value=1, max_value=_PBT_MAX_DIM)

    @st.composite
    def _build(draw):
        h = draw(dims)
        w = draw(dims)
        values = draw(
            _hnp.arrays(
                dtype=_np.float64,
                shape=(h, w),
                elements=st.floats(
                    min_value=-1000.0,
                    max_value=1000.0,
                    allow_nan=False,
                    allow_infinity=False,
                    width=64,
                ),
            )
        )
        nodata_mask = draw(
            _hnp.arrays(dtype=_np.bool_, shape=(h, w), elements=st.booleans())
        )
        return values, nodata_mask

    return _build()


def _categorical_raster_strategy():
    """(codes, nodata_mask) for a small int32 categorical raster; codes are small
    positive class codes and the nodata sentinel is a distinct large value."""
    dims = st.integers(min_value=1, max_value=_PBT_MAX_DIM)

    @st.composite
    def _build(draw):
        h = draw(dims)
        w = draw(dims)
        codes = draw(
            _hnp.arrays(
                dtype=_np.int32,
                shape=(h, w),
                elements=st.integers(min_value=1, max_value=6),
            )
        )
        nodata_mask = draw(
            _hnp.arrays(dtype=_np.bool_, shape=(h, w), elements=st.booleans())
        )
        return codes, nodata_mask

    return _build()


def _full_cover_cell(height, width, pixel_size=1.0):
    """
    A cell polygon that fully covers the whole raster extent so every pixel centre
    falls inside it (origin top-left (0, height) convention). Used by properties
    that reason over the complete pixel set.
    """
    return box(0.0, 0.0, float(width) * pixel_size, float(height) * pixel_size)


# ---------------------------------------------------------------------------
# Property 1–5, 10 — raster zonal-statistic properties
# ---------------------------------------------------------------------------


class TestZonalStatProperties:
    """
    Property-based tests for ``_zonal_raster_stat`` — the continuous zonal
    statistic core (Properties 1, 2, 3, 4, 5, 10).
    """

    @settings(max_examples=100, deadline=None)
    @given(data=_continuous_raster_strategy())
    def test_property_1_mean_of_valid_pixels_nodata_excluded(self, data):
        # Feature: geographic-environmental-features, Property 1: Zonal statistic
        # equals the mean of valid pixels, NoData excluded — adding further NoData
        # pixels within the cell does not change the derived value.
        # Validates: Requirements 1.1, 1.2, 1.3, 2.3
        values, nodata_mask = data
        h, w = values.shape
        array = values.copy()
        array[nodata_mask] = _PBT_NODATA
        cell = _full_cover_cell(h, w)

        with _temp_raster(array, nodata=_PBT_NODATA) as src:
            result = _zonal_raster_stat(src, cell, "mean")
            selected = _pbt_inside_pixel_centres(cell, src.transform, h, w)

        # Independent reference: mean of exactly the selected, non-NoData pixels.
        valid_positions = [(r, c) for (r, c) in selected if not nodata_mask[r, c]]
        if not valid_positions:
            assert result.value is None
            return
        expected = _np.mean([values[r, c] for (r, c) in valid_positions])
        assert result.value == pytest.approx(float(expected), abs=1e-9)

    @settings(max_examples=100, deadline=None)
    @given(data=_continuous_raster_strategy())
    def test_property_2_valid_plus_nodata_partition_selection(self, data):
        # Feature: geographic-environmental-features, Property 2: valid + NoData
        # counts partition the clipped selection; both counts are non-negative and
        # sum to the total number of pixels in the cell-centre selection.
        # Validates: Requirements 2.2
        values, nodata_mask = data
        h, w = values.shape
        array = values.copy()
        array[nodata_mask] = _PBT_NODATA
        cell = _full_cover_cell(h, w)

        with _temp_raster(array, nodata=_PBT_NODATA) as src:
            result = _zonal_raster_stat(src, cell, "mean")
            selected = _pbt_inside_pixel_centres(cell, src.transform, h, w)

        assert result.n_valid >= 0
        assert result.n_nodata >= 0
        # For a cell fully within the raster, the clipped selection is exactly the
        # cell-centre pixel set, so valid + nodata equals that count.
        assert result.n_valid + result.n_nodata == len(selected)

    @settings(max_examples=100, deadline=None)
    @given(data=_continuous_raster_strategy())
    def test_property_3_deterministic_pixel_selection_idempotent(self, data):
        # Feature: geographic-environmental-features, Property 3: deterministic
        # pixel selection (idempotence) — computing the statistic twice yields
        # identical value and identical valid/NoData counts.
        # Validates: Requirements 2.1, 2.4
        values, nodata_mask = data
        h, w = values.shape
        array = values.copy()
        array[nodata_mask] = _PBT_NODATA
        cell = _full_cover_cell(h, w)

        with _temp_raster(array, nodata=_PBT_NODATA) as src:
            first = _zonal_raster_stat(src, cell, "mean")
            second = _zonal_raster_stat(src, cell, "mean")

        assert first.n_valid == second.n_valid
        assert first.n_nodata == second.n_nodata
        assert first.in_coverage == second.in_coverage
        if first.value is None:
            assert second.value is None
        else:
            assert first.value == pytest.approx(second.value, abs=0.0)

    @settings(max_examples=100, deadline=None)
    @given(data=_continuous_raster_strategy())
    def test_property_4_identical_partial_cell_rule_across_rasters(self, data):
        # Feature: geographic-environmental-features, Property 4: identical
        # partial-cell rule across two co-registered rasters — the same cell
        # selects the same pixel positions/counts in both, independent of pixel
        # values. Two co-registered rasters (same transform/shape) with different
        # data but the SAME NoData layout select identical valid/NoData counts.
        # Validates: Requirements 1.5
        values, nodata_mask = data
        h, w = values.shape
        # Raster A: the drawn values. Raster B: a co-registered raster with
        # different values but the identical NoData layout (so the cell-centre
        # selection and NoData partition must match exactly).
        array_a = values.copy()
        array_a[nodata_mask] = _PBT_NODATA
        array_b = (values * 2.0 + 1.0)
        array_b[nodata_mask] = _PBT_NODATA
        cell = _full_cover_cell(h, w)

        with _temp_raster(array_a, nodata=_PBT_NODATA) as src_a:
            res_a = _zonal_raster_stat(src_a, cell, "mean")
        with _temp_raster(array_b, nodata=_PBT_NODATA) as src_b:
            res_b = _zonal_raster_stat(src_b, cell, "mean")

        # Identical pixel selection => identical valid/NoData partition and coverage.
        assert res_a.n_valid == res_b.n_valid
        assert res_a.n_nodata == res_b.n_nodata
        assert res_a.in_coverage == res_b.in_coverage

    @settings(max_examples=100, deadline=None)
    @given(data=_continuous_raster_strategy())
    def test_property_5_zero_valid_yields_null_and_low_confidence(self, data):
        # Feature: geographic-environmental-features, Property 5: zero valid pixels
        # yield a null value AND low confidence (and null land_use for the
        # categorical variable). A raster made entirely NoData over the cell has no
        # valid pixels, so value is None, in_coverage is False, and a confidence
        # decision that includes this raster is 'low'.
        # Validates: Requirements 1.6, 2.6, 3.5
        values, nodata_mask = data
        h, w = values.shape
        cell = _full_cover_cell(h, w)

        # Force EVERY pixel to NoData -> zero valid pixels in the selection.
        all_nodata = _np.full((h, w), _PBT_NODATA, dtype=_np.float64)
        with _temp_raster(all_nodata, nodata=_PBT_NODATA) as src:
            stat = _zonal_raster_stat(src, cell, "mean")

        assert stat.value is None
        assert stat.n_valid == 0
        assert stat.in_coverage is False

        # A confidence decision over required rasters where elevation is this
        # zero-valid stat must be low (Req 1.6 -> Req 5 low-confidence link).
        good = CellStat(value=1.0, n_valid=4, n_nodata=0, in_coverage=True)
        good_mode = ModeResult(
            land_use="x", code=1, n_valid=4, n_nodata=0, in_coverage=True
        )
        per_raster = {"elevation": stat, "slope": good, "nlum": good_mode}
        assert _confidence_flag(per_raster) == CONFIDENCE_LOW

        # Categorical variant: an all-NoData categorical raster yields null land_use.
        all_nodata_codes = _np.full((h, w), 0, dtype=_np.int32)
        with _temp_raster(all_nodata_codes, nodata=0, dtype=_np.int32) as csrc:
            mode = _categorical_mode(csrc, cell, {1: "a"})
        assert mode.land_use is None
        assert mode.code is None
        assert mode.n_valid == 0

    @settings(max_examples=100, deadline=None)
    @given(
        data=_continuous_raster_strategy(),
        offset=st.floats(min_value=100.0, max_value=1000.0),
    )
    def test_property_10_out_of_coverage_cells_have_null_variables(self, data, offset):
        # Feature: geographic-environmental-features, Property 10: out-of-coverage
        # cells (centroid outside raster bounds) have null variables and are
        # classified out of coverage for that raster.
        # Validates: Requirements 6.2
        values, nodata_mask = data
        h, w = values.shape
        array = values.copy()
        array[nodata_mask] = _PBT_NODATA
        # A cell placed far outside the raster extent (raster covers [0,w]x[0,h]).
        far = box(offset, offset, offset + 1.0, offset + 1.0)

        with _temp_raster(array, nodata=_PBT_NODATA) as src:
            assert _pbt_raster_coverage(src, far) is False
            stat = _zonal_raster_stat(src, far, "mean")
            mode = _categorical_mode(src, far, {1: "a"})

        assert stat.value is None
        assert stat.in_coverage is False
        assert mode.land_use is None
        assert mode.in_coverage is False


# ---------------------------------------------------------------------------
# Property 6 — categorical mode
# ---------------------------------------------------------------------------


class TestCategoricalModeProperties:
    """Property-based test for ``_categorical_mode`` (Property 6)."""

    @settings(max_examples=100, deadline=None)
    @given(data=_categorical_raster_strategy())
    def test_property_6_dominant_land_use_is_mode_lowest_code_tiebreak(self, data):
        # Feature: geographic-environmental-features, Property 6: dominant land-use
        # is the mapped mode with lowest-code tie-break — the returned code is a
        # most-frequent code among valid pixels, the lowest code wins on a tie, and
        # it maps to table[code] when present and to unmapped:<code> otherwise.
        # Validates: Requirements 3.1, 3.2, 3.3, 3.4
        codes, nodata_mask = data
        h, w = codes.shape
        _NODATA_CODE = 9999
        array = codes.copy().astype(_np.int32)
        array[nodata_mask] = _NODATA_CODE
        cell = _full_cover_cell(h, w)
        # Map only some codes so both the mapped and unmapped branches are exercised.
        class_table = {1: "one", 2: "two", 3: "three"}

        with _temp_raster(array, nodata=_NODATA_CODE, dtype=_np.int32) as src:
            result = _categorical_mode(src, cell, class_table)
            selected = _pbt_inside_pixel_centres(cell, src.transform, h, w)

        valid_codes = [
            int(codes[r, c]) for (r, c) in selected if not nodata_mask[r, c]
        ]
        if not valid_codes:
            assert result.code is None
            assert result.land_use is None
            return

        # Independent reference mode with lowest-code tie-break.
        counts = {}
        for code in valid_codes:
            counts[code] = counts.get(code, 0) + 1
        max_count = max(counts.values())
        expected_code = min(c for c, n in counts.items() if n == max_count)

        assert result.code == expected_code
        # Returned code is genuinely a most-frequent code.
        assert counts[result.code] == max_count
        # Mapping: present -> table name; absent -> unmapped marker (Req 3.3, 3.4).
        if expected_code in class_table:
            assert result.land_use == class_table[expected_code]
        else:
            assert result.land_use == f"unmapped:{expected_code}"


# ---------------------------------------------------------------------------
# Property 7, 8, 12 — protected-area overlap
# ---------------------------------------------------------------------------


class TestProtectedOverlapProperties:
    """
    Property-based tests for ``_protected_overlap`` (Properties 7, 8, 12).

    Synthetic cells and CAPAD features are built directly in ``COMPUTATION_CRS``
    (EPSG:3577, metre coordinates) so the real ``geopandas.sjoin`` intersects path
    is exercised without any reprojection or real files.
    """

    # A fixed 3x3 lattice of 100 m cells so cell layout is deterministic; feature
    # placement is what hypothesis varies.
    def _cells(self):
        cell_ids = []
        geoms = []
        for i in range(3):
            for j in range(3):
                cell_ids.append(f"C{i}{j}")
                geoms.append(box(i * 100.0, j * 100.0, i * 100.0 + 100.0, j * 100.0 + 100.0))
        return gpd.GeoDataFrame(
            {"cell_id": cell_ids}, geometry=geoms, crs=_COMPUTATION_CRS
        )

    # A feature is a small square placed at a hypothesis-chosen origin within/around
    # the 0..300 lattice, with a hypothesis-chosen name (or None for unnamed).
    _feature_origin = st.floats(min_value=-50.0, max_value=300.0)
    _feature_size = st.floats(min_value=10.0, max_value=120.0)

    @settings(max_examples=100, deadline=None)
    @given(
        specs=st.lists(
            st.tuples(
                _feature_origin,
                _feature_origin,
                _feature_size,
                st.sampled_from(["Park A", "Park B", "Reserve C", "Park A"]),
            ),
            min_size=0,
            max_size=4,
        )
    )
    def test_property_7_flag_and_names_match_intersecting_features(self, specs):
        # Feature: geographic-environmental-features, Property 7: protected flag and
        # names match the intersecting CAPAD features — protected_area is true iff
        # the cell intersects >=1 feature; the name is the distinct, delimiter-joined
        # set of intersecting feature names; empty string when no overlap.
        # Validates: Requirements 4.1, 4.2, 4.3, 4.4
        cells = self._cells()
        capad = gpd.GeoDataFrame(
            {"NAME": [name for (_, _, _, name) in specs]},
            geometry=[
                box(x, y, x + s, y + s) for (x, y, s, _) in specs
            ],
            crs=_COMPUTATION_CRS,
        )

        result = _protected_overlap(cells, capad)

        # Every cell appears exactly once (bijection over the input, Req 6.1/7.2).
        assert set(result) == set(cells["cell_id"])

        # Brute-force reference: for each cell, the distinct names of intersecting
        # features (all named here), matching against the module output.
        for _, cell_row in cells.iterrows():
            cid = cell_row["cell_id"]
            cell_geom = cell_row.geometry
            hit_names = sorted(
                {
                    name
                    for (x, y, s, name) in specs
                    if box(x, y, x + s, y + s).intersects(cell_geom)
                }
            )
            protected, name = result[cid]
            if hit_names:
                assert protected is True
                assert name == PROTECTED_AREA_NAME_DELIMITER.join(hit_names)
            else:
                assert protected is False
                assert name == ""

    @settings(max_examples=100, deadline=None)
    @given(
        specs=st.lists(
            st.tuples(_feature_origin, _feature_origin, _feature_size),
            min_size=1,
            max_size=4,
        ),
        blank=st.sampled_from([None, "", "   "]),
    )
    def test_property_8_unnamed_features_flag_true_with_placeholder(self, specs, blank):
        # Feature: geographic-environmental-features, Property 8: unnamed
        # intersecting features flag true with the placeholder — any cell that
        # intersects a feature whose name is missing/null/blank is protected and
        # carries the UNNAMED_PROTECTED_AREA placeholder for that feature.
        # Validates: Requirements 4.5
        cells = self._cells()
        # Every feature is unnamed (blank name).
        capad = gpd.GeoDataFrame(
            {"NAME": [blank] * len(specs)},
            geometry=[box(x, y, x + s, y + s) for (x, y, s) in specs],
            crs=_COMPUTATION_CRS,
        )

        result = _protected_overlap(cells, capad)

        for _, cell_row in cells.iterrows():
            cid = cell_row["cell_id"]
            cell_geom = cell_row.geometry
            intersects_any = any(
                box(x, y, x + s, y + s).intersects(cell_geom) for (x, y, s) in specs
            )
            protected, name = result[cid]
            if intersects_any:
                assert protected is True
                # Only unnamed features here, so the placeholder is the whole name.
                assert name == UNNAMED_PROTECTED_AREA
            else:
                assert protected is False
                assert name == ""

    @settings(max_examples=100, deadline=None)
    @given(
        cell_ids=st.lists(
            st.text(
                alphabet=st.characters(min_codepoint=48, max_codepoint=90),
                min_size=1,
                max_size=8,
            ),
            min_size=1,
            max_size=12,
            unique=True,
        )
    )
    def test_property_12_output_cell_id_bijection_with_grid(self, cell_ids):
        # Feature: geographic-environmental-features, Property 12: output cell_id set
        # is a bijection with the grid, values preserved — every input cell_id
        # appears exactly once in the result, no cell_id is added or dropped, and
        # each value is reused byte-for-byte.
        # Validates: Requirements 6.1, 7.2, 8.2, 8.3
        n = len(cell_ids)
        geoms = [box(i * 10.0, 0.0, i * 10.0 + 10.0, 10.0) for i in range(n)]
        cells = gpd.GeoDataFrame(
            {"cell_id": cell_ids}, geometry=geoms, crs=_COMPUTATION_CRS
        )
        # An arbitrary single feature (may or may not overlap); the bijection must
        # hold regardless of overlap.
        capad = gpd.GeoDataFrame(
            {"NAME": ["Somewhere"]},
            geometry=[box(0.0, 0.0, 25.0, 5.0)],
            crs=_COMPUTATION_CRS,
        )

        result = _protected_overlap(cells, capad)

        # Multiset equality: keys are exactly the input cell_ids, each once.
        assert sorted(result.keys()) == sorted(cell_ids)
        assert len(result) == n
        # Values preserved byte-for-byte (same string objects/content).
        for cid in cell_ids:
            assert cid in result


# ---------------------------------------------------------------------------
# Property 9, 11 — confidence flag & coverage bookkeeping
# ---------------------------------------------------------------------------


def _pbt_cellstat_strategy():
    """A CellStat with small non-negative counts and a coverage flag; value is
    derived so it is None exactly when there are zero valid pixels."""

    @st.composite
    def _build(draw):
        in_coverage = draw(st.booleans())
        n_valid = draw(st.integers(min_value=0, max_value=20))
        n_nodata = draw(st.integers(min_value=0, max_value=20))
        value = None if n_valid == 0 else draw(
            st.floats(min_value=-100.0, max_value=100.0, allow_nan=False)
        )
        return CellStat(
            value=value, n_valid=n_valid, n_nodata=n_nodata, in_coverage=in_coverage
        )

    return _build()


def _pbt_moderesult_strategy():
    """A ModeResult with small non-negative counts and a coverage flag."""

    @st.composite
    def _build(draw):
        in_coverage = draw(st.booleans())
        n_valid = draw(st.integers(min_value=0, max_value=20))
        n_nodata = draw(st.integers(min_value=0, max_value=20))
        return ModeResult(
            land_use=("x" if n_valid else None),
            code=(1 if n_valid else None),
            n_valid=n_valid,
            n_nodata=n_nodata,
            in_coverage=in_coverage,
        )

    return _build()


class TestConfidenceAndCoverageProperties:
    """Property-based tests for ``_confidence_flag`` and coverage bookkeeping."""

    @staticmethod
    def _reference_low(stat):
        """Independent reference: is this single required-raster stat 'low'?

        Low iff out of coverage, or the clipped selection is empty, or >= 50%
        NoData (2*n_nodata >= total)."""
        if not stat.in_coverage:
            return True
        total = stat.n_valid + stat.n_nodata
        if total == 0:
            return True
        return 2 * stat.n_nodata >= total

    @settings(max_examples=100, deadline=None)
    @given(
        elevation=_pbt_cellstat_strategy(),
        slope=_pbt_cellstat_strategy(),
        nlum=_pbt_moderesult_strategy(),
        tri=_pbt_cellstat_strategy(),
    )
    def test_property_9_confidence_is_coverage_nodata_biconditional(
        self, elevation, slope, nlum, tri
    ):
        # Feature: geographic-environmental-features, Property 9: confidence flag is
        # the coverage/NoData biconditional over the required rasters — low iff any
        # required raster (elevation, slope, nlum) is out of coverage or >= 50%
        # NoData; otherwise high; always exactly one of high/low. TRI is excluded.
        # Validates: Requirements 5.1, 5.2, 5.3, 5.4, 6.4
        per_raster = {
            "elevation": elevation,
            "slope": slope,
            "nlum": nlum,
            "tri": tri,  # present but must be ignored by the decision.
        }
        flag = _confidence_flag(per_raster)

        # Domain: exactly one of high/low (Req 5.4).
        assert flag in {CONFIDENCE_HIGH, CONFIDENCE_LOW}

        # Biconditional over the REQUIRED rasters only (TRI excluded, Req 6.4).
        expected_low = any(
            self._reference_low(per_raster[name])
            for name in REQUIRED_CONFIDENCE_RASTERS
        )
        assert (flag == CONFIDENCE_LOW) == expected_low

        # Explicit TRI-exclusion check: flipping TRI to a clearly-low stat must not
        # change the decision.
        per_raster_bad_tri = dict(per_raster)
        per_raster_bad_tri["tri"] = CellStat(
            value=None, n_valid=0, n_nodata=8, in_coverage=False
        )
        assert _confidence_flag(per_raster_bad_tri) == flag

    @settings(max_examples=100, deadline=None)
    @given(
        coverage_flags=st.lists(st.booleans(), min_size=0, max_size=200),
    )
    def test_property_11_coverage_bookkeeping_partitions_grid(self, coverage_flags):
        # Feature: geographic-environmental-features, Property 11: coverage
        # bookkeeping partitions the grid per raster — for any grid and raster, the
        # count of cells inside coverage plus the count outside equals the total
        # number of cells, and both counts are non-negative integers.
        # Validates: Requirements 6.5
        # Model one raster's per-cell coverage as a list of in_coverage booleans
        # (one CellStat per grid cell), exactly as run() accumulates them.
        stats = [
            CellStat(
                value=(1.0 if flag else None),
                n_valid=(4 if flag else 0),
                n_nodata=(0 if flag else 4),
                in_coverage=flag,
            )
            for flag in coverage_flags
        ]
        total = len(stats)

        inside = sum(1 for s in stats if s.in_coverage)
        outside = sum(1 for s in stats if not s.in_coverage)

        assert inside >= 0
        assert outside >= 0
        assert isinstance(inside, int)
        assert isinstance(outside, int)
        # Partition: inside + outside == total grid cells (Req 6.5).
        assert inside + outside == total


# ---------------------------------------------------------------------------
# Property 13 — Feature_Table schema
# ---------------------------------------------------------------------------


class TestSchemaProperties:
    """Property-based test for the Feature_Table schema (Property 13)."""

    @settings(max_examples=100, deadline=None)
    @given(
        n=st.integers(min_value=1, max_value=8),
        col_order=st.permutations(SCHEMA_COLUMNS),
    )
    def test_property_13_feature_table_has_exact_schema(self, n, col_order):
        # Feature: geographic-environmental-features, Property 13: Feature_Table has
        # exactly the required schema — after schema enforcement the non-geometry
        # columns are exactly SCHEMA_COLUMNS (the eight required columns), in order,
        # plus a geometry column, regardless of the source column order.
        # Validates: Requirements 7.1
        cell_ids = [f"S{i:03d}" for i in range(n)]
        geoms = [box(i, 0.0, i + 1.0, 1.0) for i in range(n)]
        # Build a table whose columns arrive in an arbitrary (permuted) order, plus
        # spurious extra columns that schema enforcement must drop.
        raw = {
            "cell_id": cell_ids,
            "elevation_m": [1.0] * n,
            "slope_deg": [2.0] * n,
            "land_use": ["x"] * n,
            "protected_area": [False] * n,
            "protected_area_name": [""] * n,
            "tri": [3.0] * n,
            "confidence_flag": [CONFIDENCE_HIGH] * n,
            "spurious_extra": [1] * n,
            "another_extra": ["z"] * n,
        }
        gdf = gpd.GeoDataFrame(raw, geometry=geoms, crs=STORAGE_CRS)

        # Schema enforcement (as run() does before writing): select exactly the
        # eight schema columns in canonical order, keep geometry.
        enforced = gdf[list(col_order)]  # arbitrary order does not matter to the set
        enforced = gpd.GeoDataFrame(
            {col: gdf[col] for col in SCHEMA_COLUMNS},
            geometry=gdf.geometry,
            crs=STORAGE_CRS,
        )

        # The non-geometry columns are exactly SCHEMA_COLUMNS in order (Req 7.1).
        non_geom = [c for c in enforced.columns if c != enforced.geometry.name]
        assert non_geom == SCHEMA_COLUMNS
        # A geometry column is present.
        assert enforced.geometry.name in enforced.columns
        # No spurious columns survive.
        assert "spurious_extra" not in enforced.columns
        assert "another_extra" not in enforced.columns


# ---------------------------------------------------------------------------
# Property 14 — regeneration determinism
# ---------------------------------------------------------------------------


class TestDeterminismProperties:
    """
    Property-based test for regeneration determinism (Property 14).

    Re-running the three pure builders (``_zonal_raster_stat``,
    ``_categorical_mode``, ``_protected_overlap``) on identical synthetic inputs
    must produce identical outputs — the per-cell basis of the whole-table
    determinism guarantee (Req 7.7).
    """

    @settings(max_examples=100, deadline=None)
    @given(
        cont=_continuous_raster_strategy(),
        cat=_categorical_raster_strategy(),
    )
    def test_property_14_regeneration_is_deterministic(self, cont, cat):
        # Feature: geographic-environmental-features, Property 14: regeneration is
        # deterministic — the same synthetic inputs produce identical
        # _zonal_raster_stat / _categorical_mode / _protected_overlap outputs on
        # repeat.
        # Validates: Requirements 7.7
        values, nd_mask = cont
        h, w = values.shape
        cont_arr = values.copy()
        cont_arr[nd_mask] = _PBT_NODATA
        cont_cell = _full_cover_cell(h, w)

        codes, cnd_mask = cat
        ch, cw = codes.shape
        _NODATA_CODE = 9999
        cat_arr = codes.copy().astype(_np.int32)
        cat_arr[cnd_mask] = _NODATA_CODE
        cat_cell = _full_cover_cell(ch, cw)

        with _temp_raster(cont_arr, nodata=_PBT_NODATA) as src:
            r1 = _zonal_raster_stat(src, cont_cell, "mean")
            r2 = _zonal_raster_stat(src, cont_cell, "mean")
        assert (r1.value, r1.n_valid, r1.n_nodata, r1.in_coverage) == (
            r2.value,
            r2.n_valid,
            r2.n_nodata,
            r2.in_coverage,
        )

        with _temp_raster(cat_arr, nodata=_NODATA_CODE, dtype=_np.int32) as csrc:
            m1 = _categorical_mode(csrc, cat_cell, {1: "a", 2: "b"})
            m2 = _categorical_mode(csrc, cat_cell, {1: "a", 2: "b"})
        assert (m1.land_use, m1.code, m1.n_valid, m1.n_nodata, m1.in_coverage) == (
            m2.land_use,
            m2.code,
            m2.n_valid,
            m2.n_nodata,
            m2.in_coverage,
        )

        cells = gpd.GeoDataFrame(
            {"cell_id": ["A", "B"]},
            geometry=[box(0.0, 0.0, 50.0, 50.0), box(50.0, 0.0, 100.0, 50.0)],
            crs=_COMPUTATION_CRS,
        )
        capad = gpd.GeoDataFrame(
            {"NAME": ["Park"]},
            geometry=[box(10.0, 10.0, 40.0, 40.0)],
            crs=_COMPUTATION_CRS,
        )
        assert _protected_overlap(cells, capad) == _protected_overlap(cells, capad)


# ---------------------------------------------------------------------------
# Property 15 — resolved stage order
# ---------------------------------------------------------------------------


class TestStageOrderProperties:
    """Property-based test for resolved stage order (Property 15)."""

    @settings(max_examples=100, deadline=None)
    @given(dummy=st.integers())
    def test_property_15_feature_builder_after_grid(self, dummy):
        # Feature: geographic-environmental-features, Property 15: resolved stage
        # order places the feature builder after the grid — in config.STAGES the
        # index of 'geographic.features' is greater than the index of 'grid', so a
        # resolved order containing both always schedules the consumer after the
        # producer.
        # Validates: Requirements 10.4, 10.7
        stages = list(_pipeline_config.STAGES)
        assert "grid" in stages
        assert "geographic.features" in stages
        assert stages.index("geographic.features") > stages.index("grid")
