"""
Cross-domain integration validation — checks that span multiple subpackages.

These checks validate wind farm siting against geographic layers:
- Wind farms are on land (NE + ABS masks)
- Wind farms are outside protected areas (CAPAD)
- Wind farms have acceptable slope
- Land-mask assessment: NE vs ABS coastline on the analysis grid

It also holds the cross-domain checks that compare one stage's output against
another's:
- scoring (S1-10) vs the analysis grid and the integrated table
- shortlist (S1-11) vs the Scored_Table and the analysis grid

Domain-specific validation lives in each subpackage's own validate.py:
- pipeline.wind.validate — GWA raster sampling, crosscheck
- pipeline.geographic.validate — CAPAD area, DEM elevation, NLUM decode
- pipeline.scoring.validate — score range, rank contiguity, contribution reconcile
- pipeline.shortlist.validate — row count vs Top_N, eligible-only, ordering,
  coordinates, CSV/GeoJSON equality, disclaimer/resolution presence

Importable entry point:
    from pipeline.validate import run
    result = run(verbose=False, skip_land_sea=False)

Output:
    DATA/geographic/metadata/landmask_assessment.md
    (wind-farm geographic checks are appended to validation_geographic.md
     or reported standalone)
"""

from __future__ import annotations

import csv
import io
import json
import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import rasterize
from rasterio.transform import from_origin
from rasterio.warp import transform as warp_transform
from rasterio.windows import from_bounds

from . import config
from .common.geo import (
    apply_vsicurl_env,
    atomic_write_json,
    atomic_write_text,
    banner,
    human_bytes,
    sha256_file,
    utc_now,
)
from .geographic import config as geo_config
from .grid.config import NSW_BBOX
from .integration import config as integration_config
from .integration.config import (
    COMPUTATION_CRS,
    INTEGRATION_DIR,
    INTEGRATION_META_DIR,
    INTEGRATION_VINTAGE,
    OUTPUT_FILENAME,
    OUTPUT_LAYER,
    SCORED_FEATURE_COLUMNS,
    STORAGE_CRS,
)
from .integration.merge import BOOL_COLUMNS, COLUMN_UNITS, OUTPUT_COLUMNS
from .wind import config as wind_config
from .wind.gwa import resolve_source


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GWA_ORIGIN_LON = 109.21125
GWA_ORIGIN_LAT = -8.86125
GWA_PIXEL_DEG = 0.0025
CELL_DEG = 0.05
PX_PER_CELL = int(round(CELL_DEG / GWA_PIXEL_DEG))
STRIP_BBOX = config.COAST_BBOX

# Siting constraint defaults
DEFAULT_MAX_SLOPE_DEG = 15.0


# ---------------------------------------------------------------------------
# S2-02 — Sprint 1 integrated-table input contract
# ---------------------------------------------------------------------------
#
# The schema this tier validates is *read* from the Schema_Authority
# (`OUTPUT_COLUMNS` / `COLUMN_UNITS` / `BOOL_COLUMNS` in
# `pipeline/integration/merge.py`; `SCORED_FEATURE_COLUMNS` /
# `INTEGRATION_DIR` / `OUTPUT_FILENAME` / `OUTPUT_LAYER` /
# `INTEGRATION_VINTAGE` / `INTEGRATION_META_DIR` and the re-exported
# `STORAGE_CRS` / `COMPUTATION_CRS` in `pipeline/integration/config.py`) and is
# never re-typed as literals, so a schema, path or CRS change upstream
# propagates into this gate rather than drifting (KAN-38 cross-cutting note).

# Default path to the frozen Sprint 1 integrated table. Derived from the
# integration config — never a hard-coded literal — so an upstream rename of
# the output directory or filename flows through to the validator.
DEFAULT_INTEGRATED_PATH = INTEGRATION_DIR / OUTPUT_FILENAME

# The Baseline_Manifest (design Model 1) lives alongside the existing
# integration_manifest.json under INTEGRATION_META_DIR and follows the same
# file-naming / metadata convention.
BASELINE_MANIFEST_FILENAME = "integrated_baseline_manifest.json"
DEFAULT_BASELINE_MANIFEST_PATH = INTEGRATION_META_DIR / BASELINE_MANIFEST_FILENAME

# The Validation_Result (design Model 2) and its sibling Validation_Report are
# written alongside the Baseline_Manifest under INTEGRATION_META_DIR, following
# the same file-naming convention. Defined here as module constants — never
# hard-coded literals at the write sites — so a path change lands in one place,
# mirroring the BASELINE_MANIFEST_FILENAME pattern. Tests redirect writes by
# monkeypatching INTEGRATION_META_DIR (the writers derive their default path
# from it), consistent with DEFAULT_BASELINE_MANIFEST_PATH.
VALIDATION_RESULT_FILENAME = "integrated_input_validation.json"
VALIDATION_REPORT_FILENAME = "integrated_input_validation.md"
DEFAULT_VALIDATION_RESULT_PATH = INTEGRATION_META_DIR / VALIDATION_RESULT_FILENAME
DEFAULT_VALIDATION_REPORT_PATH = INTEGRATION_META_DIR / VALIDATION_REPORT_FILENAME

# Screening_Language purpose sentence (S2-01 §1.4, requirement 8A). Reused in
# the Validation_Report and any diagnostic output so the validator only ever
# describes its purpose as preliminary screening — never as identifying a
# "best site". Kept as a single constant so the phrasing cannot drift between
# outputs.
SCREENING_PURPOSE = (
    "This gate is a precondition on preliminary screening: it verifies the "
    "frozen integrated input contract so the decision engine only screens data "
    "it has verified. The engine surfaces higher-ranked candidate cells under "
    "the selected assumptions and criteria — preliminary screening, never a "
    "\"best site\"."
)

# Per-scored-column input-contract Sanity_Range (design Model 3, checks 8–9).
#
# These are *input-contract sanity bounds* — the plausible physical range a
# stored value must fall within to be a well-formed input to the decision
# engine. They are DISTINCT from the S2-01 §5.2 per-run scoring bounds, which
# are computed from the eligible population at scoring time; a value inside its
# Sanity_Range here still gets min–max normalised downstream. The bounds are
# consistent with the `COLUMN_UNITS` entry for each column and the S2-01 §2
# units / Directions:
#
#   wind_speed            m/s              [0, 25]        higher_is_better
#   demand_proxy          normalised 0–1   [0, 1]         higher_is_better
#   dist_transmission_km  km (EPSG:3577)   [0, 2000]      lower_is_better
#   dist_substation_km    km (EPSG:3577)   [0, 2000]      lower_is_better
#   slope_deg             degrees          [0, 90]        lower_is_better
#   elevation_m           metres           [-20, 3000]    context
#   inside_rez            boolean          {false, true}  higher_is_better
#   protected_area        boolean          {false, true}  hard-constraint context
#
# Out-of-range values are reported (expected vs observed) and fail their check;
# they are never clamped or coerced silently.
SANITY_RANGES: dict[str, tuple[float, float] | frozenset[bool]] = {
    "wind_speed": (0.0, 25.0),
    "demand_proxy": (0.0, 1.0),
    "dist_transmission_km": (0.0, 2000.0),
    "dist_substation_km": (0.0, 2000.0),
    "slope_deg": (0.0, 90.0),
    "elevation_m": (-20.0, 3000.0),
    "inside_rez": frozenset({False, True}),
    "protected_area": frozenset({False, True}),
}


