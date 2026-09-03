"""
Pure check computations for the S1-12 sanity-check stage (`sanity`).

This module holds the four plausibility checks the sanity stage runs against
the Sprint 1 outputs, plus the percentile/statistics helpers they share. Every
function here is PURE: frames in, structured results out, no filesystem access
and no mutation of any input. The loader (`load.py`) is the only file-reading
path; it hands fully in-memory frames to these functions, so each check is
independently testable and re-runnable against updated pipeline outputs.

The stage is a REALITY CHECK, not a modelling step: it asks whether the
pipeline's outputs make sense against known reality. A surprising result is
NEVER used to adjust the model and a data row is NEVER silently dropped —
surprises are recorded HONESTLY with an investigation note that distinguishes a
likely data issue from a legitimate model result, for the report's
"Issues for Sprint 2" section (Requirements 6, 8).

CRS is explicit at every boundary: containment operations run in the single
logged `CONTAINMENT_CRS` (EPSG:3577) via `geo.locate_points_to_cells`; storage
is EPSG:4326. This module never converts CRS silently.

Section map (checks are added incrementally by the S1-12 task plan):
  - Shared: percentile over the eligible population, anomaly records.
  - Check 1 — Known Wind Farm Comparison (Requirement 2)  [task 3.1]
  - Check 2 — Exclusion Validation (Requirement 3)         [this task]
  - Check 3 — Feature-Value Spot-Checks (Requirement 4)    [this task]
  - Check 4 — Score-Distribution Plausibility (Requirement 5) [task 6.1]
  - CheckOutcome no-silent-passes contract (Requirement 11) [task 9.1]

Design reference: design.md §4 "Check 1 — Known Wind Farm Comparison".
"""

from __future__ import annotations

from dataclasses import dataclass, field

import geopandas as gpd
import numpy as np
import pandas as pd

from . import config
from .geo import CrsTransform, locate_points_to_cells


# ===========================================================================
# Shared — anomaly records
# ===========================================================================
#
# The frozen `Anomaly` dataclass itself is OWNED by task 8.1 (`issues.py`),
# which defines it and implements `collect_issues(*check_results)` to gather
# every anomaly the four checks surface into the report's "Issues for Sprint 2"
# section. To avoid a premature dependency on that module — and the circular
# import it would create — each check result here exposes its surfaced
# anomalies as a list of plain, structured `CheckAnomaly` records. Task 8.1's
# `collect_issues` reads these fields (`check`, `description`, `kind`,
# `investigation_note`) and maps each into a real `Anomaly`. The field names
# match the `Anomaly` dataclass one-for-one so the mapping is mechanical.


# Anomaly kinds, mirrored by issues.Anomaly.kind (Requirements 6.4, 6.5). An
# anomaly is either a suspected DATA issue (an input looks wrong) or a
# legitimate MODEL result (the model genuinely disagrees with the expectation);
# the check records which, honestly, and NEVER auto-adjusts the model.
ANOMALY_DATA_ISSUE = "data_issue"
ANOMALY_MODEL_RESULT = "model_result"


@dataclass(frozen=True)
class CheckAnomaly:
    """
    A single surprising / inconsistent result surfaced by a check, recorded
    honestly rather than suppressed (Requirements 6, 8.3).

    This is the check-side, dependency-free record of an anomaly. Task 8.1's
    ``issues.collect_issues`` gathers every ``CheckAnomaly`` from the four check
    results and maps it — field for field — onto the frozen ``issues.Anomaly``
    dataclass for the report's "Issues for Sprint 2" section. ``kind`` is one of
    :data:`ANOMALY_DATA_ISSUE` / :data:`ANOMALY_MODEL_RESULT` (6.4, 6.5).
    """

    check: str  # which check surfaced it, e.g. "Known Wind Farm Comparison"
    description: str  # what was observed that was surprising
    kind: str  # ANOMALY_DATA_ISSUE | ANOMALY_MODEL_RESULT
    investigation_note: str  # how to tell a data issue from a model result


# ===========================================================================
# Shared — percentile over the eligible population (Requirements 2.3, 2.4, 5.1)
# ===========================================================================


def percentile_over_eligible(score: float, eligible_scores) -> float:
    """
    Percentile rank of ``score`` within the Eligible_Cell population, 0-to-100.

    Computes ``100 * (count of eligible scores <= score) / n_eligible`` over the
    Eligible_Cell population ONLY (Requirement 2.4). Excluded_Cell values are
    never passed in — the caller supplies the eligible scores — so perturbing an
    Excluded_Cell value can never change the result (Property 2). This is the
    "less-than-or-equal" (weak) percentile: a score at or above every eligible
    score is the 100th percentile; a score below every eligible score is above
    ``0`` only by the count of ties at the minimum.

    Args:
        score: the suitability_score whose percentile is wanted.
        eligible_scores: the suitability_score values of the Eligible_Cell
            population (array-like); Excluded_Cell values must NOT be included.

    Returns:
        The percentile on a 0-to-100 scale as a float.

    Raises:
        ValueError: if ``eligible_scores`` is empty — a percentile over an empty
            population is undefined, and silently returning 0 would be a lie.
    """
    values = np.asarray(eligible_scores, dtype=float)
    values = values[~np.isnan(values)]
    n_eligible = values.size
    if n_eligible == 0:
        raise ValueError(
            "percentile_over_eligible: the eligible population is empty; a "
            "percentile over zero eligible cells is undefined."
        )
    count_le = int(np.count_nonzero(values <= score))
    return 100.0 * count_le / n_eligible


# ===========================================================================
# Check 1 — Known Wind Farm Comparison (Requirement 2)
# ===========================================================================
#
# For each Known_Wind_Farm: locate it to its Containing_Cell in EPSG:3577
# (logged), look up that cell's suitability_score / rank / Percentile over the
# eligible population, and build a results-table row. Report how many farms fall
# in the Upper_Quartile (>= 75th percentile) against the expectation that most
# operational farms do. Any farm scoring below POOR_SCORE_PERCENTILE, landing in
# an Excluded_Cell (null score), or falling in NO grid cell is recorded HONESTLY
# with an investigation note — the model is never adjusted and the farm is never
# silently dropped (2.6, 2.7, 6.5, 8.3).


