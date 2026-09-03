"""
Timestamped / versioned output filenames for the S1-11 shortlist stage
(Requirement 7).

A single UTC Run_Timestamp is derived ONCE per run (``run_timestamp``) and
reused across BOTH output filenames and every metadata artefact
(Requirement 7.2). ``resolve_output_paths`` turns that one timestamp into the
concrete ``sprint1_shortlist_<UTCdate>.csv`` / ``.geojson`` paths
(Requirement 7.1), applies the project region slug ``nsw`` via the shared
``OUTPUT_PREFIX`` (Requirement 7.3), and — rather than silently overwriting an
existing run — appends a finer-grained UTC time component by a documented,
deterministic rule and surfaces the collision so the Summary_Report can record
it (Requirement 7.4).

Design reference: design.md §9 "Timestamped filenames".

Naming convention
-----------------
The shortlist output name is a project-convention filename whose stem is the
shared ``OUTPUT_PREFIX`` (``sprint1_shortlist``) — this already carries the
``{source=sprint1}_{dataset=shortlist}`` head and, by construction, the
``{region=nsw}`` slug — followed by the UTC date the run executed:

    sprint1_shortlist_<UTCdate>.csv
    sprint1_shortlist_<UTCdate>.geojson

where ``<UTCdate>`` is the ``YYYYMMDD`` UTC date parsed from the single
Run_Timestamp (Requirement 7.1, 7.2). The extension distinguishes the two
exports; both share the same stem so a reviewer sees at a glance that the CSV
and the GeoJSON belong to the same run (paired with the CSV/GeoJSON
same-``cell_id``-set-and-order guarantee of Requirement 5.5).

Collision rule (Requirement 7.4)
--------------------------------
Two runs on the same UTC day would otherwise resolve to the identical
``sprint1_shortlist_<YYYYMMDD>`` stem. Silently overwriting the earlier run is
forbidden, so the rule is deterministic and derived from the SAME Run_Timestamp
(never from a second wall-clock read, which would break the "one timestamp for
the run" contract):

    1. Base stem      ``sprint1_shortlist_<YYYYMMDD>``.
       Used when neither the ``.csv`` nor the ``.geojson`` already exists.
    2. Second-precise  ``sprint1_shortlist_<YYYYMMDD>T<HHMMSS>``.
       Used when the base stem collides — the finer-grained UTC *time* of the
       same Run_Timestamp is appended.
    3. Microsecond-precise ``sprint1_shortlist_<YYYYMMDD>T<HHMMSS>f<micro>``.
       Used only in the (pathological) case where the second-precise stem also
       already exists.

A stem "collides" if EITHER the ``.csv`` OR the ``.geojson`` for that stem is
already present, so the CSV and GeoJSON always stay paired under a single stem.
``resolve_output_paths`` returns a :class:`ResolvedPaths` triple whose
``collision`` field records whether the finer-grained rule had to be applied,
which stem was chosen, and the collided base name, for the Summary_Report.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

from ..common.geo import utc_now
from . import config


def run_timestamp() -> str:
    """
    The single UTC Run_Timestamp for a shortlist run, derived ONCE via
    ``common.geo.utc_now()`` (Requirement 7.2).

    Returns the ISO-8601 UTC string (seconds precision, ``+00:00`` offset),
    identical to the value written into every metadata artefact so the
    filenames and the metadata agree for the run. Call this exactly once in
    ``run()`` and thread the returned value everywhere the Run_Timestamp is
    needed — never call it a second time, which would produce two timestamps
    for one run.
    """
    return utc_now()


class CollisionOutcome(NamedTuple):
    """
    Collision outcome surfaced for the Summary_Report (Requirement 7.4).

    ``occurred``      True when the base ``<UTCdate>`` stem already existed and
                      the finer-grained rule was applied.
    ``base_stem``     The base ``sprint1_shortlist_<UTCdate>`` stem that was
                      probed first.
    ``resolved_stem`` The stem actually used for the written files (equal to
                      ``base_stem`` when no collision occurred).
    ``precision``     The precision tier applied: ``"date"`` (no collision),
                      ``"second"``, or ``"microsecond"``.
    """

    occurred: bool
    base_stem: str
    resolved_stem: str
    precision: str


class ResolvedPaths(NamedTuple):
    """
    Resolved output paths plus the collision outcome.

    The first two fields (``csv``, ``geojson``) preserve the design's
    documented ``tuple[Path, Path]`` shape for positional unpacking; the third
    (``collision``) surfaces the Requirement 7.4 outcome for the
    Summary_Report. Callers that only want the paths can still write
    ``csv, geojson, _ = resolve_output_paths(...)``.
    """

    csv: Path
    geojson: Path
    collision: CollisionOutcome


def _parse_utc(ts: str) -> datetime:
    """
    Parse the ISO-8601 Run_Timestamp back into an aware UTC ``datetime``.

    ``utc_now()`` emits ``...+00:00``; ``fromisoformat`` handles that offset on
    supported runtimes. A trailing ``Z`` is normalised defensively. The result
    is coerced to UTC so the date/time components extracted for the filename
    are unambiguously UTC (Requirement 7.2 — "derive the Run_Timestamp in
    UTC").
    """
    normalised = ts.strip()
    if normalised.endswith("Z"):
        normalised = normalised[:-1] + "+00:00"
    parsed = datetime.fromisoformat(normalised)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _stem_exists(out_dir: Path, stem: str) -> bool:
    """
    A stem "collides" if EITHER the ``.csv`` OR the ``.geojson`` for it is
    already present, so the CSV and GeoJSON stay paired under one stem.
    """
    return (out_dir / f"{stem}.csv").exists() or (out_dir / f"{stem}.geojson").exists()


def resolve_output_paths(out_dir: Path, ts: str) -> ResolvedPaths:
    """
    Resolve the timestamped Shortlist_CSV and Shortlist_GeoJSON paths from the
    single Run_Timestamp ``ts`` (Requirement 7.1, 7.2, 7.3, 7.4).

    Parameters
    ----------
    out_dir:
        The shortlist output directory (``config.SHORTLIST_DIR``).
    ts:
        The single UTC Run_Timestamp from :func:`run_timestamp`. The SAME value
        is threaded into the metadata, so filenames and metadata agree
        (Requirement 7.2).

    Returns
    -------
    ResolvedPaths
        ``(csv, geojson, collision)``. The stem is
        ``sprint1_shortlist_<UTCdate>`` (``config.OUTPUT_PREFIX`` +
        ``_<YYYYMMDD>``), which already carries the ``nsw`` region slug via the
        shared prefix (Requirement 7.3). On a collision the finer-grained rule
        documented in this module's docstring is applied and ``collision``
        records the outcome for the Summary_Report (Requirement 7.4).
    """
    parsed = _parse_utc(ts)
    prefix = config.OUTPUT_PREFIX

    date_component = parsed.strftime("%Y%m%d")
    base_stem = f"{prefix}_{date_component}"

    # Tier 1 — base date stem (the common, no-collision case).
    if not _stem_exists(out_dir, base_stem):
        collision = CollisionOutcome(
            occurred=False,
            base_stem=base_stem,
            resolved_stem=base_stem,
            precision="date",
        )
        return ResolvedPaths(
            csv=out_dir / f"{base_stem}.csv",
            geojson=out_dir / f"{base_stem}.geojson",
            collision=collision,
        )

    # Tier 2 — append the second-precise UTC time of the SAME Run_Timestamp.
    second_stem = f"{prefix}_{date_component}T{parsed.strftime('%H%M%S')}"
    if not _stem_exists(out_dir, second_stem):
        resolved_stem = second_stem
        precision = "second"
    else:
        # Tier 3 — append microseconds of the same Run_Timestamp.
        resolved_stem = f"{second_stem}f{parsed.microsecond:06d}"
        precision = "microsecond"

    collision = CollisionOutcome(
        occurred=True,
        base_stem=base_stem,
        resolved_stem=resolved_stem,
        precision=precision,
    )
    return ResolvedPaths(
        csv=out_dir / f"{resolved_stem}.csv",
        geojson=out_dir / f"{resolved_stem}.geojson",
        collision=collision,
    )
