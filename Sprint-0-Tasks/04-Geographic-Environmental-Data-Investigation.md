# Task 4 — Geographic & Environmental Data Investigation

**Sprint:** 0 (Week 1)
**Assignee:** _[Name]_
**Status:** Not Started
**Estimated Effort:** 1–2 days

---

## 1. Objective

Investigate, document and sample publicly available Australian geographic and environmental datasets that support the geographic/environmental suitability criterion — including elevation, protected areas, land use, administrative boundaries, and other spatial constraints relevant to wind energy site selection.

---

## 2. Context

The Product Knowledge Base identifies "Geographic and environmental suitability" as the fourth core criterion. This data serves two distinct purposes in the platform:

1. **Hard exclusions** — areas where wind development is clearly not permitted (national parks, protected areas, highly urbanised zones).
2. **Suitability penalties/thresholds** — factors that reduce suitability without outright excluding a location (steep terrain, certain land-use types, distance from roads).

Additionally, administrative boundary data is needed as a reference layer (state/territory boundaries, NEM region geometries) to align other datasets.

Key sources likely include Geoscience Australia, the Australian Government's data.gov.au portal, NationalMap/AREMI, and state-level spatial data portals.

---

## 3. Investigation Checklist

### A. Administrative Boundaries
- [ ] Identify a dataset of Australian state and territory boundaries (polygons)
- [ ] Check whether NEM region boundaries are available as spatial data
- [ ] Identify Local Government Area (LGA) boundaries if available
- [ ] Record format, CRS, and licence for each
- [ ] Note the datum — GDA94 vs GDA2020

### B. Elevation / Digital Elevation Model (DEM)
- [ ] Identify the national DEM from Geoscience Australia (SRTM-derived, ~30m or ~1 arc-second)
- [ ] Determine available resolutions (1 arc-second ~30m, 3 arc-second ~90m, or coarser)
- [ ] Check file format (GeoTIFF, NetCDF, tiles?)
- [ ] Determine file size for national coverage
- [ ] Assess whether slope can be derived from the DEM or is provided pre-computed
- [ ] Check whether a coarser version exists that is more manageable for screening

### C. Protected Areas & National Parks
- [ ] Identify the Collaborative Australian Protected Areas Database (CAPAD) or equivalent
- [ ] Determine whether data includes IUCN categories
- [ ] Check whether marine vs terrestrial protected areas are distinguished
- [ ] Record format, CRS, and licence
- [ ] Confirm that boundaries are provided as polygons (for spatial exclusion)

### D. Land Use
- [ ] Identify the Australian Land Use and Management (ALUM) classification dataset
- [ ] Determine spatial resolution and format
- [ ] Check whether categories distinguish: agriculture, forestry, urban, conservation, mining, etc.
- [ ] Assess whether land use data can identify clearly unsuitable areas (dense urban, water bodies)
- [ ] Record vintage — how recent is the latest version?

### E. Urban Areas & Population Centres
- [ ] Identify datasets showing urban extent or population centre boundaries
- [ ] This may also serve as a proxy for demand allocation (cross-reference with Task 2)
- [ ] Check whether population data at a spatial level (SA1, SA2, mesh block) is available from ABS
- [ ] Record format and CRS

### F. Roads & Accessibility
- [ ] Identify publicly available road network data for Australia
- [ ] Potential sources: OpenStreetMap extract, Geoscience Australia, state transport agencies
- [ ] Determine whether road classification is included (highway, sealed, unsealed)
- [ ] Note: this is secondary priority — investigate only if time allows

### G. Coastline & Water Bodies
- [ ] Identify a coastline dataset (useful for masking ocean areas from the analysis grid)
- [ ] Check whether major water bodies (lakes, reservoirs) are included
- [ ] This supports hard exclusion of water/ocean cells

### H. Sample Downloads
- [ ] Download a manageable sample of each promising dataset
- [ ] For large rasters (DEM), download a tile or clip covering one state or a small region
- [ ] Store samples in `DATA/geographic/` with clear naming

