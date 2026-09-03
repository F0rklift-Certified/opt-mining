# Opt-Mining Data Pipeline

Modular pipeline for wind resource (Task 1), electricity infrastructure (Task 3), geographic/environmental (Task 4), demand (Task 2), and grid generation (S1-02) data processing.

## Quick Start

```bash
# Full pipeline (all domains sequentially)
python -m pipeline

# Run only one domain
python -m pipeline --only wind
python -m pipeline --only geographic   # resolves 6 geographic stages: probe, download,
                                       # inspect, derive, validate, features — with
                                       # features running last against a pre-existing grid
python -m pipeline --only infrastructure
python -m pipeline --only demand
python -m pipeline --only grid
python -m pipeline --only demand.feature --allocation-method uniform

# Run a single stage
python -m pipeline --only wind.probe
python -m pipeline --only geographic.derive
python -m pipeline --only infrastructure.features --infra-features-crs EPSG:3577

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

# Grid generation (standalone)
python -m pipeline.grid
python -m pipeline.grid --verbose

# Exclusion layer (standalone, S1-07 — requires the grid to exist already)
python -m pipeline --only exclusions
python -m pipeline --only exclusions --exclusion-rules path/to/custom_rules.yaml

# Integrated NSW Feature Table (S1-08 — requires the grid, the four feature
# layers and the exclusion layer to exist already; joins them by cell_id and
# appends the S1-09 data-confidence columns)
python -m pipeline --only integration
python -m pipeline --only integration --confidence-weights path/to/my_weights.yaml
python -m pipeline --only scoring
python -m pipeline --only scoring --scoring-weights path/to/my_weights.yaml

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
├── grid/
│   ├── __init__.py         # Subpackage docstring (S1-02 architecture decision)
│   ├── __main__.py         # Standalone CLI: python -m pipeline.grid
│   ├── config.py           # Grid constants (GWA origin, cell size, NSW bbox, CRS)
│   └── generate.py         # generate_grid() → GeoDataFrame; run() → GeoPackage
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
│   ├── inspect.py          # Stage: substations, power lines, generators
│   └── features.py         # Stage (S1-05): per-cell infrastructure features
├── integration/
│   ├── __init__.py
│   ├── analyse.py          # Task 5 evidence: grid geometry, CRS alignment (unregistered)
│   ├── config.py           # Input paths composed from each domain's config; output names
│   ├── merge.py            # Stage (S1-08): left-join every layer -> Integrated Feature Table
│   ├── confidence.py       # S1-09: per-cell data_confidence / confidence_score / confidence_notes
│   └── confidence_weights.yaml  # S1-09 weights, resolution/limitation factors, flag factors, thresholds
├── scoring/
│   ├── __init__.py
│   ├── config.py           # Paths, vocabularies, tolerances (composed from upstream configs)
│   ├── scoring_weights.yaml  # S1-10 criteria weights, directions and rationales — USER INPUT
│   ├── weights.py          # Weights loader + validator (fails before any write)
│   ├── load.py             # Reads the S1-08 integrated table (the sole feature input)
│   ├── normalise.py        # Directional min-max from the eligible population only
│   ├── score.py            # Stage (S1-10): the PURE weighted-MCDA scoring function
│   ├── rank.py             # Descending by score, ties by ascending cell_id
│   ├── write.py            # Scored_Table assembly + atomic GeoPackage/CSV writers
│   ├── report.py           # Method report, validation report, derived-product provenance
│   ├── validate.py         # No-silent-passes checks over the scored table
│   └── run.py              # Stage entry point: run(verbose=False, ...) -> dict
├── demand/
│   ├── __init__.py
│   ├── __main__.py          # Demand-specific CLI
│   ├── config.py            # AEMO URLs, date defaults
│   ├── download.py          # Stage: fetch AEMO demand ZIPs
│   ├── validate.py          # Stage: quality gate
│   ├── inspect.py           # Stage: statistical summary
│   ├── aggregate.py         # Stage: annual mean demand per NEM region
│   └── feature.py           # Stage (S1-04): per-cell demand proxy
└── exclusions/
    ├── __init__.py           # Scope note: reads raw sources directly (see below)
    ├── config.py             # Paths, output schema, delimiters
    ├── rules.py              # Pure rule engine: load_rules(), evaluate_cell()
    ├── raster_stats.py       # Reusable cell-centre-mask zonal-mean helper
    ├── exclusion_rules.yaml  # Default configurable exclusion rules (S1-07)
    └── apply.py              # Stage: builds the Eligibility_Table + report
```