# The column names the Scored_Table exposes (from config.REQUIRED_SCORE_COLUMNS).
_CELL_ID = config.REQUIRED_SCORE_COLUMNS[0]  # "cell_id"
_SCORE = config.REQUIRED_SCORE_COLUMNS[1]  # "suitability_score"
_RANK = config.REQUIRED_SCORE_COLUMNS[2]  # "rank"


@dataclass(frozen=True)
class WindFarmRow:
    """
    One row of the Known_Wind_Farm_Comparison results table (Requirement 2.3).

    Columns mirror the report table ``Wind Farm | Cell ID | Score | Rank |
    Percentile | Notes``. ``cell_id`` is ``None`` when the farm point falls in
    NO grid cell (2.7); ``score`` / ``rank`` / ``percentile`` are ``None`` when
    the Containing_Cell is an Excluded_Cell (null score) or out-of-grid (2.6,
    2.7). ``notes`` records the honest outcome verbatim as it appears in the
    report's Notes column.
    """

    wind_farm: str  # farm name (REQUIRED_WIND_GENERATOR_ATTR)
    cell_id: object | None  # Containing_Cell id, or None if out-of-grid (2.7)
    score: float | None  # cell suitability_score, or None if excluded (2.6)
    rank: object | None  # cell rank, or None if excluded/out-of-grid
    percentile: float | None  # percentile over eligible pop, or None (2.4)
    in_upper_quartile: bool  # percentile >= UPPER_QUARTILE_PERCENTILE (2.5)
    notes: str  # honest outcome for the Notes column (2.6, 2.7)


@dataclass(frozen=True)
class WindFarmCheckResult:
    """
    Structured result of Check 1 — Known Wind Farm Comparison (Requirement 2).

    ``rows`` is one :class:`WindFarmRow` per Known_Wind_Farm, in the input
    wind-generator order, never dropping a farm (2.3, 2.7). ``n_known_farms`` /
    ``n_upper_quartile`` / ``proportion_upper_quartile`` report how many farms
    fall in the Upper_Quartile against the stated expectation that most
    operational farms do (2.5). ``expectation`` states that expectation in
    words for the report. ``anomalies`` carries every honestly-recorded
    surprise (poor score, excluded cell, out-of-grid) for task 8.1's
    ``collect_issues`` to gather (2.6, 2.7, 6.5, 8.3). ``transform_log`` is the
    list the containment transforms were appended to, rendered verbatim in the
    report's transform-log line.
    """

    rows: list[WindFarmRow]
    n_known_farms: int
    n_upper_quartile: int
    proportion_upper_quartile: float
    expectation: str
    anomalies: list[CheckAnomaly] = field(default_factory=list)
    transform_log: list[CrsTransform] = field(default_factory=list)


# The check name recorded on every anomaly this check surfaces.
_CHECK_NAME = "Known Wind Farm Comparison"

# Stated expectation rendered in the report (Requirement 2.5).
_UPPER_QUARTILE_EXPECTATION = (
    f"Most operational wind farms are expected to fall in the Upper_Quartile "
    f"(Percentile >= {config.UPPER_QUARTILE_PERCENTILE:g}) of the Eligible_Cell "
    f"score population."
)


