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
  - Check 4 — Score-Distribution Plausibility (Requirement 5) [this task]
  - CheckOutcome no-silent-passes contract (Requirement 11) [this task]

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
# Shared — the CheckOutcome no-silent-passes contract (Requirement 11)
# ===========================================================================
#
# Every AUTOMATED check headline exposes its result through a single structured
# `CheckOutcome(expected, observed, passed)` so the renderer can print all three
# and no check ever records a `pass` without a recorded observed value (11.1).
# The four check result classes below build their outcome(s) ON DEMAND from
# fields they already carry (see the `outcome` / `outcomes` / `cluster_outcome`
# / `correlation_outcome` accessors), so this contract is ADDITIVE: it never
# changes an existing dataclass constructor signature or breaks a caller/test
# that reads the raw fields (`n_upper_quartile`, `cluster_passed`, `corr_passed`,
# `assertions[].passed`, ...). Check 1 reports the Upper_Quartile count against
# the expectation (11.2); each Check 2 assertion reports observed eligibility /
# grid-membership (11.3); Check 4 reports the clustering and wind-correlation
# checks with their observed statistics (11.4). A failing outcome is surfaced
# here exactly as recorded, never overwritten or hidden (11.5). This is the
# reality-check stage only; the cross-domain structural checks remain in
# `pipeline/validate.py` and are NOT duplicated here (11.6).
#
# Check 3 (Feature-Value Spot-Checks) is deliberately NOT an automated pass/fail
# check — verification is a human-judgement item, so it emits no CheckOutcome
# (design §6). The observed values it records for the reviewer are carried on
# its own SpotCheckRow fields.


# The sentinel used when an observed value is genuinely absent/undefined and
# recorded HONESTLY as such (never as a silent pass). An outcome may carry this
# as its ``observed`` ONLY when ``passed`` is False, enforced in __post_init__.
OBSERVED_NONE = None


