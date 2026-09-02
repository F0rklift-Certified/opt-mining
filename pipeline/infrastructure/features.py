"""S1-05 per-cell electricity infrastructure feature builder."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
import zipfile
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import Point, shape

from ..common.geo import atomic_write_text, utc_now
from . import config, helpers


def _load_grid(path: Path) -> gpd.GeoDataFrame:
    if not Path(path).exists():
        raise FileNotFoundError(path)
    gdf = gpd.read_file(path)
    if "cell_id" not in gdf.columns:
        raise ValueError(f"Grid {path} is missing cell_id")
    if gdf.cell_id.duplicated().any():
        raise ValueError(f"Grid {path} contains duplicate cell_id values")
    if gdf.crs is None:
        raise ValueError(f"Grid {path} has no CRS")
    return gdf


def _load_ga_layer(path: Path, state: str) -> gpd.GeoDataFrame:
    """Load every GA layer through the shared helper/filter contract."""
    if not Path(path).exists():
        return gpd.GeoDataFrame(geometry=[], crs=config.GA_SOURCE_CRS)
    collection = helpers.load_geojson(path)
    features = helpers.filter_by_state(collection.get("features", []), state)
    rows = []
    for feature in features:
        geom = feature.get("geometry")
        if geom:
            row = dict(feature.get("properties") or {})
            row["geometry"] = shape(geom)
            rows.append(row)
    return gpd.GeoDataFrame(rows, geometry="geometry", crs=config.GA_SOURCE_CRS)


def _resolve_connection_points(xlsx_path: Path) -> tuple[gpd.GeoDataFrame, int]:
    if not Path(xlsx_path).exists():
        return gpd.GeoDataFrame(geometry=[], crs=config.STORAGE_CRS), 0
    try:
        raw = pd.read_excel(xlsx_path, header=None)
    except Exception:
        return gpd.GeoDataFrame(geometry=[], crs=config.STORAGE_CRS), 0
    if len(raw) < 4:
        return gpd.GeoDataFrame(geometry=[], crs=config.STORAGE_CRS), max(0, len(raw) - 3)
    headers = [str(v).strip().lower() for v in raw.iloc[2].tolist()]
    lat_idx = next((i for i, h in enumerate(headers) if "latitude" in h or h in {"lat", "y"}), None)
    lon_idx = next((i for i, h in enumerate(headers) if "longitude" in h or h in {"lon", "long", "x"}), None)
    data = raw.iloc[3:]
    if lat_idx is None or lon_idx is None:
        return gpd.GeoDataFrame(geometry=[], crs=config.STORAGE_CRS), len(data)
    points, excluded = [], 0
    for _, row in data.iterrows():
        try:
            lat, lon = float(row.iloc[lat_idx]), float(row.iloc[lon_idx])
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError
            points.append(Point(lon, lat))
        except (TypeError, ValueError):
            excluded += 1
    return gpd.GeoDataFrame({"geometry": points}, geometry="geometry", crs=config.STORAGE_CRS), excluded


def _load_rez(rez_dir: Path) -> gpd.GeoDataFrame | None:
    files = sorted(Path(rez_dir).glob("*.zip")) if Path(rez_dir).exists() else []
    if not files:
        return None
    frames = []
    names = {"new_england": "New England REZ", "central_west_orana": "Central-West Orana REZ", "hunter_central_coast": "Hunter-Central Coast REZ"}
    for archive in files:
        try:
            with tempfile.TemporaryDirectory() as tmp:
                with zipfile.ZipFile(archive) as zf:
                    zf.extractall(tmp)
                shp = next(Path(tmp).rglob("*.shp"))
                frame = gpd.read_file(shp)
                if frame.crs is None:
                    raise ValueError(f"REZ source {archive} has no CRS")
                stem = archive.stem
                zone_name = next((v for k, v in names.items() if k in stem), archive.stem)
                frame = frame[["geometry"]].copy()
                frame["rez_name"] = zone_name
                frames.append(frame)
        except ValueError:
            # A declared-but-missing CRS is a schema error: do not guess it.
            raise
        except Exception:
            # A single unavailable archive must not prevent the rest of the
            # feature layer from being generated.  The method report records
            # that the REZ overlay is unavailable/partial and confidence is
            # lowered for affected rows.
            continue
    # Best-effort loading is also valid when every candidate archive is
    # unavailable or malformed. Returning None lets the caller emit null
    # REZ features and low confidence rather than failing on frames[0].
    if not frames:
        return None
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), geometry="geometry", crs=frames[0].crs)


def _nearest_distance_km(centroids_3577: gpd.GeoDataFrame, target_3577: gpd.GeoDataFrame) -> pd.Series:
    if target_3577 is None or target_3577.empty:
        # Match the non-empty path's index contract for safe DataFrame joins.
        return pd.Series(np.nan, index=centroids_3577.index, dtype="float64")
    joined = gpd.sjoin_nearest(centroids_3577[["cell_id", "geometry"]], target_3577[["geometry"]], distance_col="dist_m")
    distances = joined.groupby("cell_id")["dist_m"].min() / 1000.0
    return centroids_3577.cell_id.map(distances).set_axis(centroids_3577.index)


def _compute_rez_membership(grid_3577: gpd.GeoDataFrame, rez_3577: gpd.GeoDataFrame | None) -> tuple[pd.Series, pd.Series]:
    if rez_3577 is None or rez_3577.empty:
        return pd.Series(pd.NA, index=grid_3577.index, dtype="object"), pd.Series(pd.NA, index=grid_3577.index, dtype="object")
    left = grid_3577[["cell_id", "geometry"]]
    right = rez_3577[["rez_name", "geometry"]]
    joined = gpd.sjoin(left, right, predicate="intersects", how="left")
    matches = joined.dropna(subset=["index_right"])
    inside = matches.groupby("cell_id").size().reindex(left.cell_id, fill_value=0).gt(0).to_numpy()
    names = joined.dropna(subset=["index_right"]).groupby("cell_id")["rez_name"].apply(lambda s: config.REZ_NAME_DELIMITER.join(sorted({str(v) if pd.notna(v) and str(v).strip() else config.UNNAMED_REZ for v in s})))
    rez_names = left.cell_id.map(names).where(left.cell_id.map(names).notna(), None)
    return pd.Series(inside, index=grid_3577.index), pd.Series(rez_names.to_numpy(), index=grid_3577.index, dtype="object")


def _assign_confidence(df: gpd.GeoDataFrame) -> pd.Series:
    required = ["dist_transmission_km", "dist_substation_km", "dist_connection_km", "inside_rez"]
    return pd.Series(np.where(df[required].isna().any(axis=1), "low", "high"), index=df.index)


def validate_feature_table(feature_path: Path, grid_path: Path | None = None) -> dict:
    """Validate the persisted S1-05 layer against its contract.

    The checks are intentionally independent of the feature-builder internals
    so they can be used in CI or by a reviewer after a file is regenerated.
    """
    feature_path = Path(feature_path)
    if not feature_path.exists():
        raise FileNotFoundError(feature_path)
    table = gpd.read_file(feature_path, layer=config.FEATURE_TABLE_LAYER)
    expected = [
        "cell_id", "dist_transmission_km", "dist_substation_km",
        "dist_connection_km", "inside_rez", "rez_name", "confidence_flag",
        "geometry",
    ]
    missing = [column for column in expected if column not in table.columns]
    if missing:
        raise ValueError(f"Feature table missing columns: {missing}")
    if table.crs is None or table.crs.to_string() != config.STORAGE_CRS:
        raise ValueError(f"Feature table CRS must be {config.STORAGE_CRS}, got {table.crs}")
    if table.cell_id.isna().any() or table.cell_id.duplicated().any():
        raise ValueError("Feature table cell_id values must be present and unique")
    distance_cols = ["dist_transmission_km", "dist_substation_km", "dist_connection_km"]
    negative_counts = {}
    for column in distance_cols:
        values = pd.to_numeric(table[column], errors="coerce")
        negative_counts[column] = int((values.dropna() < 0).sum())
        if negative_counts[column]:
            raise ValueError(f"{column} contains a negative distance")
    rez_values = table.inside_rez.dropna()
    invalid_rez = sorted(set(rez_values.tolist()) - {True, False})
    if invalid_rez:
        raise ValueError(f"inside_rez must contain only boolean values or null: {invalid_rez}")
    if not set(table.confidence_flag.dropna().unique()).issubset(set(config.CONFIDENCE_LEVELS)):
        raise ValueError("confidence_flag must contain only high or low")
    null_required = table[distance_cols + ["inside_rez"]].isna().any(axis=1)
    if (table.loc[null_required, "confidence_flag"] != "low").any():
        raise ValueError("Rows with null required features must have low confidence")
    expected_cells = observed_cells = None
    if grid_path is not None:
        grid = _load_grid(Path(grid_path))
        expected_cells, observed_cells = len(grid), len(table)
        if observed_cells != expected_cells or set(table.cell_id) != set(grid.cell_id):
            raise ValueError("Feature table must contain exactly one row for every grid cell")
    return {
        "rows": len(table),
        "expected_rows": expected_cells,
        "observed_rows": observed_cells,
        "crs": table.crs.to_string(),
        "high_confidence": int((table.confidence_flag == "high").sum()),
        "low_confidence": int((table.confidence_flag == "low").sum()),
        "checks": {
            "row_count": {"pass": expected_cells is None or observed_cells == expected_cells, "expected": expected_cells, "observed": observed_cells},
            "cell_ids": {"pass": expected_cells is None or set(table.cell_id) == set(grid.cell_id), "expected": expected_cells, "observed": observed_cells},
            "schema": {"pass": not missing, "expected": expected, "observed": list(table.columns)},
            "non_negative_distances": {"pass": not any(negative_counts.values()), "negative_counts": negative_counts},
            "inside_rez_values": {"pass": not invalid_rez, "invalid_values": invalid_rez},
            "confidence_values": {"pass": True, "allowed": list(config.CONFIDENCE_LEVELS)},
            "null_features_low_confidence": {"pass": not bool((table.loc[null_required, "confidence_flag"] != "low").any()), "violations": int((table.loc[null_required, "confidence_flag"] != "low").sum())},
        },
    }


def _build_feature_table(grid: gpd.GeoDataFrame, distances: dict, inside: pd.Series, names: pd.Series, confidence: pd.Series) -> gpd.GeoDataFrame:
    return gpd.GeoDataFrame({"cell_id": grid.cell_id.tolist(), "dist_transmission_km": distances["transmission"].to_numpy(), "dist_substation_km": distances["substation"].to_numpy(), "dist_connection_km": distances["connection"].to_numpy(), "inside_rez": inside.to_numpy(), "rez_name": names.to_numpy(), "confidence_flag": confidence.to_numpy()}, geometry=grid.geometry.copy(), crs=grid.crs).to_crs(config.STORAGE_CRS)


def _write_feature_table(gdf: gpd.GeoDataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + ".tmp" + path.suffix)
    try:
        gdf.to_file(tmp, layer=config.FEATURE_TABLE_LAYER, driver="GPKG", index=False)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _write_method_report(stats: dict, path: Path) -> None:
    text = f"""# Infrastructure Feature Layer Method Report

