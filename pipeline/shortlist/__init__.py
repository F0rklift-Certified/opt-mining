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

(The full module map is authored under task 12.3.)
"""