@dataclass(frozen=True)
class CheckOutcome:
    """
    The no-silent-passes contract for a single automated check (Requirement 11).

    Carries the ``expected`` outcome, the ``observed`` outcome, and the explicit
    ``passed`` pass/fail for one automated check headline, so the renderer can
    print all three and a reviewer can see WHY a check passed or failed (11.1).

    A pass is NEVER recorded without a recorded observed value: ``__post_init__``
    rejects ``passed=True`` when ``observed`` is ``None`` or an empty string
    (11.1). A FAIL may legitimately carry a ``None``/empty observed — an
    undefined or absent observation is itself an honest failing outcome and is
    surfaced, never hidden (11.5).

    ``label`` names the check headline (e.g. "Upper_Quartile count",
    "Sydney CBD exclusion", "Degenerate-clustering") so a rendered/serialised
    list of outcomes is self-describing. It defaults to an empty string for the
    minimal ``CheckOutcome(expected, observed, passed)`` shape named in the
    design.
    """

    expected: object  # the expected outcome (human-readable or structured)
    observed: object  # the observed outcome; may be None ONLY when passed=False
    passed: bool  # explicit pass/fail — never a pass without an observed value
    label: str = ""  # optional headline label for a self-describing outcome

    def __post_init__(self) -> None:
        # A pass MUST carry a recorded observed value. An empty string or None
        # observed alongside passed=True would be a silent pass (11.1).
        if self.passed:
            observed_is_empty = self.observed is None or (
                isinstance(self.observed, str) and self.observed.strip() == ""
            )
            if observed_is_empty:
                raise ValueError(
                    "CheckOutcome: a pass cannot be recorded without an observed "
                    f"value (label={self.label!r}, expected={self.expected!r}). "
                    "Record the observed value, or set passed=False."
                )


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

    @property
    def outcome(self) -> CheckOutcome:
        """
        The Check 1 headline as a :class:`CheckOutcome` (Requirements 11.1, 11.2).

        Reports the Upper_Quartile count against the expectation that MOST
        Known_Wind_Farms fall in the Upper_Quartile, with the observed count
        recorded (11.2). ``passed`` is True iff a strict majority of the known
        farms land in the Upper_Quartile (``n_upper_quartile > n_known_farms /
        2``); it is derived ON DEMAND from the already-recorded fields, so no
        pass is ever recorded without the observed count (11.1). With no known
        farms the observed count is recorded (0 of 0) and the outcome does NOT
        pass — there is nothing to confirm the expectation against.
        """
        passed = (
            self.n_known_farms > 0
            and self.n_upper_quartile > self.n_known_farms / 2.0
        )
        observed = (
            f"{self.n_upper_quartile} of {self.n_known_farms} known wind farms "
            f"in the Upper_Quartile "
            f"(proportion {self.proportion_upper_quartile:.3f})"
        )
        return CheckOutcome(
            expected=self.expectation,
            observed=observed,
            passed=passed,
            label="Upper_Quartile count",
        )


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

    @property
    def outcome(self) -> CheckOutcome:
        """
        This assertion as a :class:`CheckOutcome` (Requirements 3.4, 11.3).

        Exposes the already-recorded ``expected`` / ``observed`` / ``passed`` of
        one Exclusion_Validation assertion through the shared no-silent-passes
        contract, so the reporter can render observed eligibility / grid-
        membership as an explicit pass/fail with the observed value (11.3). The
        ``ExclusionAssertion`` constructor already guarantees an observed value
        is recorded for every assertion, so a pass here always carries an
        observed value (3.4, 11.1).
        """
        return CheckOutcome(
            expected=self.expected,
            observed=self.observed,
            passed=self.passed,
            label=f"{self.landmark} exclusion",
        )


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

    @property
    def outcomes(self) -> list[CheckOutcome]:
        """
        Every Check 2 assertion as a :class:`CheckOutcome` (Requirements 11.1, 11.3).

        One outcome per :class:`ExclusionAssertion` (landmark exclusions plus the
        offshore/ocean assertion), each reporting the observed eligibility /
        grid-membership as an explicit pass/fail with the observed value (11.3).
        A failing assertion is surfaced as a failing outcome, never hidden
        (11.5). Built ON DEMAND from ``assertions``, so no existing field or test
        (which read ``assertions[].passed``) is affected.
        """
        return [assertion.outcome for assertion in self.assertions]


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

# ===========================================================================
# Check 4 — Score-Distribution Plausibility (Requirement 5)
# ===========================================================================
#
# Over the Eligible_Cell population ONLY (5.1):
#   - report distribution statistics of suitability_score: min, max, mean, std,
#     and quartiles Q1 / median / Q3;
#   - compute the degenerate-clustering flag — the fraction of eligible scores
#     within CLUSTER_EPSILON of 0 or 1 — and flag the distribution degenerate
#     if that fraction EXCEEDS CLUSTER_FRACTION_THRESHOLD, reported as an
#     explicit pass/fail with the observed fraction (5.2);
#   - report the geographic diversity of the top-scoring cells (latitude range,
#     longitude range, and the REZs represented WHERE available), so a single-
#     region concentration is visible (5.3);
#   - compute the wind_speed-versus-suitability_score correlation (Spearman by
#     default, Pearson as a documented alternative) over eligible cells, with a
#     documented POSITIVE sign expectation; report — NOT enforce — it, with an
#     honest note when the sign is unexpected (5.4).
# A degenerate distribution or a non-positive correlation is reported HONESTLY
# as a CheckAnomaly with an investigation note; the model is NEVER adjusted to
# alter the distribution (5.5, 8.2, 8.3).

# The Integrated_Feature_Table column Check 4 correlates the score against
# (from config.REQUIRED_INTEGRATED_COLUMNS): the wind resource.
# (_INT_WIND_SPEED is defined in the Check 3 section above.)