def check_known_wind_farms(
    wind_generators: gpd.GeoDataFrame,
    grid: gpd.GeoDataFrame,
    scored: pd.DataFrame,
    containment_crs: str,
    transform_log: list[CrsTransform],
) -> WindFarmCheckResult:
    """
    Check 1 — locate each Known_Wind_Farm to its cell and report its score.

    PURE. For each Wind_Generators feature (a Known_Wind_Farm):

      1. Locate it to its Containing_Cell via
         :func:`geo.locate_points_to_cells` in the single explicit
         ``containment_crs`` (EPSG:3577), appending the transform to
         ``transform_log`` (Requirements 2.1, 2.2). A point in NO grid cell gets
         a null cell and is reported honestly, never dropped (2.7).
      2. Look up that cell's ``suitability_score`` and ``rank`` from ``scored``,
         and its Percentile over the Eligible_Cell population ONLY via
         :func:`percentile_over_eligible` (2.3, 2.4).
      3. Build a results-table row
         (``Wind Farm | Cell ID | Score | Rank | Percentile | Notes``) (2.3).

    Reports the count and proportion of farms in the Upper_Quartile (Percentile
    >= ``UPPER_QUARTILE_PERCENTILE``) and states the expectation that most
    operational farms fall there (2.5).

    Records HONESTLY in the Notes field, with an investigation note
    distinguishing a likely data issue from a legitimate model result, any farm
    whose cell scores below ``POOR_SCORE_PERCENTILE``, whose cell is an
    Excluded_Cell (null score), or whose point falls in NO grid cell. The model
    is NEVER adjusted and the farm is NEVER silently dropped; each such outcome
    is also surfaced as a :class:`CheckAnomaly` for the Sprint-2 issues section
    (2.6, 2.7, 6.5, 8.3).

    Args:
        wind_generators: the GA Wind_Generators points (EPSG:4326 storage),
            carrying ``config.REQUIRED_WIND_GENERATOR_ATTR`` (``name``).
        grid: the Analysis_Grid cell polygons (EPSG:4326 storage), carrying
            ``cell_id``.
        scored: the Scored_Table with ``cell_id`` / ``suitability_score`` /
            ``rank`` for every scored cell (eligible AND excluded).
        containment_crs: the single explicit containment CRS (EPSG:3577).
        transform_log: mutable list the containment transforms are appended to;
            rendered verbatim in the report's transform-log line.

    Returns:
        A :class:`WindFarmCheckResult`.
    """
    name_attr = config.REQUIRED_WIND_GENERATOR_ATTR

    # 1. Locate every farm point to its Containing_Cell in the metric CRS. The
    #    result has one row per input point, in point order, with a null cell_id
    #    for any out-of-extent point (2.7). transform_log is appended to (2.1, 2.2).
    located = locate_points_to_cells(
        wind_generators,
        grid,
        containment_crs,
        transform_log,
        purpose="wind-farm containment",
    )

    # The eligible population for the percentile — Excluded_Cell values are
    # never included (2.4). A cell is eligible iff it has BOTH a non-null score
    # and a non-null rank (the same rule as load.split_eligible).
    eligible_mask = scored[_SCORE].notna() & scored[_RANK].notna()
    eligible_scores = scored.loc[eligible_mask, _SCORE].to_numpy(dtype=float)

    # Fast cell_id -> (score, rank) lookup over the full Scored_Table.
    scored_indexed = scored.set_index(_CELL_ID)

    # Preserve wind-generator order; located rows are in the same order.
    farm_names = wind_generators[name_attr].tolist()
    located_cell_ids = located["cell_id"].tolist()

    rows: list[WindFarmRow] = []
    anomalies: list[CheckAnomaly] = []
    n_upper_quartile = 0

    for farm_name, cell_id in zip(farm_names, located_cell_ids):
        display_name = "(unnamed)" if farm_name is None or (
            isinstance(farm_name, float) and np.isnan(farm_name)
        ) else str(farm_name)

        # --- Case A: the farm point falls in NO grid cell (2.7) ---
        if cell_id is None or (isinstance(cell_id, float) and np.isnan(cell_id)):
            note = (
                "Point falls in NO Analysis_Grid cell (offshore / out-of-extent); "
                "recorded explicitly, not dropped."
            )
            rows.append(
                WindFarmRow(
                    wind_farm=display_name,
                    cell_id=None,
                    score=None,
                    rank=None,
                    percentile=None,
                    in_upper_quartile=False,
                    notes=note,
                )
            )
            anomalies.append(
                CheckAnomaly(
                    check=_CHECK_NAME,
                    description=(
                        f"Known wind farm '{display_name}' does not fall within "
                        f"any Analysis_Grid cell."
                    ),
                    kind=ANOMALY_DATA_ISSUE,
                    investigation_note=(
                        "Likely a DATA issue: the generator coordinate may be "
                        "offshore, in a neighbouring state, or outside the NSW "
                        "analysis extent. Verify the generator location against "
                        "the source before treating it as a model result."
                    ),
                )
            )
            continue

        # --- Look up the Containing_Cell's score and rank ---
        if cell_id not in scored_indexed.index:
            # The grid contains this cell but the Scored_Table does not — a
            # genuine data-coverage gap, reported honestly.
            note = (
                f"Containing cell {cell_id!r} is present in the grid but ABSENT "
                f"from the Scored_Table; recorded explicitly, not dropped."
            )
            rows.append(
                WindFarmRow(
                    wind_farm=display_name,
                    cell_id=cell_id,
                    score=None,
                    rank=None,
                    percentile=None,
                    in_upper_quartile=False,
                    notes=note,
                )
            )
            anomalies.append(
                CheckAnomaly(
                    check=_CHECK_NAME,
                    description=(
                        f"Known wind farm '{display_name}' locates to cell "
                        f"{cell_id!r}, which is absent from the Scored_Table."
                    ),
                    kind=ANOMALY_DATA_ISSUE,
                    investigation_note=(
                        "Likely a DATA issue: the grid and Scored_Table disagree "
                        "on cell coverage. Verify the Scored_Table was generated "
                        "over the same grid before treating it as a model result."
                    ),
                )
            )
            continue

        cell = scored_indexed.loc[cell_id]
        # A cell_id could in principle be non-unique; take the first match
        # deterministically and keep the outcome honest.
        if isinstance(cell, pd.DataFrame):
            cell = cell.iloc[0]
        raw_score = cell[_SCORE]
        raw_rank = cell[_RANK]
        score_is_null = pd.isna(raw_score)
        rank_is_null = pd.isna(raw_rank)

        # --- Case B: the Containing_Cell is an Excluded_Cell (null score) (2.6) ---
        if score_is_null or rank_is_null:
            note = (
                f"Containing cell {cell_id!r} is an Excluded_Cell "
                f"(null suitability_score/rank); the farm sits in land the "
                f"pipeline excluded. Recorded honestly; model NOT adjusted."
            )
            rows.append(
                WindFarmRow(
                    wind_farm=display_name,
                    cell_id=cell_id,
                    score=None,
                    rank=None,
                    percentile=None,
                    in_upper_quartile=False,
                    notes=note,
                )
            )
            anomalies.append(
                CheckAnomaly(
                    check=_CHECK_NAME,
                    description=(
                        f"Known wind farm '{display_name}' locates to Excluded_Cell "
                        f"{cell_id!r} with a null suitability_score."
                    ),
                    kind=ANOMALY_DATA_ISSUE,
                    investigation_note=(
                        "Distinguish a DATA issue from a MODEL result: an "
                        "operational farm on excluded land usually means an "
                        "exclusion layer (protected area, land use) or the "
                        "generator coordinate is wrong. If the exclusion is "
                        "genuinely correct at this resolution, it is a legitimate "
                        "model result. Investigate the input before any change; "
                        "the model is never adjusted to raise this cell's score."
                    ),
                )
            )
            continue

        # --- Case C: an eligible Containing_Cell — the normal path ---
        score = float(raw_score)
        percentile = percentile_over_eligible(score, eligible_scores)
        in_uq = percentile >= config.UPPER_QUARTILE_PERCENTILE
        if in_uq:
            n_upper_quartile += 1

        if percentile < config.POOR_SCORE_PERCENTILE:
            # A known operational farm scoring poorly is surprising — record it
            # honestly with an investigation note (2.6).
            note = (
                f"Scores POORLY: Percentile {percentile:.1f} is below the "
                f"documented {config.POOR_SCORE_PERCENTILE:g}th-percentile "
                f"threshold. Recorded honestly; model NOT adjusted."
            )
            anomalies.append(
                CheckAnomaly(
                    check=_CHECK_NAME,
                    description=(
                        f"Known wind farm '{display_name}' (cell {cell_id!r}) "
                        f"scores at the {percentile:.1f}th percentile, below the "
                        f"{config.POOR_SCORE_PERCENTILE:g}th-percentile "
                        f"'scores poorly' threshold."
                    ),
                    kind=ANOMALY_MODEL_RESULT,
                    investigation_note=(
                        "Distinguish a DATA issue from a MODEL result: check the "
                        "cell's feature values (wind_speed, slope, transmission "
                        "distance) against source before concluding the model is "
                        "wrong. A genuinely low score at a real farm is a "
                        "legitimate model result worth flagging for Sprint 2; the "
                        "model is never adjusted to raise this cell's score."
                    ),
                )
            )
        elif in_uq:
            note = (
                f"In Upper_Quartile (Percentile {percentile:.1f} >= "
                f"{config.UPPER_QUARTILE_PERCENTILE:g}), as expected."
            )
        else:
            note = f"Percentile {percentile:.1f} (mid-range)."

        rows.append(
            WindFarmRow(
                wind_farm=display_name,
                cell_id=cell_id,
                score=score,
                rank=None if rank_is_null else raw_rank,
                percentile=percentile,
                in_upper_quartile=in_uq,
                notes=note,
            )
        )

    n_known_farms = len(rows)
    proportion = (n_upper_quartile / n_known_farms) if n_known_farms else 0.0

    return WindFarmCheckResult(
        rows=rows,
        n_known_farms=n_known_farms,
        n_upper_quartile=n_upper_quartile,
        proportion_upper_quartile=proportion,
        expectation=_UPPER_QUARTILE_EXPECTATION,
        anomalies=anomalies,
        transform_log=transform_log,
    )


