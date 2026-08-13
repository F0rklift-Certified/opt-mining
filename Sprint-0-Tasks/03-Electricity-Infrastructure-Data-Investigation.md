# Task 3 — Electricity Infrastructure Data Investigation

**Sprint:** 0 (Week 1)
**Assignee:** _[Name]_
**Status:** Not Started
**Estimated Effort:** 1–2 days

---

## 1. Objective

Investigate, document and sample publicly available Australian electricity infrastructure datasets — including transmission lines, substations, connection points, generators, and Renewable Energy Zones (REZs) — to determine what can be used for the grid/infrastructure accessibility criterion in the suitability scoring model.

---

## 2. Context

The Product Knowledge Base identifies infrastructure accessibility as one of the four core criteria. The platform needs to compute distance and access measures from candidate grid cells to nearby transmission lines, substations, connection points, and existing generators.

Infrastructure proximity is a key practical constraint for wind farm development — a site with excellent wind resource but no nearby grid connection is far more expensive and risky to develop.

Potential sources include AEMO (network and generation data), Geoscience Australia, state-level network operators, and the Australian Renewable Energy Mapping Infrastructure (AREMI) / NationalMap.

---

## 3. Investigation Checklist

### A. Transmission Lines
- [ ] Identify publicly available datasets showing transmission line routes across Australia
- [ ] Determine whether data includes voltage levels (e.g. 132kV, 220kV, 275kV, 330kV, 500kV)
- [ ] Check whether data is geospatial (line geometries with coordinates) or tabular
- [ ] Record format, CRS, and licence
- [ ] Note spatial completeness — does it cover all states and territories?

### B. Substations & Connection Points
- [ ] Identify datasets listing substation locations
- [ ] Determine whether coordinates (lat/lon) are provided
- [ ] Check whether capacity or voltage information is included
- [ ] Identify AEMO's "connection point" data and whether it includes geographic coordinates
- [ ] Note what attributes are available (name, region, voltage, capacity, status)

### C. Generators (Existing)
- [ ] Identify AEMO's generation information page or register
- [ ] Determine what generator attributes are available (type, capacity, fuel source, location, status)
- [ ] Check whether geographic coordinates are provided for each generator
- [ ] Filter for wind generators specifically — these serve as validation data later
- [ ] Note whether planned/proposed generators are included alongside operational ones

### D. Renewable Energy Zones (REZs)
- [ ] Identify whether REZ boundaries are published as geospatial data (shapefiles, GeoJSON)
- [ ] Check AEMO's Integrated System Plan (ISP) documents for REZ definitions
- [ ] Determine whether state-level REZ data exists (e.g. NSW REZ maps from EnergyCo)
- [ ] Record what attributes are available (name, state, technology focus, capacity target)

### E. General Access & Download
- [ ] For each dataset found, determine whether it is freely downloadable
- [ ] Record licensing and attribution requirements
- [ ] Check whether data is available via AREMI / NationalMap as a consolidated source
- [ ] Identify whether any data requires an API or special request

### F. Sample Download
- [ ] Download a manageable sample of each promising dataset
- [ ] Prioritise datasets that include geographic coordinates or spatial geometries
- [ ] Store samples in `DATA/infrastructure/` with clear naming (e.g. `transmission-lines.geojson`, `generators.csv`)

---

## 4. Data Sources Investigated

| Source Name | URL | Format(s) | Licence | Download Available? | Notes |
|-------------|-----|-----------|---------|---------------------|-------|
| AEMO — Generation Information | https://aemo.com.au/energy-systems/electricity/national-electricity-market-nem/nem-forecasting-and-planning/forecasting-and-planning-data/generation-information | | | | |
| AEMO — Integrated System Plan (ISP) | https://aemo.com.au/energy-systems/major-publications/integrated-system-plan-isp | | | | REZ data |
| AREMI / NationalMap | https://nationalmap.gov.au/ | | | | Consolidated infrastructure layers |
| Geoscience Australia — Infrastructure | https://www.ga.gov.au/ | | | | |
| NSW EnergyCo — REZ Maps | | | | | State-level REZ |
| | | | | | |

---

## 5. Sample Data Downloaded

| File Name | Source | Size | Spatial Coverage | Temporal Coverage | Location in Repo |
|-----------|--------|------|------------------|-------------------|------------------|
|           |        |      |                  |                   | `DATA/infrastructure/` |

---

## 6. Data Inspection Summary

*Open each downloaded sample and record:*

| Dataset | Columns/Variables | Row Count / Feature Count | Missing Values | Coordinate Fields | Units | Geometry Type | Usable? |
|---------|-------------------|--------------------------|----------------|-------------------|-------|---------------|---------|
|         |                   |                          |                |                   |       |               |         |

**For geospatial vector data specifically, also record:**
- Geometry type (Point / LineString / Polygon):
- CRS (EPSG code):
- Number of features:
- Attribute fields:
- Spatial extent (bounds):

**For tabular data with coordinates:**
- Coordinate column names (lat/lon or easting/northing?):
- CRS stated or implied:
- Percentage of records with valid coordinates:

---

## 7. Data Dictionary