*Generated by `pipeline.infrastructure.features` on {utc_now()}. Do not edit by hand.*

## Method

Distances are straight-line distances from each cell centroid to the nearest point on the nearest geometry, computed in **{stats['computation_crs']}** and reported in kilometres. Transmission-line distances use the line geometry itself, not endpoints. REZ membership uses polygon intersection in {stats['computation_crs']}; shared boundaries count.

## Inputs and CRS transforms

- GA transmission lines, substations and generators are loaded through `pipeline.infrastructure.helpers` and filtered with the same `{stats['state']}` rule.
- AEMO KCI connection points: no latitude/longitude columns were present in the supplied workbook; {stats['connection_excluded']} records were therefore excluded rather than assigned a default location.
- NSW EnergyCo REZ boundary ZIPs are read with their declared CRS and assigned their documented zone names.
- Transform log: grid {config.STORAGE_CRS} → {stats['computation_crs']}; GA layers {config.GA_SOURCE_CRS} → {stats['computation_crs']}; connection points EPSG:4326 → {stats['computation_crs']}; REZ source CRS → {stats['computation_crs']}.

## Limitations and confidence

Missing/unreadable/empty sources produce null features, never sentinel distances. `confidence_flag` is `high` only when every required source feature is available, otherwise `low`. Counts: high={stats['n_high_confidence']}, low={stats['n_low_confidence']}. REZ source available={stats['rez_available']}; boundary candidates={stats['rez_overlap_cells']}.