# ===========================================================================
# Check 2 — Exclusion Validation (Requirement 3)
# ===========================================================================
#
# For each documented LANDMARKS entry (Sydney CBD / Newcastle / Wollongong
# urban centres; Blue Mountains NP / Kosciuszko NP national parks): build its
# point from the documented EPSG:4326 coordinate, locate it to its cell in the
# single explicit CONTAINMENT_CRS (EPSG:3577, logged), and assert the cell is an
# Excluded_Cell (ineligible / null suitability_score) or absent from the grid
# (3.1, 3.2). Additionally assert NO offshore/ocean cell exists in the grid:
# every grid cell must resolve to a land/eligible-population membership (i.e.
# be present in the Integrated_Feature_Table, which is built over land cells
# only), so a grid cell absent from that table would be an ocean-only anomaly
# (3.3). Each assertion records the expected outcome, the observed outcome, and
# an explicit pass/fail — NEVER a pass without an observed value (3.4). A
# failing assertion is reported HONESTLY as an Anomaly with an investigation
# note and is NOT suppressed to make the check pass (3.6, 8.3).


# The Integrated_Feature_Table columns Check 2 reads (from
# config.REQUIRED_INTEGRATED_COLUMNS): the cell key and the eligible flag.
_INT_CELL_ID = config.REQUIRED_INTEGRATED_COLUMNS[0]  # "cell_id"
_INT_ELIGIBLE = config.REQUIRED_INTEGRATED_COLUMNS[5]  # "eligible"

# The check name recorded on every anomaly this check surfaces.
_EXCLUSION_CHECK_NAME = "Exclusion Validation"

# The kind label the offshore/ocean assertion carries in its records.
_OFFSHORE_KIND = "offshore"


@dataclass(frozen=True)
class ExclusionAssertion:
    """
    One expected-versus-observed assertion of Check 2 (Requirements 3.4, 11.3).

    Mirrors the report's assertion-record table
    (``landmark | kind | lat | lon | cell_id | expected | observed | passed``).
    A landmark assertion carries the documented EPSG:4326 coordinate (3.5) and
    the ``cell_id`` it located to in the CONTAINMENT_CRS (``None`` when the point
    is absent from the grid). The offshore/ocean assertion (``kind ==
    "offshore"``) covers the whole grid, so its ``lat`` / ``lon`` / ``cell_id``
    are ``None``. ``expected`` and ``observed`` are the human-readable outcomes
    and ``passed`` is the explicit pass/fail — NEVER a pass without an observed
    value (3.4).
    """

    landmark: str  # e.g. "Sydney CBD", or "no offshore/ocean cell" for 3.3
    kind: str  # "urban" | "park" | "offshore"
    lat: float | None  # documented EPSG:4326 latitude, or None (offshore)
    lon: float | None  # documented EPSG:4326 longitude, or None (offshore)
    cell_id: object | None  # located Containing_Cell, or None if absent (3.2)
    expected: str  # expected outcome, e.g. "ineligible / excluded / absent"
    observed: str  # observed eligibility / grid-membership (3.4, 11.3)
    passed: bool  # explicit pass/fail, never a pass without an observed value


@dataclass(frozen=True)
class ExclusionCheckResult:
    """
    Structured result of Check 2 — Exclusion Validation (Requirement 3).

    ``assertions`` is one :class:`ExclusionAssertion` per documented landmark
    (in ``LANDMARKS`` order) plus the single offshore/ocean assertion over the
    whole grid (3.1, 3.2, 3.3). ``n_passed`` / ``n_failed`` count the explicit
    pass/fail outcomes (11.3). ``all_passed`` is the per-check flag. Every
    failing assertion is also surfaced as a :class:`CheckAnomaly` in
    ``anomalies`` for task 8.1's ``collect_issues`` to gather, recorded honestly
    and never suppressed (3.6, 8.3). ``transform_log`` is the list the landmark
    containment transforms were appended to, rendered verbatim in the report's
    transform-log line.
    """

    assertions: list[ExclusionAssertion]
    n_passed: int
    n_failed: int
    all_passed: bool
    anomalies: list[CheckAnomaly] = field(default_factory=list)
    transform_log: list[CrsTransform] = field(default_factory=list)


def _landmarks_to_points(landmarks, storage_crs: str) -> gpd.GeoDataFrame:
    """
    Build an EPSG:4326 point frame from the documented ``LANDMARKS`` coordinates.

    Each landmark's documented ``(lat, lon)`` in EPSG:4326 storage becomes a
    point, in ``LANDMARKS`` order, so :func:`geo.locate_points_to_cells` can
    locate it to its cell in the CONTAINMENT_CRS (3.5). PURE: constructs a new
    frame and never touches disk.
    """
    from shapely.geometry import Point

    geometries = [Point(lm.lon, lm.lat) for lm in landmarks]
    return gpd.GeoDataFrame(
        {
            "landmark": [lm.name for lm in landmarks],
            "kind": [lm.kind for lm in landmarks],
            "lat": [lm.lat for lm in landmarks],
            "lon": [lm.lon for lm in landmarks],
        },
        geometry=geometries,
        crs=storage_crs,
    )


