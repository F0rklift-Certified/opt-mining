"""
Typed data models the Decision_Service operations return (S2-08, CONTRACT.md §5).

These are plain, transport-agnostic dataclasses so the operation functions stay
unit-testable without the FastAPI layer (a later task maps each to an HTTP
endpoint and re-declares them as Pydantic models for the OpenAPI schema — the
OpenAPI schema, not this module, is the authoritative machine-readable form per
CONTRACT.md §5). None of them carries decision logic: they are the shapes the
service serves, populated verbatim from materialised engine outputs.

`RunHandle` is needed by `run_analysis` (task 2.1), `RankedRow` by
`get_ranked_results` (task 3.1), `SiteDetail` by `get_site_detail` (task 3.2)
and `ExcludedRow` by `get_exclusions` (task 3.3); `CellFeature` / `CellCollection`
by `get_run_cells` (the v1.1 geometry operation, CONTRACT.md §4.7);
`ScenarioComparison` / `ScenarioComparisonRow` by `compare_scenarios` (task 5.1);
`DataQualityStatus` / `DataQualityCheck` by `get_data_quality` (task 5.2).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RunHandle:
    """
    Identifies one materialised Run of the decision engine (CONTRACT.md §5).

    A Run is "execute the S2-05 scoring engine with these weights and
    materialise the outputs" (design.md). The handle is what the
    `GET /runs/{run_id}/...` read operations key on.

    Fields
    ------
    run_id :
        Identifier for the materialised Run, used in the read-operation paths.
        Content-derived from the resolved weights so that re-running the same
        weights (or the same scenario) resolves to the same Run rather than
        proliferating identical materialisations.
    weights_id :
        Stable identifier of the weight set used — the scenario key for a
        scenario Run, or a content-derived id (the SHA-256 of the resolved
        weights YAML) for an explicit-weights Run. This is the traceable
        weights identity the engine's method report and manifest also record.
    scenario :
        The named Scenario key when the Run was launched from one; ``None`` for
        an explicit-weights Run.
    """

    run_id: str
    weights_id: str
    scenario: str | None = None

    def to_dict(self) -> dict:
        """Serialise to the CONTRACT.md §5 `RunHandle` shape."""
        return {
            "run_id": self.run_id,
            "weights_id": self.weights_id,
            "scenario": self.scenario,
        }


@dataclass(frozen=True)
class RankedRow:
    """
    One eligible cell's ranked result for a Run (CONTRACT.md §5, Requirement 6.3).

    A `RankedRow` is a verbatim projection of one row of the materialised
    S2-05 Scored_Table — never a recomputed value. `get_ranked_results`
    (`results.py`) reads the fixed Scored_Table and returns one `RankedRow`
    per eligible cell (a non-null `suitability_score` and `rank`); an excluded
    cell (null score / null rank) never becomes a `RankedRow`. The service
    performs no scoring, normalisation or ranking to produce these — the score
    and rank are the engine's, carried through unchanged (CONTRACT.md §1,
    Requirement 2.4).

    Fields
    ------
    cell_id :
        Analysis-cell id, copied byte-for-byte from the Scored_Table so it
        joins back to the analysis grid on `cell_id`.
    suitability_score :
        The S2-05 `suitability_score` in ``[0, 1]``, read from the table
        (never recomputed).
    rank :
        The S2-05 integer `rank` (1 = highest-ranked), read from the table and
        preserved under any Display_Filter (Requirement 3.2).
    key_components :
        The per-criterion component values for the cell — the `contrib_{feature}`
        shares from the Scored_Table — keyed by criterion `feature` (the
        `contrib_` prefix stripped). These sum to `suitability_score` within
        the engine's reconciliation tolerance; the service copies them through,
        it does not compute them.
    """

    cell_id: str
    suitability_score: float
    rank: int
    key_components: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialise to the CONTRACT.md §5 `RankedRow` shape."""
        return {
            "cell_id": self.cell_id,
            "suitability_score": self.suitability_score,
            "rank": self.rank,
            "key_components": dict(self.key_components),
        }


