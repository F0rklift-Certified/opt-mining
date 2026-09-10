"""
Shortlist assembly & schema for the S1-11 shortlist stage
(Requirement 4.1, 4.3).

After the coordinate join (`coords.join_coordinates`) has attached
`centroid_lat` / `centroid_lon` to the selected top-N Eligible_Cells, this
module shapes that in-memory frame into the documented Shortlist schema: it
selects and REORDERS the columns into the documented `SHORTLIST_COLUMNS` order
(`rank`, `cell_id`, `suitability_score`, `confidence`, `centroid_lat`,
`centroid_lon`) and, WHERE an optional context column (`rez`,
`nearby_wind_farm`) is already present on the joined frame from an upstream
layer, appends it after the core columns as a named, documented column
(Requirement 4.1, 4.3).

Two rules are load-bearing and named here because a naive implementation would
either fabricate data or silently drop a value:

  PURE, NO FABRICATION. This is a pure function of an in-memory frame — no file
  I/O and no mutation of the input. It only SELECTS and REORDERS existing
  columns; it never adds, pads, or synthesises a row, so only the Eligible_Cells
  that survived selection appear and no Excluded_Cell and no fabricated/padded
  row can enter here (Requirement 2.2, 3.4). The row order of the input (the
  S1-10 ascending-`rank` ordering the earlier stages preserved) is carried
  through unchanged.

  OPTIONAL-CONTEXT IS "WHERE AVAILABLE". An optional context column is appended
  ONLY when it is actually present on the joined frame. A column that no
  upstream layer supplied is simply absent from the Shortlist — it is never
  fabricated as null/empty to force the schema. Every optional column that IS
  appended is a DOCUMENTED column: its definition and source are exposed via
  :func:`optional_context_columns` so the Summary_Report (task 10) can record
  them alongside the schema (Requirement 4.3).

The core columns come straight from the selected + joined frame and are never
recomputed: `rank`, `suitability_score`, `confidence` are the S1-10 values
carried through selection, and `centroid_lat` / `centroid_lon` are the grid
values from the join (Requirement 4.6). Design reference: design.md §6
"Shortlist assembly & schema".
"""

from __future__ import annotations

from typing import NamedTuple

import pandas as pd

from . import config


class OptionalContextColumn(NamedTuple):
    """
    The definition and source of an optional context column, surfaced for the
    Summary_Report (Requirement 4.3).

    ``name``        The column name as it appears in the Shortlist
                    (one of ``config.OPTIONAL_CONTEXT_COLUMNS``).
    ``definition``  A human-readable description of what the column carries,
                    for the Summary_Report's documented-column list.
    ``source``      The upstream layer / provenance the value derives from, so a
                    reviewer can trace where the context came from.
    """

    name: str
    definition: str
    source: str


# The documented definition and source for each optional context column the
# shortlist MAY carry. This is the authoritative catalogue keyed by the column
# names in ``config.OPTIONAL_CONTEXT_COLUMNS`` — a column is only ever appended
# to the Shortlist when it is present on the joined frame AND catalogued here,
# so every appended column is a *documented* column (Requirement 4.3). Keeping
# the wording here (rather than in the report module) means the definition
# travels with the column that produces it.
OPTIONAL_CONTEXT_DEFINITIONS: dict[str, OptionalContextColumn] = {
    "rez": OptionalContextColumn(
        name="rez",
        definition=(
            "Renewable Energy Zone (REZ) that the shortlisted cell lies within, "
            "identified by name; null where the cell lies outside any declared REZ."
        ),
        source=(
            "REZ membership joined on cell_id from the upstream Renewable Energy "
            "Zone boundary layer, where that layer is available."
        ),
    ),
    "nearby_wind_farm": OptionalContextColumn(
        name="nearby_wind_farm",
        definition=(
            "Indicator that the shortlisted cell is near an existing wind farm, "
            "flagging candidate sites that already sit within established "
            "wind-development context."
        ),
        source=(
            "Proximity to the upstream existing-wind-farm infrastructure layer, "
            "joined on cell_id, where that layer is available."
        ),
    ),
}


