# Task 3 — Electricity Infrastructure Data Investigation

**Sprint:** 0 (Week 1)
**Assignee:** XINHAO WANG
**Status:** Completed

---

## 1. Objective

Publicly available Australian electricity infrastructure datasets were
investigated, documented and sampled — including transmission lines,
substations, connection projects, generators and Renewable Energy Zones (REZs)
— to determine what can be used for the grid/infrastructure accessibility
criterion in the suitability scoring model.

The checklist records the investigation completed for this task. Supporting
evidence is provided in the source register, downloaded samples and inspection
reports under `DATA/infrastructure/`.

---

## 2. Context

The Product Knowledge Base identifies infrastructure accessibility as one of the four core criteria. The platform needs to compute distance and access measures from candidate grid cells to nearby transmission lines, substations, connection points, and existing generators.

Infrastructure proximity is a key practical constraint for wind farm development — a site with excellent wind resource but no nearby grid connection is far more expensive and risky to develop.

Potential sources include AEMO (network and generation data), Geoscience Australia, state-level network operators, and the Australian Renewable Energy Mapping Infrastructure (AREMI) / NationalMap.

---

## 3. Investigation Checklist

### A. Transmission Lines
- [x] Identify publicly available datasets showing transmission line routes across Australia
- [x] Determine whether data includes voltage levels (e.g. 132kV, 220kV, 275kV, 330kV, 500kV)
- [x] Check whether data is geospatial (line geometries with coordinates) or tabular
- [x] Record format, CRS, and licence/attribution information
- [x] Note spatial completeness — does it cover all states and territories?

### B. Substations & Connection Points
- [x] Identify datasets listing substation locations
- [x] Determine whether coordinates (lat/lon) are provided
- [x] Check whether capacity or voltage information is included
- [x] Identify AEMO's "connection point" data and whether it includes geographic coordinates
- [x] Note what attributes are available (name, region, voltage, capacity, status)

### C. Generators (Existing)
- [x] Identify a public generation register/reference layer
- [x] Determine what generator attributes are available (type, capacity, fuel source, location, status)
- [x] Check whether geographic coordinates are provided for each generator
- [x] Filter for wind generators specifically — these serve as validation data later
- [x] Note whether planned/proposed generators are included alongside operational ones

### D. Renewable Energy Zones (REZs)
- [x] Identify whether REZ boundaries are published as geospatial data (shapefiles, GeoJSON)
- [x] Check AEMO's Integrated System Plan (ISP) documents for REZ definitions
- [x] Determine whether state-level REZ data exists (e.g. NSW REZ maps from EnergyCo)
- [x] Record what attributes are available (name, state, technology focus, capacity target)

### E. General Access & Download
- [x] For each dataset found, determine whether it is freely downloadable
- [x] Record licensing and attribution requirements
- [x] Check whether data is available via AREMI / NationalMap as a consolidated source
- [x] Identify whether any data requires an API or special request

### F. Sample Download
- [x] Download a manageable sample of each promising dataset
- [x] Prioritise datasets that include geographic coordinates or spatial geometries
- [x] Store samples in `DATA/infrastructure/` with clear naming (e.g. `transmission-lines.geojson`, `generators.csv`)

---

## 4. Data Sources Investigated

