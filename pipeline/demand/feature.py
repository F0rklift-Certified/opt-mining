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


def load_load_weights(path: Path) -> gpd.GeoDataFrame:
    """Load the geocoded zone-substation load-point layer for ``load_weighted``.

    Mirrors :func:`load_urban_weights`: a missing or unreadable source **halts
    loudly** naming the path, so a missing geocoded layer can never silently
    fall back to another method. The layer must carry the configured load-metric
    column (``config.LOAD_MVA_COLUMN``, max demand in MVA); its absence is a hard
    error. The returned GeoDataFrame is point geometry in its stored CRS
    (EPSG:4326); the caller reprojects to EPSG:3577 for the distance-decay.
    """
    path = Path(path)
    if not path.exists():
        raise RuntimeError(
            f"Load-weighting (geocoded zone-substation) source is missing: {path}. "
            f"Run `python -m pipeline.demand.geocode_load` to build it from the NSW "
            f"DNSP DAPR max-demand extract; allocation is never silently defaulted "
            f"for a missing source."
        )
    try:
        gdf = gpd.read_file(path, layer=config.LOAD_POINTS_LAYER)
    except Exception as exc:  # unreadable / corrupt / missing layer
        raise RuntimeError(
            f"Load-weighting source could not be read: {path} ({exc})"
        ) from exc
    if config.LOAD_MVA_COLUMN not in gdf.columns:
        raise RuntimeError(
            f"Load-weighting source {path} is missing the load column "
            f"{config.LOAD_MVA_COLUMN!r}; got {list(gdf.columns)}"
        )
    return gdf


def compute_load_cell_weights(grid_3577: gpd.GeoDataFrame, load_points_3577: gpd.GeoDataFrame, source_region: pd.Series) -> pd.Series:
    """Per-cell distance-decay weight for ``load_weighted`` allocation.

    Implements the chosen model (findings.md §4):

        w_cell = Σ_s  load_mva_s · exp(-d(cell, s) / LOAD_DECAY_LENGTH_M)

    over geocoded substations ``s`` within ``config.LOAD_SEARCH_RADIUS_M`` of the
    cell centroid (distances in EPSG:3577 metres), plus
    ``config.DEMAND_WEIGHT_FLOOR`` on every **assigned** cell (``source_region``
    not null) so no assigned cell has zero weight.

    Candidate substations per cell are found with a spatial index (buffer the
    cell centroids by the search radius and ``gpd.sjoin`` against the points),
    then the decay is summed in a fixed ``(cell_id, substation order)`` order so
    the floating-point result is reproducible. Only the RELATIVE shape matters:
    the per-region rescale in :func:`allocate_demand` absorbs the MVA units and
    the forecast-vs-recorded mismatch, conserving each region's total exactly.

    Returns a float Series indexed like ``grid_3577``/``source_region``: ``NaN``
    for outside-region cells, otherwise ``decay_sum + floor`` (>= floor).
    """
    index = grid_3577.index
    assigned_mask = source_region.notna()
    weights = pd.Series(float("nan"), index=index, dtype="float64")
    weights.loc[assigned_mask] = float(config.DEMAND_WEIGHT_FLOOR)

    if len(load_points_3577) == 0:
        return weights

    load = load_points_3577[[config.LOAD_MVA_COLUMN, "geometry"]].copy()
    load = load[load[config.LOAD_MVA_COLUMN].notna()].reset_index(drop=True)
    # Drop zero/negative loads (e.g. the documented Pindari = 0 row): they add no
    # shape and an exp-decay of zero load is a no-op.
    load = load[load[config.LOAD_MVA_COLUMN].astype(float) > 0.0].reset_index(drop=True)
    if len(load) == 0:
        return weights
    load["load_index"] = load.index
    load["load_mva"] = load[config.LOAD_MVA_COLUMN].astype(float)

    decay = float(config.LOAD_DECAY_LENGTH_M)
    radius = float(config.LOAD_SEARCH_RADIUS_M)

    # Candidate (cell, substation) pairs within the search radius: buffer the
    # cell centroids by `radius` and intersect with the substation points via the
    # spatial index, then compute the exact centroid-to-point distance.
    centroids = grid_3577.geometry.centroid
    cell_buffers = gpd.GeoDataFrame(
        {"cell_id": grid_3577["cell_id"].to_numpy(), "cell_index": index},
        geometry=centroids.buffer(radius),
        crs=grid_3577.crs,
    )
    candidates = gpd.sjoin(
        cell_buffers,
        load[["load_index", "load_mva", "geometry"]],
        how="inner",
        predicate="intersects",
    )
    if len(candidates) == 0:
        return weights

    # Deterministic accumulation order (cell_id, then substation index).
    candidates = candidates.sort_values(["cell_id", "load_index"], kind="mergesort")

    load_geoms = load.geometry
    decay_sum = pd.Series(0.0, index=index, dtype="float64")
    for row in candidates.itertuples(index=False):
        cell_idx = row.cell_index
        dist = float(centroids.loc[cell_idx].distance(load_geoms.loc[row.load_index]))
        if dist > radius:
            continue
        decay_sum.loc[cell_idx] += float(row.load_mva) * _exp_decay(dist, decay)

    weights.loc[assigned_mask] = weights.loc[assigned_mask] + decay_sum.loc[assigned_mask]
    return weights


