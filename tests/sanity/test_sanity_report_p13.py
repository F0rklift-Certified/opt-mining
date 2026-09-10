"""Property test for the S1-12 sanity-check Validation_Report renderer.

# Feature: s1-12-validation-sanity-check, Property 13: The report contains all required sections and disclaimers

Property 13: The report contains all required sections and disclaimers.
    For ANY generated inputs the rendered Validation_Report contains the six
    required sections, the run metadata (Pipeline_Version and the total /
    eligible cell counts), the Preliminary_Disclaimer text, and the
    Analysis_Resolution statement.

Validates: Requirements 7.2, 7.3, 7.5, 7.6

The four check results the renderer consumes are built by running the REAL
checks (``check_known_wind_farms`` / ``check_exclusions`` / ``select_spot_cells``
+ ``check_spot_values`` / ``check_distribution``) over synthetic frames, reusing
the construction the sibling Property 11 test uses so containment is unambiguous
after the EPSG:4326 -> EPSG:3577 reprojection. The recorded anomalies are then
gathered with ``issues.collect_issues`` and bundled — together with the shared
CRS transform log — into a :class:`report.SanityResults`, alongside a
:class:`report.RunMetadata` drawn with varied values.

The rendered Markdown string is then asserted to contain, for every generated
input:

  - the six section headers (``1. Known Wind Farm Comparison`` .. ``6.
    Conclusion``) in order (7.2);
  - the run-metadata values: the Pipeline_Version, and the total / eligible cell
    counts (7.3);
  - the Preliminary_Disclaimer text (7.5);
  - the Analysis_Resolution statement (7.6).

The renderer is PURE over the results/metadata, so no filesystem access is
needed and the assertions hold for any generated inputs.
"""

import geopandas as gpd
import numpy as np
import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st
from shapely.geometry import Point, box

from pipeline.sanity import config
from pipeline.sanity.checks import (
    check_distribution,
    check_exclusions,
    check_known_wind_farms,
    check_spot_values,
    select_spot_cells,
)
from pipeline.sanity.geo import CrsTransform
from pipeline.sanity.issues import collect_issues
from pipeline.sanity.report import RunMetadata, SanityResults, render_report

STORAGE_CRS = config.STORAGE_CRS  # "EPSG:4326"
CONTAINMENT_CRS = config.CONTAINMENT_CRS  # "EPSG:3577"

# Grid origin chosen inside the EPSG:3577 (Australian Albers) valid extent so
# reprojection from EPSG:4326 is well-defined; 0.1 deg square cells keep
# interior points unambiguous after reprojection (mirrors the P11 test).
ORIGIN_LON = 149.0
ORIGIN_LAT = -33.0
CELL_DEG = 0.1

_SCORE = config.REQUIRED_SCORE_COLUMNS[1]  # "suitability_score"
_RANK = config.REQUIRED_SCORE_COLUMNS[2]  # "rank"
_NAME = config.REQUIRED_WIND_GENERATOR_ATTR  # "name"
_INT_CELL_ID = config.REQUIRED_INTEGRATED_COLUMNS[0]  # "cell_id"
_INT_WIND_SPEED = config.REQUIRED_INTEGRATED_COLUMNS[1]  # "wind_speed"
_INT_ELIGIBLE = config.REQUIRED_INTEGRATED_COLUMNS[5]  # "eligible"

# Half-width of each landmark cell (degrees); small enough that landmark cells
# never overlap yet the reprojected point stays comfortably interior.
_HALF = 0.02

# The six required section headers, in the order Requirement 7.2 mandates.
_REQUIRED_SECTIONS = (
    "1. Known Wind Farm Comparison",
    "2. Exclusion Validation",
    "3. Feature Value Spot-Checks",
    "4. Score Distribution",
    "5. Issues for Sprint 2",
    "6. Conclusion",
)


def _cell_id(col: int, row: int) -> str:
    return f"c{col}_{row}"


def _make_grid(n_cols: int, n_rows: int) -> gpd.GeoDataFrame:
    """A rectangular block of adjacent square cells with deterministic ids."""
    cell_ids = []
    geoms = []
    for row in range(n_rows):
        for col in range(n_cols):
            minx = ORIGIN_LON + col * CELL_DEG
            miny = ORIGIN_LAT + row * CELL_DEG
            cell_ids.append(_cell_id(col, row))
            geoms.append(box(minx, miny, minx + CELL_DEG, miny + CELL_DEG))
    return gpd.GeoDataFrame({"cell_id": cell_ids}, geometry=geoms, crs=STORAGE_CRS)


