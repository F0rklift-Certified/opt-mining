"""
Configuration for the geographic & environmental pipeline.

All geographic-specific paths, URLs and constants live here. Shared
project-level constants are imported from the top-level pipeline config.
"""

from pathlib import Path

from .. import config as _shared

# Re-export shared constants used throughout geographic stages
PROJECT_ROOT = _shared.PROJECT_ROOT
DEFAULT_BBOX = _shared.DEFAULT_BBOX
DEFAULT_AREA = _shared.DEFAULT_AREA
GL1_BBOX = _shared.GL1_BBOX
GL1_AREA = _shared.GL1_AREA
COAST_BBOX = _shared.COAST_BBOX
TIMEOUT = _shared.TIMEOUT
REQUEST_DELAY = _shared.REQUEST_DELAY
VSICURL_ENV = _shared.VSICURL_ENV

# --- Geographic output directories ---
GEO_DIR = PROJECT_ROOT / "DATA" / "geographic"
GEO_META_DIR = GEO_DIR / "metadata"
GEO_RAW_DIR = GEO_DIR / "raw"

# --- ArcGIS REST endpoints ---
ABS_ASGS_BASE = "https://geo.abs.gov.au/arcgis/rest/services/ASGS2021"
CAPAD_BASE = (
    "https://gis.environment.gov.au/gispubmap/rest/services/ogc_services/CAPAD/FeatureServer"
)

# --- SRTM public mirror (OpenTopography S3) ---
SRTM_GL1_VRT = "https://opentopography.s3.sdsc.edu/raster/SRTM_GL1/SRTM_GL1_srtm.vrt"
SRTM_GL3_VRT = "https://opentopography.s3.sdsc.edu/raster/SRTM_GL3/SRTM_GL3_srtm.vrt"

# --- ABARES NLUM ---
NLUM_ZIP_URL = (
    "https://www.agriculture.gov.au/sites/default/files/documents/"
    "NLUM_v7_1_250m_ALUMV8_2020_21_alb_20260814.zip"
)

# --- Natural Earth coastline ---
NE_LAND_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/"
    "geojson/ne_50m_land.geojson"
)

# --- Derived constants ---
# Commit guardrail: GeoJSON files larger than this are re-fetched with
# server-side generalisation.
MAX_COMMIT_BYTES = 10 * 10**6
GENERALISE_OFFSET_DEG = 0.0005

# Australia bounding box for Natural Earth filtering
AUS_BBOX = (112.0, -44.5, 154.5, -9.0)

# NEM regions derivation mapping (state codes from ABS STE layer)
NEM_REGIONS = {
    "NSW1": ["1", "8"],
    "VIC1": ["2"],
    "QLD1": ["3"],
    "SA1": ["4"],
    "TAS1": ["6"],
}