def check_exclusions(
    landmarks,
    grid: gpd.GeoDataFrame,
    scored: pd.DataFrame,
    integrated: pd.DataFrame,
    containment_crs: str,
    transform_log: list[CrsTransform],
) -> ExclusionCheckResult:
    """
    Check 2 — assert documented landmarks are excluded and no ocean cell exists.

    PURE. For each documented ``LANDMARKS`` entry (Sydney CBD / Newcastle /
    Wollongong urban centres, Blue Mountains NP / Kosciuszko NP national parks):

      1. Build the landmark point from its documented EPSG:4326 coordinate and
         locate it to its cell in the single explicit ``containment_crs``
         (EPSG:3577), appending the transform to ``transform_log`` (3.5).
      2. Assert the Containing_Cell is an Excluded_Cell — ineligible
         (``eligible == False`` in the Integrated_Feature_Table) OR carrying a
         null ``suitability_score``/``rank`` in the Scored_Table — or absent
         from the grid entirely (3.1, 3.2). A point absent from the grid PASSES:
         a landmark outside the analysis extent is trivially not ranked.

    Additionally assert NO offshore/ocean cell exists in the Analysis_Grid:
    every grid ``cell_id`` must resolve to a land/eligible-population membership,
    i.e. be present in the Integrated_Feature_Table (which is built over land
    cells only). Any grid cell ABSENT from that table is an ocean-only anomaly
    and fails the assertion (3.3).

    For EVERY assertion the result records the expected outcome, the observed
    outcome, and an explicit pass/fail; a pass is NEVER recorded without an
    observed value (3.4). A failing assertion — an urban/protected cell observed
    eligible, or an offshore cell found in the grid — is reported HONESTLY as a
    :class:`CheckAnomaly` with an investigation note distinguishing a likely
    data issue from a legitimate model result, and is NEVER suppressed to make
    the check pass (3.6, 8.3).

    Args:
        landmarks: the documented landmark table (``config.LANDMARKS``), each a
            named EPSG:4326 coordinate with a ``kind`` (``urban`` | ``park``).
        grid: the Analysis_Grid cell polygons (EPSG:4326 storage), carrying
            ``cell_id``.
        scored: the Scored_Table with ``cell_id`` / ``suitability_score`` /
            ``rank`` for every scored cell (eligible AND excluded).
        integrated: the Integrated_Feature_Table with ``cell_id`` and the
            ``eligible`` flag, built over land cells only.
        containment_crs: the single explicit containment CRS (EPSG:3577).
        transform_log: mutable list the containment transforms are appended to;
            rendered verbatim in the report's transform-log line.

    Returns:
        An :class:`ExclusionCheckResult`.
    """
    # 1. Locate every landmark point to its Containing_Cell in the metric CRS.
    #    The result is one row per landmark, in LANDMARKS order, with a null
    #    cell_id for any point absent from the grid (3.2). transform_log is
    #    appended to (3.5).
    points = _landmarks_to_points(landmarks, config.STORAGE_CRS)
    located = locate_points_to_cells(
        points,
        grid,
        containment_crs,
        transform_log,
        purpose="landmark containment",
    )

    # Fast cell_id -> row lookups over the Scored_Table and the eligible flag of
    # the Integrated_Feature_Table.
    scored_indexed = scored.set_index(_CELL_ID)
    integrated_eligible = (
        integrated.set_index(_INT_CELL_ID)[_INT_ELIGIBLE]
        if _INT_ELIGIBLE in integrated.columns
        else None
    )

    assertions: list[ExclusionAssertion] = []
    anomalies: list[CheckAnomaly] = []

    located_cell_ids = located["cell_id"].tolist()
    landmark_list = list(landmarks)

    for landmark, cell_id in zip(landmark_list, located_cell_ids):
        expected = "ineligible / excluded / absent from grid"

        # --- Case A: the landmark falls in NO grid cell — PASS (3.2) ---
        if cell_id is None or (isinstance(cell_id, float) and np.isnan(cell_id)):
            observed = "absent from grid (point falls in no Analysis_Grid cell)"
            assertions.append(
                ExclusionAssertion(
                    landmark=landmark.name,
                    kind=landmark.kind,
                    lat=landmark.lat,
                    lon=landmark.lon,
                    cell_id=None,
                    expected=expected,
                    observed=observed,
                    passed=True,
                )
            )
            continue

        # --- Determine the observed eligibility of the Containing_Cell ---
        # A cell is "eligible" (i.e. NOT excluded) if EITHER the integrated
        # eligible flag is True OR the Scored_Table gives it a non-null
        # score/rank. The assertion PASSES when the cell is excluded by BOTH
        # signals (or absent from either). Observed is always recorded (3.4).
        observed_parts: list[str] = []
        is_eligible = False

        # Scored_Table signal.
        if cell_id in scored_indexed.index:
            cell = scored_indexed.loc[cell_id]
            if isinstance(cell, pd.DataFrame):
                cell = cell.iloc[0]
            score_null = pd.isna(cell[_SCORE])
            rank_null = pd.isna(cell[_RANK])
            if score_null and rank_null:
                observed_parts.append("null suitability_score/rank in Scored_Table")
            else:
                observed_parts.append(
                    f"non-null suitability_score={cell[_SCORE]!r} in Scored_Table"
                )
                is_eligible = True
        else:
            observed_parts.append("absent from Scored_Table")

        # Integrated eligible-flag signal.
        if integrated_eligible is not None and cell_id in integrated_eligible.index:
            flag = integrated_eligible.loc[cell_id]
            if isinstance(flag, pd.Series):
                flag = flag.iloc[0]
            if bool(flag):
                observed_parts.append("eligible == True in Integrated_Feature_Table")
                is_eligible = True
            else:
                observed_parts.append("eligible == False in Integrated_Feature_Table")
        else:
            observed_parts.append("absent from Integrated_Feature_Table")

        observed = f"cell {cell_id!r}: " + "; ".join(observed_parts)
        passed = not is_eligible

        assertions.append(
            ExclusionAssertion(
                landmark=landmark.name,
                kind=landmark.kind,
                lat=landmark.lat,
                lon=landmark.lon,
                cell_id=cell_id,
                expected=expected,
                observed=observed,
                passed=passed,
            )
        )

        if not passed:
            kind_word = "urban centre" if landmark.kind == "urban" else "national park"
            anomalies.append(
                CheckAnomaly(
                    check=_EXCLUSION_CHECK_NAME,
                    description=(
                        f"Landmark '{landmark.name}' ({kind_word}) locates to cell "
                        f"{cell_id!r}, which is observed ELIGIBLE — expected an "
                        f"Excluded_Cell."
                    ),
                    kind=ANOMALY_DATA_ISSUE,
                    investigation_note=(
                        "Distinguish a DATA issue from a MODEL result: an urban "
                        "centre or national park that is ranked usually means an "
                        "exclusion layer (populated-area or protected-area) did "
                        "not cover this cell, or the landmark coordinate is wrong. "
                        "Investigate the exclusion inputs before any change; the "
                        "model is never adjusted to force this cell to exclude."
                    ),
                )
            )

    # --- Offshore/ocean assertion over the whole grid (3.3) ---
    # Every grid cell must resolve to a land/eligible-population membership: the
    # Integrated_Feature_Table is built over land cells only, so any grid cell
    # absent from it is an ocean-only anomaly. Observed is always recorded (3.4).
    grid_cell_ids = set(grid[_CELL_ID].tolist())
    if integrated_eligible is not None:
        integrated_cell_ids = set(integrated_eligible.index.tolist())
    else:
        integrated_cell_ids = set(integrated[_INT_CELL_ID].tolist())
    offshore_cells = sorted(grid_cell_ids - integrated_cell_ids, key=repr)
    n_offshore = len(offshore_cells)
    offshore_passed = n_offshore == 0

    if offshore_passed:
        offshore_observed = (
            f"all {len(grid_cell_ids)} grid cells resolve to a "
            f"land/eligible-population membership in the Integrated_Feature_Table"
        )
    else:
        sample = offshore_cells[:5]
        offshore_observed = (
            f"{n_offshore} grid cell(s) absent from the Integrated_Feature_Table "
            f"(e.g. {sample}); these have no land/eligible-population membership"
        )

    assertions.append(
        ExclusionAssertion(
            landmark="no offshore/ocean cell in the Analysis_Grid",
            kind=_OFFSHORE_KIND,
            lat=None,
            lon=None,
            cell_id=None,
            expected="every grid cell resolves to a land/eligible-population membership",
            observed=offshore_observed,
            passed=offshore_passed,
        )
    )

    if not offshore_passed:
        anomalies.append(
            CheckAnomaly(
                check=_EXCLUSION_CHECK_NAME,
                description=(
                    f"{n_offshore} Analysis_Grid cell(s) are absent from the "
                    f"Integrated_Feature_Table (e.g. {offshore_cells[:5]}), "
                    f"indicating possible offshore/ocean cells in the grid."
                ),
                kind=ANOMALY_DATA_ISSUE,
                investigation_note=(
                    "Likely a DATA issue: the Analysis_Grid should tile land "
                    "only. Grid cells with no membership in the "
                    "Integrated_Feature_Table suggest an ocean/offshore cell "
                    "leaked into the grid, or the integration stage dropped land "
                    "cells. Investigate the grid-generation land mask and the "
                    "integration key coverage before any change."
                ),
            )
        )

    n_failed = sum(1 for a in assertions if not a.passed)
    n_passed = len(assertions) - n_failed

    return ExclusionCheckResult(
        assertions=assertions,
        n_passed=n_passed,
        n_failed=n_failed,
        all_passed=n_failed == 0,
        anomalies=anomalies,
        transform_log=transform_log,
    )

