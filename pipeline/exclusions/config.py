"""
Configuration for the exclusion-layer pipeline stage (S1-07).

All exclusion-specific paths and constants live here, following the same
per-subpackage config.py pattern as wind/geographic/grid. Shared
project-level constants and the storage/computation CRS are re-exported
from grid/config.py (the authoritative source — see grid/config.py's own
docstring), not re-declared, to avoid the constant-duplication hazard noted
in the S1-06 design ("integration/analyse.py and validate.py re-hardcode
GWA_ORIGIN/CELL_DEG").
"""

from pathlib import Path

from .. import config as _shared
from ..demand import config as _demand_config
from ..geographic import config as _geo_config
from ..grid import config as _grid_config
from ..wind import config as _wind_config

PROJECT_ROOT = _shared.PROJECT_ROOT

# --- CRS (authoritative source: grid/config.py) ---
STORAGE_CRS = _grid_config.STORAGE_CRS  # "EPSG:4326"
COMPUTATION_CRS = _grid_config.COMPUTATION_CRS  # "EPSG:3577"

# --- Output directories ---
EXCLUSIONS_DIR = PROJECT_ROOT / "DATA" / "exclusions"
EXCLUSIONS_META_DIR = EXCLUSIONS_DIR / "metadata"

OUTPUT_FILENAME = "optmining_exclusions_2024_nsw.gpkg"
REPORT_FILENAME = "exclusion_summary.md"

# --- Inputs ---
# The grid file's name is not exported as a constant by pipeline/grid/generate.py
# (it is written inline in that module's run()), so it is repeated here verbatim.
GRID_PATH = _grid_config.PROJECT_ROOT / "DATA" / "grid" / "nsw_analysis_grid.gpkg"

# --- Feature-table inputs (joined on cell_id) ---
# The exclusion stage no longer samples raw rasters/vectors; it joins the
# per-cell feature tables the upstream stages already produce (S1-03 wind,
# S1-06 geographic), each statewide-NSW and keyed on cell_id. These two
# constants are composed from the producing domains' own configs — never
# re-typed literals — and mirror integration/config.py's WIND_PATH /
# GEOGRAPHIC_PATH so an upstream rename flows through both.
WIND_FEATURE_PATH = (
    _wind_config.WIND_FEATURES_DIR
    / f"gwa_v4_wind-feature_{_wind_config.WIND_FEATURE_VINTAGE}_nsw.gpkg"
)
WIND_FEATURE_LAYER = "wind_features"  # wind/features.py FEATURE_LAYER

GEOGRAPHIC_FEATURE_PATH = (
    _geo_config.GEO_DIR / "features" / "optmining_geographic-features_2024_nsw.gpkg"
)
GEOGRAPHIC_FEATURE_LAYER = "geographic_features"  # geographic/features.py OUTPUT_LAYER

# Demand-proxy feature table (S1-04). The exclusion stage joins demand_proxy
# so the `missing_demand_data` rule can exclude any cell lacking a demand
# value — demand_proxy is a scored criterion (S2-01), so a null here would
# otherwise let a cell be scored on missing critical data (the enclave the
# statewide expansion surfaced: AEMO demand is allocated by NEM region, and
# cells mapping to no region — e.g. the ACT enclave — carry a null proxy).
# Composed from the demand domain's own config, mirroring
# integration/config.py's DEMAND_PATH / DEMAND_LAYER so a rename flows through.
DEMAND_FEATURE_PATH = _demand_config.OUTPUT_DIR / _demand_config.FEATURE_TABLE_NAME
DEMAND_FEATURE_LAYER = _demand_config.FEATURE_TABLE_LAYER  # "demand_proxy"

# --- Rules config ---
DEFAULT_RULES_PATH = Path(__file__).resolve().parent / "exclusion_rules.yaml"

# --- Output schema conventions ---
# Delimiter for joining MULTIPLE distinct protected-area names within one
# cell's `protected_area_name` field. Deliberately distinct from
# rules.REASON_DELIMITER (", "), which joins multiple *rule* reasons at the
# top level (per the ticket's Output Format example) — the two delimiters
# nest without ambiguity: "Slope exceeds 15°, Protected area: A; B".
PROTECTED_AREA_NAME_DELIMITER = "; "
UNNAMED_PROTECTED_AREA_PLACEHOLDER = "(unnamed protected area)"

OUTPUT_COLUMNS = [
    "cell_id",
    "eligible",
    "exclusion_reason",
    "triggered_rules",
    "exclusion_reasons",
    "protected_area",
    "protected_area_name",
    "slope_deg",
    "urban_area",
    "wind_speed_100m_ms",
    "data_flags",
]