# The check name recorded on every anomaly this check surfaces.
_DISTRIBUTION_CHECK_NAME = "Score-Distribution Plausibility"

# The default correlation method (Spearman is rank-based, so robust to the
# monotone-but-nonlinear relationship expected between wind and score).
CORR_METHOD_SPEARMAN = "spearman"
CORR_METHOD_PEARSON = "pearson"

# The fraction of the eligible population, ordered by descending score, treated
# as the "top-scoring cells" for the geographic-diversity report (5.3). A
# documented, deterministic rule: the highest-scoring decile, floored at a
# handful of cells so a tiny population still reports a range.
TOP_CELLS_FRACTION = 0.10
TOP_CELLS_MIN = 5

# Candidate column names a REZ label may travel under, checked in order. The
# grid/integrated frames do not currently carry a REZ column, so this is
# handled gracefully: absent -> reported as "not available", never fabricated
# (5.3).
_REZ_COLUMN_CANDIDATES = ("rez", "rez_name", "rez_id", "REZ")

# The documented positive sign expectation for the wind-vs-score correlation
# (5.4). wind_speed is a positively-weighted input criterion, so a higher wind
# resource is expected to correspond to a higher suitability_score.
_CORR_EXPECTATION = (
    "Higher wind resource is expected to correspond to a higher "
    "suitability_score (wind_speed is a positively-weighted input criterion), "
    "so the wind-versus-score correlation is expected to be POSITIVE."
)


@dataclass(frozen=True)
class DistributionCheckResult:
    """
    Structured result of Check 4 — Score-Distribution Plausibility (Req. 5).

    All statistics are computed over the Eligible_Cell population ONLY, so
    perturbing an Excluded_Cell value can never change them (5.1, Property 7).

    ``stats`` carries ``{"min","max","mean","std","q1","median","q3"}`` of
    ``suitability_score`` over the eligible population (5.1). ``cluster_fraction``
    is the observed fraction of eligible scores within ``CLUSTER_EPSILON`` of 0
    or 1; ``cluster_degenerate`` is ``True`` iff that fraction EXCEEDS
    ``CLUSTER_FRACTION_THRESHOLD``; ``cluster_passed`` is the explicit pass/fail
    (a NON-degenerate distribution passes) reported with the observed fraction
    (5.2, 11.4). ``top_lat_range`` / ``top_lon_range`` are the ``(min, max)``
    EPSG:4326 latitude/longitude of the top-scoring cells and ``rez_represented``
    lists the REZs among them WHERE available, so a single-region concentration
    is visible (5.3). ``wind_score_corr`` is the Spearman (default) or Pearson
    correlation between ``wind_speed`` and ``suitability_score`` over eligible
    cells, ``corr_method`` names which; ``corr_sign_expected_positive`` records
    the documented positive expectation and ``corr_passed`` whether the observed
    correlation is sensibly positive — REPORTED, never enforced (5.4).

    ``anomalies`` carries an honestly-recorded :class:`CheckAnomaly` for a
    degenerate distribution and/or a non-positive correlation, for task 8.1's
    ``collect_issues`` to gather; the model is NEVER adjusted to alter the
    distribution (5.5, 8.2, 8.3). ``n_eligible`` is the eligible-population size
    the statistics were computed over, and ``notes`` records honest caveats
    (e.g. an unavailable REZ column or an undefined correlation).
    """

    stats: dict
    cluster_fraction: float
    cluster_degenerate: bool
    cluster_passed: bool
    top_lat_range: tuple
    top_lon_range: tuple
    rez_represented: list
    wind_score_corr: float | None
    corr_method: str
    corr_sign_expected_positive: bool
    corr_passed: bool
    expectation: str = _CORR_EXPECTATION
    n_eligible: int = 0
    anomalies: list[CheckAnomaly] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def cluster_outcome(self) -> CheckOutcome:
        """
        The degenerate-clustering headline as a :class:`CheckOutcome` (11.1, 11.4).

        Reports the clustering check as an explicit pass/fail with the observed
        clustering fraction recorded (11.4). ``passed`` mirrors ``cluster_passed``
        (a NON-degenerate distribution passes); the observed value is always the
        recorded ``cluster_fraction``, so no pass is recorded without an observed
        statistic (11.1). Built ON DEMAND from the already-recorded fields.
        """
        observed = (
            f"{self.cluster_fraction:.4f} of eligible scores within "
            f"{config.CLUSTER_EPSILON:g} of 0 or 1 "
            f"(threshold {config.CLUSTER_FRACTION_THRESHOLD:g}); "
            f"degenerate={self.cluster_degenerate}"
        )
        expected = (
            f"at most {config.CLUSTER_FRACTION_THRESHOLD:g} of eligible scores "
            f"clustered within {config.CLUSTER_EPSILON:g} of 0 or 1 "
            f"(a non-degenerate distribution)"
        )
        return CheckOutcome(
            expected=expected,
            observed=observed,
            passed=self.cluster_passed,
            label="Degenerate-clustering",
        )

    @property
    def correlation_outcome(self) -> CheckOutcome:
        """
        The wind-versus-score correlation headline as a :class:`CheckOutcome`.

        Reports the correlation check as an explicit pass/fail with the observed
        correlation statistic recorded (Requirements 11.1, 11.4). ``passed``
        mirrors ``corr_passed`` (a sensibly POSITIVE correlation passes). The
        correlation is REPORTED against the documented positive expectation, not
        enforced (5.4): an undefined correlation (``wind_score_corr is None``) is
        an honest FAIL that carries its observed state ("undefined ..."), so it is
        surfaced rather than silently passed (11.1, 11.5). Built ON DEMAND from
        the already-recorded fields.
        """
        if self.wind_score_corr is None:
            observed = (
                f"undefined {self.corr_method} correlation "
                f"(insufficient data or zero variance)"
            )
        else:
            observed = (
                f"{self.corr_method} correlation "
                f"{self.wind_score_corr:+.4f} over {self.n_eligible} eligible cells"
            )
        return CheckOutcome(
            expected=self.expectation,
            observed=observed,
            passed=self.corr_passed,
            label="Wind-versus-score correlation",
        )


