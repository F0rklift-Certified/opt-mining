"""
Grid configuration — constants for the common analysis cell.

These values define the spatial grid that underpins the entire scoring pipeline.
They are derived from the Global Wind Atlas v4 raster specification (Task 1)
and the site definition decision (Sprint 0, Task 5 / Sprint 1, S1-02).

All constants here align with pipeline/integration/analyse.py. If those values
ever diverge, this module is authoritative for Sprint 1 onwards.
"""

from pathlib import Path

from .. import config as pipeline_config

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = pipeline_config.PROJECT_ROOT
GRID_OUTPUT_DIR = PROJECT_ROOT / "DATA" / "grid"

# Pre-downloaded ABS state boundary (from Sprint 0 geographic pipeline)
ABS_STE_PATH = (
    PROJECT_ROOT / "DATA" / "geographic" / "boundaries"
    / "abs_ste_2021_national.geojson"
)

# ---------------------------------------------------------------------------
# GWA v4 raster lattice (from Task 1 inspection)
# ---------------------------------------------------------------------------

# Western and northern edge of the Australian GWA v4 coverage
GWA_ORIGIN_LON: float = 109.21125
GWA_ORIGIN_LAT: float = -8.86125

# Native pixel size in degrees
GWA_STEP_DEG: float = 0.0025

# ---------------------------------------------------------------------------
# Analysis cell specification
# ---------------------------------------------------------------------------

# Number of native GWA pixels per analysis cell side
CELL_FACTOR: int = 20

# Cell size in degrees (0.05 deg = 20 * 0.0025 deg)
CELL_DEG: float = GWA_STEP_DEG * CELL_FACTOR  # 0.05

# ---------------------------------------------------------------------------
# NSW bounding box (W, S, E, N) in EPSG:4326
# Derived from ABS STE 2021 state boundary geometry extent
# ---------------------------------------------------------------------------

NSW_BBOX: tuple[float, float, float, float] = (141.0, -37.55, 153.7, -28.15)

# ---------------------------------------------------------------------------
# Coordinate Reference Systems
# ---------------------------------------------------------------------------

# Storage CRS — native CRS of the largest dataset (GWA). All grid outputs and
# feature layers are stored in this CRS.
STORAGE_CRS: str = "EPSG:4326"

# Computation CRS — Australian Albers Equal Area. Used for distance (km) and
# area (km^2) calculations. Degrees are not a unit of length.
COMPUTATION_CRS: str = "EPSG:3577"

# ---------------------------------------------------------------------------
# Earth geometry constants (for representative dimension reporting)
# ---------------------------------------------------------------------------

M_PER_DEG_LAT: float = 111_132.0
M_PER_DEG_LON_EQ: float = 111_320.0
