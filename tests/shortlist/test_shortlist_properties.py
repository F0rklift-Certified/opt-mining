"""
Property-based tests for the S1-11 preliminary ranked-shortlist stage.

Each test corresponds to one numbered property in the feature design document
and runs at least 100 generated examples. The pure resolver under test
(`pipeline.shortlist.config.resolve_top_n`) is exercised directly on in-memory
values, so no test here touches the filesystem — the point of Property 4 is
precisely that an invalid Top_N is rejected BEFORE any output is written.
"""

from __future__ import annotations

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from pipeline.shortlist.config import resolve_top_n

SETTINGS = settings(max_examples=100, deadline=None)


# Non-positive-integer Top_N values: zero, negatives, non-integers (floats,
# strings, None-like non-ints), and bool (an int subclass that must not
# masquerade as a count of 1/0). Each of these must be rejected.
_invalid_top_n = st.one_of(
    st.integers(max_value=0),  # zero and negatives
    st.floats(allow_nan=True, allow_infinity=True),  # any float, incl. 3.0
    st.booleans(),  # True/False (int subclass, still invalid)
    st.text(max_size=8),  # non-numeric type
    st.complex_numbers(allow_nan=False, allow_infinity=False),
)


# Feature: s1-11-generate-ranked-shortlist, Property 4: Invalid Top_N is rejected before any write
@SETTINGS
@given(value=_invalid_top_n)
def test_property_4_invalid_top_n_rejected_before_any_write(value):
    # A non-positive-integer Top_N must halt with a ValueError that identifies
    # the offending value, before any output is produced. resolve_top_n does no
    # filesystem I/O, so a raise here IS the "no partial output on disk"
    # guarantee at this layer.
    #
    # Provide the invalid value at the highest-precedence position (cli_value)
    # so the resolver validates exactly this value.
    with pytest.raises(ValueError) as excinfo:
        resolve_top_n(cli_value=value, config_value=None)

    # The error must identify the invalid value. resolve_top_n renders it with
    # repr(), so the repr of the offending value appears in the message. NaN is
    # the one value whose repr does not round-trip through equality, so match on
    # its textual token instead.
    message = str(excinfo.value)
    if isinstance(value, float) and math.isnan(value):
        assert "nan" in message.lower()
    else:
        assert repr(value) in message