def _interior_point(col: int, row: int) -> Point:
    """A point at the centre of cell ``(col, row)`` — unambiguously interior."""
    minx = ORIGIN_LON + col * CELL_DEG
    miny = ORIGIN_LAT + row * CELL_DEG
    return Point(minx + 0.5 * CELL_DEG, miny + 0.5 * CELL_DEG)


def _cell_box(lon: float, lat: float):
    """A small square landmark cell centred on ``(lon, lat)`` in EPSG:4326."""
    return box(lon - _HALF, lat - _HALF, lon + _HALF, lat + _HALF)


_score_strategy = st.floats(
    min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False
)
_wind_strategy = st.floats(
    min_value=5.0, max_value=12.0, allow_nan=False, allow_infinity=False
)

# The three fates a landmark can take (mirroring the P4 / P11 tests): excluded
# (passes), eligible (a forced failing assertion), or absent from the grid.
_EXCLUDED = "excluded"
_ELIGIBLE = "eligible"
_ABSENT = "absent"
_fate = st.sampled_from([_EXCLUDED, _ELIGIBLE, _ABSENT])


@settings(max_examples=120, deadline=None)
@given(
    n_cols=st.integers(min_value=2, max_value=5),
    n_rows=st.integers(min_value=2, max_value=5),
    fates=st.lists(
        _fate, min_size=len(config.LANDMARKS), max_size=len(config.LANDMARKS)
    ),
    pipeline_version=st.text(
        alphabet=st.characters(
            whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="._-"
        ),
        min_size=1,
        max_size=20,
    ),
    run_timestamp=st.datetimes().map(lambda d: d.strftime("%Y-%m-%dT%H:%M:%SZ")),
    data=st.data(),
)
def test_property_13_report_contains_all_sections_and_disclaimers(
    n_cols, n_rows, fates, pipeline_version, run_timestamp, data
):
    grid = _make_grid(n_cols, n_rows)
    n_cells = n_cols * n_rows
    all_cells = [
        _cell_id(col, row) for row in range(n_rows) for col in range(n_cols)
    ]

    # --- Synthetic Scored_Table over every grid cell (some cells excluded). ---
    eligible_flags = [
        data.draw(st.booleans(), label=f"eligible_{i}") for i in range(n_cells)
    ]
    # Force enough eligible cells that the distribution/correlation statistics
    # are well-defined and a spot-cell selection is always possible.
    n_forced = min(n_cells, config.SPOT_CHECK_MIN)
    for i in range(n_forced):
        eligible_flags[i] = True

    scores = []
    ranks = []
    winds = []
    rank_counter = 1
    for i in range(n_cells):
        if eligible_flags[i]:
            scores.append(data.draw(_score_strategy, label=f"score_{i}"))
            ranks.append(rank_counter)
            rank_counter += 1
            winds.append(data.draw(_wind_strategy, label=f"wind_{i}"))
        else:
            scores.append(np.nan)
            ranks.append(np.nan)
            winds.append(np.nan)

    scored = pd.DataFrame({"cell_id": all_cells, _SCORE: scores, _RANK: ranks})

    n_eligible_cells = sum(eligible_flags)

    # --- Synthetic Integrated_Feature_Table over the SAME cells. ---
    integrated = pd.DataFrame(
        {
            _INT_CELL_ID: all_cells,
            _INT_WIND_SPEED: winds,
            _INT_ELIGIBLE: eligible_flags,
        }
    )

    # --- Synthetic Wind_Generators, each placed at a known interior cell. ---
    n_farms = data.draw(st.integers(min_value=0, max_value=8), label="n_farms")
    farm_geoms = []
    farm_names = []
    for f in range(n_farms):
        col = data.draw(st.integers(min_value=0, max_value=n_cols - 1))
        row = data.draw(st.integers(min_value=0, max_value=n_rows - 1))
        farm_geoms.append(_interior_point(col, row))
        farm_names.append(f"farm_{f}")
    wind_generators = gpd.GeoDataFrame(
        {_NAME: farm_names},
        geometry=farm_geoms if farm_geoms else [],
        crs=STORAGE_CRS,
    )

    # --- Check 1 — Known Wind Farm Comparison. ---
    wf_log: list[CrsTransform] = []
    wf_result = check_known_wind_farms(
        wind_generators, grid, scored, CONTAINMENT_CRS, wf_log
    )

    # --- Check 2 — Exclusion Validation (dedicated landmark frames). ---
    lm_grid_ids = []
    lm_grid_geoms = []
    lm_scored_rows = []
    lm_integrated_rows = []
    for idx, (landmark, fate) in enumerate(zip(config.LANDMARKS, fates)):
        if fate == _ABSENT:
            continue
        cid = f"landmark_cell_{idx}"
        lm_grid_ids.append(cid)
        lm_grid_geoms.append(_cell_box(landmark.lon, landmark.lat))
        if fate == _ELIGIBLE:
            lm_scored_rows.append(
                {"cell_id": cid, "suitability_score": 0.5, "rank": idx + 1}
            )
            lm_integrated_rows.append({"cell_id": cid, "eligible": True})
        else:  # _EXCLUDED
            lm_scored_rows.append(
                {"cell_id": cid, "suitability_score": None, "rank": None}
            )
            lm_integrated_rows.append({"cell_id": cid, "eligible": False})

    lm_grid = gpd.GeoDataFrame(
        {"cell_id": lm_grid_ids}, geometry=lm_grid_geoms, crs=STORAGE_CRS
    )
    lm_scored = pd.DataFrame(
        lm_scored_rows, columns=["cell_id", "suitability_score", "rank"]
    )
    lm_integrated = pd.DataFrame(
        lm_integrated_rows, columns=["cell_id", "eligible"]
    )
    ex_log: list[CrsTransform] = []
    ex_result = check_exclusions(
        config.LANDMARKS,
        lm_grid,
        lm_scored,
        lm_integrated,
        CONTAINMENT_CRS,
        ex_log,
    )

    # --- The eligible population, joined with wind_speed for Checks 3 and 4. ---
    eligible = scored[scored[_SCORE].notna() & scored[_RANK].notna()].copy()
    eligible = eligible.merge(
        integrated[[_INT_CELL_ID, _INT_WIND_SPEED]],
        left_on="cell_id",
        right_on=_INT_CELL_ID,
        how="left",
    )

    # --- Check 3 — Feature-Value Spot-Checks. ---
    # ``select_spot_cells`` requires n in [SPOT_CHECK_MIN, SPOT_CHECK_MAX] and a
    # non-empty eligible population; it returns fewer rows only when the
    # population itself is smaller than n. The eligible population is always
    # non-empty here (at least one cell was forced eligible above).
    spot = select_spot_cells(eligible, config.SPOT_CHECK_MIN)
    spot_result = check_spot_values(spot, integrated)

    # --- Check 4 — Score-Distribution Plausibility. ---
    dist_result = check_distribution(eligible)

    # --- Gather anomalies and assemble the aggregate result + metadata. ---
    issues = collect_issues(wf_result, ex_result, spot_result, dist_result)
    transform_log = list(wf_log) + list(ex_log)
    results = SanityResults(
        wind_farms=wf_result,
        exclusions=ex_result,
        spot_values=spot_result,
        distribution=dist_result,
        issues=issues,
        transform_log=transform_log,
    )
    meta = RunMetadata(
        run_timestamp=run_timestamp,
        pipeline_version=pipeline_version,
        n_cells=n_cells,
        n_eligible=n_eligible_cells,
        resolved_shortlist_path=f"DATA/shortlist/sprint1_shortlist_{run_timestamp}.geojson",
    )

    # =======================================================================
    # Render and assert the report contains every required element (7.2, 7.3,
    # 7.5, 7.6).
    # =======================================================================
    report = render_report(results, meta)

    # --- All six required sections are present, in order (7.2). ---
    last_pos = -1
    for section in _REQUIRED_SECTIONS:
        pos = report.find(section)
        assert pos != -1, f"missing required section: {section!r}"
        assert pos > last_pos, f"section {section!r} out of order"
        last_pos = pos

    # --- Run metadata: Pipeline_Version and the cell counts (7.3). ---
    assert pipeline_version in report, "report must record the Pipeline_Version"
    assert f"{n_cells:,}" in report, "report must record the total cell count"
    assert (
        f"{n_eligible_cells:,}" in report
    ), "report must record the eligible cell count"
    assert run_timestamp in report, "report must record the run timestamp"

    # --- The Preliminary_Disclaimer text is present (7.5). ---
    assert (
        config.PRELIMINARY_DISCLAIMER in report
    ), "report must carry the Preliminary_Disclaimer verbatim"

    # --- The Analysis_Resolution statement is present (7.6). ---
    assert (
        config.ANALYSIS_RESOLUTION in report
    ), "report must state the Analysis_Resolution"
