"""
Tests for S2-06a qualitative band derivation.

Bands classify a normalised value into a label from the templates, honouring
the boolean and constant-criterion policies of scoring.normalise. Pure
functions: identical inputs -> identical labels.

Feature: s2-06a-explanation-engine-eligible-cells
"""

from __future__ import annotations

import math

from pipeline.explanation.bands import band_for, is_constant
from pipeline.explanation.templates import load_templates
from pipeline.scoring.normalise import Bounds

T = load_templates()


def _continuous(lo=0.0, hi=10.0) -> Bounds:
    return Bounds(
        feature="dist_transmission_km", lo=lo, hi=hi,
        observed_min=lo, observed_max=hi, is_boolean=False,
        is_constant=(lo == hi), n_observed=4,
    )


def _boolean() -> Bounds:
    return Bounds(
        feature="inside_rez", lo=0.0, hi=1.0,
        observed_min=0.0, observed_max=1.0, is_boolean=True,
        is_constant=False, n_observed=4,
    )


def _constant() -> Bounds:
    return Bounds(
        feature="slope_deg", lo=5.0, hi=5.0,
        observed_min=5.0, observed_max=5.0, is_boolean=False,
        is_constant=True, n_observed=4,
    )


def test_continuous_bands_follow_the_template_thresholds():
    b = _continuous()
    assert band_for(0.95, b, T) == "top decile"
    assert band_for(0.7, b, T) == "strong"
    assert band_for(0.4, b, T) == "moderate"
    assert band_for(0.1, b, T) == "limited"


def test_boolean_uses_present_absent_labels():
    b = _boolean()
    assert band_for(1.0, b, T) == T.boolean_true_label
    assert band_for(0.0, b, T) == T.boolean_false_label


def test_constant_criterion_is_not_surfaced():
    assert band_for(1.0, _constant(), T) is None
    assert is_constant(_constant())
    assert not is_constant(_continuous())


def test_missing_value_is_not_surfaced():
    assert band_for(None, _continuous(), T) is None
    assert band_for(float("nan"), _continuous(), T) is None


def test_determinism_same_input_same_label():
    b = _continuous()
    assert band_for(0.72, b, T) == band_for(0.72, b, T)


def test_boundary_values_land_in_the_tighter_band():
    b = _continuous()
    # Exactly on a threshold belongs to that band (>=).
    assert band_for(0.9, b, T) == "top decile"
    assert band_for(0.65, b, T) == "strong"
    assert band_for(0.35, b, T) == "moderate"
    assert band_for(0.0, b, T) == "limited"
