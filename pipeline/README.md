# Opt-Mining Data Pipeline

Modular pipeline for wind resource (Task 1), electricity infrastructure (Task 3), geographic/environmental (Task 4), and demand (Task 2) data investigation.

## Quick Start

```bash
# Full pipeline (all domains sequentially)
python -m pipeline

# Run only one domain
python -m pipeline --only wind
python -m pipeline --only geographic
python -m pipeline --only infrastructure
python -m pipeline --only demand

# Run a single stage
python -m pipeline --only wind.probe
python -m pipeline --only geographic.derive

# Skip domains or stages
python -m pipeline --skip demand --skip infrastructure
python -m pipeline --skip-validate

# Custom study area
python -m pipeline --bbox 150.0,-31.5,152.0,-29.5 --area-name my-area

# Wind: specific hub heights and turbine classes
python -m pipeline --only wind --heights 100,150 --turbine-class IEC1,IEC2

# Wind: custom aggregation cell size (10 = ~2.5 km cells)
python -m pipeline --only wind.analyse --agg-factor 10

# Demand: specific date range and regions
python -m pipeline --only demand --start-date 2024-01-01 --end-date 2024-12-31 --regions NSW1,QLD1

# Validation: stricter slope threshold
python -m pipeline --max-slope 12

# Verbose output
python -m pipeline --verbose
```

## Data Specification

The authoritative specification of all datasets used in the Sprint 1 pipeline is:

**[`DATA/data-specification/sprint1_data_specification.md`](../DATA/data-specification/sprint1_data_specification.md)**

This document records the source, variables, units, CRS, resolution, temporal coverage, licence, limitations, and pipeline use for every dataset. No data may enter the pipeline without being listed there.

Datasets considered but excluded are documented in [`DATA/data-specification/sprint1_out_of_scope.md`](../DATA/data-specification/sprint1_out_of_scope.md).

## Architecture

```
pipeline/
├── __init__.py             # Package docstring
├── __main__.py             # CLI orchestrator (domain-sequential routing)
├── config.py               # Shared constants (PROJECT_ROOT, bbox, GDAL env, STAGES)
├── validate.py             # Cross-domain integration checks (land mask, siting)
├── common/
│   ├── __init__.py
│   └── geo.py              # ArcGIS REST, atomic writes, banners, human_bytes
├── wind/
│   ├── __init__.py
│   ├── config.py           # GWA URLs, wind paths, aggregation constants
│   ├── gwa.py              # GWA API helpers (resolve_source, apply_vsicurl_env)
│   ├── probe.py            # Stage: GWA layer availability
│   ├── download.py         # Stage: clip GWA rasters via /vsicurl/
│   ├── inspect.py          # Stage: raster statistics and reports
│   ├── validate.py         # Stage: wind farm sampling, crosscheck
│   └── analyse.py          # Stage: aggregation sensitivity
├── geographic/
│   ├── __init__.py
│   ├── config.py           # ArcGIS endpoints, SRTM/NLUM URLs, geo paths
│   ├── probe.py            # Stage: source register (ArcGIS, SRTM, NLUM)
│   ├── download.py         # Stage: vectors (ABS, CAPAD, NE) + rasters (SRTM, NLUM)
│   ├── inspect.py          # Stage: vector + raster sample inspection
│   ├── derive.py           # Stage: slope + TRI from DEM
│   └── validate.py         # Stage: geographic ground-truth checks
├── infrastructure/
│   ├── __init__.py
│   ├── config.py           # GA endpoint, expected files, filters
│   ├── helpers.py          # GeoJSON load/filter/stats
│   ├── download.py         # Stage: presence check of pre-downloaded files
│   └── inspect.py          # Stage: substations, power lines, generators
└── demand/
    ├── __init__.py
    ├── __main__.py          # Demand-specific CLI
    ├── config.py            # AEMO URLs, date defaults
    ├── download.py          # Stage: fetch AEMO demand ZIPs
    ├── validate.py          # Stage: quality gate
    ├── inspect.py           # Stage: statistical summary
    └── aggregate.py         # Stage: annual mean demand per NEM region
```

