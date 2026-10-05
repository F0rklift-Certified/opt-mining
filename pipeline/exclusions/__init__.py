"""
Exclusion Layer — Sprint 1, S1-07.

Determines which analysis-grid cells are ELIGIBLE for suitability scoring.
Exclusions are an explicit, separate pipeline stage — never hidden inside
scoring code. Every cell in the common analysis grid gets an `eligible`
boolean plus a transparent, auditable `exclusion_reason` (one or more,
"; "-joined) when it fails one or more configured rules.

Per the Constitution: "Where critical data is missing, exclude the cell.
Where non-critical data is missing or low confidence, retain and flag it."
This stage implements the hard-exclusion half of that rule; the softer
"retain and flag" half surfaces as the `data_flags` column rather than an
exclusion.

Rules are DATA, not code: they live in `exclusion_rules.yaml` (default:
this package's own copy) and are evaluated generically by `rules.py`.
Adding, removing, reordering or retuning a rule (e.g. changing the slope
threshold) is a YAML edit — `rules.py` never changes for that.

Exclusion reason schema (machine + human readable)
--------------------------------------------------
Every excluded cell retains its reason(s) in three consistent forms, all
derived from a single rule evaluation (`rules.evaluate_cell_detailed`) so
they can never drift:

    exclusion_reason   human-readable text, reasons joined with ", "
    triggered_rules    machine-readable rule-name codes, same delimiter
    exclusion_reasons  JSON list of {"code": rule_name, "text": reason}
                       pairs (null when eligible) — the paired form the
                       S2-06b explanation engine and S3-05 site-detail view
                       consume directly.

The `code` values are the FROZEN exclusion reason-code vocabulary: the rule
`name` values in `exclusion_rules.yaml`. That vocabulary is the authoritative
machine-readable contract, governed as frozen decision F16 in the
Decision-Engine Specification (`Sprint-2-Tasks/decision_engine_specification.md`
§6.5); adding or renaming a code follows that document's §6.2 change-control
process and must be applied in every recording location it lists. S2-06b's
`exclusion_reasons` explanation schema consumes this vocabulary unchanged —
coordinate any code change with that task (and S3-05).

Modules:
    rules.py         — pure rule-engine: load_rules(), evaluate_cell()
    raster_stats.py  — reusable cell-centre-mask zonal-mean helper
    apply.py          — the stage: reads sources, computes fields, applies
                        rules, writes the Eligibility_Table + method report.
                        Public entry point: apply.run(verbose=False) -> dict

IMPORTANT — scope note, read before extending this module
-----------------------------------------------------------
S1-07 is blocked by S1-06 ("Build Geographic & Environmental Features") and
depends on S1-03 ("Build the Wind Feature Layer"). Both are now implemented
and registered in `pipeline/config.py` STAGES as `geographic.features`
(`pipeline/geographic/features.py`) and `wind.features`
(`pipeline/wind/features.py`), each producing a per-cell Feature_Table on the
common analysis grid.

S3-10 migrates slope and wind to those authoritative per-cell tables, using
exact cell_id joins with coverage/uniqueness checks. Demand comes from the
same NSW demand-proxy table as integration. Missing demand is excluded by the
explicitly approved F16 code addition `missing_demand_data`; no imputation or
scoring-weight change is made.

The separately approved `outside_nsw_land` rule checks the stored centroid
against the committed ABS NSW boundary in EPSG:3577 (boundary included).
It retains every rectangular-grid cell and its exclusion reason. Coarse
border cells can straddle NSW; this is not a parcel-level land mask.

Protected-area and urban rules still compute their specific overlap definitions
from full-NSW CAPAD and ABS UCL vectors. The geographic stage's urban-distance
feature is not an urban-overlap substitute. The ABS UCL source is registered in
DATA/geographic/metadata/abs_ucl_2021_nsw_source.json. Legacy REZ-window rasters
are no longer production exclusion inputs. See docs/release/baseline-change.json
for the authorised before/after audit and the frozen specification §6.5 for
the reason-code vocabulary.
"""
