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

CAPAD_PATH = _geo_config.GEO_DIR / "protected" / "dcceew_capad-terrestrial_2024_nsw.geojson"
URBAN_PATH = _geo_config.GEO_DIR / "urban" / f"abs_ucl_2021_{_geo_config.DEFAULT_AREA}.geojson"
# ABS UCL/SOS ("Section of State") classification: sos_code_2021 == "13" is
# "Rural Balance" — the catch-all polygon covering everything OUTSIDE every
# actual urban centre/locality in the state (its own geometry spans well
# beyond the New England REZ, out past the NSW coastline). It is not an
# urban area and MUST be excluded from the urban-overlap test, or almost
# every rural cell in the state is incorrectly flagged as urban. Real
# urban features carry sos_code_2021 "11" (Other Urban) or "12" (Bounded
# Locality) — both are genuine urban centres/localities per the ABS UCL
# structure and are kept.
URBAN_EXCLUDE_SOS_CODES = {"13"}
SLOPE_RASTER_PATH = (
    _geo_config.GEO_DIR / "elevation" / f"srtm-gl3_slope-horn_90m_{_geo_config.DEFAULT_AREA}.tif"
)
WIND_SPEED_RASTER_PATH = (
    _wind_config.WIND_DIR / f"gwa_v4_wind-speed_100m_{_wind_config.DEFAULT_AREA}.tif"
)

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
    "protected_area",
    "protected_area_name",
    "slope_deg",
    "urban_area",
    "wind_speed_100m_ms",
    "data_flags",
]
