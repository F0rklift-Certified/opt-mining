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

# Verbose output
python -m pipeline --verbose
```

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
--prototype-path PATH Path to OptMining prototype for crosscheck
--skip-land-sea       Skip the land/sea remote check in validate
--verbose             Detailed logging
```

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