*Create one data dictionary per dataset. Below are templates for the most likely datasets:*

### 7a. Transmission Lines

**Dataset:** [Name]
**Source:** [URL]
**Format:** [Shapefile / GeoJSON / etc.]
**CRS:** [e.g. EPSG:4283 GDA94 / EPSG:7844 GDA2020]
**Geometry:** LineString

| Field/Column Name | Data Type | Units | Description | Example Value | Missing Values? |
|-------------------|-----------|-------|-------------|---------------|-----------------|
| NAME | string | — | Line name/identifier | Sydney–Newcastle 330kV | |
| VOLTAGE | numeric | kV | Operating voltage | 330 | |
| OWNER | string | — | Network owner | TransGrid | |
| STATUS | string | — | Operational status | Operating | |
| | | | | | |

### 7b. Generators

**Dataset:** [Name]
**Source:** [URL]
**Format:** [CSV / Excel / etc.]
**CRS:** [EPSG:4326 if lat/lon provided]

| Field/Column Name | Data Type | Units | Description | Example Value | Missing Values? |
|-------------------|-----------|-------|-------------|---------------|-----------------|
| Station Name | string | — | Power station name | Bango Wind Farm | |
| Technology Type | string | — | Generation technology | Wind | |
| Nameplate Capacity | float | MW | Registered capacity | 244.0 | |
| Latitude | float | degrees | Location latitude | -34.52 | |
| Longitude | float | degrees | Location longitude | 148.67 | |
| Region | string | — | NEM region | NSW1 | |
| Status | string | — | Current status | Committed | |
| | | | | | |

### 7c. Renewable Energy Zones

**Dataset:** [Name]
**Source:** [URL]
**Format:** [Shapefile / GeoJSON / etc.]
**CRS:** [e.g. EPSG:4283]
**Geometry:** Polygon

| Field/Column Name | Data Type | Units | Description | Example Value | Missing Values? |
|-------------------|-----------|-------|-------------|---------------|-----------------|
| REZ_NAME | string | — | Zone name | New England | |
| STATE | string | — | State | NSW | |
| TECHNOLOGY | string | — | Intended technology | Wind + Solar | |
| | | | | | |

---

## 8. Integration Issues Identified

| Issue | Description | Severity (High/Med/Low) | Suggested Resolution | Resolved? |
|-------|-------------|-------------------------|----------------------|-----------|
| Mixed CRS | Different datasets may use GDA94 (EPSG:4283) vs GDA2020 (EPSG:7844) vs WGS84 (EPSG:4326) | High | Standardise all to a single CRS during ingestion | No |
| Missing coordinates | Some generators or substations may lack lat/lon | Med | Document coverage; geocode from address if critical | No |
| Inconsistent region naming | NEM regions (NSW1) vs state names (NSW) vs full names (New South Wales) | Med | Create a mapping/lookup table | No |
| Data currency | Infrastructure data may be outdated (new lines/substations not shown) | Low | Document vintage; accept for screening purposes | No |
| Multiple sources | Same infrastructure may appear in multiple datasets with different attributes | Low | Choose authoritative source per feature type | No |
| | | | | |

*Also consider:*
- Are transmission line geometries accurate enough to compute meaningful distance measures?
- Do generator locations represent the actual site or an administrative/connection point?
- Are REZ boundaries official or indicative?
- How will "distance to nearest infrastructure" be calculated — Euclidean or network distance?

---

## 9. Key Findings & Recommendations

*After completing the investigation, summarise:*

- What infrastructure datasets are available and usable?
- Which datasets have reliable geographic coordinates?
- What is the best source for each infrastructure type (transmission, substations, generators, REZs)?
- Are there significant gaps in coverage (WA, NT, specific states)?
- What distance/proximity measures can realistically be derived?
- What is the recommended CRS to standardise on?
- Are there any blockers or concerns?
- Which existing wind farms can be used for validation (cross-reference with Task 1)?

---

## 10. Acceptance Criteria

- [ ] At least one dataset is identified and documented for each infrastructure type:
  - [ ] Transmission lines
  - [ ] Substations or connection points
  - [ ] Generators (with wind generators identifiable)
  - [ ] Renewable Energy Zones (if available)
- [ ] Sample datasets are downloaded and stored in `DATA/infrastructure/`
- [ ] Each sample has been opened and inspected (features, columns, CRS, geometry type, missing values)
- [ ] A data dictionary is completed for each primary dataset
- [ ] Integration issues are identified (at minimum: CRS differences, missing coordinates, region naming)
- [ ] Existing wind farm locations are noted (these become validation data for the full platform)
- [ ] Findings and recommendations section is written

---

## 11. References & Links

- AEMO Generation Information: https://aemo.com.au/energy-systems/electricity/national-electricity-market-nem/nem-forecasting-and-planning/forecasting-and-planning-data/generation-information
- AEMO ISP: https://aemo.com.au/energy-systems/major-publications/integrated-system-plan-isp
- NationalMap / AREMI: https://nationalmap.gov.au/
- Geoscience Australia: https://www.ga.gov.au/
- Product Knowledge Base: see `Opt-Mining - Product Knowledge Base.md`
