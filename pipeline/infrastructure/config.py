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

# --- S1-05 feature layer ---
GRID_PATH = PROJECT_ROOT / "DATA" / "grid" / "nsw_analysis_grid.gpkg"
TRANSMISSION_PATH = INFRA_DIR / "transmission-lines" / "ga_power_lines_2026_nsw.geojson"
SUBSTATION_PATH = INFRA_DIR / "substations" / "ga_substations_2026_nsw.geojson"
GENERATOR_PATH = INFRA_DIR / "generators" / "ga_powerstations_2026_australia.geojson"
CONNECTION_POINTS_PATH = INFRA_DIR / "connection-points" / "aemo_kci_2026.xlsx"
REZ_DIR = INFRA_DIR / "renewable-energy-zones" / "energyco-nsw"
FEATURE_TABLE_NAME = "optmining_infra-features_2026_nsw.gpkg"
FEATURE_TABLE_LAYER = "infra_features"
METHOD_REPORT_NAME = "infrastructure_features_method.md"
FEATURE_MANIFEST_NAME = "download_manifest.json"
STORAGE_CRS = "EPSG:4326"
COMPUTATION_CRS = "EPSG:3577"
GA_SOURCE_CRS = "EPSG:7844"
REZ_NAME_DELIMITER = "; "
UNNAMED_REZ = "UNNAMED_REZ"
CONFIDENCE_LEVELS = ("high", "low")

# --- Expected pre-downloaded files ---
EXPECTED_FILES = [
    "generators/ga_powerstations_2026_australia.geojson",
    "substations/ga_substations_2026_nsw.geojson",
    "transmission-lines/ga_power_lines_2026_nsw.geojson",
    "connection-points/aemo_kci_2026.xlsx",
    "renewable-energy-zones/energyco-nsw/energyco_new_england_rez_boundary.zip",
    "renewable-energy-zones/energyco-nsw/energyco_central_west_orana_rez_boundary.zip",
    "renewable-energy-zones/energyco-nsw/energyco_hunter_central_coast_rez_boundary.zip",
]