## Stage Execution Order

The pipeline runs domains sequentially:

```
wind.probe → wind.download → wind.inspect → wind.validate → wind.analyse
→ geographic.probe → geographic.download → geographic.inspect → geographic.derive → geographic.validate
→ infrastructure.download → infrastructure.inspect
→ demand
→ validate (cross-domain integration checks)
```

## CLI Options

```
--bbox W,S,E,N        Study window in EPSG:4326 (default: 150.0,-31.5,152.0,-29.5)
--area-name NAME      Short slug for filenames (default: new-england-rez)
--only DOMAIN|STAGE   Run only one domain or stage
--skip DOMAIN|STAGE   Skip a domain or stage (repeatable)
--skip-validate       Skip the cross-domain validation stage
--state STATE         State filter for infrastructure (default: NSW)
--fuel-type TYPE      Fuel type for generator filter (default: wind)
--start-date DATE     Demand data start (default: 2025-07-01)
--end-date DATE       Demand data end (default: 2026-06-30)
--regions IDS         Comma-separated NEM region IDs for demand (default: all 5)
--heights METRES      Comma-separated hub heights for wind-speed downloads (default: 50,100,150)
--turbine-class CLS   Comma-separated IEC classes for capacity-factor (default: IEC2)
--agg-factor N        Native pixels per analysis cell side (default: 20 = ~5 km)
--max-slope DEGREES   Maximum slope for wind farm siting checks (default: 15.0)
--prototype-path PATH Path to OptMining prototype for crosscheck
--skip-land-sea       Skip the land/sea remote check in validate
--verbose             Detailed logging
```

### Parameter Details

| Flag | Affects stages | Description |
|------|---------------|-------------|
| `--regions` | demand (aggregate) | Filters aggregation to specified NEM regions. Valid: NSW1, QLD1, SA1, TAS1, VIC1. All data is still downloaded; filtering applies at the summary step. |
| `--heights` | wind.download | Controls which hub-height wind-speed layers are clipped from the GWA. Valid heights: 10, 50, 100, 150, 200. |
| `--turbine-class` | wind.download | Selects IEC turbine class capacity-factor layers. Valid: IEC1, IEC2, IEC3. Multiple classes can be comma-separated. |
| `--agg-factor` | wind.analyse | Number of native GWA pixels (0.0025 deg each) per analysis cell side. 20 = 0.05 deg ~ 5 km. Lower values give finer cells but noisier statistics. |
| `--max-slope` | validate | Slope threshold in degrees for the cross-domain siting check. Wind farms on slopes above this are flagged as failures. |

## Importing Stages Directly

Each stage module exposes a `run()` function:

```python
from pipeline.wind.probe import run as wind_probe
from pipeline.geographic.download import run as geo_download
from pipeline.infrastructure.inspect import run as infra_inspect

wind_probe(verbose=True)
geo_download(bbox=(150.0, -31.5, 152.0, -29.5), area_name="new-england-rez")
infra_inspect(state="NSW", fuel_type="wind")
```

## Data Outputs

Outputs write to the existing `DATA/` layout:

```
DATA/
├── wind-resource/          # GWA raster clips + metadata
├── geographic/             # Boundaries, elevation, land use, protected areas
├── infrastructure/         # GA power lines, substations, generators
└── electricity-demand/     # AEMO demand data
```

## Expected Outputs

A successful full pipeline run produces the following file tree under `DATA/`:

### Wind Resource (`DATA/wind-resource/`)

