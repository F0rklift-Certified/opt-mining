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
depends on S1-03 ("Build the Wind Feature Layer"). Both currently exist only
as ticket + design documentation under `Sprint-1-Tasks/S1-0{3,6}-.../` —
`pipeline/geographic/features.py` and an equivalent wind per-cell feature
module do not exist in this codebase, and neither stage is registered in
`pipeline/config.py` STAGES. There is no per-cell Feature_Table to join to
yet.

Rather than block on that, `apply.py` reads the raw Sprint-0 sources
directly (CAPAD protected areas, the derived slope raster, ABS urban
centres, the GWA wind-speed raster) and recomputes only the specific
per-cell values the default exclusion rules need: protected-area overlap,
mean slope, urban overlap, and wind-data availability. This deliberately
duplicates logic that S1-06/S1-03 are meant to own as their per-cell
feature tables.

When S1-06 and S1-03 are actually implemented, `apply.py`'s field-computing
functions (`_protected_overlap`, `_urban_overlap`, the raster sampling
calls) should be deleted and replaced with a read of their Feature_Table /
wind feature table output, joined on `cell_id`. The rule engine (`rules.py`)
and the output / validation / report code do not need to change — they
operate on a generic per-cell field dict, not on how those fields were
computed.

Also note the current source-data coverage: the slope raster, the GWA
wind-speed raster and the ABS urban-centre extract only cover the New
England REZ study window, not the full NSW grid (see
`DATA/geographic/DATA_PROVENANCE.md` / `DATA/wind-resource/DATA_PROVENANCE.md`).
CAPAD (protected areas) is the one source with full-NSW coverage. This means
the vast majority of the 47,311-cell NSW grid will be excluded today with
reason "Missing wind data" simply because no wind data exists there yet —
that is the honest, documented state of Sprint 1 data coverage, not a bug
in this stage. See the generated method report's Coverage section.
"""
