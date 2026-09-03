"""
Scoring — the S1-10 baseline suitability model (stage `scoring`).

Position in the pipeline sequence: `scoring` is registered in
`config.STAGES` immediately AFTER `integration` (S1-08, which produces the
sole feature input) and BEFORE `validate` (the cross-domain tier, which
cross-checks the scored table against the grid):

    ... → exclusions → integration → scoring → validate

The model is a transparent, deterministic weighted multi-criteria decision
analysis (MCDA) — NOT a machine-learning model. Every eligible cell's score
is a weighted average of its normalised criterion values, and the additive
contribution of each criterion to each score is written out alongside it, so
a planner can interrogate why one cell outranked another. Excluded cells
(S1-07 `eligible = False`) receive a null score and no rank: ineligible land
is never ranked as if it were developable.

Criteria weights are USER INPUTS loaded from `scoring_weights.yaml` at
runtime (or `--scoring-weights PATH`); no weight literal appears anywhere in
this subpackage's source. The model is never circular — `wind_speed` enters
only as an input criterion and is never a prediction target.

Modules:
    config    — Paths, filenames, vocabularies and tolerances. Input paths
                and the confidence vocabulary are composed from the producing
                domain's config, never re-typed as literals.
    weights   — `Criterion` / `WeightsConfig` dataclasses and `load_weights`:
                parses and validates the weights YAML, failing before any
                output is written.
    load      — `load_integrated`: reads the S1-08 integrated feature table
                as the sole feature input, halting on any missing column.
                The only file-reading path for feature data.
    normalise — `compute_bounds` / `normalise_series`: directional min-max
                rescaling to [0, 1] from the ELIGIBLE population only.
    score     — `score_frame`: the PURE Scoring_Function (DataFrame +
                WeightsConfig in, scored DataFrame out, no file I/O), so the
                scoring computation is independently replaceable without
                touching the data-loading layer.
    rank      — `assign_ranks`: descending by score, ties broken by ascending
                `cell_id`, eligible cells only.
    write     — Atomic GeoPackage + CSV writers for the Scored_Table.
    report    — Method report (formula, weights, bounds, counts) and the
                derived-product provenance triple.
    validate  — No-silent-passes checks over the Scored_Table.
    run       — Stage entry point: `run(verbose=False, ...) -> dict`.

Usage:
    from pipeline.scoring.run import run
    summary = run(verbose=True)

    # or with the pure scoring function directly, on an in-memory frame:
    from pipeline.scoring.score import score_frame
    from pipeline.scoring.weights import load_weights
    scored = score_frame(features, load_weights("path/to/weights.yaml"))
"""