| Source Name | URL | Format(s) | Licence | Download Available? | Notes |
|-------------|-----|-----------|---------|---------------------|-------|
| AEMO — Generation Information | https://aemo.com.au/energy-systems/electricity/national-electricity-market-nem/nem-forecasting-and-planning/forecasting-and-planning-data/generation-information | XLSX (NEM generation information) | Public AEMO publication | Yes — public XLSX listed; not downloaded because the GA spatial layer was selected as the primary generator reference | Useful for NEM capacity/status context; not used as the primary spatial layer in this task |
| AEMO — Key Connection Information (KCI) | https://www.aemo.com.au/energy-systems/electricity/national-electricity-market-nem/nem-forecasting-and-planning/forecasting-and-planning-data/generation-information | XLSX | Public AEMO publication; connection-specific details may be restricted | Yes — downloaded 2026-08-15 | Includes project/connection identifiers, proponent, plant type, text site description, capacity and forecast completion fields; no latitude/longitude columns in the downloaded workbook; use as planning reference, not spare network capacity |
| AEMO — 2026 Integrated System Plan, indicative REZ boundaries | https://www.aemo.com.au/energy-systems/major-publications/integrated-system-plan-isp/2026-integrated-system-plan-isp | KMZ/GIS data; A3 PDF | Public download; downloaded after browser verification | Yes — downloaded 2026-08-15; 44 Placemark features; indicative planning reference, not a legal boundary |
| AREMI / NationalMap | https://www.nationalmap.gov.au/ | Web catalogue; source-dependent WMS/WFS/ArcGIS/CSV services | Licence and attribution inherited from the contributing custodian | Indirectly — NationalMap provides discovery and visualisation; it normally references the custodian's live service rather than storing a separate copy | Useful for discovering consolidated renewable-energy and infrastructure layers; primary samples in this report were downloaded directly from GA, AEMO and EnergyCo |
| Geoscience Australia — Electricity Infrastructure 2026 | https://services.ga.gov.au/gis/rest/services/Electricity_Infrastructure/MapServer | ArcGIS Feature Service; downloaded as GeoJSON | © Commonwealth of Australia (Geoscience Australia) 2026; safety and completeness disclaimer applies | Yes | National Power Lines, Substations and Major Power Stations; EPSG:7844 |
| NSW EnergyCo — REZ boundary GIS files | https://www.energyco.nsw.gov.au/our-projects/what-is-a-renewable-energy-zone/renewable-energy-zone-locations | Shapefile ZIP | Public NSW Government / EnergyCo download | Yes — New England, Central-West Orana and Hunter-Central Coast samples downloaded 2026-08-18 | Official NSW geographical-area boundaries; native CRS GDA94 geographic (EPSG:4283 convention) |
| | | | | | |

**AREMI / NationalMap note:** NationalMap is a catalogue and visualisation
interface: it normally points to datasets held by the contributing government
agency or service rather than storing a separate copy. The AREMI project
provided a consolidated renewable-energy mapping interface and was completed
in 2021. NationalMap/AREMI was used as a discovery route, and authoritative
samples were downloaded directly from GA, AEMO and EnergyCo.

---

## 5. Sample Data Downloaded

| File Name | Source | Size | Spatial Coverage | Temporal Coverage | Location in Repo / Notes |
|-----------|--------|------|------------------|-------------------|-------------------------|
| `ga_power_lines_2026_australia.geojson` | Geoscience Australia Electricity Infrastructure | 16 MB | Australia, all states and territories | Current service downloaded 2026-08-13 | `DATA/infrastructure/transmission-lines/` |
| `ga_power_lines_2026_nsw.geojson` | Derived from the national GA download | 5.2 MB | New South Wales | Current service downloaded 2026-08-13 | `DATA/infrastructure/transmission-lines/` |
| `ga_substations_2026_australia.geojson` | Geoscience Australia Electricity Infrastructure | 1.4 MB | Australia, all states and territories | Current service downloaded 2026-08-15 | `DATA/infrastructure/substations/` |
| `ga_substations_2026_nsw.geojson` | Derived from the national GA download | 0.5 MB | New South Wales | Current service downloaded 2026-08-15 | `DATA/infrastructure/substations/` |
| `ga_powerstations_2026_australia.geojson` | Geoscience Australia Electricity Infrastructure | 0.4 MB | Australia, all states and territories | Current service downloaded 2026-08-15 | `DATA/infrastructure/generators/` |
| `ga_wind_generators_2026_nsw.geojson` | Derived/filter of GA power stations | 0.1 MB | New South Wales | Current service downloaded 2026-08-15 | `DATA/infrastructure/generators/` |
| `aemo_indicative_rez_boundaries_2026.kmz` | AEMO 2026 ISP | 885 KB | Australia/NEM REZs | 2026 ISP (downloaded 2026-08-15) | 44 Placemark features; 50 polygons across 6 multi-geometries; KML longitude/latitude; indicative planning boundary |
| `aemo_kci_2026.xlsx` | AEMO Generation Information / KCI | 408 KB | NEM connection enquiries/applications | Q2 2026 KCI publication (downloaded 2026-08-15) | 9,560 formatted rows; 2,354 populated records; 1,006 unique AEMO KCI IDs; no latitude/longitude columns in the public file |
| `energyco_new_england_rez_boundary.zip` | NSW EnergyCo | 241 KB | New England REZ | EnergyCo boundary file (downloaded 2026-08-18) | Shapefile components; GDA94 geographic (EPSG:4283 convention) |
| `energyco_central_west_orana_rez_boundary.zip` | NSW EnergyCo | 362 KB | Central-West Orana REZ | EnergyCo boundary file (downloaded 2026-08-18) | Shapefile components; GDA94 geographic (EPSG:4283 convention) |
| `energyco_hunter_central_coast_rez_boundary.zip` | NSW EnergyCo | 328 KB | Hunter-Central Coast REZ | EnergyCo boundary file (downloaded 2026-08-18) | Shapefile components; GDA94 geographic (EPSG:4283 convention) |