def _rank_average(values: np.ndarray) -> np.ndarray:
    """
    Average (fractional) ranks of ``values``, ties sharing the mean rank.

    Matches ``scipy.stats.rankdata(values, method="average")`` using only numpy,
    so Spearman can be computed when scipy is unavailable (the venv does not
    ship scipy). PURE.
    """
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(values.size, dtype=float)
    ranks[order] = np.arange(1, values.size + 1, dtype=float)
    # Average the ranks within each group of tied values.
    sorted_vals = values[order]
    i = 0
    n = sorted_vals.size
    while i < n:
        j = i + 1
        while j < n and sorted_vals[j] == sorted_vals[i]:
            j += 1
        if j - i > 1:
            avg = (i + 1 + j) / 2.0  # mean of ranks (i+1)..j
            ranks[order[i:j]] = avg
        i = j
    return ranks


def _correlation(x: np.ndarray, y: np.ndarray, method: str) -> float | None:
    """
    Correlation of ``x`` and ``y`` (``spearman`` default, or ``pearson``).

    Uses ``scipy.stats`` WHERE available (matching the pipeline's stated scipy
    usage in ``integration/analyse.py``), and falls back to a pure-numpy
    implementation otherwise — the venv does not currently ship scipy, so the
    numpy path is the live one. Spearman is Pearson on average ranks. Returns
    ``None`` (an undefined correlation, reported honestly) when fewer than two
    points remain or either input has zero variance, rather than emitting a
    spurious value. PURE.
    """
    if x.size < 2 or y.size < 2:
        return None

    if method == CORR_METHOD_SPEARMAN:
        try:
            from scipy import stats as _scipy_stats  # type: ignore

            rho = _scipy_stats.spearmanr(x, y).correlation
            return None if rho is None or np.isnan(rho) else float(rho)
        except Exception:
            # Pure-numpy Spearman: Pearson correlation of the average ranks.
            xr = _rank_average(x)
            yr = _rank_average(y)
            return _correlation(xr, yr, CORR_METHOD_PEARSON)

    # Pearson.
    if np.std(x) == 0.0 or np.std(y) == 0.0:
        return None
    try:
        from scipy import stats as _scipy_stats  # type: ignore

        r = _scipy_stats.pearsonr(x, y)[0]
        return None if r is None or np.isnan(r) else float(r)
    except Exception:
        matrix = np.corrcoef(x, y)
        r = matrix[0, 1]
        return None if np.isnan(r) else float(r)


