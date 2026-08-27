# Decision: Common Analysis Cell

**Task:** S1-02 — Finalise the Common Analysis Cell  
**Date:** 2026-08-27  
**Status:** Decided  
**Decision:** Option A — 0.05° GWA-aligned geographic cells (EPSG:4326)

---

## 1. Problem Statement

All feature layers (wind resource, electricity demand, infrastructure accessibility, geographic suitability) must share a common spatial index so they can be joined into an integrated site table for scoring and ranking. This requires selecting a single spatial unit — the "analysis cell" — that every pipeline output maps to.

The choice of analysis cell is a foundational architectural decision. It determines:
- How raster data is aggregated (wind speed, slope, land use)
- How vector data is spatially indexed (infrastructure distance, protected area overlap)
- How tabular data is spatially allocated (demand indicators)
- The resolution at which the platform presents results

---

## 2. Options Evaluated

### Option A: ~0.05° GWA-aligned Geographic Cells (EPSG:4326)

Divide the study area into uniform 0.05-degree cells anchored on the Global Wind Atlas v4 raster origin. Each cell is exactly 20×20 native GWA pixels.

**Pros:**
- Aligns directly with the largest and finest dataset (GWA, ~250 m, 600+ MB per layer)
- Clean 20:1 pixel-to-cell ratio — no fractional overlaps, no interpolation
- Simple to implement, explain, and visualise
- Resolution-agnostic scoring (always aggregates, never interpolates)
- Direct web-map tile alignment (Leaflet, MapLibre)

**Cons:**
- Cell width varies with latitude (~4.68 km at 33°S, ~4.00 km at 44°S)
- Geographic CRS — distances must be computed in a projected CRS
- Not an Australian spatial standard (less familiar to Australian GIS practitioners)

### Option B: ~5 km Projected Cells (EPSG:3577, Australian Albers)

Divide the study area into 5,000 m × 5,000 m cells in Australian Albers Equal Area projection.

**Pros:**
- Equal-area cells — consistent km² across the study area
- Distance calculations native in metres (no CRS switching)
- Standard for Australian spatial analysis (ERIN, GA, ABS use Albers)

**Cons:**
- Requires resampling all GWA raster layers from geographic to projected grid
- No clean pixel ratio — introduces boundary-pixel ambiguity
- Reprojecting 600+ MB rasters is computationally expensive and error-prone
- Adds a resampling artefact where none exists in Option A

---

## 3. Decision Criteria

| Criterion | Option A (0.05° geographic) | Option B (5 km projected) | Winner |
|-----------|---------------------------|--------------------------|--------|
| **Wind data alignment** | Native match — 20×20 pixels per cell, zero boundary ambiguity | Requires resampling — fractional pixel overlaps at every cell edge | A |
| **Computational cost** | No resampling needed for wind/elevation rasters | Must reproject all rasters before aggregation (~minutes per layer) | A |
| **Area distortion / consistency** | Cell area varies ~10% across NSW (24.5–27.2 km²) | Perfectly uniform (25 km² everywhere) | B |
| **Distance calculations** | Must reproject cell centroids to EPSG:3577 for distances | Native in metres | B |
| **Raster zonal statistics** | Straightforward — clean block reads from native grid | Straightforward once reprojected | Tie |
| **Downstream joins** | Cell ID based (identical mechanism) | Cell ID based (identical mechanism) | Tie |
| **Australian standard practice** | Less common in Australian GIS | Standard (GA, ERIN, ABS) | B |
| **Simplicity / reproducibility** | Simpler (fewer transformation steps, fewer potential errors) | More complex pipeline (resampling step required) | A |

**Score: Option A wins 4 criteria, Option B wins 3, 2 ties.**

---

## 4. Decision

**Option A is selected.**

---

## 5. Rationale

1. **Data alignment is the strongest argument.** The GWA v4 raster at 0.0025° resolution is the platform's largest and finest input dataset. A 0.05° cell provides a perfect 20:1 ratio — every cell is exactly 400 native pixels. This eliminates an entire class of aggregation artefact (boundary pixels split between cells, fractional weighting, interpolation noise). No other option offers this property.

2. **Resolution is appropriate.** Every raster dataset (GWA ~250 m, SRTM ~90 m, NLUM ~250 m) is finer than the cell. The grid always aggregates, never interpolates — the correct direction for a screening tool that summarises real data rather than fabricating sub-cell detail.

3. **Computational feasibility.** NSW contains 47,311 cells — well within standard hardware constraints (16 GB RAM, SSD). No reprojection of the 600+ MB GWA layers is needed, saving minutes of compute time and eliminating a potential error source.

4. **Area variation is acceptable.** The ~10% variation in cell area across NSW (24.5 km² in the south to 27.2 km² in the north) does not affect relative rankings. Cells are compared by scored features, not by raw area. The variation must be stated wherever results are presented, per the Constitution's transparency requirements.

