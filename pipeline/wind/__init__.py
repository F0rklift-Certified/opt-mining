"""
Wind Resource Pipeline — Global Wind Atlas data investigation.

Stages:
    1. probe     — Discover which GWA layers are available via HTTP HEAD
    2. download  — Clip GWA country rasters to the study window via /vsicurl/
    3. inspect   — Examine local raster clips (statistics, metadata reports)
    4. validate  — Sample rasters at known wind farm locations + crosscheck
    5. analyse   — Aggregation sensitivity analysis for the scoring grid
    6. features  — Per-cell wind feature table on the common analysis grid (S1-03).
                   NOTE: this stage CONSUMES the grid, so it is registered in
                   config.STAGES AFTER the `grid` stage, not inline with 1-5.

Usage:
    from pipeline.wind.probe import run as wind_probe
    from pipeline.wind.download import run as wind_download
"""
