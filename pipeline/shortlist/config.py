"""
Configuration for the S1-11 preliminary ranked-shortlist stage (`shortlist`).

Every INPUT path and vocabulary below is composed from the producing
domain's own config module, never re-typed as a literal, so an upstream
rename propagates here instead of silently drifting. This follows
`pipeline/scoring/config.py` and `pipeline/integration/config.py`.

The default score input is the S1-10 Scored_Table
(`DATA/scoring/optmining_suitability-score_2026_nsw.gpkg`); the default
grid is the S1-02 Analysis_Grid (`DATA/grid/nsw_analysis_grid.gpkg`). Both
paths are reused from the producing stage's config rather than re-typed.

Top_N is a RUNTIME value (a `--shortlist-top-n` CLI flag / config value),
NOT a frozen decision (Q1–Q7): it widens or narrows the screening output
and never changes the analysis. `DEFAULT_TOP_N` is the fallback when
nothing is supplied.
"""

from pathlib import Path

from .. import config as _shared
from ..grid import config as _grid_config
from ..scoring import config as _scoring_config

PROJECT_ROOT = _shared.PROJECT_ROOT

# --- CRS (authoritative source: grid/config.py) ---
# Storage and GeoJSON output CRS. This stage performs NO reprojection — there
# is no distance or area computation here — so no EPSG:3577 boundary arises.
STORAGE_CRS = _grid_config.STORAGE_CRS  # "EPSG:4326"

# ---------------------------------------------------------------------------
# Inputs (composed from the producing stages' config, never re-typed)
# ---------------------------------------------------------------------------

# The S1-10 Scored_Table — the SOLE per-cell score input. Composed from
# scoring/config.py so a rename of the scoring output propagates here.
SCORED_PATH = _scoring_config.SCORING_DIR / _scoring_config.OUTPUT_FILENAME
SCORED_LAYER = _scoring_config.OUTPUT_LAYER  # "suitability_score"

# The S1-02 Analysis_Grid — source of centroid_lat / centroid_lon per cell.
# grid/generate.py writes the file inline; reuse the path the scoring stage
# already keys against (via integration → exclusions) rather than a 4th copy.
GRID_PATH = PROJECT_ROOT / "DATA" / "grid" / "nsw_analysis_grid.gpkg"
GRID_LAYER = "nsw_grid"  # grid/generate.py to_file(layer=...)

# ---------------------------------------------------------------------------
# Output locations
# ---------------------------------------------------------------------------

SHORTLIST_DIR = PROJECT_ROOT / "DATA" / "shortlist"
SHORTLIST_META_DIR = SHORTLIST_DIR / "metadata"

# Output filenames are timestamped/versioned by naming.py (task 8.1) as
# `sprint1_shortlist_<UTCdate>.{csv,geojson}`. Where the project
# `{source}_{dataset}_{year/vintage}_{region}.{ext}` convention applies, the
# region slug is `nsw` (consistent with the scoring output slug, 7.3).
REGION_SLUG = "nsw"
OUTPUT_PREFIX = "sprint1_shortlist"

SUMMARY_REPORT_FILENAME = "shortlist_summary.md"
METADATA_SIDECAR_FILENAME = "shortlist_metadata.json"
VALIDATION_REPORT_FILENAME = "shortlist_validation.md"
MANIFEST_FILENAME = "shortlist_manifest.json"
SOURCE_REGISTER_FILENAME = "source_register.csv"
PROVENANCE_FILENAME = "DATA_PROVENANCE.md"

STAGE_NAME = "shortlist"
MODULE_NAME = "shortlist.run"

# ---------------------------------------------------------------------------
# Top_N (Requirement 3)
# ---------------------------------------------------------------------------

# Default number of highest-ranked Eligible_Cells to shortlist when no CLI
# value and no pipeline-config value is supplied (Requirement 3.1).
DEFAULT_TOP_N = 20