# ===========================================================================
# Check 3 — Feature-Value Spot-Checks (Requirement 4)
# ===========================================================================
#
# Deterministically select N (SPOT_CHECK_MIN..SPOT_CHECK_MAX, default
# SPOT_CHECK_DEFAULT) Spot_Check_Cells that span the Eligible_Cell score range,
# then record each selected cell's feature values so a human reviewer can
# independently verify them against source. The selection is a fixed function of
# (sorted eligible scores, n) so repeated runs pick the SAME cells (12.3); the
# recording never fabricates a value — a missing feature is recorded as MISSING
# with a note (4.6). This check surfaces no automated pass/fail: verification is
# a human-judgement item, so each row carries the VERIFY_SOURCES entry for its
# value and an empty `discrepancy` field for the reviewer to fill in (4.3, 4.4).

# The Integrated_Feature_Table columns Check 3 reads (from
# config.REQUIRED_INTEGRATED_COLUMNS): the feature values the spot-check records.
_INT_WIND_SPEED = config.REQUIRED_INTEGRATED_COLUMNS[1]  # "wind_speed"
_INT_SLOPE_DEG = config.REQUIRED_INTEGRATED_COLUMNS[2]  # "slope_deg"
_INT_DIST_TRANSMISSION = config.REQUIRED_INTEGRATED_COLUMNS[3]  # "dist_transmission_km"
_INT_PROTECTED = config.REQUIRED_INTEGRATED_COLUMNS[4]  # "protected"

# The grid centroid columns a Spot_Check_Cell carries once eligible cells have
# been joined to the Analysis_Grid (config.REQUIRED_GRID_COLUMNS[1:3]).
_CENTROID_LAT = config.REQUIRED_GRID_COLUMNS[1]  # "centroid_lat"
_CENTROID_LON = config.REQUIRED_GRID_COLUMNS[2]  # "centroid_lon"

# The sentinel recorded when a required feature value is absent, rather than
# fabricating one (Requirement 4.6).
MISSING_VALUE = "MISSING"

# The score-band label each selected position spans (Requirement 4.2). The top
# and bottom cells are always included; interior selections are labelled
# "middle".
SPOT_BAND_TOP = "top"
SPOT_BAND_MIDDLE = "middle"
SPOT_BAND_BOTTOM = "bottom"

# The check name recorded on any anomaly this check surfaces.
_SPOT_CHECK_NAME = "Feature-Value Spot-Checks"


@dataclass(frozen=True)
class SpotCheckRow:
    """
    One recorded Spot_Check_Cell (Requirements 4.3, 4.4, 4.6).

    Mirrors the report's spot-check table. ``cell_id`` / ``centroid_lat`` /
    ``centroid_lon`` locate the cell in EPSG:4326 storage (4.3). ``score_band``
    records where in the score range the cell sits (``top`` / ``middle`` /
    ``bottom``), the deterministic span the selection guarantees (4.2). Each
    feature value (``wind_speed`` / ``slope_deg`` / ``dist_transmission_km`` /
    ``protected``) is the value read from the Integrated_Feature_Table, or the
    :data:`MISSING_VALUE` sentinel when that feature is absent, never fabricated
    (4.6). ``verify_sources`` maps each feature name to the independent source a
    reviewer verifies it against (4.4). ``discrepancy`` is intentionally left
    empty for the human reviewer to fill in (4.3).
    """

    cell_id: object  # selected Spot_Check_Cell id (grid-native, 4.3)
    centroid_lat: float | None  # EPSG:4326 latitude, or None if unavailable (4.3)
    centroid_lon: float | None  # EPSG:4326 longitude, or None if unavailable (4.3)
    score: float  # the cell's suitability_score (context for the band)
    score_band: str  # SPOT_BAND_TOP | SPOT_BAND_MIDDLE | SPOT_BAND_BOTTOM (4.2)
    wind_speed: object  # float value or MISSING_VALUE (4.3, 4.4, 4.6)
    slope_deg: object  # float value or MISSING_VALUE (4.3, 4.4, 4.6)
    dist_transmission_km: object  # float value or MISSING_VALUE (4.3, 4.4, 4.6)
    protected: object  # bool value or MISSING_VALUE (4.3, 4.4, 4.6)
    verify_sources: dict  # feature name -> independent verification source (4.4)
    discrepancy: str  # empty human-verification field, left blank (4.3)
    notes: str  # honest note recording any MISSING feature value (4.6)


