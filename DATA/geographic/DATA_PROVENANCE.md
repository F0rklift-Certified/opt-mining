# Data Provenance — Geographic & Environmental Datasets (Task 4)

One section per dataset sampled into this directory. Retrieval parameters, byte
counts and UTC timestamps for every file are in `metadata/download_manifest.json`;
endpoint probes (including sources that refuse scripted access) are in
`metadata/source_register.csv`. Format follows `DATA/wind-resource/DATA_PROVENANCE.md`
so Task 5 can consolidate.

Common to all samples: retrieved 2026-08-20 by the scripts in `scripts/geo_*.py`;
no authentication, registration or API key was required for anything sampled.
Committed vector samples requested with an explicit `outSR=4326`; national-extent
vectors carry a recorded ~50 m server-side generalisation (`maxAllowableOffset=0.0005°`)
to stay under the 10 MB commit guardrail — window extracts are full resolution.

---

## 1. ABS ASGS Edition 3 (2021) boundaries — STE, AUS, LGA, UCL

| Field | Value |
|-------|-------|
| **Name** | Australian Statistical Geography Standard (ASGS) Edition 3, 2021 |
| **Publisher** | Australian Bureau of Statistics |
| **Access endpoint** | `https://geo.abs.gov.au/arcgis/rest/services/ASGS2021/<layer>/FeatureServer/0`, `f=geojson` |
| **Layers sampled** | STE (states, national), AUS (outline, national), LGA (window), UCL (window); SA2 probed only |
| **Temporal coverage** | Static boundary edition, current from 2021 |
| **Native CRS / datum** | ASGS Ed. 3 boundaries are GDA2020-based; the ArcGIS service source SR is EPSG:3857 (Web Mercator) and returns that unless `outSR` is explicit |
| **Units** | `area_albers_sqkm` in km² (ABS-computed Albers area) |
| **Licence** | CC BY 4.0 — attribution: Australian Bureau of Statistics |
| **Method** | Paged FeatureServer queries via `scripts/geo_fetch_vectors.py`; "Outside Australia" null-geometry row filtered from STE |
| **Assumptions** | The served `area_albers_sqkm` is authoritative; verified by recomputation in EPSG:3577 to −0.38 % (the gap is the recorded ~50 m generalisation trimming coastline) |
| **Limitations** | National files are generalised (~50 m) — do not reuse for sub-100 m work; external territories included in STE extent |

## 2. Derived: NEM region geometries

| Field | Value |
|-------|-------|
| **Name** | `derived/nem_regions_asgs2021_national.geojson` — **DERIVED, NOT AUTHORITATIVE** |
| **Derivation** | Re-grouping of ABS STE polygons by `scripts/geo_fetch_vectors.py::derive_nem_regions()`: NSW+ACT→NSW1, VIC→VIC1, QLD→QLD1, SA→SA1, TAS→TAS1; WA, NT, Other Territories excluded (not in the NEM) |
| **Why derived** | AEMO publishes NEM region maps only — no public GIS layer exists (source register) |
| **Geometry note** | Member-state polygons collected into one MultiPolygon per region without geometric dissolve; identical behaviour for point-in-polygon and rasterisation, honestly labelled as re-grouped ABS geometry |
| **Licence** | Inherits CC BY 4.0 from ABS |
| **Limitations** | Regions inherit the ~50 m generalisation; the NSW1=NSW+ACT convention must be restated wherever regions are used |

## 3. CAPAD 2024 — terrestrial protected areas

| Field | Value |
|-------|-------|
| **Name** | Collaborative Australian Protected Areas Database (CAPAD) 2024, terrestrial |
| **Publisher** | Department of Climate Change, Energy, the Environment and Water (DCCEEW) |
| **Access endpoint** | `https://gis.environment.gov.au/gispubmap/rest/services/ogc_services/CAPAD/FeatureServer/0` (layer 1 = marine, probed only), `f=geojson` |
| **Samples** | NSW statewide (1,018 features, ~50 m generalisation recorded) + full-resolution study-window extract (61 features) |
| **Temporal coverage** | Biennial snapshot, 2024 edition — recently gazetted reserves may lag up to two years |
| **Native CRS** | EPSG:4283 (GDA94) |
| **Units** | **`GAZ_AREA`/`GIS_AREA` are hectares** (validated: Kosciuszko 688,945 ha = 6,889 km² ≈ gazetted ~6,900 km²); **dates are epoch milliseconds** |
| **Licence** | CC BY 4.0 — attribution: © Commonwealth of Australia (DCCEEW). CAPAD aggregates jurisdictional data; some sensitive site boundaries are generalised by custodians before publication |
| **Method** | Paged FeatureServer queries (`STATE='NSW'` / window envelope) via `scripts/geo_fetch_vectors.py` |
| **Assumptions** | `ENVIRON='T'` marks terrestrial; IUCN field trusted as served (0 nulls in sample) |
| **Limitations** | Reserve names omit type suffixes ("Kosciuszko", not "Kosciuszko National Park"); marine layer not sampled — the analysis grid is terrestrial |

## 4. ABARES NLUM v7.1 — land use, 250 m, ALUM v8, 2020–21

