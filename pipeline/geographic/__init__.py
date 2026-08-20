"""
Geographic & Environmental Pipeline — boundaries, elevation, land use, protected areas.

Stages:
    1. probe     — Discover available geographic/environmental data sources
    2. download  — Fetch vectors (ABS, CAPAD, NE, NEM) + rasters (SRTM, NLUM)
    3. inspect   — Examine vector and raster samples (statistics, metadata)
    4. derive    — Compute slope and terrain ruggedness from DEM clips
    5. validate  — Geographic ground-truth checks (CAPAD areas, DEM, NLUM)

Usage:
    from pipeline.geographic.probe import run as geo_probe
    from pipeline.geographic.download import run as geo_download
"""