@dataclass(frozen=True)
class SiteDetail:
    """
    One cell's full detail for a Run (CONTRACT.md §5, Requirement 1.3, 6.2, 6.3).

    A `SiteDetail` is assembled ENTIRELY from materialised engine outputs — it
    is never recomputed (CONTRACT.md §1, Requirement 2.4). Its three sources are:

    * the Run's S2-05 Scored_Table — the `suitability_score`, `rank` and the
      per-criterion `contrib_{feature}` contributions, read from the SAME table
      `get_ranked_results` reads, so the two operations agree for a `cell_id`
      (the consistency guarantee, Requirement 2.3 / Property P1);
    * the S1-08 integrated feature table the Run scored — the cell's input
      `features` and its S2-03 `eligible` flag;
    * the S2-06 explanation output — the `explanation` (Explanation_Structure),
      carried through VERBATIM (its fields are neither renamed nor reordered,
      CONTRACT.md §5).

    Fields
    ------
    cell_id :
        Analysis-cell id, copied verbatim so it joins back to the grid.
    features :
        The cell's input feature values (e.g. ``wind_speed``,
        ``dist_transmission_km``, ``slope_deg``, ``inside_rez``), read from the
        integrated table the Run scored. Carried through unchanged.
    contributions :
        The per-criterion contribution shares (``contrib_{feature}``) from the
        Scored_Table, keyed by criterion `feature` (the ``contrib_`` prefix
        stripped). For an eligible cell these sum to ``suitability_score``
        within the engine's reconciliation tolerance; the service copies them
        through, it does not compute them. A null contribution (a criterion
        with no value for the cell) is omitted rather than fabricated as 0.0.
    suitability_score :
        The S2-05 score in ``[0, 1]``; IDENTICAL to what `get_ranked_results`
        returns for this cell in this Run (Requirement 2.3). ``None`` for an
        excluded cell (which carries no score).
    rank :
        The S2-05 integer rank (1 = highest-ranked); IDENTICAL to
        `get_ranked_results`. ``None`` for an excluded cell (which carries no
        rank).
    eligible :
        Whether the cell passed the S2-03 hard exclusions, read from the
        integrated table's `eligible` flag.
    explanation :
        The S2-06 Explanation_Structure for the cell, carried through verbatim
        (the eligible-path or excluded-path record exactly as S2-06 wrote it).
    demand_load_mva :
        DISPLAY-ONLY estimate of the network load within the demand decay radius
        for the cell, in MVA — the raw sum of zone-substation max demand over the
        substations within the configured search radius of the cell centroid,
        read verbatim from the integrated table's ``load_within_radius_mva``
        column. It is an informational ESTIMATE of nearby network load (not
        demand AT the cell, not spare capacity) and is NEVER an input to
        ``demand_proxy``, the composite score or the rank. ``None`` when the
        column is absent/null (a non-load_weighted Run, or a cell with no nearby
        substation under an older integrated table).
    """

    cell_id: str
    features: dict[str, Any] = field(default_factory=dict)
    contributions: dict[str, float] = field(default_factory=dict)
    suitability_score: float | None = None
    rank: int | None = None
    eligible: bool = False
    explanation: dict[str, Any] = field(default_factory=dict)
    demand_load_mva: float | None = None

    def to_dict(self) -> dict:
        """Serialise to the CONTRACT.md §5 `SiteDetail` shape."""
        return {
            "cell_id": self.cell_id,
            "features": dict(self.features),
            "contributions": dict(self.contributions),
            "suitability_score": self.suitability_score,
            "rank": self.rank,
            "eligible": self.eligible,
            "explanation": dict(self.explanation),
            "demand_load_mva": self.demand_load_mva,
        }


