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
  - Check 3 — Feature-Value Spot-Checks (Requirement 4)    [task 5.1]
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
