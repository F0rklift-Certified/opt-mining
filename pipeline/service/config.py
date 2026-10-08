"""
Structural configuration for the Decision_Service (S2-08).

Paths and filenames only — NO decision parameters. Every input location is
composed from the producing stage's own config module (never re-typed as a
literal), so an upstream rename propagates here instead of silently drifting;
this follows the same discipline as `pipeline/scoring/config.py`.

The service materialises each Run under a per-run directory below
`DATA/service/runs/{run_id}/`, so a Run launched from explicit weights or a
scenario never clobbers the default `DATA/scoring/` Scored_Table that the
`scoring` stage owns.
"""

from pathlib import Path

from .. import config as _shared
from ..exclusions import config as _exclusions_config
from ..exclusions import rules as _exclusions_rules
from ..explanation import config as _explanation_config
from ..scoring import config as _scoring_config

PROJECT_ROOT = _shared.PROJECT_ROOT

# --- Input: the engine's sole feature table (authoritative: scoring/config.py) ---
INTEGRATED_PATH = _scoring_config.INTEGRATED_PATH
INTEGRATED_LAYER = _scoring_config.INTEGRATED_LAYER

# The integrated table's S2-03 eligibility flag, read by get_site_detail so the
# served `eligible` traces to the engine's own exclusions output (never
# recomputed). Authoritative source: scoring/config.py.
ELIGIBLE_COLUMN = _scoring_config.ELIGIBLE_COLUMN  # "eligible"

# --- Input: the S2-06 Explanation_Structure output (authoritative upstream) ---
# get_site_detail resolves a cell's explanation from this materialised JSON,
# keyed by `cell_id`, and carries the record through VERBATIM. Composed from
# explanation/config.py so an upstream rename of the artefact or its directory
# breaks loudly here rather than silently drifting; the service never recomputes
# an explanation (CONTRACT.md §1, §5).
EXPLANATION_PATH = _explanation_config.EXPLANATION_DIR / _explanation_config.OUTPUT_FILENAME
EXPLANATION_CELL_ID_FIELD = _explanation_config.FIELD_CELL_ID  # "cell_id"

# --- Input: the S2-03 Eligibility_Table (authoritative upstream: exclusions/) ---
# get_exclusions reads the materialised Eligibility_Table the exclusions stage
# wrote and serves its excluded cells verbatim as ExcludedRows. The path, layer
# and reason column names are all composed from exclusions/config.py and
# exclusions/rules.py (never re-typed as literals here) so an upstream rename of
# the artefact or a reason column breaks loudly at import rather than silently
# drifting; the service never recomputes an exclusion (CONTRACT.md §1, §5).
ELIGIBILITY_TABLE_PATH = (
    _exclusions_config.EXCLUSIONS_DIR / _exclusions_config.OUTPUT_FILENAME
)
# The exclusions stage writes the Eligibility_Table to the GeoPackage's default
# (single) layer, so it is read back by path with no explicit layer name.
ELIGIBILITY_TABLE_LAYER = None

# The Eligibility_Table's cell-id column (authoritative: scoring/config.py, the
# shared cell_id convention every layer joins on).
ELIGIBILITY_CELL_ID_COLUMN = _scoring_config.CELL_ID_COLUMN  # "cell_id"

# The S2-03 per-cell eligibility flag column (authoritative: scoring/config.py,
# where the same "eligible" flag is read by the scoring engine).
ELIGIBILITY_ELIGIBLE_COLUMN = _scoring_config.ELIGIBLE_COLUMN  # "eligible"

# The reason columns the exclusions stage writes (authoritative:
# exclusions/config.py OUTPUT_COLUMNS). `EXCLUSION_REASONS_COLUMN` is the
# machine+human paired JSON form (a list of {"code", "text"} pairs) the S2-06
# explanation engine also consumes; `TRIGGERED_RULES_COLUMN` and
# `EXCLUSION_REASON_COLUMN` are the code-list and human-text forms, all derived
# from ONE rule evaluation so they can never drift (see exclusions/apply.py).
EXCLUSION_REASONS_COLUMN = "exclusion_reasons"
TRIGGERED_RULES_COLUMN = "triggered_rules"
EXCLUSION_REASON_COLUMN = "exclusion_reason"

# The delimiter the exclusions stage uses to join multiple reason codes / texts,
# in rule-config order (authoritative: exclusions/rules.REASON_DELIMITER). Reused
# here so a served ExcludedRow's reason_text/reason_codes split and join exactly
# as the engine wrote them.
REASON_DELIMITER = _exclusions_rules.REASON_DELIMITER  # ", "

# --- Input: the packaged weight sources (user inputs; authoritative upstream) ---
DEFAULT_WEIGHTS_PATH = _scoring_config.DEFAULT_WEIGHTS_PATH
DEFAULT_SCENARIOS_PATH = _scoring_config.DEFAULT_SCENARIOS_PATH

# --- Input: the S2-02 Data_Quality_Status (authoritative upstream: validate.py) ---
# get_data_quality reads the Validation_Result JSON sidecar the S2-02 validator
# materialised (`integrated_input_validation.json` under INTEGRATION_META_DIR)
# and surfaces its `all_passed` verdict + per-check records VERBATIM. The path is
# composed from `pipeline.validate`'s OWN constants (the module that produces the
# sidecar) — never re-typed as a literal here — so an upstream rename of the
# artefact or its directory breaks loudly at import rather than silently drifting.
# The service never re-runs validation (CONTRACT.md §1, §4.6, §5). Imported lazily
# inside the resolver so the thin service layer does not pull the validator's
# heavy geospatial dependencies at import time.
def data_quality_result_path() -> Path:
    """
    Absolute path to the S2-02 Validation_Result JSON sidecar.

    Composed from `pipeline.validate.DEFAULT_VALIDATION_RESULT_PATH` (the
    producing module's authoritative constant), so this path can never drift
    from where the S2-02 validator writes it.
    """
    from .. import validate as _validate

    return _validate.DEFAULT_VALIDATION_RESULT_PATH

# --- Output: the per-Run materialisation store ---
SERVICE_DIR = PROJECT_ROOT / "DATA" / "service"
RUNS_DIR = SERVICE_DIR / "runs"

# Per-run artefact filenames. The Scored_Table filenames mirror the `scoring`
# stage's own (`optmining_suitability-score_{vintage}_nsw`) so a Run's output is
# recognisably the same product, differing only by the enclosing run directory.
SCORED_GPKG_FILENAME = _scoring_config.OUTPUT_FILENAME
SCORED_CSV_FILENAME = _scoring_config.CSV_FILENAME
SCORED_LAYER = _scoring_config.OUTPUT_LAYER
RUN_MANIFEST_FILENAME = "run.json"

# Length of the hex run id derived from the resolved weights identity. 16 hex
# chars (64 bits) is collision-safe for the handful of runs a session creates
# while staying short enough to sit in a URL path segment.
RUN_ID_LENGTH = 16

STAGE_NAME = "service"
MODULE_NAME = "service.runs"
