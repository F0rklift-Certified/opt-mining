"""
Configuration for the S1-12 validation / sanity-check stage (`sanity`).

This is the pipeline's TERMINAL stage. It consumes the Sprint 1 outputs as
READ-ONLY inputs and produces a human-readable Validation_Report (plus an
optional machine-readable Results_Sidecar) that checks whether the pipeline's
results are *plausible against known reality*.

It is deliberately distinct from the cross-domain STRUCTURAL validation in
`pipeline/validate.py`: that step checks internal data-integrity contracts
(row counts, schema, CRS, key coverage); this stage instead asks whether the
results *make sense*. The stage key/domain is `sanity` (not `validate`) so the
two concerns never clash.

Every INPUT path below is composed from the producing domain's own config
module wherever one exists, never re-typed as a literal, so an upstream rename
propagates here instead of silently drifting. This follows
`pipeline/scoring/config.py` and `pipeline/shortlist/config.py`.

CRS constants are re-exported from grid/config.py (the authoritative source).
"""

from pathlib import Path
from typing import NamedTuple

from .. import config as _shared
from ..grid import config as _grid_config
from ..scoring import config as _scoring_config
from ..shortlist import config as _shortlist_config

PROJECT_ROOT = _shared.PROJECT_ROOT

STAGE_NAME = "sanity"
MODULE_NAME = "sanity.run"

# ---------------------------------------------------------------------------
# CRS (authoritative source: grid/config.py)
# ---------------------------------------------------------------------------

# Storage CRS — every input and every stored coordinate is EPSG:4326.
STORAGE_CRS = _grid_config.STORAGE_CRS  # "EPSG:4326"

# Containment CRS — every spatial-containment operation (locating a wind-farm
# point or a landmark to its cell) is performed in this ONE explicit,
# equal-area CRS, and the EPSG:4326 -> EPSG:3577 transform is logged. No CRS
# conversion is ever performed silently.
CONTAINMENT_CRS = _grid_config.COMPUTATION_CRS  # "EPSG:3577"

# ---------------------------------------------------------------------------
# Inputs (default paths; composed from the producing stages' config where one
# exists, never re-typed). Each is opened READ-ONLY by the loader.
# ---------------------------------------------------------------------------

# S1-10 Scored_Table — per-cell suitability_score / rank (the SOLE score input).
SCORED_PATH = _scoring_config.SCORING_DIR / _scoring_config.OUTPUT_FILENAME
SCORED_LAYER = _scoring_config.OUTPUT_LAYER  # "suitability_score"

# S1-11 Shortlist directory. The Shortlist itself is a timestamped file
# (`sprint1_shortlist_<UTCdate>.{csv,geojson}`); load.resolve_shortlist picks
# the most recent one under this directory by the documented UTC rule.
SHORTLIST_DIR = _shortlist_config.SHORTLIST_DIR  # DATA/shortlist/

# S1-08 Integrated_Feature_Table — source of the per-cell feature values that
# the spot-checks read.
INTEGRATED_PATH = (
    PROJECT_ROOT / "DATA" / "integration"
    / "optmining_integrated-features_2026_nsw.gpkg"
)
INTEGRATED_LAYER = "integrated_features"

# Geoscience Australia Wind_Generators — the known operating wind farms that
# Check 1 locates against the score surface.
WIND_GENERATORS_PATH = (
    PROJECT_ROOT / "DATA" / "infrastructure" / "generators"
    / "ga_wind_generators_2026_nsw.geojson"
)

# S1-02 Analysis_Grid — source of the cell polygons and centroid_lat/lon per
# cell_id. grid/generate.py writes the file inline; reuse the path the
# shortlist stage already keys against rather than adding another copy.
GRID_PATH = _shortlist_config.GRID_PATH  # DATA/grid/nsw_analysis_grid.gpkg
GRID_LAYER = _shortlist_config.GRID_LAYER  # "nsw_grid"

# ---------------------------------------------------------------------------
# Required columns / attributes (halt BEFORE any output if one is absent,
# naming the column and the input it was expected in — Requirement 1.5)
# ---------------------------------------------------------------------------

REQUIRED_SCORE_COLUMNS = ("cell_id", "suitability_score", "rank")
REQUIRED_INTEGRATED_COLUMNS = (
    "cell_id",
    "wind_speed",
    "slope_deg",
    "dist_transmission_km",
    "protected",
    "eligible",
)
REQUIRED_GRID_COLUMNS = ("cell_id", "centroid_lat", "centroid_lon", "geometry")

# The single attribute Check 1 needs from each Wind_Generators feature.
REQUIRED_WIND_GENERATOR_ATTR = "name"

# ---------------------------------------------------------------------------
# Check 2 — Exclusion Validation: documented landmarks (Requirement 3.1, 3.2)
# ---------------------------------------------------------------------------


class Landmark(NamedTuple):
    """A named reality-check location, documented in EPSG:4326.

    ``kind`` records why the landmark is expected to be excluded: an ``urban``
    centre or a ``park`` (protected area). Each is located to its Containing_Cell
    in the CONTAINMENT_CRS (EPSG:3577) and asserted to be an Excluded_Cell
    (ineligible / null suitability_score) or absent from the grid.
    """

    name: str
    lat: float  # EPSG:4326 latitude (degrees)
    lon: float  # EPSG:4326 longitude (degrees)
    kind: str  # "urban" | "park"