@dataclass(frozen=True)
class SpotCheckResult:
    """
    Structured result of Check 3 — Feature-Value Spot-Checks (Requirement 4).

    ``rows`` is one :class:`SpotCheckRow` per selected Spot_Check_Cell, in
    ascending-score selection order (bottom .. top), so the report table spans
    the score range (4.2, 4.3). ``n_spot_cells`` is the count actually recorded
    (== the requested ``n``). ``verify_sources`` is the shared feature ->
    verification-source map (a copy of ``config.VERIFY_SOURCES``) rendered once
    in the report header for reference (4.4). ``anomalies`` carries an honestly
    recorded note for every cell that was missing a required feature value, for
    task 8.1's ``collect_issues`` to gather (4.6). Check 3 emits no automated
    pass/fail — verification is a human-judgement item (11.x note in design §6).
    """

    rows: list[SpotCheckRow]
    n_spot_cells: int
    verify_sources: dict = field(default_factory=dict)
    anomalies: list[CheckAnomaly] = field(default_factory=list)


def select_spot_cells(eligible: pd.DataFrame, n: int) -> pd.DataFrame:
    """
    Deterministically select ``n`` Eligible_Cells spanning the score range.

    PURE and DETERMINISTIC. The selection is a fixed function of
    ``(sorted eligible scores, n)`` — no randomness, no clock, no filesystem —
    so repeated runs over identical inputs pick the SAME cells (Requirement
    12.3).

    Steps:

      1. Require ``SPOT_CHECK_MIN <= n <= SPOT_CHECK_MAX``; otherwise raise a
         ``ValueError`` naming the invalid count so the caller halts BEFORE any
         output (Requirement 4.5). The orchestrator (``run``) also validates the
         count up front; validating here keeps the pure function honest when
         called directly.
      2. Order the Eligible_Cells ascending by ``suitability_score`` with a
         ``cell_id`` tie-break, so the ordering is total and stable regardless
         of the input row order.
      3. Pick ``n`` evenly-spaced quantile positions spanning the full range —
         ``round(i * (m - 1) / (n - 1))`` for ``i`` in ``0..n-1`` over ``m``
         sorted rows — so the selection ALWAYS includes the bottom cell
         (position 0), the top cell (position ``m - 1``), and ``n - 2`` interior
         quantiles between them (Requirement 4.2). Positions are de-duplicated
         while preserving order, so a small eligible population never yields the
         same cell twice.

    A ``score_band`` column is attached to the returned frame: ``bottom`` for the
    lowest-score selection, ``top`` for the highest, ``middle`` for the interior
    ones (the deterministic span, 4.2).

    Args:
        eligible: the Eligible_Cell frame (non-null ``suitability_score`` AND
            ``rank``), carrying at least ``cell_id`` and ``suitability_score``.
            Any additional columns (e.g. ``centroid_lat`` / ``centroid_lon``
            joined in from the Analysis_Grid) are preserved for
            :func:`check_spot_values` to read.
        n: the requested Spot_Check_Cells count, ``SPOT_CHECK_MIN..SPOT_CHECK_MAX``.

    Returns:
        A new DataFrame of exactly ``n`` selected rows (or fewer only if the
        eligible population itself has fewer than ``n`` distinct cells), in
        ascending-score order, with an added ``score_band`` column. The input
        frame is never mutated.

    Raises:
        ValueError: if ``n`` is outside ``[SPOT_CHECK_MIN, SPOT_CHECK_MAX]``
            (4.5), or if the eligible population is empty.
    """
    if not (config.SPOT_CHECK_MIN <= n <= config.SPOT_CHECK_MAX):
        raise ValueError(
            f"select_spot_cells: requested Spot_Check_Cells count {n} is outside "
            f"the inclusive range [{config.SPOT_CHECK_MIN}, {config.SPOT_CHECK_MAX}]."
        )

    m = len(eligible)
    if m == 0:
        raise ValueError(
            "select_spot_cells: the eligible population is empty; cannot select "
            "any Spot_Check_Cells."
        )

    # 2. Total, stable ordering: ascending score, cell_id tie-break.
    ordered = eligible.sort_values(
        by=[_SCORE, _CELL_ID], ascending=[True, True], kind="mergesort"
    ).reset_index(drop=True)

    # 3. Evenly-spaced quantile positions spanning [0, m-1], always including
    #    the bottom (0) and top (m-1). De-duplicate while preserving order so a
    #    small population never selects the same cell twice.
    if n == 1:
        positions = [0]
    else:
        raw = [round(i * (m - 1) / (n - 1)) for i in range(n)]
        seen: set[int] = set()
        positions = []
        for pos in raw:
            if pos not in seen:
                seen.add(pos)
                positions.append(pos)

    selected = ordered.iloc[positions].copy().reset_index(drop=True)

    # Attach the deterministic score_band label: bottom / top / middle.
    bands = []
    last = len(selected) - 1
    for idx, pos in enumerate(positions):
        if pos == 0:
            bands.append(SPOT_BAND_BOTTOM)
        elif pos == m - 1:
            bands.append(SPOT_BAND_TOP)
        else:
            bands.append(SPOT_BAND_MIDDLE)
        # Guard the degenerate single-cell edge: if only one position survived
        # de-duplication it is simultaneously top and bottom; label it "bottom".
        if last == 0:
            bands[-1] = SPOT_BAND_BOTTOM
    selected["score_band"] = bands

    return selected