def _format_bound(bound: tuple[float, float] | frozenset[bool]) -> str:
    """Human-readable Sanity_Range for a Check_Record expected value.

    Numeric bounds render as a closed interval ``[lo, hi]``; boolean bounds
    render as the allowed set ``{false, true}``. Used only for reporting — the
    check logic reads the raw ``bound`` from ``SANITY_RANGES``.
    """
    if isinstance(bound, frozenset):
        return "{" + ", ".join(str(v).lower() for v in sorted(bound)) + "}"
    lo, hi = bound
    return f"[{lo:g}, {hi:g}]"


# ---------------------------------------------------------------------------
# Frozen-baseline reference (design Component 1)
# ---------------------------------------------------------------------------


def freeze_baseline(
    integrated_path: Path | None = None,
    *,
    write: bool = False,
) -> dict:
    """
    Resolve the Sprint 1 integrated feature table and return its baseline record.

    The record is::

        {
          "artefact": "s1-08 integrated feature table",
          "path": str,            # relative to PROJECT_ROOT
          "layer": "integrated_features",   # integration.config.OUTPUT_LAYER
          "version": "2026",      # integration.config.INTEGRATION_VINTAGE
          "sha256": "<64-hex>",   # common.geo.sha256_file (observed, this run)
          "bytes": int,           # path.stat().st_size
          "bytes_human": "…",     # common.geo.human_bytes
          "storage_crs": "EPSG:4326",   # copied from integration.config
          "computation_crs": "EPSG:3577",
          "frozen_at_utc": "…",   # when the baseline was first frozen
          "frozen_by": "pipeline.validate.freeze_baseline",
          "verified_at_utc": "…", # this run (common.geo.utc_now)
          "hash_ok": bool,        # observed sha256 == frozen sha256
        }

    The persisted Baseline_Manifest (Model 1) holds the *frozen reference*: the
    fields above **excluding** the per-run ``verified_at_utc`` and ``hash_ok``.
    The returned dict is that manifest record plus ``verified_at_utc`` and
    ``hash_ok`` (Model 2's ``baseline`` block).

    Freeze semantics:

    - ``write=True`` and no Baseline_Manifest exists → record the current
      SHA-256 as the frozen reference exactly once (a one-time freeze), unless
      Hash_Drift against an in-flight reference would be recorded — the initial
      freeze is guarded so it only happens from a clean state.
    - ``write=True`` and a Baseline_Manifest already exists → overwrite it with
      the newly recorded values.
    - ``write=False`` (the default, verify mode) → re-hash the current file and
      compare to the recorded baseline SHA-256, setting ``hash_ok`` so
      Hash_Drift is surfaced as a failing check rather than silently accepted.

    The Integrated_Dataset is treated as strictly read-only: no code path here
    writes to, moves, renames, or alters it. Only the sidecar Baseline_Manifest
    under INTEGRATION_META_DIR is ever written, and only in write mode.
    """
    path = DEFAULT_INTEGRATED_PATH if integrated_path is None else Path(integrated_path)
    manifest_path = DEFAULT_BASELINE_MANIFEST_PATH

    # Observed provenance for the file as it exists on disk right now. This is
    # a read of the frozen artefact — never a write.
    observed_sha = sha256_file(path)
    size = path.stat().st_size
    now = utc_now()

    # Resolve the recorded reference (if any) so we can compare and preserve
    # the original freeze timestamp across overwrites.
    existing: dict | None = None
    if manifest_path.exists():
        try:
            existing = json.loads(manifest_path.read_text())
        except (ValueError, OSError):
            existing = None

    frozen_sha = existing.get("sha256") if existing else None
    frozen_at = existing.get("frozen_at_utc") if existing else None

    try:
        rel_path = str(path.resolve().relative_to(integration_config.PROJECT_ROOT))
    except ValueError:
        # A fixture table outside the project root (tests) — record as given.
        rel_path = str(path)

    if write:
        if existing is None:
            # One-time freeze. Guard the initial recording: only freeze from a
            # clean state. There is no prior reference to drift from, so the
            # observed hash *is* the clean state we record; frozen_at is now.
            frozen_sha = observed_sha
            frozen_at = now
        else:
            # Re-freeze / overwrite with the newly observed values, preserving
            # the original freeze timestamp only if this is a genuine re-record
            # of the same artefact. Overwrite adopts the observed hash as the
            # new reference.
            frozen_sha = observed_sha
            frozen_at = frozen_at or now
    else:
        # Verify mode with no recorded reference yet: the observed hash is all
        # we have, so hash_ok is trivially True against itself and frozen_at is
        # unknown until a write establishes it.
        if frozen_sha is None:
            frozen_sha = observed_sha
        if frozen_at is None:
            frozen_at = now

    hash_ok = observed_sha == frozen_sha

    manifest_record = {
        "artefact": "s1-08 integrated feature table",
        "path": rel_path,
        "layer": OUTPUT_LAYER,
        "version": INTEGRATION_VINTAGE,
        "sha256": frozen_sha,
        "bytes": size,
        "bytes_human": human_bytes(size),
        "storage_crs": STORAGE_CRS,
        "computation_crs": COMPUTATION_CRS,
        "frozen_at_utc": frozen_at,
        "frozen_by": "pipeline.validate.freeze_baseline",
    }

    if write:
        # Guard: never record a drifted state as the frozen reference. On the
        # initial freeze frozen_sha == observed_sha by construction, so this
        # only bites a re-freeze that somehow disagrees with itself; recording
        # is prevented until a clean state is established.
        if manifest_record["sha256"] != observed_sha:
            raise RuntimeError(
                "refusing to record Baseline_Manifest with a drifted SHA-256; "
                "establish a clean state before freezing"
            )
        atomic_write_json(manifest_path, manifest_record)

    return {
        **manifest_record,
        "verified_at_utc": now,
        "hash_ok": hash_ok,
    }


# ---------------------------------------------------------------------------
# Input-contract checks (design Component 2)
# ---------------------------------------------------------------------------
#
# Consumer contract (holistic note): S2-05 scoring (KAN-42) and the S2-08
# decision service (KAN-45) read the Validation_Result JSON sidecar this tier
# emits and gate on its `all_passed` verdict — they never re-run validation.
# This is a preliminary-screening precondition (Screening_Language): the engine
# only screens data it has verified. This function is the source of the
# Check_Records that feed that verdict.


