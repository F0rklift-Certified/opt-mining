"""
Integration — cross-domain synthesis (Task 5) and the S1-08 Integrated
Feature Table.

Modules:
    analyse — Task 5 evidence: grid geometry, CRS alignment, resolution
              mapping, cell counts. Standalone; not registered in
              config.STAGES.
    merge   — S1-08 stage `integration`: left-joins the five per-cell layers
              (wind, geographic, infrastructure, demand, exclusions) onto the
              S1-02 analysis grid by `cell_id` and writes the Integrated
              Feature Table (GeoPackage + CSV) with a merge-validation report
              and provenance.
    config  — Paths, layer names and constants for the merge stage; every
              input path is composed from the producing domain's config.

Usage:
    from pipeline.integration.merge import run
    run(verbose=True)
"""
