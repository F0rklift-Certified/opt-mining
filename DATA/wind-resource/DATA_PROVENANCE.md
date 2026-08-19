# Data Provenance — Global Wind Atlas v4 (Australia)

## Dataset

| Field | Value |
|-------|-------|
| **Name** | Global Wind Atlas 4 (GWA 4.0) |
| **Publisher** | Technical University of Denmark (DTU Wind Energy), in partnership with the World Bank Group, funded by ESMAP, using data provided by Vortex |
| **Version** | 4.0, released June 2025; dataset record published 2025-07-09 |
| **DOI** | [10.11583/DTU.28955267](https://doi.org/10.11583/DTU.28955267) |
| **Application URL** | https://globalwindatlas.info/ |
| **Dataset record** | https://data.dtu.dk/articles/dataset/Global_Wind_Atlas_4/28955267 |
| **Source URL used** | `https://gwa.cdn.nazkamapps.com/country_tifs_v4/AUS_<variable>[_<height>m].tif` |
| **Access endpoint** | `https://globalwindatlas.info/api/gis/country/AUS/<variable>[/<height>]` (302 redirect to the CDN) |
| **Format** | GeoTIFF, single band, float32, internally tiled (512x512), zstd compressed, 6 overview levels |
| **Retrieval method** | `scripts/download_gwa_sample.py` — windowed read over GDAL `/vsicurl/`; the full rasters are never downloaded |
| **Server file date** | 2025-06-12 (HTTP `Last-Modified` on every layer retrieved) |
| **Vintage verified stable** | Yes — bit-for-bit identical to rasters downloaded independently on 2026-08-06 by the OptMining prototype, whose SHA-256 sidecars still verify. See `metadata/crosscheck_prototype.md`. |
| **Authentication** | None. No registration, no API key, no download limit encountered. |

## Temporal Coverage

| Field | Value |
|-------|-------|
| **Temporal nature** | Long-term climatology — a single static mean per pixel, not a time series |
| **Underlying period** | ERA5 reanalysis, 2008–2017 (10 years) |
| **Temporal resolution** | N/A — the published layers are 10-year means |
| **Vintage** | GWA 4.0, June 2025 |

The Atlas is **static** for platform purposes. It does not need temporal alignment with the AEMO
demand time series (Task 2); the demand side is aggregated to a comparable long-run indicator
instead. The two describe different decades and this must be stated wherever they are combined.

## Spatial Coverage

| Field | Value |
|-------|-------|
| **CRS** | EPSG:4326 (WGS 84), explicitly declared in the file |
| **Native pixel size** | 0.0025° x 0.0025° |
| **Approximate metres** | ~278 m N–S at every latitude; E–W ~274 m at 10°S, ~241 m at 30°S, ~200 m at 44°S |
| **Grid size (Australia)** | 21,601 x 18,374 pixels |
| **Bounds (Australia)** | 109.21125, -54.79625, 163.21375, -8.86125 |
| **Valid-data coverage** | ~48% of that bounding box; the remainder is NaN outside Australian territory |
| **Includes marine areas** | **Yes** — ocean pixels carry real wind speeds, they are not NoData |

The "250 m" figure quoted in the Product Knowledge Base is nominal and matches no Australian
latitude. The grid is defined in degrees, so pixels are not square in metres and their east–west
size shrinks with latitude — by 27% between Cape York and southern Tasmania. Any resampling or
area-weighting step must state which figure it assumes rather than treating a pixel as 250 m.

## Units

| Variable | Unit | Description |
|----------|------|-------------|
| `wind-speed` | m/s | 10-year mean wind speed at the stated height |
| `power-density` | W/m² | 10-year mean wind power density (relates to the cube of wind speed) |
| `capacity-factor_IEC1/2/3` | ratio, 0–1 | Modelled capacity factor for an IEC class 1/2/3 turbine at 100 m hub height, rotor diameter 117 m / 136 m / 150 m |
| `air-density` | kg/m³ | Modelled air density at the stated height |
| `combined-Weibull-A` | m/s | All-sector combined Weibull scale parameter |
| `combined-Weibull-k` | dimensionless | All-sector combined Weibull shape parameter |

**The GeoTIFFs carry no embedded unit, description or version metadata** — `AREA_OR_POINT=Area`
is the only tag present. Units are known only from the publisher's dataset description, so they
must be recorded here and asserted in code rather than read from the file.

## Licence and Attribution

| Field | Value |
|-------|-------|
| **Licence** | Creative Commons Attribution 4.0 International (CC BY 4.0) |
| **Licence URL** | https://creativecommons.org/licenses/by/4.0/ |
| **Commercial use** | Permitted |
| **Redistribution** | Permitted with attribution |

Required citation:

> Floors, Rogier Ralph; Davis, Neil; Olsen, Bjarke Tobias; Badger, Jake; Hansen, Brian Ohrbeck
> (2025). *Global Wind Atlas 4.* Technical University of Denmark. Dataset.
> https://doi.org/10.11583/DTU.28955267.v1

This attribution must travel through to the platform interface and any exported report.

### Access-terms compliance

The Global Wind Atlas application states, on its GIS files and API access page:

> "This API service is not to be used for bulk downloads of all countries or datasets. Please
> contact the GWA team through the Contact page if you have such a request."

Our retrieval reads a single country's rasters and transfers only the ~2 MB window each — around
11 MB in total, against ~3 GB if the five layers had been downloaded in full. If the project later
needs national coverage across many layers, **contact the GWA team first** rather than scaling this
script up. The alternative sanctioned route is the DTU repository, which hosts the global rasters
directly (6–16 GB per layer).

## Method (summary)

ERA5 reanalysis (2008–2017) is dynamically downscaled to 3 km with the WRF mesoscale model,
generalised using DTU's generalisation methodology, then downscaled with WAsP/PyWAsP to ~250 m.
Version 4 adds updated air density, and new stability and geostrophic wind shear models from ERA5.

## Assumptions

1. **The Atlas is an input, never a prediction target.** Per the AI Development Constitution, no
   model in this platform may be trained to predict Atlas values from features derived from the
   Atlas.
2. Wind speed at **150 m** is treated as the most representative height for current utility-scale
   Australian wind development. See the Task 1 findings for the evidence; the platform must keep
   the height configurable rather than fixing it.
3. Capacity factor IEC2 is retained as the most directly interpretable resource layer, with the
   caveat that it is modelled for one specific turbine (100 m hub, 136 m rotor) and is not a
   yield estimate for any real project.
4. The sampled window (New England REZ, NSW) is representative of ridge-line terrain, not of
   Australia. National statistics quoted in the task document come from a decimated read of the
   full raster, and are labelled as such.

## Scope and Limitations

**These layers describe modelled long-term mean wind climate at ~250 m resolution. They are not a
measurement, not a yield prediction, and not a bankable resource assessment.**

1. **Marine pixels are not masked.** The strongest wind speeds in the Australian raster are over
   open ocean. A land mask (Task 4) is mandatory before any ranking, or the entire shortlist will
   be offshore. This is the single highest-risk property of this dataset.
2. **Aggregation to the ~5 km analysis grid discards the ridge signal that matters.** The mean gap
   between a 5 km cell's best 250 m pixel and its 400-pixel average is 1.28 m/s in the study
   window. See `metadata/aggregation_sensitivity.md`.
3. **No terrain ruggedness or elevation layer is available per country.** RIX and site elevation
   exist in GWA 4 only as global rasters (6.1 GB and 8.9 GB) on the DTU repository.
4. **The climatology is a 2008–2017 mean.** It carries no interannual variability, no seasonal
   breakdown, and no information about future conditions.
5. **Capacity-factor layers assume one turbine model each** at a fixed hub height of 100 m. They
   are comparative indicators between locations, not energy yield estimates.