def _exp_decay(distance_m: float, decay_length_m: float) -> float:
    """Distance-decay kernel ``exp(-d/d0)`` (module-level for testability)."""
    import math

    return math.exp(-distance_m / decay_length_m)


def compute_demand_coord_confidence(
    grid_3577: gpd.GeoDataFrame,
    load_points_3577: gpd.GeoDataFrame,
    source_region: pd.Series,
) -> pd.Series:
    """Per-cell demand coordinate-confidence tier for ``load_weighted`` (metadata).

    Returns an INFORMATIONAL string Series indexed like ``grid_3577`` /
    ``source_region`` with values from
    ``config.DEMAND_COORD_CONFIDENCE_LEVELS`` ("high" | "low" | "n/a"). It is
    derived from the SAME distance-decay neighbourhood ``compute_load_cell_weights``
    uses, so it faithfully reports whether a cell's load signal rode a
    low-confidence geocoded substation. It NEVER touches ``demand_proxy``, the
    score or the ranking — it is surfaced only for audit.

    Definition (conservative; see ``config.DEMAND_COORD_CONFIDENCE_COLUMN``):

    - ``"low"`` — at least one low-confidence load point (``nominatim_low_confidence``
      OR ``osm_low_confidence``) with ``max_demand`` (MVA) > 0 lies within
      ``config.LOAD_SEARCH_RADIUS_M`` of the cell centroid (it contributes to the
      cell's load weight). The same ``MVA > 0`` filter that
      :func:`compute_load_cell_weights` applies is applied here, so a
      zero/negative-MVA point (e.g. the documented ``Pindari = 0`` row) that adds
      no decay weight can never flag a cell ``low``.
    - ``"high"`` — an assigned cell (``source_region`` not null) whose
      contributing load points are all precise, or which has no load point in
      range (it never rode a low-confidence point).
    - ``"n/a"`` — an unassigned (outside-region) cell. Under a method with no
      load points, :func:`derive_demand_coord_confidence` returns all ``"n/a"``
      without calling this function.

    Determinism: the result depends only on set membership of a cell's
    within-radius low-confidence points, so it is reproducible regardless of
    iteration order.
    """
    index = grid_3577.index
    assigned_mask = source_region.notna()
    # Assigned cells default to "high"; unassigned cells are "n/a".
    tier = pd.Series(config.DEMAND_COORD_CONFIDENCE_NA, index=index, dtype="object")
    tier.loc[assigned_mask] = config.DEMAND_COORD_CONFIDENCE_HIGH

    if len(load_points_3577) == 0:
        return tier

    # Match the MVA filter compute_load_cell_weights uses: a point only
    # contributes to a cell's load weight if its max demand is > 0, so a
    # zero/negative-MVA point (e.g. the documented Pindari = 0 row) must not be
    # able to flag a cell "low". Points missing the MVA column are retained
    # (an older/partial layer degrades conservatively rather than dropping rows).
    load = load_points_3577.copy()
    if config.LOAD_MVA_COLUMN in load.columns:
        mva = pd.to_numeric(load[config.LOAD_MVA_COLUMN], errors="coerce")
        load = load[mva.fillna(1.0) > 0.0]
    if len(load) == 0:
        return tier

    # Flag each load point low-confidence if EITHER flag column is True. A
    # missing flag column is treated as all-False (precise), so an older layer
    # without the flags degrades to "high" everywhere rather than erroring.
    low_flag = pd.Series(False, index=load.index)
    for col in config.LOAD_LOW_CONFIDENCE_COLUMNS:
        if col in load.columns:
            low_flag = low_flag | load[col].fillna(False).astype(bool)
    low = load[low_flag.to_numpy()]
    if len(low) == 0:
        return tier

    radius = float(config.LOAD_SEARCH_RADIUS_M)
    centroids = grid_3577.geometry.centroid
    cell_buffers = gpd.GeoDataFrame(
        {"cell_id": grid_3577["cell_id"].to_numpy(), "cell_index": index},
        geometry=centroids.buffer(radius),
        crs=grid_3577.crs,
    )
    low = low[["geometry"]].reset_index(drop=True)
    low["low_index"] = low.index
    candidates = gpd.sjoin(
        cell_buffers, low[["low_index", "geometry"]], how="inner", predicate="intersects",
    )
    if len(candidates) == 0:
        return tier

    low_geoms = low.geometry
    low_cells = set()
    for row in candidates.itertuples(index=False):
        cell_idx = row.cell_index
        dist = float(centroids.loc[cell_idx].distance(low_geoms.loc[row.low_index]))
        if dist <= radius:
            low_cells.add(cell_idx)
    # Only assigned cells can be "low"; an unassigned cell stays "n/a" even if a
    # low-confidence point happens to fall within its (unused) radius.
    low_assigned = [i for i in low_cells if bool(assigned_mask.loc[i])]
    tier.loc[low_assigned] = config.DEMAND_COORD_CONFIDENCE_LOW
    return tier