## Stage Execution Order

The pipeline runs domains sequentially:

```
wind.probe → wind.download → wind.inspect → wind.validate → wind.analyse
→ geographic.probe → geographic.download → geographic.inspect → geographic.derive → geographic.validate
→ infrastructure.download → infrastructure.inspect
→ demand
→ grid (common analysis cell generation)
→ wind.features (S1-03 per-cell wind feature table — consumes the grid)
→ geographic.features (per-cell geographic feature table on the common grid, S1-06)
→ infrastructure.features (per-cell infrastructure features)
→ demand.feature (per-cell demand proxy)
→ exclusions (S1-07 exclusion layer — eligibility per cell)
→ integration (S1-08 Integrated Feature Table — joins every feature layer + exclusions by cell_id; S1-09 appends the composite data confidence)
→ scoring (S1-10 baseline suitability model — weighted MCDA over the integrated table; scores, ranks and explains every eligible cell)
→ validate (cross-domain integration checks)
```

`wind.features` is registered after `grid` (not inline with the other
`wind.*` stages) because it consumes `DATA/grid/nsw_analysis_grid.gpkg`.
Note that `--only wind` therefore runs `wind.features` last, against a
pre-existing grid file on disk — regenerate it first with `--only grid`
if absent. Its source raster is the NSW-wide GWA clip, regenerated with:

```bash
python -m pipeline --only wind.download \
  --bbox 141.01125,-37.51125,153.66125,-28.16125 --area-name nsw --heights 100
```

(That bbox is the exact grid extent, snapped to the GWA lattice so each
analysis cell is a clean 20×20 native-pixel block.)

Note: `geographic.features` is registered in `config.STAGES` after `grid` (not inline with the other `geographic.*` stages) because it CONSUMES the grid — the grid producer must run before this consumer.

Note: `integration` (S1-08) runs after `exclusions` and before `validate` because it consumes every feature table and the Eligibility_Table. It joins whatever is on disk and halts — naming the stage to run — if any input is absent, so `python -m pipeline` (all stages) is the single command from raw data to the integrated table, and `--only integration` re-joins already-generated layers. The S1-09 confidence layer runs inside the same stage, between the join and validation, from `pipeline/integration/confidence_weights.yaml`.

Note: `scoring` (S1-10) runs after `integration` and before `validate` because the integrated feature table is its sole input. It is a transparent, deterministic **weighted multi-criteria decision analysis (MCDA)** — not a machine-learning model:

```
norm_i    = (v_i - min_i) / (max_i - min_i)          direction higher_is_better
norm_i    = 1 - (v_i - min_i) / (max_i - min_i)      direction lower_is_better
contrib_i = weight_i * norm_i / W_cell
score     = SUM_i contrib_i                          -> [0, 1]
```

