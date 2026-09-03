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

However, `apply.py` has NOT yet been migrated to consume them: it still reads
the raw Sprint-0 sources directly (CAPAD protected areas, the derived slope
raster, ABS urban centres, the GWA wind-speed raster) and recomputes only the
specific per-cell values the default exclusion rules need: protected-area
overlap, mean slope, urban overlap, and wind-data availability. This
duplicates logic that S1-06/S1-03 now own as their per-cell feature tables.

OUTSTANDING FOLLOW-UP: `apply.py`'s field-computing functions
(`_protected_overlap`, `_urban_overlap`, the raster sampling calls) should be
deleted and replaced with a read of the `geographic.features` /
`wind.features` outputs, joined on `cell_id`. The rule engine (`rules.py`) and
the output / validation / report code do not need to change — they operate on
a generic per-cell field dict, not on how those fields were computed.

Also note the coverage of the RAW sources this stage currently reads: the
slope raster, the GWA wind-speed raster and the ABS urban-centre extract only
cover the New England REZ study window, not the full NSW grid (see
`DATA/geographic/DATA_PROVENANCE.md` / `DATA/wind-resource/DATA_PROVENANCE.md`).
CAPAD (protected areas) is the one source with full-NSW coverage. This means
the vast majority of the 47,311-cell NSW grid is excluded today with reason
"Missing wind data" — because this stage reads the REZ-clipped raster, NOT
because wind data is unavailable. The NSW-wide `wind.features` table produced
by S1-03 has a wind-speed value for every cell; once the migration above lands
(joining that table on `cell_id` instead of sampling the raw raster), this
exclusion count will drop accordingly. See the generated method report's
Coverage section.
"""
