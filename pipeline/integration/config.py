"""
Configuration for the S1-08 integration stage (`integration`).

Every INPUT path below is composed from the producing domain's own config
module, never re-typed as a literal, so an upstream rename propagates here
and a test can redirect a layer by monkeypatching one attribute. The two
exceptions — the geographic and wind feature-table constants — live in
`pipeline/geographic/features.py` and `pipeline/wind/features.py`, both of
which import rasterio at module load; the integration stage needs no
rasterio, so those two are repeated as literals and pinned by
`tests/test_pipeline_structure.py::TestIntegrationImports`
(`test_config_matches_rasterio_backed_upstream_modules`).

CRS constants are re-exported from grid/config.py (the authoritative source),
following pipeline/exclusions/config.py.
"""

from .. import config as _shared
from ..demand import config as _demand_config
from ..exclusions import config as _excl_config
from ..geographic import config as _geo_config
from ..grid import config as _grid_config
from ..infrastructure import config as _infra_config
from ..wind import config as _wind_config

PROJECT_ROOT = _shared.PROJECT_ROOT

# --- CRS (authoritative source: grid/config.py) ---
STORAGE_CRS = _grid_config.STORAGE_CRS  # "EPSG:4326" — every input and the output
COMPUTATION_CRS = _grid_config.COMPUTATION_CRS  # "EPSG:3577" — recorded only; nothing is computed here

# --- Output locations ---
INTEGRATION_DIR = PROJECT_ROOT / "DATA" / "integration"
INTEGRATION_META_DIR = INTEGRATION_DIR / "metadata"

# Vintage token = the newest upstream vintage the table merges
# (infrastructure 2026, demand 2026, wind 2025, geographic/exclusions 2024).
INTEGRATION_VINTAGE = "2026"
OUTPUT_FILENAME = f"optmining_integrated-features_{INTEGRATION_VINTAGE}_nsw.gpkg"
CSV_FILENAME = f"optmining_integrated-features_{INTEGRATION_VINTAGE}_nsw.csv"
OUTPUT_LAYER = "integrated_features"
METHOD_REPORT_FILENAME = "integration_method.md"
VALIDATION_REPORT_FILENAME = "merge_validation.md"
MANIFEST_FILENAME = "integration_manifest.json"

# --- Inputs (one row per grid cell each; all stored in STORAGE_CRS) ---
# Grid (S1-02). The filename is written inline by grid/generate.py, so the
# other consumers (wind/features.py, exclusions/config.py) repeat it; reuse
# the exclusions constant rather than adding a fourth copy.
GRID_PATH = _excl_config.GRID_PATH
GRID_LAYER = "nsw_grid"  # grid/generate.py to_file(layer=...)

# Wind feature table (S1-03) — wind/features.py composes the same name.
WIND_PATH = (
    _wind_config.WIND_FEATURES_DIR
    / f"gwa_v4_wind-feature_{_wind_config.WIND_FEATURE_VINTAGE}_nsw.gpkg"
)
WIND_LAYER = "wind_features"  # wind/features.py FEATURE_LAYER

# Geographic & environmental feature table (S1-06) — geographic/features.py
# OUTPUT_PATH / OUTPUT_LAYER (rasterio-backed module; literals pinned by test).
GEOGRAPHIC_PATH = _geo_config.GEO_DIR / "features" / "optmining_geographic-features_2024_nsw.gpkg"
GEOGRAPHIC_LAYER = "geographic_features"

# Infrastructure feature table (S1-05).
INFRA_PATH = _infra_config.INFRA_DIR / _infra_config.FEATURE_TABLE_NAME
INFRA_LAYER = _infra_config.FEATURE_TABLE_LAYER

# Demand proxy feature table (S1-04).
DEMAND_PATH = _demand_config.OUTPUT_DIR / _demand_config.FEATURE_TABLE_NAME
DEMAND_LAYER = _demand_config.FEATURE_TABLE_LAYER

# Exclusions Eligibility_Table (S1-07). apply.py writes it without a
# `layer=` argument, so the layer name is whatever GDAL derived from the
# temporary filename; None means "auto-detect the single layer".
EXCLUSIONS_PATH = _excl_config.EXCLUSIONS_DIR / _excl_config.OUTPUT_FILENAME
EXCLUSIONS_LAYER = None

# --- Per-layer confidence vocabularies (carried through, renamed per layer) ---
WIND_CONFIDENCE_LEVELS = (_wind_config.CONF_VALID, _wind_config.CONF_NODATA)
GEO_CONFIDENCE_LEVELS = ("high", "low")  # geographic/features.py CONFIDENCE_HIGH/LOW
INFRA_CONFIDENCE_LEVELS = _infra_config.CONFIDENCE_LEVELS
DEMAND_CONFIDENCE_LEVELS = _demand_config.CONFIDENCE_LEVELS

# --- Cross-layer consistency tolerances (WARN checks, never fatal) ---
# S1-07 recomputes slope and wind speed from the rasters with its own zonal
# code path; values should agree to well within these tolerances.
SLOPE_TOLERANCE_DEG = 0.05
WIND_TOLERANCE_MS = 0.01