@dataclass(frozen=True)
class ExcludedRow:
    """
    One excluded cell's eligibility reason(s) for a Run (CONTRACT.md §5,
    Requirement 1.4).

    An `ExcludedRow` is a verbatim projection of one EXCLUDED row of the S2-03
    Eligibility_Table — never a recomputed value. `get_exclusions`
    (`results.py`) reads the materialised Eligibility_Table and returns one
    `ExcludedRow` per cell the engine flagged ineligible (`eligible == False`);
    an eligible cell never becomes an `ExcludedRow`. The service performs no
    exclusion arithmetic — the codes and text are the engine's, carried through
    unchanged (CONTRACT.md §1, Requirement 2.4).

    Both the machine-readable `reason_codes` and the human-readable
    `reason_text` are derived from the SAME `exclusion_reasons` JSON pairs the
    exclusions stage wrote (a list of ``{"code", "text"}`` produced from one
    rule evaluation), so the two forms of an `ExcludedRow` can never disagree
    with each other or with the engine's `triggered_rules` / `exclusion_reason`
    columns.

    Fields
    ------
    cell_id :
        Analysis-cell id, copied verbatim from the Eligibility_Table so it
        joins back to the analysis grid on `cell_id`.
    reason_codes :
        The machine-readable exclusion rule codes for the cell — the
        `exclusion_reasons[].code` (equivalently `triggered_rules`) vocabulary
        from S2-03 (Decision_Engine_Spec §6 / F16), in rule-config order. A
        cell can carry more than one code.
    reason_text :
        The human-readable reason(s) for the cell — the
        `exclusion_reasons[].text` values joined in rule-config order with the
        exclusions stage's own reason delimiter, identical to the engine's
        `exclusion_reason` column.
    """

    cell_id: str
    reason_codes: list[str] = field(default_factory=list)
    reason_text: str = ""

    def to_dict(self) -> dict:
        """Serialise to the CONTRACT.md §5 `ExcludedRow` shape."""
        return {
            "cell_id": self.cell_id,
            "reason_codes": list(self.reason_codes),
            "reason_text": self.reason_text,
        }


@dataclass(frozen=True)
class CellFeature:
    """
    One analysis cell's map feature for a Run (CONTRACT.md §5, Requirement 1.7).

    A `CellFeature` is a verbatim projection of one row of the materialised
    S2-05 Scored_Table into a GeoJSON Point Feature — never a recomputed value.
    `get_run_cells` (`results.py`) reads the fixed Scored_Table and builds one
    `CellFeature` per cell (eligible AND excluded alike), carrying the grid
    centroid through unchanged. The service performs no scoring, ranking or
    reprojection to produce these: the centroid is the engine's own
    `centroid_lat`/`centroid_lon` in EPSG:4326, and the score/rank are read
    from the table (null for an excluded cell). `eligible` is the IDENTICAL
    predicate `get_ranked_results` uses — a non-null `suitability_score` AND a
    non-null `rank` — so the eligible set equals the ranked-table set
    (CONTRACT.md §1, §7 P1, Requirement 2.4).

    Fields
    ------
    cell_id :
        Analysis-cell id, copied byte-for-byte from the Scored_Table so it
        joins back to the analysis grid on `cell_id`.
    centroid_lon :
        The cell centroid's longitude in EPSG:4326, carried through verbatim
        (the `centroid_lon` the engine wrote); no reprojection.
    centroid_lat :
        The cell centroid's latitude in EPSG:4326, carried through verbatim
        (the `centroid_lat` the engine wrote); no reprojection.
    eligible :
        Whether the cell is eligible — ``suitability_score`` AND ``rank`` both
        non-null, the identical rule `get_ranked_results` applies.
    suitability_score :
        The S2-05 `suitability_score`, read from the table; ``None`` for an
        excluded cell (which carries no score).
    rank :
        The S2-05 integer `rank`, read from the table; ``None`` for an excluded
        cell (which carries no rank).
    """

    cell_id: str
    centroid_lon: float
    centroid_lat: float
    eligible: bool
    suitability_score: float | None = None
    rank: int | None = None

    def to_dict(self) -> dict:
        """Serialise to the CONTRACT.md §5 GeoJSON `CellFeature` shape."""
        return {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [self.centroid_lon, self.centroid_lat],
            },
            "properties": {
                "cell_id": self.cell_id,
                "eligible": self.eligible,
                "suitability_score": self.suitability_score,
                "rank": self.rank,
            },
        }


