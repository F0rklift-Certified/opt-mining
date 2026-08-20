# Task 1 — Wind Resource Data Investigation

**Sprint:** 0 (Week 1)
**Assignee:** Pouya Mousavi
**Status:** Complete
**Estimated Effort:** 1–2 days

---

## 1. Objective

Investigate, document and sample the wind resource data available for Australia — primarily from the Global Wind Atlas — to determine what can be used as the wind resource criterion in the suitability scoring model.

---

## 2. Context

The Global Wind Atlas is identified in the Product Knowledge Base as the highest-priority data source. It provides mean wind speed, power density, terrain roughness, orography, and capacity-factor layers. The platform will use this data as an *input* — it is not a prediction target.

Key reference: https://globalwindatlas.info/

> **Correction to the above.** The Knowledge Base's list of layers describes Global Wind Atlas v3. The current release is **v4.0 (June 2025)**, which publishes **RIX (a ruggedness index)** and **site elevation** rather than "roughness" and "orography" — and neither is available through the per-country download route. See §8, issue 3.

---

## 3. Investigation Checklist

### Availability & Access
- [x] Identify what datasets are available on the Global Wind Atlas for Australia
- [x] Determine what variables are provided (wind speed, power density, capacity factor, roughness, orography, etc.)
- [x] Identify available measurement heights (e.g. 10m, 50m, 100m, 150m, 200m)
- [x] Check whether data can be downloaded (bulk download vs. API vs. area selection)
- [x] Determine the download process — is registration required? Are there download limits?
- [x] Record licensing and usage restrictions (attribution requirements, commercial use, redistribution)

### Spatial Properties
- [x] Determine the native spatial resolution (e.g. 250m, 1km)
- [x] Identify the coordinate reference system (CRS) used
- [x] Confirm whether latitude/longitude coordinates are explicitly provided or derived from raster grid
- [x] Check spatial extent — does it cover all of Australia including offshore?

### Format & Structure
- [x] Identify available file formats (GeoTIFF, NetCDF, CSV, shapefile, etc.)
- [x] Document file sizes for Australian coverage
- [x] Determine whether data is provided as raster or vector
- [x] Check if seasonal/monthly breakdowns are available or only annual means

### Sample Download
- [x] Download a manageable sample covering a small area (e.g. one state, or a ~200km x 200km region)
- [x] Try multiple variables if available (wind speed + power density at minimum)
- [x] Record exact download parameters (area, height, variable, format)
- [x] Store samples in `DATA/wind-resource/` with a clear naming convention

---

## 4. Data Sources Investigated

| Source Name | URL | Format(s) | Licence | Download Available? | Notes |
|-------------|-----|-----------|---------|---------------------|-------|
| Global Wind Atlas v4 — country GeoTIFF API | `https://globalwindatlas.info/api/gis/country/AUS/<variable>[/<height>]` | GeoTIFF (float32, tiled, zstd, overviews) | CC BY 4.0 | **Yes** — no registration, no API key, 302-redirects to CDN | **Primary source.** Serves 7 of the 9 v4 layer families. |
| Global Wind Atlas — web application | https://globalwindatlas.info/ | GeoTIFF via interactive download | CC BY 4.0 | Yes — point, custom area, country, or first admin unit | The only route to RIX and elevation for a sub-national area. Not scriptable. |
| DTU Data repository — *Global Wind Atlas 4* | https://data.dtu.dk/articles/dataset/Global_Wind_Atlas_4/28955267 · DOI [10.11583/DTU.28955267](https://doi.org/10.11583/DTU.28955267) | Global GeoTIFF (COG) | CC BY 4.0 | Yes — direct file download | Authoritative metadata, licence and citation. Global files are **6–16 GB each**. Only route to RIX (6.1 GB) and site elevation (8.9 GB). |
| GWA methodology paper (BAMS 2023) | https://doi.org/10.1175/BAMS-D-21-0075.1 | Journal article | — | Open access | Method reference for the technical report. |

**Not pursued.** Bureau of Meteorology station data and MERRA-2 / ERA5 reanalysis were considered as supplementary sources and rejected for Version 1: BoM stations are point measurements at 10 m, too sparse and too low for utility-scale screening; raw reanalysis is 30 km, far coarser than the Atlas, which is itself a downscaled product of ERA5. Neither adds information the Atlas does not already carry. Revisit only if independent validation of the Atlas becomes a requirement.

