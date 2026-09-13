"""
Configuration for the S2-06a explanation stage (`explanation`).

Every INPUT path, column name and vocabulary below is composed from the
producing domain's own config module, never re-typed as a literal, so an
upstream rename (a Scored_Table column, the contribution prefix, the vintage)
propagates here and breaks loudly rather than silently drifting. This follows
`pipeline/scoring/config.py` and `pipeline/integration/config.py`.

NOTE ON PHRASING: no explanation phrase or band label appears in this file or
anywhere else in `pipeline/explanation/` source. Phrases, band labels and band
thresholds are USER INPUTS loaded at runtime from `explanation_templates.yaml`
(mirroring the weights-as-data principle of `scoring/scoring_weights.yaml`).
The constants here are structural — paths, filenames, schema field names and
tolerances — not narrative content.
"""

from pathlib import Path

from .. import config as _shared
from ..scoring import config as _scoring_config

PROJECT_ROOT = _shared.PROJECT_ROOT

# --- CRS (authoritative source: grid/config.py, via scoring/config.py) ---
STORAGE_CRS = _scoring_config.STORAGE_CRS  # "EPSG:4326"
COMPUTATION_CRS = _scoring_config.COMPUTATION_CRS  # "EPSG:3577" — recorded only

# --- Inputs -----------------------------------------------------------------
# The S2-05 Scored_Table (GeoPackage) — the SOLE score/contribution input.
SCORED_TABLE_PATH = _scoring_config.SCORING_DIR / _scoring_config.OUTPUT_FILENAME
SCORED_TABLE_LAYER = _scoring_config.OUTPUT_LAYER  # "suitability_score"

# The S1-08 integrated feature table — read ONLY to recompute the eligible
# population normalisation bounds/values that the qualitative bands need. The
# scoring stage's own loader/config own this path; we reuse it, never re-type.
INTEGRATED_PATH = _scoring_config.INTEGRATED_PATH
INTEGRATED_LAYER = _scoring_config.INTEGRATED_LAYER  # "integrated_features"

# The criteria weights (user input, overridable with --scoring-weights). The
# SAME file the scoring stage used, so the recomputed norms match the persisted
# contributions. Defaulting here to the packaged scoring weights keeps the two
# stages in lockstep unless the caller overrides both identically.
DEFAULT_WEIGHTS_PATH = _scoring_config.DEFAULT_WEIGHTS_PATH

# The explanation template/rule set (user input, overridable with
# --explanation-templates). Packaged alongside this module.
DEFAULT_TEMPLATES_PATH = Path(__file__).resolve().parent / "explanation_templates.yaml"

# --- Scored_Table columns (authoritative source: scoring/config.py) ---
CELL_ID_COLUMN = _scoring_config.CELL_ID_COLUMN  # "cell_id"
SCORE_COLUMN = _scoring_config.SCORE_COLUMN  # "suitability_score"
RANK_COLUMN = _scoring_config.RANK_COLUMN  # "rank"
OUTPUT_CONFIDENCE_COLUMN = _scoring_config.OUTPUT_CONFIDENCE_COLUMN  # "confidence"
CONTRIBUTION_PREFIX = _scoring_config.CONTRIBUTION_PREFIX  # "contrib_"

# The integrated table's eligibility flag (used to recompute bounds from the
# eligible population, exactly as the scoring stage does).
ELIGIBLE_COLUMN = _scoring_config.ELIGIBLE_COLUMN  # "eligible"

# Reconciliation tolerance shared with scoring: the recomputed norms must
# reproduce the persisted contributions to within this, or the run halts.
RECONCILE_TOLERANCE = _scoring_config.RECONCILE_TOLERANCE  # 1e-9

# --- Output locations -------------------------------------------------------
EXPLANATION_DIR = PROJECT_ROOT / "DATA" / "explanation"
EXPLANATION_META_DIR = EXPLANATION_DIR / "metadata"

# Vintage tracks the Scored_Table it explains, so the products are visibly the
# same generation of the data.
EXPLANATION_VINTAGE = _scoring_config.SCORING_VINTAGE  # "2026"

# {source}_{dataset}_{year/vintage}_{region}.{ext}, region slug "nsw".
OUTPUT_FILENAME = f"optmining_site-explanations_{EXPLANATION_VINTAGE}_nsw.json"
CSV_FILENAME = f"optmining_site-explanations_{EXPLANATION_VINTAGE}_nsw.csv"

METHOD_REPORT_FILENAME = "explanation_method.md"
VALIDATION_REPORT_FILENAME = "explanation_validation.md"
SCHEMA_FILENAME = "explanation_schema.md"
MANIFEST_FILENAME = "explanation_manifest.json"
SOURCE_REGISTER_FILENAME = "source_register.csv"
PROVENANCE_FILENAME = "DATA_PROVENANCE.md"

# --- Explanation_Structure schema (OWNED HERE; extended by S2-06b) ----------
# These are the eligible-path field names. S2-06b ADDS exclusion_reasons,
# proxy_caveats and data_quality_notes — it must not rename or remove these.
FIELD_CELL_ID = "cell_id"
FIELD_ELIGIBLE = "eligible"
FIELD_HEADLINE = "headline"
FIELD_POSITIVE_FACTORS = "positive_factors"
FIELD_WEAKNESSES = "weaknesses"

# Field order for the JSON records and the flat CSV, kept stable so a rerun is
# byte-identical and downstream consumers can rely on it.
ELIGIBLE_FIELDS = (
    FIELD_CELL_ID,
    FIELD_ELIGIBLE,
    FIELD_HEADLINE,
    FIELD_POSITIVE_FACTORS,
    FIELD_WEAKNESSES,
)

# --- Factor-selection rule parameters (structural; phrasing is in the YAML) --
# How many positive factors / weaknesses to surface per cell at most. Kept
# small so the narrative is a screening summary, not an exhaustive dump. These
# are ceilings: a cell with fewer discriminating criteria surfaces fewer.
MAX_POSITIVE_FACTORS = 3
MAX_WEAKNESSES = 2

# A criterion is only reported as a WEAKNESS when the cell's normalised value
# for it is at or below this threshold (i.e. the cell genuinely scores poorly
# on it, not merely "not top"). Structural default; the band LABELS and their
# own thresholds are data in the YAML.
WEAKNESS_NORM_CEILING = 0.5

STAGE_NAME = "explanation"
MODULE_NAME = "explanation.run"