| Field | Value |
|-------|-------|
| **Name** | National Land Use Map v7.1, ALUM Classification v8, 2020–21 |
| **Publisher** | ABARES (Department of Agriculture, Fisheries and Forestry) |
| **Source URL** | `https://www.agriculture.gov.au/sites/default/files/documents/NLUM_v7_1_250m_ALUMV8_2020_21_alb_20260814.zip` (64.2 MB) |
| **Samples** | Study-window clip (884×999 px) kept in **native EPSG:3577** — no resampling; 144-class table machine-extracted from the zip's CSV |
| **Temporal coverage** | 2020–21 land-use year (file published 2026-08-14); underlying state mapping vintages vary and are documented by ABARES |
| **Native CRS** | EPSG:3577 (GDA94 / Australian Albers), 250 m pixels |
| **Units** | Categorical int16 ALUM v8 codes; 0 = "No data/offshore" |
| **Licence** | CC BY 4.0 — attribution: ABARES, National Land Use Map 2020–21 |
| **Method** | Zip downloaded once to gitignored `raw/`; raster opened via `/vsizip/` without extraction; window clipped by `scripts/geo_fetch_rasters.py` with bounds transformed 4326→3577 |
| **Assumptions** | The shipped class table is authoritative (all window codes decode against it — validated) |
| **Limitations** | 250 m cells blur linear features (roads, rivers); the finer 50 m CLUM exists if ever needed. The Albers-vs-geographic split with other rasters is a declared resampling boundary for Task 5 |

## 5. SRTM GL1 / GL3 elevation (OpenTopography mirror)

| Field | Value |
|-------|-------|
| **Name** | NASA SRTM GL1 (1 arc-second, ~30 m) and GL3 (3 arc-second, ~90 m) |
| **Publisher** | NASA/USGS; mirrored by OpenTopography (S3, public) |
| **Source URL** | `https://opentopography.s3.sdsc.edu/raster/SRTM_GL{1,3}/SRTM_GL{1,3}_srtm.vrt` |
| **Samples** | GL3 study-window clip (2400×2400 px, 5.9 MB); GL1 0.5° sub-window containing both Task 1 wind farms (1800×1800 px, 2.5 MB). National mosaics never downloaded — windowed `/vsicurl/` reads only |
| **Why not Geoscience Australia** | GA's ArcGIS services return HTTP 403 to scripted clients (probe recorded); ELVIS is interactive-only. SRTM is the same lineage GA's 1-second DEM suite derives from, without GA's smoothing (DEM-S) |
| **Temporal coverage** | Single epoch — SRTM mission, February 2000 |
| **Native CRS** | EPSG:4326, int16 metres above sea level |
| **NoData** | **Inconsistent across the family**: GL3 mosaic declares 0 (conflates sea level); GL1 declares −32768. Both windows measured 0 % nodata (inland) |
| **Licence** | US public domain; OpenTopography requests acknowledgment: "SRTM data hosted by OpenTopography, https://opentopography.org/" |
| **Method** | `scripts/geo_fetch_rasters.py`; validation: Ben Lomond-band window max (1,512 m), Armidale 977 m, Glen Innes 1,071 m, GL1-vs-GL3 coincident mean abs diff 0.9 m over 81 points |
| **Limitations** | Unsmoothed — slope from GL1 runs ~+1.3° hot vs GL3 at the same footprint (see `metadata/slope_derivation.md`); coastal use requires the land mask, never the nodata value |

## 6. Derived: slope and TRI rasters

| Field | Value |
|-------|-------|
| **Name** | `elevation/srtm-*_slope-horn_*.tif`, `elevation/srtm-gl1_tri_30m_glen-innes.tif` — **DERIVED** |
| **Derivation** | `scripts/geo_derive_slope.py`: Horn 3×3 slope (degrees) with per-row metre spacing (111,132 m/° N–S; 111,320·cos(lat) m/° E–W); Riley TRI (metres) |
| **Storage** | int16 with scale factors declared in the GeoTIFF (slope ×0.01°, TRI ×0.1 m); quantisation ≪ method error |
| **Purpose** | Task 1 hand-off: replaces the Atlas's inaccessible RIX/elevation layers; evidence for Task 5's aggregation-statistic decision |
| **Limitations** | Inherits SRTM noise (bounded in `metadata/slope_derivation.md`); edge pixels use replicated padding |

## 7. Natural Earth 1:50m land

| Field | Value |
|-------|-------|
| **Name** | Natural Earth `ne_50m_land` (Australia-region landmasses, 56 features kept by bbox filter) |
| **Publisher** | Natural Earth (community, hosted on GitHub) |
| **Source URL** | `https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_land.geojson` |
| **Licence** | Public domain |
| **Purpose** | This is the OptMining prototype's land-mask source — sampled to assess it against the ABS outline (`metadata/landmask_assessment.md`); **assessment outcome: prefer the ABS outline** (21 of its 28 false-land cells carry top-decile wind) |
| **Limitations** | 1:50m generalisation smooths the coastline by kilometres in places; retained for reference, not recommended as the production mask |

---

## Scope and limitations (directory-wide)

1. Samples cover the Task 1 study window (New England REZ) plus national small
   vectors; nothing here demonstrates national-scale processing cost.
2. The committed national vectors are generalised (~50 m, recorded per file in the
   manifest). Re-fetch without `maxAllowableOffset` for finer work.
3. NEM regions, slope and TRI are derived files — regenerate from source rather
   than treating them as custodial data.
4. CRS landscape (GDA94 / GDA2020 / WGS84 / Albers) is documented as evidence for
   Task 5 to ratify the storage-vs-compute CRS split (ADR-0002); nothing in this
   directory re-decides it.
