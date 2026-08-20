"""
Configuration for the infrastructure pipeline.

All infrastructure-specific paths, URLs and constants live here. Shared
project-level constants are imported from the top-level pipeline config.
"""

from pathlib import Path

from .. import config as _shared

# Re-export shared constants used throughout infrastructure stages
PROJECT_ROOT = _shared.PROJECT_ROOT
TIMEOUT = _shared.TIMEOUT

# --- Infrastructure directories ---
INFRA_DIR = PROJECT_ROOT / "DATA" / "infrastructure"
INFRA_META_DIR = INFRA_DIR / "metadata"

# --- Geoscience Australia endpoint ---
GA_INFRA_BASE = "https://services.ga.gov.au/gis/rest/services/Electricity_Infrastructure/MapServer"

# --- Default filters ---
DEFAULT_STATE = "NSW"
DEFAULT_FUEL_TYPE = "wind"

# --- Expected pre-downloaded files ---
EXPECTED_FILES = [
    "generators/ga_powerstations_2026_australia.geojson",
    "substations/ga_substations_2026_australia.geojson",
    "transmission-lines/ga_power_lines_2026_part_001.geojson",
    "transmission-lines/ga_power_lines_2026_part_002.geojson",
    "connection-points/aemo_kci_2026.xlsx",
]
