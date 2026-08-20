"""
Configuration for the wind resource pipeline.

All GWA-specific paths, URLs and constants live here. Shared project-level
constants (PROJECT_ROOT, DEFAULT_BBOX, VSICURL_ENV, etc.) are imported from
the top-level pipeline config.
"""

from pathlib import Path

from .. import config as _shared

# Re-export shared constants used throughout wind stages
PROJECT_ROOT = _shared.PROJECT_ROOT
DEFAULT_BBOX = _shared.DEFAULT_BBOX
DEFAULT_AREA = _shared.DEFAULT_AREA
TIMEOUT = _shared.TIMEOUT
VSICURL_ENV = _shared.VSICURL_ENV

# --- Wind output directories ---
WIND_DIR = PROJECT_ROOT / "DATA" / "wind-resource"
WIND_META_DIR = WIND_DIR / "metadata"
WIND_REF_DIR = WIND_DIR / "reference"

# --- Global Wind Atlas ---
GWA_API_BASE = "https://globalwindatlas.info/api/gis/country"
GWA_COUNTRY = "AUS"
GWA_TIMEOUT = 60

GWA_DEFAULT_SAMPLES = [
    ("wind-speed", 50),
    ("wind-speed", 100),
    ("wind-speed", 150),
    ("power-density", 100),
    ("capacity-factor_IEC2", None),
]

GWA_HEIGHTS = [10, 50, 100, 150, 200]
GWA_HEIGHT_VARIABLES = [
    ("wind-speed", "m/s", "10-year mean wind speed"),
    ("power-density", "W/m^2", "10-year mean wind power density"),
    ("air-density", "kg/m^3", "Modelled air density"),
    ("combined-Weibull-A", "m/s", "All-sector Weibull scale parameter"),
    ("combined-Weibull-k", "-", "All-sector Weibull shape parameter"),
]
GWA_FLAT_VARIABLES = [
    ("capacity-factor_IEC1", "ratio", "IEC class 1 turbine, 100 m hub, 117 m rotor"),
    ("capacity-factor_IEC2", "ratio", "IEC class 2 turbine, 100 m hub, 136 m rotor"),
    ("capacity-factor_IEC3", "ratio", "IEC class 3 turbine, 100 m hub, 150 m rotor"),
    ("capacity-factor_offshore", "ratio", "Offshore turbine, 150 m hub, 150 m rotor"),
    ("RIX", "%", "Ruggedness index — area within 3.5 km with slopes over 30 degrees"),
    ("elevation", "m", "Site elevation used by the Atlas"),
]

# --- Aggregation grid ---
# 20 × 0.0025° = 0.05° ≈ 5 km cell. Matches Product Knowledge Base target.
AGGREGATION_FACTOR = 20
NATIVE_PIXEL_DEG = 0.0025  # GWA native pixel size
