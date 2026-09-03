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
    "pipeline.wind.features",
    "pipeline.geographic.download",
    "pipeline.geographic.inspect",
    "pipeline.geographic.derive",
    "pipeline.geographic.validate",
    "pipeline.validate",
    "pipeline.exclusions.apply",
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

    def test_features(self):
        mod = _try_import("pipeline.wind.features")
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


class TestExclusionsImports:
    """Exclusion-layer subpackage modules are importable (S1-07)."""

    def test_config(self):
        from pipeline.exclusions import config as ec
        assert hasattr(ec, "EXCLUSIONS_DIR")
        assert hasattr(ec, "DEFAULT_RULES_PATH")

    def test_rules(self):
        from pipeline.exclusions.rules import evaluate_cell, load_rules
        assert callable(load_rules)
        assert callable(evaluate_cell)

    def test_apply(self):
        mod = _try_import("pipeline.exclusions.apply")
        assert hasattr(mod, "run")


class TestIntegrationImports:
    """Integration subpackage: Task 5 analyse plus the S1-08 merge stage."""

    _CONFIG_ATTRS = (
        "INTEGRATION_DIR", "INTEGRATION_META_DIR", "INTEGRATION_VINTAGE",
        "OUTPUT_FILENAME", "CSV_FILENAME", "OUTPUT_LAYER",
        "METHOD_REPORT_FILENAME", "VALIDATION_REPORT_FILENAME", "MANIFEST_FILENAME",
        "GRID_PATH", "GRID_LAYER", "WIND_PATH", "WIND_LAYER",
        "GEOGRAPHIC_PATH", "GEOGRAPHIC_LAYER", "INFRA_PATH", "INFRA_LAYER",
        "DEMAND_PATH", "DEMAND_LAYER", "EXCLUSIONS_PATH", "EXCLUSIONS_LAYER",
        "STORAGE_CRS", "COMPUTATION_CRS",
        "WIND_CONFIDENCE_LEVELS", "GEO_CONFIDENCE_LEVELS",
        "INFRA_CONFIDENCE_LEVELS", "DEMAND_CONFIDENCE_LEVELS",
        "SLOPE_TOLERANCE_DEG", "WIND_TOLERANCE_MS",
        # S1-09 confidence layer
        "SCORED_FEATURE_COLUMNS", "CONFIDENCE_COLUMNS", "DATA_CONFIDENCE_LEVELS",
        "CONFIDENCE_FLAG_COLUMNS", "CONFIDENCE_NOTE_DELIMITER", "CONFIDENCE_NO_NOTES",
        "CONFIDENCE_SCORE_DECIMALS", "DEFAULT_CONFIDENCE_WEIGHTS_PATH",
        "CONFIDENCE_METHOD_FILENAME", "CONFIDENCE_SUMMARY_FILENAME",
        "GRID_ORIGIN_LON", "GRID_ORIGIN_LAT", "CELL_DEG",
    )

    def test_config(self):
        from pipeline.integration import config as ic
        missing = [name for name in self._CONFIG_ATTRS if not hasattr(ic, name)]
        assert missing == []

    def test_config_paths_derive_from_upstream_configs(self):
        # Every input path is composed from the producing domain's config so a
        # rename upstream propagates here (and tests can monkeypatch one place).
        from pipeline.demand import config as dc
        from pipeline.exclusions import config as ec
        from pipeline.infrastructure import config as infc
        from pipeline.integration import config as ic
        from pipeline.wind import config as wc
        assert ic.GRID_PATH == ec.GRID_PATH
        assert ic.WIND_PATH.parent == wc.WIND_FEATURES_DIR
        assert wc.WIND_FEATURE_VINTAGE in ic.WIND_PATH.name
        assert ic.INFRA_PATH == infc.INFRA_DIR / infc.FEATURE_TABLE_NAME
        assert ic.INFRA_LAYER == infc.FEATURE_TABLE_LAYER
        assert ic.INFRA_CONFIDENCE_LEVELS == infc.CONFIDENCE_LEVELS
        assert ic.DEMAND_PATH == dc.OUTPUT_DIR / dc.FEATURE_TABLE_NAME
        assert ic.DEMAND_LAYER == dc.FEATURE_TABLE_LAYER
        assert ic.DEMAND_CONFIDENCE_LEVELS == dc.CONFIDENCE_LEVELS
        assert ic.EXCLUSIONS_PATH == ec.EXCLUSIONS_DIR / ec.OUTPUT_FILENAME
        assert ic.EXCLUSIONS_LAYER is None  # apply.py writes without layer=; auto-detect
        assert ic.WIND_CONFIDENCE_LEVELS == (wc.CONF_VALID, wc.CONF_NODATA)
        assert ic.STORAGE_CRS == ec.STORAGE_CRS == "EPSG:4326"
        assert ic.OUTPUT_FILENAME.endswith(".gpkg") and ic.CSV_FILENAME.endswith(".csv")
        assert ic.INTEGRATION_META_DIR.parent == ic.INTEGRATION_DIR

    def test_config_matches_rasterio_backed_upstream_modules(self):
        # geographic/wind constants live in modules that import rasterio, so the
        # integration config repeats them as literals; guard against drift here.
        geo = _try_import("pipeline.geographic.features")
        wind = _try_import("pipeline.wind.features")
        from pipeline.integration import config as ic
        assert ic.GEOGRAPHIC_PATH == geo.OUTPUT_PATH
        assert ic.GEOGRAPHIC_LAYER == geo.OUTPUT_LAYER
        assert ic.GEO_CONFIDENCE_LEVELS == (geo.CONFIDENCE_HIGH, geo.CONFIDENCE_LOW)
        assert ic.WIND_LAYER == wind.FEATURE_LAYER
        assert ic.GRID_LAYER == wind.GRID_LAYER
        assert ic.GRID_PATH == wind.GRID_PATH

    def test_analyse(self):
        from pipeline.integration.analyse import run
        assert callable(run)

    def test_default_confidence_weights_file_exists_and_loads(self):
        from pipeline.integration import config as ic
        from pipeline.integration.confidence import load_weights
        assert ic.DEFAULT_CONFIDENCE_WEIGHTS_PATH.exists()
        assert load_weights(ic.DEFAULT_CONFIDENCE_WEIGHTS_PATH).weight_sum > 0

    def test_merge_importable_without_rasterio(self):
        # The stage needs no rasterio: prove it in a fresh interpreter so an
        # earlier test importing rasterio cannot mask a regression.
        import subprocess
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        code = (
            "import sys; import pipeline.integration.merge as m; "
            "import pipeline.integration.confidence as c; "
            "assert callable(m.run) and callable(c.load_weights); "
            "assert 'rasterio' not in sys.modules, 'merge imported rasterio'"
        )
        proc = subprocess.run([sys.executable, "-c", code], cwd=root,
                              capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, proc.stderr


class TestScoringImports:
    """Scoring subpackage: the S1-10 baseline suitability model."""

    _CONFIG_ATTRS = (
        "INTEGRATED_PATH", "INTEGRATED_LAYER", "DEFAULT_WEIGHTS_PATH",
        "SCORING_DIR", "SCORING_META_DIR", "SCORING_VINTAGE",
        "OUTPUT_FILENAME", "CSV_FILENAME", "OUTPUT_LAYER",
        "METHOD_REPORT_FILENAME", "VALIDATION_REPORT_FILENAME",
        "MANIFEST_FILENAME", "SOURCE_REGISTER_FILENAME", "PROVENANCE_FILENAME",
        "CELL_ID_COLUMN", "ELIGIBLE_COLUMN", "CONFIDENCE_COLUMN",
        "CONFIDENCE_LEVELS", "SCORE_COLUMN", "RANK_COLUMN",
        "CONTRIBUTION_PREFIX", "OUTPUT_CONFIDENCE_COLUMN", "CARRIED_COLUMNS",
        "RECONCILE_TOLERANCE", "CONSTANT_CRITERION_VALUE", "BOOLEAN_BOUNDS",
        "HIGHER_IS_BETTER", "LOWER_IS_BETTER", "DIRECTIONS",
        "STORAGE_CRS", "COMPUTATION_CRS", "STAGE_NAME", "MODULE_NAME",
    )

    def test_config(self):
        from pipeline.scoring import config as sc
        missing = [name for name in self._CONFIG_ATTRS if not hasattr(sc, name)]
        assert missing == []

    def test_config_derives_from_upstream_configs(self):
        """
        Input path and the confidence vocabulary are composed from the
        producing domain's config, so an upstream rename propagates here
        rather than silently drifting.
        """
        from pipeline.grid import config as gc
        from pipeline.integration import config as ic
        from pipeline.scoring import config as sc

        assert sc.INTEGRATED_PATH == ic.INTEGRATION_DIR / ic.OUTPUT_FILENAME
        assert sc.INTEGRATED_LAYER == ic.OUTPUT_LAYER
        assert sc.CONFIDENCE_COLUMN == ic.CONFIDENCE_COLUMNS[0]
        assert sc.CONFIDENCE_LEVELS == ic.DATA_CONFIDENCE_LEVELS
        assert sc.STORAGE_CRS == gc.STORAGE_CRS
        assert sc.SCORING_VINTAGE == ic.INTEGRATION_VINTAGE

    def test_modules_importable(self):
        for name in ("weights", "load", "normalise", "score", "rank",
                     "write", "report", "validate", "run"):
            mod = _try_import(f"pipeline.scoring.{name}")
            assert mod is not None, name

    def test_run_entry_point(self):
        mod = _try_import("pipeline.scoring.run")
        assert hasattr(mod, "run") and callable(mod.run)

    def test_default_weights_file_exists_and_loads(self):
        from pipeline.scoring import config as sc
        from pipeline.scoring.weights import load_weights

        assert sc.DEFAULT_WEIGHTS_PATH.exists()
        weights = load_weights(sc.DEFAULT_WEIGHTS_PATH)
        assert weights.criteria and weights.weight_sum > 0
        assert all(c.rationale.strip() for c in weights.criteria)

    def test_scoring_importable_without_rasterio(self):
        """
        The scoring stage is pure pandas/geopandas/yaml — it must not drag in
        rasterio, so it can run in an environment without it (mirrors the
        same guarantee for integration.merge).
        """
        import subprocess
        import sys
        from pathlib import Path

        root = Path(__file__).resolve().parent.parent
        code = (
            "import sys; import pipeline.scoring.run as r; "
            "assert callable(r.run); "
            "assert 'rasterio' not in sys.modules, 'scoring imported rasterio'"
        )
        proc = subprocess.run([sys.executable, "-c", code], cwd=root,
                              capture_output=True, text=True, timeout=60)
        assert proc.returncode == 0, proc.stderr


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
        # wind.features consumes the grid, so it must be registered after
        # the grid stage that produces it (Req 6.3).
        assert "wind.features" in config.STAGES
        assert config.STAGES.index("wind.features") > config.STAGES.index("grid")
        assert config.STAGES.index("wind.features") < config.STAGES.index("validate")
        # geographic.features consumes the grid, so it must be registered
        # after the grid stage that produces it (Req 10.4, 10.7).
        assert "geographic.features" in config.STAGES
        assert config.STAGES.index("geographic.features") > config.STAGES.index("grid")
        # integration (S1-08) consumes every feature layer and the exclusion
        # layer, so it is scheduled after all of them and before validate.
        assert "integration" in config.STAGES
        for producer in ("wind.features", "geographic.features",
                         "infrastructure.features", "demand.feature", "exclusions"):
            assert config.STAGES.index(producer) < config.STAGES.index("integration")
        assert config.STAGES.index("integration") < config.STAGES.index("validate")
        # scoring (S1-10) consumes the integrated feature table, so the
        # producer is scheduled before this consumer, and before validate so
        # the cross-domain tier sees the scored output (Req 11.4, 11.8).
        assert "scoring" in config.STAGES
        assert config.STAGES.index("integration") < config.STAGES.index("scoring")
        assert config.STAGES.index("scoring") < config.STAGES.index("validate")

    def test_config_domains(self):
        assert "wind" in config.DOMAINS
        assert "geographic" in config.DOMAINS
        assert "infrastructure" in config.DOMAINS
        assert "demand" in config.DOMAINS
        assert "integration" in config.DOMAINS
        assert "scoring" in config.DOMAINS

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
        # wind now resolves 6 stages (was 5) after registering wind.features
        # (S1-03 feature builder), which sits after `grid` in STAGES.
        assert len(stages) == 6
        assert stages[-1] == "wind.features"

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

    def test_infrastructure_features_stage_and_crs_option(self):
        import sys
        sys.argv = [
            "test", "--only", "infrastructure.features",
            "--infra-features-crs", "EPSG:3857",
        ]
        from pipeline.__main__ import _build_kwargs, parse_args, resolve_stages
        args = parse_args()
        assert resolve_stages(args) == ["infrastructure.features"]
        kwargs = _build_kwargs(
            "infrastructure.features", args, (150.0, -31.5, 152.0, -29.5)
        )
        assert kwargs["computation_crs"] == "EPSG:3857"

    def test_infrastructure_features_rejects_geographic_crs(self):
        import sys
        sys.argv = ["test", "--infra-features-crs", "EPSG:4326"]
        from pipeline.__main__ import parse_args
        with pytest.raises(SystemExit):
            parse_args()

    def test_only_integration_resolves_single_stage(self):
        import sys
        sys.argv = ["test", "--only", "integration"]
        from pipeline.__main__ import parse_args, resolve_stages
        assert resolve_stages(parse_args()) == ["integration"]

    def test_get_runner_integration(self):
        from pipeline.__main__ import _get_runner
        assert _get_runner("integration").__module__ == "pipeline.integration.merge"

    def test_confidence_weights_flag_threads_into_integration_kwargs(self):
        import sys
        from pathlib import Path
        from pipeline.__main__ import _build_kwargs, parse_args
        bbox = (150.0, -31.5, 152.0, -29.5)
        sys.argv = ["test", "--only", "integration", "--confidence-weights", "custom.yaml"]
        assert _build_kwargs("integration", parse_args(), bbox)["weights_path"] == Path("custom.yaml")
        sys.argv = ["test", "--only", "integration"]
        assert "weights_path" not in _build_kwargs("integration", parse_args(), bbox)

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
