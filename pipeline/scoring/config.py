"""
Configuration for the S1-10 baseline suitability model (stage `scoring`).

Every INPUT path and vocabulary below is composed from the producing
domain's own config module, never re-typed as a literal, so an upstream
rename or a change to the confidence vocabulary propagates here instead of
silently drifting. This follows `pipeline/integration/config.py`.

NOTE ON WEIGHTS: no criterion weight appears in this file or anywhere else
in `pipeline/scoring/`. Weights, directions and rationales are USER INPUTS
loaded at runtime from `scoring_weights.yaml` (Constitution: "Criteria
weights are user inputs, never hard-coded constants"). The constants here
are structural — paths, filenames, tolerances and vocabularies — not model
parameters.
"""

from pathlib import Path

from .. import config as _shared
from ..grid import config as _grid_config
from ..integration import config as _integration_config

PROJECT_ROOT = _shared.PROJECT_ROOT

# --- CRS (authoritative source: grid/config.py) ---
STORAGE_CRS = _grid_config.STORAGE_CRS  # "EPSG:4326" — input and output
COMPUTATION_CRS = _grid_config.COMPUTATION_CRS  # "EPSG:3577" — recorded only

# --- Input: the S1-08 integrated feature table (the SOLE feature input) ---
INTEGRATED_PATH = _integration_config.INTEGRATION_DIR / _integration_config.OUTPUT_FILENAME
INTEGRATED_LAYER = _integration_config.OUTPUT_LAYER  # "integrated_features"

# --- Input: the criteria weights (user input, overridable with --scoring-weights) ---
DEFAULT_WEIGHTS_PATH = Path(__file__).resolve().parent / "scoring_weights.yaml"

# --- Input: the named weighting scenarios (S2-07 presets; user input) ---
# A scenario is a named weight set, validated by the same parser as the
# default weights. Presets are data, not code — see scenarios.py.
DEFAULT_SCENARIOS_PATH = Path(__file__).resolve().parent / "scenarios.yaml"

# --- Output locations ---
SCORING_DIR = PROJECT_ROOT / "DATA" / "scoring"
SCORING_META_DIR = SCORING_DIR / "metadata"

# Vintage token tracks the integrated table it scores (2026), so the two
# products are visibly the same generation of the data.
SCORING_VINTAGE = _integration_config.INTEGRATION_VINTAGE  # "2026"

# {source}_{dataset}_{year/vintage}_{region}.{ext}, region slug "nsw".
OUTPUT_FILENAME = f"optmining_suitability-score_{SCORING_VINTAGE}_nsw.gpkg"
CSV_FILENAME = f"optmining_suitability-score_{SCORING_VINTAGE}_nsw.csv"
OUTPUT_LAYER = "suitability_score"

METHOD_REPORT_FILENAME = "scoring_method.md"
VALIDATION_REPORT_FILENAME = "scoring_validation.md"
MANIFEST_FILENAME = "scoring_manifest.json"
SOURCE_REGISTER_FILENAME = "source_register.csv"
PROVENANCE_FILENAME = "DATA_PROVENANCE.md"

# --- Required columns on the integrated table ---
CELL_ID_COLUMN = "cell_id"

# Upper bound on any single criterion weight. Weights are relative (they are
# normalised by their sum), so a cap loses no expressiveness; it exists so a
# huge value such as 1e308 cannot overflow the sum to inf and silently score
# every cell 0 while ranks are still shown (QA F-07). Structural guard, not a
# model parameter.
MAX_CRITERION_WEIGHT = 100.0
ELIGIBLE_COLUMN = "eligible"

# The S1-09 composite confidence flag. Composed from integration/config.py so
# that renaming it upstream breaks loudly here rather than silently producing
# a fabricated confidence column.
CONFIDENCE_COLUMN = _integration_config.CONFIDENCE_COLUMNS[0]  # "data_confidence"

