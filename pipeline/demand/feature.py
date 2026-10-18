"""S1-04 demand feature layer.

Allocates AEMO NEM-region annual mean demand to the common analysis grid.
The MVP uses deterministic uniform allocation; outputs are proxies, not
measurements of local electricity consumption.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import geopandas as gpd
import pandas as pd
from ..common.geo import atomic_write_text, utc_now
from . import config


def _repo_relative(path: Path) -> str:
    """Return a portable repository-relative path for generated artifacts."""
    path = Path(path)
    try:
        return path.resolve().relative_to(config.PROJECT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def load_grid(path: Path) -> gpd.GeoDataFrame:
    if not Path(path).exists():
        raise FileNotFoundError(path)
    gdf = gpd.read_file(path)
    if "cell_id" not in gdf.columns:
        raise ValueError(f"Grid {path} is missing cell_id")
    if gdf["cell_id"].duplicated().any():
        dup = gdf.loc[gdf["cell_id"].duplicated(), "cell_id"].head().tolist()
        raise ValueError(f"Grid {path} has duplicate cell_id values: {dup}")
    if gdf.crs is None:
        raise ValueError(f"Grid {path} has no CRS")
    return gdf


def load_aggregate(path: Path) -> pd.DataFrame:
    if not Path(path).exists():
        raise FileNotFoundError(path)
    try:
        df = pd.read_csv(path)
    except Exception as exc:
        raise ValueError(f"Could not read demand aggregate {path}: {exc}") from exc
    required = {"REGIONID", config.DEMAND_INPUT_COLUMN}
    if not required.issubset(df.columns):
        raise ValueError(f"Demand aggregate {path} must contain {sorted(required)}")
    df[config.DEMAND_INPUT_COLUMN] = pd.to_numeric(df[config.DEMAND_INPUT_COLUMN], errors="coerce")
    if df[config.DEMAND_INPUT_COLUMN].isna().any():
        raise ValueError(f"Demand aggregate {path} contains non-numeric demand values")
    if df["REGIONID"].duplicated().any():
        raise ValueError(f"Demand aggregate {path} has duplicate REGIONID values")
    return df


def load_nem_regions(path: Path) -> gpd.GeoDataFrame:
    if not Path(path).exists():
        raise FileNotFoundError(path)
    try:
        gdf = gpd.read_file(path)
    except Exception as exc:
        raise ValueError(f"Could not read NEM geometry {path}: {exc}") from exc
    if "REGIONID" not in gdf.columns:
        if "nem_region" in gdf.columns:
            gdf = gdf.rename(columns={"nem_region": "REGIONID"})
        else:
            raise ValueError(f"NEM geometry {path} is missing REGIONID")
    if gdf.crs is None:
        raise ValueError(f"NEM geometry {path} has no resolvable CRS")
    # The derived national layer contains a few self-intersections; repair
    # them deterministically before spatial allocation.
    invalid = ~gdf.geometry.is_valid
    if invalid.any():
        gdf.loc[invalid, "geometry"] = gdf.loc[invalid, "geometry"].make_valid()
    return gdf


def assign_source_region(grid_3577: gpd.GeoDataFrame, regions_3577: gpd.GeoDataFrame) -> pd.Series:
    """Assign each cell using centroid containment, then overlap tie-break."""
    regions = regions_3577[["REGIONID", "geometry"]].copy()
    out = pd.Series(pd.NA, index=grid_3577.index, dtype="object")
    centroids = grid_3577.geometry.centroid
    for idx, point in centroids.items():
        containing = regions[regions.geometry.contains(point)]
        if len(containing):
            out.loc[idx] = sorted(containing["REGIONID"].astype(str))[0]
            continue
        intersects = regions[regions.geometry.intersects(grid_3577.geometry.loc[idx])].copy()
        if len(intersects):
            intersects["_area"] = intersects.geometry.intersection(grid_3577.geometry.loc[idx]).area
            max_area = intersects["_area"].max()
            tied = intersects[intersects["_area"] == max_area]
            out.loc[idx] = sorted(tied["REGIONID"].astype(str))[0]
    return out


def load_urban_weights(path: Path) -> gpd.GeoDataFrame:
    """Load the ABS UCL urban-centre/locality layer used for demand weighting.

    Mirrors ``pipeline.geographic.features._load_urban``: a missing or unreadable
    source **halts loudly** naming the path, so a missing UCL extract can never
    silently fall back to uniform allocation. The returned GeoDataFrame carries
    ``sos_code_2021`` (to drop the "Rural Balance" catch-all) and
    ``sosr_name_2021`` (ordinal population band) in its declared CRS.
    """
    path = Path(path)
    if not path.exists():
        raise RuntimeError(
            f"Urban-weighting (ABS UCL) source is missing: {path}. The statewide "
            f"urban extract must be present for urban_weighted demand allocation; "
            f"allocation is never silently defaulted to uniform for a missing source."
        )
    try:
        return gpd.read_file(path)
    except Exception as exc:  # unreadable / corrupt urban source
        raise RuntimeError(
            f"Urban-weighting (ABS UCL) source could not be read: {path} ({exc})"
        ) from exc


def compute_cell_weights(grid_3577: gpd.GeoDataFrame, urban_3577: gpd.GeoDataFrame, source_region: pd.Series) -> pd.Series:
    """Per-cell urban-footprint weight for ``urban_weighted`` allocation.

    Mirrors ``pipeline.geographic.features._urban_overlap``: drop SOS code "13"
    (Rural Balance), use ``gpd.sjoin(predicate="intersects")`` in EPSG:3577 to
    find candidate polygons, then compute the actual intersection *area* per
    cell (not a boolean), scaled by the ordinal ``sosr_name_2021`` band
    multiplier. ``config.DEMAND_WEIGHT_FLOOR`` is added to every **assigned**
    cell (``source_region`` not null) so no assigned cell has zero weight.

    Returns a float Series indexed like ``grid_3577``/``source_region``:
    ``NaN`` for cells outside any region (not assigned), otherwise
    ``overlap_area_weighted + floor`` (always >= floor for assigned cells).
    Deterministic: intersection contributions are summed in a fixed
    (cell_id, polygon) order so floating-point results are reproducible.
    """
    index = grid_3577.index
    # Assigned cells (inside a region) start at the floor; outside-region cells
    # stay NaN so allocate_demand leaves them null (confidence low downstream).
    assigned_mask = source_region.notna()
    weights = pd.Series(float("nan"), index=index, dtype="float64")
    weights.loc[assigned_mask] = float(config.DEMAND_WEIGHT_FLOOR)

    urban = urban_3577
    if "sos_code_2021" in urban.columns:
        urban = urban[~urban["sos_code_2021"].isin(config.URBAN_EXCLUDE_SOS_CODES)]

    if len(urban) == 0:
        return weights

    # Repair any self-intersecting UCL polygons deterministically before the
    # intersection-area computation (mirrors load_nem_regions); an invalid input
    # geometry otherwise triggers a shapely TopologyException.
    urban = urban.copy()
    invalid = ~urban.geometry.is_valid
    if invalid.any():
        urban.loc[invalid, "geometry"] = urban.loc[invalid, "geometry"].make_valid()

    cells = grid_3577[["cell_id", "geometry"]].copy()
    cells["cell_index"] = index
    urban_cols = ["geometry"]
    if "sosr_name_2021" in urban.columns:
        urban_cols = ["geometry", "sosr_name_2021"]
    urban = urban[urban_cols].reset_index(drop=True)
    urban["urban_index"] = urban.index

    joined = gpd.sjoin(cells, urban, how="inner", predicate="intersects")
    if len(joined) == 0:
        return weights

    # Deterministic iteration order (cell_id, then polygon index) so the
    # floating-point accumulation of overlap areas is reproducible.
    joined = joined.sort_values(["cell_id", "urban_index"], kind="mergesort")

    cell_geoms = grid_3577.geometry
    urban_geoms = urban.geometry
    has_band = "sosr_name_2021" in urban_cols
    overlap = pd.Series(0.0, index=index, dtype="float64")
    for row in joined.itertuples(index=False):
        cell_idx = row.cell_index
        urban_idx = row.urban_index
        inter = cell_geoms.loc[cell_idx].intersection(urban_geoms.loc[urban_idx])
        area = float(inter.area)
        if area <= 0:
            continue
        band = row.sosr_name_2021 if has_band else None
        multiplier = config.SOSR_WEIGHT_MULTIPLIERS.get(band, config.SOSR_DEFAULT_MULTIPLIER)
        overlap.loc[cell_idx] += area * float(multiplier)

    # Add the overlap weight only to assigned cells (outside-region cells stay
    # NaN and never participate in a region's allocation).
    weights.loc[assigned_mask] = weights.loc[assigned_mask] + overlap.loc[assigned_mask]
    return weights


def allocate_demand(source_region: pd.Series, region_demand: pd.Series, method: str = "uniform", weights=None) -> pd.Series:
    if method not in config.ALLOCATION_METHODS:
        raise NotImplementedError(
            f"Unsupported allocation method {method!r}; expected one of {config.ALLOCATION_METHODS}"
        )
    result = pd.Series(float("nan"), index=source_region.index, dtype="float64")
    if method == "uniform":
        counts = source_region.dropna().value_counts()
        for region, count in counts.items():
            if region in region_demand.index and count:
                result.loc[source_region == region] = float(region_demand.loc[region]) / count
        return result

    # urban_weighted: distribute each region's demand by per-cell weight,
    #   raw[cell] = weights[cell] / sum(weights in region) * region_demand[region]
    # which conserves each region's total exactly.
    if weights is None:
        raise ValueError("urban_weighted allocation requires a per-cell weights Series")
    for region in source_region.dropna().unique():
        if region not in region_demand.index:
            continue
        mask = (source_region == region) & weights.notna()
        total_weight = float(weights.loc[mask].sum())
        if total_weight <= 0:
            continue
        result.loc[mask] = weights.loc[mask] / total_weight * float(region_demand.loc[region])
    return result


def normalise_proxy(raw_mw: pd.Series, source_region: pd.Series) -> pd.Series:
    result = pd.Series(float("nan"), index=raw_mw.index, dtype="float64")
    for region in source_region.dropna().unique():
        mask = source_region == region
        max_value = raw_mw.loc[mask].max()
        if pd.notna(max_value) and max_value > 0:
            result.loc[mask] = raw_mw.loc[mask] / max_value
    return result.clip(0, 1)


def assign_confidence(source_region: pd.Series, proxy: pd.Series, boundary_indices=None, floored_indices=None) -> pd.Series:
    result = pd.Series("low", index=source_region.index, dtype="object")
    valid = source_region.notna() & proxy.notna()
    result.loc[valid] = "high"
    if boundary_indices is not None:
        result.loc[result.index.intersection(boundary_indices)] = "medium"
    # Cells allocated purely on the floor (no real urban overlap) are assigned
    # but weakly supported -> downgrade high to medium. `low` stays reserved for
    # null-proxy / outside-region so the persisted "Null proxy confidence" check
    # still holds.
    if floored_indices is not None:
        floored = result.index.intersection(floored_indices)
        downgrade = floored[result.loc[floored] == "high"]
        result.loc[downgrade] = "medium"
    return result


def build_feature_table(grid: gpd.GeoDataFrame, proxy: pd.Series, method: str, source_region: pd.Series, confidence: pd.Series) -> gpd.GeoDataFrame:
    source_values = source_region.astype(object).where(source_region.notna(), None)
    out = gpd.GeoDataFrame({
        "cell_id": grid["cell_id"].tolist(),
        "demand_proxy": proxy.to_numpy(),
        "allocation_method": method,
        "source_region": source_values.to_numpy(),
        "confidence_flag": confidence.to_numpy(),
    }, geometry=grid.geometry.copy(), crs=grid.crs)
    return out.to_crs(config.STORAGE_CRS)


def write_feature_table(gdf: gpd.GeoDataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + ".tmp" + path.suffix)
    try:
        gdf.to_file(tmp, layer=config.FEATURE_TABLE_LAYER, driver="GPKG", index=False)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def write_method_report(stats: dict, path: Path) -> None:
    method = stats.get("allocation_method", config.DEFAULT_ALLOCATION_METHOD)
    header = [
        "# Demand Feature Layer Method Report", "", f"*Generated by `pipeline.demand.feature` on {utc_now()}. Do not edit by hand.*", "",
    ]
    if method == "urban_weighted":
        method_block = [
            "## Method", "Urban-footprint weighted allocation (ABS UCL 2021).", "",
            "`raw_cell_demand_MW = (w_cell / Σ w_region) × MEAN_DEMAND_MW_region`", "",
            "where `w_cell = urban-overlap area (EPSG:3577) × SOSR band multiplier + floor`.",
            "Each region's demand is distributed across its cells in proportion to the",
            "urban footprint of each cell, so the sum of per-cell raw demand within a",
            "region still equals that region's annual mean (conservation is exact).", "",
            "`demand_proxy` is the per-region max-normalised `raw_cell_demand_MW`; it is a",
            "normalized proxy indicator, not measured local demand.", "",
            "## Assumptions and limitations",
            "- Demand is distributed by urban footprint; urban footprint is NOT measured local electricity demand.",
            "- The SOSR→weight multipliers and the non-urban floor are modelling choices (currently all band multipliers are 1.0, i.e. a footprint-only baseline).",
            "- ABS UCL Section-of-State code 13 (Rural Balance) is excluded before the overlap.",
            "- Cells with no urban overlap carry only the floor weight and are flagged `medium` (assigned but weakly supported).",
            "- A region with no urban overlap at all degrades gracefully to uniform allocation within that region.",
            "- NSW1 represents NSW and ACT under the NEM convention.",
            "- Cells outside all NEM polygons receive null demand and low confidence.", "",
            "## Inputs",
            f"- Demand aggregate: `{stats['aggregate_path']}`; column `MEAN_DEMAND_MW` (MW).",
            f"- NEM region geometry: `{stats['regions_path']}`.",
            f"- Analysis grid: `{stats['grid_path']}`.",
            f"- Urban weighting dataset (ABS UCL 2021): `{stats.get('weighting_path', '')}` (sha256 `{stats.get('weighting_sha256', '')}`).", "",
            "## Reproducibility and checks",
            f"- Storage CRS: {config.STORAGE_CRS}; computation CRS: {config.COMPUTATION_CRS}.",
            f"- CRS transform: grid and UCL {config.STORAGE_CRS} → {config.COMPUTATION_CRS} for overlap-area and allocation; output stored in {config.STORAGE_CRS}.",
            f"- Non-urban weight floor: {stats.get('demand_weight_floor')}.",
            f"- SOSR band multipliers: `{json.dumps(stats.get('sosr_weight_multipliers', {}), sort_keys=True)}`.",
            f"- Per-region demand_proxy spread (min/median/max, nunique): `{json.dumps(stats.get('proxy_spread', {}), sort_keys=True)}`.",
            f"- Floored (non-urban) assigned cells: {stats.get('floored_cell_count', 0)}.",
            f"- Cells: {stats['n_cells']}; outside-region: {stats['n_outside_region']}; boundary/tie-break candidates: {stats['boundary_cell_count']}.",
            f"- Per-region counts: `{json.dumps(stats['per_region_counts'], sort_keys=True)}`.",
            f"- Confidence counts: `{json.dumps(stats['confidence_counts'], sort_keys=True)}`.",
            "- Confidence definitions: high = assigned cell with real urban overlap and valid proxy; medium = deterministic boundary-overlap fallback OR floored (non-urban) assigned cell; low = outside/unmatched region or null proxy.",
            "- Boundary assignments use centroid containment, then greatest overlap and lexicographic REGIONID tie-break.",
            f"- Aggregate regions outside this grid scope are explicitly reported: `{json.dumps(stats['unassigned_regions'])}`.",
        ]
    else:
        method_block = [
            "## Method", "Uniform regional allocation.", "", "`raw_cell_demand_MW = MEAN_DEMAND_MW_region / N_cells_region`", "",
            "`demand_proxy` is a normalized proxy indicator, not measured local demand; the input is a regional aggregate.", "",
            "## Assumptions and limitations", "- Every assigned cell within a NEM region receives an equal share of that region's annual mean demand.", "- NSW1 represents NSW and ACT under the NEM convention.", "- Cells outside all NEM polygons receive null demand and low confidence.", "- Uniform allocation does not represent local load centres or feeder constraints.", "",
            "## Inputs", f"- Demand aggregate: `{stats['aggregate_path']}`; column `MEAN_DEMAND_MW` (MW).", f"- NEM region geometry: `{stats['regions_path']}`.", f"- Analysis grid: `{stats['grid_path']}`.", "- No weighting dataset is used under uniform allocation.", "",
            "## Reproducibility and checks", f"- Storage CRS: {config.STORAGE_CRS}; computation CRS: {config.COMPUTATION_CRS}.", f"- CRS transform: grid {config.STORAGE_CRS} → {config.COMPUTATION_CRS} for spatial allocation; output stored in {config.STORAGE_CRS}.", f"- Cells: {stats['n_cells']}; outside-region: {stats['n_outside_region']}; boundary/tie-break candidates: {stats['boundary_cell_count']}.", f"- Per-region counts: `{json.dumps(stats['per_region_counts'], sort_keys=True)}`.", f"- Confidence counts: `{json.dumps(stats['confidence_counts'], sort_keys=True)}`.", "- Confidence definitions: high = centroid-assigned cell with valid proxy; medium = deterministic boundary-overlap fallback; low = outside/unmatched region or null proxy.", "- Boundary assignments use centroid containment, then greatest overlap and lexicographic REGIONID tie-break.", f"- Aggregate regions outside this grid scope are explicitly reported: `{json.dumps(stats['unassigned_regions'])}`.",
        ]
    atomic_write_text(path, "\n".join(header + method_block) + "\n")


def validate_feature_table(table: gpd.GeoDataFrame, grid: gpd.GeoDataFrame, source: pd.Series, raw: pd.Series, aggregate: pd.DataFrame) -> dict:
    """No-silent-pass checks used immediately before writing outputs."""
    required = ["cell_id", "demand_proxy", "allocation_method", "source_region", "confidence_flag"]
    checks = {
        "row_count": len(table) == len(grid),
        "cell_id_set": set(table.cell_id) == set(grid.cell_id) and table.cell_id.is_unique,
        "schema": table.columns.tolist() == required + ["geometry"],
        "proxy_range": table.demand_proxy.dropna().between(0, 1).all(),
        "source_regions": set(table.source_region.dropna()).issubset(set(aggregate.REGIONID)),
        "confidence_enum": set(table.confidence_flag.dropna()).issubset(set(config.CONFIDENCE_LEVELS)),
    }
    expected = aggregate.set_index("REGIONID")[config.DEMAND_INPUT_COLUMN]
    observed = raw.groupby(source).sum(min_count=1)
    missing_regions = [str(r) for r in expected.index if r not in observed.index and float(expected.loc[r]) != 0.0]
    checks["demand_conservation"] = not missing_regions and all(
        abs(float(observed.loc[r]) - float(v)) <= config.CONSERVATION_TOLERANCE_MW
        for r, v in expected.items()
    )
    if missing_regions:
        raise ValueError(
            "Feature table validation failed: demand_conservation "
            f"(missing observed regions with non-zero demand: {missing_regions})"
        )
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise ValueError("Feature table validation failed: " + ", ".join(failed))
    return checks


def record_provenance(feature_path: Path, stats: dict) -> None:
    meta_dir = config.OUTPUT_DIR / "metadata"
    meta_dir.mkdir(parents=True, exist_ok=True)
    prov = config.OUTPUT_DIR / "DATA_PROVENANCE.md"
    method_label = stats.get("allocation_method", config.DEFAULT_ALLOCATION_METHOD)
    if method_label == "urban_weighted":
        method_cell = "Urban-footprint weighted allocation (ABS UCL 2021)"
        inputs_cell = "AEMO demand aggregate + NEM region geometry + ABS UCL 2021 urban footprint"
    else:
        method_cell = "Uniform allocation"
        inputs_cell = "AEMO demand aggregate + NEM region geometry"
    row = f"| demand.feature | {feature_path.name} | {inputs_cell} | {method_cell} | Derived proxy indicator; not measured local demand |"
    if prov.exists():
        text = prov.read_text()
        existing_lines = text.rstrip("\n").split("\n")
        # Replace any existing row for this output so the Method cell reflects the
        # current allocation method; otherwise append a fresh row.
        replaced = False
        for i, line in enumerate(existing_lines):
            if line.startswith("| demand.feature |") and f"| {feature_path.name} |" in line:
                existing_lines[i] = row
                replaced = True
                break
        if replaced:
            atomic_write_text(prov, "\n".join(existing_lines) + "\n")
        else:
            atomic_write_text(prov, "\n".join(existing_lines) + "\n" + row + "\n")
    else:
        atomic_write_text(prov, "# Electricity Demand Data Provenance\n\n| Stage | Output | Inputs | Method | Notes |\n|---|---|---|---|---|\n" + row + "\n")
    digest = hashlib.sha256(feature_path.read_bytes()).hexdigest()
    manifest = meta_dir / config.FEATURE_MANIFEST_NAME
    obj = json.loads(manifest.read_text()) if manifest.exists() else {}
    obj[feature_path.name] = {"sha256": digest, "bytes": feature_path.stat().st_size, "utc": utc_now(), "derived_proxy": True}
    atomic_write_text(manifest, json.dumps(obj, indent=2) + "\n")


def _proxy_spread(proxy: pd.Series, source_region: pd.Series) -> dict:
    """Per-region demand_proxy spread (nunique, min, median, max) for reporting."""
    spread: dict = {}
    for region in sorted(source_region.dropna().astype(str).unique()):
        mask = source_region.astype(object) == region
        values = proxy.loc[mask].dropna()
        if len(values) == 0:
            continue
        spread[region] = {
            "nunique": int(values.nunique()),
            "min": round(float(values.min()), 6),
            "median": round(float(values.median()), 6),
            "max": round(float(values.max()), 6),
        }
    return spread


def run(verbose: bool = False, allocation_method: str | None = None, grid_path: Path | None = None, aggregate_path: Path | None = None, nem_regions_path: Path | None = None, weighting_path: Path | None = None) -> dict:
    allocation_method = allocation_method or config.DEFAULT_ALLOCATION_METHOD
    if allocation_method not in config.ALLOCATION_METHODS:
        raise NotImplementedError(
            f"Unsupported allocation_method {allocation_method!r}; expected one of {config.ALLOCATION_METHODS}"
        )
    grid_path = Path(grid_path or config.GRID_PATH)
    aggregate_path = Path(aggregate_path or (config.OUTPUT_DIR / config.AGGREGATED_CSV_NAME))
    nem_regions_path = Path(nem_regions_path or config.NEM_REGIONS_PATH)
    weighting_path = Path(weighting_path or config.URBAN_WEIGHTS_PATH)
    grid = load_grid(grid_path)
    aggregate = load_aggregate(aggregate_path)
    regions = load_nem_regions(nem_regions_path)
    grid_3577 = grid.to_crs(config.COMPUTATION_CRS)
    regions_3577 = regions.to_crs(config.COMPUTATION_CRS)
    source = assign_source_region(grid_3577, regions_3577)
    centroids = grid_3577.geometry.centroid
    boundary_indices = []
    for idx, point in centroids.items():
        if not regions_3577.geometry.contains(point).any() and regions_3577.geometry.intersects(grid_3577.geometry.loc[idx]).any():
            boundary_indices.append(idx)
    demand = aggregate.set_index("REGIONID")[config.DEMAND_INPUT_COLUMN]

    weights = None
    floored_indices = None
    urban_weights_sha = None
    if allocation_method == "urban_weighted":
        urban_gdf = load_urban_weights(weighting_path)  # hard-fail if missing
        urban_weights_sha = hashlib.sha256(Path(weighting_path).read_bytes()).hexdigest()
        urban_3577 = urban_gdf.to_crs(config.COMPUTATION_CRS)
        weights = compute_cell_weights(grid_3577, urban_3577, source)
        # Floored cells: assigned (not null weight) but carrying only the floor
        # (no real urban overlap) -> weakly supported, downgraded to medium.
        assigned = weights.notna()
        floored_mask = assigned & (weights <= float(config.DEMAND_WEIGHT_FLOOR))
        floored_indices = list(weights.index[floored_mask])

    raw = allocate_demand(source, demand, allocation_method, weights)
    proxy = normalise_proxy(raw, source)
    confidence = assign_confidence(source, proxy, boundary_indices, floored_indices)
    table = build_feature_table(grid, proxy, allocation_method, source, confidence)
    output_path = config.OUTPUT_DIR / config.FEATURE_TABLE_NAME
    report_path = config.OUTPUT_DIR / config.METHOD_REPORT_NAME
    assigned_regions = set(source.dropna().astype(str))
    scoped_aggregate = aggregate[aggregate["REGIONID"].astype(str).isin(assigned_regions)].copy()
    validate_feature_table(table, grid, source, raw, scoped_aggregate)
    stats = {"grid_path": _repo_relative(grid_path), "aggregate_path": _repo_relative(aggregate_path), "regions_path": _repo_relative(nem_regions_path), "allocation_method": allocation_method, "n_cells": len(table), "n_outside_region": int(source.isna().sum()), "boundary_cell_count": len(boundary_indices), "per_region_counts": {str(k): int(v) for k, v in source.value_counts(dropna=True).items()}, "confidence_counts": {str(k): int(v) for k, v in confidence.value_counts().items()}, "unassigned_regions": sorted(set(aggregate["REGIONID"].astype(str)) - assigned_regions), "proxy_spread": _proxy_spread(proxy, source)}
    if allocation_method == "urban_weighted":
        stats["weighting_path"] = _repo_relative(weighting_path)
        stats["weighting_sha256"] = urban_weights_sha
        stats["demand_weight_floor"] = float(config.DEMAND_WEIGHT_FLOOR)
        stats["sosr_weight_multipliers"] = dict(config.SOSR_WEIGHT_MULTIPLIERS)
        stats["floored_cell_count"] = len(floored_indices) if floored_indices is not None else 0
    write_feature_table(table, output_path)
    from .validate import validate_feature_table as validate_persisted_feature_table
    persisted_validation = validate_persisted_feature_table(output_path, grid_path, aggregate_path)
    if not persisted_validation.passed:
        failed = [name for name, passed, _ in persisted_validation.details if not passed]
        raise ValueError("Persisted demand feature validation failed: " + ", ".join(failed))
    write_method_report(stats, report_path)
    record_provenance(output_path, stats)
    if verbose:
        print(f"  Demand feature output: {output_path} ({len(table):,} cells)")
    return {"feature_table_path": output_path, "method_report_path": report_path, "allocation_method": allocation_method, **{k: v for k, v in stats.items() if k not in {"grid_path", "aggregate_path", "regions_path"}}}
