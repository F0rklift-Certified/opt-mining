"""
Shared configuration for the data pipeline.

Only project-level constants that are used across multiple subpackages
live here. Domain-specific configuration lives in each subpackage's
own config.py (wind/config.py, geographic/config.py, etc.).
"""

from pathlib import Path

# --- Directory layout ---
PIPELINE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PIPELINE_DIR.parent

# --- Study window ---
# New England REZ, NSW — approx. 2 deg x 2 deg (~190 km E-W x ~222 km N-S).
DEFAULT_BBOX = (150.0, -31.5, 152.0, -29.5)
DEFAULT_AREA = "new-england-rez"

# GL1 sub-window — 0.5 deg around the two operating wind farms.
GL1_BBOX = (151.5, -30.0, 152.0, -29.5)
GL1_AREA = "glen-innes"

# Coastal strip for land-mask assessment (NSW coast).
COAST_BBOX = (150.0, -35.0, 154.0, -28.0)

# --- Request settings ---
TIMEOUT = 120
REQUEST_DELAY = 0.5  # polite delay between paginated requests

# --- GDAL environment ---
VSICURL_ENV = {
    "GDAL_DISABLE_READDIR_ON_OPEN": "EMPTY_DIR",
    "CPL_VSIL_CURL_ALLOWED_EXTENSIONS": ".tif,.vrt,.zip",
    "GDAL_HTTP_MAX_RETRY": "3",
    "GDAL_HTTP_RETRY_DELAY": "2",
}

# --- Pipeline stages (domain-sequential execution order) ---
STAGES = [
    "wind.probe",
    "wind.download",
    "wind.inspect",
    "wind.validate",
    "wind.analyse",
    "geographic.probe",
    "geographic.download",
    "geographic.inspect",
    "geographic.derive",
    "geographic.validate",
    "infrastructure.download",
    "infrastructure.inspect",
    "demand",
    "grid",  # common analysis cell (S1-02) — must run before feature layers
    "validate",  # cross-domain integration checks
]

# --- Domain list ---
DOMAINS = ["wind", "geographic", "infrastructure", "demand", "grid"]