| File | Stage | Description |
|------|-------|-------------|
| `gwa_v4_wind-speed_50m_new-england-rez.tif` | download | Mean wind speed at 50 m hub height (GeoTIFF, EPSG:4326) |
| `gwa_v4_wind-speed_100m_new-england-rez.tif` | download | Mean wind speed at 100 m hub height |
| `gwa_v4_wind-speed_150m_new-england-rez.tif` | download | Mean wind speed at 150 m hub height |
| `gwa_v4_power-density_100m_new-england-rez.tif` | download | Power density at 100 m (W/m²) |
| `gwa_v4_capacity-factor_IEC2_new-england-rez.tif` | download | Capacity factor for IEC Class II turbine |
| `DATA_PROVENANCE.md` | download | Human-readable provenance table |
| `metadata/layer_availability.md` | probe | GWA layer reachability report |
| `metadata/download_manifest.json` | download | SHA-256 hashes, byte counts, timestamps |
| `metadata/*_inspection.md` | inspect | Per-raster statistics (min, max, mean, nodata %) |
| `metadata/validation_wind_farms.md` | validate | Sampling results at known wind farm locations |
| `metadata/crosscheck_prototype.md` | validate | Cross-check against independent prototype data |
| `metadata/aggregation_sensitivity.md` | analyse | Sensitivity to aggregation window size |
| `reference/nsw_wind_farms_new_england.csv` | validate | Reference wind farm locations used for validation |

### Geographic (`DATA/geographic/`)

| File | Stage | Description |
|------|-------|-------------|
| `boundaries/abs_aus_2021_national.geojson` | download | Australia national boundary (ABS ASGS 2021) |
| `boundaries/abs_ste_2021_national.geojson` | download | State/territory boundaries |
| `boundaries/abs_lga_2021_new-england-rez.geojson` | download | Local government areas clipped to study area |
| `coastline/ne_land-50m_australia.geojson` | download | Natural Earth 1:50m land polygon (Australia) |
| `elevation/srtm-gl1_elevation_30m_glen-innes.tif` | download | SRTM GL1 DEM at 30 m resolution |
| `elevation/srtm-gl3_elevation_90m_new-england-rez.tif` | download | SRTM GL3 DEM at 90 m resolution |
| `elevation/srtm-gl1_slope-horn_30m_glen-innes.tif` | derive | Horn slope (degrees) derived from 30 m DEM |
| `elevation/srtm-gl3_slope-horn_90m_new-england-rez.tif` | derive | Horn slope (degrees) derived from 90 m DEM |
| `elevation/srtm-gl1_tri_30m_glen-innes.tif` | derive | Terrain Ruggedness Index from 30 m DEM |
| `landuse/abares_nlum-alumv8_2020-21_new-england-rez.tif` | download | National Land Use Map (ALUMV8 classified raster) |
| `landuse/abares_alumv8_class_table.csv` | download | ALUMV8 class code lookup table |
| `protected/dcceew_capad-terrestrial_2024_new-england-rez.geojson` | download | CAPAD protected areas clipped to study area |
| `protected/dcceew_capad-terrestrial_2024_nsw.geojson` | download | CAPAD protected areas (full NSW) |
| `urban/abs_ucl_2021_new-england-rez.geojson` | download | Urban centre/locality boundaries |
| `derived/nem_regions_asgs2021_national.geojson` | derive | NEM region geometries (dissolved from state boundaries) |
| `DATA_PROVENANCE.md` | download | Human-readable provenance table |
| `metadata/source_register.csv` | probe | Catalogue of all probed data sources |
| `metadata/download_manifest.json` | download | SHA-256 hashes, byte counts, timestamps |
| `metadata/validation_geographic.md` | validate | Ground-truth checks (spot elevations, reserve areas) |
| `metadata/landmask_assessment.md` | validate | NE coastline vs ABS boundary comparison |
| `metadata/*_inspection.md` | inspect | Per-layer sample inspection reports |

### Infrastructure (`DATA/infrastructure/`)