---

## 6. Data Inspection Summary

*Open each downloaded sample and record:*

| Dataset | Columns/Variables | Row Count / Feature Count | Missing Values | Coordinate Fields | Units | Geometry Type | Usable? |
|---------|-------------------|--------------------------|----------------|-------------------|-------|---------------|---------|
| GA Power Lines 2026 | 18 attributes including `capacity_kv`, `status`, `state`, `spatial_confidence` | 3,147 national; 957 NSW | Core scoring fields complete; `feature_source_date` missing for 2,653 | Geometry in EPSG:7844 | kV; service length field | LineString | Yes — screening-level proximity |
| GA Substations 2026 | 19 attributes including `latitude`, `longitude`, `voltage_kv`, `status`, `state`, `spatial_confidence` | 1,866 national; 586 NSW | Coordinates complete; voltage missing for 48; feature source date missing for 1,775 | Latitude/longitude plus point geometry in EPSG:7844 | kV | Point | Yes — screening-level proximity |
| GA Major Power Stations 2026 | 22 attributes including fuel/technology, generation capacity and coordinates | 430 national; 87 wind facilities; 16 NSW wind | Coordinates complete; capacity missing for 21; technology missing for 51 | Latitude/longitude plus point geometry in EPSG:7844 | MW | Point | Yes — validation reference |
| AEMO KCI (public file) | Connection/project fields including ID, proponent, plant type, text site location, capacity estimates and forecast completion | 2,354 populated records; 1,006 unique KCI IDs | Site description present for 2,287 records; capacity fields are variably populated | No coordinate columns in the downloaded public workbook | MW; dates | Tabular | Conditional — useful for planned connection/project context, but not direct spatial joining or spare-capacity modelling |

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

**Dataset:** Geoscience Australia Electricity Infrastructure — Power Lines 2026
**Source:** https://services.ga.gov.au/gis/rest/services/Electricity_Infrastructure/MapServer/2
**Format:** ArcGIS Feature Service, downloaded as GeoJSON
**CRS:** EPSG:7844 — GDA2020 geographic coordinates
**Geometry:** LineString

| Field/Column Name | Data Type | Units | Description | Example Value | Missing Values? |
|-------------------|-----------|-------|-------------|---------------|-----------------|
| objectid | integer | — | Service feature identifier | 1 | No |
| feature_name | string | — | Transmission line name/identifier | varies | No |
| capacity_kv | integer | kV | Nominal line voltage | 330 | No |
| status | string | — | Operational status | Operational | No |
| state | string | — | State/territory abbreviation | NSW | No |
| spatial_confidence | integer | — | Source spatial-confidence classification | varies | No |
| attribute_source | string | — | Attribute provenance | varies | No |
| attribute_source_date | datetime | — | Attribute-source date | varies | No |
| feature_source | string | — | Geometry provenance | varies | No |
| feature_source_date | datetime | — | Geometry-source date | varies | Yes — 2,653 of 3,147 |
| globalid | UUID | — | Stable global identifier | varies | No |
| geometry | geometry | — | Transmission line route | LineString | No |

