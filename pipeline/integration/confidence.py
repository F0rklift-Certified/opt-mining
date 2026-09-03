"""
S1-09 — Data quality and confidence layer.

Derives a per-cell composite confidence from the Integrated NSW Feature Table
(S1-08): the availability of the ten scored features, each source's spatial
resolution relative to the 0.05° analysis cell and its documented limitations
(S1-01 data specification), the upstream per-layer confidence flags, and
S1-07's soft data flags. Weights, factors and thresholds are DATA loaded from
`confidence_weights.yaml` (see that file for the formula); this module has no
built-in notion of what any feature means.

Appends three columns to the integrated table via merge.attach_confidence():
    data_confidence   high | medium | low
    confidence_score  float 0-1, 3 dp
    confidence_notes  '; '-joined reasons for reduced confidence, '—' when none

This is a metadata/quality layer, not a filter: no cell is ever dropped.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import yaml

from . import config
from ..common.geo import sha256_file


class ConfidenceConfigError(ValueError):
    """
    Raised when the confidence weights file is missing or malformed. A
    malformed config must halt the run loudly — scoring cells against a
    partial or mis-parsed weight set would silently misstate confidence,
    which the Constitution forbids ("never let poor data pass as good").
    """


# ---------------------------------------------------------------------------
# Config model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FeatureWeight:
    name: str
    weight: float
    resolution: float
    limitation: float
    note: str
    resolution_basis: str = ""
    limitation_basis: str = ""

    @property
    def factor(self) -> float:
        """resolution × limitation — the feature's contribution when present."""
        return self.resolution * self.limitation


@dataclass(frozen=True)
class FlagRule:
    layer: str
    column: str
    features: tuple[str, ...]
    factors: dict[str, float]
    notes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class SoftFlag:
    match: str
    factor: float
    note: str


@dataclass(frozen=True)
class Thresholds:
    high: float
    medium: float


@dataclass(frozen=True)
class Weights:
    version: str
    features: tuple[FeatureWeight, ...]      # in SCORED_FEATURE_COLUMNS order
    flags: tuple[FlagRule, ...]              # in CONFIDENCE_FLAG_COLUMNS order
    soft_flags: tuple[SoftFlag, ...]
    thresholds: Thresholds
    path: Path | None = None
    sha256: str | None = None

    @property
    def weight_sum(self) -> float:
        return sum(f.weight for f in self.features)

    def feature(self, name: str) -> FeatureWeight:
        for f in self.features:
            if f.name == name:
                return f
        raise KeyError(name)

    def layer_of(self, feature: str) -> str | None:
        for rule in self.flags:
            if feature in rule.features:
                return rule.layer
        return None

    @property
    def max_attainable(self) -> float:
        """Score of a cell with every feature present and every flag at 1.0."""
        return sum(f.weight * f.factor for f in self.features) / self.weight_sum


# ---------------------------------------------------------------------------
# Loader — validate eagerly, name the offending key
# ---------------------------------------------------------------------------

_TOP_LEVEL_REQUIRED = ("version", "thresholds", "features", "flag_factors")
_TOP_LEVEL_OPTIONAL = ("soft_flags",)
_FEATURE_REQUIRED = ("weight", "resolution", "limitation", "note")
_FEATURE_OPTIONAL = ("resolution_basis", "limitation_basis")


