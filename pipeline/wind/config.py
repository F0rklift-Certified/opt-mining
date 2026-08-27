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

# --- Configurable defaults for CLI ---
DEFAULT_HEIGHTS = [50, 100, 150]
DEFAULT_TURBINE_CLASSES = ["IEC2"]
VALID_TURBINE_CLASSES = ["IEC1", "IEC2", "IEC3"]


def build_samples(
    heights: list[int] | None = None,
    turbine_classes: list[str] | None = None,
) -> list[tuple[str, int | None]]:
    """
    Build the GWA sample list from configurable heights and turbine classes.

    Parameters
    ----------
    heights : list[int] | None
        Hub heights in metres for wind-speed layers. None uses DEFAULT_HEIGHTS.
    turbine_classes : list[str] | None
        IEC turbine classes for capacity-factor layers. None uses DEFAULT_TURBINE_CLASSES.

    Returns
    -------
    list[tuple[str, int | None]]
        List of (variable, height_or_None) tuples for the download stage.
    """
    if heights is None:
        heights = DEFAULT_HEIGHTS
    if turbine_classes is None:
        turbine_classes = DEFAULT_TURBINE_CLASSES

    samples: list[tuple[str, int | None]] = []

    # Wind speed at each height
    for h in heights:
        samples.append(("wind-speed", h))

    # Power density at the primary height (max of requested, or 100)
    pd_height = max(h for h in heights if h >= 100) if any(h >= 100 for h in heights) else heights[0]
    samples.append(("power-density", pd_height))

    # Capacity factor for each turbine class
    for tc in turbine_classes:
        samples.append((f"capacity-factor_{tc}", None))

    return samples

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
DEFAULT_AGGREGATION_FACTOR = 20
AGGREGATION_FACTOR = DEFAULT_AGGREGATION_FACTOR  # backward compat for direct imports
NATIVE_PIXEL_DEG = 0.0025  # GWA native pixel size