def derive_demand_coord_confidence(
    grid_3577: gpd.GeoDataFrame,
    source_region: pd.Series,
    method: str,
    load_points_3577: gpd.GeoDataFrame | None = None,
) -> pd.Series:
    """Method-aware wrapper for the demand coordinate-confidence tier (metadata).

    Returns a per-cell ``"high" | "low" | "n/a"`` Series. The tier is only
    meaningful under ``load_weighted`` (the only method with load points);
    under ``urban_weighted`` / ``uniform`` there are no load points, so every
    cell is the not-applicable ``"n/a"`` value. This is informational only — it
    never feeds back into ``demand_proxy``, the score, the weights or the rank.
    """
    if method == "load_weighted" and load_points_3577 is not None and len(load_points_3577):
        return compute_demand_coord_confidence(grid_3577, load_points_3577, source_region)
    return pd.Series(
        config.DEMAND_COORD_CONFIDENCE_NA, index=source_region.index, dtype="object"
    )


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

    # Weighted (urban_weighted / load_weighted): distribute each region's demand
    # by per-cell weight,
    #   raw[cell] = weights[cell] / sum(weights in region) * region_demand[region]
    # which conserves each region's total exactly regardless of how the weights
    # were derived (urban-overlap area or real-load distance-decay).
    if weights is None:
        raise ValueError(f"{method} allocation requires a per-cell weights Series")
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