def _run_integrated_input_checks(
    verbose: bool = False,
    integrated_path: Path | None = None,
) -> list[dict]:
    """
    Input-contract checks on the frozen S1-08 integrated feature table.

    Returns a list of ``{"name", "expected", "observed", "passed"}`` dicts using
    the same ``check(name, expected, observed, passed)`` helper as every other
    tier — no silent passes: each check states expected vs observed vs a boolean
    pass/fail. Returns ``[]`` only when the integrated table does not exist yet
    (a partial pipeline run), never to skip a check silently on a table that is
    present.

    The battery (design Component 2) is twelve checks; this function builds them
    in order into a single ``checks`` list:

      1. baseline hash matches the frozen reference   (this task)
      2. required columns present                      (this task)
      3. scored feature columns present                (this task)
      4. cell_id non-null                              (task 4.3)
      5. cell_id unique                                (task 4.3)
      6. coordinates valid & in the NSW envelope       (task 4.3)
      7. geometry validity & storage CRS               (task 4.3)
      8. units/ranges per scored column                (task 4.5)
      9. missing-value counts per feature              (task 4.5)
      10. eligible present & boolean, no nulls         (task 4.7)
      11. eligible/exclusion_reason consistent         (task 4.7)
      12. at least one Eligible_Cell                   (task 4.7)

    Checks 4–12 are added by later tasks; they append to the same ``checks``
    list at the marked insertion point below, reading the single GeoDataFrame
    loaded once near the top. The Integrated_Dataset is read-only here — the
    validator never reprojects it (storage is EPSG:4326; any distance/area logic
    uses COMPUTATION_CRS explicitly).
    """
    path = DEFAULT_INTEGRATED_PATH if integrated_path is None else Path(integrated_path)

    checks: list[dict] = []

    def check(name, expected, observed, passed):
        checks.append({"name": name, "expected": expected,
                       "observed": observed, "passed": bool(passed)})

    # A partial pipeline run has not produced the integrated table yet. Return
    # [] so the gate is a no-op until the S1-08 artefact exists — never to skip
    # a check on a table that IS present (that would be a silent pass). The
    # run() wiring (task 7.1) turns this empty list into all_passed=False.
    if not path.exists():
        return checks

    import geopandas as gpd

    # Load the frozen table once; every content check (2–12) reads this same
    # GeoDataFrame. Check 1 (hash) reads the file bytes via freeze_baseline and
    # needs no columns, so it runs off `path` directly.
    gdf = gpd.read_file(path, layer=OUTPUT_LAYER)
    observed_columns = list(gdf.columns)

    # --- Check 1 — baseline hash matches the frozen reference (1.3, 1.4) -----
    # Verify mode (write=False): re-hash the current file and compare to the
    # recorded Baseline_Manifest SHA-256 so Hash_Drift surfaces as a FAIL rather
    # than being silently accepted. hash_ok is the single source of truth.
    baseline = freeze_baseline(path)
    check(
        "Baseline hash matches the frozen reference",
        "sha256 == frozen reference",
        "match" if baseline["hash_ok"] else "DRIFTED",
        baseline["hash_ok"],
    )

    # --- Check 2 — required columns present (2.1, 2.3, 2.4) -----------------
    # Expected is the full OUTPUT_COLUMNS set, READ from the Schema_Authority
    # (never re-typed). Observed names any missing columns; FAIL if any absent.
    missing_required = [c for c in OUTPUT_COLUMNS if c not in observed_columns]
    check(
        "Required columns present",
        f"all {len(OUTPUT_COLUMNS)} OUTPUT_COLUMNS present",
        "0 missing" if not missing_required
        else f"{len(missing_required)} missing: {missing_required}",
        not missing_required,
    )

    # --- Check 3 — scored feature columns present (2.2, 2.5, 2.6, 2.7) ------
    # Expected is the full SCORED_FEATURE_COLUMNS set (a superset of the S2-01
    # §2 frozen Scored_Criteria), READ from the Schema_Authority. Observed names
    # any missing scored columns; FAIL if any absent.
    missing_scored = [c for c in SCORED_FEATURE_COLUMNS if c not in observed_columns]
    check(
        "Scored feature columns present",
        f"all {len(SCORED_FEATURE_COLUMNS)} SCORED_FEATURE_COLUMNS present",
        "0 missing" if not missing_scored
        else f"{len(missing_scored)} missing: {missing_scored}",
        not missing_scored,
    )

    # --- Check 4 — cell_id non-null (3.1, 3.2) ------------------------------
    # Expected zero nulls; observed the null count; FAIL if any. Degrade
    # gracefully if the column is somehow absent (checks 2/3 already report a
    # missing required column) rather than raising.
    if "cell_id" not in observed_columns:
        check(
            "cell_id non-null",
            "0 null cell_id values",
            "unavailable: cell_id column absent",
            False,
        )
    else:
        null_cell_ids = int(gdf["cell_id"].isna().sum())
        check(
            "cell_id non-null",
            "0 null cell_id values",
            f"{null_cell_ids:,} null cell_id values",
            null_cell_ids == 0,
        )

    # --- Check 5 — cell_id unique (3.3, 3.4) --------------------------------
    # Expected zero duplicates; observed the duplicate count (rows beyond the
    # first occurrence of each value); FAIL if any.
    if "cell_id" not in observed_columns:
        check(
            "cell_id unique",
            "0 duplicate cell_id values",
            "unavailable: cell_id column absent",
            False,
        )
    else:
        duplicate_cell_ids = int(gdf["cell_id"].duplicated(keep="first").sum())
        check(
            "cell_id unique",
            "0 duplicate cell_id values",
            f"{duplicate_cell_ids:,} duplicate cell_id values",
            duplicate_cell_ids == 0,
        )

    # --- Check 6 — coordinates valid & in the NSW envelope (4.1, 4.2) -------
    # Expected: every centroid_lat ∈ [-90, 90], centroid_lon ∈ [-180, 180], and
    # every centroid within the NSW analysis bounding box (NSW_BBOX, read from
    # grid.config as (west, south, east, north) — never re-typed). Observed the
    # out-of-range count; FAIL if any. This is a coordinate-range test on the
    # stored EPSG:4326 lat/lon columns — no reprojection, no distance/area math.
    coord_cols_present = "centroid_lat" in observed_columns and "centroid_lon" in observed_columns
    if not coord_cols_present:
        check(
            "Coordinates valid and within the NSW analysis bounding box",
            "centroid_lat ∈ [-90, 90], centroid_lon ∈ [-180, 180], "
            "centroid within NSW_BBOX",
            "unavailable: centroid_lat/centroid_lon column absent",
            False,
        )
    else:
        west, south, east, north = NSW_BBOX
        lat = gdf["centroid_lat"]
        lon = gdf["centroid_lon"]
        lat_ok = lat.between(-90.0, 90.0)
        lon_ok = lon.between(-180.0, 180.0)
        in_box = lat.between(south, north) & lon.between(west, east)
        out_of_range = int((~(lat_ok & lon_ok & in_box)).sum())
        check(
            "Coordinates valid and within the NSW analysis bounding box",
            "centroid_lat ∈ [-90, 90], centroid_lon ∈ [-180, 180], "
            f"centroid within NSW_BBOX {NSW_BBOX}",
            f"{out_of_range:,} out-of-range centroids",
            out_of_range == 0,
        )

    # --- Check 7 — geometry validity & storage CRS (4.3, 4.4, 4.5, 4.6) -----
    # Two conditions in one Check_Record: every geometry is valid AND the table
    # is stored in STORAGE_CRS (EPSG:4326). The observed CRS is recorded
    # regardless of pass/fail (4.4). The gdf is never reprojected — this is a
    # pure inspection of the stored geometry column and its CRS; any downstream
    # distance/area logic uses COMPUTATION_CRS explicitly (4.6).
    #
    # Compare gdf.crs to STORAGE_CRS robustly: gdf.crs is a pyproj CRS object,
    # so match its authority tuple against STORAGE_CRS ("EPSG:4326"). A crs of
    # None is a failing CRS assertion (unknown storage frame).
    if gdf.crs is None:
        observed_crs = "None"
        crs_ok = False
    else:
        observed_crs = gdf.crs.to_string()
        try:
            crs_ok = gdf.crs.to_authority() == tuple(STORAGE_CRS.split(":"))
        except Exception:
            crs_ok = observed_crs == STORAGE_CRS

    geom = gdf.geometry
    invalid_geom = int((~geom.is_valid | geom.is_empty | geom.isna()).sum())

    check(
        "Geometry valid and stored in the storage CRS",
        f"all geometries valid and crs == {STORAGE_CRS}",
        f"{invalid_geom:,} invalid geometries; crs={observed_crs}",
        invalid_geom == 0 and crs_ok,
    )

    # --- Check 8 — units/ranges per scored column (5.3, 5.4, 5.5) -----------
    # One Check_Record per scored column that HAS a Sanity_Range bound (read
    # from SANITY_RANGES). Only 8 of the 10 SCORED_FEATURE_COLUMNS have a bound;
    # dist_connection_km and land_use have none and are not range-checked here.
    # Expected is the column's Sanity_Range; observed is the out-of-range count.
    # Out-of-range values are REPORTED (expected vs observed) and fail the check
    # — they are never clamped, coerced, or silently modified (5.5). For numeric
    # bounds a non-numeric entry (coerced to NaN by to_numeric) counts as
    # out-of-range rather than being silently dropped; for boolean bounds any
    # value not in {False, True} counts as out-of-range.
    import pandas as pd

    for column in SCORED_FEATURE_COLUMNS:
        bound = SANITY_RANGES.get(column)
        if bound is None:
            # No input-contract range for this scored column (e.g.
            # dist_connection_km, land_use) — nothing to range-check.
            continue

        if column not in observed_columns:
            # Absence is already reported by check 3; degrade gracefully here
            # rather than raising, but never report a silent pass.
            check(
                f"Units/ranges within sanity bound: {column}",
                f"all values within Sanity_Range {_format_bound(bound)}",
                f"unavailable: {column} column absent",
                False,
            )
            continue

        series = gdf[column]

        if isinstance(bound, frozenset):
            # Boolean Sanity_Range: count values not in {False, True}. Nulls and
            # any non-boolean value are out-of-range (not silently accepted).
            allowed = bound
            out_of_range = int(sum(0 if v in allowed else 1 for v in series.tolist()))
        else:
            lo, hi = bound
            # Coerce to numeric so a non-numeric value becomes NaN; NaN is
            # neither < lo nor > hi, so count it explicitly as out-of-range
            # rather than letting it slip through.
            numeric = pd.to_numeric(series, errors="coerce")
            below = numeric < lo
            above = numeric > hi
            non_numeric = numeric.isna() & series.notna()
            out_of_range = int((below | above | non_numeric).sum())

        check(
            f"Units/ranges within sanity bound: {column}",
            f"all values within Sanity_Range {_format_bound(bound)}",
            f"{out_of_range:,} out-of-range values",
            out_of_range == 0,
        )

    # --- Check 9 — missing-value counts per feature (6.1, 6.2, 6.3) ---------
    # One Check_Record per column in SCORED_FEATURE_COLUMNS (all 10), read from
    # the Schema_Authority. Observed is the missing/null count; expected is an
    # explicit non-empty string so the count is REPORTED rather than silently
    # omitted (6.3 — no silent pass). A nonzero missing count fails the check so
    # an injected null is a visible failure.
    for column in SCORED_FEATURE_COLUMNS:
        if column not in observed_columns:
            # Absence is already reported by check 3; report explicitly here
            # rather than raising, and never as a silent pass.
            check(
                f"Missing-value count: {column}",
                "0 missing values",
                f"unavailable: {column} column absent",
                False,
            )
            continue

        missing = int(gdf[column].isna().sum())
        check(
            f"Missing-value count: {column}",
            "0 missing values",
            f"{missing:,} missing values",
            missing == 0,
        )

    # --- Check 10 — eligible present & boolean, no nulls (7.1, 7.2, 7.2A) ---
    # Re-assert the EXACT invariant pipeline/integration/merge.py enforces at
    # production time (do not reinvent): boolean dtype with zero nulls. The
    # dtype string test `str(dtype) in ("bool", "boolean")` treats every other
    # or ambiguous dtype (e.g. object, int64, float64) as non-boolean → FAIL.
    # "eligible" is in BOOL_COLUMNS; merge.py references the literal, so match
    # merge.py here to keep the two gates textually aligned. Degrade gracefully
    # if the column is absent (check 2 already reports the missing column)
    # rather than raising.
    eligible_col = "eligible"
    assert eligible_col in BOOL_COLUMNS  # schema-authority sanity, not runtime
    if eligible_col not in observed_columns:
        check(
            "eligible present, boolean, no nulls",
            "boolean dtype, 0 nulls",
            "unavailable: eligible column absent",
            False,
        )
    else:
        elig = gdf[eligible_col]
        n_null = int(elig.isna().sum())
        is_bool = str(elig.dtype) in ("bool", "boolean")
        check(
            "eligible present, boolean, no nulls",
            "boolean dtype, 0 nulls",
            f"dtype {elig.dtype}, {n_null:,} nulls",
            n_null == 0 and is_bool,
        )

    # --- Check 11 — eligible/exclusion_reason consistent (7.3, 7.4) --------
    # Re-assert the merge.py invariant verbatim: a cell is inconsistent when it
    # is eligible yet carries an exclusion reason, or is ineligible yet has no
    # reason. Expected 0 inconsistent rows; observed the inconsistent-row count.
    # Degrade gracefully if either column is absent (check 2 reports it) rather
    # than raising.
    if eligible_col not in observed_columns or "exclusion_reason" not in observed_columns:
        check(
            "eligible/exclusion_reason consistent",
            "0 inconsistent rows",
            "unavailable: eligible or exclusion_reason column absent",
            False,
        )
    else:
        eligible = gdf[eligible_col].fillna(False).astype(bool)
        reason = gdf["exclusion_reason"]
        reason_present = reason.notna() & (reason.fillna("").astype(str).str.len() > 0)
        inconsistent = int(
            ((eligible & reason_present) | (~eligible & ~reason_present)).sum()
        )
        check(
            "eligible/exclusion_reason consistent",
            "0 inconsistent rows",
            f"{inconsistent:,} inconsistent rows",
            inconsistent == 0,
        )

    # --- Check 12 — at least one Eligible_Cell (7.5, 7.6) ------------------
    # A ranking is never emitted from zero eligible cells (the consumer contract
    # in the module docstring). Expected ≥ 1 eligible; observed the Eligible_Cell
    # count; FAIL if zero. Uses the same fillna(False).astype(bool) coercion as
    # merge.py so a null eligible is treated as ineligible for the count.
    if eligible_col not in observed_columns:
        check(
            "At least one Eligible_Cell",
            "≥ 1 eligible cell",
            "unavailable: eligible column absent",
            False,
        )
    else:
        n_eligible = int(gdf[eligible_col].fillna(False).astype(bool).sum())
        check(
            "At least one Eligible_Cell",
            "≥ 1 eligible cell",
            f"{n_eligible:,} eligible cells",
            n_eligible >= 1,
        )

    if verbose:
        for entry in checks:
            print(f"    [{'PASS' if entry['passed'] else 'FAIL'}] {entry['name']}")
    return checks