# Documented EPSG:4326 coordinates. Urban centres (Sydney CBD, Newcastle,
# Wollongong) are excluded as populated areas; national parks (Blue Mountains,
# Kosciuszko) are protected areas. Located to cells in EPSG:3577.
LANDMARKS = (
    Landmark("Sydney CBD", -33.8688, 151.2093, kind="urban"),
    Landmark("Newcastle", -32.9283, 151.7817, kind="urban"),
    Landmark("Wollongong", -34.4278, 150.8931, kind="urban"),
    Landmark("Blue Mountains NP", -33.7000, 150.3000, kind="park"),
    Landmark("Kosciuszko NP", -36.4560, 148.2630, kind="park"),
)

# Valid landmark kinds.
LANDMARK_KINDS = ("urban", "park")

# ---------------------------------------------------------------------------
# Check 3 — Feature-Value Spot-Checks (Requirement 4)
# ---------------------------------------------------------------------------

# Spot_Check_Cells count is a RUNTIME value (--sanity-spot-cells), validated to
# the inclusive range [SPOT_CHECK_MIN, SPOT_CHECK_MAX]; a value outside the
# range halts the run before any output (Requirement 4.5).
SPOT_CHECK_MIN = 5
SPOT_CHECK_MAX = 10
SPOT_CHECK_DEFAULT = 8

# The independent source a reviewer verifies each spot-checked feature value
# against. Rendered next to the value with an empty discrepancy field for the
# human reviewer to fill in (Requirement 4.3, 4.4).
VERIFY_SOURCES = {
    "wind_speed": "open Global Wind Atlas (GWA) at the cell centroid",
    "slope_deg": "a topographic reference (SRTM-derived slope)",
    "dist_transmission_km": "a GIS distance measurement to the nearest transmission line",
    "protected": "CAPAD protected-area lookup",
}

# ---------------------------------------------------------------------------
# Check 1 / Check 4 — percentile and distribution thresholds (Requirements 2, 5)
# ---------------------------------------------------------------------------

# Upper_Quartile threshold — most operational wind farms are expected to fall
# at or above this percentile of the eligible score population (Requirement 2.5).
UPPER_QUARTILE_PERCENTILE = 75.0

# A farm whose cell scores below this percentile is recorded honestly with an
# investigation note distinguishing a likely data issue from a legitimate model
# result (Requirement 2.6). The model is NEVER adjusted.
POOR_SCORE_PERCENTILE = 25.0

# Degenerate-clustering flag (Requirement 5.2): the score distribution is
# degenerate if the fraction of eligible scores within CLUSTER_EPSILON of 0 or 1
# exceeds CLUSTER_FRACTION_THRESHOLD. Reported as an explicit pass/fail with the
# observed fraction; never used to adjust the model.
CLUSTER_EPSILON = 0.02
CLUSTER_FRACTION_THRESHOLD = 0.5

# ---------------------------------------------------------------------------
# Output locations (Requirement 7, 10)
# ---------------------------------------------------------------------------

# The Validation_Report path is FIXED (not timestamped) so downstream readers
# and the README always know where to find it.
REPORT_PATH = PROJECT_ROOT / "outputs" / "sprint1_validation_report.md"

# Provenance / metadata directory for the derived report + sidecar.
SANITY_DIR = PROJECT_ROOT / "DATA" / "sanity"
SANITY_META_DIR = SANITY_DIR / "metadata"

# The optional machine-readable Results_Sidecar. Its name follows the project
# `{source}_{dataset}_{year/vintage}_{region}.{ext}` convention with region
# slug `nsw` and the 2026 vintage token (matching the Scored_Table it reports
# on). Requirement 10.4.
REGION_SLUG = "nsw"
SIDECAR_VINTAGE = _scoring_config.SCORING_VINTAGE  # "2026"
SIDECAR_FILENAME = f"optmining_validation-results_{SIDECAR_VINTAGE}_{REGION_SLUG}.json"
SIDECAR_PATH = SANITY_DIR / SIDECAR_FILENAME

# Provenance artefact names (mirroring infrastructure/features.py).
MANIFEST_FILENAME = "sanity_manifest.json"
SOURCE_REGISTER_FILENAME = "source_register.csv"
PROVENANCE_FILENAME = "DATA_PROVENANCE.md"

# ---------------------------------------------------------------------------
# Disclaimers and analysis resolution (Requirements 7.5, 7.6)
# ---------------------------------------------------------------------------

# The Preliminary_Disclaimer travels with the report wherever results are
# presented: this is a plausibility sanity check, NOT a formal accuracy
# assessment and NOT a site approval (Requirement 7.5). Wording is consistent
# with the S1-11 shortlist screening disclaimer.
PRELIMINARY_DISCLAIMER = (
    "This report is a preliminary-screening plausibility sanity check. It asks "
    "whether the pipeline's outputs make sense against known reality; it is NOT "
    "a formal accuracy assessment and NOT a site approval. Surprising results "
    "are documented honestly for investigation, and the model is never adjusted "
    "to make a check pass."
)

# The Analysis_Resolution statement, stated wherever results are presented
# (Requirement 7.6). The ~5 km cell is the 0.05 degree grid cell
# (grid CELL_DEG = 0.05).
ANALYSIS_RESOLUTION = "~5 km (0.05 degree) analysis grid cell"