@dataclass(frozen=True)
class CellCollection:
    """
    A Run's cells as a GeoJSON FeatureCollection (CONTRACT.md §5, Requirement 1.7).

    A `CellCollection` is a verbatim projection of the materialised S2-05
    Scored_Table — one Point Feature per cell, carrying each cell's centroid in
    EPSG:4326 unchanged. `get_run_cells` (`results.py`) builds it; the service
    performs no scoring, ranking or reprojection (CONTRACT.md §1, Requirement
    2.4). The map the Web_Application renders from this collection and the
    ranking table are therefore the SAME engine output: the set of `eligible`
    Features equals the set `get_ranked_results` returns for the Run (§7 P1).

    Fields
    ------
    run_id :
        Identifier of the materialised Run these cells belong to.
    features :
        One `CellFeature` per Scored_Table row, in the table's own row order,
        carried through verbatim.
    score_quantiles :
        Display metadata for the map's colour scale (added v1.2.2, S4-02): the
        eligible population's `suitability_score` at each probability in
        `config.MAP_SCORE_QUANTILES`, as ``(quantile, suitability_score)``
        pairs in ascending quantile order. A descriptive statistic of the
        engine's own scores — it changes no score, rank or eligibility — served
        so the UI can place its colour stops without sorting (scope guard).
        Empty when the Run has no eligible cell.
    """

    run_id: str
    features: list[CellFeature] = field(default_factory=list)
    score_quantiles: list[tuple[float, float]] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialise to the CONTRACT.md §5 GeoJSON `CellCollection` shape."""
        return {
            "type": "FeatureCollection",
            "run_id": self.run_id,
            "features": [feature.to_dict() for feature in self.features],
            "score_quantiles": [
                {"quantile": quantile, "suitability_score": score}
                for quantile, score in self.score_quantiles
            ],
        }


@dataclass(frozen=True)
class ScenarioComparisonRow:
    """
    One cell's rank comparison across two Scenarios (CONTRACT.md §5,
    Requirement 1.5).

    A `ScenarioComparisonRow` is assembled from the ranks of TWO materialised
    Runs — one per Scenario, each produced by the S2-05 engine (never a second
    scorer, Property P5 / Requirement 4.3). The service performs no scoring or
    ranking to produce it; the two ranks are the engine's, read from each Run's
    Scored_Table via `get_ranked_results`. The only arithmetic is the display
    convenience `rank_delta = rank_a - rank_b` — a difference of two engine
    ranks, not a re-derivation of either.

    Fields
    ------
    cell_id :
        Analysis-cell id, copied verbatim so it joins back to the grid. The
        same `cell_id` identifies the cell under both Scenarios (the two Runs
        score the same eligible population).
    rank_a :
        The cell's S2-05 rank under `scenario_a` (1 = highest-ranked), read from
        that Run's Scored_Table. ``None`` when the cell is not eligible/ranked
        under `scenario_a`.
    rank_b :
        The cell's S2-05 rank under `scenario_b`, read from that Run's
        Scored_Table. ``None`` when the cell is not eligible/ranked under
        `scenario_b`.
    rank_delta :
        ``rank_a - rank_b`` when BOTH ranks are present; ``None`` otherwise
        (CONTRACT.md §5). A negative delta means the cell ranks BETTER (a lower,
        i.e. more favourable, rank number) under `scenario_a` than under
        `scenario_b`; a positive delta means it ranks better under `scenario_b`.
    """

    cell_id: str
    rank_a: int | None = None
    rank_b: int | None = None
    rank_delta: int | None = None

    def to_dict(self) -> dict:
        """Serialise to the CONTRACT.md §5 `ScenarioComparisonRow` shape."""
        return {
            "cell_id": self.cell_id,
            "rank_a": self.rank_a,
            "rank_b": self.rank_b,
            "rank_delta": self.rank_delta,
        }


@dataclass(frozen=True)
class ScenarioComparison:
    """
    A per-cell rank comparison of two named Scenarios (CONTRACT.md §5,
    Requirement 1.5, 4.3).

    A `ScenarioComparison` is the result of `compare_scenarios`
    (`scenarios.py`): it materialises each Scenario as its own S2-05 Run and
    reads the two ranks per cell, so a rank change is attributable PURELY to the
    weight difference — the two Runs share the same criteria, directions and
    eligible-population normalisation bounds (CONTRACT.md §3, §4.5). The service
    runs no second scorer; each scenario's ranks are the engine's, reused via
    the Run store and `get_ranked_results` (Property P5).

    Fields
    ------
    labels :
        The two Scenario keys compared, as ``{"a": scenario_a, "b":
        scenario_b}`` (CONTRACT.md §5), so the consumer can label the two rank
        columns without re-deriving which side is which.
    rows :
        One `ScenarioComparisonRow` per cell that is eligible/ranked under at
        least one of the two Scenarios, ordered by ascending `rank_a` (the
        `scenario_a` ranking), with cells ranked only under `scenario_b` (no
        `rank_a`) following in ascending `rank_b` order. A cell excluded under
        both Scenarios takes no part.
    """

    labels: dict[str, str] = field(default_factory=dict)
    rows: list[ScenarioComparisonRow] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialise to the CONTRACT.md §5 `ScenarioComparison` shape."""
        return {
            "labels": dict(self.labels),
            "rows": [row.to_dict() for row in self.rows],
        }


