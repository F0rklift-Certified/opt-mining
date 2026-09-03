"""
Sanity Pipeline — S1-12 Validation / Sanity Check (`sanity` stage).

The pipeline's **terminal** stage. It reads the Sprint 1 outputs READ-ONLY and
reports whether the results are *plausible against known reality*, producing the
human-readable Validation_Report (``outputs/sprint1_validation_report.md``) plus
an optional machine-readable Results_Sidecar.

What the stage does
    It consumes the Sprint 1 outputs as read-only inputs — the ranked Shortlist
    (S1-11, latest timestamped file under ``DATA/shortlist/``), the per-cell
    Scored_Table (S1-10), the Integrated_Feature_Table (S1-08), the Geoscience
    Australia Wind_Generators dataset, and the Analysis_Grid — and runs four
    plausibility checks that ask whether the pipeline's outputs *make sense*:

        1. Known Wind Farm Comparison — locate each known wind farm to its
           containing cell and check its score / rank / percentile.
        2. Exclusion Validation — assert urban centres and national parks
           resolve to excluded cells and that no offshore cell exists.
        3. Feature-Value Spot-Checks — record feature values for a deterministic
           spread of cells for independent human verification.
        4. Score-Distribution Plausibility — distribution statistics, a
           degenerate-clustering flag, top-score geographic diversity, and the
           wind-versus-score correlation.

    Surprising results are documented honestly and, where systematic, logged as
    Sprint2_Issues. The stage is read-only on all inputs and NEVER re-scores,
    re-ranks, re-weights, or re-tunes the model.

Distinction from the structural ``validate`` step
    This stage is deliberately distinct from the cross-domain structural
    validation in ``pipeline/validate.py``. ``validate.py`` checks internal
    data-integrity contracts — row counts, schema, CRS, and ``cell_id`` key
    coverage — i.e. whether the data is well-formed. The ``sanity`` stage
    instead asks whether the *results* are believable against known reality. The
    stage key and its domain are named ``sanity`` (not ``validate``) so the two
    separate concerns never clash.

Terminal position in the stage sequence
    ``sanity`` is registered in ``pipeline/config.py`` as the last stage, after
    ``shortlist`` (the producer of one of its inputs), so it runs last:

        ... -> exclusions -> integration -> scoring -> shortlist -> sanity

Usage:
    from pipeline.sanity.run import run as sanity_run
"""