---

## 4. Data Sources Investigated

| Source Name | URL | Format(s) | Licence | Download Available? | Notes |
|-------------|-----|-----------|---------|---------------------|-------|
| Geoscience Australia — DEM (SRTM) | https://www.ga.gov.au/ | | | | National elevation |
| CAPAD — Protected Areas | https://www.dcceew.gov.au/environment/land/nrs/science/capad | | | | Hard exclusions |
| ABARES — Land Use | https://www.agriculture.gov.au/abares/aclump | | | | Land classification |
| ABS — Statistical Boundaries | https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs-edition-3 | | | | Admin boundaries, SA2, LGA |
| NationalMap / AREMI | https://nationalmap.gov.au/ | | | | Multiple layers |
| data.gov.au | https://data.gov.au/ | | | | General portal |
| OpenStreetMap — Australia | https://download.geofabrik.de/australia-oceania/australia.html | | | | Roads, water |
| | | | | | |

---

## 5. Sample Data Downloaded

| File Name | Source | Size | Spatial Coverage | Temporal Coverage | Location in Repo |
|-----------|--------|------|------------------|-------------------|------------------|
|           |        |      |                  |                   | `DATA/geographic/` |

---

## 6. Data Inspection Summary

*Open each downloaded sample and record:*

| Dataset | Type (Raster/Vector) | Columns/Bands | Row Count / Features / Grid Size | Missing Values / NoData | CRS | Usable? |
|---------|---------------------|---------------|----------------------------------|------------------------|-----|---------|
|         |                     |               |                                  |                        |     |         |

**For raster data (DEM), also record:**
- Number of bands:
- Pixel size (x, y):
- NoData value:
- Data type (float32, int16, etc.):
- Elevation units (metres):
- Bounds (xmin, ymin, xmax, ymax):
- File size per tile:

**For vector data (boundaries, protected areas), also record:**
- Geometry type (Point / Polygon / MultiPolygon):
- Number of features:
- Key attribute fields:
- Spatial extent:

---

## 7. Data Dictionary

*Create one data dictionary per dataset. Templates below:*

### 7a. Digital Elevation Model

**Dataset:** [Name, e.g. GA SRTM DEM 1 Second]
**Source:** [URL]
**Format:** [GeoTIFF]
**CRS:** [e.g. EPSG:4326]
**Spatial Resolution:** [e.g. ~30m / 1 arc-second]
**Units:** Metres above sea level

| Band | Data Type | Units | Description | Value Range | NoData Value |
|------|-----------|-------|-------------|-------------|--------------|
| 1 | float32 | m | Elevation above sea level | -10 to ~2230 | -9999 |

### 7b. Protected Areas (CAPAD)

**Dataset:** [Name]
**Source:** [URL]
**Format:** [Shapefile / GeoJSON / GeoPackage]
**CRS:** [e.g. EPSG:4283 GDA94]
**Geometry:** Polygon / MultiPolygon

| Field/Column Name | Data Type | Units | Description | Example Value | Missing Values? |
|-------------------|-----------|-------|-------------|---------------|-----------------|
| NAME | string | — | Protected area name | Kosciuszko National Park | |
| TYPE | string | — | Area type | National Park | |
| IUCN_CAT | string | — | IUCN category | II | |
| STATE | string | — | State/territory | NSW | |
| AREA_KM2 | float | km² | Area | 6900.2 | |
| | | | | | |

### 7c. Land Use

**Dataset:** [Name]
**Source:** [URL]
**Format:** [GeoTIFF / Shapefile]
**CRS:** [e.g. EPSG:4283]
**Spatial Resolution:** [e.g. 50m]

| Field/Band | Data Type | Units | Description | Example Value | Missing Values? |
|------------|-----------|-------|-------------|---------------|-----------------|
| LU_CODE | integer | — | ALUM classification code | 210 | |
| LU_DESC | string | — | Land use description | Grazing modified pastures | |
| | | | | | |