### 7b. Substations & Connection Points

**Dataset:** Geoscience Australia Electricity Infrastructure — Substations 2026
**Source:** https://services.ga.gov.au/gis/rest/services/Electricity_Infrastructure/MapServer/0
**Format:** ArcGIS Feature Service, downloaded as GeoJSON
**CRS:** EPSG:7844 — GDA2020 geographic coordinates
**Geometry:** Point

| Field/Column Name | Data Type | Units | Description | Example Value | Missing Values? |
|---|---|---|---|---|---|
| objectid | integer | — | Service feature identifier | 1 | No |
| feature_name | string | — | Substation name | Mt Emerald | 2 missing nationally |
| status | string | — | Operational status | Operational | No |
| voltage_kv | integer | kV | Nominal substation voltage | 275 | 48 missing nationally |
| locality | string | — | Locality | MUTCHILBA | No |
| state | string | — | State/territory abbreviation | QLD | No |
| spatial_confidence | integer | — | Source spatial-confidence classification | 5 | No |
| latitude | float | degrees | Point latitude | -17.18265519 | No |
| longitude | float | degrees | Point longitude | 145.38182319 | No |
| globalid | UUID | — | Stable global identifier | varies | No |
| geometry | geometry | — | Substation point | Point | No |

**Caveat:** This dataset identifies substation locations and nominal voltage;
it does not provide spare connection capacity. It should support proximity
screening, not a claim that a site can connect to the grid.

### 7c. Generators

**Dataset:** Geoscience Australia Electricity Infrastructure — Major Power Stations 2026
**Source:** https://services.ga.gov.au/gis/rest/services/Electricity_Infrastructure/MapServer/1
**Format:** ArcGIS Feature Service, downloaded as GeoJSON
**CRS:** EPSG:7844 — GDA2020 geographic coordinates
**Geometry:** Point

| Field/Column Name | Data Type | Units | Description | Example Value | Missing Values? |
|---|---|---|---|---|---|
| feature_name | string | — | Power station name | Mokoan Solar Farm | No |
| primary_fuel_type | string | — | Primary fuel category | Wind | 1 missing |
| technology_type | string | — | Generation technology | Turbine - Wind | 51 missing |
| generation_capacity_mw | float | MW | Registered generation capacity | 46 | 21 missing |
| number_of_units | integer | — | Number of generation units | 1 | 114 missing |
| status | string | — | Facility status | Operational | No |
| owner | string | — | Registered owner | varies | 42 missing |
| state | string | — | State/territory abbreviation | VIC | No |
| latitude | float | degrees | Point latitude | -36.49033873 | No |
| longitude | float | degrees | Point longitude | 146.13079262 | No |
| spatial_confidence | integer | — | Source spatial-confidence classification | 5 | No |
| geometry | geometry | — | Power station point | Point | No |

**Wind filter used:** `primary_fuel_type` or `technology_type` contains the
case-insensitive string `wind`. This returns 87 wind-related features nationally
and 16 in NSW. One hybrid `Wind/solar` feature is included and should remain
flagged as hybrid in validation analysis.

### 7d. Renewable Energy Zones

**Dataset:** AEMO Indicative REZ Boundaries 2026
**Source:** https://www.aemo.com.au/energy-systems/major-publications/integrated-system-plan-isp/2026-integrated-system-plan-isp
**Format:** KMZ containing KML
**CRS:** KML longitude/latitude (WGS84 / EPSG:4326 convention)
**Geometry:** Polygon

| Field/Column Name | Data Type | Units | Description | Example Value | Missing Values? |
|-------------------|-----------|-------|-------------|---------------|-----------------|
| KML placemark name | string | — | Indicative zone name/code | N2 New England | No |
| geometry | Polygon/MultiGeometry | — | Indicative REZ boundary | Polygon | No |
| coordinates | longitude/latitude | degrees | KML boundary vertices | 151.2,-32.0 | No |
| publication vintage | date | — | ISP publication vintage | 2026 ISP | No |

