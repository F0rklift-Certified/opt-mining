# S1-02: Finalise the Common Analysis Cell

**Type:** Task  
**Priority:** Highest  
**Story Points:** 3  
**Labels:** architecture, spatial  
**Blocked by:** S1-01  
**Blocks:** S1-03, S1-04, S1-05, S1-06, S1-07, S1-08

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

- [ ] Decision document exists comparing Option A vs Option B
- [ ] Decision criteria are documented:
  - Alignment with primary wind data source
  - Computational cost
  - Area distortion / consistency
  - Compatibility with downstream distance calculations
  - Compatibility with raster zonal statistics
- [ ] Chosen option is formally recorded with rationale
- [ ] A reproducible script or module generates the NSW cell grid (GeoDataFrame)
- [ ] Grid output includes: `cell_id`, `geometry`, `centroid_lat`, `centroid_lon`, `area_km2`
- [ ] Grid is saved as GeoPackage or GeoJSON for reuse by downstream tasks
- [ ] CRS is explicitly documented in code and metadata
- [ ] Cell count for NSW is reported and sanity-checked
- [ ] Grid boundary is defined (NSW state boundary, or NSW + buffer)

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