@dataclass(frozen=True)
class DataQualityCheck:
    """
    One S2-02 input-contract check record (CONTRACT.md §5, Requirement 6.2, 6.3).

    A `DataQualityCheck` is a verbatim projection of one Check_Record the S2-02
    validator (`pipeline/validate.py`) wrote to the Validation_Result JSON
    sidecar — the exact ``{name, expected, observed, passed}`` shape the
    validator emits (`build_validation_result`), carried through UNCHANGED. The
    service performs NO validation of its own; it re-runs no check and re-derives
    no verdict (CONTRACT.md §1, Requirement 2). Every check is surfaced — passing
    and failing alike — so there are no silent passes (CONTRACT.md §5).

    Fields
    ------
    name :
        The check name, copied verbatim (e.g. "Baseline hash matches the frozen
        reference", "At least one Eligible_Cell").
    expected :
        The expected value/condition the validator recorded, as a string.
    observed :
        The observed value the validator recorded, as a string.
    passed :
        Whether this individual check passed. A ``False`` here is a failing
        blocking check that a data-quality banner should surface (Requirement
        5.2).
    """

    name: str
    expected: str
    observed: str
    passed: bool

    def to_dict(self) -> dict:
        """Serialise to the CONTRACT.md §5 `DataQualityCheck` shape."""
        return {
            "name": self.name,
            "expected": self.expected,
            "observed": self.observed,
            "passed": self.passed,
        }