### 4a. Layer availability — every variable/height combination probed

All 31 combinations were tested with HTTP HEAD by `scripts/probe_gwa_layers.py`; full record in `DATA/wind-resource/metadata/layer_availability.md`. Sizes are for full Australian coverage.

| Variable | Units | Heights available (m) | Per-country API | Australia file size |
|---|---|---|---|---|
| `wind-speed` | m/s | 10, 50, 100, 150, 200 | Yes | 599–684 MB |
| `power-density` | W/m² | 10, 50, 100, 150, 200 | Yes | 640–714 MB |
| `air-density` | kg/m³ | 10, 50, 100, 150, 200 | Yes | 287 MB |
| `combined-Weibull-A` | m/s | 10, 50, 100, 150, 200 | Yes | 595–677 MB |
| `combined-Weibull-k` | — | 10, 50, 100, 150, 200 | Yes | 551–629 MB |
| `capacity-factor_IEC1` / `IEC2` / `IEC3` | ratio | fixed 100 m hub | Yes | 652–657 MB |
| `capacity-factor_offshore` | ratio | fixed 150 m hub | **No — HTTP 403** | global file only |
| `RIX` (ruggedness index) | % | n/a | **No — HTTP 403** | global file only, 6.1 GB |
| `elevation` (site elevation) | m | n/a | **No — HTTP 403** | global file only, 8.9 GB |

No seasonal or monthly breakdown exists in any of these layers. Every layer is a single long-term mean.

---

## 5. Sample Data Downloaded

