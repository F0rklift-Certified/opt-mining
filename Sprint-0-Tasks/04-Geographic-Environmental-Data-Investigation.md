# Task 4 — Geographic & Environmental Data Investigation

**Sprint:** 0 (Week 1)
**Assignee:** Pouya Mousavi
**Status:** Complete
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

This task also owns three hand-offs assigned by Task 1 (`01-Wind-Resource-Data-Investigation.md` §8–§9): the coastline/land mask (high severity — Atlas ocean pixels carry real wind values), slope and ruggedness derivation (the Atlas's own terrain layers return HTTP 403), and proof that area computations run in a projected equal-area CRS.

All samples reuse Task 1's study window — the New England REZ, `150.0, -31.5, 152.0, -29.5` (W, S, E, N in EPSG:4326) — so Task 5 can overlay wind, infrastructure and geographic layers on the same ground.

---

## 3. Investigation Checklist

### A. Administrative Boundaries
- [x] Identify a dataset of Australian state and territory boundaries (polygons) — **ABS ASGS 2021 STE layer**, 10 features served (9 kept after dropping the null-geometry "Outside Australia" row); see §7d
- [x] Check whether NEM region boundaries are available as spatial data — **No.** AEMO publishes maps only; NEM regions were **derived** from STE polygons (NSW+ACT → NSW1; WA/NT/Other Territories excluded) into `derived/nem_regions_asgs2021_national.geojson`, flagged derived-not-authoritative
- [x] Identify Local Government Area (LGA) boundaries if available — **ABS ASGS 2021 LGA layer**, 566 features nationally; 12 intersect the study window (sampled)
- [x] Record format, CRS, and licence for each — see `metadata/source_register.csv` and §7d
- [x] Note the datum — GDA94 vs GDA2020 — ASGS 2021 (Edition 3) digital boundaries are published on **GDA2020**; the ArcGIS service *stores* them in Web Mercator (EPSG:3857) and silently returns that unless `outSR` is passed explicitly (§8)

### B. Elevation / Digital Elevation Model (DEM)
- [x] Identify the national DEM from Geoscience Australia (SRTM-derived, ~30m or ~1 arc-second) — identified (GA SRTM-derived 1s DEM suite: DEM/DEM-S/DEM-H), but **GA's ArcGIS services return HTTP 403 to scripted clients** (probe recorded in the source register); the interactive ELVIS portal works for humans only. Sampling used the same SRTM lineage via OpenTopography's public S3 mirror (GL1/GL3), which supports `/vsicurl/` windowed reads
- [x] Determine available resolutions — 1 arc-second (~30 m, GL1), 3 arc-second (~90 m, GL3) sampled; GA also lists a 9-second legacy product (register row)
- [x] Check file format — GeoTIFF tiles behind a VRT mosaic index (OpenTopography); GA products are ESRI Grid/GeoTIFF
- [x] Determine file size for national coverage — national mosaics are tens of GB; never downloaded. Windowed reads transferred only the study clips: GL3 full window 5.9 MB, GL1 sub-window 2.5 MB (§5)
- [x] Assess whether slope can be derived from the DEM or is provided pre-computed — **both**: a pre-computed national slope grid exists (CSIRO, derived from GA DEM-S, registration required — register row), and slope was **derived here** with Horn's method (§8, `metadata/slope_derivation.md`)
- [x] Check whether a coarser version exists that is more manageable for screening — **yes, GL3 (~90 m)**; Evidence 1 in `slope_derivation.md` quantifies what coarsening costs (§9)

### C. Protected Areas & National Parks
- [x] Identify the Collaborative Australian Protected Areas Database (CAPAD) or equivalent — **CAPAD 2024** via DCCEEW's ArcGIS FeatureServer; 14,492 terrestrial polygons nationally, 1,018 in NSW (sampled)
- [x] Determine whether data includes IUCN categories — **yes**, `IUCN` field, 0 nulls in the NSW sample (categories incl. Ia, II; Kosciuszko validates as II)
- [x] Check whether marine vs terrestrial protected areas are distinguished — **yes**: separate layers (terrestrial layer 0 = 14,492 features; marine layer 1 = 5,337 features, register row only), plus an `ENVIRON` field (`T` throughout the NSW terrestrial sample)
- [x] Record format, CRS, and licence — ArcGIS REST (`f=geojson` works), native EPSG:4283 (GDA94), CC BY 4.0; see register
- [x] Confirm that boundaries are provided as polygons (for spatial exclusion) — **yes**: NSW sample is 593 MultiPolygon + 425 Polygon features

### D. Land Use
- [x] Identify the Australian Land Use and Management (ALUM) classification dataset — **ABARES NLUM v7.1, 250 m, ALUM v8 classes** (2020–21 vintage sampled; 2015–16 also published). The finer 50 m CLUM (Dec 2023 v2) exists and is registered but was deliberately not sampled: 250 m is already 20× finer than the ~5 km analysis cell at 1/25th the volume
- [x] Determine spatial resolution and format — 250 m GeoTIFF (zipped, 64.2 MB national), native **EPSG:3577** (GDA94 Australian Albers)
- [x] Check whether categories distinguish agriculture, forestry, urban, conservation, mining, etc. — **yes**: 144-class table shipped inside the zip (machine-extracted to `landuse/abares_alumv8_class_table.csv`) with tertiary/secondary/primary hierarchy; the study window spans conservation (1.1.x), grazing (2.1/3.2), cropping (3.3.x), urban (5.4.x), mining (5.8.x) and water (6.x) classes
- [x] Assess whether land use data can identify clearly unsuitable areas (dense urban, water bodies) — **yes**: primary class 5 (Intensive uses) and class 6 (Water) map directly to exclusions; the window even resolves class 5.6.3 "Wind electricity generation" over the existing wind farms
- [x] Record vintage — 2020–21 (NLUM v7.1, published 2026-08-14 per file name); underlying state mapping dates vary and are documented by ABARES

### E. Urban Areas & Population Centres
- [x] Identify datasets showing urban extent or population centre boundaries — **ABS ASGS 2021 UCL** (Urban Centres and Localities), 1,837 features nationally, 28 intersect the study window (sampled)
- [x] This may also serve as a proxy for demand allocation (cross-reference with Task 2) — **ABS SA2** (2,473 features, 19 fields) probed and registered as the natural population-weighting join geometry
- [x] Check whether population data at a spatial level (SA1, SA2, mesh block) is available from ABS — SA2 geometry confirmed on the same service; population counts join via ABS census products (Task 2's domain)
- [x] Record format and CRS — same service/format/CRS as the other ASGS layers (§7d)

### F. Roads & Accessibility
- [x] Identify publicly available road network data for Australia — **OSM Australia extract (Geofabrik)**, `australia-latest.osm.pbf`, 958.7 MB (HEAD-probed; secondary priority per this checklist, so registered but not sampled)
- [x] Potential sources — Geofabrik OSM (probed); GA roads exist behind the same 403-to-scripts ArcGIS estate as the DEM
- [x] Determine whether road classification is included — OSM `highway=*` tagging carries classification; not verified on a sample (not sampled)
- [x] Note: this is secondary priority — investigate only if time allows — time-boxed to the register row, as instructed

### G. Coastline & Water Bodies
- [x] Identify a coastline dataset (useful for masking ocean areas from the analysis grid) — two candidates assessed head-to-head (§8, `metadata/landmask_assessment.md`): **Natural Earth 1:50m land** (the prototype's mask) and the **ABS ASGS Australia outline**; DEA Coastlines registered as the higher-fidelity upgrade path
- [x] Check whether major water bodies (lakes, reservoirs) are included — coastline products exclude inland water; **NLUM class 6 (Water)** covers lakes/reservoirs/rivers in-window (6.1.0, 6.2.x, 6.3.x observed), and **DEA Waterbodies** is registered as a dedicated polygon source
- [x] This supports hard exclusion of water/ocean cells — confirmed quantitatively: ocean cells carry mean 7.96 m/s wind vs 5.18 m/s on land, so an unmasked grid ranks offshore first (§9)

### H. Sample Downloads
- [x] Download a manageable sample of each promising dataset — 12 committed samples + 3 derived rasters (§5)
- [x] For large rasters (DEM), download a tile or clip covering one state or a small region — windowed `/vsicurl/` clips only; the one full-file download (NLUM zip, 64.2 MB) lives in gitignored `raw/`
- [x] Store samples in `DATA/geographic/` with clear naming — vectors as `<custodian>_<layer>_<vintage>_<extent>.geojson`, rasters as `<product>_<variable>_<res>_<area>.tif`

---

## 4. Data Sources Investigated

Generated register: `DATA/geographic/metadata/source_register.md` / `.csv` (21 sources probed metadata-only; 20 reachable to scripted clients). Summary:

| Source Name | URL / Endpoint | Format(s) | Licence | Download Available? | Notes |
|-------------|-----|-----------|---------|---------------------|-------|
| ABS ASGS 2021 (STE, AUS, LGA, SA2, UCL) | geo.abs.gov.au ArcGIS REST | GeoJSON via `f=geojson` | CC BY 4.0 | Yes (scripted) | Service source SR is EPSG:3857 — `outSR` must be explicit |
| DCCEEW CAPAD 2024 (terrestrial + marine) | gis.environment.gov.au ArcGIS REST | GeoJSON via `f=geojson`, polygons | CC BY 4.0 | Yes (scripted) | 14,492 terrestrial / 5,337 marine features; native EPSG:4283 |
| ABARES NLUM v7.1 250 m (ALUM v8) | agriculture.gov.au zip | GeoTIFF (zipped) | CC BY 4.0 | Yes (64.2 MB) | Native EPSG:3577; 2020–21 and 2015–16 vintages probed |
| ABARES CLUM 50 m | agriculture.gov.au portal | GeoTIFF/Esri Grid | CC BY 4.0 | Yes (manual) | Registered only — 250 m suffices for a ~5 km grid |
| SRTM GL1/GL3 (OpenTopography S3) | opentopography.s3.sdsc.edu VRT | GeoTIFF tiles + VRT | NASA public domain | Yes (`/vsicurl/` windows) | The working scripted DEM route |
| Geoscience Australia DEM services | services.ga.gov.au | ArcGIS REST | CC BY 4.0 | **No (HTTP 403 to scripts)** | Mirrors Task 1's GWA 403 finding; ELVIS portal is interactive-only |
| CSIRO pre-computed slope (from GA DEM-S) | data.csiro.au | Esri Grid | CC BY | Registration required | Answers "is slope pre-computed?" — yes, but national grid too large for this task |
| Natural Earth 1:50m land | GitHub raw | GeoJSON | Public domain | Yes (529.8 KB) | The prototype's land-mask source; assessed in §8 |
| DEA Coastlines / DEA Waterbodies | data.dea.ga.gov.au S3 | GeoPackage/Shapefile | CC BY 4.0 | Yes | Registered upgrade paths for coastline and inland water |
| OSM Australia (Geofabrik) | download.geofabrik.de | .osm.pbf | ODbL | Yes (958.7 MB) | Roads; secondary priority, not sampled |
| NationalMap / data.gov.au | portals | various | various | n/a | Discovery only; they proxy the custodial services above |
| AEMO (NEM region boundaries) | aemo.com.au | maps only, no GIS layer | — | No | Regions derived from ABS STE instead (§3A) |

---

## 5. Sample Data Downloaded

From `metadata/download_manifest.json` (source URLs, parameters, byte counts and UTC timestamps for every retrieval). Study window `150.0, -31.5, 152.0, -29.5` unless noted.

| File Name | Source | Size | Spatial Coverage | Temporal Coverage | Location in Repo |
|-----------|--------|------|------------------|-------------------|------------------|
| `abs_ste_2021_national.geojson` | ABS ASGS 2021 | 3.6 MB | National (9 features) | 2021 (Ed. 3) | `DATA/geographic/boundaries/` |
| `abs_aus_2021_national.geojson` | ABS ASGS 2021 | 3.3 MB | National outline | 2021 (Ed. 3) | `DATA/geographic/boundaries/` |
| `abs_lga_2021_new-england-rez.geojson` | ABS ASGS 2021 | 6.2 MB | 12 LGAs intersecting window | 2021 (Ed. 3) | `DATA/geographic/boundaries/` |
| `abs_ucl_2021_new-england-rez.geojson` | ABS ASGS 2021 | 640.5 KB | 28 urban centres in window | 2021 (Ed. 3) | `DATA/geographic/urban/` |
| `nem_regions_asgs2021_national.geojson` | derived from STE | 2.1 MB | 5 NEM regions | 2021 basis | `DATA/geographic/derived/` |
| `dcceew_capad-terrestrial_2024_nsw.geojson` | DCCEEW CAPAD | 3.3 MB | NSW (1,018 features) | CAPAD 2024 | `DATA/geographic/protected/` |
| `dcceew_capad-terrestrial_2024_new-england-rez.geojson` | DCCEEW CAPAD | 3.4 MB | 61 features, window, full res | CAPAD 2024 | `DATA/geographic/protected/` |
| `ne_land-50m_australia.geojson` | Natural Earth | 308.6 KB | Australia-region landmasses (56) | NE master | `DATA/geographic/coastline/` |
| `srtm-gl3_elevation_90m_new-england-rez.tif` | SRTM GL3 | 5.9 MB | Study window (2400×2400 px) | SRTM (2000) | `DATA/geographic/elevation/` |
| `srtm-gl1_elevation_30m_glen-innes.tif` | SRTM GL1 | 2.5 MB | 0.5° sub-window with both Task 1 wind farms | SRTM (2000) | `DATA/geographic/elevation/` |
| `abares_nlum-alumv8_2020-21_new-england-rez.tif` | ABARES NLUM | 220.9 KB | Study window (884×999 px, EPSG:3577) | 2020–21 | `DATA/geographic/landuse/` |
| `abares_alumv8_class_table.csv` | shipped in NLUM zip | 19.3 KB | — (144 classes) | ALUM v8 | `DATA/geographic/landuse/` |

Derived terrain rasters (generated by `scripts/geo_derive_slope.py`, stored as scaled int16): `srtm-gl3_slope-horn_90m_new-england-rez.tif` (8.5 MB), `srtm-gl1_slope-horn_30m_glen-innes.tif` (4.8 MB), `srtm-gl1_tri_30m_glen-innes.tif` (3.5 MB), all in `DATA/geographic/elevation/`.

National vector layers carry a recorded ~50 m server-side generalisation (`maxAllowableOffset=0.0005°`) to stay under the 10 MB commit guardrail; window extracts are full-resolution. The only full-file download was the 64.2 MB NLUM zip (gitignored `raw/`); DEM mosaics were read as windows only.

---

## 6. Data Inspection Summary

One generated report per sample in `DATA/geographic/metadata/*_inspection.md` (11 reports). Summary:

| Dataset | Type (Raster/Vector) | Columns/Bands | Row Count / Features / Grid Size | Missing Values / NoData | CRS | Usable? |
|---------|---------------------|---------------|----------------------------------|------------------------|-----|---------|
| ABS STE (national) | Vector | 11 fields | 9 features (8 MultiPolygon, 1 Polygon) | 0 nulls | EPSG:4326 (requested) | Yes |
| ABS AUS outline | Vector | 9 fields | 1 MultiPolygon | 0 nulls | EPSG:4326 (requested) | Yes |
| ABS LGA (window) | Vector | 11 fields | 12 features | 0 nulls | EPSG:4326 (requested) | Yes |
| ABS UCL (window) | Vector | 15 fields | 28 features | 0 nulls | EPSG:4326 (requested) | Yes |
| NEM regions (derived) | Vector | 5 fields | 5 MultiPolygons | 0 nulls | EPSG:4326 | Yes (reference only) |
| CAPAD terrestrial NSW | Vector | 29 fields | 1,018 features (593 MultiPolygon, 425 Polygon) | `NRS_MPA`/`ZONE_TYPE` all-null; `COMMENTS` 991/1018 empty; core fields 0 nulls | EPSG:4326 (requested; native 4283) | Yes |
| CAPAD terrestrial window | Vector | 29 fields | 61 features, full resolution | as above | EPSG:4326 (requested) | Yes |
| Natural Earth land | Vector | 4 fields | 56 landmasses | 0 nulls | EPSG:4326 | Yes (see §8 mask assessment) |
| SRTM GL3 elevation | Raster | 1 band | 2400×2400 px | nodata=0 declared; 0.00% in window | EPSG:4326 | Yes |
| SRTM GL1 elevation | Raster | 1 band | 1800×1800 px | nodata=−32768; 0.00% in window | EPSG:4326 | Yes |
| NLUM ALUM v8 (window) | Raster | 1 band | 884×999 px | nodata=0 ("No data/offshore"); 0.00% in window | EPSG:3577 (native) | Yes |

**For raster data (DEM), also record** (from `srtm-gl3_..._inspection.md` / `srtm-gl1_..._inspection.md`):
- Number of bands: 1
- Pixel size (x, y): GL3 0.000833° × 0.000833° (~90 m); GL1 0.000278° × 0.000278° (~30 m)
- NoData value: GL3 declares **0.0**; GL1 declares **−32768** (inconsistent within the same product family — see §8)
- Data type: int16
- Elevation units: metres above sea level
- Bounds (W, S, E, N): GL3 (149.99958, −31.49958, 151.99958, −29.49958); GL1 (151.24986, −29.99986, 151.74986, −29.49986)
- File size per clip: GL3 5.9 MB; GL1 2.5 MB (deflate-compressed windows; national mosaics never downloaded)
- Window statistics: GL3 min 211 m, median 690 m, mean 722.3 m, max 1,512 m; GL1 min 552 m, mean 958.1 m, max 1,496 m

**For vector data (boundaries, protected areas), also record** (from the inspection reports):
- Geometry type: Polygon / MultiPolygon throughout
- Number of features: STE 9 (national), CAPAD NSW 1,018, CAPAD window 61, LGA window 12, UCL window 28, NE land 56
- Key attribute fields: see §7
- Spatial extent: STE spans (96.817, −43.740, 167.998, −9.142) — external territories included; CAPAD NSW spans to 159.280°E (Lord Howe Island)

---

## 7. Data Dictionary

### 7a. Digital Elevation Model (+ derived terrain)

**Dataset:** SRTM GL1 (1 arc-second) / GL3 (3 arc-second), OpenTopography S3 mirror of the NASA SRTM GL products
**Source:** https://opentopography.s3.sdsc.edu/raster/SRTM_GL1/SRTM_GL1_srtm.vrt (and `SRTM_GL3`)
**Format:** GeoTIFF tiles behind a VRT mosaic; sampled as windowed clips
**CRS:** EPSG:4326
**Spatial Resolution:** ~30 m (GL1) / ~90 m (GL3)
**Units:** Metres above sea level

| Band | Data Type | Units | Description | Value Range (window) | NoData Value |
|------|-----------|-------|-------------|-------------|--------------|
| 1 | int16 | m | Elevation above sea level | 211–1,512 (GL3 window); 552–1,496 (GL1 sub-window) | 0 (GL3 mosaic) / −32768 (GL1 mosaic) |

Derived rasters (this task, `scripts/geo_derive_slope.py`): Horn slope in degrees (int16 × 0.01 scale) and Riley TRI in metres (int16 × 0.1 scale), scale factors declared in the GeoTIFF band metadata.

### 7b. Protected Areas (CAPAD)

**Dataset:** CAPAD 2024 — Terrestrial (DCCEEW)
**Source:** https://gis.environment.gov.au/gispubmap/rest/services/ogc_services/CAPAD/FeatureServer/0 (layer 1 = marine)
**Format:** ArcGIS FeatureServer, sampled as GeoJSON (`f=geojson`)
**CRS:** native EPSG:4283 (GDA94); sampled with explicit `outSR=4326`
**Geometry:** Polygon / MultiPolygon

| Field/Column Name | Data Type | Units | Description | Example Value | Missing Values? |
|-------------------|-----------|-------|-------------|---------------|-----------------|
| NAME | string | — | Reserve name, **without type suffix** | Kosciuszko | 0/1018 |
| TYPE / TYPE_ABBR | string | — | Reserve type | National Park / FLR | 0/1018 |
| IUCN | string | — | IUCN category (Ia–VI, or NA/NAS) | II | 0/1018 |
| STATE | string | — | State/territory | NSW | 0/1018 |
| GAZ_AREA / GIS_AREA | float | **hectares** | Gazetted / GIS-computed area | 688,944.6 (= 6,889 km²) | 0/1018 |
| GAZ_DATE / LATEST_GAZ | int | **epoch milliseconds** | Gazettal dates | 498402000000 | 6/1018 |
| ENVIRON | string | — | T(errestrial)/M(arine) flag | T | 0/1018 |
| GOVERNANCE, AUTHORITY, EPBC, PA_ID, OVERLAP, MGT_PLAN | string | — | Management metadata | G / FC_NSW / State | 0/1018 |
| NRS_MPA, ZONE_TYPE | — | — | Marine-only fields | — | all null in terrestrial sample |

Two facts discovered by failing validation checks, now encoded above: **areas are hectares, not km²**, and names omit the reserve-type suffix.

### 7c. Land Use

**Dataset:** ABARES National Land Use Map (NLUM) v7.1, 250 m, ALUM Classification v8, 2020–21
**Source:** https://www.agriculture.gov.au/abares/aclump (zip: `NLUM_v7_1_250m_ALUMV8_2020_21_alb_20260814.zip`, 64.2 MB)
**Format:** GeoTIFF (single band, categorical)
**CRS:** EPSG:3577 (GDA94 / Australian Albers) — kept native in the sample, no resampling
**Spatial Resolution:** 250 m

| Field/Band | Data Type | Units | Description | Example Value | Missing Values? |
|------------|-----------|-------|-------------|---------------|-----------------|
| Band 1 | int16 | — | ALUM v8 code (tertiary level) | 320 = "3.2.0 Grazing modified pastures" | 0 = "No data/offshore" |
| Class table | CSV | — | 144 classes: Value, TERTV8, SECV8, PRIMV8, national pixel counts | 113 = "1.1.3 National park" | machine-extracted from the zip |

Window composition (from the inspection report): grazing modified pastures 46.5%, grazing native vegetation 13.6%, cereals 12.1%, residual native cover 8.2%, national park 3.5%; urban, mining, water and even "5.6.3 Wind electricity generation" classes resolve in-window.

### 7d. Administrative Boundaries

**Dataset:** ABS ASGS Edition 3 (2021) — STE, AUS, LGA, SA2, UCL layers
**Source:** https://geo.abs.gov.au/arcgis/rest/services/ASGS2021/<layer>/FeatureServer/0
**Format:** ArcGIS FeatureServer, sampled as GeoJSON (`f=geojson`)
**CRS:** service source SR is EPSG:3857 (Web Mercator) — **`outSR` must be passed explicitly**; ASGS Ed. 3 boundaries are GDA2020-based
**Geometry:** Polygon / MultiPolygon

| Field/Column Name | Data Type | Units | Description | Example Value | Missing Values? |
|-------------------|-----------|-------|-------------|---------------|-----------------|
| state_code_2021 | string | — | State code (1=NSW … 8=ACT, 9=Other Territories) | 1 | 0/9 |
| state_name_2021 | string | — | State name | New South Wales | 0/9 |
| area_albers_sqkm | float | km² | ABS-computed Albers area | 800797.6591 | 0/9 |
| asgs_loci_uri_2021 | string | — | Linked-data URI | linked.data.gov.au/dataset/asgsed3/STE/1 | 0/9 |
| lga_code_2021 / lga_name_2021 | string | — | LGA identifiers (LGA layer) | — | 0/12 in window |
| ucl_code_2021 / ucl_name_2021, sos*_2021 | string | — | Urban centre identifiers + Section-of-State (UCL layer) | — | 0/28 in window |

Derived NEM regions (`derived/nem_regions_asgs2021_national.geojson`): `nem_region` (NSW1/VIC1/QLD1/SA1/TAS1), `member_states`, `member_state_codes`, `area_albers_sqkm_sum`, `derivation` note. NSW1 = NSW + ACT; WA, NT and Other Territories are outside the NEM.

---

## 8. Integration Issues Identified

| Issue | Description | Severity (High/Med/Low) | Suggested Resolution | Resolved? |
|-------|-------------|-------------------------|----------------------|-----------|
| Land mask is mandatory | Measured on a 101×81-cell coastal strip: ocean cells average **7.96 m/s** vs **5.18 m/s** on land — an unmasked grid ranks offshore first (Task 1's hand-off, now quantified) | High | Apply a land mask before any ranking; use the ABS outline (below) | Yes — `landmask_assessment.md` |
| Which land mask | The prototype's Natural Earth 1:50m mask disagrees with the ABS outline on only 38/8,181 cells (0.46%), but **21 of its 28 false-land cells beat the P90 wind of real land** — the error concentrates exactly where it damages a shortlist most | Med | Adopt the ABS ASGS outline (same cost to use, ~50 m fidelity); keep DEA Coastlines as the upgrade path | Yes — recommendation in §9 |
| GA services refuse scripts | `services.ga.gov.au` returns HTTP 403 to scripted clients (as GWA did in Task 1); ELVIS is interactive-only | Med | SRTM GL1/GL3 via OpenTopography S3 is the working scripted route (same SRTM lineage as GA's DEM) | Yes — route proven |
| DEM noise vs resolution | GL1(30 m)-derived slope aggregated to 90 m runs **+1.31° hotter on average** (mean abs diff 1.67°, P95 4.52°) than slope computed at 90 m — consistent with GA's advice that unsmoothed 1-second SRTM is noisy for terrain attributes | Med | Use GL3 for screening-scale slope; treat GL1 slope as an upper-bound sensitivity | Evidence in `slope_derivation.md`; decision → Task 5 |
| Aggregation statistic dominates | At a 10° threshold the share of excluded cells is **11.6% (mean) vs 42.1% (p90) vs 85.7% (max)** — the statistic choice moves the outcome more than the threshold | Med | Task 5 must choose and justify the statistic; evidence table provided | Evidence provided; decision → Task 5 |
| Datum landscape | CAPAD native GDA94 (4283); NLUM native GDA94 Albers (3577); ASGS Ed. 3 GDA2020-based, served via a Web-Mercator-sourced service; SRTM/GWA WGS84 (4326). Datum offsets ≤ ~1.8 m — immaterial at 5 km cells but must stay explicit | Med | Follow Task 1 §8 / prototype ADR-0002: **EPSG:4326 for storage, EPSG:3577 for distance/area**; documented here as evidence for Task 5 to ratify, not re-decided | Documented |
| ABS service default SR | The ASGS service *source* SR is EPSG:3857 and queries return Web Mercator unless `outSR` is explicit | Med | Always pass `outSR` (done in `geo_common.query_layer_geojson`) | Yes |
| Area units and fields | CAPAD `GIS_AREA`/`GAZ_AREA` are **hectares**; dates are epoch **milliseconds**; reserve names omit the type suffix — all three discovered by failing validation checks | Med | Encoded in §7b; validation now passes with unit conversion | Yes |
| Projected-CRS areas | Areas must be computed in an equal-area CRS (Task 1 hand-off) | Med | Proven: EPSG:3577 shoelace areas match served values — Kosciuszko +0.00%, NSW −0.38% (the −0.38% is the recorded ~50 m generalisation trimming coastline detail) | Yes — `validation_geographic.md` |
| Inconsistent DEM nodata | GL3 mosaic declares nodata=0 (conflating sea level with voids); GL1 declares −32768 | Low–Med | Inland windows unaffected (0% nodata measured); coastal DEM work must pair the DEM with the land mask, never trust nodata alone | Documented |
| Committed-vector generalisation | National STE/AUS/UCL/CAPAD-NSW carry a recorded ~50 m `maxAllowableOffset` to stay under the 10 MB commit guardrail | Low | Offset recorded per file in the manifest; window extracts kept full-resolution | Yes |
| NEM regions not authoritative | AEMO publishes no GIS layer; regions here are re-grouped ABS state polygons | Low | File flagged derived-not-authoritative; NSW+ACT→NSW1 rule documented | Yes |
| State naming variants | "NSW" (CAPAD) vs "New South Wales" (ABS) vs code "1" (ASGS) | Low | `state_code_2021` is the join key; CAPAD's `STATE` needs a 5-row lookup | Documented |
| Raster CRS split | NLUM is Albers (3577); DEM/wind are geographic (4326) — any cell-level join crosses a resampling boundary | Low | Kept NLUM native in the sample; Task 5 chooses the resampling direction once, explicitly | Documented |

*Also considered:* slope **can** be derived (done here, Horn's method — and a pre-computed CSIRO national slope grid exists behind registration); no single dataset combines all exclusion layers (union CAPAD + NLUM classes 5/6 + land mask in preprocessing); UCL (demographic urban) and NLUM 5.4.x (land-cover urban) overlap but differ — NLUM is the natural primary since it shares the exclusion raster stack; CAPAD is a biennial snapshot, so recently gazetted reserves lag up to two years (acceptable for screening, worth a caveat wherever results are presented).

---

## 9. Key Findings & Recommendations

**Availability.** Every required category has a current, freely licensed, scriptably accessible national dataset: ABS ASGS 2021 (boundaries, urban), DCCEEW CAPAD 2024 (protected areas), ABARES NLUM 250 m ALUM v8 (land use), SRTM GL1/GL3 (elevation). 20 of 21 probed sources are reachable to scripts; the exception is Geoscience Australia's ArcGIS estate (HTTP 403), for which SRTM-via-OpenTopography is the working equivalent.

**Hard exclusions vs suitability penalties** (the categorisation this task owes the platform):

| Layer | Use | Basis |
|---|---|---|
| CAPAD terrestrial polygons | **Hard exclusion** | Product Knowledge Base rule; IUCN categories available if policy later distinguishes them |
| Ocean (land mask: ABS ASGS outline) | **Hard exclusion** | Ocean cells carry mean 7.96 m/s wind vs 5.18 land — unmasked grids rank offshore first |
| NLUM class 6 (Water) | **Hard exclusion** | Lakes/reservoirs/rivers resolve at 250 m in-window |
| NLUM class 5.4.x (urban residential) + UCL polygons | **Hard exclusion** (dense urban) | Two independent views of "urban"; NLUM primary, UCL as cross-check |
| Slope (Horn, from DEM) | **Penalty/threshold** | PKB forbids auto-exclusion; evidence: threshold × statistic table in `slope_derivation.md` |
| TRI (ruggedness) | **Penalty** | Replacement for the Atlas's inaccessible RIX |
| NLUM agricultural/forestry classes | **Penalty (weighting)** | Both operating wind farms sit on class 320 (grazing modified pastures) — grazing land is where wind farms actually get built |
| Distance to roads (OSM) | **Penalty, deferred** | Registered, not sampled; secondary priority |

**Land mask (Task 1's high-severity hand-off).** Recommend the **ABS ASGS 2021 Australia outline** over the prototype's Natural Earth 1:50m mask. By area they disagree on only 0.46% of coastal-strip cells, but 21 of the 28 cells Natural Earth wrongly keeps exceed the P90 wind speed of genuine land — coastline error masquerades as prime sites. The ABS outline costs the same to apply (one GeoJSON, same rasterisation rule) and removes that failure mode. DEA Coastlines is the registered upgrade path if cell size ever drops below ~1 km.

**DEM resolution.** **GL3 (~90 m) is sufficient and preferred for the ~5 km screening grid.** It is 20× finer than the analysis cell, 9× lighter than GL1, and — measured here — *less* noise-biased for slope: GL1-derived slope runs +1.31° hotter after aggregation to the same footprint. Reserve GL1 (or GA's DEM-S once accessible) for later fine-siting work.

**Slope derivation.** Horn's 3×3 method with latitude-corrected spacing, implemented in `scripts/geo_derive_slope.py` with rasterio+numpy alone — no new dependencies. A pre-computed CSIRO slope grid exists (registration required) if a national run later wants to skip derivation. The aggregation statistic (mean/max/p90 per cell) changes exclusion shares by up to 74 percentage points at the same threshold; that choice is Task 5's, with the evidence table ready.

**Unexpectedly unavailable.** (1) GA's own DEM services to scripted clients (403) — worked around; (2) any AEMO NEM-region GIS layer — derived from ABS states instead; (3) GWA terrain layers (known from Task 1) — replaced by this task's derivations.

**CRS.** Native CRSs met here: EPSG:4283 (CAPAD), 3577 (NLUM, DEA), 4326 (SRTM, NE), GDA2020-based ASGS served from a 3857-sourced service. Recommendation unchanged from Task 1/ADR-0002 — **store in EPSG:4326, compute distance/area in EPSG:3577** — now backed by working proof: shoelace areas recomputed in 3577 match custodian-served values (Kosciuszko +0.00%, NSW −0.38%). Task 5 ratifies; nothing found here argues against it. Datum offsets (GDA94 vs GDA2020 vs WGS84, ≤ ~1.8 m) are immaterial at 5 km cells but must remain declared at every boundary.

**Blockers.** None. All acceptance criteria are met with scripted, reproducible retrievals. Two watch-items: CAPAD is a biennial snapshot (recently gazetted reserves lag), and the ~50 m generalisation on committed national vectors must not be forgotten if anyone reuses those files for sub-100 m work (the manifest records it per file).

**Validation.** 23/23 ground-truth checks pass (`metadata/validation_geographic.md`), including the cross-task check that both Task 1 wind farms — real, operating sites — survive every proposed exclusion and penalty layer: on land under both masks, outside all 1,018 NSW protected areas, on agricultural land use, at 4.3°/7.0° derived slope.

---

## 10. Acceptance Criteria

- [x] At least one dataset is identified and documented for each category:
  - [x] Administrative boundaries (state/territory at minimum) — §3A, §4, §7d
  - [x] Elevation / DEM — §3B, §4, §7a
  - [x] Protected areas (for hard exclusion) — §3C, §4, §7b
  - [x] Land use — §3D, §4, §7c
- [x] Secondary datasets are noted if investigated (urban areas, roads, coastline) — §3E–G, §4
- [x] Sample datasets are downloaded and stored in `DATA/geographic/` — §5 (12 samples + 3 derived rasters)
- [x] Each sample has been opened and inspected (geometry type, CRS, resolution, attributes, coverage) — §6 (11 generated inspection reports)
- [x] A data dictionary is completed for each primary dataset — §7a–d
- [x] Integration issues are identified (at minimum: CRS/datum, resolution vs grid, file size management) — §8 (14 issues, several measured rather than assumed)
- [x] Datasets are categorised into "hard exclusion" vs "suitability penalty" use — §9 table
- [x] Findings and recommendations section is written — §9

Additional artefacts beyond the stated criteria: the land-mask adequacy assessment with offshore-leakage quantification, slope/TRI derivation with GL1-vs-GL3 noise evidence, the 0.05°-grid aggregation-sensitivity table, the derived NEM-region layer, the machine-readable source register, and 23 ground-truth validation checks including the cross-task wind-farm survival test (§12).

---

## 11. References & Links

- Geoscience Australia — Elevation: https://www.ga.gov.au/scientific-topics/national-location-information/digital-elevation-data
- CAPAD (Protected Areas): https://www.dcceew.gov.au/environment/land/nrs/science/capad
- CAPAD ArcGIS service: https://gis.environment.gov.au/gispubmap/rest/services/ogc_services/CAPAD/FeatureServer
- ABARES Land Use: https://www.agriculture.gov.au/abares/aclump
- ABS ASGS Boundaries: https://www.abs.gov.au/statistics/standards/australian-statistical-geography-standard-asgs-edition-3
- ABS ASGS ArcGIS services: https://geo.abs.gov.au/arcgis/rest/services/ASGS2021
- OpenTopography SRTM: https://opentopography.org/
- DEA Coastlines / Waterbodies: https://data.dea.ga.gov.au/
- NationalMap: https://nationalmap.gov.au/
- data.gov.au: https://data.gov.au/
- Geofabrik OSM Australia: https://download.geofabrik.de/australia-oceania/australia.html
- Product Knowledge Base: see `Opt-Mining - Product Knowledge Base.md`
- Task 1 hand-offs: `Sprint-0-Tasks/01-Wind-Resource-Data-Investigation.md` §8–§9

---

## 12. Artefacts Produced by This Task

| Path | Contents |
|------|----------|
| `scripts/geo_common.py` | Shared helpers: window constants, ArcGIS paged-GeoJSON queries (explicit `outSR`), atomic writes, GDAL remote-read env |
| `scripts/geo_probe_sources.py` | Metadata-only probe of 21 sources → `source_register.md`/`.csv` |
| `scripts/geo_fetch_vectors.py` | ABS/CAPAD/Natural Earth samples + derived NEM regions → manifest |
| `scripts/geo_fetch_rasters.py` | SRTM windowed clips; NLUM zip → `raw/` → native-CRS clip + class table → manifest |
| `scripts/geo_inspect_samples.py` | One inspection report per sample (11) |
| `scripts/geo_derive_slope.py` | Horn slope + Riley TRI rasters; GL1-vs-GL3 and aggregation evidence → `slope_derivation.md` |
| `scripts/geo_landmask_assessment.py` | NE-vs-ABS mask comparison on a GWA-anchored 0.05° grid with wind leakage → `landmask_assessment.md` |
| `scripts/geo_validate_samples.py` | 23 ground-truth checks incl. EPSG:3577 area proofs and wind-farm survival → `validation_geographic.md` |
| `DATA/geographic/` | Samples (§5), metadata reports, `DATA_PROVENANCE.md` |

Reproduce (from the repo root; requires network access):

```
.venv/bin/python scripts/geo_probe_sources.py
.venv/bin/python scripts/geo_fetch_vectors.py
.venv/bin/python scripts/geo_fetch_rasters.py
.venv/bin/python scripts/geo_inspect_samples.py
.venv/bin/python scripts/geo_derive_slope.py
.venv/bin/python scripts/geo_landmask_assessment.py
.venv/bin/python scripts/geo_validate_samples.py
```

Every figure quoted in this document comes from one of these outputs. None was typed by hand.
