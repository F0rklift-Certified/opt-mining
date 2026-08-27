"""
Grid subpackage — Common Analysis Cell generation for the Opt-Mining platform.

This subpackage generates and manages the spatial grid that all pipeline outputs
are mapped to. Every feature layer (wind, demand, infrastructure, geographic)
joins to this common grid, enabling integrated site scoring.

Architecture decision (S1-02):
    Cell size: 0.05 degrees (~5 km at NSW latitudes)
    CRS: EPSG:4326 (storage) / EPSG:3577 (computation)
    Alignment: Anchored on Global Wind Atlas origin (109.21125, -8.86125)
               so each cell is exactly 20x20 native GWA pixels — no boundary
               ambiguity or fractional overlap.

Public API:
    from pipeline.grid.generate import generate_grid, run

    # Generate the grid as a GeoDataFrame (no I/O)
    gdf = generate_grid()

    # Generate, sanity-check, and write to GeoPackage
    result = run(verbose=True)
"""