# ---------------------------------------------------------------------------
# Validation_Result sidecar + Validation_Report emitter (design Component 3)
# ---------------------------------------------------------------------------
#
# These are PURE writers: they compute the Validation_Result from a baseline
# record + a list of Check_Records and write the two output files. They never
# raise on a data-quality failure — the Halt_Or_Flag decision lives at the
# engine boundary (S2-03+), which reads `all_passed`. Wiring into run() is
# task 7.1; these functions are standalone so task 6.2 can test them
# hermetically by monkeypatching the module output-path constants.


def _verdict(checks: list[dict]) -> bool:
    """
    The `all_passed` verdict over a list of Check_Records.

    Semantics (requirements 9.2 / 10.3):

    - When ``checks`` is non-empty, ``all_passed`` is the conjunction of every
      Check_Record's ``passed``. The baseline hash match is represented as
      check 1 in a present-table battery, so the hash is already folded into
      this conjunction — no separate hash term is needed here.
    - When ``checks`` is empty (the Integrated_Dataset is absent, so
      ``_run_integrated_input_checks`` returned ``[]``), there is **no** hash
      check and nothing was verified. An empty ``all(...)`` is vacuously
      ``True`` in Python, which would report a missing dataset as passing — a
      silent pass this gate forbids. So a missing/empty battery is forced to
      ``all_passed = False`` (requirement 4A.1 → 10.4A, 8.3).
    """
    if not checks:
        return False
    return all(bool(c["passed"]) for c in checks)