@dataclass(frozen=True)
class DataQualityStatus:
    """
    The S2-02 Data_Quality_Status for the frozen integrated dataset
    (CONTRACT.md §5, Requirement 1.6, 5.1, 5.2, 5.3, 6.2, 6.3).

    A `DataQualityStatus` mirrors the S2-02 machine-readable Validation_Result
    (`integrated_input_validation.json`) the S2-02 validator materialised: the
    overall ``all_passed`` verdict and the per-check records, carried through
    UNCHANGED. `get_data_quality` (`quality.py`) reads that sidecar and projects
    it into this shape — it performs no validation, re-runs no check and
    re-derives no verdict (CONTRACT.md §1, Requirement 2). This is how the
    Web_Application learns the frozen dataset failed a blocking check so it can
    render a data-quality banner (Requirement 5.2), and the mechanism by which a
    Run derived from a failed dataset never hides its failure — the failure is
    always retrievable here (Requirement 5.3).

    Fields
    ------
    passed :
        The overall verdict — the S2-02 ``all_passed`` (the conjunction of every
        input-contract Check_Record, including the baseline-hash match), carried
        through unchanged. ``False`` means the frozen dataset failed a blocking
        check and the Web_Application should show a data-quality banner
        (Requirement 5.2).
    checks :
        The per-check records, one ``DataQualityCheck`` per S2-02 Check_Record,
        in the validator's own order. Every check is surfaced — no silent passes
        (CONTRACT.md §5).
    """

    passed: bool
    checks: list[DataQualityCheck] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialise to the CONTRACT.md §5 `DataQualityStatus` shape."""
        return {
            "passed": self.passed,
            "checks": [check.to_dict() for check in self.checks],
        }


@dataclass(frozen=True)
class SanityCheckItem:
    """
    One normalised sanity-check outcome (S3-08, CONTRACT.md §5).

    A `SanityCheckItem` is a verbatim projection of one `{label, expected,
    observed, passed}` outcome block the S1-12 sanity stage wrote to the
    Results_Sidecar (the Upper_Quartile and top-band known-wind-farm outcomes,
    the clustering/correlation/REZ distribution outcomes, and the synthesized
    exclusion summary). `get_sanity_check` (`sanity.py`) reads those blocks and
    projects each into this shape; it performs no sanity check of its own and
    re-derives no verdict (CONTRACT.md §1, Requirement 2). Every check is
    surfaced — passing and failing alike — so there are no silent passes
    (CONTRACT.md §5): an ABSENT check block is projected as a visible honest
    failure (`passed=False`, `observed="not available"`), never omitted.

    Fields
    ------
    name :
        The check label, copied verbatim (e.g. "Upper_Quartile count",
        "Known-wind-farm top-ranked band", "Exclusion validation").
    expected :
        The expected value/condition the sanity stage recorded, as a string.
    observed :
        The observed value the sanity stage recorded, as a string.
    passed :
        Whether this individual check passed (the sanity stage's own verdict).
    """

    name: str
    expected: str
    observed: str
    passed: bool

    def to_dict(self) -> dict:
        """Serialise to the CONTRACT.md §5 `SanityCheckItem` shape."""
        return {
            "name": self.name,
            "expected": self.expected,
            "observed": self.observed,
            "passed": self.passed,
        }


@dataclass(frozen=True)
class SanityContradiction:
    """
    One documented sanity contradiction / issue (S3-08, CONTRACT.md §5).

    A `SanityContradiction` is a verbatim projection of one entry in the S1-12
    Results_Sidecar's `issues_for_sprint_2` list — the superset of anomalies
    across all four plausibility checks (a known farm on excluded/low-ranked
    land, a clustering/correlation anomaly, a spot-value anomaly). The service
    carries each entry through unchanged, inventing no new investigation note
    (CONTRACT.md §1). The `check` label identifies which plausibility check
    raised the contradiction so a reviewer can see its source.

    Fields
    ------
    check :
        The plausibility check that raised the contradiction (e.g. "Known Wind
        Farm Comparison").
    description :
        The human-readable description of the contradiction, carried verbatim.
    kind :
        The anomaly kind (e.g. "data_issue"), distinguishing a data issue from a
        legitimate model result.
    investigation_note :
        The documented investigation note, carried verbatim.
    """

    check: str
    description: str
    kind: str
    investigation_note: str

    def to_dict(self) -> dict:
        """Serialise to the CONTRACT.md §5 `SanityContradiction` shape."""
        return {
            "check": self.check,
            "description": self.description,
            "kind": self.kind,
            "investigation_note": self.investigation_note,
        }


@dataclass(frozen=True)
class SanityWindFarmRow:
    """
    One known-wind-farm comparison row (S3-08, CONTRACT.md §5).

    A `SanityWindFarmRow` is a verbatim projection of one row of the S1-12
    Results_Sidecar's `known_wind_farm_comparison.table` — each GA wind
    generator located to its containing cell, with that cell's engine
    `score`/`rank`/`percentile` and the Upper_Quartile flag. The service copies
    the row through; it computes no score, rank or percentile (CONTRACT.md §1,
    Requirement 2). The farm label is read from the sidecar's `wind_farm` field
    (the engine already resolved it from the GA `feature_name` attribute), NOT a
    `name` attribute.

    Fields
    ------
    wind_farm :
        The resolved wind-farm display name, carried verbatim from the sidecar's
        `wind_farm` field.
    cell_id :
        The containing analysis-cell id.
    score :
        The cell's S2-05 `suitability_score`; `None` for an Excluded_Cell.
    rank :
        The cell's S2-05 integer `rank`; `None` for an Excluded_Cell.
    percentile :
        The cell's score percentile over the eligible population; `None` for an
        Excluded_Cell.
    in_upper_quartile :
        Whether the cell falls in the Upper_Quartile (percentile >= 75).
    in_top_band :
        Whether the cell's engine rank falls in the top-ranked band (rank <=
        `top_band_n`), carried verbatim from the sidecar so the panel renders it
        under the "rank <= N" header without computing band membership itself
        (the Upper_Quartile flag and band membership diverge; NFR1).
    notes :
        The sanity stage's per-row note, carried verbatim.
    """

    wind_farm: str
    cell_id: str
    score: float | None = None
    rank: int | None = None
    percentile: float | None = None
    in_upper_quartile: bool = False
    in_top_band: bool = False
    notes: str = ""

    def to_dict(self) -> dict:
        """Serialise to the CONTRACT.md §5 `SanityWindFarmRow` shape."""
        return {
            "wind_farm": self.wind_farm,
            "cell_id": self.cell_id,
            "score": self.score,
            "rank": self.rank,
            "percentile": self.percentile,
            "in_upper_quartile": self.in_upper_quartile,
            "in_top_band": self.in_top_band,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class SanityRunMetadata:
    """
    The sanity result's lineage metadata (S3-08, CONTRACT.md §5).

    A `SanityRunMetadata` is a verbatim projection of the S1-12 Results_Sidecar's
    `run_metadata` block — the run timestamp, pipeline version, resolved
    shortlist path and cell counts that let a reviewer confirm the sanity result
    reflects the same engine generation as the map/shortlist (FR5/AC7). Every
    field defaults to empty / `None` so a sidecar missing `run_metadata` (or a
    field within it) projects cleanly — the panel renders "lineage metadata
    unavailable" rather than crashing, and the service never asserts a lineage it
    cannot evidence.

    Fields
    ------
    run_timestamp :
        The UTC Run_Timestamp the sanity stage stamped; empty when absent.
    pipeline_version :
        The pipeline version the sanity run recorded; empty when absent.
    resolved_shortlist_path :
        The resolved shortlist path the sanity run read; empty when absent.
    n_cells :
        The total analysis-cell count; `None` when absent.
    n_eligible :
        The eligible-cell count; `None` when absent.
    """

    run_timestamp: str = ""
    pipeline_version: str = ""
    resolved_shortlist_path: str = ""
    n_cells: int | None = None
    n_eligible: int | None = None

    def to_dict(self) -> dict:
        """Serialise to the CONTRACT.md §5 `SanityRunMetadata` shape."""
        return {
            "run_timestamp": self.run_timestamp,
            "pipeline_version": self.pipeline_version,
            "resolved_shortlist_path": self.resolved_shortlist_path,
            "n_cells": self.n_cells,
            "n_eligible": self.n_eligible,
        }


@dataclass(frozen=True)
class SanityCheck:
    """
    The S1-12 sanity-check / validation result for the baseline engine output
    (S3-08, CONTRACT.md §5).

    A `SanityCheck` mirrors the S1-12 machine-readable Results_Sidecar the sanity
    stage materialised: the always-on model-not-trained `caveat`, the
    `preliminary_disclaimer`, the lineage `run_metadata`, the normalised list of
    per-check outcomes (incl. the synthesized exclusion summary), the full
    contradictions list, the known-wind-farm comparison table, the top-ranked
    band N, and the per-landmark exclusion assertions — all carried through
    VERBATIM. `get_sanity_check` (`sanity.py`) reads that sidecar and projects it
    into this shape; it performs no sanity check, re-runs nothing and re-derives
    no verdict (CONTRACT.md §1, Requirement 2). This is how the Web_Application
    surfaces the sanity result reachable from the app shell (FR4/AC6), with the
    caveat always shown (FR2/AC3) and the lineage visible (FR5/AC7); a
    missing/unreadable sidecar fails honestly rather than fabricating a passing
    verdict (Requirement 7.3).

    Fields
    ------
    caveat :
        The always-on model-not-trained-to-reproduce caveat (FR2/AC3), carried
        verbatim from the sidecar's top-level `caveat`.
    preliminary_disclaimer :
        The preliminary-screening disclaimer, carried verbatim.
    run_metadata :
        The lineage metadata (FR5/AC7); `None` when the sidecar carries none.
    checks :
        The six normalised per-check outcomes, including the synthesized
        exclusion summary. Every check is surfaced — no silent passes.
    contradictions :
        The full `issues_for_sprint_2` list (all four checks' anomalies).
    wind_farms :
        The known-wind-farm comparison table rows, carried verbatim.
    top_band_n :
        The top-ranked band N (rank <= N) the top-band outcome used, so the panel
        can render "rank <= N" without arithmetic.
    exclusion_assertions :
        The per-landmark exclusion-validation assertions, carried verbatim for an
        optional sub-table.
    """

    caveat: str = ""
    preliminary_disclaimer: str = ""
    run_metadata: SanityRunMetadata | None = None
    checks: list[SanityCheckItem] = field(default_factory=list)
    contradictions: list[SanityContradiction] = field(default_factory=list)
    wind_farms: list[SanityWindFarmRow] = field(default_factory=list)
    top_band_n: int = 0
    exclusion_assertions: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialise to the CONTRACT.md §5 `SanityCheck` shape."""
        return {
            "caveat": self.caveat,
            "preliminary_disclaimer": self.preliminary_disclaimer,
            "run_metadata": (
                self.run_metadata.to_dict() if self.run_metadata is not None else None
            ),
            "checks": [check.to_dict() for check in self.checks],
            "contradictions": [c.to_dict() for c in self.contradictions],
            "wind_farms": [w.to_dict() for w in self.wind_farms],
            "top_band_n": self.top_band_n,
            "exclusion_assertions": [dict(a) for a in self.exclusion_assertions],
        }