def _find_rez_column(frame: pd.DataFrame) -> str | None:
    """Return the first present REZ-label column, or ``None`` if absent (5.3)."""
    for candidate in _REZ_COLUMN_CANDIDATES:
        if candidate in frame.columns:
            return candidate
    return None


def check_distribution(
    eligible: pd.DataFrame, corr_method: str = CORR_METHOD_SPEARMAN
) -> DistributionCheckResult:
    """
    Check 4 — characterise the eligible score distribution and its plausibility.

    PURE. Over the Eligible_Cell population ONLY (Requirement 5.1):

      1. Report distribution statistics of ``suitability_score`` — ``min``,
         ``max``, ``mean``, ``std``, and quartiles ``q1`` / ``median`` / ``q3``
         (5.1). Computed over the eligible frame the caller supplies, so
         Excluded_Cell values can never enter (Property 7).
      2. Compute the degenerate-clustering flag: the fraction of eligible scores
         within ``config.CLUSTER_EPSILON`` of 0 or 1. The distribution is
         degenerate iff that fraction EXCEEDS ``config.CLUSTER_FRACTION_THRESHOLD``.
         Report it as an explicit pass/fail (a non-degenerate distribution
         PASSES) alongside the observed fraction (5.2, 11.4).
      3. Report the geographic diversity of the top-scoring cells — the
         ``(min, max)`` latitude and longitude of the highest-scoring cells, and
         the REZs represented WHERE a REZ column is available — so a single-
         region concentration is visible (5.3). Centroids/REZ are read WHERE the
         caller joined them from the grid; absent, they are reported honestly as
         "not available", never fabricated.
      4. Compute the ``wind_speed``-versus-``suitability_score`` correlation
         (Spearman by default, Pearson as the documented alternative) over
         eligible cells, with the documented POSITIVE sign expectation. Report
         it — NOT enforce it — with an honest note when the sign is unexpected
         (5.4). ``wind_speed`` is read WHERE the caller joined it from the
         Integrated_Feature_Table; absent, the correlation is ``None`` with a
         note.

    A degenerate distribution and/or a non-positive (or undefined) correlation
    is recorded HONESTLY as a :class:`CheckAnomaly` with an investigation note
    distinguishing a likely data issue from a legitimate model result; the model
    is NEVER adjusted to alter the distribution (5.5, 8.2, 8.3).

    Args:
        eligible: the Eligible_Cell frame (non-null ``suitability_score`` AND
            ``rank``), carrying at least ``cell_id`` and ``suitability_score``.
            WHERE the caller has joined them, ``centroid_lat`` / ``centroid_lon``
            (from the Analysis_Grid) enable the geographic-diversity report and
            ``wind_speed`` (from the Integrated_Feature_Table) enables the
            correlation; an optional REZ column enables the REZ list. Any of
            these that are absent are reported honestly rather than fabricated.
        corr_method: ``"spearman"`` (default) or ``"pearson"``.

    Returns:
        A :class:`DistributionCheckResult`.

    Raises:
        ValueError: if the eligible population is empty — distribution
            statistics over zero eligible cells are undefined, and silently
            returning zeros would be a lie.
    """
    if corr_method not in (CORR_METHOD_SPEARMAN, CORR_METHOD_PEARSON):
        raise ValueError(
            f"check_distribution: unknown correlation method {corr_method!r}; "
            f"expected {CORR_METHOD_SPEARMAN!r} or {CORR_METHOD_PEARSON!r}."
        )

    scores = eligible[_SCORE].to_numpy(dtype=float)
    scores = scores[~np.isnan(scores)]
    n_eligible = scores.size
    if n_eligible == 0:
        raise ValueError(
            "check_distribution: the eligible population is empty; distribution "
            "statistics over zero eligible cells are undefined."
        )

    notes: list[str] = []
    anomalies: list[CheckAnomaly] = []

    # --- 1. Distribution statistics over the eligible population only (5.1) ---
    q1, median, q3 = (float(v) for v in np.percentile(scores, [25.0, 50.0, 75.0]))
    stats = {
        "min": float(np.min(scores)),
        "max": float(np.max(scores)),
        "mean": float(np.mean(scores)),
        # Population std (ddof=0) — a descriptive spread of the whole eligible
        # population, not an inferential sample estimate.
        "std": float(np.std(scores)),
        "q1": q1,
        "median": median,
        "q3": q3,
    }

    # --- 2. Degenerate-clustering flag (5.2) ---
    near_zero = np.abs(scores - 0.0) <= config.CLUSTER_EPSILON
    near_one = np.abs(scores - 1.0) <= config.CLUSTER_EPSILON
    cluster_fraction = float(np.count_nonzero(near_zero | near_one) / n_eligible)
    cluster_degenerate = cluster_fraction > config.CLUSTER_FRACTION_THRESHOLD
    cluster_passed = not cluster_degenerate

    if cluster_degenerate:
        anomalies.append(
            CheckAnomaly(
                check=_DISTRIBUTION_CHECK_NAME,
                description=(
                    f"Score distribution is degenerately clustered: "
                    f"{cluster_fraction:.1%} of eligible scores lie within "
                    f"{config.CLUSTER_EPSILON:g} of 0 or 1, exceeding the "
                    f"{config.CLUSTER_FRACTION_THRESHOLD:.0%} threshold."
                ),
                kind=ANOMALY_MODEL_RESULT,
                investigation_note=(
                    "Distinguish a DATA issue from a MODEL result: heavy "
                    "clustering at the extremes usually points to a "
                    "normalisation bound collapsing the range or a criterion "
                    "saturating, rather than a genuine bimodal landscape. "
                    "Investigate the normalisation and criterion inputs; the "
                    "model is never adjusted to spread the distribution."
                ),
            )
        )

    # --- 3. Geographic diversity of the top-scoring cells (5.3) ---
    n_top = max(TOP_CELLS_MIN, int(np.ceil(n_eligible * TOP_CELLS_FRACTION)))
    n_top = min(n_top, n_eligible)
    # Deterministic top selection: descending score, cell_id tie-break.
    top_sort_cols = [_SCORE]
    top_ascending = [False]
    if _CELL_ID in eligible.columns:
        top_sort_cols.append(_CELL_ID)
        top_ascending.append(True)
    top_cells = eligible.sort_values(
        by=top_sort_cols, ascending=top_ascending, kind="mergesort"
    ).head(n_top)

    has_lat = _CENTROID_LAT in top_cells.columns
    has_lon = _CENTROID_LON in top_cells.columns

    if has_lat:
        lat_vals = top_cells[_CENTROID_LAT].to_numpy(dtype=float)
        lat_vals = lat_vals[~np.isnan(lat_vals)]
    else:
        lat_vals = np.array([], dtype=float)
    if has_lon:
        lon_vals = top_cells[_CENTROID_LON].to_numpy(dtype=float)
        lon_vals = lon_vals[~np.isnan(lon_vals)]
    else:
        lon_vals = np.array([], dtype=float)

    if lat_vals.size:
        top_lat_range = (float(np.min(lat_vals)), float(np.max(lat_vals)))
    else:
        top_lat_range = (None, None)
        notes.append(
            "Top-cell latitude range not available: no centroid_lat column was "
            "joined from the Analysis_Grid."
        )
    if lon_vals.size:
        top_lon_range = (float(np.min(lon_vals)), float(np.max(lon_vals)))
    else:
        top_lon_range = (None, None)
        notes.append(
            "Top-cell longitude range not available: no centroid_lon column was "
            "joined from the Analysis_Grid."
        )

    rez_column = _find_rez_column(top_cells)
    if rez_column is not None:
        rez_represented = sorted(
            {
                str(v)
                for v in top_cells[rez_column].tolist()
                if v is not None and not (isinstance(v, float) and np.isnan(v))
            }
        )
    else:
        rez_represented = []
        notes.append(
            "REZs represented among the top cells not available: no REZ column "
            "is present on the eligible/grid frame."
        )

    # --- 4. Wind-versus-score correlation (5.4) — reported, NOT enforced ---
    corr_sign_expected_positive = True
    if _INT_WIND_SPEED in top_cells.columns or _INT_WIND_SPEED in eligible.columns:
        paired = eligible[[_INT_WIND_SPEED, _SCORE]].to_numpy(dtype=float)
        finite = ~np.isnan(paired).any(axis=1)
        paired = paired[finite]
        wind_vals = paired[:, 0]
        score_vals = paired[:, 1]
        wind_score_corr = _correlation(wind_vals, score_vals, corr_method)
    else:
        wind_score_corr = None
        notes.append(
            "Wind-versus-score correlation not available: no wind_speed column "
            "was joined from the Integrated_Feature_Table."
        )

    if wind_score_corr is None:
        # Undefined correlation (missing wind_speed, <2 points, or zero
        # variance) — reported honestly, not enforced. It does NOT pass the
        # positive expectation, but it fails the run only if we chose to enforce
        # it — which we do NOT (5.4, 5.5).
        corr_passed = False
        notes.append(
            "Wind-versus-score correlation is undefined (insufficient data or "
            "zero variance); reported honestly, not enforced."
        )
    else:
        corr_passed = wind_score_corr > 0.0

    if wind_score_corr is not None and not corr_passed:
        anomalies.append(
            CheckAnomaly(
                check=_DISTRIBUTION_CHECK_NAME,
                description=(
                    f"Wind-versus-score correlation is {wind_score_corr:+.3f} "
                    f"({corr_method}), which is NOT sensibly positive against "
                    f"the documented positive expectation."
                ),
                kind=ANOMALY_MODEL_RESULT,
                investigation_note=(
                    "Distinguish a DATA issue from a MODEL result: wind_speed is "
                    "a positively-weighted criterion, so a non-positive "
                    "wind-versus-score correlation is surprising. Check the "
                    "wind_speed join and the criterion weighting/normalisation "
                    "for a sign or column mix-up before concluding the model is "
                    "wrong. Reported honestly; the model is never adjusted to "
                    "flip the correlation."
                ),
            )
        )

    return DistributionCheckResult(
        stats=stats,
        cluster_fraction=cluster_fraction,
        cluster_degenerate=cluster_degenerate,
        cluster_passed=cluster_passed,
        top_lat_range=top_lat_range,
        top_lon_range=top_lon_range,
        rez_represented=rez_represented,
        wind_score_corr=wind_score_corr,
        corr_method=corr_method,
        corr_sign_expected_positive=corr_sign_expected_positive,
        corr_passed=corr_passed,
        expectation=_CORR_EXPECTATION,
        n_eligible=n_eligible,
        anomalies=anomalies,
        notes=notes,
    )
