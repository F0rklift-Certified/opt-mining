# S1-02: Finalise the Common Analysis Cell

**Type:** Task  
**Priority:** Highest  
**Story Points:** 3  
**Labels:** architecture, spatial  
**Blocked by:** S1-01  
**Blocks:** S1-03, S1-04, S1-05, S1-06, S1-07, S1-08  
**Status:** Complete  
**Completed:** 2026-08-27
**PR** https://github.com/F0rklift-Certified/opt-mining/pull/7

---

## Objective

Select and document the spatial unit (analysis cell) that all pipeline outputs will be mapped to. This is a foundational architectural decision — every feature layer depends on it.

---

## Context

All feature layers (wind, demand, infrastructure, geographic) must share a common spatial index so they can be joined into an integrated site table. Two options have been identified:

**Option A:** ~0.05° GWA-aligned geographic cells (EPSG:4326)
- Aligns directly with Global Wind Atlas grid
- Avoids resampling wind data
- Cell size varies with latitude (~5.5 km at NSW latitudes)
- Geographic CRS — distances in degrees, not metres

**Option B:** ~5 km projected cells using EPSG:3577 (Australian Albers Equal Area)
- Equal-area cells — consistent km² across the study area
- Distance calculations are straightforward (metres)
- Requires resampling wind data from GWA native grid
- Standard for Australian spatial analysis

---

## Deliverables

1. Decision document with analysis of both options
2. Reproducible script/module that generates the NSW cell grid
3. Output grid file (GeoPackage or GeoJSON)

---

## Acceptance Criteria

- [x] Decision document exists comparing Option A vs Option B
- [x] Decision criteria are documented:
  - Alignment with primary wind data source
  - Computational cost
  - Area distortion / consistency
  - Compatibility with downstream distance calculations
  - Compatibility with raster zonal statistics
- [x] Chosen option is formally recorded with rationale
- [x] A reproducible script or module generates the NSW cell grid (GeoDataFrame)
- [x] Grid output includes: `cell_id`, `geometry`, `centroid_lat`, `centroid_lon`, `area_km2`
- [x] Grid is saved as GeoPackage or GeoJSON for reuse by downstream tasks
- [x] CRS is explicitly documented in code and metadata
- [x] Cell count for NSW is reported and sanity-checked
- [x] Grid boundary is defined (NSW state boundary, or NSW + buffer)

---

## Decision Factors to Evaluate

| Criterion | Option A (0.05° geographic) | Option B (5 km projected) |
|-----------|---------------------------|--------------------------|
| Wind data alignment | Native match | Requires resampling |
| Equal area | No (varies ~5%) | Yes |
| Distance calculations | Needs projection | Native in metres |
| Raster zonal stats | Straightforward | Straightforward |
| Downstream joins | Cell ID based | Cell ID based |
| Australian standard practice | Less common | Common (EPSG:3577) |

---

## Notes

- The Constitution requires: "Make coordinate reference systems, spatial resolutions and units explicit at every boundary — never convert silently"
- Whichever option is chosen, document the exact cell dimensions, total count, and any edge-handling rules
- Consider whether the grid should extend slightly beyond NSW to avoid boundary effects


---

## Completion Summary

**Decision:** Option A — 0.05° GWA-aligned geographic cells (EPSG:4326)

**Key Results:**

| Metric | Value |
|--------|-------|
| Total cells (NSW bbox) | 47,311 |
| Grid dimensions | 253 cols × 187 rows |
| Cell size | 0.05° (20 × GWA native pixel) |
| Representative cell | 4.68 km × 5.56 km (at 32.8°S) |
| Area range | 24.54 – 27.20 km² |
| Storage CRS | EPSG:4326 |
| Computation CRS | EPSG:3577 |
| GWA pixels per cell | 20 × 20 = 400 (exact) |
| Output file size | 13.2 MB |

**Artefacts Produced:**

| Path | Description |
|------|-------------|
| `DATA/grid/decision_analysis_cell.md` | Decision document with full Option A vs B analysis |
| `DATA/grid/nsw_analysis_grid.gpkg` | NSW grid GeoPackage (47,311 cells, EPSG:4326) |
| `DATA/grid/nsw_analysis_grid_metadata.json` | Metadata sidecar (CRS, origin, area stats) |
| `pipeline/grid/__init__.py` | Subpackage docstring |
| `pipeline/grid/__main__.py` | Standalone CLI (`python -m pipeline.grid`) |
| `pipeline/grid/config.py` | Grid constants (GWA origin, cell size, bbox, CRS) |
| `pipeline/grid/generate.py` | `generate_grid()` and `run()` functions |
| `tests/test_grid.py` | 24 integration tests (all passing) |

**Dependencies Added:**

| Package | Version | Purpose |
|---------|---------|---------|
| geopandas | 1.1.4 | GeoDataFrame creation, spatial operations, GeoPackage I/O |
| shapely | 2.1.2 | Polygon geometry creation (box) |
| pyogrio | 0.13.0 | Fast GeoPackage read/write backend for geopandas |
| pyproj | 3.7.2 | CRS transformations (EPSG:4326 ↔ EPSG:3577 for area) |

**How to Run:**

```bash
# Via the pipeline CLI
python -m pipeline --only grid --verbose

# Standalone
python -m pipeline.grid --verbose

# Programmatically
from pipeline.grid.generate import generate_grid
gdf = generate_grid()  # Returns GeoDataFrame, no I/O
```

**Tests:**

```bash
pytest tests/test_grid.py -v
# 24 passed in 1.4s
```

**Downstream Usage:**

All feature-layer tasks (S1-03 through S1-08) import the grid via:

```python
import geopandas as gpd
grid = gpd.read_file("DATA/grid/nsw_analysis_grid.gpkg")
# Join features to grid on cell_id or spatial join
```

Or generate fresh in-memory:

```python
from pipeline.grid.generate import generate_grid
grid = generate_grid()
```
