"""
Scaffold-constant tests for the S2-02 input-contract gate (task 1.1 output in
`pipeline.validate`).

These tests pin the two module-level scaffold constants added by task 1.1 —
`SANITY_RANGES` and `DEFAULT_INTEGRATED_PATH` — against the Schema_Authority so
that a schema or path change in `pipeline/integration/config.py` /
`pipeline/integration/merge.py` PROPAGATES into the validator rather than the
validator drifting away from the schema it is supposed to check:

  * every `SANITY_RANGES` key is a scored column (a strict subset of
    `SCORED_FEATURE_COLUMNS` — `dist_connection_km` and `land_use` carry no
    bound, so equality is NOT expected);
  * each bound's shape (numeric range vs boolean set) is consistent with the
    `COLUMN_UNITS` entry for that column and the S2-01 §2 units/Directions;
  * `DEFAULT_INTEGRATED_PATH` resolves to `INTEGRATION_DIR / OUTPUT_FILENAME`,
    never a hard-coded literal.

Scope: task 1.2 — ONLY the scaffold constants. `freeze_baseline` and the check
battery are exercised by their own tasks/tests.

Requirements: 1.1, 2.1, 2.2, 5.1.
"""

from __future__ import annotations

from pipeline import validate
from pipeline.integration.config import (
    INTEGRATION_DIR,
    OUTPUT_FILENAME,
    SCORED_FEATURE_COLUMNS,
)
from pipeline.integration.merge import COLUMN_UNITS


# Columns whose Sanity_Range is a numeric interval vs a boolean set. Derived
# from the design Model 3 table; each is cross-checked against COLUMN_UNITS
# below rather than trusted blindly.
_NUMERIC_UNIT_TOKENS = {
    "wind_speed": "m/s",
    "demand_proxy": "normalised",
    "dist_transmission_km": "km",
    "dist_substation_km": "km",
    "slope_deg": "degrees",
    "elevation_m": "m AMSL",
}
_BOOLEAN_COLUMNS = {"inside_rez", "protected_area"}


class TestSanityRangesSubsetOfScoredColumns:
    """SANITY_RANGES keys are a (strict) subset of the scored feature columns."""

    def test_every_key_is_a_scored_column(self):
        scored = set(SCORED_FEATURE_COLUMNS)
        extra = set(validate.SANITY_RANGES) - scored
        assert extra == set(), (
            f"SANITY_RANGES has keys not in SCORED_FEATURE_COLUMNS: {sorted(extra)}"
        )

    def test_subset_is_strict_not_equal(self):
        # dist_connection_km and land_use are scored columns with no sanity
        # bound; the subset assertion must allow a strict subset, not equality.
        scored = set(SCORED_FEATURE_COLUMNS)
        keys = set(validate.SANITY_RANGES)
        assert keys < scored, (
            "SANITY_RANGES should be a STRICT subset of SCORED_FEATURE_COLUMNS "
            f"(unbounded scored columns exist); keys={sorted(keys)}, "
            f"scored={sorted(scored)}"
        )

    def test_unbounded_scored_columns_are_absent(self):
        # These two scored columns intentionally carry no Sanity_Range.
        for column in ("dist_connection_km", "land_use"):
            assert column in SCORED_FEATURE_COLUMNS
            assert column not in validate.SANITY_RANGES


class TestSanityRangesConsistentWithColumnUnits:
    """Each bound's shape agrees with the COLUMN_UNITS entry for that column."""

    def test_every_bounded_column_has_a_column_units_entry(self):
        for column in validate.SANITY_RANGES:
            assert column in COLUMN_UNITS, (
                f"{column} has a Sanity_Range but no COLUMN_UNITS entry"
            )

    def test_numeric_bounds_are_ordered_float_tuples(self):
        for column, token in _NUMERIC_UNIT_TOKENS.items():
            assert column in validate.SANITY_RANGES, (
                f"{column} expected to carry a numeric Sanity_Range"
            )
            bound = validate.SANITY_RANGES[column]
            assert isinstance(bound, tuple) and len(bound) == 2, (
                f"{column} Sanity_Range should be a (lo, hi) tuple, got {bound!r}"
            )
            lo, hi = bound
            assert isinstance(lo, float) and isinstance(hi, float), (
                f"{column} bounds should be floats, got {bound!r}"
            )
            assert lo < hi, f"{column} bound is not ordered: {bound!r}"
            # The unit string in the schema authority matches the interval kind.
            assert token in COLUMN_UNITS[column], (
                f"{column} COLUMN_UNITS {COLUMN_UNITS[column]!r} does not mention "
                f"the expected unit token {token!r}"
            )

    def test_boolean_bounds_are_the_false_true_set(self):
        for column in _BOOLEAN_COLUMNS:
            assert column in validate.SANITY_RANGES, (
                f"{column} expected to carry a boolean Sanity_Range"
            )
            bound = validate.SANITY_RANGES[column]
            assert bound == frozenset({False, True}), (
                f"{column} boolean Sanity_Range should be frozenset({{False, True}}), "
                f"got {bound!r}"
            )
            assert "bool" in COLUMN_UNITS[column], (
                f"{column} COLUMN_UNITS {COLUMN_UNITS[column]!r} is not documented "
                f"as a boolean column"
            )

    def test_every_bound_is_numeric_or_boolean(self):
        # No third shape may creep in; every key is accounted for above.
        classified = set(_NUMERIC_UNIT_TOKENS) | _BOOLEAN_COLUMNS
        assert set(validate.SANITY_RANGES) == classified, (
            "SANITY_RANGES keys are not fully classified as numeric or boolean; "
            f"unclassified={sorted(set(validate.SANITY_RANGES) - classified)}"
        )


class TestDefaultIntegratedPath:
    """The default integrated-table path is derived, not a re-typed literal."""

    def test_resolves_to_integration_dir_over_output_filename(self):
        assert validate.DEFAULT_INTEGRATED_PATH == INTEGRATION_DIR / OUTPUT_FILENAME

    def test_filename_component_is_the_config_output_filename(self):
        # A rename of OUTPUT_FILENAME upstream must flow through.
        assert validate.DEFAULT_INTEGRATED_PATH.name == OUTPUT_FILENAME

    def test_parent_is_the_config_integration_dir(self):
        assert validate.DEFAULT_INTEGRATED_PATH.parent == INTEGRATION_DIR