def write_coord_confidence_sidecar(
    grid: gpd.GeoDataFrame, coord_confidence: pd.Series, path: Path
) -> None:
    """Write the per-cell demand coordinate-confidence tier to a sidecar CSV.

    The sidecar carries exactly ``cell_id,demand_coord_confidence`` for every
    grid cell, sorted by ``cell_id`` so a rerun with unchanged inputs is
    byte-identical. It lives ALONGSIDE the feature GeoPackage so the gpkg
    schema (and bytes) never change; the integration stage joins this tier onto
    the integrated table as an informational column. The tier never affects
    ``demand_proxy``, the score or the ranking.
    """
    frame = pd.DataFrame({
        "cell_id": grid["cell_id"].to_numpy(),
        config.DEMAND_COORD_CONFIDENCE_COLUMN: coord_confidence.to_numpy(),
    }).sort_values("cell_id", kind="mergesort").reset_index(drop=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.stem + ".tmp" + path.suffix)
    try:
        frame.to_csv(tmp, index=False, lineterminator="\n", encoding="utf-8")
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
            f"- Demand coordinate-confidence tier (INFORMATIONAL, surface-only metadata) written to sidecar `{config.COORD_CONFIDENCE_SIDECAR_NAME}`: `{json.dumps(stats.get('coord_confidence_counts', {}), sort_keys=True)}`. Under urban_weighted there are no load points, so every cell is the not-applicable `n/a` value. The tier NEVER feeds back into `demand_proxy`, the composite score, the weights or the ranking — it only lets an analyst audit whether a cell's demand signal rode a low-confidence geocoded substation. Definition: `low` = a Nominatim/OSM low-confidence load point lies within the search radius of the cell centroid; `high` = assigned cell whose contributing points are all precise (or none in range); `n/a` = not applicable (no load points / outside region).",
            f"- Floored (non-urban) assigned cells: {stats.get('floored_cell_count', 0)}.",
            f"- Cells: {stats['n_cells']}; outside-region: {stats['n_outside_region']}; boundary/tie-break candidates: {stats['boundary_cell_count']}.",
            f"- Per-region counts: `{json.dumps(stats['per_region_counts'], sort_keys=True)}`.",
            f"- Confidence counts: `{json.dumps(stats['confidence_counts'], sort_keys=True)}`.",
            "- Confidence definitions: high = assigned cell with real urban overlap and valid proxy; medium = deterministic boundary-overlap fallback OR floored (non-urban) assigned cell; low = outside/unmatched region or null proxy.",
            "- Boundary assignments use centroid containment, then greatest overlap and lexicographic REGIONID tie-break.",
            f"- Aggregate regions outside this grid scope are explicitly reported: `{json.dumps(stats['unassigned_regions'])}`.",
        ]
    elif method == "load_weighted":
        method_block = [
            "## Method", "Measured/forecast zone-substation load weighted allocation (NSW DNSP DAPR).", "",
            "`raw_cell_demand_MW = (w_cell / Σ w_region) × MEAN_DEMAND_MW_region`", "",
            "where `w_cell = Σ_s load_mva_s · exp(-d(cell, s) / d0) + floor`, summed over",
            "geocoded zone substations `s` within the search radius of the cell centroid",
            "(distance-decay around real substation points, distances in EPSG:3577).",
            "Real zone-substation max demand sets the within-region SHAPE; the AEMO regional",
            "aggregate sets the LEVEL. The per-region rescale conserves each region's total",
            "exactly and absorbs the MVA-vs-MW and forecast-vs-recorded mismatch because only",
            "the RELATIVE shape is used.", "",
            "`demand_proxy` is the per-region max-normalised `raw_cell_demand_MW`; it is a",
            "normalized proxy indicator of nearness to existing network load, not measured",
            "local demand, not spare capacity and not a guarantee of offtake.", "",
            "## Assumptions and limitations",
            "- Max demand is LOAD, not spare capacity and not a guarantee of future offtake — a cell near real load is likely an easier market, nothing more.",
            "- The weight is MVA used directly (no MVA→MW conversion); the per-region rescale makes only the relative shape matter, so units never affect conservation.",
            "- The input MIXES Essential POE50 FORECAST demand (366 substations, 2025/26 summer) with Ausgrid RECORDED actuals (177 substations, 2024/25 summer) and Endeavour RECORDED actuals (166 substations, higher of summer/winter 2025 `Actual (MVA)`). All are MVA and are used only for relative shape, but the forecast-vs-recorded mix (Essential is forecast; Ausgrid and Endeavour are recorded) is a real like-with-unlike limitation.",
            "- Sub-transmission and voltage-split rows (e.g. `Terranora 110/66kV`, `Cudgen 11kV`/`Cudgen 33kV`) are KEPT as load points — they still mark real load locations; voltage suffixes are stripped only for name-matching.",
            "- Endeavour Energy now contributes 166 recorded-actual zone substations extracted from the Endeavour DAPR portal pop-ups, so Greater Western Sydney / Blue Mountains / Illawarra / South Coast now carry direct load points (previously 0). Each Endeavour row arrives WITH a precise portal coordinate and is emitted as a precise point (`coord_source='portal'`), bypassing name-geocoding. The 20 proposed/no-recorded-demand Endeavour substations are excluded at source (see `load/endeavour_portal/SOURCES_endeavour.md`). Areas still beyond every substation's search radius fall back to the floor and are flagged `medium`.",
            "- Substations with coordinates already present (the 166 Endeavour portal rows) take a coordinates-already-present fast-path and are emitted directly as precise points (`coord_source='portal'`, treated GA-precise, never low-confidence). The name-only rows (Essential/Ausgrid) are geocoded by deterministic name-matching against three sources — Geoscience Australia NSW substations (primary), OpenStreetMap named NSW `power=substation` features (second, for GA misses; operator-agreement gate, site-suffix/abbreviation normalisation, `osm_low_confidence` flag), then Nominatim (OSM place-geocoding) suburb/locality CENTROIDS (third, for GA+OSM misses). Nominatim returns a place centroid a few km off the substation, not a precise point, so every Nominatim match is a separately-flagged lower-confidence tier (`coord_source='nominatim'`, `nominatim_low_confidence=True`) that an analyst can down-weight/audit — acceptable only because the 15 km decay / 40 km radius tolerates a centroid offset. Substations unmatched by ALL THREE name sources are DROPPED (coordinates never invented) and listed in `DATA/electricity-demand/load/unmatched_substations.csv`.",
            "- LICENCE (coordinates): the OSM-sourced coordinates (OSM `power=substation` features AND Nominatim place centroids) are © OpenStreetMap contributors, licensed under ODbL 1.0 (https://www.openstreetmap.org/copyright); attribution satisfies ODbL for internal use. The Endeavour coordinates come from the Endeavour DAPR portal (NOT OSM) and are precise substation positions.",
            "- LICENCE (demand magnitudes): the three NSW DNSP DAPRs are NOT published under an open licence; their disclaimers restrict purpose. Their use here is a documented, knowingly-accepted INTERNAL-USE decision — this is not a grant of an open licence. Coordinates (OSM, open) and demand magnitudes (DNSP, restricted) carry different reuse rights.",
            "- NSW1 represents NSW and ACT under the NEM convention; regions other than NSW1 have no NSW load points and degrade to uniform-within-region on the floor.",
            "- Cells outside all NEM polygons receive null demand and low confidence.", "",
            "## Inputs",
            f"- Demand aggregate: `{stats['aggregate_path']}`; column `MEAN_DEMAND_MW` (MW).",
            f"- NEM region geometry: `{stats['regions_path']}`.",
            f"- Analysis grid: `{stats['grid_path']}`.",
            f"- Geocoded load points (NSW zone-substation max demand, MVA): `{stats.get('weighting_path', '')}` (sha256 `{stats.get('weighting_sha256', '')}`).",
            "- Raw DNSP DAPR sources (see `DATA/electricity-demand/load/SOURCES.md` for full provenance and SHAs):",
            "  - Essential Energy `DAPR 2025 BSP, ZS and Lines Extract Summary - V2.xlsx` (sha256 `eefd0606de5936cea772c3df696360126d401f667605072517cb3d4fbcc225b5`).",
            "  - Ausgrid `Ausgrid_Substation_Capacity_and_Demand_Forecast_2025.xlsx` (sha256 `f9f1d537fa3d39e0223c3fb99408be7d9605d7e04ca6306292f18e0895a8fbda`).",
            "  - Endeavour DAPR Mapping Portal pop-up extraction `endeavour_portal/endeavour_zone_substation_max_demand.csv` (sha256 `553e1233fb24be42075f61b387569d11eb814a8f0995195a0d61651db62fff96`) — 166 recorded-actual zone substations WITH precise portal coordinates (20 proposed/no-recorded-demand substations excluded at source; see `load/endeavour_portal/SOURCES_endeavour.md`). The Endeavour DAPR 2025 PDF (sha256 `2a958edda1c244f9d48784a00a20fc54e0edd12de946b69e57e71e072162b717`) is the supporting document.",
            f"- Geocoding substation references (name-only rows): Geoscience Australia NSW substation points (`{_repo_relative(config.GA_SUBSTATIONS_PATH)}`, primary), OpenStreetMap named NSW substations (`{_repo_relative(config.OSM_SUBSTATIONS_PATH)}`, second) and Nominatim OSM place-geocoding centroids (`{_repo_relative(config.NOMINATIM_SUBSTATIONS_PATH)}`, third, lower-confidence; © OpenStreetMap contributors, ODbL 1.0). Rows with coordinates already present (Endeavour portal) bypass these and use `coord_source='portal'`.", "",
            "## Reproducibility and checks",
            f"- Storage CRS: {config.STORAGE_CRS}; computation CRS: {config.COMPUTATION_CRS}.",
            f"- CRS transform: grid and load points {config.STORAGE_CRS} → {config.COMPUTATION_CRS} for distance-decay and allocation; output stored in {config.STORAGE_CRS}.",
            f"- Distance-decay length d0: {stats.get('load_decay_length_m')} m; search radius: {stats.get('load_search_radius_m')} m; load metric column: `{stats.get('load_mva_column')}` (MVA).",
            f"- Non-coverage weight floor: {stats.get('demand_weight_floor')}.",
            f"- Geocoding match rate: {stats.get('geocode_matched')} of {stats.get('geocode_load_rows')} substations matched (portal {stats.get('geocode_matched_portal')} + GA {stats.get('geocode_matched_ga')} + OSM {stats.get('geocode_matched_osm')} + Nominatim {stats.get('geocode_matched_nominatim')}; the {stats.get('geocode_matched_portal')} Endeavour rows carry precise portal coordinates [`coord_source='portal'`] and bypass name-geocoding; {stats.get('geocode_osm_low_confidence')} OSM low-confidence; all Nominatim matches are lower-confidence PLACE centroids [`coord_source='nominatim'`, `nominatim_low_confidence=True`] that an analyst can down-weight/audit; {stats.get('geocode_unmatched')} unmatched, dropped and listed).",
            f"- Per-region demand_proxy spread (min/median/max, nunique): `{json.dumps(stats.get('proxy_spread', {}), sort_keys=True)}`.",
            f"- Demand coordinate-confidence tier (INFORMATIONAL, surface-only metadata) written to sidecar `{config.COORD_CONFIDENCE_SIDECAR_NAME}`: `{json.dumps(stats.get('coord_confidence_counts', {}), sort_keys=True)}`. `low` = a Nominatim low-confidence PLACE centroid or an OSM low-confidence load point lies within the search radius of the cell centroid (it contributes to the cell's load weight); `high` = assigned cell whose contributing points are all precise (GA/portal/OSM-high) or which has no load point in range; `n/a` = outside every NEM region (unassigned). The tier NEVER feeds back into `demand_proxy`, the composite score, the weights or the ranking — it is metadata that lets an analyst audit whether a cell's demand signal rode a low-confidence geocoded substation.",
            f"- Floored (no-coverage) assigned cells: {stats.get('floored_cell_count', 0)}.",
            f"- Cells: {stats['n_cells']}; outside-region: {stats['n_outside_region']}; boundary/tie-break candidates: {stats['boundary_cell_count']}.",
            f"- Per-region counts: `{json.dumps(stats['per_region_counts'], sort_keys=True)}`.",
            f"- Confidence counts: `{json.dumps(stats['confidence_counts'], sort_keys=True)}`.",
            "- Confidence definitions: high = assigned cell near real load (within a substation's decay radius) with valid proxy; medium = deterministic boundary-overlap fallback OR floored (no-coverage) assigned cell; low = outside/unmatched region or null proxy.",
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
    elif method_label == "load_weighted":
        method_cell = "Measured/forecast zone-substation load weighted allocation (NSW DNSP DAPR; internal-use)"
        inputs_cell = "AEMO demand aggregate + NEM region geometry + geocoded NSW zone-substation max demand (DNSP DAPR)"
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
    if weighting_path is not None:
        weighting_path = Path(weighting_path)
    elif allocation_method == "load_weighted":
        weighting_path = Path(config.LOAD_WEIGHTS_PATH)
    else:
        weighting_path = Path(config.URBAN_WEIGHTS_PATH)
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
    weights_sha = None
    load_3577 = None  # kept for the demand coordinate-confidence tier (load_weighted only)
    if allocation_method == "urban_weighted":
        urban_gdf = load_urban_weights(weighting_path)  # hard-fail if missing
        weights_sha = hashlib.sha256(Path(weighting_path).read_bytes()).hexdigest()
        urban_3577 = urban_gdf.to_crs(config.COMPUTATION_CRS)
        weights = compute_cell_weights(grid_3577, urban_3577, source)
        # Floored cells: assigned (not null weight) but carrying only the floor
        # (no real urban overlap) -> weakly supported, downgraded to medium.
        assigned = weights.notna()
        floored_mask = assigned & (weights <= float(config.DEMAND_WEIGHT_FLOOR))
        floored_indices = list(weights.index[floored_mask])
    elif allocation_method == "load_weighted":
        load_gdf = load_load_weights(weighting_path)  # hard-fail if missing
        weights_sha = hashlib.sha256(Path(weighting_path).read_bytes()).hexdigest()
        load_3577 = load_gdf.to_crs(config.COMPUTATION_CRS)
        weights = compute_load_cell_weights(grid_3577, load_3577, source)
        # Cells beyond every substation's search radius carry only the floor ->
        # weakly supported (Endeavour gap / far-from-substation) -> medium.
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
        stats["weighting_sha256"] = weights_sha
        stats["demand_weight_floor"] = float(config.DEMAND_WEIGHT_FLOOR)
        stats["sosr_weight_multipliers"] = dict(config.SOSR_WEIGHT_MULTIPLIERS)
        stats["floored_cell_count"] = len(floored_indices) if floored_indices is not None else 0
    elif allocation_method == "load_weighted":
        stats["weighting_path"] = _repo_relative(weighting_path)
        stats["weighting_sha256"] = weights_sha
        stats["demand_weight_floor"] = float(config.DEMAND_WEIGHT_FLOOR)
        stats["load_decay_length_m"] = float(config.LOAD_DECAY_LENGTH_M)
        stats["load_search_radius_m"] = float(config.LOAD_SEARCH_RADIUS_M)
        stats["load_mva_column"] = config.LOAD_MVA_COLUMN
        stats["floored_cell_count"] = len(floored_indices) if floored_indices is not None else 0
        # Carry the geocoding provenance from the layer's manifest entry (built
        # by geocode_load) so the method report can state the match rate.
        manifest_path = config.OUTPUT_DIR / "metadata" / config.FEATURE_MANIFEST_NAME
        if manifest_path.exists():
            try:
                entry = json.loads(manifest_path.read_text()).get(Path(weighting_path).name, {})
                stats["geocode_match_rate"] = entry.get("match_rate")
                stats["geocode_matched"] = entry.get("matched")
                stats["geocode_matched_portal"] = entry.get("matched_portal")
                stats["geocode_matched_ga"] = entry.get("matched_ga")
                stats["geocode_matched_osm"] = entry.get("matched_osm")
                stats["geocode_matched_nominatim"] = entry.get("matched_nominatim")
                stats["geocode_osm_low_confidence"] = entry.get("osm_low_confidence")
                stats["geocode_unmatched"] = entry.get("unmatched")
                stats["geocode_load_rows"] = entry.get("load_rows")
            except (json.JSONDecodeError, OSError):
                pass
    write_feature_table(table, output_path)
    # Informational demand coordinate-confidence tier (surface-only metadata).
    # Derived from the SAME load-point neighbourhood used for the weights but
    # written to a SIDECAR CSV so the feature GeoPackage schema/bytes never
    # change. Under urban_weighted/uniform (no load points) every cell is "n/a".
    coord_confidence = derive_demand_coord_confidence(
        grid_3577, source, allocation_method, load_3577
    )
    sidecar_path = config.OUTPUT_DIR / config.COORD_CONFIDENCE_SIDECAR_NAME
    write_coord_confidence_sidecar(grid, coord_confidence, sidecar_path)
    stats["coord_confidence_counts"] = {
        str(k): int(v) for k, v in coord_confidence.value_counts().items()
    }
    from .validate import validate_feature_table as validate_persisted_feature_table
    persisted_validation = validate_persisted_feature_table(output_path, grid_path, aggregate_path)
    if not persisted_validation.passed:
        failed = [name for name, passed, _ in persisted_validation.details if not passed]
        raise ValueError("Persisted demand feature validation failed: " + ", ".join(failed))
    write_method_report(stats, report_path)
    record_provenance(output_path, stats)
    if verbose:
        print(f"  Demand feature output: {output_path} ({len(table):,} cells)")
    return {"feature_table_path": output_path, "method_report_path": report_path, "coord_confidence_sidecar_path": sidecar_path, "allocation_method": allocation_method, **{k: v for k, v in stats.items() if k not in {"grid_path", "aggregate_path", "regions_path"}}}