# The confidence vocabulary is WHATEVER S1-09 EMITS — currently
# ("high", "medium", "low"). The S1-10 ticket assumed a two-value
# high/low flag; S1-09 shipped three levels. We carry the upstream value
# through verbatim rather than collapsing `medium` into `low` or `high`,
# because either collapse would fabricate a confidence the data does not
# support (Constitution: "Never let poor data pass as good", "Report
# confidence alongside every score"; Requirement 10.1/10.4 — carry through,
# never fabricate). Validation asserts membership in THIS vocabulary, so a
# value outside it is still an explicit failure. See the method report's
# "Deviations from the S1-10 ticket" section.
CONFIDENCE_LEVELS = _integration_config.DATA_CONFIDENCE_LEVELS  # ("high","medium","low")

# --- Output schema ---
SCORE_COLUMN = "suitability_score"
RANK_COLUMN = "rank"
CONTRIBUTION_PREFIX = "contrib_"  # contribution column = contrib_{criterion feature}

# The scored table names the carried-through flag `confidence` (the S1-10
# ticket's output schema); its VALUES are S1-09's `data_confidence`, copied
# verbatim. The rename is presentational only — no value is altered.
OUTPUT_CONFIDENCE_COLUMN = "confidence"

# Grid columns carried through so the shortlist stage (S1-11) can locate a
# cell without re-joining the grid. This stays EXACTLY the two coordinate
# columns: the decision service (pipeline/service/results.py) and the S2-08
# get_run_cells endpoint unpack it as (lat_col, lon_col), so it must not grow.
CARRIED_COLUMNS = ("centroid_lat", "centroid_lon")

# INFORMATIONAL columns carried through from the integrated table onto the
# Scored_Table verbatim — NOT criteria, not read by the scoring core, and never
# affecting the score, the contributions or the rank. `demand_coord_confidence`
# is the integrated table's surface-only demand coordinate-confidence tier,
# passed through so an analyst can audit it in the Scored_Table and shortlist.
# Carried only WHERE present on the integrated table (back-compatible with an
# older integrated table that lacks it).
DEMAND_COORD_CONFIDENCE_COLUMN = _integration_config.DEMAND_COORD_CONFIDENCE_COLUMN
# `load_within_radius_mva` is the integrated table's DISPLAY-ONLY per-cell
# network-load read-out (raw sum of nearby zone-substation max demand, MVA). It
# is carried through verbatim as context — never a criterion, never read by the
# scoring core, and never affecting the score, the contributions or the rank —
# so the Site Detail panel can surface a tangible MVA figure alongside the
# dimensionless demand_proxy. Carried only WHERE present (back-compatible).
DEMAND_LOAD_MVA_COLUMN = _integration_config.DEMAND_LOAD_MVA_COLUMN
CARRIED_CONTEXT_COLUMNS = (DEMAND_COORD_CONFIDENCE_COLUMN, DEMAND_LOAD_MVA_COLUMN)

# --- Numerics ---
# Tolerance for "the per-criterion contributions reconstruct the score".
# The contributions are summed in the same order they are computed, so the
# residual is pure float round-off over ~6 terms; 1e-9 is several orders of
# magnitude above that and well below any decision-relevant difference.
RECONCILE_TOLERANCE = 1e-9

# Documented fill for a criterion that is CONSTANT over the eligible
# population (min == max), where (v - min) / (max - min) is 0/0. Every cell
# scores identically on such a criterion, so it adds a constant offset to
# every score and cannot change the ranking; 1.0 is used (rather than 0.0)
# so that a criterion which is uniformly at its only observed value is not
# penalised for lack of variation. Criteria in this state are flagged as
# constant in the method report so the reader can see the criterion carried
# no discriminating information on that run.
CONSTANT_CRITERION_VALUE = 1.0

# Definitional domain for a boolean criterion (Requirement 4.7). Booleans
# use their fixed {False -> 0.0, True -> 1.0} domain rather than the
# population min/max, so an all-False boolean criterion scores 0 for every
# cell (honest) instead of triggering the constant fill and scoring 1.0.
BOOLEAN_BOUNDS = (0.0, 1.0)

# Valid criterion directions.
HIGHER_IS_BETTER = "higher_is_better"
LOWER_IS_BETTER = "lower_is_better"
DIRECTIONS = (HIGHER_IS_BETTER, LOWER_IS_BETTER)

STAGE_NAME = "scoring"
MODULE_NAME = "scoring.run"