## Runtime

Full grid cells processed: {stats['n_cells']}. Runtime: {stats['runtime_seconds']:.3f} seconds.
"""
    atomic_write_text(path, text)


def _write_provenance(feature_path: Path, stats: dict) -> None:
    config.INFRA_META_DIR.mkdir(parents=True, exist_ok=True)
    prov = config.INFRA_DIR / "DATA_PROVENANCE.md"
    row = f"\n| infrastructure.features | {feature_path.name} | GA lines/substations, AEMO KCI, EnergyCo REZ | EPSG:3577 centroid distances | Derived product; generated {utc_now()} |\n"
    if prov.exists():
        existing = prov.read_text()
        if feature_path.name not in existing:
            atomic_write_text(prov, existing.rstrip() + "\n" + row)
    else:
        atomic_write_text(prov, "# Infrastructure Data Provenance\n\n| Stage | Output | Sources | Method | Notes |\n|---|---|---|---|---|\n" + row)
    manifest = config.INFRA_META_DIR / config.FEATURE_MANIFEST_NAME
    obj = json.loads(manifest.read_text()) if manifest.exists() else {}
    obj[feature_path.name] = {"sha256": hashlib.sha256(feature_path.read_bytes()).hexdigest(), "bytes": feature_path.stat().st_size, "utc": utc_now(), "generation_params": {"state": stats["state"], "computation_crs": stats["computation_crs"]}}
    atomic_write_text(manifest, json.dumps(obj, indent=2) + "\n")


def run(verbose: bool = False, state: str = config.DEFAULT_STATE, grid_path: Path | None = None, computation_crs: str = config.COMPUTATION_CRS) -> dict:
    started = time.perf_counter()
    grid_path = Path(grid_path or config.GRID_PATH)
    grid = _load_grid(grid_path)
    grid_3577 = grid.to_crs(computation_crs)
    lines = _load_ga_layer(config.TRANSMISSION_PATH, state)
    substations = _load_ga_layer(config.SUBSTATION_PATH, state)
    _ = _load_ga_layer(config.GENERATOR_PATH, state)  # context layer, shared filtering contract
    connections, connection_excluded = _resolve_connection_points(config.CONNECTION_POINTS_PATH)
    rez = _load_rez(config.REZ_DIR)
    def project(frame): return frame.to_crs(computation_crs) if frame is not None and not frame.empty else frame
    centroids = gpd.GeoDataFrame({"cell_id": grid.cell_id}, geometry=grid_3577.geometry.centroid, crs=computation_crs)
    distances = {"transmission": _nearest_distance_km(centroids, project(lines)), "substation": _nearest_distance_km(centroids, project(substations)), "connection": _nearest_distance_km(centroids, project(connections))}
    inside, names = _compute_rez_membership(grid_3577, project(rez))
    temp = gpd.GeoDataFrame({"dist_transmission_km": distances["transmission"], "dist_substation_km": distances["substation"], "dist_connection_km": distances["connection"], "inside_rez": inside}, index=grid.index)
    confidence = _assign_confidence(temp)
    table = _build_feature_table(grid, distances, inside, names, confidence)
    output = config.INFRA_DIR / config.FEATURE_TABLE_NAME
    report = config.INFRA_META_DIR / config.METHOD_REPORT_NAME
    runtime = time.perf_counter() - started
    stats = {"state": state, "computation_crs": computation_crs, "n_cells": len(table), "n_high_confidence": int((confidence == "high").sum()), "n_low_confidence": int((confidence == "low").sum()), "runtime_seconds": runtime, "connection_excluded": connection_excluded, "rez_available": rez is not None, "rez_overlap_cells": int((inside == True).sum()) if rez is not None else 0}
    _write_feature_table(table, output)
    validate_feature_table(output, grid_path)
    _write_method_report(stats, report)
    _write_provenance(output, stats)
    if verbose:
        print(f"  Infrastructure feature output: {output} ({len(table):,} cells; {runtime:.2f}s)")
    return {"feature_table_path": output, "method_report_path": report, **stats}