| File | Stage | Description |
|------|-------|-------------|
| `transmission-lines/ga_power_lines_2026_australia.geojson` | download | National transmission network (GA) |
| `transmission-lines/ga_power_lines_2026_nsw.geojson` | download | NSW transmission lines (state-filtered) |
| `substations/ga_substations_2026_australia.geojson` | download | National substations (GA) |
| `substations/ga_substations_2026_nsw.geojson` | download | NSW substations (state-filtered) |
| `generators/ga_powerstations_2026_australia.geojson` | download | National power stations (GA) |
| `generators/ga_wind_generators_2026_australia.geojson` | download | Wind generators (national) |
| `generators/ga_wind_generators_2026_nsw.geojson` | download | Wind generators (NSW) |
| `connection-points/aemo_kci_2026.xlsx` | download | AEMO key connection information |
| `renewable-energy-zones/aemo_indicative_rez_boundaries_2026.kmz` | download | AEMO indicative REZ boundaries |
| `metadata/*_inspection.md` | inspect | Feature counts, schema summaries, spatial extent |

### Electricity Demand (`DATA/electricity-demand/`)

| File | Stage | Description |
|------|-------|-------------|
| `raw/PUBLIC_ACTUAL_OPERATIONAL_DEMAND_DAILY_*.zip` | download | AEMO daily demand ZIP archives |
| `demand_annual_summary.csv` | aggregate | Annual mean demand by NEM region (MW) |
| `demand_annual_summary.meta.json` | aggregate | Metadata for the summary (date range, row count) |
| `inspection_summary.txt` | inspect | Statistical summary of demand data |

### Cross-Domain Validation (`DATA/geographic/metadata/`)

| File | Stage | Description |
|------|-------|-------------|
| `landmask_assessment.md` | validate | Quantifies coastal leakage between mask sources |

The `validate` (cross-domain) stage does not produce additional files; it writes pass/fail results to stdout. The geographic and wind domain validation reports (listed above) capture siting constraint checks (slope, protected areas, land mask).

## Data Sources

| Domain | Source | Licence |
|--------|--------|---------|
| Wind resource | Global Wind Atlas v4 (DTU) | CC BY 4.0 |
| Boundaries | ABS ASGS 2021 | CC BY 4.0 |
| Protected areas | DCCEEW CAPAD 2024 | CC BY 4.0 |
| Land use | ABARES NLUM 2020-21 | CC BY 4.0 |
| Elevation | NASA SRTM GL1/GL3 (OpenTopography) | Public domain |
| Coastline | Natural Earth 1:50m | Public domain |
| Infrastructure | Geoscience Australia Electricity Infrastructure | CC BY 4.0 |
| Demand | AEMO NEMWeb Operational Demand | Public |

## Data Provenance and Validation

### Provenance Tracking

The pipeline records the origin, licence and vintage of every dataset it acquires. Provenance is captured at two levels:

1. **Source register** (`DATA/geographic/metadata/source_register.csv` / `.md`) — a catalogue of all candidate sources probed during the `probe` stage, including endpoints that refuse scripted access. Records custodian, access method, status code, native CRS, licence, and vintage.
2. **Download manifests** (`DATA/geographic/metadata/download_manifest.json`) — byte counts, SHA-256 hashes, retrieval timestamps (UTC) and request parameters for every file written during `download` stages.
3. **Per-domain DATA_PROVENANCE.md** files (e.g. `DATA/geographic/DATA_PROVENANCE.md`, `DATA/wind-resource/DATA_PROVENANCE.md`) — human-readable provenance tables structured per dataset with fields for publisher, access endpoint, temporal coverage, native CRS, units, licence, method, assumptions and limitations.

Derived files (NEM region geometries, slope/TRI rasters) are explicitly labelled as derived and document the transformation applied, so they are never mistaken for custodial data.

### Validation Strategy

Validation is structured in two tiers:

