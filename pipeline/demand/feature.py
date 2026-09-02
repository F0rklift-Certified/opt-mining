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
from shapely.geometry import Point

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


def allocate_demand(source_region: pd.Series, region_demand: pd.Series, method: str = "uniform", weights=None) -> pd.Series:
    if method != "uniform":
        raise NotImplementedError("Only uniform allocation is implemented in the S1-04 MVP")
    counts = source_region.dropna().value_counts()
    result = pd.Series(float("nan"), index=source_region.index, dtype="float64")
    for region, count in counts.items():
        if region in region_demand.index and count:
            result.loc[source_region == region] = float(region_demand.loc[region]) / count
    return result


def normalise_proxy(raw_mw: pd.Series, source_region: pd.Series) -> pd.Series:
    result = pd.Series(float("nan"), index=raw_mw.index, dtype="float64")
    for region in source_region.dropna().unique():
        mask = source_region == region
        max_value = raw_mw.loc[mask].max()
        if pd.notna(max_value) and max_value > 0:
            result.loc[mask] = raw_mw.loc[mask] / max_value
    return result.clip(0, 1)


def assign_confidence(source_region: pd.Series, proxy: pd.Series, boundary_indices=None) -> pd.Series:
    result = pd.Series("low", index=source_region.index, dtype="object")
    valid = source_region.notna() & proxy.notna()
    result.loc[valid] = "high"
    if boundary_indices is not None:
        result.loc[result.index.intersection(boundary_indices)] = "medium"
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
    lines = [
        "# Demand Feature Layer Method Report", "", f"*Generated by `pipeline.demand.feature` on {utc_now()}. Do not edit by hand.*", "",
        "## Method", "Uniform regional allocation.", "", "`raw_cell_demand_MW = MEAN_DEMAND_MW_region / N_cells_region`", "",
        "`demand_proxy` is a normalized proxy indicator, not measured local demand; the input is a regional aggregate.", "",
        "## Assumptions and limitations", "- Every assigned cell within a NEM region receives an equal share of that region's annual mean demand.", "- NSW1 represents NSW and ACT under the NEM convention.", "- Cells outside all NEM polygons receive null demand and low confidence.", "- Uniform allocation does not represent local load centres or feeder constraints.", "",
        "## Inputs", f"- Demand aggregate: `{stats['aggregate_path']}`; column `MEAN_DEMAND_MW` (MW).", f"- NEM region geometry: `{stats['regions_path']}`.", f"- Analysis grid: `{stats['grid_path']}`.", "- No weighting dataset is used in this MVP.", "",
        "## Reproducibility and checks", f"- Storage CRS: {config.STORAGE_CRS}; computation CRS: {config.COMPUTATION_CRS}.", f"- CRS transform: grid {config.STORAGE_CRS} → {config.COMPUTATION_CRS} for spatial allocation; output stored in {config.STORAGE_CRS}.", f"- Cells: {stats['n_cells']}; outside-region: {stats['n_outside_region']}; boundary/tie-break candidates: {stats['boundary_cell_count']}.", f"- Per-region counts: `{json.dumps(stats['per_region_counts'], sort_keys=True)}`.", f"- Confidence counts: `{json.dumps(stats['confidence_counts'], sort_keys=True)}`.", "- Confidence definitions: high = centroid-assigned cell with valid proxy; medium = deterministic boundary-overlap fallback; low = outside/unmatched region or null proxy.", "- Boundary assignments use centroid containment, then greatest overlap and lexicographic REGIONID tie-break.", f"- Aggregate regions outside this grid scope are explicitly reported: `{json.dumps(stats['unassigned_regions'])}`.",
    ]
    atomic_write_text(path, "\n".join(lines) + "\n")


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
    row = f"\n| demand.feature | {feature_path.name} | AEMO demand aggregate + NEM region geometry | Uniform allocation | Derived proxy indicator; not measured local demand |\n"
    if prov.exists():
        text = prov.read_text()
        if feature_path.name not in text:
            atomic_write_text(prov, text.rstrip() + "\n" + row)
    else:
        atomic_write_text(prov, "# Electricity Demand Data Provenance\n\n| Stage | Output | Inputs | Method | Notes |\n|---|---|---|---|---|\n" + row)
    digest = hashlib.sha256(feature_path.read_bytes()).hexdigest()
    manifest = meta_dir / config.FEATURE_MANIFEST_NAME
    obj = json.loads(manifest.read_text()) if manifest.exists() else {}
    obj[feature_path.name] = {"sha256": digest, "bytes": feature_path.stat().st_size, "utc": utc_now(), "derived_proxy": True}
    atomic_write_text(manifest, json.dumps(obj, indent=2) + "\n")


def run(verbose: bool = False, allocation_method: str = "uniform", grid_path: Path | None = None, aggregate_path: Path | None = None, nem_regions_path: Path | None = None, weighting_path: Path | None = None) -> dict:
    if allocation_method != config.DEFAULT_ALLOCATION_METHOD:
        raise NotImplementedError("S1-04 MVP supports allocation_method='uniform' only")
    grid_path = Path(grid_path or config.GRID_PATH)
    aggregate_path = Path(aggregate_path or (config.OUTPUT_DIR / config.AGGREGATED_CSV_NAME))
    nem_regions_path = Path(nem_regions_path or config.NEM_REGIONS_PATH)
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
    raw = allocate_demand(source, demand, allocation_method)
    proxy = normalise_proxy(raw, source)
    confidence = assign_confidence(source, proxy, boundary_indices)
    table = build_feature_table(grid, proxy, allocation_method, source, confidence)
    output_path = config.OUTPUT_DIR / config.FEATURE_TABLE_NAME
    report_path = config.OUTPUT_DIR / config.METHOD_REPORT_NAME
    assigned_regions = set(source.dropna().astype(str))
    scoped_aggregate = aggregate[aggregate["REGIONID"].astype(str).isin(assigned_regions)].copy()
    validate_feature_table(table, grid, source, raw, scoped_aggregate)
    stats = {"grid_path": _repo_relative(grid_path), "aggregate_path": _repo_relative(aggregate_path), "regions_path": _repo_relative(nem_regions_path), "n_cells": len(table), "n_outside_region": int(source.isna().sum()), "boundary_cell_count": len(boundary_indices), "per_region_counts": {str(k): int(v) for k, v in source.value_counts(dropna=True).items()}, "confidence_counts": {str(k): int(v) for k, v in confidence.value_counts().items()}, "unassigned_regions": sorted(set(aggregate["REGIONID"].astype(str)) - assigned_regions)}
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
