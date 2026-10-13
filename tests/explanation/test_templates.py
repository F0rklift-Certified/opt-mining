"""
Tests for the S2-06a explanation template/rule loader.

Templates are DATA: the loader validates them the way scoring.weights
validates the weights file, failing before any output on every fault path.
Everything runs on tiny YAML under tmp_path or in-memory dicts.

Feature: s2-06a-explanation-engine-eligible-cells
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

from pipeline.explanation import config as ecfg  # noqa: E402
from pipeline.explanation.templates import (  # noqa: E402
    BANNED_SUPERLATIVES,
    ExplanationConfigError,
    ExplanationTemplates,
    load_templates,
    parse_templates,
)

_DEFAULT_RAW = yaml.safe_load(ecfg.DEFAULT_TEMPLATES_PATH.read_text(encoding="utf-8"))


def _default_raw() -> dict:
    return copy.deepcopy(_DEFAULT_RAW)


def _write(tmp_path: Path, obj, name="templates.yaml") -> Path:
    path = tmp_path / name
    path.write_text(
        obj if isinstance(obj, str) else yaml.safe_dump(obj), encoding="utf-8"
    )
    return path


# --- The shipped file loads and is well-formed ------------------------------


def test_shipped_templates_load():
    t = load_templates(ecfg.DEFAULT_TEMPLATES_PATH)
    assert isinstance(t, ExplanationTemplates)
    assert t.headline
    assert "best site" not in t.headline.lower()
    # One phrase per default scoring criterion.
    assert set(t.phrases) == {
        "wind_speed", "dist_transmission_km", "demand_proxy",
        "dist_substation_km", "slope_deg", "inside_rez",
    }
    assert t.config_id  # SHA-256 of the file


def test_bands_sorted_descending_and_cover_zero():
    t = load_templates(ecfg.DEFAULT_TEMPLATES_PATH)
    mins = [b.min_norm for b in t.bands]
    assert mins == sorted(mins, reverse=True)
    assert min(mins) == 0.0


def test_band_label_mapping_picks_the_tightest_band():
    t = load_templates(ecfg.DEFAULT_TEMPLATES_PATH)
    assert t.band_label(0.95) == "top decile"
    assert t.band_label(0.9) == "top decile"
    assert t.band_label(0.7) == "strong"
    assert t.band_label(0.4) == "moderate"
    assert t.band_label(0.0) == "limited"


def test_config_id_is_sha256_of_bytes(tmp_path):
    from pipeline.common.geo import sha256_file
    path = _write(tmp_path, _default_raw())
    assert load_templates(path).config_id == sha256_file(path)


# --- Fault paths: every one fails before anything is produced ---------------


def test_missing_file_raises():
    with pytest.raises(ExplanationConfigError, match="not found"):
        load_templates(Path("/no/such/templates.yaml"))


def test_unparsable_yaml_raises(tmp_path):
    path = _write(tmp_path, "headline: [unterminated\n")
    with pytest.raises(ExplanationConfigError, match="not valid YAML"):
        load_templates(path)


def test_empty_file_raises(tmp_path):
    path = _write(tmp_path, "")
    with pytest.raises(ExplanationConfigError, match="empty"):
        load_templates(path)


def test_missing_headline_raises():
    raw = _default_raw()
    del raw["headline"]
    with pytest.raises(ExplanationConfigError, match="headline"):
        parse_templates(raw)


def test_empty_headline_raises():
    raw = _default_raw()
    raw["headline"] = "   "
    with pytest.raises(ExplanationConfigError, match="headline"):
        parse_templates(raw)


def test_superlative_headline_raises():
    raw = _default_raw()
    raw["headline"] = "The best site under the selected assumptions"
    with pytest.raises(ExplanationConfigError, match="best site"):
        parse_templates(raw)


def test_missing_criterion_phrase_raises():
    raw = _default_raw()
    raw["criteria"] = [c for c in raw["criteria"] if c["feature"] != "wind_speed"]
    # It parses (no 'wind_speed' entry), but phrases_for() fails loudly.
    t = parse_templates(raw)
    with pytest.raises(ExplanationConfigError, match="wind_speed"):
        t.phrases_for("wind_speed")


def test_empty_criterion_phrase_raises():
    raw = _default_raw()
    raw["criteria"][0]["positive"] = ""
    with pytest.raises(ExplanationConfigError, match="positive"):
        parse_templates(raw)


def test_band_threshold_out_of_range_raises():
    raw = _default_raw()
    raw["bands"][0]["min_norm"] = 1.5
    with pytest.raises(ExplanationConfigError, match="outside"):
        parse_templates(raw)


def test_lowest_band_must_be_zero():
    raw = _default_raw()
    for band in raw["bands"]:
        if band["min_norm"] == 0.0:
            band["min_norm"] = 0.1
    with pytest.raises(ExplanationConfigError, match="0.0"):
        parse_templates(raw)


def test_duplicate_criterion_phrase_raises():
    raw = _default_raw()
    raw["criteria"].append(dict(raw["criteria"][0]))
    with pytest.raises(ExplanationConfigError, match="duplicate"):
        parse_templates(raw)


def test_superlative_in_phrase_raises():
    raw = _default_raw()
    raw["criteria"][0]["positive"] = "The optimal site for wind"
    with pytest.raises(ExplanationConfigError, match="optimal site"):
        parse_templates(raw)


def test_banned_list_nonempty():
    # Guard: the banned vocabulary is not accidentally emptied.
    assert "best site" in BANNED_SUPERLATIVES


# --- S2-06b: proxy marker + data-quality block ------------------------------


def test_shipped_demand_proxy_is_marked_and_carries_a_caveat():
    t = load_templates(ecfg.DEFAULT_TEMPLATES_PATH)
    demand = t.phrases["demand_proxy"]
    assert demand.is_proxy is True
    assert demand.proxy_caveat
    assert "proxy" in demand.proxy_caveat.lower()
    # A non-proxy criterion defaults to not-a-proxy, no caveat.
    assert t.phrases["wind_speed"].is_proxy is False
    assert t.phrases["wind_speed"].proxy_caveat is None


def test_shipped_data_quality_block_parsed():
    t = load_templates(ecfg.DEFAULT_TEMPLATES_PATH)
    assert "{level}" in t.data_quality.level_template
    assert "{level_note}" in t.data_quality.notes_template
    assert "{notes}" in t.data_quality.notes_template


def test_proxy_true_without_caveat_raises():
    raw = _default_raw()
    for c in raw["criteria"]:
        if c["feature"] == "demand_proxy":
            c["proxy"] = True
            c.pop("proxy_caveat", None)
    with pytest.raises(ExplanationConfigError, match="proxy_caveat"):
        parse_templates(raw)


def test_caveat_on_non_proxy_criterion_raises():
    raw = _default_raw()
    raw["criteria"][0]["proxy_caveat"] = "some caveat"  # wind_speed, not a proxy
    with pytest.raises(ExplanationConfigError, match="not marked 'proxy: true'"):
        parse_templates(raw)


def test_non_boolean_proxy_marker_raises():
    raw = _default_raw()
    raw["criteria"][0]["proxy"] = "yes"
    with pytest.raises(ExplanationConfigError, match="must be true or false"):
        parse_templates(raw)


def test_superlative_in_proxy_caveat_raises():
    raw = _default_raw()
    for c in raw["criteria"]:
        if c["feature"] == "demand_proxy":
            c["proxy_caveat"] = "The best site for demand"
    with pytest.raises(ExplanationConfigError, match="best site"):
        parse_templates(raw)


def test_missing_data_quality_block_raises():
    raw = _default_raw()
    del raw["data_quality"]
    with pytest.raises(ExplanationConfigError, match="data_quality"):
        parse_templates(raw)


def test_level_template_without_placeholder_raises():
    raw = _default_raw()
    raw["data_quality"]["level_template"] = "Confidence level"
    with pytest.raises(ExplanationConfigError, match=r"\{level\}"):
        parse_templates(raw)


def test_notes_template_missing_placeholder_raises():
    raw = _default_raw()
    raw["data_quality"]["notes_template"] = "{level_note} only"
    with pytest.raises(ExplanationConfigError, match=r"\{notes\}"):
        parse_templates(raw)


def test_superlative_in_data_quality_raises():
    raw = _default_raw()
    raw["data_quality"]["level_template"] = "best site confidence {level}"
    with pytest.raises(ExplanationConfigError, match="best site"):
        parse_templates(raw)