def build_validation_result(baseline: dict, checks: list[dict]) -> dict:
    """
    Build the Validation_Result object (design Model 2) from a baseline record
    and a list of Check_Records.

    Shape::

        {
          "generated_at_utc": "…",              # common.geo.utc_now
          "generator": "pipeline.validate",
          "baseline": { …Model 1 record…,       # incl. verified_at_utc, hash_ok
                        "verified_at_utc": "…", "hash_ok": bool },
          "all_passed": bool,
          "n_checks": int,
          "n_passed": int,
          "checks": [ {name, expected, observed, passed}, … ],
        }

    Invariants enforced (requirement 10.3):

    - ``all_passed == all(c["passed"] for c in checks)`` for a non-empty
      battery, and ``all_passed == False`` for an empty one (see ``_verdict``).
    - ``n_passed == sum(1 for c in checks if c["passed"])``.
    - ``n_checks == len(checks)``.

    ``checks`` is copied into the exact ``{name, expected, observed, passed}``
    shape (with ``passed`` coerced to a plain ``bool``) so the emitted result
    is JSON-clean and cannot carry incidental extra keys.
    """
    normalised = [
        {
            "name": c["name"],
            "expected": c["expected"],
            "observed": c["observed"],
            "passed": bool(c["passed"]),
        }
        for c in checks
    ]
    n_passed = sum(1 for c in normalised if c["passed"])
    return {
        "generated_at_utc": utc_now(),
        "generator": "pipeline.validate",
        "baseline": baseline,
        "all_passed": _verdict(normalised),
        "n_checks": len(normalised),
        "n_passed": n_passed,
        "checks": normalised,
    }


def write_validation_result(result: dict, meta_dir: Path | None = None) -> Path:
    """
    Atomically write the Validation_Result JSON sidecar (requirement 10.1,
    12.1).

    Writes to ``meta_dir / VALIDATION_RESULT_FILENAME`` via
    ``common.geo.atomic_write_json``. ``meta_dir`` defaults to the module's
    ``INTEGRATION_META_DIR`` (resolved at call time so a monkeypatched
    constant is honoured in tests). Returns the written path.

    Written even when ``result["checks"]`` is empty (requirement 4A.1 → 10.4A):
    a missing/absent table still yields a written result with
    ``all_passed = False``.
    """
    directory = INTEGRATION_META_DIR if meta_dir is None else Path(meta_dir)
    out_path = directory / VALIDATION_RESULT_FILENAME
    atomic_write_json(out_path, result)
    return out_path


def render_validation_report(result: dict) -> str:
    """
    Render the Validation_Report markdown for a Validation_Result.

    Layout (requirements 8A.1, 8A.1A, 8A.2, 10.5, 10.6):

    1. ``banner("validate")`` as the FIRST content (do-not-edit stamp, 10.6).
    2. A title and the Screening_Language purpose sentence (preliminary
       screening — never "best site"), so the report and any diagnostic output
       describe the validator's purpose in Screening_Language.
    3. An overall verdict line (PASS/FAIL, n_passed/n_checks).
    4. The expected/observed/result table — one row per Check_Record with a
       PASS/FAIL result column (10.5). When there are zero Check_Records the
       table is rendered with an explicit "no checks executed" note so the
       absence is visible rather than silent (4A.1 → 10.4A).
    5. A baseline summary (path, version, sha256, hash_ok).
    """
    baseline = result.get("baseline") or {}
    lines: list[str] = []

    # 1. Banner FIRST (requirement 10.6).
    lines.append(banner("validate"))
    lines.append("")

    # 2. Title + Screening_Language purpose (requirements 8A.1/8A.1A/8A.2).
    lines.append("# Integrated-input contract validation")
    lines.append("")
    lines.append(SCREENING_PURPOSE)
    lines.append("")

    # 3. Overall verdict.
    verdict = "PASS" if result.get("all_passed") else "FAIL"
    lines.append(
        f"**Result:** {verdict} "
        f"({result.get('n_passed', 0)}/{result.get('n_checks', 0)} checks passed)"
    )
    lines.append("")

    # 4. Expected / observed / result table (requirement 10.5).
    lines.append("## Checks")
    lines.append("")
    checks = result.get("checks") or []
    if not checks:
        lines.append(
            "_No checks executed — the integrated table was absent, so this "
            "validation fails as a matter of contract (nothing was verified)._"
        )
        lines.append("")
    else:
        lines.append("| Check | Expected | Observed | Result |")
        lines.append("| --- | --- | --- | --- |")
        for c in checks:
            result_cell = "PASS" if c["passed"] else "FAIL"
            # Escape pipes so a stray "|" in an observed value cannot break the
            # markdown table layout.
            name = str(c["name"]).replace("|", "\\|")
            expected = str(c["expected"]).replace("|", "\\|")
            observed = str(c["observed"]).replace("|", "\\|")
            lines.append(
                f"| {name} | {expected} | {observed} | {result_cell} |"
            )
        lines.append("")

    # 5. Baseline summary.
    lines.append("## Baseline")
    lines.append("")
    lines.append(f"- Artefact: {baseline.get('artefact', 'n/a')}")
    lines.append(f"- Path: `{baseline.get('path', 'n/a')}`")
    lines.append(f"- Layer: {baseline.get('layer', 'n/a')}")
    lines.append(f"- Version: {baseline.get('version', 'n/a')}")
    lines.append(f"- SHA-256: `{baseline.get('sha256', 'n/a')}`")
    lines.append(f"- Bytes: {baseline.get('bytes_human', 'n/a')}")
    lines.append(f"- Storage CRS: {baseline.get('storage_crs', 'n/a')}")
    lines.append(f"- Computation CRS: {baseline.get('computation_crs', 'n/a')}")
    lines.append(f"- Verified at (UTC): {baseline.get('verified_at_utc', 'n/a')}")
    hash_ok = baseline.get("hash_ok")
    lines.append(
        f"- Hash matches frozen reference: {'yes' if hash_ok else 'no'}"
    )
    lines.append("")

    return "\n".join(lines)


