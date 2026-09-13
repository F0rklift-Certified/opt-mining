"""
Tests for the pure S2-06a explanation engine.

Hand-built cells with known contributions and normalised values, so the
expected positive factors / weaknesses are derivable on paper. The engine is
pure: same input twice -> identical dict, and no output ever contains a banned
superlative.

Feature: s2-06a-explanation-engine-eligible-cells
"""

from __future__ import annotations

from pipeline.explanation import config as ecfg
from pipeline.explanation.engine import CellExplanationInput, CriterionView, explain_cell
from pipeline.explanation.templates import BANNED_SUPERLATIVES, load_templates
from pipeline.scoring.normalise import Bounds

T = load_templates()


def _bounds(feature, *, boolean=False, constant=False) -> Bounds:
    return Bounds(
        feature=feature, lo=0.0, hi=1.0 if boolean else 10.0,
        observed_min=0.0, observed_max=1.0 if boolean else 10.0,
        is_boolean=boolean, is_constant=constant, n_observed=4,
    )


def _view(feature, contribution, norm, *, boolean=False, constant=False) -> CriterionView:
    return CriterionView(
        feature=feature, contribution=contribution, norm=norm,
        bounds=_bounds(feature, boolean=boolean, constant=constant),
    )


def _no_superlative(explanation: dict) -> None:
    blob = " ".join(
        [explanation["headline"], *explanation["positive_factors"], *explanation["weaknesses"]]
    ).lower()
    for banned in BANNED_SUPERLATIVES:
        assert banned not in blob


# --- A high-scoring cell: strong everywhere, one mild weakness --------------


def high_scoring_cell() -> CellExplanationInput:
    return CellExplanationInput(
        cell_id="NSW001",
        criteria=(
            _view("wind_speed", contribution=0.40, norm=0.95),            # top decile
            _view("inside_rez", contribution=0.20, norm=1.0, boolean=True),  # present
            _view("dist_transmission_km", contribution=0.10, norm=0.70),  # strong
            _view("slope_deg", contribution=0.05, norm=0.30),             # weakness (<=0.5)
        ),
    )


def test_high_scoring_positive_factors_ranked_by_contribution():
    e = explain_cell(high_scoring_cell(), T)
    assert e["cell_id"] == "NSW001"
    assert e["eligible"] is True
    assert e["headline"] == T.headline
    # Top 3 by contribution among favourable (norm>0.5): wind(0.40), rez(0.20), transmission(0.10)
    assert e["positive_factors"] == [
        "Strong wind resource (top decile)",
        "Inside a Renewable Energy Zone (present)",
        "Close to transmission (strong)",
    ]
    # slope_deg (norm 0.30 <= 0.5) is the weakness; 0.30 < 0.35 -> "limited" band
    assert e["weaknesses"] == ["Steeper terrain (limited)"]
    _no_superlative(e)


# --- A marginal cell: weak resource, distant, only demand carries it --------


def marginal_cell() -> CellExplanationInput:
    return CellExplanationInput(
        cell_id="NSW042",
        criteria=(
            _view("wind_speed", contribution=0.05, norm=0.20),            # weakness
            _view("dist_transmission_km", contribution=0.02, norm=0.10),  # worst weakness
            _view("demand_proxy", contribution=0.15, norm=0.80),          # the one strength
            _view("inside_rez", contribution=0.0, norm=0.0, boolean=True),  # absent -> weakness
        ),
    )


def test_marginal_cell_surfaces_the_one_strength_and_worst_weaknesses():
    e = explain_cell(marginal_cell(), T)
    # Only demand_proxy has norm>0.5, so it is the sole positive factor.
    assert e["positive_factors"] == ["Near electrical demand (strong)"]
    # Weaknesses ranked worst-first (lowest norm): inside_rez(0.0), dist_transmission(0.10)
    # capped at MAX_WEAKNESSES=2.
    assert e["weaknesses"] == [
        "Outside any Renewable Energy Zone (absent)",
        "Distant from transmission (limited)",
    ]
    _no_superlative(e)


# --- Determinism ------------------------------------------------------------


def test_determinism_identical_dicts():
    assert explain_cell(high_scoring_cell(), T) == explain_cell(high_scoring_cell(), T)
    assert explain_cell(marginal_cell(), T) == explain_cell(marginal_cell(), T)


# --- Caps and edge policies -------------------------------------------------


def test_positive_factors_capped():
    # Five favourable criteria; only MAX_POSITIVE_FACTORS surface.
    cell = CellExplanationInput(
        cell_id="NSWcap",
        criteria=tuple(
            _view(f, contribution=c, norm=0.9)
            for f, c in [
                ("wind_speed", 0.5), ("demand_proxy", 0.4),
                ("dist_transmission_km", 0.3), ("dist_substation_km", 0.2),
                ("slope_deg", 0.1),
            ]
        ),
    )
    e = explain_cell(cell, T)
    assert len(e["positive_factors"]) == ecfg.MAX_POSITIVE_FACTORS


def test_constant_criterion_never_surfaces():
    cell = CellExplanationInput(
        cell_id="NSWconst",
        criteria=(
            _view("wind_speed", contribution=0.30, norm=0.80),
            _view("slope_deg", contribution=0.10, norm=1.0, constant=True),  # constant fill
        ),
    )
    e = explain_cell(cell, T)
    assert e["positive_factors"] == ["Strong wind resource (strong)"]
    assert e["weaknesses"] == []  # constant slope is not a weakness either


def test_missing_value_criterion_never_surfaces():
    cell = CellExplanationInput(
        cell_id="NSWmiss",
        criteria=(
            _view("wind_speed", contribution=0.30, norm=0.80),
            _view("slope_deg", contribution=None, norm=None),  # no value for this cell
        ),
    )
    e = explain_cell(cell, T)
    assert e["positive_factors"] == ["Strong wind resource (strong)"]
    assert e["weaknesses"] == []


def test_positive_feature_not_double_listed_as_weakness():
    # A criterion exactly at the ceiling (0.5) is not a positive (needs >0.5)
    # and IS eligible as a weakness (<=0.5); ensure no phrase appears twice.
    cell = CellExplanationInput(
        cell_id="NSWedge",
        criteria=(
            _view("wind_speed", contribution=0.30, norm=0.9),
            _view("slope_deg", contribution=0.10, norm=0.5),
        ),
    )
    e = explain_cell(cell, T)
    assert e["positive_factors"] == ["Strong wind resource (top decile)"]
    assert e["weaknesses"] == ["Steeper terrain (moderate)"]
