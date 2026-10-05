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
    raster_stats.py  — reusable cell-centre-mask zonal-mean helper (retained
                        for other callers / tests; no longer used by apply.py)
    apply.py          — the stage: joins the feature tables, applies rules,
                        writes the Eligibility_Table + method report.
                        Public entry point: apply.run(verbose=False) -> dict

Scope note — the feature-table migration has landed
----------------------------------------------------
S1-07 depends on S1-06 ("Build Geographic & Environmental Features") and S1-03
("Build the Wind Feature Layer"). Both are implemented and registered in
`pipeline/config.py` STAGES as `geographic.features`
(`pipeline/geographic/features.py`) and `wind.features`
(`pipeline/wind/features.py`), each producing a per-cell Feature_Table on the
common analysis grid.

`apply.py` consumes those tables directly: `read_feature_tables()` opens the
geographic and wind feature GeoPackages (each with its explicit `layer=`) and
`build_cell_table()` inner-joins them on `cell_id` to assemble the per-cell
field dict — `protected_area` / `protected_area_name` / `slope_deg` /
`urban_area` / `on_land` from `geographic.features`, and `wind_speed_100m_ms`
(the wind column `wind_speed_100m`) from `wind.features`. The stage no longer
re-samples raw rasters or vectors; the duplicated sampling logic the earlier
scope note flagged has been deleted. The join is asserted 1:1 and must cover
every grid cell — a missing table, a missing `cell_id`, or a row-count
mismatch halts the run rather than silently mass-excluding cells.

Both feature tables are statewide-NSW: they carry a value for every one of the
47,311 grid cells, so the exclusion layer now covers the full NSW grid. A cell
is excluded only where a rule genuinely fires — a null critical field
(`missing_wind_data`, `missing_slope_data`), an offshore/marine centre
(`offshore_or_marine`), a CAPAD protected-area overlap, an urban-centre
overlap, or excessive slope. The rule engine (`rules.py`) and the output /
validation / report code are unchanged by the migration: they operate on a
generic per-cell field dict, independent of how those fields were computed.
"""