def write_validation_report(result: dict, meta_dir: Path | None = None) -> Path:
    """
    Render and atomically write the Validation_Report markdown (requirements
    10.5, 10.6, 12.2).

    Writes to ``meta_dir / VALIDATION_REPORT_FILENAME`` via
    ``common.geo.atomic_write_text``. ``meta_dir`` defaults to the module's
    ``INTEGRATION_META_DIR`` (resolved at call time so a monkeypatched constant
    is honoured in tests). Returns the written path.

    Written even when the checks list is empty (requirement 4A.1 → 10.4A).
    """
    directory = INTEGRATION_META_DIR if meta_dir is None else Path(meta_dir)
    out_path = directory / VALIDATION_REPORT_FILENAME
    atomic_write_text(out_path, render_validation_report(result))
    return out_path


def write_validation_outputs(
    baseline: dict,
    checks: list[dict],
    meta_dir: Path | None = None,
) -> tuple[dict, Path, Path]:
    """
    Build the Validation_Result and write BOTH output files (JSON + report).

    Convenience seam for run() (task 7.1) and for hermetic tests (task 6.2):
    a single call that builds the result, writes the JSON sidecar and the
    markdown report, and returns ``(result, json_path, report_path)``.

    Both files are always written — including when ``checks`` is empty — so a
    missing/absent table still yields written outputs with ``all_passed=False``
    (requirement 4A.1 → 10.4A, 8.3). This function is a PURE writer: it never
    raises on a data-quality failure.
    """
    result = build_validation_result(baseline, checks)
    json_path = write_validation_result(result, meta_dir=meta_dir)
    report_path = write_validation_report(result, meta_dir=meta_dir)
    return result, json_path, report_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _point_in_polygons(lon: float, lat: float, geometries: list[dict]) -> bool:
    """Containment via single-pixel rasterisation (cell-centre rule)."""
    res = 0.0025
    transform = from_origin(lon - res / 2, lat + res / 2, res, res)
    burned = rasterize(((g, 1) for g in geometries), out_shape=(1, 1),
                       transform=transform, fill=0, all_touched=False, dtype="uint8")
    return bool(burned[0, 0])


def _sample_raster_at(path: Path, lon: float, lat: float) -> float:
    """Sample band 1 at a WGS84 point, handling CRS transform and scale."""
    with rasterio.open(path) as src:
        xs, ys = warp_transform("EPSG:4326", src.crs, [lon], [lat])
        value = next(src.sample([(xs[0], ys[0])]))[0]
        scale = src.scales[0] if src.scales else 1.0
    return float(value) * scale


# ---------------------------------------------------------------------------
# Wind farm geographic checks
# ---------------------------------------------------------------------------


def _run_cross_domain_checks(verbose: bool, max_slope: float = DEFAULT_MAX_SLOPE_DEG) -> list[dict]:
    """Check wind farms against geographic layers."""
    checks: list[dict] = []

    def check(name, expected, observed, passed):
        checks.append({"name": name, "expected": expected,
                       "observed": observed, "passed": bool(passed)})

    wind_farms_path = wind_config.WIND_REF_DIR / "nsw_wind_farms_new_england.csv"
    if not wind_farms_path.exists():
        return checks

    # Load geographic layers
    capad_nsw_path = geo_config.GEO_DIR / "protected" / "dcceew_capad-terrestrial_2024_nsw.geojson"
    ne_path = geo_config.GEO_DIR / "coastline" / "ne_land-50m_australia.geojson"
    abs_path = geo_config.GEO_DIR / "boundaries" / "abs_aus_2021_national.geojson"
    gl1_slope_path = (geo_config.GEO_DIR / "elevation" /
                      f"srtm-gl1_slope-horn_30m_{geo_config.GL1_AREA}.tif")

    ne_geoms = [f["geometry"] for f in
                json.loads(ne_path.read_text())["features"] if f.get("geometry")]
    abs_geoms = [f["geometry"] for f in
                 json.loads(abs_path.read_text())["features"] if f.get("geometry")]
    capad_geoms = [f["geometry"] for f in
                   json.loads(capad_nsw_path.read_text())["features"] if f.get("geometry")]

    with open(wind_farms_path) as fh:
        farms = list(csv.DictReader(fh))

    for farm in farms:
        name = farm["name"]
        lon, lat = float(farm["longitude"]), float(farm["latitude"])
        on_ne = _point_in_polygons(lon, lat, ne_geoms)
        on_abs = _point_in_polygons(lon, lat, abs_geoms)
        check(f"{name}: on land", "both masks", f"NE={on_ne}, ABS={on_abs}",
              on_ne and on_abs)
        in_capad = _point_in_polygons(lon, lat, capad_geoms)
        check(f"{name}: outside CAPAD", "outside",
              "inside" if in_capad else "outside", not in_capad)
        if gl1_slope_path.exists():
            slope = _sample_raster_at(gl1_slope_path, lon, lat)
            check(f"{name}: slope < {max_slope:.0f} deg", f"< {max_slope:.0f} deg",
                  f"{slope:.1f} deg", slope < max_slope)

    return checks


# ---------------------------------------------------------------------------
# Scoring cross-domain checks (S1-10)
# ---------------------------------------------------------------------------


def _run_scoring_cross_checks(verbose: bool = False) -> list[dict]:
    """
    Cross-domain checks on the S1-10 Scored_Table.

    These live here rather than in `pipeline/scoring/validate.py` because they
    span domains: they compare the scored table against the S1-02 analysis
    grid and the S1-08 integrated table, which the scoring stage's own
    validation tier does not load. Within-stage checks (score range, rank
    contiguity, contribution reconciliation) stay in the scoring package.

    Returns [] when the scored table has not been generated yet, so a partial
    pipeline run does not fail on a stage that has not been run.
    """
    checks: list[dict] = []

    def check(name, expected, observed, passed):
        checks.append({"name": name, "expected": expected,
                       "observed": observed, "passed": bool(passed)})

    from .scoring import config as scoring_config

    scored_path = scoring_config.SCORING_DIR / scoring_config.OUTPUT_FILENAME
    grid_path = scoring_config.PROJECT_ROOT / "DATA" / "grid" / "nsw_analysis_grid.gpkg"
    if not scored_path.exists():
        return checks

    import geopandas as gpd

    scored = gpd.read_file(scored_path, layer=scoring_config.OUTPUT_LAYER)
    cell_column = scoring_config.CELL_ID_COLUMN

    # 1. The scored table covers exactly the analysis grid.
    if grid_path.exists():
        grid_ids = set(gpd.read_file(grid_path, layer="nsw_grid")[cell_column])
        scored_ids = set(scored[cell_column])
        missing = grid_ids - scored_ids
        extra = scored_ids - grid_ids
        check("Scored table cell_id set equals the analysis grid",
              "0 missing, 0 extra",
              f"{len(missing):,} missing, {len(extra):,} extra",
              not missing and not extra)

    # 2. Eligibility agrees with the integrated table that gated it. A cell
    #    the exclusion layer rejected must not carry a score here.
    integrated_path = scoring_config.INTEGRATED_PATH
    if integrated_path.exists():
        integrated = gpd.read_file(
            integrated_path, layer=scoring_config.INTEGRATED_LAYER,
            columns=[cell_column, scoring_config.ELIGIBLE_COLUMN],
        )
        merged = scored[[cell_column, scoring_config.SCORE_COLUMN]].merge(
            integrated, on=cell_column, how="left", validate="one_to_one",
        )
        eligible = merged[scoring_config.ELIGIBLE_COLUMN].fillna(False).astype(bool)
        has_score = merged[scoring_config.SCORE_COLUMN].notna()
        violations = int((~eligible & has_score).sum()) + int((eligible & ~has_score).sum())
        check("Scored cells match the S1-07 eligibility flag in the integrated table",
              "0 mismatches",
              f"{violations:,} mismatches "
              f"({int(eligible.sum()):,} eligible, {int(has_score.sum()):,} scored)",
              violations == 0)

    if verbose:
        for entry in checks:
            print(f"    [{'PASS' if entry['passed'] else 'FAIL'}] {entry['name']}")
    return checks