**Limitation:** AEMO's REZ boundaries are indicative planning overlays, not
legal cadastral boundaries and not a guarantee of connection capacity. A
state-level boundary source is available from NSW EnergyCo for the declared NSW
REZs. These files are preferable when the analysis is specifically NSW-based,
but their publication vintage and GDA94 CRS must be retained.

### 7d.1. NSW EnergyCo REZ Boundaries

**Source page:** https://www.energyco.nsw.gov.au/our-projects/what-is-a-renewable-energy-zone/renewable-energy-zone-locations
**Downloaded samples:**

- `renewable-energy-zones/energyco-nsw/energyco_new_england_rez_boundary.zip`
- `renewable-energy-zones/energyco-nsw/energyco_central_west_orana_rez_boundary.zip`
- `renewable-energy-zones/energyco-nsw/energyco_hunter_central_coast_rez_boundary.zip`

All three are Shapefile ZIP packages with `.shp`, `.shx`, `.dbf`, `.prj`, `.cpg`,
`.sbn` and `.sbx` components. The `.prj` files identify GDA94 geographic
coordinates (EPSG:4283 convention). EnergyCo describes these as geographical
area boundaries; use them for NSW overlays and keep AEMO's 2026 KMZ as the
national/NEM planning comparison layer.

### 7e. AEMO Connection-Point / KCI Data

**Dataset:** AEMO Key Connection Information (KCI) public datafile, linked from the Generation Information page.
**Source:** https://www.aemo.com.au/energy-systems/electricity/national-electricity-market-nem/nem-forecasting-and-planning/forecasting-and-planning-data/generation-information
**Format:** XLSX (408 KB downloaded from the public file listed as 407.78 KB on 24 July 2026)
**Observed contents:** 9,560 formatted worksheet rows, of which 2,354 contain populated connection records and 1,006 unique AEMO KCI IDs. The public workbook contains text site descriptions but no latitude/longitude columns.
**Important limitation:** AEMO's public file is a connection-project register, not a technical register of spare substation capacity. AEMO states that formal connection enquiries should be directed to the connecting network service provider and that transmission network data may be supplied on request.

| Field/Column Name | Expected content | Use in Task 3 | Limitation |
|---|---|---|---|
| TNSP Connection Enquiry / Application ID | Unique connection identifier | Deduplicate and track projects | Not a physical asset ID |
| Proponent / plant type | Applicant and technology | Planned-generation screening | May change as projects progress |
| Site location description | Text project location | Manual context and possible future geocoding | The downloaded public workbook has no latitude/longitude columns; do not geocode automatically without validation |
| Maximum power generation | Proposed capacity (MW) | Capacity-weighted validation | Not available network headroom |
| Forecast completion date | Expected connection timing | Temporal filtering | Forecast, not guarantee |

---

## 8. Integration Issues Identified

| Issue | Description | Severity (High/Med/Low) | Suggested Resolution | Disposition in Task 3 |
|-------|-------------|-------------------------|----------------------|-----------|
| Mixed CRS | Different datasets may use GDA94 (EPSG:4283) vs GDA2020 (EPSG:7844) vs WGS84 (EPSG:4326) | High | Standardise all to a single CRS during ingestion | Documented; standardisation is a downstream ingestion step |
| Missing coordinates | Some generators or substations may lack lat/lon | Med | Document coverage; geocode from address if critical | Documented; no geocoding was required for the downloaded GA samples |
| Inconsistent region naming | NEM regions (NSW1) vs state names (NSW) vs full names (New South Wales) | Med | Create a mapping/lookup table | Documented; lookup table is a downstream integration step |
| Data currency | Infrastructure data may be outdated (new lines/substations not shown) | Low | Document vintage; accept for screening purposes | Documented and recorded with download dates |
| Multiple sources | Same infrastructure may appear in multiple datasets with different attributes | Low | Choose authoritative source per feature type | Resolved for this investigation by assigning GA/AEMO/EnergyCo primary roles |
| AEMO connection data is not spare capacity | Public KCI identifies connection projects and site information, but not remaining thermal/fault-level capacity at a substation | High | Use GA substations/lines for proximity and request network studies from the relevant NSP/AEMO for feasibility | Documented limitation; technical feasibility is outside Task 3 |
| KCI workbook has no coordinates | The downloaded public KCI file contains site descriptions but no latitude/longitude fields | High | Keep KCI as project-context metadata; use GA geometry for spatial scoring and obtain coordinates from the NSP/AEMO or a validated project source when needed | Documented limitation; no direct spatial join is claimed |
| REZ download access | AEMO 2026 REZ KMZ required browser verification, which was completed successfully | Low | Retain the downloaded KMZ, source URL and publication vintage; add a state statutory boundary only if the project later requires it | Yes |
| NSW REZ source selection | AEMO provides an indicative national planning overlay while EnergyCo provides NSW geographical-area GIS packages | Med | Use EnergyCo for NSW boundary screening and AEMO for national/ISP comparison; retain source-specific vintage and CRS | Yes |
| | | | | |