- **Criteria weights are user inputs**, loaded at runtime from `pipeline/scoring/scoring_weights.yaml` (or `--scoring-weights PATH`). No weight literal appears anywhere in `pipeline/scoring/`; edit the YAML to change the model's priorities. Each criterion carries a weight, a direction (`higher_is_better` / `lower_is_better`) and a written rationale.
- **Normalisation** is linear min-max, with bounds computed from the **eligible cell population on each run** — never hard-coded. Boolean criteria use their definitional `{False -> 0.0, True -> 1.0}` domain. A criterion that is constant over the eligible population is filled with a documented constant rather than dividing by zero, and is flagged as constant in the method report.
- **Only eligible cells are scored.** Cells the S1-07 exclusion layer rejected receive a null score, a null rank and null contributions, and take no part in the normalisation bounds or the ranking — ineligible land is never ranked as if it were developable.
- **Explainability:** every criterion's additive contribution to every score is written to the table as `contrib_{feature}`, and the contributions are verified to sum back to the score on every run. `rank` 1 is the best cell; ties break by ascending `cell_id`.
- **Confidence** is carried through from the S1-09 composite flag unchanged, never recomputed or fabricated. The optional confidence discount (`--confidence-discount`) multiplies both the score and its contributions by the cell's factor, so they stay reconcilable.
- **Not circular:** `wind_speed` is an input criterion only, never a prediction target.

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
--allocation-method M Demand allocation for demand.feature (MVP: uniform)
--infra-features-crs CRS Projected CRS for infrastructure distances (default: EPSG:3577)
--heights METRES      Comma-separated hub heights for wind-speed downloads (default: 50,100,150)
--turbine-class CLS   Comma-separated IEC classes for capacity-factor (default: IEC2)
--agg-factor N        Native pixels per analysis cell side (default: 20 = ~5 km)
--max-slope DEGREES   Maximum slope for wind farm siting checks (default: 15.0)
--prototype-path PATH Path to OptMining prototype for crosscheck
--skip-land-sea       Skip the land/sea remote check in validate
--exclusion-rules PATH Custom exclusion rules YAML for the 'exclusions' stage
                       (default: pipeline/exclusions/exclusion_rules.yaml)
--confidence-weights PATH Custom confidence weights YAML for the 'integration' stage (S1-09)
                       (default: pipeline/integration/confidence_weights.yaml)
--scoring-weights PATH Custom criteria weights YAML for the 'scoring' stage (S1-10)
                       (default: pipeline/scoring/scoring_weights.yaml)
--confidence-discount  Enable the S1-10 confidence discount (overrides the weights file)
--no-confidence-discount Disable the S1-10 confidence discount (overrides the weights file)
--verbose             Detailed logging
```

**`--only geographic` and the feature builder.** Because `geographic.features` is registered in `config.STAGES` after `grid`, `--only geographic` resolves all six geographic stages in `STAGES` order — `geographic.probe, geographic.download, geographic.inspect, geographic.derive, geographic.validate, geographic.features` — with `features` running last. Note that `--only geographic` runs `geographic.features` **without** first running `grid`, so it depends on a previously-generated grid file (`DATA/grid/nsw_analysis_grid.gpkg`) already existing on disk; the stage fails loudly with a clear error if the grid is absent. Run `python -m pipeline --only grid` first (or a full run) if the grid has not yet been generated.

**`--only integration`.** The stage's inputs are the fixed products of `grid`, `wind.features`, `geographic.features`, `infrastructure.features`, `demand.feature` and `exclusions` (paths composed in `pipeline/integration/config.py` from each domain's config). It never reprojects or back-fills; a missing input, an undeclared or non-EPSG:4326 CRS, or a duplicate `cell_id` halts the stage with an error naming the offending layer. Its only flag is `--confidence-weights PATH` (S1-09): the confidence config is loaded and validated before any input is read, so a missing or malformed YAML fails the stage before it writes anything; weights, resolution/limitation factors, per-layer flag factors and the high/medium thresholds are all data in that file.

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
from pipeline.grid.generate import run as grid_run
from pipeline.grid.generate import generate_grid

wind_probe(verbose=True)
geo_download(bbox=(150.0, -31.5, 152.0, -29.5), area_name="new-england-rez")
infra_inspect(state="NSW", fuel_type="wind")

# Grid: generate and write to GeoPackage
grid_run(verbose=True)

# Grid: get the GeoDataFrame directly (no I/O)
gdf = generate_grid()

# Exclusion layer (S1-07): apply the configurable rules and write the Eligibility_Table
from pipeline.exclusions.apply import run as exclusions_run
exclusions_run(verbose=True)

# Integrated Feature Table (S1-08 + S1-09): left-join every layer + exclusions on
# cell_id, then append the composite data confidence
from pipeline.integration.merge import run as integration_run
summary = integration_run(verbose=True)   # summary["validation"] holds every check
summary["confidence"]["counts"]            # {"high": ..., "medium": ..., "low": ...}

# Confidence layer on its own (pure; no I/O)
from pipeline.integration.confidence import assess, load_weights
weights = load_weights("pipeline/integration/confidence_weights.yaml")
columns = assess(integrated_table, weights)   # data_confidence, confidence_score, confidence_notes
```