def _number(value) -> float | None:
    """A real number (never a bool, which YAML parses as an int subclass)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _require_text(value, what: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfidenceConfigError(f"{what} must be a non-empty string")
    return value


def _require_mapping(value, what: str) -> dict:
    if not isinstance(value, dict):
        raise ConfidenceConfigError(f"{what} must be a mapping")
    return value


def _unit_interval(value, what: str, *, closed_low: bool) -> float:
    number = _number(value)
    interval = "[0, 1]" if closed_low else "(0, 1]"
    if number is None or number > 1 or number < 0 or (number == 0 and not closed_low):
        raise ConfidenceConfigError(f"{what} must be a number in {interval} (got {value!r})")
    return number


def _parse_feature(name: str, raw) -> FeatureWeight:
    spec = _require_mapping(raw, f"features.{name}")
    unknown = sorted(set(spec) - set(_FEATURE_REQUIRED) - set(_FEATURE_OPTIONAL))
    if unknown:
        raise ConfidenceConfigError(f"features.{name} has unknown key(s) {unknown}")
    missing = [k for k in _FEATURE_REQUIRED if k not in spec]
    if missing:
        raise ConfidenceConfigError(f"features.{name} is missing key(s) {missing}")
    weight = _number(spec["weight"])
    if weight is None or weight <= 0:
        raise ConfidenceConfigError(
            f"features.{name}.weight must be a number > 0 (got {spec['weight']!r})"
        )
    return FeatureWeight(
        name=name,
        weight=weight,
        resolution=_unit_interval(spec["resolution"], f"features.{name}.resolution", closed_low=False),
        limitation=_unit_interval(spec["limitation"], f"features.{name}.limitation", closed_low=False),
        note=_require_text(spec["note"], f"features.{name}.note"),
        resolution_basis=str(spec.get("resolution_basis", "") or ""),
        limitation_basis=str(spec.get("limitation_basis", "") or ""),
    )


def _parse_flag_rule(layer: str, raw, scoped: dict[str, str]) -> FlagRule:
    column, vocabulary = config.CONFIDENCE_FLAG_COLUMNS[layer]
    spec = _require_mapping(raw, f"flag_factors.{layer}")
    unknown = sorted(set(spec) - {"features", "factors", "notes"})
    if unknown:
        raise ConfidenceConfigError(f"flag_factors.{layer} has unknown key(s) {unknown}")

    features = spec.get("features")
    if not isinstance(features, list) or not features or not all(
        isinstance(f, str) and f in config.SCORED_FEATURE_COLUMNS for f in features
    ):
        raise ConfidenceConfigError(
            f"flag_factors.{layer}.features must be a non-empty list of scored feature "
            f"columns (got {features!r})"
        )
    for feature in features:
        if feature in scoped:
            raise ConfidenceConfigError(
                f"feature {feature!r} is scoped under more than one layer "
                f"({scoped[feature]} and {layer})"
            )
        scoped[feature] = layer

    factors_raw = _require_mapping(spec.get("factors"), f"flag_factors.{layer}.factors")
    missing = [v for v in vocabulary if v not in factors_raw]
    extra = sorted(set(factors_raw) - set(vocabulary))
    if missing or extra:
        raise ConfidenceConfigError(
            f"flag_factors.{layer}.factors must map exactly the vocabulary {tuple(vocabulary)}; "
            f"missing {missing}; unknown {extra}"
        )
    factors = {
        value: _unit_interval(factors_raw[value], f"flag_factors.{layer}.factors.{value}", closed_low=True)
        for value in vocabulary
    }

    notes_raw = spec.get("notes") or {}
    notes_raw = _require_mapping(notes_raw, f"flag_factors.{layer}.notes")
    unknown_notes = sorted(set(notes_raw) - set(vocabulary))
    if unknown_notes:
        raise ConfidenceConfigError(
            f"flag_factors.{layer}.notes has unknown value(s) {unknown_notes}"
        )
    notes = {value: _require_text(text, f"flag_factors.{layer}.notes.{value}")
             for value, text in notes_raw.items()}
    for value, factor in factors.items():
        if factor < 1 and value not in notes:
            raise ConfidenceConfigError(
                f"flag_factors.{layer}.notes.{value} is required because its factor is < 1"
            )
    return FlagRule(layer=layer, column=column, features=tuple(features),
                    factors=factors, notes=notes)


def _parse_soft_flags(raw) -> tuple[SoftFlag, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise ConfidenceConfigError("soft_flags must be a list")
    flags: list[SoftFlag] = []
    seen: set[str] = set()
    for i, item in enumerate(raw):
        spec = _require_mapping(item, f"soft_flags[{i}]")
        unknown = sorted(set(spec) - {"match", "factor", "note"})
        if unknown:
            raise ConfidenceConfigError(f"soft_flags[{i}] has unknown key(s) {unknown}")
        match = _require_text(spec.get("match"), f"soft_flags[{i}].match")
        if match in seen:
            raise ConfidenceConfigError(f"duplicate soft_flags match {match!r}")
        seen.add(match)
        flags.append(SoftFlag(
            match=match,
            factor=_unit_interval(spec.get("factor"), f"soft_flags[{i}].factor", closed_low=False),
            note=_require_text(spec.get("note"), f"soft_flags[{i}].note"),
        ))
    return tuple(flags)


def _parse_thresholds(raw) -> Thresholds:
    spec = _require_mapping(raw, "thresholds")
    high, medium = _number(spec.get("high")), _number(spec.get("medium"))
    if high is None or medium is None or not (1 >= high > medium >= 0):
        raise ConfidenceConfigError(
            f"thresholds must satisfy 1 >= high > medium >= 0 (got high={spec.get('high')!r}, "
            f"medium={spec.get('medium')!r})"
        )
    return Thresholds(high=high, medium=medium)


def parse_weights(raw, *, path: Path | None = None, sha256: str | None = None) -> Weights:
    """Validate a parsed YAML document and build the Weights model."""
    top = _require_mapping(raw, "Confidence weights config (top level)")
    unknown = sorted(set(top) - set(_TOP_LEVEL_REQUIRED) - set(_TOP_LEVEL_OPTIONAL))
    if unknown:
        raise ConfidenceConfigError(f"unknown top-level key(s) {unknown}")
    missing = [k for k in _TOP_LEVEL_REQUIRED if k not in top]
    if missing:
        raise ConfidenceConfigError(f"missing top-level key(s) {missing}")

    version = _require_text(top["version"], "'version'")
    thresholds = _parse_thresholds(top["thresholds"])

    features_raw = _require_mapping(top["features"], "'features'")
    expected = set(config.SCORED_FEATURE_COLUMNS)
    if set(features_raw) != expected:
        raise ConfidenceConfigError(
            "'features' must define exactly the scored feature columns; "
            f"missing {sorted(expected - set(features_raw))}; "
            f"unknown {sorted(set(features_raw) - expected)}"
        )
    features = tuple(_parse_feature(name, features_raw[name]) for name in config.SCORED_FEATURE_COLUMNS)

    flags_raw = _require_mapping(top["flag_factors"], "'flag_factors'")
    unknown_layers = sorted(set(flags_raw) - set(config.CONFIDENCE_FLAG_COLUMNS))
    if unknown_layers:
        raise ConfidenceConfigError(f"flag_factors has unknown layer(s) {unknown_layers}")
    scoped: dict[str, str] = {}
    flags = tuple(
        _parse_flag_rule(layer, flags_raw[layer], scoped)
        for layer in config.CONFIDENCE_FLAG_COLUMNS if layer in flags_raw
    )

    return Weights(
        version=version,
        features=features,
        flags=flags,
        soft_flags=_parse_soft_flags(top.get("soft_flags")),
        thresholds=thresholds,
        path=path,
        sha256=sha256,
    )


def load_weights(path: Path) -> Weights:
    """Load and validate a confidence weights YAML file."""
    path = Path(path)
    if not path.exists():
        raise ConfidenceConfigError(f"Confidence weights file not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfidenceConfigError(f"{path} is not valid YAML: {exc}") from exc
    return parse_weights(raw, path=path, sha256=sha256_file(path))