# ---------------------------------------------------------------------------
# Confidence vocabulary
# ---------------------------------------------------------------------------

# The confidence values the shortlist distribution counts. The S1-10 ticket
# defined a two-value high/low flag; the shortlist reports counts at these
# levels (Requirement 6.4). Values outside this vocabulary are surfaced by
# validation rather than silently dropped.
CONFIDENCE_LEVELS = ("high", "low")

# ---------------------------------------------------------------------------
# Output schema (Requirement 4)
# ---------------------------------------------------------------------------

# The documented column order carried in the Shortlist_CSV and as
# Shortlist_GeoJSON feature properties (Requirement 4.1).
SHORTLIST_COLUMNS = (
    "rank",
    "cell_id",
    "suitability_score",
    "confidence",
    "centroid_lat",
    "centroid_lon",
)

# Optional context columns appended WHERE available from an upstream layer;
# each carries a definition and source recorded in the Summary_Report
# (Requirement 4.3).
OPTIONAL_CONTEXT_COLUMNS = ("rez", "nearby_wind_farm")

# ---------------------------------------------------------------------------
# GeoJSON geometry choice (Requirement 5.4)
# ---------------------------------------------------------------------------

# The shortlist is a point-of-interest layer keyed to centroid_lat/lon, and a
# point is unambiguous at the ~5 km analysis resolution, so the centroid
# Point is the default; the cell polygon is the documented alternative.
DEFAULT_GEOMETRY = "centroid"
GEOMETRY_CHOICES = ("centroid", "polygon")

# ---------------------------------------------------------------------------
# Disclaimer and analysis-resolution statement (Requirement 8)
# ---------------------------------------------------------------------------

# The Preliminary_Disclaimer travels with EVERY output and its metadata: the
# shortlist is a preliminary screening starting point, not a site approval
# (Requirement 8.1, 8.5). Wording is consistent with the S1-10 scoring
# report's screening disclaimer.
PRELIMINARY_DISCLAIMER = (
    "This shortlist is a preliminary screening output. It indicates where to "
    "look next; it is not a site approval, an engineering assessment, or a "
    "final recommendation."
)

# The Analysis_Resolution statement, stated wherever results are presented
# (Requirement 8.2). The ~5 km cell is the 0.05 degree grid cell (grid
# CELL_DEG = 0.05).
ANALYSIS_RESOLUTION = "~5 km (0.05 degree) analysis grid cell"


# ---------------------------------------------------------------------------
# Top_N resolver (Requirement 3.1, 3.3, 3.5)
# ---------------------------------------------------------------------------


def resolve_top_n(cli_value: int | None, config_value: int | None) -> int:
    """
    Resolve the effective Top_N for a run.

    Precedence (Requirement 3.1, 3.3):
        explicit CLI value  >  pipeline-config value  >  DEFAULT_TOP_N (20)

    The first non-None of ``cli_value`` then ``config_value`` wins; when both
    are None the default is used.

    Halts (raises ``ValueError``) BEFORE any output if the resolved value is
    not a positive integer — zero, negative, or non-integer (including a
    ``bool``, which is a Python ``int`` subclass but is not a valid count) —
    identifying the invalid value so the caller can surface it (Requirement
    3.5). The check runs at the top of ``run()`` so no partial output is
    written for an invalid Top_N.
    """
    if cli_value is not None:
        resolved = cli_value
    elif config_value is not None:
        resolved = config_value
    else:
        resolved = DEFAULT_TOP_N

    # bool is a subclass of int; reject it explicitly so True/False can never
    # masquerade as a count of 1/0.
    if isinstance(resolved, bool) or not isinstance(resolved, int) or resolved <= 0:
        raise ValueError(
            f"Top_N must be a positive integer; got {resolved!r}. "
            "Supply a positive integer via --shortlist-top-n or the pipeline "
            "configuration."
        )

    return resolved