The S1-10 scoring stage, and its pure scoring function on any in-memory frame:

```python
from pipeline.scoring.run import run as scoring_run
summary = scoring_run(verbose=True)           # summary["validation"] holds every check

# The scoring computation itself is pure — a DataFrame and a WeightsConfig in,
# a scored DataFrame out, with no file I/O — so it can be swapped for a
# different model without touching the loading or writing layers.
from pipeline.scoring.score import score_and_rank
from pipeline.scoring.weights import load_weights as load_criteria_weights
weights = load_criteria_weights("pipeline/scoring/scoring_weights.yaml")
scored = score_and_rank(feature_frame, weights)
```

## Data Outputs

Outputs write to the existing `DATA/` layout:

```
DATA/
├── wind-resource/          # GWA raster clips + metadata
├── geographic/             # Boundaries, elevation, land use, protected areas
├── infrastructure/         # GA power lines, substations, generators
├── electricity-demand/     # AEMO demand data
├── grid/                   # Common analysis cell grid (S1-02)
├── exclusions/             # Eligibility_Table + method report (S1-07)
├── integration/            # Integrated NSW Feature Table (S1-08) with data confidence (S1-09) + Task 5 analysis
└── scoring/                # Baseline suitability score, rank and per-criterion contributions (S1-10)
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
| `gwa_v4_wind-speed_100m_nsw.tif` | download | Mean wind speed at 100 m, NSW-wide grid-extent clip (S1-03 source) |
| `gwa_v4_power-density_100m_nsw.tif` | download | Power density at 100 m, NSW-wide clip |
| `gwa_v4_capacity-factor_IEC2_nsw.tif` | download | IEC Class II capacity factor, NSW-wide clip |
| `features/gwa_v4_wind-feature_2025_nsw.gpkg` | wind.features | Per-cell wind feature table (S1-03): cell_id, wind_speed_100m, units, data_source, confidence_flag |
| `metadata/wind_feature_method.md` | wind.features | Method report: variable justification, aggregation rule, stats, validation checks |
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
| `features/optmining_geographic-features_2024_nsw.gpkg` | geographic.features | Per-cell geographic feature table on the common analysis grid (GeoPackage, EPSG:4326): `cell_id`, `elevation_m`, `slope_deg`, `land_use`, `protected_area`, `protected_area_name`, `tri`, `confidence_flag` (S1-06) |
| `metadata/geographic_features_method.md` | geographic.features | Method report: zonal-statistics method, coverage (New England REZ / Glen-Innes-only TRI vs full NSW grid), confidence counts, CRS transformations, runtime |
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
| `optmining_infra-features_2026_nsw.gpkg` | infrastructure.features | Per-cell infrastructure distances and REZ membership; distances use EPSG:3577 from cell centroids |

### Electricity Demand (`DATA/electricity-demand/`)

| File | Stage | Description |
|------|-------|-------------|
| `raw/PUBLIC_ACTUAL_OPERATIONAL_DEMAND_DAILY_*.zip` | download | AEMO daily demand ZIP archives |
| `demand_annual_summary.csv` | aggregate | Annual mean demand by NEM region (MW) |
| `demand_annual_summary.meta.json` | aggregate | Metadata for the summary (date range, row count) |
| `inspection_summary.txt` | inspect | Statistical summary of demand data |
| `aemo_demand-proxy_2026_nsw.gpkg` | demand.feature | Per-cell demand proxy on the common grid (EPSG:4326) |

### Grid (`DATA/grid/`)

| File | Stage | Description |
|------|-------|-------------|
| `nsw_analysis_grid.gpkg` | grid | NSW common analysis cell grid (GeoPackage, EPSG:4326) |
| `nsw_analysis_grid_metadata.json` | grid | Grid metadata (CRS, origin, cell count, area stats) |
| `decision_analysis_cell.md` | — | Architecture decision document (Option A selection) |

### Exclusion Layer (`DATA/exclusions/`) — S1-07

| File | Stage | Description |
|------|-------|-------------|
| `optmining_exclusions_2024_nsw.gpkg` | exclusions | Eligibility_Table: one row per grid `cell_id` with `eligible`, `exclusion_reason`, `triggered_rules`, the raw per-cell fields the rules evaluated (`protected_area`, `protected_area_name`, `slope_deg`, `urban_area`, `wind_speed_100m_ms`), and a non-exclusionary `data_flags` column (GeoPackage, EPSG:4326) |
| `metadata/exclusion_summary.md` | exclusions | Method report: exclusion summary stats (total/eligible/excluded, by-reason breakdown), the data-source coverage caveat, and the rule configuration used for that run |

**Scope note:** S1-06 (geographic features) and S1-03 (wind features) are now implemented and registered in `config.STAGES` (`geographic.features`, `wind.features`). However, this stage still reads the raw CAPAD, slope, ABS urban-centre and GWA wind-speed sources directly and recomputes the per-cell fields the rules need, rather than joining the S1-03/S1-06 Feature_Tables on `cell_id`. Migrating to that join is outstanding follow-up (see `pipeline/exclusions/__init__.py`). This matters functionally: the GWA wind-speed source read here covers only the New England REZ window, so ~45,711 of the 47,311 cells are excluded today with reason "Missing wind data" even though the NSW-wide `wind.features` table has a value for every cell. Until the migration lands, that exclusion count reflects the raw-source coverage read by this stage, not the true wind-data availability.

### Integrated NSW Feature Table (`DATA/integration/`) — S1-08 + S1-09

| File | Stage | Description |
|------|-------|-------------|
| `optmining_integrated-features_2026_nsw.gpkg` | integration | One row per grid `cell_id` (47,311), EPSG:4326, layer `integrated_features`: `cell_id, centroid_lat, centroid_lon, area_km2, wind_speed, wind_confidence, demand_proxy, source_region, demand_confidence, dist_transmission_km, dist_substation_km, dist_connection_km, inside_rez, rez_name, infra_confidence, elevation_m, slope_deg, tri, land_use, protected_area, protected_area_name, geo_confidence, eligible, exclusion_reason, triggered_rules, data_flags, n_missing_features, data_confidence, confidence_score, confidence_notes, geometry` (the last three are the S1-09 confidence layer) |
| `optmining_integrated-features_2026_nsw.csv` | integration | The same table without geometry — the deterministic artefact (byte-identical across reruns with unchanged inputs; the GeoPackage's hash drifts with its internal `last_change` timestamp) |
| `metadata/integration_method.md` | integration | Method report: join order, reproducibility (UTC timestamp, git commit), input SHA-256s, column map with units, null accounting, `n_missing_features` histogram, eligible/excluded counts, runtime |
| `metadata/merge_validation.md` | integration | Every validation check with expected vs observed values and PASS / FAIL / WARN |
| `metadata/confidence_method.md` | integration | S1-09 methodology: formula, per-feature weights with resolution and limitation factors and their data-spec bases, per-layer flag factors, soft flags, thresholds, what is deliberately not an input, config SHA-256 |
| `metadata/confidence_summary.md` | integration | S1-09 data-quality summary: counts and shares per level, score histogram, distinct score profiles, ranked reasons (all cells and eligible cells), eligibility cross-tab, lattice neighbour agreement, 1°×1° blocks, bounding boxes |
| `metadata/integration_manifest.json` | integration | `derived_features` record: output hashes and sizes, git commit, the six inputs with SHA-256 |
| `DATA_PROVENANCE.md` | integration | Generated derived-layer block (BEGIN/END markers) beneath the handwritten header |
| `integration_analysis.md` | — | Task 5 cross-domain analysis (Sprint 0, `pipeline.integration.analyse`) |

**Scope note:** the table carries the per-layer flags (`wind_confidence`, `demand_confidence`, `infra_confidence`, `geo_confidence`), an objective `n_missing_features` count (nulls among the ten scored feature columns) and, from S1-09, the composite `data_confidence` / `confidence_score` / `confidence_notes`. The composite is a weighted sum over the ten scored features of availability × resolution factor × known-limitation factor × upstream-flag factor, normalised by the weight sum, with thresholds high ≥ 0.8 and medium ≥ 0.5 (`pipeline/integration/confidence_weights.yaml`; formula and bases in `metadata/confidence_method.md`). On the committed data the distribution is high 1,600 / medium 45,711 / low 0 with five distinct scores: the 1,600 New-England-REZ-window cells (which include every eligible cell) score 0.830 and the rest of the state 0.633–0.699, because the geographic rasters and the connection-point distance are the missing evidence while the heavily weighted wind and GA distances are present statewide. The maximum attainable score under the defaults is 0.870. Confidence never excludes a cell; excluded cells are retained with `eligible = False`. The WARN cross-layer checks compare S1-07's own raster recomputation with the geographic and wind layers; on the committed data they report the known divergence that S1-07 samples the New-England-REZ wind clip while `wind.features` covers all of NSW (45,711 cells where only one side is null), plus 73 boundary cells whose means differ by more than 0.01 m/s.

### Baseline Suitability Score (`DATA/scoring/`) — S1-10

| File | Stage | Description |
|------|-------|-------------|
| `optmining_suitability-score_2026_nsw.gpkg` | scoring | One row per grid `cell_id` (47,311), EPSG:4326, layer `suitability_score`: `cell_id, centroid_lat, centroid_lon, suitability_score, rank, confidence, contrib_wind_speed, contrib_dist_transmission_km, contrib_demand_proxy, contrib_dist_substation_km, contrib_slope_deg, contrib_inside_rez, geometry`. One `contrib_{feature}` column per configured criterion, so the schema follows the weights file |
| `optmining_suitability-score_2026_nsw.csv` | scoring | The same table without geometry — the deterministic artefact (byte-identical across reruns with unchanged inputs) |
| `metadata/scoring_method.md` | scoring | Method report: the formula, every criterion with its weight, direction and rationale, the per-criterion normalisation bounds computed on that run, constant-criterion flags, the confidence-discount setting and factor map, eligible/excluded/confidence counts, the contribution reconciliation rule, documented deviations, input SHA-256s, git commit and runtime |
| `metadata/scoring_validation.md` | scoring | Every validation check with expected vs observed values and PASS / FAIL — no silent passes |
| `metadata/scoring_manifest.json` | scoring | `derived_features` record: output hashes and sizes, git commit, the integrated-table input, and the `weights_config_id` (SHA-256 of the weights file that produced the scores) |
| `metadata/source_register.csv` | scoring | Source-register row marking the scored table a derived product |
| `DATA_PROVENANCE.md` | scoring | Generated derived-layer block (BEGIN/END markers) recording inputs, weights, method and hashes |

**Scope note:** the score is a weighted MCDA over criteria normalised to [0, 1] from the **eligible** cell population, not a fitted or learned model — no parameter in it comes from anywhere but the weights YAML and the run's own data. On the committed data 1,233 of 47,311 cells are eligible and scored (scores 0.218–0.932, mean 0.646) and 46,078 carry a null score and no rank. Two properties of the current data are worth knowing before reading a shortlist. First, `demand_proxy` is **constant** across every eligible cell (the MVP proxy allocates one NEM-region value uniformly), so it adds a flat 0.15 to every score and cannot discriminate between cells — the ranking is effectively driven by the other five criteria, and the method report flags this on every run. Second, every eligible cell is `high` confidence, so the optional confidence discount would be an identical multiplier on every scored cell; it is disabled by default for that reason. Excluded cells are retained with a null score rather than dropped, so the table still joins one-to-one to the grid.

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
| Exclusions | `pipeline.exclusions.apply.validate` | Row count == grid cell count; exact `cell_id` set match; required output columns present; `eligible`/`exclusion_reason` consistency; eligible + excluded == total |
| Integration | `pipeline.integration.merge.validate` | Per-input CRS == EPSG:4326; per layer: `cell_id` set match, row count and null counts unchanged after the left join; final row count == grid; `cell_id` unique and in grid order; geometry identical to grid; column order; `eligible` boolean + `eligible`/`exclusion_reason` consistency; `n_missing_features` recount; confidence vocabularies; S1-09: confidence columns present, `confidence_score` in [0, 1] with no nulls, `data_confidence` vocabulary and consistency with the thresholds, non-empty `confidence_notes`, full recount via `confidence.assess()`; WARN cross-layer consistency vs S1-07; GeoPackage/CSV read-back |

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

**Supported Python: 3.13 only. Do not use Python 3.14.** The project
standardises on Python 3.13 — the single interpreter CI tests — so the
supported version and the verified version are the same. On CPython 3.14.x the
S1-02 grid builder (`pipeline/grid/generate.py`) produces degenerate zero-area
cells — every analysis cell collapses to a point, breaking the grid and every
feature layer that joins to it. The same source, `numpy==2.2.6` and
`shapely==2.1.2` build a correct 47,311-cell grid on Python 3.13, so the
fault is in the 3.14 interpreter, not this code. `pyproject.toml`
(`requires-python = ">=3.13,<3.14"`) enforces this for pip.

```
pandas>=2.2
requests>=2.32
rasterio>=1.4
numpy>=2.2
geopandas>=1.1
shapely>=2.1
pyogrio>=0.13
pyproj>=3.7
pyyaml>=6.0
```

See `requirements.txt` for pinned versions. GeoPandas and its spatial stack were introduced at S1-02 (grid generation) and are used by all downstream feature-layer tasks (S1-03–S1-08).

## Frozen Decisions (resolved 2026-08-27)

These questions arose from the Task 5 integration analysis. They were resolved by team consensus and **frozen** in `DATA/data-specification/sprint1_data_specification.md` §2 (decisions Q1–Q7). Changes now follow the specification's change-control process (§8). The table below is the decision record.

| # | Question | Decision |
|---|----------|----------|
| 1 | Wind aggregation statistic for 250 m → 5 km cells? | **Mean** — single stable statistic; report P90 as a feature and max as a "best micro-site" indicator in explanation. |
| 2 | Primary hub height for scoring? | **100 m** — consistent with the capacity-factor layers; 150 m carried as a sensitivity layer only. |
| 3 | Slope aggregation statistic per cell? | **Mean for scoring; P90 in explanation.** Evidence: exclusion varies 11.6% (mean) to 42.1% (p90) to 85.7% (max) at a 10° threshold. |
| 4 | Population data source for demand allocation? | **ABS Census 2021 ERP at SA2 level** — sufficient resolution for a ~5 km grid, simpler than mesh block. |
| 5 | Operational or total demand? | **Operational demand** — grid-served load, the load new generation must serve (excludes behind-the-meter PV). |
| 6 | Hard exclusion threshold for protected areas? | **Binary** — any CAPAD intersection excludes the cell. |
| 7 | Infrastructure distance hard exclusion? | **No hard exclusion for V1** — continuous distance penalty only; remote cells rank low naturally. |
