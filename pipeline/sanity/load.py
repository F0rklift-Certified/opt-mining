"""
Input resolver and loader for the S1-12 sanity-check stage (Requirements 1, 8).

This is the ONLY file-reading path in the sanity stage. It resolves the latest
timestamped Shortlist under ``DATA/shortlist/`` by a documented deterministic
rule, reads the five Sprint 1 outputs (Scored_Table, Shortlist,
Integrated_Feature_Table, Wind_Generators, Analysis_Grid) READ-ONLY, and hands
fully in-memory frames to the pure checks (``checks.py``). Because the pure
checks receive frames rather than paths, they are independently testable and
never touch disk.

Every check here halts BEFORE the stage writes anything, and every error names
the offending path, column, or source (Requirements 1.4, 1.5, 2.2, 3.5). The
stage NEVER re-derives, renumbers, reformats, or reorders ``cell_id`` (1.2) and
NEVER re-scores or re-ranks (1.3): ``cell_id``, ``suitability_score``, and
``rank`` are reused exactly as S1-10/S1-11 wrote them. Every input is opened in
read-only mode, so no input is ever mutated (8.1).

This module mirrors the fail-fast, path-naming discipline of
``pipeline/scoring/load.py`` and ``pipeline/shortlist/load.py`` and the
explicit-CRS discipline of ``pipeline/shortlist/coords.py``
(``pyogrio.read_info`` + ``pyproj.CRS`` before reading geometry, refusing to
assume an unstated CRS).

Design reference: design.md §2 "Input resolver & loader".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio
from pyproj import CRS

from . import config


# ---------------------------------------------------------------------------
# Input path bundle and loaded-frame result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SanityInputs:
    """
    The resolved default paths for a sanity run.

    Every field defaults to the corresponding ``config`` constant, so a caller
    (``run()``) can override any single path (e.g. ``--wind-generators``)
    without re-typing the rest. ``shortlist_path`` is the concrete timestamped
    file chosen by :func:`resolve_shortlist`; it has no config default because
    it is resolved at runtime from ``shortlist_dir`` (Requirement 1.6).
    """

    scored_path: Path = config.SCORED_PATH
    shortlist_path: Path | None = None
    integrated_path: Path = config.INTEGRATED_PATH
    wind_generators_path: Path = config.WIND_GENERATORS_PATH
    grid_path: Path = config.GRID_PATH


@dataclass(frozen=True)
class LoadedFrames:
    """
    The fully in-memory frames the pure checks operate on (Requirement 1.1).

    ``scored`` carries every scored cell (eligible AND excluded), reused
    byte-for-byte from S1-10 (1.2, 1.3). ``eligible`` / ``excluded`` are the two
    disjoint views of ``scored`` — an Eligible_Cell has BOTH a non-null
    ``suitability_score`` and a non-null ``rank``; everything else is an
    Excluded_Cell (null score/rank, or offshore/absent). Percentile, quartile,
    and distribution statistics are computed over ``eligible`` ONLY (2.4, 5.1).

    ``resolved_shortlist_path`` is the concrete timestamped Shortlist file used,
    recorded for the report metadata (1.6).
    """

    scored: gpd.GeoDataFrame
    shortlist: pd.DataFrame
    integrated: gpd.GeoDataFrame
    wind_generators: gpd.GeoDataFrame
    grid: gpd.GeoDataFrame
    eligible: gpd.GeoDataFrame
    excluded: gpd.GeoDataFrame
    resolved_shortlist_path: Path


# ---------------------------------------------------------------------------
# Shortlist resolution (Requirement 1.6, 1.4)
# ---------------------------------------------------------------------------

# The S1-11 shortlist stage names its outputs
# ``sprint1_shortlist_<YYYYMMDD>[T<HHMMSS>[f<micro>]].{csv,geojson}`` from a
# single UTC Run_Timestamp (see ``pipeline/shortlist/naming.py``). This pattern
# parses that stem back into an orderable UTC datetime so the MOST RECENT run is
# selected deterministically. The date component is required; the time and
# microsecond components are optional and default to the start of the UTC day,
# matching the naming module's tiered collision rule.
_SHORTLIST_STEM_RE = re.compile(
    r"^"
    + re.escape(config.SHORTLIST_OUTPUT_PREFIX)
    + r"_(?P<date>\d{8})"
    + r"(?:T(?P<time>\d{6}))?"
    + r"(?:f(?P<micro>\d{6}))?"
    + r"$"
)

# The Shortlist is exported as both CSV and GeoJSON under the same stem; the
# GeoJSON carries geometry, so resolve to it when both are present. A run that
# emitted only the CSV still resolves (to the CSV).
_SHORTLIST_EXTENSIONS = (".geojson", ".csv")


def _parse_shortlist_timestamp(stem: str) -> datetime | None:
    """
    Parse a Shortlist filename stem into an orderable aware UTC ``datetime``.

    Returns ``None`` for a stem that does not match the documented
    ``sprint1_shortlist_<UTCdate>...`` convention, so a stray file in the
    directory is ignored rather than mis-ranked. A stem with only the date
    component is anchored to 00:00:00 UTC; the optional ``T<HHMMSS>`` and
    ``f<micro>`` components refine it, exactly as ``shortlist/naming.py``
    produced them.
    """
    match = _SHORTLIST_STEM_RE.match(stem)
    if match is None:
        return None

    date_part = match.group("date")
    time_part = match.group("time") or "000000"
    micro_part = match.group("micro") or "000000"

    try:
        parsed = datetime.strptime(date_part + time_part, "%Y%m%d%H%M%S")
    except ValueError:
        return None
    return parsed.replace(microsecond=int(micro_part), tzinfo=timezone.utc)


def resolve_shortlist(shortlist_dir: Path | str | None = None) -> Path:
    """
    Resolve the Shortlist input by a documented, deterministic rule: the file
    with the most recent UTC Run_Timestamp in its name under ``DATA/shortlist/``
    (Requirement 1.6).

    The S1-11 stage encodes the single UTC Run_Timestamp into every Shortlist
    filename (``sprint1_shortlist_<YYYYMMDD>[T<HHMMSS>[f<micro>]]``), so parsing
    that timestamp and taking the maximum selects the latest run without a
    second wall-clock read and without depending on filesystem mtimes. Ties on
    the parsed timestamp (a CSV/GeoJSON pair share a stem) are broken by
    preferring the GeoJSON (it carries geometry) and then by filename, so the
    result is fully deterministic. The resolved path is returned for the caller
    to record in the report metadata (1.6).

    Halts (raises) BEFORE any output when no Shortlist is present (1.4):
      - ``FileNotFoundError`` if ``shortlist_dir`` does not exist or is not a
        directory, naming the path;
      - ``FileNotFoundError`` if the directory contains no file matching the
        documented ``sprint1_shortlist_<UTCdate>...`` naming convention.
    """
    shortlist_dir = (
        Path(shortlist_dir) if shortlist_dir is not None else config.SHORTLIST_DIR
    )
    if not shortlist_dir.is_dir():
        raise FileNotFoundError(
            f"Shortlist directory not found: {shortlist_dir}. Run "
            f"`python -m pipeline --only shortlist` to generate a Shortlist "
            f"before the sanity stage."
        )

    # Rank every matching file by (parsed UTC timestamp, extension preference,
    # name). Extension preference favours .geojson over .csv so a run's geometry
    # export wins when both share a stem.
    candidates: list[tuple[datetime, int, str, Path]] = []
    for path in shortlist_dir.iterdir():
        if not path.is_file() or path.suffix.lower() not in _SHORTLIST_EXTENSIONS:
            continue
        timestamp = _parse_shortlist_timestamp(path.stem)
        if timestamp is None:
            continue
        # Lower index = higher preference; negate so a larger tuple wins in max.
        ext_rank = _SHORTLIST_EXTENSIONS.index(path.suffix.lower())
        candidates.append((timestamp, -ext_rank, path.name, path))

    if not candidates:
        raise FileNotFoundError(
            f"No Shortlist file found under {shortlist_dir} matching the "
            f"'{config.SHORTLIST_OUTPUT_PREFIX}_<UTCdate>[T<HHMMSS>][f<micro>]"
            f".{{csv,geojson}}' naming convention. Run "
            f"`python -m pipeline --only shortlist` to generate one before the "
            f"sanity stage."
        )

    # Most recent timestamp, then geometry-carrying extension, then name.
    _, _, _, resolved = max(candidates, key=lambda item: (item[0], item[1], item[2]))
    return resolved


# ---------------------------------------------------------------------------
# CRS resolution helper (Requirements 2.2, 3.5)
# ---------------------------------------------------------------------------


def _crs_string(crs) -> str:
    """Normalise a CRS to 'AUTHORITY:CODE' where possible (else its WKT)."""
    parsed = CRS.from_user_input(crs)
    authority = parsed.to_authority()
    if authority:
        return f"{authority[0]}:{authority[1]}"
    return parsed.to_wkt()


def _require_resolvable_crs(path: Path, layer: str | None, source_name: str) -> str:
    """
    Read a vector source's DECLARED CRS before reading geometry and refuse to
    proceed if it is absent (Requirements 2.2, 3.5).

    A source with no resolvable CRS is a fatal error: the stage halts before any
    write rather than assuming a projection. Mirrors the explicit-CRS discipline
    of ``shortlist/coords.load_grid``. Returns the normalised CRS string for the
    report's transform log.
    """
    try:
        declared = pyogrio.read_info(path, layer=layer).get("crs")
    except Exception as exc:  # noqa: BLE001 — any read failure is fatal and named
        raise RuntimeError(f"Could not read {source_name} {path}: {exc}") from exc

    if not declared:
        raise ValueError(
            f"{source_name} {path} has no resolvable CRS; the sanity stage never "
            f"assumes a projection and performs every containment operation in "
            f"one explicit CRS ({config.CONTAINMENT_CRS}). Regenerate the source "
            f"with an explicit CRS."
        )
    return _crs_string(declared)


# ---------------------------------------------------------------------------
# Vector readers (READ-ONLY, fail-fast, path/column/CRS-naming)
# ---------------------------------------------------------------------------


def _read_vector(
    path: Path,
    *,
    layer: str | None,
    source_name: str,
    required_columns: tuple[str, ...],
    require_crs: bool,
) -> gpd.GeoDataFrame:
    """
    Read a vector source READ-ONLY and validate it, halting BEFORE any output.

    Halts on:
      - a missing file, naming the path (1.4);
      - an unreadable file, naming the path (1.4);
      - any ``required_columns`` entry absent, naming the column AND the input
        it was expected in (1.5);
      - a source with no resolvable CRS when ``require_crs`` is set, naming the
        source and never assuming a projection (2.2, 3.5).

    ``cell_id`` (and every other column) is returned verbatim — never
    re-derived, renumbered, reformatted, or reordered (1.2). The frame is read
    into memory and returned whole; the file itself is never modified (8.1).
    """
    if not path.exists():
        raise FileNotFoundError(
            f"{source_name} not found: {path}. The sanity stage consumes the "
            f"Sprint 1 outputs read-only; generate this input before running "
            f"the sanity stage."
        )

    if require_crs:
        # Refuse an unresolvable CRS before touching geometry (2.2, 3.5).
        _require_resolvable_crs(path, layer, source_name)

    try:
        frame = gpd.read_file(path, layer=layer)
    except Exception as exc:  # noqa: BLE001 — any read failure is fatal and named
        raise RuntimeError(f"Could not read {source_name} {path}: {exc}") from exc

    missing = [c for c in required_columns if c not in frame.columns]
    if missing:
        raise ValueError(
            f"{source_name} {path} lacks required column(s) {missing} expected "
            f"by the sanity stage. The stage reads {list(required_columns)} from "
            f"this input and re-derives none of them; regenerate the input if a "
            f"column is missing."
        )

    return frame


def _read_shortlist(path: Path) -> pd.DataFrame:
    """
    Read the resolved Shortlist READ-ONLY (Requirement 1.1, 1.4).

    The Shortlist is the S1-11 export selected by :func:`resolve_shortlist`;
    it is read as-is (GeoJSON via GeoPandas, CSV via pandas) and used for the
    known-wind-farm comparison and geographic-diversity context. Halts on a
    missing or unreadable file, naming the path (1.4). ``suitability_score`` and
    ``rank`` are carried through untouched — never re-scored or re-ranked (1.3).
    """
    if not path.exists():
        raise FileNotFoundError(
            f"Shortlist not found: {path}. The resolved Shortlist path must "
            f"exist for the sanity stage to read it read-only."
        )
    try:
        if path.suffix.lower() == ".csv":
            return pd.read_csv(path)
        return gpd.read_file(path)
    except Exception as exc:  # noqa: BLE001 — any read failure is fatal and named
        raise RuntimeError(f"Could not read Shortlist {path}: {exc}") from exc


# ---------------------------------------------------------------------------
# Eligible / excluded split (Requirement 2.4, 5.1)
# ---------------------------------------------------------------------------


def split_eligible(scored: gpd.GeoDataFrame) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """
    Split the Scored_Table into Eligible_Cells and Excluded_Cells.

    An Eligible_Cell has a non-null ``suitability_score`` AND a non-null
    ``rank`` (both produced by S1-10); every other scored cell — a null score,
    a null rank, or both — is an Excluded_Cell. Percentile, quartile, and
    distribution statistics are computed over the eligible view ONLY, so
    excluded/ineligible cells never dilute the rank or the distribution
    (Requirements 2.4, 5.1).

    PURE: returns two new views over ``scored`` without mutating it. ``cell_id``
    and every score/rank value are carried through unchanged (1.2, 1.3).
    """
    score_col = config.REQUIRED_SCORE_COLUMNS[1]  # "suitability_score"
    rank_col = config.REQUIRED_SCORE_COLUMNS[2]  # "rank"

    eligible_mask = scored[score_col].notna() & scored[rank_col].notna()
    eligible = scored.loc[eligible_mask].copy()
    excluded = scored.loc[~eligible_mask].copy()
    return eligible, excluded


# ---------------------------------------------------------------------------
# Top-level loader (Requirement 1.1, 8.1)
# ---------------------------------------------------------------------------


def load_inputs(paths: SanityInputs | None = None) -> LoadedFrames:
    """
    Read all five stage inputs READ-ONLY and return in-memory frames (1.1, 8.1).

    Inputs (each opened read-only; none is ever mutated — 8.1):
      - Scored_Table (S1-10) — ``cell_id`` / ``suitability_score`` / ``rank``
        reused byte-for-byte, never re-scored or re-ranked (1.2, 1.3);
      - the resolved Shortlist (S1-11) — pre-resolved on ``paths`` or resolved
        here from ``SHORTLIST_DIR`` by the documented latest-timestamp rule
        (1.6);
      - Integrated_Feature_Table (S1-08) — the per-cell feature values the
        spot-checks read;
      - Wind_Generators (GA) — the known wind farms Check 1 locates;
      - Analysis_Grid (S1-02) — the cell polygons and centroids.

    Halts BEFORE any output on (each naming the offending path/column/source):
      - any missing or unreadable input (1.4);
      - any required column absent, naming the column and the input it was
        expected in (1.5);
      - any spatial source (grid or wind generators) with no resolvable CRS,
        naming the source and never assuming a projection (2.2, 3.5).

    The loaded Scored_Table is split into Eligible_Cells and Excluded_Cells
    (:func:`split_eligible`) so the pure checks operate on the eligible
    population only where required (2.4, 5.1).
    """
    paths = paths if paths is not None else SanityInputs()

    # Resolve the Shortlist path if the caller did not supply a concrete one.
    shortlist_path = (
        paths.shortlist_path
        if paths.shortlist_path is not None
        else resolve_shortlist(config.SHORTLIST_DIR)
    )

    # Scored_Table (S1-10). Its geometry CRS is not used for a containment
    # operation (scores are joined on cell_id), so CRS is not required here; the
    # required score columns are (1.5).
    scored = _read_vector(
        config_or(paths.scored_path, config.SCORED_PATH),
        layer=config.SCORED_LAYER,
        source_name="Scored_Table",
        required_columns=config.REQUIRED_SCORE_COLUMNS,
        require_crs=False,
    )

    # Integrated_Feature_Table (S1-08) — the spot-check feature source.
    integrated = _read_vector(
        config_or(paths.integrated_path, config.INTEGRATED_PATH),
        layer=config.INTEGRATED_LAYER,
        source_name="Integrated_Feature_Table",
        required_columns=config.REQUIRED_INTEGRATED_COLUMNS,
        require_crs=False,
    )

    # Analysis_Grid (S1-02) — used for point-in-polygon containment, so its CRS
    # MUST be resolvable (2.2, 3.5).
    grid = _read_vector(
        config_or(paths.grid_path, config.GRID_PATH),
        layer=config.GRID_LAYER,
        source_name="Analysis_Grid",
        required_columns=config.REQUIRED_GRID_COLUMNS,
        require_crs=True,
    )

    # Wind_Generators (GA) — points located to cells in Check 1, so its CRS MUST
    # be resolvable (2.2). The single required attribute is the wind-farm name.
    wind_generators = _read_vector(
        config_or(paths.wind_generators_path, config.WIND_GENERATORS_PATH),
        layer=None,
        source_name="Wind_Generators",
        required_columns=(config.REQUIRED_WIND_GENERATOR_ATTR,),
        require_crs=True,
    )

    # The resolved Shortlist (S1-11).
    shortlist = _read_shortlist(shortlist_path)

    eligible, excluded = split_eligible(scored)

    return LoadedFrames(
        scored=scored,
        shortlist=shortlist,
        integrated=integrated,
        wind_generators=wind_generators,
        grid=grid,
        eligible=eligible,
        excluded=excluded,
        resolved_shortlist_path=Path(shortlist_path),
    )


def config_or(value: Path | str | None, default: Path) -> Path:
    """Return ``value`` as a ``Path`` when supplied, else the config ``default``."""
    return Path(value) if value is not None else default