*Also consider:*
- Are transmission line geometries accurate enough to compute meaningful distance measures?
- Do generator locations represent the actual site or an administrative/connection point?
- Are REZ boundaries official or indicative?
- How will "distance to nearest infrastructure" be calculated — Euclidean or network distance?

---

## 9. Key Findings & Recommendations

The investigation supports a screening-level infrastructure criterion, with a
clear separation between spatial proximity and actual connection feasibility:

- **Best baseline spatial source:** Geoscience Australia Electricity Infrastructure 2026 was selected. It provides national line, substation and major power-station geometries in one CRS (EPSG:7844), with voltage/status fields and complete coordinates in the downloaded samples.
- **Connection-point source:** AEMO's public KCI file is the best source for proposed/active connection projects and text site descriptions, but the downloaded workbook has no coordinates and is not a spare-capacity register. Formal feasibility requires the relevant network service provider and, where needed, an AEMO network-data request.
- **Wind validation:** The GA power-station layer identified 87 wind-related facilities nationally and 16 in NSW. These should be used as validation/reference points, not as a complete turbine inventory.
- **REZs:** AEMO ISP publishes an indicative national GIS overlay, while NSW EnergyCo publishes state-level geographical-area Shapefile packages for New England, Central-West Orana and Hunter-Central Coast. Use the EnergyCo files for NSW-specific screening and AEMO for national/ISP comparison.
- **Recommended scoring measure:** Reproject all layers to an equal-area/equidistant projected CRS for the analysis region, calculate straight-line distance to the nearest line and substation, and report voltage/status filters separately. Do not call this network distance or available capacity.
- **Quality controls:** retain source URL, publication/download date, CRS, spatial-confidence fields and a vintage field; map state/NEM region names to a controlled lookup table; flag indicative coordinates and missing voltage/capacity fields.

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

- [x] At least one dataset is identified and documented for each infrastructure type:
  - [x] Transmission lines
  - [x] Substations or connection points
  - [x] Generators (with wind generators identifiable)
  - [x] Renewable Energy Zones (if available)
- [x] Sample datasets are downloaded and stored in `DATA/infrastructure/`
- [x] Each downloaded sample has been opened and inspected (features, columns, CRS, geometry type, missing values)
- [x] A data dictionary is completed for each primary dataset
- [x] Integration issues are identified (at minimum: CRS differences, missing coordinates, region naming)
- [x] Existing wind farm locations are noted (these become validation data for the full platform)
- [x] Findings and recommendations section is written

---

## 11. References & Links

- AEMO Generation Information: https://aemo.com.au/energy-systems/electricity/national-electricity-market-nem/nem-forecasting-and-planning/forecasting-and-planning-data/generation-information
- AEMO ISP: https://aemo.com.au/energy-systems/major-publications/integrated-system-plan-isp
- NationalMap / AREMI: https://nationalmap.gov.au/
- Geoscience Australia: https://www.ga.gov.au/
- Product Knowledge Base: see `Opt-Mining - Product Knowledge Base.md`