5. **Simplicity.** Fewer transformation steps means fewer opportunities for silent error. The Constitution states: "Make coordinate reference systems, spatial resolutions and units explicit at every boundary — never convert silently." Option A minimises the number of boundaries where conversion is needed.

**Mitigations for Option A's weaknesses:**
- Distance calculations: all distance computations (infrastructure proximity) reproject cell centroids to EPSG:3577 before computing Euclidean distances. This is a single, well-defined, well-tested step.
- Area computation: `area_km2` is pre-computed per cell via EPSG:3577 projection and stored as a column. Downstream tasks never need to compute area themselves.
- Cell width variation: documented in metadata and caveated in all result presentations.

---

## 6. Grid Specification

| Parameter | Value | Source |
|-----------|-------|--------|
| Cell size | 0.05° | 20 × GWA native pixel (0.0025°) |
| Origin (longitude) | 109.21125° E | GWA v4 western edge (Task 1 inspection) |
| Origin (latitude) | -8.86125° S | GWA v4 northern edge (Task 1 inspection) |
| NSW grid origin (snapped) | (141.01125° E, -28.16125° S) | Snapped to GWA lattice from NSW bbox |
| NSW bounding box | (141.0, -37.55, 153.7, -28.15) | ABS STE 2021 state boundary extent |
| Grid dimensions (NSW) | 253 cols × 187 rows | Computed from snapped origin + bbox |
| Total cells (NSW) | 47,311 | Full rectangular bounding box |
| Storage CRS | EPSG:4326 (WGS 84) | Native CRS of GWA — no reprojection needed |
| Computation CRS | EPSG:3577 (GDA94 / Australian Albers) | Equal-area for distance and area calculations |
| Cell ID format | `S{lat:.3f}_E{lon:.3f}` | Centroid coordinates, human-readable |
| Cell area range | 24.54 – 27.20 km² | Computed via EPSG:3577 projection |
| Representative cell size | 4.68 km × 5.56 km | At 32.8°S (NSW mid-latitude) |
| GWA pixels per cell | 20 × 20 = 400 | Exact — no fractional overlap |
| Output format | GeoPackage (.gpkg) | Binary, fast I/O, native CRS metadata |

---

## 7. Grid Alignment Proof

The analysis grid is anchored on the GWA v4 raster origin so that every cell boundary coincides exactly with a native pixel boundary.

**Verification:**
- GWA origin: (109.21125, -8.86125)
- GWA pixel step: 0.0025°
- Analysis cell step: 0.05° = 20 × 0.0025°
- Ratio: 20 (integer — no fractional overlap)
- NSW grid western edge: 141.01125° = 109.21125° + 12,720 × 0.0025°
- 12,720 is an integer — confirmed alignment

This alignment is validated by an automated test (`tests/test_grid.py`) that verifies every cell edge is an integer number of GWA pixels from the origin.

---

## 8. Scope and Boundary

- **Spatial scope:** Full rectangular bounding box covering NSW. The grid includes cells over ocean, over interstate land, and over NSW land. Land-masking (distinguishing NSW-land cells from ocean/interstate cells) is performed by downstream tasks (S1-06, S1-07).

- **Buffer:** No explicit buffer is added beyond the NSW state boundary bbox. The rectangular grid naturally extends slightly beyond the irregular state boundary in all directions, providing implicit edge coverage.

- **Edge handling:** Cells at the grid boundary may partially overlap with the state border. Downstream tasks that apply the land mask will classify these cells based on centroid location or fractional overlap rules.

---

## 9. Caveats and Limitations

1. **Cell width varies with latitude.** At 28°S (northern NSW) cells are ~4.93 km wide; at 37°S (southern NSW) they are ~4.43 km wide. This ~10% variation is acceptable for screening but must be stated wherever results are presented.

2. **Not equal-area.** Cell areas range from 24.54 to 27.20 km². All area-dependent calculations use the pre-computed `area_km2` column (derived from EPSG:3577 projection), not the geographic cell footprint.

3. **Land-masking is deferred.** This grid is the full rectangular bounding box. ~16,000 cells are estimated to be ocean or interstate. These are excluded by downstream tasks, not by the grid itself.

4. **Datum offsets are negligible.** All datasets with non-WGS84 datums (GDA94, GDA2020) have offsets ≤ 1.8 m to WGS84. Against a ~5,000 m cell, this is 0.04% — invisible at screening resolution. Transformations are still declared explicitly per the Constitution.

---

## 10. References

- Sprint 0, Task 5: Data Integration Analysis & Site Definition Proposal (§7: Site Definition Recommendation)
- Sprint 0, Task 1: Wind Resource Data Investigation (GWA grid specification)
- Opt-Mining AI Development Constitution (CRS-explicitness requirement)
- `pipeline/integration/analyse.py`: Computational evidence for grid geometry and cell counts
- `pipeline/grid/generate.py`: Implementation module
- `DATA/grid/nsw_analysis_grid_metadata.json`: Generated grid metadata