def available_optional_columns(joined: pd.DataFrame) -> tuple[str, ...]:
    """
    Return the optional context columns actually present on ``joined``, in the
    documented ``config.OPTIONAL_CONTEXT_COLUMNS`` order.

    An optional column counts as "available" only when it is an actual column of
    the joined frame AND is catalogued in :data:`OPTIONAL_CONTEXT_DEFINITIONS`
    (so its definition and source can be documented). A column that no upstream
    layer supplied is simply omitted — never fabricated (Requirement 4.3).
    """
    return tuple(
        col
        for col in config.OPTIONAL_CONTEXT_COLUMNS
        if col in joined.columns and col in OPTIONAL_CONTEXT_DEFINITIONS
    )


def optional_context_columns(joined: pd.DataFrame) -> tuple[OptionalContextColumn, ...]:
    """
    Return the definition/source records for the optional context columns that
    WILL be appended to the Shortlist for ``joined``, in documented order
    (Requirement 4.3).

    This is the hook the Summary_Report writer (task 10) uses to record each
    optional column's definition and source. It reports exactly the columns
    :func:`assemble_shortlist` appends — so the report can never document a
    column the Shortlist does not carry, nor omit one it does — because both
    derive the set from :func:`available_optional_columns`.

    PURE: reads only ``joined``'s column labels; no file I/O and no mutation.
    Returns an empty tuple when no optional context column is available.
    """
    return tuple(
        OPTIONAL_CONTEXT_DEFINITIONS[col] for col in available_optional_columns(joined)
    )


def assemble_shortlist(joined: pd.DataFrame) -> pd.DataFrame:
    """
    Assemble the Shortlist frame in the documented schema (Requirement 4.1,
    4.3).

    Selects the documented core columns in the documented order —
    ``config.SHORTLIST_COLUMNS`` = (``rank``, ``cell_id``, ``suitability_score``,
    ``confidence``, ``centroid_lat``, ``centroid_lon``) — then appends any
    optional context column (``rez``, ``nearby_wind_farm``) that is available on
    ``joined``, in documented order, AFTER the core columns (Requirement 4.1,
    4.3).

    PURE: takes the coordinate-joined in-memory frame, returns a NEW in-memory
    frame; no file I/O and no mutation of the input. It only selects and
    reorders existing columns, so it can neither drop an Eligible_Cell nor
    fabricate/pad a row — only the rows that survived selection appear, in their
    incoming (ascending-``rank``) order (Requirement 2.2, 3.4). ``rank``,
    ``suitability_score``, ``confidence`` and ``centroid_lat`` / ``centroid_lon``
    are carried through byte-for-consistent with their producers and never
    recomputed (Requirement 4.6).

    An empty joined frame (zero eligible cells, Requirement 3.6) assembles to an
    empty frame that still carries every documented column, so the downstream
    writers emit headered outputs with the disclaimer.

    Raises
    ------
    KeyError
        If ``joined`` is missing any of the documented core
        ``config.SHORTLIST_COLUMNS`` — a fail-fast condition naming the absent
        column(s), since a core column can only be missing if an upstream stage
        broke the contract. This halts before any output is written.

    Notes
    -----
    The optional context columns that were appended (with their definitions and
    sources for the Summary_Report) are available via
    :func:`optional_context_columns` on the same ``joined`` frame, so the caller
    documents exactly the columns this function appended.
    """
    core = list(config.SHORTLIST_COLUMNS)

    missing = [c for c in core if c not in joined.columns]
    if missing:
        raise KeyError(
            f"Cannot assemble the Shortlist: the joined frame is missing "
            f"documented column(s) {missing}. The shortlist schema requires "
            f"{core} in that order (rank/score/confidence carried from the "
            f"Scored_Table, centroid_lat/centroid_lon from the coordinate "
            f"join); an absent core column means an upstream stage broke its "
            f"contract."
        )

    optional = list(available_optional_columns(joined))

    ordered_columns = core + optional
    # Select + reorder existing columns only — never add or pad a row. `.copy()`
    # returns a fresh frame so the caller cannot mutate `joined` through the
    # result. The incoming row order (ascending S1-10 `rank`) is preserved.
    return joined.loc[:, ordered_columns].copy()
