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

# --- Input: the packaged weight sources (user inputs; authoritative upstream) ---
DEFAULT_WEIGHTS_PATH = _scoring_config.DEFAULT_WEIGHTS_PATH
DEFAULT_SCENARIOS_PATH = _scoring_config.DEFAULT_SCENARIOS_PATH

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
