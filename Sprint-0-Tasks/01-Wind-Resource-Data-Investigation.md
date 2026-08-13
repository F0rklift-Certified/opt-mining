# Task 1 — Wind Resource Data Investigation

**Sprint:** 0 (Week 1)
**Assignee:** _[Name]_
**Status:** Not Started
**Estimated Effort:** 1–2 days

---

## 1. Objective

Investigate, document and sample the wind resource data available for Australia — primarily from the Global Wind Atlas — to determine what can be used as the wind resource criterion in the suitability scoring model.

---

## 2. Context

The Global Wind Atlas is identified in the Product Knowledge Base as the highest-priority data source. It provides mean wind speed, power density, terrain roughness, orography, and capacity-factor layers. The platform will use this data as an *input* — it is not a prediction target.

Key reference: https://globalwindatlas.info/

---

## 3. Investigation Checklist

### Availability & Access
- [ ] Identify what datasets are available on the Global Wind Atlas for Australia
- [ ] Determine what variables are provided (wind speed, power density, capacity factor, roughness, orography, etc.)
- [ ] Identify available measurement heights (e.g. 10m, 50m, 100m, 150m, 200m)
- [ ] Check whether data can be downloaded (bulk download vs. API vs. area selection)
- [ ] Determine the download process — is registration required? Are there download limits?
- [ ] Record licensing and usage restrictions (attribution requirements, commercial use, redistribution)

### Spatial Properties
- [ ] Determine the native spatial resolution (e.g. 250m, 1km)
- [ ] Identify the coordinate reference system (CRS) used
- [ ] Confirm whether latitude/longitude coordinates are explicitly provided or derived from raster grid
- [ ] Check spatial extent — does it cover all of Australia including offshore?

### Format & Structure
- [ ] Identify available file formats (GeoTIFF, NetCDF, CSV, shapefile, etc.)
- [ ] Document file sizes for Australian coverage
- [ ] Determine whether data is provided as raster or vector
- [ ] Check if seasonal/monthly breakdowns are available or only annual means

### Sample Download
- [ ] Download a manageable sample covering a small area (e.g. one state, or a ~200km x 200km region)
- [ ] Try multiple variables if available (wind speed + power density at minimum)
- [ ] Record exact download parameters (area, height, variable, format)
- [ ] Store samples in `DATA/wind-resource/` with a clear naming convention

---

## 4. Data Sources Investigated

| Source Name | URL | Format(s) | Licence | Download Available? | Notes |
|-------------|-----|-----------|---------|---------------------|-------|
| Global Wind Atlas | https://globalwindatlas.info/ | | | | Primary source |
| | | | | | |
| | | | | | |

*If you find alternative or supplementary wind resource datasets (e.g. Bureau of Meteorology wind data, MERRA-2 reanalysis), record them here even if they are secondary.*

---

## 5. Sample Data Downloaded

| File Name | Source | Size | Spatial Coverage | Temporal Coverage | Location in Repo |
|-----------|--------|------|------------------|-------------------|------------------|
|           |        |      |                  |                   | `DATA/wind-resource/` |

---

## 6. Data Inspection Summary

*Open each downloaded sample and record:*

| Dataset | Columns/Variables | Row Count / Grid Size | Missing Values | Coordinate Fields | Units | Date/Time Fields | Usable? |
|---------|-------------------|----------------------|----------------|-------------------|-------|------------------|---------|
|         |                   |                      |                |                   |       |                  |         |

**For raster data specifically, also record:**
- Number of bands:
- Pixel size (x, y):
- NoData value:
- Data type (float32, int16, etc.):
- CRS (EPSG code):
- Bounds (xmin, ymin, xmax, ymax):

---

## 7. Data Dictionary

**Dataset:** Global Wind Atlas — [Variable Name]
**Source:** https://globalwindatlas.info/
**Format:** [GeoTIFF / NetCDF / etc.]
**CRS:** [e.g. EPSG:4326]
**Temporal Range:** [e.g. "Long-term mean based on ERA5 reanalysis 2008–2017" or similar]
**Spatial Resolution:** [e.g. 250m]

| Field/Column/Band | Data Type | Units | Description | Example Value | Missing Values? |
|-------------------|-----------|-------|-------------|---------------|-----------------|
| wind_speed_100m | | m/s | Mean wind speed at 100m height | | |
| power_density | | W/m² | Mean wind power density | | |
| capacity_factor | | ratio (0–1) | Estimated capacity factor | | |
| roughness | | m | Surface roughness length | | |
| | | | | | |

*Create one table per variable/layer if they come as separate files.*

---

## 8. Integration Issues Identified

| Issue | Description | Severity (High/Med/Low) | Suggested Resolution | Resolved? |
|-------|-------------|-------------------------|----------------------|-----------|
| Resolution mismatch | Native resolution (~250m) vs platform grid (~5km) | Med | Aggregation strategy needed (mean? max?) | No |
| File size | Full Australia at native resolution may be very large | Med | Downsample or tile; process state-by-state | No |
| | | | | |

*Also consider:*
- Does the CRS match what other datasets use?
- Will the raster grid align with the ~5km analysis grid defined in the Product Knowledge Base?
- Are there gaps in coverage (e.g. certain islands, offshore areas)?
- What aggregation method is appropriate when downsampling to 5km cells?

---

## 9. Key Findings & Recommendations

*After completing the investigation, summarise:*

- What variables are most useful for the wind resource criterion?
- Which measurement height is most appropriate for utility-scale wind assessment?
- What is the recommended download strategy for the full project (whole of Australia vs. state-by-state)?
- Are there any blockers or concerns?
- Are supplementary data sources needed, or is the Global Wind Atlas sufficient?

---

## 10. Acceptance Criteria

- [ ] Global Wind Atlas data availability is fully documented (variables, heights, resolution, format, licence)
- [ ] At least one sample dataset is downloaded and stored in `DATA/wind-resource/`
- [ ] Sample has been opened and inspected (columns, grid size, CRS, units, missing values)
- [ ] A data dictionary is completed for the primary wind resource dataset
- [ ] Integration issues are identified and documented (at least CRS and resolution alignment)
- [ ] Findings and recommendations section is written
- [ ] Any alternative data sources discovered are noted

---

## 11. References & Links

- Global Wind Atlas: https://globalwindatlas.info/
- Global Wind Atlas methodology documentation: https://globalwindatlas.info/about/method
- Product Knowledge Base: see `Opt-Mining - Product Knowledge Base.md`
- AI Development Constitution: see `Opt-Mining - AI Development Constitution.md`