**Domain-specific validation** (each domain's own `validate.py`):

| Domain | Module | Checks |
|--------|--------|--------|
| Wind | `pipeline.wind.validate` | GWA raster sampling at known wind farm locations; percentile ranking; crosscheck windowed clips against independent downloads |
| Geographic | `pipeline.geographic.validate` | CAPAD area (Kosciuszko NP extent); DEM spot-elevation (Armidale, Glen Innes); NLUM class decode completeness; ABS state area cross-check |
| Demand | `pipeline.demand.validate` | Duplicate detection; 30-min timestamp continuity; regional completeness (5 NEM regions); non-null numeric demand values |

**Cross-domain integration** (`pipeline.validate`):

- Wind farms are on land (NE + ABS mask agreement)
- Wind farms are outside protected areas (CAPAD)
- Wind farms have acceptable slope (< 15°)
- Land-mask assessment: NE 1:50m vs ABS coastline on the analysis grid — quantifies coastal leakage and recommends the preferred mask

### Validation Reports

Validation stages produce Markdown reports in the relevant `metadata/` directory:

- `DATA/geographic/metadata/validation_geographic.md`
- `DATA/geographic/metadata/landmask_assessment.md`
- `DATA/wind-resource/metadata/validation_wind_farms.md`
- `DATA/wind-resource/metadata/crosscheck_prototype.md`

### Design Principles

- **No silent passes.** Every validation check reports its expected value, observed value and pass/fail status.
- **Validate against reality.** Known operational wind farm locations and gazetted reserve areas serve as ground-truth anchors — if a known-good site fails a check, the data layer is suspect.
- **Fail loud, not late.** The demand quality gate (`--skip-validate` to bypass) halts the pipeline on data integrity violations; geographic and wind checks produce reports for human review.
- **Provenance travels with data.** Attribution, CRS, units, and limitations are recorded at ingest so downstream stages and the eventual interface can propagate them without re-deriving context.

## Dependencies

```
pandas>=2.2
requests>=2.32
rasterio>=1.4
numpy>=2.2
```

No additional dependencies beyond `requirements.txt`. The pipeline deliberately avoids geopandas/shapely/fiona — vector operations use stdlib JSON + rasterio features.

## Open Questions (Team Decision Required)

These questions arose from the Task 5 integration analysis. Each affects how the pipeline scores and ranks sites in Sprint 1. The team needs to make a call on each before implementation proceeds.

| # | Question | Options | Recommendation |
|---|----------|---------|----------------|
| 1 | Wind aggregation statistic for 250 m → 5 km cells? | (a) Mean — stable, buries ridges. (b) Max — captures best micro-site, noisy. (c) P90 — compromise. (d) Report multiple, let user choose. | Report mean + p90 as features; use mean as default scoring input; present max as "best micro-site" indicator in explanation. |
| 2 | Primary hub height for scoring? | (a) 100 m — consistent with capacity factor layers. (b) 150 m — closer to modern turbine heights. | Use 100 m for V1 (CF consistency); carry 150 m as sensitivity layer. |
| 3 | Slope aggregation statistic per cell? | (a) Mean slope — general terrain difficulty. (b) P90 — flags cells with steep sections. (c) Max — most conservative. | Use mean slope as penalty input; report p90 in explanation. Evidence: exclusion varies 11.6% (mean) to 42.1% (p90) to 85.7% (max) at 10° threshold. |
| 4 | Population data source for demand allocation? | (a) ABS Census 2021 ERP at SA2 level. (b) ABS Census 2021 at mesh block. (c) ABS gridded population estimates. | SA2 level — sufficient resolution for ~5 km grid, simpler to implement. |
| 5 | Should demand criterion use operational or total demand? | (a) Operational demand — grid-served load. (b) PRICE_AND_DEMAND — includes price. | Operational demand. It measures the load new generation must serve. |
| 6 | Hard exclusion threshold for protected areas? | (a) Binary — any CAPAD overlap excludes the cell. (b) Fractional — exclude only if > X% is protected. | Binary exclusion (any intersection). |
| 7 | Should infrastructure distance have a hard exclusion threshold? | (a) No — continuous distance only. (b) Yes — exclude cells > 100 km from transmission. | No hard exclusion for V1. Distance is a continuous penalty; remote cells rank low naturally. |