def _feature_value_or_missing(row, column):
    """
    Read ``column`` from a per-cell feature ``row``, or the MISSING sentinel.

    Returns ``(value, missing)``: ``value`` is the native feature value when the
    column is present and non-null, otherwise :data:`MISSING_VALUE`; ``missing``
    is ``True`` in the latter case. Never fabricates a value (Requirement 4.6).
    """
    if row is None or column not in row.index:
        return MISSING_VALUE, True
    raw = row[column]
    if pd.isna(raw):
        return MISSING_VALUE, True
    return raw, False


def check_spot_values(spot_cells: pd.DataFrame, integrated: pd.DataFrame) -> SpotCheckResult:
    """
    Check 3 — record each Spot_Check_Cell's feature values for verification.

    PURE. For each selected cell in ``spot_cells`` (from
    :func:`select_spot_cells`) record, in a :class:`SpotCheckRow`:

      - ``cell_id`` and its ``centroid_lat`` / ``centroid_lon`` in EPSG:4326
        storage — read from the ``spot_cells`` frame, which the caller joins to
        the Analysis_Grid so the centroids are available (Requirement 4.3);
      - the feature values ``wind_speed``, ``slope_deg`` (or elevation),
        ``dist_transmission_km``, and the ``protected`` flag, read from the
        Integrated_Feature_Table for that ``cell_id`` (4.3);
      - the ``VERIFY_SOURCES`` entry for each value — the independent source a
        reviewer verifies it against — and an empty ``discrepancy`` field for
        the human reviewer to fill in (4.3, 4.4).

    A cell missing a required feature value in the Integrated_Feature_Table
    records that value as :data:`MISSING_VALUE` with an honest note rather than
    fabricating one, and surfaces a :class:`CheckAnomaly` so the omission is
    visible in the Sprint-2 issues section (4.6). The model is never adjusted and
    no cell is silently dropped.

    Args:
        spot_cells: the selected Spot_Check_Cells (from :func:`select_spot_cells`),
            carrying ``cell_id``, ``suitability_score``, ``score_band``, and —
            where the caller joined the grid — ``centroid_lat`` / ``centroid_lon``.
        integrated: the Integrated_Feature_Table with ``cell_id`` and the
            per-cell feature columns (``wind_speed`` / ``slope_deg`` /
            ``dist_transmission_km`` / ``protected``).

    Returns:
        A :class:`SpotCheckResult`.
    """
    verify_sources = dict(config.VERIFY_SOURCES)

    # Fast cell_id -> feature-row lookup over the Integrated_Feature_Table.
    integrated_indexed = (
        integrated.set_index(_INT_CELL_ID)
        if _INT_CELL_ID in integrated.columns
        else None
    )

    has_lat = _CENTROID_LAT in spot_cells.columns
    has_lon = _CENTROID_LON in spot_cells.columns

    rows: list[SpotCheckRow] = []
    anomalies: list[CheckAnomaly] = []

    for _, cell in spot_cells.iterrows():
        cell_id = cell[_CELL_ID]

        centroid_lat = (
            float(cell[_CENTROID_LAT])
            if has_lat and not pd.isna(cell[_CENTROID_LAT])
            else None
        )
        centroid_lon = (
            float(cell[_CENTROID_LON])
            if has_lon and not pd.isna(cell[_CENTROID_LON])
            else None
        )

        # Locate this cell's feature row in the Integrated_Feature_Table.
        feature_row = None
        if integrated_indexed is not None and cell_id in integrated_indexed.index:
            feature_row = integrated_indexed.loc[cell_id]
            # A non-unique cell_id would give a DataFrame; take the first match
            # deterministically and keep the outcome honest.
            if isinstance(feature_row, pd.DataFrame):
                feature_row = feature_row.iloc[0]

        wind_speed, ws_missing = _feature_value_or_missing(feature_row, _INT_WIND_SPEED)
        slope_deg, sl_missing = _feature_value_or_missing(feature_row, _INT_SLOPE_DEG)
        dist_tx, dt_missing = _feature_value_or_missing(feature_row, _INT_DIST_TRANSMISSION)
        protected, pr_missing = _feature_value_or_missing(feature_row, _INT_PROTECTED)

        # Coerce present numeric values to plain floats / bools for a clean table.
        if not ws_missing:
            wind_speed = float(wind_speed)
        if not sl_missing:
            slope_deg = float(slope_deg)
        if not dt_missing:
            dist_tx = float(dist_tx)
        if not pr_missing:
            protected = bool(protected)

        missing_features = [
            name
            for name, is_missing in (
                (_INT_WIND_SPEED, ws_missing),
                (_INT_SLOPE_DEG, sl_missing),
                (_INT_DIST_TRANSMISSION, dt_missing),
                (_INT_PROTECTED, pr_missing),
            )
            if is_missing
        ]

        if feature_row is None:
            note = (
                f"Cell {cell_id!r} is ABSENT from the Integrated_Feature_Table; "
                f"all feature values recorded as {MISSING_VALUE}, not fabricated."
            )
        elif missing_features:
            note = (
                f"Missing feature value(s) {missing_features} recorded as "
                f"{MISSING_VALUE}, not fabricated."
            )
        else:
            note = ""

        if feature_row is None or missing_features:
            anomalies.append(
                CheckAnomaly(
                    check=_SPOT_CHECK_NAME,
                    description=(
                        f"Spot_Check_Cell {cell_id!r} is missing feature value(s) "
                        f"{missing_features or 'ALL (absent from Integrated_Feature_Table)'} "
                        f"in the Integrated_Feature_Table."
                    ),
                    kind=ANOMALY_DATA_ISSUE,
                    investigation_note=(
                        "Likely a DATA issue: the integration stage should carry "
                        "every feature for every eligible cell. A gap here means "
                        "an upstream join dropped this cell's value. Recorded as "
                        f"{MISSING_VALUE}; investigate the integration key "
                        "coverage before treating it as a model result."
                    ),
                )
            )

        rows.append(
            SpotCheckRow(
                cell_id=cell_id,
                centroid_lat=centroid_lat,
                centroid_lon=centroid_lon,
                score=float(cell[_SCORE]),
                score_band=cell["score_band"] if "score_band" in cell.index else SPOT_BAND_MIDDLE,
                wind_speed=wind_speed,
                slope_deg=slope_deg,
                dist_transmission_km=dist_tx,
                protected=protected,
                verify_sources=verify_sources,
                discrepancy="",
                notes=note,
            )
        )

    return SpotCheckResult(
        rows=rows,
        n_spot_cells=len(rows),
        verify_sources=verify_sources,
        anomalies=anomalies,
    )
