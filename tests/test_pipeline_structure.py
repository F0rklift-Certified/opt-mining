"""
Smoke tests for the modularized pipeline structure.

Verifies that each subpackage's run() functions are importable,
configs don't have circular imports, and the stage list in the
orchestrator matches what's actually available.
"""

import importlib

import pytest

from pipeline import config

# Modules that require rasterio at import time
_NEEDS_RASTERIO = [
    "pipeline.wind.download",
    "pipeline.wind.inspect",
    "pipeline.wind.validate",
    "pipeline.wind.analyse",
    "pipeline.geographic.download",
    "pipeline.geographic.inspect",
    "pipeline.geographic.derive",
    "pipeline.geographic.validate",
    "pipeline.validate",
]


def _try_import(module_name: str):
    """Import a module, skipping if rasterio is unavailable."""
    try:
        return importlib.import_module(module_name)
    except ModuleNotFoundError as e:
        if "rasterio" in str(e):
            pytest.skip("rasterio not installed")
        raise


# ---------------------------------------------------------------------------
# Subpackage import tests
# ---------------------------------------------------------------------------


class TestWindImports:
    """Wind subpackage modules are importable."""

    def test_config(self):
        from pipeline.wind import config as wc
        assert hasattr(wc, "WIND_DIR")
        assert hasattr(wc, "GWA_API_BASE")

    def test_gwa(self):
        from pipeline.wind.gwa import api_url, human_bytes, resolve_source
        assert callable(api_url)
        assert callable(resolve_source)
        assert human_bytes(1_000_000) == "1.0 MB"

    def test_probe(self):
        from pipeline.wind.probe import run
        assert callable(run)

    def test_download(self):
        mod = _try_import("pipeline.wind.download")
        assert hasattr(mod, "run")

    def test_inspect(self):
        mod = _try_import("pipeline.wind.inspect")
        assert hasattr(mod, "run")

    def test_validate(self):
        mod = _try_import("pipeline.wind.validate")
        assert hasattr(mod, "run")

    def test_analyse(self):
        mod = _try_import("pipeline.wind.analyse")
        assert hasattr(mod, "run")


class TestGeographicImports:
    """Geographic subpackage modules are importable."""

    def test_config(self):
        from pipeline.geographic import config as gc
        assert hasattr(gc, "GEO_DIR")
        assert hasattr(gc, "ABS_ASGS_BASE")

    def test_probe(self):
        from pipeline.geographic.probe import run
        assert callable(run)

    def test_download(self):
        mod = _try_import("pipeline.geographic.download")
        assert hasattr(mod, "run")

    def test_inspect(self):
        mod = _try_import("pipeline.geographic.inspect")
        assert hasattr(mod, "run")

    def test_derive(self):
        mod = _try_import("pipeline.geographic.derive")
        assert hasattr(mod, "run")

    def test_validate(self):
        mod = _try_import("pipeline.geographic.validate")
        assert hasattr(mod, "run")

    def test_features(self):
        mod = _try_import("pipeline.geographic.features")
        assert hasattr(mod, "run")


class TestInfrastructureImports:
    """Infrastructure subpackage modules are importable."""

    def test_config(self):
        from pipeline.infrastructure import config as ic
        assert hasattr(ic, "INFRA_DIR")
        assert hasattr(ic, "EXPECTED_FILES")

    def test_helpers(self):
        from pipeline.infrastructure.helpers import (
            load_geojson, filter_by_state, compute_bounds,
        )
        assert callable(load_geojson)

    def test_download(self):
        from pipeline.infrastructure.download import run
        assert callable(run)

    def test_inspect(self):
        mod = _try_import("pipeline.infrastructure.inspect")
        assert hasattr(mod, "run")


class TestDemandImports:
    """Demand subpackage modules are importable."""

    def test_config(self):
        from pipeline.demand import config as dc
        assert hasattr(dc, "OUTPUT_DIR")
        assert hasattr(dc, "STAGES")


class TestTopLevel:
    """Top-level pipeline modules are importable and consistent."""

    def test_validate(self):
        mod = _try_import("pipeline.validate")
        assert hasattr(mod, "run")

    def test_config_stages_list(self):
        assert isinstance(config.STAGES, list)
        assert len(config.STAGES) > 0
        # Every stage should be resolvable by the orchestrator
        assert "wind.probe" in config.STAGES
        assert "geographic.derive" in config.STAGES
        assert "infrastructure.inspect" in config.STAGES
        assert "demand" in config.STAGES
        assert "validate" in config.STAGES
        # geographic.features consumes the grid, so it must be registered
        # after the grid stage that produces it (Req 10.4, 10.7).
        assert "geographic.features" in config.STAGES
        assert config.STAGES.index("geographic.features") > config.STAGES.index("grid")

    def test_config_domains(self):
        assert "wind" in config.DOMAINS
        assert "geographic" in config.DOMAINS
        assert "infrastructure" in config.DOMAINS
        assert "demand" in config.DOMAINS

    def test_common_geo(self):
        from pipeline.common.geo import (
            human_bytes, atomic_write_text, banner, utc_now,
        )
        assert human_bytes(500) == "500.0 B"
        assert "pipeline." in banner("test")


# ---------------------------------------------------------------------------
# Orchestrator resolution tests
# ---------------------------------------------------------------------------


class TestOrchestratorResolution:
    """CLI stage resolution logic works correctly."""

    def test_only_domain(self):
        import sys
        sys.argv = ["test", "--only", "wind"]
        from pipeline.__main__ import parse_args, resolve_stages
        args = parse_args()
        stages = resolve_stages(args)
        assert all(s.startswith("wind.") for s in stages)
        assert len(stages) == 5

    def test_only_geographic_domain(self):
        # geographic now resolves 6 stages (was 5) after registering
        # geographic.features (S1-06 feature builder).
        import sys
        sys.argv = ["test", "--only", "geographic"]
        from pipeline.__main__ import parse_args, resolve_stages
        args = parse_args()
        stages = resolve_stages(args)
        assert all(s.startswith("geographic.") for s in stages)
        assert len(stages) == 6

    def test_only_single_stage(self):
        import sys
        sys.argv = ["test", "--only", "geographic.derive"]
        from pipeline.__main__ import parse_args, resolve_stages
        args = parse_args()
        stages = resolve_stages(args)
        assert stages == ["geographic.derive"]

    def test_skip_domain(self):
        import sys
        sys.argv = ["test", "--skip", "demand", "--skip", "infrastructure"]
        from pipeline.__main__ import parse_args, resolve_stages
        args = parse_args()
        stages = resolve_stages(args)
        assert "demand" not in stages
        assert not any(s.startswith("infrastructure.") for s in stages)
        assert "wind.probe" in stages

    def test_skip_validate(self):
        import sys
        sys.argv = ["test", "--skip-validate"]
        from pipeline.__main__ import parse_args, resolve_stages
        args = parse_args()
        stages = resolve_stages(args)
        assert "validate" not in stages
