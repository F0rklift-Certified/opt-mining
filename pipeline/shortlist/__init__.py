"""
Shortlist — the S1-11 preliminary ranked-shortlist stage (stage `shortlist`).

Position in the pipeline sequence: `shortlist` is registered in
`config.STAGES` immediately AFTER `scoring` (S1-10, which produces the sole
score input) and BEFORE `validate` (the cross-domain tier):

    ... → integration → scoring → shortlist → validate

This stage is deliberately a FILTERING and FORMATTING step, not a modelling
step. It reads the S1-10 Scored_Table, selects the top-N Eligible_Cells by
their existing ascending `rank`, joins each cell's `centroid_lat` /
`centroid_lon` from the Analysis_Grid on `cell_id` in EPSG:4326, and writes
the Sprint 1 headline output — a Shortlist_CSV and a Shortlist_GeoJSON
carrying the same `cell_id` set in the same rank order, plus a Summary_Report
of descriptive statistics. It performs no re-scoring and no re-ranking, and
never re-derives the grid.

Every output and its metadata carry the Preliminary_Disclaimer and the
~5 km Analysis_Resolution statement: the shortlist is a preliminary
screening starting point, not a site approval.

Module map
----------
- ``config.py``   — Top_N precedence resolver (CLI > pipeline config > default
                    20) and the ``DEFAULT_TOP_N`` constant; rejects a
                    non-positive-integer Top_N before any output.
- ``load.py``     — Reads the S1-10 Scored_Table as the sole per-cell score
                    input; validates the required columns and reuses ``cell_id``
                    byte-for-byte without re-scoring or re-ranking.
- ``select.py``   — Pure selection: filters to Eligible_Cells and takes the
                    top ``min(Top_N, n_eligible)`` rows ordered ascending by the
                    existing S1-10 ``rank`` (no re-ranking, no padding).
- ``coords.py``   — Loads the Analysis_Grid and left-joins ``centroid_lat`` /
                    ``centroid_lon`` on ``cell_id`` in EPSG:4326; halts on any
                    unmatched shortlisted ``cell_id``.
- ``assemble.py`` — Assembles the Shortlist frame in the documented column
                    order and appends optional context columns where available.
- ``summary.py``  — Computes the Summary_Statistics (score distribution over
                    eligible cells only, geographic spread, REZ and confidence
                    distributions, and cell counts).
- ``naming.py``   — Derives the single UTC Run_Timestamp and resolves the
                    timestamped/versioned output filenames (region slug ``nsw``),
                    appending a finer-grained component on a name collision.
- ``write.py``    — Atomic writers for the Shortlist_CSV and Shortlist_GeoJSON
                    (EPSG:4326, same ``cell_id`` set in the same rank order),
                    emitting headers even for an empty shortlist.
- ``report.py``   — Writes the Summary_Report and metadata sidecar (disclaimer +
                    resolution) and records derived-product provenance
                    (``DATA_PROVENANCE.md`` + manifest + source_register).
- ``run.py``      — Stage entry point exposing the uniform
                    ``run(verbose=False, ...) -> dict`` contract that orchestrates
                    the load → select → join → assemble → summarise → write →
                    provenance → validate flow.
- ``validate.py`` — Per-domain "no silent passes" checks (row-count, eligibility,
                    ordering, coordinate presence, CSV/GeoJSON equality, and
                    disclaimer/resolution presence).
"""
