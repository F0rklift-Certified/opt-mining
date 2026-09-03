"""
Tests for the S1-09 data-quality and confidence layer
(`pipeline.integration.confidence`).

The module is pure pandas/numpy/yaml: everything here runs on in-memory
frames and small YAML files under tmp_path. The six synthetic cells mirror
`tests/test_integration_table.py` so the worked numbers in the plan can be
asserted exactly.
"""

from __future__ import annotations

import copy
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

yaml = pytest.importorskip("yaml")

from pipeline.integration import config as icfg  # noqa: E402

SCORED = (
    "wind_speed", "demand_proxy", "dist_transmission_km", "dist_substation_km",
    "dist_connection_km", "inside_rez", "elevation_m", "slope_deg", "land_use",
    "protected_area",
)


_DEFAULT_RAW = yaml.safe_load(icfg.DEFAULT_CONFIDENCE_WEIGHTS_PATH.read_text(encoding="utf-8"))


def _default_raw() -> dict:
    """Deep copy of the packaged YAML as a dict, for mutation in fault tests."""
    return copy.deepcopy(_DEFAULT_RAW)


def _write(tmp_path: Path, obj, name="weights.yaml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(obj) if not isinstance(obj, str) else obj, encoding="utf-8")
    return path


def _parse(raw: dict):
    from pipeline.integration.confidence import parse_weights

    return parse_weights(raw)


# ---------------------------------------------------------------------------
# Packaged defaults
# ---------------------------------------------------------------------------


class TestPackagedDefaults:
    def test_config_constants(self):
        assert tuple(icfg.SCORED_FEATURE_COLUMNS) == SCORED
        assert icfg.CONFIDENCE_COLUMNS == ("data_confidence", "confidence_score", "confidence_notes")
        assert icfg.DATA_CONFIDENCE_LEVELS == ("high", "medium", "low")
        assert set(icfg.CONFIDENCE_FLAG_COLUMNS) == {"wind", "geographic", "infrastructure", "demand"}
        assert icfg.CONFIDENCE_FLAG_COLUMNS["wind"] == ("wind_confidence", icfg.WIND_CONFIDENCE_LEVELS)
        assert icfg.CONFIDENCE_FLAG_COLUMNS["geographic"] == ("geo_confidence", icfg.GEO_CONFIDENCE_LEVELS)
        assert icfg.CONFIDENCE_NOTE_DELIMITER == "; " and icfg.CONFIDENCE_NO_NOTES == "—"
        assert icfg.CONFIDENCE_SCORE_DECIMALS == 3
        assert icfg.DEFAULT_CONFIDENCE_WEIGHTS_PATH.name == "confidence_weights.yaml"
        assert icfg.CONFIDENCE_METHOD_FILENAME == "confidence_method.md"
        assert icfg.CONFIDENCE_SUMMARY_FILENAME == "confidence_summary.md"
        assert icfg.CELL_DEG == 0.05 and icfg.GRID_ORIGIN_LON == 109.21125

    def test_packaged_yaml_loads_with_s1_10_weights(self):
        from pipeline.integration.confidence import load_weights

        w = load_weights(icfg.DEFAULT_CONFIDENCE_WEIGHTS_PATH)
        assert w.version == "1.0"
        assert w.path == icfg.DEFAULT_CONFIDENCE_WEIGHTS_PATH and len(w.sha256) == 64
        assert [f.name for f in w.features] == list(SCORED)
        weights = {f.name: f.weight for f in w.features}
        assert weights == {
            "wind_speed": 0.35, "dist_transmission_km": 0.20, "demand_proxy": 0.15,
            "dist_substation_km": 0.10, "slope_deg": 0.10, "inside_rez": 0.10,
            "elevation_m": 0.05, "land_use": 0.05, "protected_area": 0.05,
            "dist_connection_km": 0.05,
        }
        assert w.weight_sum == pytest.approx(1.20)
        assert w.thresholds.high == 0.8 and w.thresholds.medium == 0.5
        assert all(f.resolution_basis and f.limitation_basis for f in w.features)
        assert w.feature("demand_proxy").resolution == 0.5
        assert w.feature("demand_proxy").limitation == 0.75
        assert w.max_attainable == pytest.approx(1.04375 / 1.20, abs=1e-6)

    def test_packaged_flag_rules(self):
        from pipeline.integration.confidence import load_weights

        w = load_weights(icfg.DEFAULT_CONFIDENCE_WEIGHTS_PATH)
        rules = {r.layer: r for r in w.flags}
        assert [r.layer for r in w.flags] == ["wind", "geographic", "infrastructure", "demand"]
        assert rules["wind"].column == "wind_confidence"
        assert rules["wind"].factors == {"valid": 1.0, "no_data": 0.0}
        assert rules["geographic"].features == ("elevation_m", "slope_deg", "land_use")
        assert "protected_area" not in rules["geographic"].features
        assert rules["geographic"].factors == {"high": 1.0, "low": 0.5}
        assert rules["infrastructure"].factors == {"high": 1.0, "low": 1.0}
        assert rules["demand"].factors == {"high": 1.0, "medium": 0.75, "low": 0.5}
        assert rules["demand"].notes["medium"] == "Demand region assigned by boundary overlap"
        assert w.layer_of("elevation_m") == "geographic"
        assert w.layer_of("protected_area") is None
        assert len(w.soft_flags) == 1
        assert w.soft_flags[0].match == "Urban-centre data unavailable"
        assert w.soft_flags[0].factor == 1.0


# ---------------------------------------------------------------------------
# Loader validation ladder
# ---------------------------------------------------------------------------


class TestLoadWeights:
    def _err(self):
        from pipeline.integration.confidence import ConfidenceConfigError

        return ConfidenceConfigError

    def test_missing_file(self, tmp_path):
        from pipeline.integration.confidence import load_weights

        with pytest.raises(self._err(), match="not found"):
            load_weights(tmp_path / "nope.yaml")

    def test_invalid_yaml(self, tmp_path):
        from pipeline.integration.confidence import load_weights

        path = _write(tmp_path, "features: [unclosed\n")
        with pytest.raises(self._err(), match="not valid YAML"):
            load_weights(path)

    def test_top_level_must_be_mapping(self, tmp_path):
        from pipeline.integration.confidence import load_weights

        path = _write(tmp_path, "- just\n- a list\n")
        with pytest.raises(self._err(), match="mapping"):
            load_weights(path)

    def test_missing_and_unknown_top_level_keys(self):
        raw = _default_raw()
        del raw["thresholds"]
        with pytest.raises(self._err(), match="missing top-level key.*thresholds"):
            _parse(raw)
        raw = _default_raw()
        raw["extra"] = 1
        with pytest.raises(self._err(), match="unknown top-level key.*extra"):
            _parse(raw)

    def test_version_required(self):
        raw = _default_raw()
        raw["version"] = ""
        with pytest.raises(self._err(), match="version"):
            _parse(raw)

    def test_features_must_match_scored_columns(self):
        raw = _default_raw()
        del raw["features"]["slope_deg"]
        raw["features"]["slopes"] = raw["features"]["elevation_m"]
        with pytest.raises(self._err(), match=r"missing \['slope_deg'\].*unknown \['slopes'\]"):
            _parse(raw)

    @pytest.mark.parametrize("value", [0, -0.1, "0.3", True])
    def test_weight_must_be_positive_number(self, value):
        raw = _default_raw()
        raw["features"]["wind_speed"]["weight"] = value
        with pytest.raises(self._err(), match=r"features\.wind_speed\.weight"):
            _parse(raw)

    @pytest.mark.parametrize("key,value", [("resolution", 0), ("resolution", 1.5),
                                           ("limitation", 0), ("limitation", 2), ("limitation", False)])
    def test_resolution_and_limitation_in_unit_interval(self, key, value):
        raw = _default_raw()
        raw["features"]["land_use"][key] = value
        with pytest.raises(self._err(), match=rf"features\.land_use\.{key}.*\(0, 1\]"):
            _parse(raw)

    def test_feature_note_required(self):
        raw = _default_raw()
        raw["features"]["tri" if False else "elevation_m"]["note"] = ""
        with pytest.raises(self._err(), match=r"features\.elevation_m\.note"):
            _parse(raw)

    def test_feature_unknown_key(self):
        raw = _default_raw()
        raw["features"]["elevation_m"]["weigth"] = 0.1
        with pytest.raises(self._err(), match=r"features\.elevation_m has unknown key.*weigth"):
            _parse(raw)

    def test_flag_layer_must_be_known(self):
        raw = _default_raw()
        raw["flag_factors"]["exclusions"] = {"features": ["wind_speed"], "factors": {"x": 1.0}}
        with pytest.raises(self._err(), match="unknown layer.*exclusions"):
            _parse(raw)

    def test_flag_factors_must_cover_vocabulary_exactly(self):
        raw = _default_raw()
        del raw["flag_factors"]["demand"]["factors"]["medium"]
        with pytest.raises(self._err(), match=r"flag_factors\.demand\.factors.*missing \['medium'\]"):
            _parse(raw)
        raw = _default_raw()
        raw["flag_factors"]["demand"]["factors"]["unknown"] = 0.5
        with pytest.raises(self._err(), match=r"flag_factors\.demand\.factors.*unknown \['unknown'\]"):
            _parse(raw)

    @pytest.mark.parametrize("value", [1.5, -0.1, "1"])
    def test_flag_factor_in_closed_unit_interval(self, value):
        raw = _default_raw()
        raw["flag_factors"]["geographic"]["factors"]["low"] = value
        with pytest.raises(self._err(), match=r"flag_factors\.geographic\.factors\.low.*\[0, 1\]"):
            _parse(raw)

    def test_feature_scoped_under_two_layers(self):
        raw = _default_raw()
        raw["flag_factors"]["wind"]["features"].append("elevation_m")
        with pytest.raises(self._err(), match="elevation_m.*more than one layer"):
            _parse(raw)

    def test_scoped_feature_must_be_scored(self):
        raw = _default_raw()
        raw["flag_factors"]["wind"]["features"] = ["tri"]
        with pytest.raises(self._err(), match=r"flag_factors\.wind\.features.*tri"):
            _parse(raw)

    def test_note_required_when_factor_below_one(self):
        raw = _default_raw()
        del raw["flag_factors"]["geographic"]["notes"]["low"]
        with pytest.raises(self._err(), match=r"flag_factors\.geographic\.notes\.low is required"):
            _parse(raw)

    def test_note_for_unknown_flag_value(self):
        raw = _default_raw()
        raw["flag_factors"]["geographic"]["notes"]["mid"] = "x"
        with pytest.raises(self._err(), match=r"flag_factors\.geographic\.notes.*unknown.*mid"):
            _parse(raw)

    def test_soft_flags_validation(self):
        raw = _default_raw()
        raw["soft_flags"].append({"match": "", "factor": 1.0, "note": "n"})
        with pytest.raises(self._err(), match=r"soft_flags\[1\]\.match"):
            _parse(raw)
        raw = _default_raw()
        raw["soft_flags"].append(dict(raw["soft_flags"][0]))
        with pytest.raises(self._err(), match="duplicate soft_flags match"):
            _parse(raw)
        raw = _default_raw()
        raw["soft_flags"][0]["factor"] = 0
        with pytest.raises(self._err(), match=r"soft_flags\[0\]\.factor.*\(0, 1\]"):
            _parse(raw)
        raw = _default_raw()
        raw["soft_flags"][0]["note"] = ""
        with pytest.raises(self._err(), match=r"soft_flags\[0\]\.note"):
            _parse(raw)

    def test_soft_flags_optional(self):
        raw = _default_raw()
        del raw["soft_flags"]
        assert _parse(raw).soft_flags == ()

    @pytest.mark.parametrize("high,medium", [(1.1, 0.5), (0.8, -0.1), (0.5, 0.5), (0.4, 0.6), ("0.8", 0.5)])
    def test_thresholds_ordering(self, high, medium):
        raw = _default_raw()
        raw["thresholds"] = {"high": high, "medium": medium}
        with pytest.raises(self._err(), match="thresholds"):
            _parse(raw)

    def test_load_records_path_and_sha(self, tmp_path):
        from pipeline.common.geo import sha256_file
        from pipeline.integration.confidence import load_weights

        path = _write(tmp_path, _default_raw())
        w = load_weights(path)
        assert w.path == path and w.sha256 == sha256_file(path)


# ---------------------------------------------------------------------------
# assess() — score, category, notes
# ---------------------------------------------------------------------------

CELL_IDS = ["CELL_CLEAN", "CELL_PROTECTED", "CELL_STEEP", "CELL_NO_GEO", "CELL_NO_NEM", "CELL_PLAIN"]
URBAN_FLAG = "Urban-centre data unavailable outside New England REZ coverage (urban_area defaults to False, not confirmed)"


def six_cells() -> pd.DataFrame:
    """The S1-08 synthetic cells as they appear in the integrated table."""
    return pd.DataFrame({
        "cell_id": CELL_IDS,
        "centroid_lat": [-30.0] * 6,
        "centroid_lon": [150.95 + 0.05 * i for i in range(6)],
        "wind_speed": [7.5, 8.1, 6.9, 7.0, 5.5, 8.4],
        "wind_confidence": ["valid"] * 6,
        "demand_proxy": [1.0, 1.0, 1.0, 1.0, np.nan, 1.0],
        "demand_confidence": ["high", "high", "medium", "high", "low", "high"],
        "dist_transmission_km": [4.2, 19.7, 5.6, 40.0, 60.5, 12.0],
        "dist_substation_km": [11.3, 26.4, 8.9, 55.0, 70.2, 15.5],
        "dist_connection_km": pd.Series([np.nan] * 6, dtype="float64"),
        "inside_rez": [True, False, False, False, False, False],
        "infra_confidence": ["low"] * 6,
        "elevation_m": [650.0, 720.0, 900.0, np.nan, 300.0, 410.0],
        "slope_deg": [3.0, 4.5, 20.0, np.nan, 2.0, 1.5],
        "land_use": ["3.2.0 Grazing modified pastures", "1.1.0 Nature conservation",
                     "3.2.0 Grazing modified pastures", None, "3.3.0 Cropping",
                     "3.2.0 Grazing modified pastures"],
        "protected_area": [False, True, False, False, False, False],
        "geo_confidence": ["high", "high", "high", "low", "high", "high"],
        "eligible": [True, False, False, False, True, True],
        "data_flags": [None, None, None, URBAN_FLAG, None, None],
    })


EXPECTED_SCORES = [0.830, 0.830, 0.818, 0.680, 0.783, 0.830]
EXPECTED_LEVELS = ["high", "high", "high", "medium", "medium", "high"]
EXPECTED_NOTES = [
    "Missing connection-point distance",
    "Missing connection-point distance",
    "Missing connection-point distance; Demand region assigned by boundary overlap",
    "Missing connection-point distance; Missing elevation; Missing slope; Missing land use; "
    "Urban-centre coverage unconfirmed (outside ABS UCL window)",
    "Missing demand proxy; Missing connection-point distance",
    "Missing connection-point distance",
]


@pytest.fixture
def weights():
    from pipeline.integration.confidence import load_weights

    return load_weights(icfg.DEFAULT_CONFIDENCE_WEIGHTS_PATH)


class TestAssess:
    def test_six_cells_exact(self, weights):
        from pipeline.integration.confidence import assess

        out = assess(six_cells(), weights)
        assert list(out.columns) == list(icfg.CONFIDENCE_COLUMNS)
        assert out["confidence_score"].tolist() == EXPECTED_SCORES
        assert out["data_confidence"].tolist() == EXPECTED_LEVELS
        assert out["confidence_notes"].tolist() == EXPECTED_NOTES
        assert out["confidence_score"].dtype == "float64"

    def test_index_aligned_and_input_not_mutated(self, weights):
        from pipeline.integration.confidence import assess

        table = six_cells()
        table.index = [10, 20, 30, 40, 50, 60]
        before = table.copy(deep=True)
        out = assess(table, weights)
        assert list(out.index) == [10, 20, 30, 40, 50, 60]
        pd.testing.assert_frame_equal(table, before)

    def test_missing_column_raises(self, weights):
        from pipeline.integration.confidence import assess

        with pytest.raises(ValueError, match="geo_confidence"):
            assess(six_cells().drop(columns=["geo_confidence"]), weights)

    def test_no_notes_when_everything_present(self, weights):
        from pipeline.integration.confidence import assess

        table = six_cells()
        table.loc[0, "dist_connection_km"] = 3.0
        out = assess(table, weights)
        assert out.loc[0, "confidence_notes"] == icfg.CONFIDENCE_NO_NOTES
        assert out.loc[0, "confidence_score"] == pytest.approx(round(weights.max_attainable, 3))
        assert out.loc[0, "data_confidence"] == "high"

    @pytest.mark.parametrize("bad", [None, "unknown"])
    def test_null_or_unknown_flag_zeroes_present_features_and_notes(self, weights, bad):
        from pipeline.integration.confidence import assess

        table = six_cells()
        table.loc[0, "wind_confidence"] = bad
        out = assess(table, weights)
        assert out.loc[0, "confidence_score"] == 0.553   # (0.99625 - 0.3325) / 1.2
        assert out.loc[0, "data_confidence"] == "medium"
        assert out.loc[0, "confidence_notes"] == (
            "Missing connection-point distance; wind_confidence outside vocabulary"
        )

    def test_bad_flag_with_feature_absent_adds_no_note(self, weights):
        from pipeline.integration.confidence import assess

        table = six_cells()
        table.loc[4, "demand_confidence"] = None   # CELL_NO_NEM: demand_proxy is null anyway
        out = assess(table, weights)
        assert out.loc[4, "confidence_notes"] == EXPECTED_NOTES[4]
        assert out.loc[4, "confidence_score"] == EXPECTED_SCORES[4]

    def test_soft_flag_factor_scales_whole_score(self):
        from pipeline.integration.confidence import assess

        raw = _default_raw()
        raw["soft_flags"][0]["factor"] = 0.9
        out = assess(six_cells(), _parse(raw))
        assert out.loc[3, "confidence_score"] == 0.612   # 0.68021 * 0.9
        assert out.loc[0, "confidence_score"] == 0.830   # unaffected

    def test_flag_note_only_when_factor_below_one(self):
        from pipeline.integration.confidence import assess

        raw = _default_raw()
        raw["flag_factors"]["demand"]["factors"]["medium"] = 1.0
        out = assess(six_cells(), _parse(raw))
        assert out.loc[2, "confidence_notes"] == "Missing connection-point distance"
        assert out.loc[2, "confidence_score"] == 0.830

    def test_geo_low_halves_present_geo_features_only(self, weights):
        from pipeline.integration.confidence import assess

        table = six_cells()
        table.loc[3, ["elevation_m", "slope_deg"]] = [500.0, 2.0]   # land_use still null, geo low
        out = assess(table, weights)
        # 0.81625 + 0.5*(0.045 + 0.09) = 0.88375 -> /1.2
        assert out.loc[3, "confidence_score"] == 0.736
        assert out.loc[3, "confidence_notes"] == (
            "Missing connection-point distance; Missing land use; "
            "Geographic rasters partly covered (geo_confidence low); "
            "Urban-centre coverage unconfirmed (outside ABS UCL window)"
        )


# ---------------------------------------------------------------------------
# Property-based tests
# ---------------------------------------------------------------------------

hypothesis = pytest.importorskip("hypothesis")
from hypothesis import given, settings, strategies as st  # noqa: E402

LEVEL_RANK = {"low": 0, "medium": 1, "high": 2}
_opt_float = st.one_of(st.none(), st.floats(min_value=0, max_value=100, allow_nan=False))
_opt_bool = st.one_of(st.none(), st.booleans())
_opt_text = st.one_of(st.none(), st.sampled_from(["a", "b"]))


@st.composite
def random_table(draw, n=None):
    n = n if n is not None else draw(st.integers(min_value=1, max_value=8))
    rows = {"cell_id": [f"C{i}" for i in range(n)]}
    for col in SCORED:
        if col in ("inside_rez", "protected_area"):
            rows[col] = pd.array(draw(st.lists(_opt_bool, min_size=n, max_size=n)), dtype="boolean")
        elif col == "land_use":
            rows[col] = draw(st.lists(_opt_text, min_size=n, max_size=n))
        else:
            rows[col] = pd.Series(draw(st.lists(_opt_float, min_size=n, max_size=n)), dtype="float64")
    for layer, (column, vocab) in icfg.CONFIDENCE_FLAG_COLUMNS.items():
        rows[column] = draw(st.lists(st.sampled_from(list(vocab) + [None, "bogus"]), min_size=n, max_size=n))
    rows["data_flags"] = draw(st.lists(st.sampled_from([None, URBAN_FLAG, "other"]), min_size=n, max_size=n))
    rows["eligible"] = draw(st.lists(st.booleans(), min_size=n, max_size=n))
    return pd.DataFrame(rows)


@st.composite
def random_weights(draw):
    raw = _default_raw()
    for name in SCORED:
        raw["features"][name]["weight"] = draw(st.floats(min_value=0.01, max_value=1, allow_nan=False))
        raw["features"][name]["resolution"] = draw(st.floats(min_value=0.05, max_value=1, allow_nan=False))
        raw["features"][name]["limitation"] = draw(st.floats(min_value=0.05, max_value=1, allow_nan=False))
    for layer, spec in raw["flag_factors"].items():
        for value in list(spec["factors"]):
            spec["factors"][value] = draw(st.floats(min_value=0, max_value=1, allow_nan=False))
            spec.setdefault("notes", {})[value] = f"{layer} {value} note"
    raw["soft_flags"][0]["factor"] = draw(st.floats(min_value=0.05, max_value=1, allow_nan=False))
    medium = draw(st.floats(min_value=0, max_value=0.98, allow_nan=False))
    high = draw(st.floats(min_value=medium + 0.01, max_value=1, allow_nan=False))
    raw["thresholds"] = {"high": high, "medium": medium}
    return _parse(raw)


class TestProperties:
    # Feature: s1-09-data-quality-and-confidence, Property 1: the raw and
    # rounded scores always lie in [0, 1], for any table and any valid config.
    @settings(max_examples=100, deadline=None)
    @given(table=random_table(), w=random_weights())
    def test_property_1_score_in_unit_interval(self, table, w):
        from pipeline.integration.confidence import assess, score_raw

        raw = score_raw(table, w)
        assert np.all((raw >= 0) & (raw <= 1))
        out = assess(table, w)
        assert out["confidence_score"].between(0, 1).all()
        assert out["confidence_score"].notna().all()

    # Feature: s1-09-data-quality-and-confidence, Property 2: nulling any one
    # present scored value never increases the raw score nor raises the level.
    @settings(max_examples=100, deadline=None)
    @given(table=random_table(), w=random_weights(), data=st.data())
    def test_property_2_nulling_a_feature_is_monotone(self, table, w, data):
        from pipeline.integration.confidence import assess, score_raw

        row = data.draw(st.integers(min_value=0, max_value=len(table) - 1))
        col = data.draw(st.sampled_from(list(SCORED)))
        before_raw = score_raw(table, w)[row]
        before_level = assess(table, w).loc[row, "data_confidence"]
        nulled = table.copy()
        nulled.loc[row, col] = None if col in ("inside_rez", "protected_area", "land_use") else np.nan
        assert score_raw(nulled, w)[row] <= before_raw + 1e-12
        after_level = assess(nulled, w).loc[row, "data_confidence"]
        assert LEVEL_RANK[after_level] <= LEVEL_RANK[before_level]

    # Feature: s1-09-data-quality-and-confidence, Property 3: categorise()
    # matches the threshold definition, including the inclusive boundaries.
    @settings(max_examples=100, deadline=None)
    @given(scores=st.lists(st.floats(min_value=0, max_value=1, allow_nan=False), min_size=1, max_size=20),
           w=random_weights())
    def test_property_3_categories_match_thresholds(self, scores, w):
        from pipeline.integration.confidence import categorise

        t = w.thresholds
        expected = ["high" if s >= t.high else "medium" if s >= t.medium else "low" for s in scores]
        assert list(categorise(np.array(scores), t)) == expected
        assert list(categorise(np.array([t.high, t.medium]), t)) == ["high", "medium"]

    # Feature: s1-09-data-quality-and-confidence, Property 4: scaling every
    # weight by the same positive factor leaves the raw score unchanged.
    @settings(max_examples=100, deadline=None)
    @given(table=random_table(), w=random_weights(), k=st.floats(min_value=0.01, max_value=100, allow_nan=False))
    def test_property_4_weights_scale_invariant(self, table, w, k):
        from dataclasses import replace
        from pipeline.integration.confidence import score_raw

        scaled = replace(w, features=tuple(replace(f, weight=f.weight * k) for f in w.features))
        np.testing.assert_allclose(score_raw(table, scaled), score_raw(table, w), rtol=0, atol=1e-9)

    # Feature: s1-09-data-quality-and-confidence, Property 5: permuting the
    # rows permutes the output identically (index-aligned, no cross-talk).
    @settings(max_examples=100, deadline=None)
    @given(table=random_table(n=6), w=random_weights(), perm=st.permutations(list(range(6))))
    def test_property_5_row_permutation_invariance(self, table, w, perm):
        from pipeline.integration.confidence import assess

        reference = assess(table, w)
        shuffled = assess(table.iloc[perm], w)
        pd.testing.assert_frame_equal(shuffled.sort_index(), reference)

    # Feature: s1-09-data-quality-and-confidence, Property 6: a feature's
    # missing-note appears in confidence_notes iff that feature is null.
    @settings(max_examples=100, deadline=None)
    @given(table=random_table(), w=random_weights())
    def test_property_6_missing_note_iff_null(self, table, w):
        from pipeline.integration.confidence import assess

        out = assess(table, w)
        for i in range(len(table)):
            notes = out.loc[i, "confidence_notes"].split(icfg.CONFIDENCE_NOTE_DELIMITER)
            for f in w.features:
                assert (f.note in notes) == bool(pd.isna(table.loc[i, f.name])), (f.name, notes)
