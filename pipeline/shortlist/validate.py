"""
Shortlist validation (S1-11, Requirement 12) — no silent passes.

Every check records what it EXPECTED, what it OBSERVED and an explicit
pass/fail, and every check is written to the validation report whether it
passed or not. A check that only speaks up when it fails is a check nobody
can audit; the pipeline's rule is that the evidence is always on the page.
This mirrors `pipeline/scoring/validate.py`, which plays the identical role
for the scoring stage — the `_check` record shape and `summarise_checks`
tallies are deliberately identical so the two reports read the same.

TIERING. This module holds the shortlist's OWN invariants — the ones that can
be checked from the shortlist artefacts alone (the assembled frame, the two
written outputs and the metadata sidecar): row-count vs Top_N, eligible-only,
ascending-`rank` ordering, non-null coordinates, CSV/GeoJSON equality, the
schema, the disclaimer/resolution presence, and the metadata/provenance
records. The CROSS-domain checks that compare the shortlist against the
Scored_Table and the Analysis_Grid (subset of their `cell_id` sets, scores /
ranks unchanged, coordinates equal to the grid) live in the cross-domain
`pipeline/validate.py` tier per the pipeline's validation-tier convention
(Requirement 12.7).

FATAL only. As in the scoring stage, there are no WARN-tier checks here: a
shortlist that fails any check below is simply wrong. The caller (`run()`)
writes the report FIRST, then decides whether to halt, so a failed run still
leaves the evidence behind.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ..common.geo import banner
from . import config

FATAL = "fatal"

# Column shorthands drawn from the documented schema so a rename in config
# propagates here rather than drifting (holistic consistency).
_RANK = config.SHORTLIST_COLUMNS[0]  # "rank"
_CELL_ID = config.SHORTLIST_COLUMNS[1]  # "cell_id"
_SCORE = config.SHORTLIST_COLUMNS[2]  # "suitability_score"
_LAT = config.SHORTLIST_COLUMNS[4]  # "centroid_lat"
_LON = config.SHORTLIST_COLUMNS[5]  # "centroid_lon"


def _check(checks: list[dict], name: str, expected, observed, passed: bool) -> None:
    """Append one audit record — same shape as `scoring.validate._check`."""
    checks.append(
        {
            "name": name,
            "expected": str(expected),
            "observed": str(observed),
            "passed": bool(passed),
            "severity": FATAL,
        }
    )


def _read_csv_cell_ids(csv_path: Path) -> list:
    """
    The ordered `cell_id` sequence written to the Shortlist_CSV.

    Read as text and parsed shallowly (the CSV is at most Top_N rows) so the
    check compares exactly what landed on disk, not the in-memory frame. Values
    are kept as strings for the element-for-element comparison with the GeoJSON,
    so an integer `cell_id` and its string form compare equal regardless of the
    two writers' dtype handling.
    """
    import csv as _csv

    with csv_path.open(encoding="utf-8", newline="") as fh:
        reader = _csv.DictReader(fh)
        if reader.fieldnames is None or _CELL_ID not in reader.fieldnames:
            return []
        return [row[_CELL_ID] for row in reader]


def _read_geojson(geojson_path: Path) -> dict:
    """Parse the Shortlist_GeoJSON FeatureCollection written to disk."""
    return json.loads(geojson_path.read_text(encoding="utf-8"))


def _geojson_cell_ids(collection: dict) -> list:
    """The ordered `cell_id` sequence carried as GeoJSON feature properties."""
    return [
        str(feature.get("properties", {}).get(_CELL_ID))
        for feature in collection.get("features", [])
    ]


def validate(
    shortlist: pd.DataFrame,
    *,
    effective_top_n: int,
    csv_path: Path | str,
    geojson_path: Path | str,
    metadata_sidecar_path: Path | str,
) -> dict:
    """
    Check the written shortlist artefacts against the shortlist's own
    invariants (Requirement 12.1–12.6), plus the schema, metadata and
    provenance guarantees the shortlist alone can verify.

    Parameters
    ----------
    shortlist:
        The assembled in-memory Shortlist frame (documented
        ``config.SHORTLIST_COLUMNS`` in order) that was written out — the
        source of truth for the row-count, eligibility, ordering, coordinate
        and schema checks.
    effective_top_n:
        The resolved effective Top_N for the run (Requirement 12.1).
    csv_path, geojson_path:
        The two written outputs, re-read from disk so the CSV/GeoJSON equality
        (12.5) and disclaimer/resolution presence (12.6) checks assert what
        actually landed on disk rather than the in-memory frame.
    metadata_sidecar_path:
        The JSON metadata sidecar, checked for the disclaimer + resolution
        (12.6) and the pipeline_version / run_timestamp / scored_table_id
        records (9.x).

    Returns a summary dict ``{"checks": [...], "passed": n, "failed": n,
    "total": n, "failed_names": [...]}`` — the same shape as
    ``scoring.validate.validate`` and ``integration.merge`` — so a caller can
    render it with the shared report writer. This function never raises on a
    data fault, so the report can always be written first.
    """
    checks: list[dict] = []
    csv_path = Path(csv_path)
    geojson_path = Path(geojson_path)
    metadata_sidecar_path = Path(metadata_sidecar_path)

    n_rows = int(len(shortlist))

    # --- 12.1 row count <= effective Top_N ---
    _check(checks, "Shortlist row count within the effective Top_N",
           f"<= {effective_top_n} rows", f"{n_rows:,} rows",
           n_rows <= effective_top_n)

    # --- schema (4.1): the documented SHORTLIST_COLUMNS present, in order ---
    core = list(config.SHORTLIST_COLUMNS)
    observed_core = [c for c in shortlist.columns if c in core]
    schema_ok = observed_core == core
    missing_cols = [c for c in core if c not in shortlist.columns]
    _check(checks, "Shortlist carries the documented SHORTLIST_COLUMNS in order",
           f"{core}",
           (f"missing {missing_cols}" if missing_cols
            else f"present, order {'matches' if schema_ok else 'DIFFERS'}"),
           schema_ok)

    # The remaining frame checks need the core columns; guard so a broken schema
    # yields reported FAILs rather than a KeyError (a validator that crashes
    # tells you less than one that fails).
    have_score = _SCORE in shortlist.columns
    have_rank = _RANK in shortlist.columns
    have_coords = _LAT in shortlist.columns and _LON in shortlist.columns

    # --- 12.2 every shortlisted cell is an Eligible_Cell ---
    if have_score and have_rank:
        ineligible = int(
            (shortlist[_SCORE].isna() | shortlist[_RANK].isna()).sum()
        )
    else:
        ineligible = n_rows
    _check(checks, "Every shortlisted cell is an Eligible_Cell "
           "(non-null suitability_score AND rank)",
           "0 ineligible cells", f"{ineligible:,} ineligible cells",
           ineligible == 0)

    # --- 12.3 ordering is ascending rank ---
    if have_rank and n_rows:
        ranks = shortlist[_RANK]
        # Count adjacent pairs that decrease (or are non-monotonic). A stable
        # ascending order has zero such violations.
        diffs = ranks.to_numpy()
        violations = int((diffs[1:] < diffs[:-1]).sum())
    else:
        violations = 0
    _check(checks, "Shortlist ordered by ascending rank (consistent with S1-10)",
           "0 ordering violations", f"{violations:,} ordering violations",
           violations == 0)

    # --- 12.4 every shortlisted cell has non-null coordinates ---
    if have_coords:
        missing_coords = int(
            (shortlist[_LAT].isna() | shortlist[_LON].isna()).sum()
        )
    else:
        missing_coords = n_rows
    _check(checks, "Every shortlisted cell has non-null centroid_lat/centroid_lon",
           "0 missing coordinates", f"{missing_coords:,} missing coordinates",
           missing_coords == 0)

    # --- 12.5 CSV and GeoJSON carry the same cell_id set in the same order ---
    if csv_path.exists() and geojson_path.exists():
        try:
            collection = _read_geojson(geojson_path)
            csv_ids = _read_csv_cell_ids(csv_path)
            geojson_ids = _geojson_cell_ids(collection)
            same_order = csv_ids == geojson_ids
            same_set = set(csv_ids) == set(geojson_ids)
            observed = (
                f"CSV {len(csv_ids):,} ids, GeoJSON {len(geojson_ids):,} ids; "
                f"{'same order' if same_order else 'ORDER/SET differs'}"
            )
        except Exception as exc:  # noqa: BLE001 — an unreadable output is a FAIL
            same_order = same_set = False
            observed = f"could not compare outputs: {exc}"
    else:
        collection = {}
        same_order = same_set = False
        observed = "one or both outputs missing on disk"
    _check(checks, "Shortlist_CSV and Shortlist_GeoJSON share the same cell_id "
           "set in the same order",
           "identical ordered cell_id sequences",
           observed, same_order and same_set)

    # --- 12.6 every output + metadata carries disclaimer AND resolution ---
    disclaimer = config.PRELIMINARY_DISCLAIMER
    resolution = config.ANALYSIS_RESOLUTION

    # GeoJSON: file-level foreign members (8.3).
    gj_ok = (
        collection.get("preliminary_disclaimer") == disclaimer
        and collection.get("analysis_resolution") == resolution
    )
    # Metadata sidecar: carries the CSV's disclaimer (8.4) + pipeline_version /
    # run_timestamp / scored_table_id (9.x).
    sidecar: dict = {}
    if metadata_sidecar_path.exists():
        try:
            sidecar = json.loads(metadata_sidecar_path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 — a corrupt sidecar is a reported FAIL
            sidecar = {}
    sidecar_ok = (
        sidecar.get("preliminary_disclaimer") == disclaimer
        and sidecar.get("analysis_resolution") == resolution
    )
    _check(checks, "Each output and its metadata carry the Preliminary_Disclaimer "
           "and the Analysis_Resolution statement",
           "disclaimer + resolution in the GeoJSON foreign members and the "
           "metadata sidecar",
           f"GeoJSON {'OK' if gj_ok else 'MISSING'}, "
           f"sidecar {'OK' if sidecar_ok else 'MISSING'}",
           gj_ok and sidecar_ok)

    # --- 9.x the metadata sidecar records the reproducibility fields ---
    scored_id = sidecar.get("scored_table_id") or {}
    has_version = bool(sidecar.get("pipeline_version"))
    has_ts = bool(sidecar.get("run_timestamp"))
    has_scored_id = bool(scored_id.get("path")) and bool(scored_id.get("sha256"))
    _check(checks, "Metadata sidecar records pipeline_version, run_timestamp and "
           "scored_table_id (path + sha256)",
           "all three present",
           f"pipeline_version {'set' if has_version else 'MISSING'}, "
           f"run_timestamp {'set' if has_ts else 'MISSING'}, "
           f"scored_table_id {'set' if has_scored_id else 'MISSING'}",
           has_version and has_ts and has_scored_id)

    return summarise_checks(checks)


def summarise_checks(checks: list[dict]) -> dict:
    """Pass/fail tallies over a check list (same shape as scoring.validate)."""
    failed = [c for c in checks if not c["passed"]]
    return {
        "checks": checks,
        "total": len(checks),
        "passed": len(checks) - len(failed),
        "failed": len(failed),
        "failed_names": [c["name"] for c in failed],
    }


def build_validation_report(result: dict, run_timestamp: str, pipeline_version: str) -> str:
    """
    Render every validation check — passed and failed — as markdown, banner
    stamped (Requirement 11.4). Mirrors `scoring.report.build_validation_report`
    so the two stages' validation reports read identically.
    """
    lines: list[str] = []
    add = lines.append
    add("# Preliminary Ranked Shortlist — Validation (S1-11)\n")
    add(banner(config.MODULE_NAME))
    add("")
    add(f"{result['passed']}/{result['total']} checks passed "
        f"({result['failed']} failures). Every check is listed whether it passed "
        f"or not — no silent passes.\n")
    add("| Check | Expected | Observed | Result |")
    add("|-------|----------|----------|--------|")
    for check in result["checks"]:
        status = "PASS" if check["passed"] else "**FAIL**"
        add(f"| {check['name']} | {check['expected']} | {check['observed']} | {status} |")
    add("")
    add(f"*Generated {run_timestamp}; pipeline version `{pipeline_version}`.*")
    return "\n".join(lines) + "\n"
