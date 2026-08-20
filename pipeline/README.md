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

## Dependencies

```
pandas>=2.2
requests>=2.32
rasterio>=1.4
numpy>=2.2
```

No additional dependencies beyond `requirements.txt`. The pipeline deliberately avoids geopandas/shapely/fiona — vector operations use stdlib JSON + rasterio features.