### 7d. Administrative Boundaries

**Dataset:** [Name]
**Source:** [URL]
**Format:** [Shapefile / GeoJSON]
**CRS:** [e.g. EPSG:4283]
**Geometry:** Polygon / MultiPolygon

| Field/Column Name | Data Type | Units | Description | Example Value | Missing Values? |
|-------------------|-----------|-------|-------------|---------------|-----------------|
| STE_NAME | string | — | State name | New South Wales | |
| STE_CODE | string | — | State code | 1 | |
| AREA_SQKM | float | km² | Area | 800642 | |
| | | | | | |

---

## 8. Integration Issues Identified

| Issue | Description | Severity (High/Med/Low) | Suggested Resolution | Resolved? |
|-------|-------------|-------------------------|----------------------|-----------|
| DEM resolution vs grid | DEM at ~30m is far finer than the ~5km analysis grid | Med | Derive slope/mean elevation per cell during aggregation | No |
| DEM file size | National DEM at 30m may be tens of GB | Med | Use coarser version or process tile-by-tile | No |
| Datum differences | GDA94 (EPSG:4283) vs GDA2020 (EPSG:7844) vs WGS84 (EPSG:4326) | Med | Difference is small (~1.8m) but must be explicit; standardise | No |
| Land use vintage | Land use data may be several years old | Low | Document vintage; accept for screening | No |
| Protected area boundaries | May include marine areas that overlap the analysis grid | Low | Filter to terrestrial only | No |
| State naming | "NSW" vs "New South Wales" vs "1" across datasets | Low | Create lookup table for state identifiers | No |
| | | | | |

*Also consider:*
- Can slope be derived from the DEM, or should a pre-computed slope dataset be found?
- Are there datasets that combine multiple exclusion layers into one?
- How do urban area boundaries interact with land-use classification?
- Are there temporal changes in protected areas that matter (recently gazetted areas)?

---

## 9. Key Findings & Recommendations

*After completing the investigation, summarise:*

- What datasets are available and usable for each category?
- Which datasets should be used for **hard exclusions** (protected areas, water, dense urban)?
- Which datasets should be used for **suitability penalties** (slope, certain land-use types)?
- What DEM resolution is practical for the project? Should we use 30m or a coarser derivative?
- What is the recommended approach for deriving slope from the DEM?
- Are there any datasets that are unexpectedly unavailable or unusable?
- What CRS do most Australian spatial datasets use — and what should the project standardise on?
- Are there any blockers or concerns?

---

## 10. Acceptance Criteria

- [ ] At least one dataset is identified and documented for each category:
  - [ ] Administrative boundaries (state/territory at minimum)
  - [ ] Elevation / DEM
  - [ ] Protected areas (for hard exclusion)
  - [ ] Land use
- [ ] Secondary datasets are noted if investigated (urban areas, roads, coastline)
- [ ] Sample datasets are downloaded and stored in `DATA/geographic/`
- [ ] Each sample has been opened and inspected (geometry type, CRS, resolution, attributes, coverage)
- [ ] A data dictionary is completed for each primary dataset
- [ ] Integration issues are identified (at minimum: CRS/datum, resolution vs grid, file size management)
- [ ] Datasets are categorised into "hard exclusion" vs "suitability penalty" use
- [ ] Findings and recommendations section is written

---

## 11. References & Links

- Geoscience Australia — Elevation: https://www.ga.gov.au/scientific-topics/national-location-information/digital-elevation-data
- CAPAD (Protected Areas): https://www.dcceew.gov.au/environment/land/nrs/science/capad
- ABARES Land Use: https://www.agriculture.gov.au/abares/aclump
- ABS ASGS Boundaries: https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs-edition-3
- NationalMap: https://nationalmap.gov.au/
- data.gov.au: https://data.gov.au/
- Geofabrik OSM Australia: https://download.geofabrik.de/australia-oceania/australia.html
- Product Knowledge Base: see `Opt-Mining - Product Knowledge Base.md`