# ---------------------------------------------------------------------------
# Shortlist cross-domain checks (S1-11)
# ---------------------------------------------------------------------------


def _latest_shortlist_outputs(shortlist_config) -> tuple[Path | None, Path | None]:
    """
    Discover the most recent written Shortlist_CSV / Shortlist_GeoJSON pair.

    The shortlist filenames are timestamped (`sprint1_shortlist_<UTCdate>.{csv,
    geojson}`), so rather than assuming a fixed name we glob the shortlist
    directory for the `OUTPUT_PREFIX` pattern and take the most recently
    modified pair — the same "find the latest output" discipline the other
    stages' validators use. Returns (None, None) when no output exists yet, so
    a partial pipeline run does not fail on a stage that has not been run.
    """
    out_dir = shortlist_config.SHORTLIST_DIR
    if not out_dir.exists():
        return None, None
    prefix = shortlist_config.OUTPUT_PREFIX
    csvs = sorted(out_dir.glob(f"{prefix}_*.csv"),
                  key=lambda p: p.stat().st_mtime, reverse=True)
    if not csvs:
        return None, None
    csv_path = csvs[0]
    geojson_path = csv_path.with_suffix(".geojson")
    return csv_path, (geojson_path if geojson_path.exists() else None)


def _run_shortlist_cross_checks(verbose: bool = False) -> list[dict]:
    """
    Cross-domain checks on the S1-11 shortlist (Requirement 12.7).

    These live here rather than in `pipeline/shortlist/validate.py` because
    they span domains: they compare the written shortlist against the S1-10
    Scored_Table and the S1-02 Analysis_Grid, which the shortlist stage's own
    validation tier does not load. Within-stage checks (row count vs Top_N,
    eligible-only, ascending rank, non-null coordinates, CSV/GeoJSON equality,
    disclaimer presence) stay in the shortlist package.

    Every check reports expected vs observed vs an explicit pass/fail — no
    silent passes. Returns [] when the shortlist has not been generated yet, so
    a partial pipeline run does not fail on a stage that has not been run.

    Checks:
      1. shortlisted cell_id set ⊆ Scored_Table cell_id set;
      2. shortlisted cell_id set ⊆ Analysis_Grid cell_id set;
      3. each shortlisted cell's suitability_score AND rank equal the
         Scored_Table values for that cell_id (no re-scoring / re-ranking);
      4. each shortlisted cell's centroid_lat / centroid_lon equal the grid
         values for that cell_id (coordinates consistent across stages).
    """
    checks: list[dict] = []

    def check(name, expected, observed, passed):
        checks.append({"name": name, "expected": expected,
                       "observed": observed, "passed": bool(passed)})

    from .shortlist import config as shortlist_config

    csv_path, geojson_path = _latest_shortlist_outputs(shortlist_config)
    if csv_path is None:
        return checks

    import pandas as pd

    shortlist = pd.read_csv(csv_path)
    cell_col = "cell_id"
    if cell_col not in shortlist.columns:
        check("Shortlist_CSV carries a cell_id column",
              "cell_id present", "cell_id MISSING", False)
        return checks

    shortlisted_ids = set(shortlist[cell_col])

    # --- 1 & 3. Against the Scored_Table (subset + scores/ranks unchanged). ---
    scored_path = shortlist_config.SCORED_PATH
    if scored_path.exists():
        import geopandas as gpd

        scored = gpd.read_file(scored_path, layer=shortlist_config.SCORED_LAYER)
        scored_ids = set(scored[cell_col])
        not_in_scored = shortlisted_ids - scored_ids
        check("Shortlisted cell_id set is a subset of the Scored_Table cell_id set",
              "0 shortlisted cells absent from the Scored_Table",
              f"{len(not_in_scored):,} absent",
              not not_in_scored)

        # Scores/ranks match the Scored_Table for the shortlisted cells: this is
        # a FILTERING stage, so no re-scoring and no re-ranking (1.3, 4.6).
        merged = shortlist[[cell_col, "suitability_score", "rank"]].merge(
            scored[[cell_col, "suitability_score", "rank"]],
            on=cell_col, how="left", suffixes=("_shortlist", "_scored"),
        )
        score_mismatch = int(
            (~_close(merged["suitability_score_shortlist"],
                     merged["suitability_score_scored"])).sum()
        )
        rank_mismatch = int(
            (merged["rank_shortlist"].astype("Int64")
             != merged["rank_scored"].astype("Int64")).sum()
        )
        check("Shortlist scores and ranks equal the Scored_Table "
              "(no re-scoring / re-ranking)",
              "0 score mismatches, 0 rank mismatches",
              f"{score_mismatch:,} score mismatches, {rank_mismatch:,} rank mismatches",
              score_mismatch == 0 and rank_mismatch == 0)

    # --- 2 & 4. Against the Analysis_Grid (subset + coordinates equal). ---
    grid_path = shortlist_config.GRID_PATH
    if grid_path.exists():
        import geopandas as gpd

        grid = gpd.read_file(grid_path, layer=shortlist_config.GRID_LAYER)
        grid_ids = set(grid[cell_col])
        not_in_grid = shortlisted_ids - grid_ids
        check("Shortlisted cell_id set is a subset of the Analysis_Grid cell_id set",
              "0 shortlisted cells absent from the grid",
              f"{len(not_in_grid):,} absent",
              not not_in_grid)

        coords = shortlist[[cell_col, "centroid_lat", "centroid_lon"]].merge(
            grid[[cell_col, "centroid_lat", "centroid_lon"]],
            on=cell_col, how="left", suffixes=("_shortlist", "_grid"),
        )
        coord_mismatch = int(
            (
                ~_close(coords["centroid_lat_shortlist"], coords["centroid_lat_grid"])
                | ~_close(coords["centroid_lon_shortlist"], coords["centroid_lon_grid"])
            ).sum()
        )
        check("Shortlist coordinates equal the Analysis_Grid values for each cell_id",
              "0 coordinate mismatches",
              f"{coord_mismatch:,} coordinate mismatches",
              coord_mismatch == 0)

    if verbose:
        for entry in checks:
            print(f"    [{'PASS' if entry['passed'] else 'FAIL'}] {entry['name']}")
    return checks


def _close(a, b, tol: float = 1e-9):
    """
    Element-wise closeness for the cross-domain numeric comparisons, treating
    two nulls as equal and null-vs-value as unequal, so a missing join value is
    reported as a mismatch (a FAIL) rather than silently passing.
    """
    both_null = a.isna() & b.isna()
    return both_null | ((a - b).abs() <= tol)