Study window: **New England Renewable Energy Zone, NSW** — bbox `150.0, -31.5, 152.0, -29.5` (EPSG:4326), 800 x 800 native pixels, ~192 km E–W x ~222 km N–S. Chosen because it is NSW (the Knowledge Base's fallback scope), it contains two operating wind farms for validation, and it overlaps the NSW REZ boundaries sampled in Task 3.

| File Name | Source | Size | Spatial Coverage | Temporal Coverage | Location in Repo |
|-----------|--------|------|------------------|-------------------|------------------|
| `gwa_v4_wind-speed_50m_new-england-rez.tif` | GWA v4 (633 MB remote) | 2.2 MB | New England REZ window | 2008–2017 mean | `DATA/wind-resource/` |
| `gwa_v4_wind-speed_100m_new-england-rez.tif` | GWA v4 (618 MB remote) | 2.2 MB | New England REZ window | 2008–2017 mean | `DATA/wind-resource/` |
| `gwa_v4_wind-speed_150m_new-england-rez.tif` | GWA v4 (610 MB remote) | 2.2 MB | New England REZ window | 2008–2017 mean | `DATA/wind-resource/` |
| `gwa_v4_power-density_100m_new-england-rez.tif` | GWA v4 (649 MB remote) | 2.2 MB | New England REZ window | 2008–2017 mean | `DATA/wind-resource/` |
| `gwa_v4_capacity-factor_IEC2_new-england-rez.tif` | GWA v4 (652 MB remote) | 2.2 MB | New England REZ window | 2008–2017 mean | `DATA/wind-resource/` |

**11 MB retrieved in total, against 3.16 GB if these five layers had been downloaded whole.** The CDN advertises `accept-ranges: bytes` and the rasters are internally tiled with overview pyramids, so `scripts/download_gwa_sample.py` opens each raster through GDAL's `/vsicurl/` driver and reads only the pixel window it needs. No full-country raster was ever stored. This satisfies both the Constitution ("do not download or process more data than the analysis requires") and the Atlas's own access terms, which prohibit using the API for bulk downloads.

Exact retrieval parameters, resolved source URLs, remote byte sizes and pixel windows are recorded in `DATA/wind-resource/metadata/download_manifest.json`.

---

## 6. Data Inspection Summary

Generated by `scripts/inspect_gwa_raster.py`; full records in `DATA/wind-resource/metadata/*_inspection.md`.

| Dataset | Variables | Grid Size | Missing Values | Coordinate Fields | Units | Date/Time Fields | Usable? |
|---------|-----------|-----------|----------------|-------------------|-------|------------------|---------|
| `wind-speed_50m` | 1 band | 800 x 800 | 0.00% | Raster grid (no explicit lat/lon columns) | m/s | None — static mean | Yes |
| `wind-speed_100m` | 1 band | 800 x 800 | 0.00% | Raster grid | m/s | None | Yes |
| `wind-speed_150m` | 1 band | 800 x 800 | 0.00% | Raster grid | m/s | None | Yes |
| `power-density_100m` | 1 band | 800 x 800 | 0.00% | Raster grid | W/m² | None | Yes |
| `capacity-factor_IEC2` | 1 band | 800 x 800 | 0.00% | Raster grid | ratio 0–1 | None | Yes |

Coordinates are **not** stored as fields. Each pixel's position is derived from the affine transform in the GeoTIFF header, which is the normal raster convention and needs no special handling in rasterio.

**For raster data specifically:**

| Property | Sample clips | Full Australia raster |
|---|---|---|
| Number of bands | 1 | 1 |
| Pixel size (x, y) | 0.0025° x 0.0025° (~240 m E–W x ~278 m N–S at lat −30.5) | 0.0025° x 0.0025° |
| NoData value | `nan` | `nan` |
| Data type | float32 | float32 |
| CRS (EPSG code) | EPSG:4326 | EPSG:4326 |
| Bounds (xmin, ymin, xmax, ymax) | 149.99875, −31.49875, 151.99875, −29.49875 | 109.21125, −54.79625, 163.21375, −8.86125 |
| Grid size | 800 x 800 | 21,601 x 18,374 |
| Internal tiling | 256x256 (as written by us) | 512x512 |
| Compression | deflate (ours) | zstd |
| Overviews | none (ours) | 2, 4, 8, 16, 32, 64 |

**Value distributions in the study window:**

| Layer | Min | p10 | Median | Mean | p90 | Max |
|---|---|---|---|---|---|---|
| Wind speed @ 50 m (m/s) | 0.234 | 3.280 | 4.323 | 4.572 | 6.291 | 12.433 |
| Wind speed @ 100 m (m/s) | 0.968 | 4.333 | 5.344 | 5.574 | 7.228 | 10.964 |
| Wind speed @ 150 m (m/s) | 1.900 | 4.922 | 6.035 | 6.213 | 7.847 | 10.624 |
| Power density @ 100 m (W/m²) | 1.645 | 107.3 | 181.3 | 222.6 | 394.6 | 1373.8 |
| Capacity factor IEC2 (ratio) | 0.001 | 0.134 | 0.213 | 0.234 | 0.367 | 0.618 |

**Two observations worth recording:**

1. **Mean shear across the window is +1.00 m/s from 50 m to 100 m, and +0.64 m/s from 100 m to 150 m.** Height selection materially changes the resource picture; it is not a cosmetic choice.
2. **0.51% of pixels show *lower* wind speed at 100 m than at 50 m** (and 0.12% at 150 m vs 100 m), concentrated on exposed ridge crests where flow speed-up peaks near the surface. This is physically plausible rather than a data error, but it means the layers are not monotonic in height and any code assuming "taller is always faster" will be wrong on ~1 pixel in 200.

**No embedded metadata.** The only GeoTIFF tag present is `AREA_OR_POINT=Area`. There are no band descriptions, no units, no version string. Units are known only from the publisher's dataset description and must be asserted in code, not read from the file.

---

## 7. Data Dictionary

**Dataset:** Global Wind Atlas 4 — Australia country rasters
**Source:** https://globalwindatlas.info/ · DOI [10.11583/DTU.28955267](https://doi.org/10.11583/DTU.28955267)
**Format:** GeoTIFF, single band, float32, tiled, zstd-compressed, with overview pyramids
**CRS:** EPSG:4326 (WGS 84)
**Temporal Range:** Long-term mean derived from ERA5 reanalysis 2008–2017 (10 years); dataset version released June 2025
**Spatial Resolution:** 0.0025° — ~278 m N–S everywhere; ~274 m E–W at 10°S falling to ~200 m at 44°S (~241 m in the study window)

Each variable is a separate file with one band. There are no multi-band or multi-variable files.

| Layer (band 1) | Data Type | Units | Description | Example Value | Missing Values? |
|-------------------|-----------|-------|-------------|---------------|-----------------|
| `wind-speed_<h>m` | float32 | m/s | 10-year mean wind speed at height `<h>` ∈ {10, 50, 100, 150, 200} | 5.344 (window median @ 100 m) | `nan` outside Australian territory; 0% within the study window |
| `power-density_<h>m` | float32 | W/m² | 10-year mean wind power density; relates to the cube of wind speed, so it separates sites that share a mean speed but differ in distribution | 181.3 (window median @ 100 m) | `nan` outside territory |
| `capacity-factor_IEC1` | float32 | ratio 0–1 | Modelled capacity factor, IEC class 1 turbine, 100 m hub, 117 m rotor | — | `nan` outside territory |
| `capacity-factor_IEC2` | float32 | ratio 0–1 | Modelled capacity factor, IEC class 2 turbine, 100 m hub, 136 m rotor | 0.213 (window median) | `nan` outside territory |
| `capacity-factor_IEC3` | float32 | ratio 0–1 | Modelled capacity factor, IEC class 3 turbine, 100 m hub, 150 m rotor | — | `nan` outside territory |
| `air-density_<h>m` | float32 | kg/m³ | Modelled air density at height `<h>` | — | `nan` outside territory |
| `combined-Weibull-A_<h>m` | float32 | m/s | All-sector combined Weibull scale parameter | — | `nan` outside territory |
| `combined-Weibull-k_<h>m` | float32 | dimensionless | All-sector combined Weibull shape parameter | — | `nan` outside territory |

Capacity factor converts to an indicative annual energy production as `AEP = P_rated × CF × 8760 h`. **This is an indicative comparison figure only** — the Constitution forbids presenting it as a project yield or a bankable number.

The all-sector Weibull parameters carry a publisher caveat: where wind arrives from multiple directions, the combined distribution can differ substantially from the individual directional distributions.

---

## 8. Integration Issues Identified

| # | Issue | Description | Severity | Suggested Resolution | Resolved? |
|---|-------|-------------|----------|----------------------|-----------|
| 1 | **Ocean pixels carry real values** | The raster is masked to Australian territory including marine areas, not to land. Open ocean off NSW reads 8.62 m/s and Bass Strait 8.68 m/s, against a New England REZ mean of 5.57 m/s. Ranking cells on wind resource without a land mask puts the entire shortlist offshore. | **High** | A coastline/land mask is a mandatory hard exclusion before any scoring. Owned by Task 4. | No |
| 2 | **250 m → 5 km aggregation discards the ridge signal** | Twenty native pixels per side collapse into one analysis cell. The mean gap between a cell's best pixel and its 400-pixel average is 1.28 m/s. Worse, the two known wind farms disagree about which statistic favours them: White Rock ranks p80 under `mean` and p95 under `max`, while Sapphire ranks p89 under `mean` and only p82 under `max`. | **High** | Decision belongs to Task 5. Evidence: `DATA/wind-resource/metadata/aggregation_sensitivity.md`. Whichever statistic is chosen must be recorded in the scenario configuration and stated wherever results are shown. | No |
| 3 | **Terrain layers unavailable per country** | The Knowledge Base expects roughness and orography. GWA v4 publishes RIX and site elevation instead, and the per-country API returns HTTP 403 for both — they exist only as 6.1 GB and 8.9 GB global rasters, or through the web app's non-scriptable interactive download. | **Med** | Source terrain from the Geoscience Australia DEM (Task 4) rather than the Atlas. Flag to Task 4 that it now owns slope *and* ruggedness. | No |
| 4 | **File size at national scale** | Five layers at full Australian coverage is 3.16 GB; the global RIX and elevation rasters are 6–16 GB each. | **Med** | Already mitigated: read windows over `/vsicurl/` rather than downloading. This scales to national coverage tile-by-tile without ever storing a full raster. | Yes — approach proven |
| 5 | **Access terms prohibit bulk download** | "This API service is not to be used for bulk downloads of all countries or datasets." | **Med** | Current usage (11 MB) is far inside the limit. Before any national-scale run across many layers, contact the GWA team or use the DTU repository files. Do not simply scale the script up. | No — flagged for Sprint 1 |
| 6 | **No embedded units or version metadata** | Files carry only `AREA_OR_POINT=Area`. Nothing in the file states m/s, W/m², or v4. | **Med** | Units, version and licence are asserted in `DATA/wind-resource/DATA_PROVENANCE.md` and must be attached at ingestion. Never infer units from a filename. | Partly — recorded, not yet enforced in code |
| 7 | **Pixels are square in degrees, not in metres** | 0.0025° is ~278 m N–S everywhere, but E–W it runs from ~274 m at Cape York (−10°) through ~241 m at the study window (−30°) to ~200 m in southern Tasmania (−44°). The nominal "250 m" is true at no Australian latitude, and the pixel aspect ratio changes by 27% across the continent. | **Low** | Make the assumption explicit at every resampling boundary, per the Constitution. Consider an equal-area CRS for any area-weighted calculation. | No |
| 8 | **Temporal mismatch with demand data** | The Atlas is a 2008–2017 climatology; Task 2's AEMO demand sample is 2025–2026. | **Low** | Unavoidable and acceptable for screening — both are long-run indicators. Must be stated wherever the two criteria are combined. | No — document, do not fix |
| 9 | **Height layers are not monotonic** | 0.51% of pixels have lower speed at 100 m than at 50 m, on exposed ridge crests. | **Low** | Do not assume taller is always faster in validation or interpolation code. | No |

**On CRS alignment specifically:** the Atlas is EPSG:4326 (WGS 84), unambiguously declared in the file. Task 3's Geoscience Australia infrastructure data declares **EPSG:7844 (GDA2020)** — checked directly in `ga_wind_generators_2026_nsw.geojson`, not assumed. The datum offset between GDA2020 and WGS 84 is on the order of a metre or two, which is negligible against a 241 m pixel and irrelevant against a 5 km analysis cell. It still must be declared and transformed explicitly rather than silently ignored, per the Constitution — the risk here is not the error size, it is an undocumented assumption that later becomes invisible.

Recommendation to Task 5: **EPSG:4326 for storage, EPSG:3577 (GDA94 / Australian Albers, equal-area) for every distance and area calculation.** The largest dataset in the platform is already in 4326 and reprojecting a 600 MB raster to suit a few thousand vector points is the wrong trade; but degrees are not a unit of length, so distance to transmission (Task 3) and area-weighted exclusions (Task 4) must be computed in a projected CRS. This is not a new proposal — the OptMining prototype already adopted exactly this split in ADR-0002 and enforces it with a runtime `assert_crs` check (§12). Task 5 should ratify it rather than re-litigate it.

**On grid alignment:** the Atlas grid origin is 109.21125 E, −8.86125 S with a 0.0025° step, so a 0.05° analysis cell is exactly 20 native pixels. Anchoring the analysis grid on that origin makes every cell a clean 20 × 20 block.

The existing OptMining prototype (see §12) anchors its grid at lon 112.9 / lat −43.7 instead. Every edge of that grid sits exactly half a native pixel off the Atlas lattice, which puts **1 native pixel column in 20 (5.00%) exactly on a cell boundary**. That prototype assigns pixels by centre with `floor()`, so this does not cause interpolation — the tie breaks deterministically toward one side — but each cell then systematically claims its western and southern boundary column and not its eastern and northern one, and the outcome depends on the floating-point representation of the coordinate arithmetic. It is a small, silent asymmetry of exactly the kind the Constitution asks us to make explicit.

**Recommend Task 5 anchor the grid on the Atlas origin** — for the prototype's bounds that means shifting lon_min from 112.9 to 112.91125 and lat likewise, a move of ~1.2 km that removes the tie entirely and costs nothing.

---

## 9. Key Findings & Recommendations

**The Global Wind Atlas is usable, freely licensed, and better quality than the brief assumed.** It is CC BY 4.0, needs no registration, and its structure (tiled, overviewed, cloud-optimised) makes national-scale work tractable without national-scale storage. It should remain the wind resource criterion for Version 1.

**Which variables are most useful.** Use **wind speed** and **power density** as the two primary features, and carry **capacity factor IEC2** as the interpretable presentation layer.

- Wind speed alone is insufficient. Power density relates to the *cube* of speed, so two cells with the same mean speed can differ materially in extractable energy depending on their distribution. Carrying both costs one extra raster read and separates sites that a mean-speed ranking would tie.
- Capacity factor is the layer a planner reads without translation, and it embeds a real power curve. But it is modelled for one specific turbine at a fixed 100 m hub, so it belongs in the explanation and the map, not as the sole scoring input.
- The Weibull A/k parameters are not needed for Version 1. They would matter for energy-yield modelling, which is explicitly out of scope.

**Which measurement height.** Use **100 m as the primary height**, with **150 m carried as a sensitivity layer**.

The reasoning is consistency rather than realism: 100 m is the only height at which wind speed, power density and the capacity-factor layers all describe the same hub, so the three features stay internally coherent. At 150 m the capacity-factor layers would no longer correspond to the wind-speed layer.

This deserves scrutiny, because it is a compromise. Mean wind speed in the study window is 0.64 m/s higher at 150 m than at 100 m, and modern utility-scale turbines are trending taller than the 100 m the Atlas fixes its capacity factors to. **Open item for the team:** cross-reference the AEMO generator register (Task 3) for the actual hub heights of recently committed Australian wind projects. If they cluster well above 100 m, the primary height should move to 150 m and the capacity-factor layers should be demoted to indicative-only. This is a data question with a data answer, and it should not be settled by assumption.

**Recommended download strategy for the full project: do not download.** Read windows over `/vsicurl/` from the country rasters, tile by tile, exactly as `scripts/download_gwa_sample.py` already does. This scales to national coverage without ever storing a 600 MB file, and it keeps the pipeline reproducible from a URL rather than from a binary blob in the repository. Two constraints on this: the Atlas's terms prohibit bulk API use, so a national run across many layers needs a conversation with the GWA team or a switch to the DTU repository files; and network reads should be cached during development so a pipeline re-run is not a re-download.

**Validation against reality — the Atlas passes.** Both operating wind farms in the study window sit in the top decile of every layer at their recorded location, and at or near the window maximum across their surrounding neighbourhood:

| Wind farm | Wind speed @ 100 m | Percentile | Neighbourhood max | Percentile |
|---|---|---|---|---|
| White Rock Wind Farm | 7.384 m/s | p93 | 8.763 m/s | p100 |
| Sapphire Wind Farm | 7.314 m/s | p91 | 7.976 m/s | p99 |

The places developers actually built are the places the Atlas rates highest. That confirms the raster is correctly oriented, georeferenced and scaled. It is a check on the *data*, not on any model: two wind farms is a small sample, and the window was chosen precisely because it is known-good wind country, so this cannot measure how well the Atlas discriminates good sites from bad ones. Full record in `DATA/wind-resource/metadata/validation_wind_farms.md`.

**Blockers and concerns, in order of severity:**

1. **The ocean problem is the real risk in this dataset.** The Atlas's strongest Australian wind speeds are over water, and marine pixels are indistinguishable from land pixels in the data. Only 48.4% of the Australian bounding box carries data, and that 48.4% is territory *including marine areas*, not land: a decimated read of the whole raster gives a mean of 7.17 m/s and a maximum of 11.84 m/s, against 5.57 m/s mean over the land-dominated New England REZ window. Spot checks confirm it directly — open Tasman Sea reads 8.62 m/s and Bass Strait 8.68 m/s, both above the 90th percentile of the New England window. Without a land mask, wind resource scoring produces a shortlist of open sea. Task 4 must deliver a coastline mask, and Sprint 1 must apply it before any ranking is computed or shown. (National figures: `metadata/gwa_v4_wind-speed_100m_australia_full_inspection.md`.)
2. **The aggregation decision is not neutral and cannot be deferred quietly.** Our two validation sites disagree about which statistic favours them, on the same raster in the same window. There is no statistic that is simply correct; there is only a choice that must be stated, justified and recorded in the scenario configuration.
3. **Terrain data must come from elsewhere.** The Atlas will not supply slope or ruggedness at the resolution and scope this project needs. Task 4 now owns both.

**Is the Global Wind Atlas sufficient on its own?** For the wind resource criterion, yes — no supplementary wind dataset is needed for Version 1. For the *geographic* inputs the Knowledge Base expected it to supply (roughness, orography), no. Those move to Task 4 and the Geoscience Australia DEM.

---

## 10. Acceptance Criteria

- [x] Global Wind Atlas data availability is fully documented (variables, heights, resolution, format, licence) — §4, §4a, §7
- [x] At least one sample dataset is downloaded and stored in `DATA/wind-resource/` — five layers, §5
- [x] Sample has been opened and inspected (columns, grid size, CRS, units, missing values) — §6
- [x] A data dictionary is completed for the primary wind resource dataset — §7
- [x] Integration issues are identified and documented (at least CRS and resolution alignment) — §8, nine issues
- [x] Findings and recommendations section is written — §9
- [x] Any alternative data sources discovered are noted — §4, including sources considered and rejected

Additional artefacts produced beyond the stated criteria:

- [x] `DATA/wind-resource/DATA_PROVENANCE.md` — standalone provenance record matching the Task 2 format, for Task 5 to consolidate
- [x] Validation against two operating wind farms — `metadata/validation_wind_farms.md`
- [x] Quantified aggregation sensitivity for the 250 m → 5 km decision — `metadata/aggregation_sensitivity.md`
- [x] Reproducible retrieval, inspection and validation scripts under `scripts/`

---

## 11. References & Links

- Global Wind Atlas: https://globalwindatlas.info/
- Global Wind Atlas methodology documentation: https://globalwindatlas.info/about/method
- GWA 4 dataset record and citation: https://data.dtu.dk/articles/dataset/Global_Wind_Atlas_4/28955267 — DOI [10.11583/DTU.28955267](https://doi.org/10.11583/DTU.28955267)
- GWA 4.0 release announcement: https://wasp.dtu.dk/news-archive/2025/06/global-wind-atlas-4-0-released
- Methodology paper: Davis et al. (2023), *The Global Wind Atlas: A High-Resolution Dataset of Climatologies and Associated Web-Based Application*, BAMS — https://doi.org/10.1175/BAMS-D-21-0075.1
- Product Knowledge Base: see `Opt-Mining - Product Knowledge Base.md`
- AI Development Constitution: see `Opt-Mining - AI Development Constitution.md`

### Artefacts produced by this task

| Path | Contents |
|---|---|
| `scripts/gwa_common.py` | Shared endpoint resolution and GDAL settings |
| `scripts/probe_gwa_layers.py` | Probes every variable/height combination for availability and size |
| `scripts/download_gwa_sample.py` | Windowed `/vsicurl/` retrieval; writes the download manifest |
| `scripts/inspect_gwa_raster.py` | Raster metadata and statistics; local files, remote headers, or decimated whole-raster summaries |
| `scripts/validate_gwa_windfarms.py` | Samples the Atlas at known wind farm locations |
| `scripts/aggregation_sensitivity.py` | Quantifies the 250 m → 5 km aggregation choice |
| `scripts/crosscheck_against_prototype.py` | Verifies the clips against the OptMining prototype's independently downloaded rasters |
| `DATA/wind-resource/*.tif` | Five sample clips, 2.2 MB each |
| `DATA/wind-resource/DATA_PROVENANCE.md` | Provenance, licence, units, assumptions, limitations |
| `DATA/wind-resource/reference/` | Wind farm validation points, sourced from Task 3 |
| `DATA/wind-resource/metadata/` | Inspection records, download manifest, validation and aggregation reports |

Reproduce everything with:

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt

.venv/bin/python scripts/probe_gwa_layers.py                  # §4a availability table
.venv/bin/python scripts/download_gwa_sample.py               # §5 sample clips
.venv/bin/python scripts/inspect_gwa_raster.py --all-local    # §6 clip statistics
.venv/bin/python scripts/inspect_gwa_raster.py --remote wind-speed --height 100 --decimate 64
.venv/bin/python scripts/validate_gwa_windfarms.py            # §9 validation
.venv/bin/python scripts/aggregation_sensitivity.py           # §8 issue 2 evidence
.venv/bin/python scripts/crosscheck_against_prototype.py      # §12a cross-verification
```

Every figure quoted in this document comes from one of these outputs. None was typed by hand.

---

## 12. Prior Work — the OptMining Prototype

A separate, earlier build exists at `~/Documents/Projects/OptMining` (repo `reoz`, last commit 2026-08-10). It is not a duplicate of this Sprint 0 work: it is a **working end-to-end pipeline skeleton** — national grid, feature builder, scoring, Flask API, Leaflet map, pytest suite, CI, and six ADRs — running on a clearly flagged **synthetic** fixture, because real ingestion was deferred to "session 2". Task 5 should treat it as the reference implementation rather than starting the architecture from scratch.

### 12a. It independently confirms this task's data

The prototype downloaded the full Australian rasters on **2026-08-06** with `scripts/download_gwa.py` and recorded SHA-256 sidecars. Cross-checking that against the clips retrieved for this task:

| Check | Result |
|---|---|
| My `/vsicurl/` window vs. their full-file read, same bbox | **Bit-for-bit identical** — `np.array_equal(..., equal_nan=True)` is `True`, max absolute difference 0, NaN masks match |
| Their recorded SHA-256 vs. the files on disk | Both **match** (`fe7efdb1…`, `e8b7599f…`) |
| Their file sizes vs. the CDN today | Identical to the byte (617,611,287 and 648,639,694) |

Two independent retrieval methods, two weeks apart, produce the same pixels. That validates the windowed-read approach used here **and** establishes that GWA v4 has not been revised since 6 August 2026 — a provenance fact worth carrying, since the layers ship no version metadata (§8, issue 6).

### 12b. Decisions already made there that Task 5 should inherit

| ADR | Decision | Bearing on this task |
|---|---|---|
| **0001** | 0.05° national grid, lon 112.9→153.7, lat −43.7→−10.0; 549,984 cells, ~278k after land masking | Confirms ~5 km is computationally real. **But** its origin is half a native pixel off the Atlas lattice — see §8, *On grid alignment* |
| **0002** | EPSG:4326 storage, EPSG:3577 for all distance/area, enforced by a runtime `assert_crs` | Matches this task's recommendation exactly. Adopt, don't re-derive |
| **0005** | The Atlas is an input, never a prediction target; the ML deliverable is unreconciled and deliberately left open | Agrees with the Constitution and with §7 here |
| **0006** | MVP ranks sites individually rather than selecting a portfolio | Consistent with the current Knowledge Base |

### 12c. Two places where this task's evidence should change that code

1. **`raster_ops.aggregate_to_grid` hard-codes a per-cell mean**, and ADR-0001 states "aggregation statistics (mean per cell) are the contract". The evidence in §8 issue 2 says that is the choice most likely to bury the ridge signal: mean drops White Rock from p93 at native resolution to p80 among 5 km cells. The aggregation statistic should become a configurable, recorded parameter rather than a hard-coded contract — and whichever value is chosen needs the justification Task 5 owes it.
2. **`ingest_wind.load()` still raises `DataNotAvailableError` for real data.** The rasters are on disk and verified; only the loader is missing. This task's `scripts/download_gwa_sample.py` and `scripts/inspect_gwa_raster.py` provide the windowed-read and CRS-handling patterns it needs.

### 12d. Gaps in that prototype which this Sprint 0 round now fills

- `data_sources.yaml` lists `aemo_network_and_generation` and `existing_wind_farms` as **"not investigated — no endpoint checked"**. Task 3 has since sourced both; the wind-farm reference points used for validation in §9 come from exactly that data.
- Its land mask is Natural Earth 1:50m centroid-in-polygon, giving `is_land` and `dist_to_coast_km`. That is a usable starting point for the hard exclusion §8 issue 1 demands, though 1:50m cartographic detail is coarse for a coastline mask and Task 4 should assess whether it is good enough.
- Its AEMO source is the **monthly `PRICE_AND_DEMAND_{YYYYMM}_{REGION}.csv`** aggregate (30 months already downloaded, 2024-01 to 2026-06). Task 2 is working from NEMWeb `Operational_Demand/ACTUAL_DAILY` instead. These are different products — total demand versus operational demand — and Task 5 must pick one deliberately rather than let two coexist.

### 12e. One caution

The prototype ships `scripts/make_synthetic_data.py` and runs the whole stack on seeded synthetic layers. It is scrupulous about this — `is_synthetic` sidecars on every file, a banner on the map, an explicit README warning — and that discipline should be preserved exactly as is. The risk is not the synthetic fixture; it is a future change that quietly swaps `data_mode` or removes a banner. Per the Constitution, no synthetic result may ever be presented as a real one, so the banner and sidecar mechanism should be treated as load-bearing code, not scaffolding to clean up later.
