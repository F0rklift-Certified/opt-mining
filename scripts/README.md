# Full-NSW coverage fix — fetch/build runners

These runners close the S2-02 data-quality warning the decision service raises:

```
Missing-value count: demand_proxy       observed 6,637
Missing-value count: dist_connection_km observed 47,311
Missing-value count: elevation_m        observed 45,711
Missing-value count: slope_deg          observed 45,711
Missing-value count: land_use           observed 45,240
```

The root cause is upstream **source coverage**, not a pipeline bug: the geographic
rasters were only ever clipped to the New England REZ, and the AEMO KCI connection
workbook carries no coordinates. These scripts re-run the frozen pipeline over full
NSW with **real** data and never fabricate values — any cell a real source does not
cover stays null.

Run everything with the workspace virtualenv:

```bash
.venv/bin/python -m scripts.<name>          # system python has no geo deps
```

## Prerequisites

- The analysis grid must exist: `python -m pipeline --only grid`.
- Network access to OpenTopography (SRTM VRT) and ABARES (NLUM zip, ~64 MB).
- **Data size:** a full-NSW SRTM/NLUM clip is far larger than the committed New
  England samples and exceeds the repo's 10 MB commit guardrail. Treat the
  `*_nsw.tif` rasters as regenerable local artefacts — add them to `.gitignore`,
  do not commit them.

## Step 1 — geographic (elevation_m, slope_deg, land_use)

```bash
.venv/bin/python -m scripts.fetch_build_geographic_nsw --verbose
```

Downloads the national SRTM GL3 + ABARES NLUM rasters and clips them to the full
NSW grid extent, derives the NSW Horn-slope raster with the frozen algorithm, then
re-runs the geographic feature builder over NSW. Re-writes
`DATA/geographic/features/optmining_geographic-features_2024_nsw.gpkg`.

SRTM and NLUM are national/global products, so this should drop the missing-value
counts for `elevation_m`, `slope_deg` and `land_use` to ~0 (any residual nulls are
genuine no-data pixels, e.g. offshore, and are left null).

> `--skip-download` / `--skip-derive` reuse existing NSW rasters.

## Step 2 — connection points (dist_connection_km) — needs a confirmed source

The KCI workbook has **no coordinates** (9,348 rows, only names and free-text
locations). This script will not invent any. Inspect first:

```bash
.venv/bin/python -m scripts.fetch_connection_point_geometry --inspect
```

Then supply ONE real geometry source:

```bash
# Preferred: coordinates you obtained from an authoritative source
.venv/bin/python -m scripts.fetch_connection_point_geometry --coords-csv path/to/coords.csv

# Or a GIS endpoint you confirm serves connection-point geometry
.venv/bin/python -m scripts.fetch_connection_point_geometry --aemo-gis-url "https://.../FeatureServer/0"

# Or a COARSE, opt-in approximation: borrow GA substation coords by locality/name
.venv/bin/python -m scripts.fetch_connection_point_geometry --match-substations
```

It writes `DATA/infrastructure/connection-points/aemo_kci_2026_geocoded.csv` with
`latitude`/`longitude` + provenance columns. To make the builder use it, set in
`pipeline/infrastructure/config.py`:

```python
CONNECTION_POINTS_PATH = INFRA_DIR / "connection-points" / "aemo_kci_2026_geocoded.csv"
```

then rebuild infrastructure features:

```bash
.venv/bin/python -m pipeline --only infrastructure.features
```

> If you have no real source, skip this step. `dist_connection_km` will remain null
> — which is the honest state. Note S2-01 classifies `dist_connection_km` as a
> **context column, not a scored criterion**, so leaving it null does not affect the
> ranking; if you want the warning to clear without a geometry source, the correct
> route is the S2-02 contract change (making Check 9 skip context-only columns),
> which is a spec decision, not a data patch.

## Step 3 — re-freeze + re-validate

```bash
.venv/bin/python -m scripts.refreeze_revalidate --verbose
```

Re-runs integration (S1-08) to rebuild the integrated table from the regenerated
layers, **re-freezes** the baseline (records the rebuilt file's new SHA-256 — the
"baseline hash matches the frozen reference" check would otherwise fail on a
legitimately-updated dataset), and re-validates, re-writing
`DATA/integration/metadata/integrated_input_validation.json` — the exact sidecar
the decision service reads for its banner. It prints a before/after of the five
missing-value checks and the overall `all_passed` verdict.

When coverage is closed the previously-failing checks pass and the service banner
clears. Any check that still fails reflects real remaining gaps and is reported
honestly — nothing is fabricated to force a pass.

## What was changed in the pipeline itself

Only one, backward-compatible change: `pipeline/geographic/features.py::run()` now
accepts optional keyword source-path overrides (`elevation_path`, `slope_path`,
`nlum_path`, etc.), all defaulting to the existing New-England constants. Every
existing caller — including `python -m pipeline --only geographic` and all tests —
is unaffected (53 geographic-feature tests pass). No frozen data file or scoring
logic was mutated.
