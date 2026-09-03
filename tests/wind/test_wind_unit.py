"""
Unit tests for wind domain pure-computation functions.

Tests horn_slope_deg and riley_tri from pipeline.geographic.derive
(these are terrain algorithms used by the geographic domain but are
pure numpy — no I/O required).
"""

import numpy as np
import pytest

rasterio = pytest.importorskip("rasterio", reason="rasterio not installed")


class TestHornSlopeDeg:
    """Horn 3x3 slope algorithm produces correct results."""

    def _make_transform(self, xres=0.001, yres=-0.001, x0=151.0, y0=-29.5):
        """Create a mock affine transform."""
        from collections import namedtuple
        T = namedtuple("Transform", ["a", "b", "c", "d", "e", "f"])
        return T(a=xres, b=0, c=x0, d=0, e=yres, f=y0)

    def test_flat_surface_zero_slope(self):
        """A flat DEM should produce zero slope everywhere."""
        from pipeline.geographic.derive import horn_slope_deg
        dem = np.full((50, 50), 500.0)
        transform = self._make_transform()
        slope = horn_slope_deg(dem, transform)
        assert slope.shape == (50, 50)
        np.testing.assert_allclose(slope, 0.0, atol=1e-10)

    def test_uniform_north_facing_slope(self):
        """A north-facing uniform slope should produce consistent values."""
        from pipeline.geographic.derive import horn_slope_deg
        # Create a DEM that rises 1 m per row (south to north)
        dem = np.zeros((100, 100))
        for i in range(100):
            dem[i, :] = (99 - i) * 1.0  # row 0 is highest (north)
        transform = self._make_transform(xres=0.001, yres=-0.001)
        slope = horn_slope_deg(dem, transform)
        # Interior pixels should all have the same slope
        interior = slope[2:-2, 2:-2]
        assert interior.min() > 0  # non-zero slope
        # Should be fairly uniform
        assert interior.std() / interior.mean() < 0.01

    def test_output_range(self):
        """Slope should be in [0, 90) degrees."""
        from pipeline.geographic.derive import horn_slope_deg
        rng = np.random.default_rng(42)
        dem = rng.uniform(0, 1000, (50, 50))
        transform = self._make_transform()
        slope = horn_slope_deg(dem, transform)
        assert slope.min() >= 0.0
        assert slope.max() < 90.0


class TestRileyTri:
    """Riley TRI (Terrain Ruggedness Index) algorithm."""

    def test_flat_surface_zero_tri(self):
        """A flat DEM should produce zero TRI."""
        from pipeline.geographic.derive import riley_tri
        dem = np.full((30, 30), 250.0)
        tri = riley_tri(dem)
        assert tri.shape == (30, 30)
        np.testing.assert_allclose(tri, 0.0, atol=1e-10)

    def test_checkerboard_positive_tri(self):
        """A checkerboard pattern should produce positive TRI."""
        from pipeline.geographic.derive import riley_tri
        dem = np.zeros((20, 20))
        dem[::2, ::2] = 10.0
        dem[1::2, 1::2] = 10.0
        tri = riley_tri(dem)
        # Interior should be positive (neighbours differ)
        assert tri[5:-5, 5:-5].min() > 0

    def test_output_non_negative(self):
        """TRI should always be non-negative."""
        from pipeline.geographic.derive import riley_tri
        rng = np.random.default_rng(99)
        dem = rng.uniform(0, 500, (40, 40))
        tri = riley_tri(dem)
        assert (tri >= 0).all()


class TestGwaHumanBytes:
    """wind.gwa.human_bytes formats consistently with common.geo.human_bytes."""

    def test_matches_common(self):
        from pipeline.wind.gwa import human_bytes as wind_hb
        from pipeline.common.geo import human_bytes as common_hb
        for n in [0, 100, 1000, 1_000_000, 1_500_000_000]:
            assert wind_hb(n) == common_hb(n)
