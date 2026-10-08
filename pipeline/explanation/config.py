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
from ..exclusions import config as _exclusions_config
from ..exclusions import rules as _exclusions_rules
from ..integration import config as _integration_config
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

# --- S2-06b input columns on the integrated table (authoritative sources) ---
# The F16 exclusion-reason forms carried onto the integrated table by S1-08
# integration/merge.py. The integrated table does NOT carry the paired
# `exclusion_reasons` JSON column (that lives only on the upstream exclusions
# Eligibility_Table); it carries the two DELIMITED forms below, which F16
# guarantees are the ordered split of one rule evaluation:
#   - triggered_rules   : machine-readable rule-name CODES, ", "-joined
#   - exclusion_reason   : human-readable reason TEXTS, ", "-joined
# The S2-06b loader RECONSTRUCTS the {code, text} pairs from these two,
# positionally, using triggered_rules (codes never contain the delimiter) as
# the authoritative count. Reconstructing rather than materialising the paired
# column on the frozen S2-02 baseline keeps this change inside the explanation
# stage (the ticket's scope) and does not mutate the frozen dataset. The names
# are composed from the exclusions config's OUTPUT_COLUMNS so an upstream rename
# breaks loudly here rather than drifting.
TRIGGERED_RULES_COLUMN = _exclusions_config.OUTPUT_COLUMNS[
    _exclusions_config.OUTPUT_COLUMNS.index("triggered_rules")
]  # "triggered_rules"
EXCLUSION_REASON_COLUMN = _exclusions_config.OUTPUT_COLUMNS[
    _exclusions_config.OUTPUT_COLUMNS.index("exclusion_reason")
]  # "exclusion_reason"

# The delimiter F16 uses to join multiple rule reasons/codes at the top level.
# Composed from the exclusions rules module so a change there propagates here.
REASON_DELIMITER = _exclusions_rules.REASON_DELIMITER  # ", "

# The S1-09 composite confidence columns: level, score and the '; '-joined
# reasons text. Composed from integration/config.py so an upstream rename
# breaks loudly here. CONFIDENCE_COLUMNS = (level, score, notes).
CONFIDENCE_LEVEL_COLUMN = _integration_config.CONFIDENCE_COLUMNS[0]  # "data_confidence"
CONFIDENCE_SCORE_COLUMN = _integration_config.CONFIDENCE_COLUMNS[1]  # "confidence_score"
CONFIDENCE_NOTES_COLUMN = _integration_config.CONFIDENCE_COLUMNS[2]  # "confidence_notes"

# The sentinel S1-09 writes into confidence_notes when a cell has no reason for
# reduced confidence. A note carrying only this sentinel adds nothing, so the
# data-quality caveat surfaces the level alone in that case.
CONFIDENCE_NO_NOTES = _integration_config.CONFIDENCE_NO_NOTES  # "—"
CONFIDENCE_NOTE_DELIMITER = _integration_config.CONFIDENCE_NOTE_DELIMITER  # "; "

# The confidence vocabulary S1-09 emits, carried through verbatim (never
# collapsed). Used by validation to assert every surfaced level is a known one.
CONFIDENCE_LEVELS = _integration_config.DATA_CONFIDENCE_LEVELS  # ("high","medium","low")

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

# --- Explanation_Structure schema (eligible fields OWNED by S2-06a) ---------
# S2-06a owns the eligible-path field names below; S2-06b (this stage now)
# EXTENDS the structure IN PLACE with exclusion_reasons (excluded path) and
# proxy_caveats / data_quality_notes (both paths). No field is renamed or
# removed — the schema is the frozen contract S2-08 get_site_detail returns and
# the S3-05 site-detail view renders.
FIELD_CELL_ID = "cell_id"
FIELD_ELIGIBLE = "eligible"
FIELD_HEADLINE = "headline"
FIELD_POSITIVE_FACTORS = "positive_factors"
FIELD_WEAKNESSES = "weaknesses"

# --- S2-06b additions -------------------------------------------------------
# The excluded-path reason list: a JSON array of {code, text} pairs from the
# integrated table's exclusion_reasons (F16). Present only on excluded records.
FIELD_EXCLUSION_REASONS = "exclusion_reasons"
# Caveats present on BOTH paths (per S2-06b requirement).
FIELD_PROXY_CAVEATS = "proxy_caveats"
FIELD_DATA_QUALITY_NOTES = "data_quality_notes"

# Field order for the eligible JSON record and its CSV columns, kept stable so
# a rerun is byte-identical and downstream consumers can rely on it. The two
# caveat fields are appended after the S2-06a fields.
ELIGIBLE_FIELDS = (
    FIELD_CELL_ID,
    FIELD_ELIGIBLE,
    FIELD_HEADLINE,
    FIELD_POSITIVE_FACTORS,
    FIELD_WEAKNESSES,
    FIELD_PROXY_CAVEATS,
    FIELD_DATA_QUALITY_NOTES,
)

# Field order for the excluded JSON record: identity + eligibility + reasons,
# then the same two caveat fields, so both paths carry the caveats.
EXCLUDED_FIELDS = (
    FIELD_CELL_ID,
    FIELD_ELIGIBLE,
    FIELD_EXCLUSION_REASONS,
    FIELD_PROXY_CAVEATS,
    FIELD_DATA_QUALITY_NOTES,
)

# The union of every field either path can emit, in a stable order, used as the
# flat CSV header. A record carries only its own path's fields in JSON; the CSV
# leaves the other path's columns empty. Order: the eligible order first, then
# the excluded-only field (exclusion_reasons) appended so existing eligible CSV
# columns keep their positions.
ALL_FIELDS = (
    FIELD_CELL_ID,
    FIELD_ELIGIBLE,
    FIELD_HEADLINE,
    FIELD_POSITIVE_FACTORS,
    FIELD_WEAKNESSES,
    FIELD_PROXY_CAVEATS,
    FIELD_DATA_QUALITY_NOTES,
    FIELD_EXCLUSION_REASONS,
)

# Keys within one exclusion-reason pair (F16). Referenced by the writer and
# validator so the pair shape is stated in one place.
REASON_CODE_KEY = "code"
REASON_TEXT_KEY = "text"

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