# ---------------------------------------------------------------------------
# Land mask assessment
# ---------------------------------------------------------------------------


def _anchored_grid(bbox):
    """Snap a bbox outward onto the Atlas-anchored 0.05 deg lattice."""
    w, s, e, n = bbox
    k_w = math.floor((w - GWA_ORIGIN_LON) / CELL_DEG)
    k_e = math.ceil((e - GWA_ORIGIN_LON) / CELL_DEG)
    k_n = math.floor((GWA_ORIGIN_LAT - n) / CELL_DEG)
    k_s = math.ceil((GWA_ORIGIN_LAT - s) / CELL_DEG)
    west = GWA_ORIGIN_LON + k_w * CELL_DEG
    east = GWA_ORIGIN_LON + k_e * CELL_DEG
    north = GWA_ORIGIN_LAT - k_n * CELL_DEG
    south = GWA_ORIGIN_LAT - k_s * CELL_DEG
    cols = k_e - k_w
    rows = k_s - k_n
    transform = from_origin(west, north, CELL_DEG, CELL_DEG)
    return (west, south, east, north), rows, cols, transform


def _mask_from_polygons(path: Path, rows: int, cols: int, transform) -> np.ndarray:
    """Rasterise polygons with cell-centre rule."""
    geoms = [f["geometry"] for f in
             json.loads(path.read_text())["features"] if f.get("geometry")]
    return rasterize(
        ((g, 1) for g in geoms), out_shape=(rows, cols),
        transform=transform, fill=0, all_touched=False, dtype="uint8",
    ).astype(bool)


def _run_landmask_assessment(verbose: bool) -> Path:
    """Assess NE vs ABS land mask on the analysis grid."""
    apply_vsicurl_env()
    grid_bounds, rows, cols, transform = _anchored_grid(STRIP_BBOX)

    ne_path = geo_config.GEO_DIR / "coastline" / "ne_land-50m_australia.geojson"
    abs_path = geo_config.GEO_DIR / "boundaries" / "abs_aus_2021_national.geojson"
    ne_land = _mask_from_polygons(ne_path, rows, cols, transform)
    abs_land = _mask_from_polygons(abs_path, rows, cols, transform)

    both = ne_land & abs_land
    ne_only = ne_land & ~abs_land
    abs_only = abs_land & ~ne_land
    neither = ~ne_land & ~abs_land

    # Read GWA wind over the strip
    provenance = resolve_source("wind-speed", 100)
    with rasterio.open(f"/vsicurl/{provenance['signed_url']}") as src:
        window = from_bounds(*grid_bounds, transform=src.transform)
        window = window.round_offsets().round_lengths()
        raw = src.read(1, window=window)

    # Average to cells
    expected_shape = (rows * PX_PER_CELL, cols * PX_PER_CELL)
    if raw.shape[0] >= expected_shape[0] and raw.shape[1] >= expected_shape[1]:
        trimmed = raw[:expected_shape[0], :expected_shape[1]]
    else:
        trimmed = raw
    blocks = trimmed.reshape(rows, PX_PER_CELL, cols, PX_PER_CELL).transpose(0, 2, 1, 3)
    blocks = blocks.reshape(rows, cols, -1).astype(np.float64)
    blocks[~np.isfinite(blocks)] = np.nan
    with np.errstate(invalid="ignore"):
        wind = np.nanmean(blocks, axis=2)

    def wind_stats(mask):
        vals = wind[mask]
        vals = vals[~np.isnan(vals)]
        if vals.size == 0:
            return {"n": 0, "mean": 0, "p90": 0, "max": 0}
        return {"n": int(vals.size), "mean": float(vals.mean()),
                "p90": float(np.percentile(vals, 90)), "max": float(vals.max())}

    s_land = wind_stats(both)
    s_ne_only = wind_stats(ne_only)
    s_ocean = wind_stats(neither)

    ne_only_vals = wind[ne_only]
    ne_only_vals = ne_only_vals[~np.isnan(ne_only_vals)]
    land_p90 = s_land["p90"]
    ne_only_hot = int((ne_only_vals > land_p90).sum()) if ne_only_vals.size else 0

    out = io.StringIO()
    out.write("# Land-mask assessment: Natural Earth 1:50m vs ABS ASGS boundary\n\n")
    out.write(banner("validate"))
    out.write(f"\nGrid: {rows} x {cols} cells of {CELL_DEG} deg over strip {STRIP_BBOX}.\n\n")
    out.write("## Cell classification\n\n")
    out.write("| Class | Cells | Share |\n|---|---|---|\n")
    total = rows * cols
    for label, mask in [("Land (both)", both), ("NE-only", ne_only),
                        ("ABS-only", abs_only), ("Ocean (both)", neither)]:
        out.write(f"| {label} | {int(mask.sum())} | {100.0 * mask.sum() / total:.2f}% |\n")
    out.write(f"\n## Leakage\n\n"
              f"- NE-only cells: **{int(ne_only.sum())}**\n"
              f"- Of those exceeding land P90 ({land_p90:.2f} m/s): **{ne_only_hot}**\n"
              f"- Ocean mean wind: {s_ocean['mean']:.2f} m/s vs land: {s_land['mean']:.2f} m/s\n"
              f"- A land mask is mandatory.\n")

    report_path = geo_config.GEO_META_DIR / "landmask_assessment.md"
    atomic_write_text(report_path, out.getvalue())
    return report_path


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def run(
    verbose: bool = False,
    skip_land_sea: bool = False,
    max_slope: float = DEFAULT_MAX_SLOPE_DEG,
) -> dict:
    """
    Run cross-domain integration validation.

    Parameters
    ----------
    verbose : bool
        Enable detailed logging.
    skip_land_sea : bool
        Skip the land-mask assessment (requires network access).
    max_slope : float
        Maximum allowable slope in degrees for wind farm siting checks.
        Default: 15.0 degrees.

    Returns a summary dict with output paths and check results.
    """
    results: dict[str, object] = {}

    print("  [1/2] Cross-domain wind farm checks (land, CAPAD, slope)...")
    checks = _run_cross_domain_checks(verbose, max_slope=max_slope)
    passed = sum(1 for c in checks if c["passed"])
    print(f"    {passed}/{len(checks)} checks passed")
    results["cross_domain_checks"] = checks

    scoring_checks = _run_scoring_cross_checks(verbose)
    if scoring_checks:
        scoring_passed = sum(1 for c in scoring_checks if c["passed"])
        print(f"    Scoring (S1-10) cross-checks: "
              f"{scoring_passed}/{len(scoring_checks)} passed")
    results["scoring_cross_checks"] = scoring_checks

    shortlist_checks = _run_shortlist_cross_checks(verbose)
    if shortlist_checks:
        shortlist_passed = sum(1 for c in shortlist_checks if c["passed"])
        print(f"    Shortlist (S1-11) cross-checks: "
              f"{shortlist_passed}/{len(shortlist_checks)} passed")
    results["shortlist_cross_checks"] = shortlist_checks

    if not skip_land_sea:
        print("  [2/2] Land-mask assessment...")
        results["landmask"] = _run_landmask_assessment(verbose)
        print(f"    → {results['landmask'].relative_to(config.PROJECT_ROOT)}")
    else:
        print("  [2/2] Land-mask assessment... [skipped]")
        results["landmask"] = None

    return results
