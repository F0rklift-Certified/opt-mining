"""
Criteria weights — loading and validation (S1-10, Requirements 2 and 3).

Weights, directions and rationales are USER INPUTS read from a YAML file at
runtime. No weight literal appears in this module or anywhere else in
`pipeline/scoring/`; `load_weights` is the only way the model learns what to
prioritise. This mirrors `pipeline/integration/confidence.py::load_weights`
(S1-09) and `pipeline/exclusions/rules.py` (S1-07), both of which treat their
tuning parameters as data.

Every validation here runs BEFORE the stage reads the feature table or writes
anything, so a malformed config fails the run without leaving a partial or
stale output behind.
"""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from pathlib import Path

import yaml

from ..common.geo import sha256_file
from . import config


class ScoringConfigError(ValueError):
    """
    A weights configuration is missing, unparsable or invalid.

    Subclasses ValueError so callers that catch ValueError (the pipeline's
    convention for bad input data) still catch it, while `except
    ScoringConfigError` can distinguish a config fault from a data fault.
    """


@dataclass(frozen=True)
class Criterion:
    """One scored criterion: a feature column, its weight and its direction."""

    feature: str  # a column of the integrated feature table
    weight: float  # non-negative; relative, not absolute
    direction: str  # config.HIGHER_IS_BETTER | config.LOWER_IS_BETTER
    rationale: str  # non-empty; why this weight and direction

    @property
    def contribution_column(self) -> str:
        """Stable, documented contribution-column name: `contrib_{feature}`."""
        return f"{config.CONTRIBUTION_PREFIX}{self.feature}"


@dataclass(frozen=True)
class WeightsConfig:
    """A validated weights configuration and the identity of its source file."""

    criteria: tuple[Criterion, ...]
    confidence_discount: bool
    confidence_factors: dict[str, float]
    config_id: str  # SHA-256 of the source YAML — the traceable weights identity
    version: str | None = None
    path: Path | None = None

    @property
    def weight_sum(self) -> float:
        """Sum of all configured weights (the score's denominator when no value is null)."""
        return float(sum(c.weight for c in self.criteria))

    @property
    def features(self) -> tuple[str, ...]:
        """The feature columns this config scores, in configured order."""
        return tuple(c.feature for c in self.criteria)

    @property
    def contribution_columns(self) -> tuple[str, ...]:
        """One contribution column per criterion, in configured order."""
        return tuple(c.contribution_column for c in self.criteria)

    def factor_for(self, confidence: object) -> float:
        """
        Confidence_Factor for a cell, or 1.0 when discounting is disabled.

        An unmapped or null confidence value falls back to 1.0 (no discount)
        rather than to an invented penalty: the vocabulary itself is checked
        by validation, so an unexpected value surfaces there as an explicit
        failure instead of being silently converted into a score haircut.
        """
        if not self.confidence_discount:
            return 1.0
        return float(self.confidence_factors.get(confidence, 1.0))


def _require_mapping(raw: object, path: Path) -> dict:
    if raw is None:
        raise ScoringConfigError(f"{path} is empty — expected a YAML mapping")
    if not isinstance(raw, dict):
        raise ScoringConfigError(
            f"{path} must be a YAML mapping at the top level, got {type(raw).__name__}"
        )
    return raw


def _parse_weight(value: object, feature: str, path: Path) -> float:
    """Weight must be a non-negative real number (Requirement 2.7)."""
    # bool is a subclass of int in Python; a boolean weight is a config
    # mistake, not a 0/1 weight, so it is rejected explicitly.
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ScoringConfigError(
            f"{path}: criterion '{feature}' has a non-numeric weight "
            f"{value!r} ({type(value).__name__}); expected a non-negative number"
        )
    weight = float(value)
    if weight != weight:  # NaN
        raise ScoringConfigError(
            f"{path}: criterion '{feature}' has a NaN weight; expected a non-negative number"
        )
    if weight < 0:
        raise ScoringConfigError(
            f"{path}: criterion '{feature}' has a negative weight {weight}; "
            f"weights must be non-negative"
        )
    return weight


def _parse_criterion(entry: object, index: int, path: Path) -> Criterion:
    if not isinstance(entry, dict):
        raise ScoringConfigError(
            f"{path}: criteria[{index}] must be a mapping with feature/weight/"
            f"direction/rationale, got {type(entry).__name__}"
        )
    feature = entry.get("feature")
    if not isinstance(feature, str) or not feature.strip():
        raise ScoringConfigError(
            f"{path}: criteria[{index}] is missing a non-empty 'feature' name"
        )
    feature = feature.strip()

    if "weight" not in entry:
        raise ScoringConfigError(f"{path}: criterion '{feature}' has no 'weight'")
    weight = _parse_weight(entry["weight"], feature, path)

    direction = entry.get("direction")
    if direction not in config.DIRECTIONS:
        raise ScoringConfigError(
            f"{path}: criterion '{feature}' has invalid direction {direction!r}; "
            f"expected one of {' or '.join(config.DIRECTIONS)}"
        )

    rationale = entry.get("rationale")
    if not isinstance(rationale, str) or not rationale.strip():
        raise ScoringConfigError(
            f"{path}: criterion '{feature}' has no non-empty 'rationale'. Every "
            f"weight must carry a written justification a reviewer can challenge."
        )

    return Criterion(
        feature=feature,
        weight=weight,
        direction=direction,
        rationale=" ".join(rationale.split()),
    )


def _parse_confidence_factors(raw: object, path: Path) -> dict[str, float]:
    """Confidence -> multiplier map, validated against the S1-09 vocabulary."""
    if raw is None:
        return {level: 1.0 for level in config.CONFIDENCE_LEVELS}
    if not isinstance(raw, dict):
        raise ScoringConfigError(
            f"{path}: 'confidence_factors' must be a mapping of confidence value "
            f"to multiplier, got {type(raw).__name__}"
        )
    factors: dict[str, float] = {}
    for level, value in raw.items():
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ScoringConfigError(
                f"{path}: confidence_factors['{level}'] is non-numeric ({value!r})"
            )
        factor = float(value)
        if not 0.0 <= factor <= 1.0:
            raise ScoringConfigError(
                f"{path}: confidence_factors['{level}'] = {factor} is outside [0, 1]; "
                f"a discount may reduce a score, never inflate it"
            )
        factors[str(level)] = factor
    return factors


def parse_weights(
    raw: object,
    *,
    path: Path | None = None,
    config_id: str = "",
) -> WeightsConfig:
    """
    Validate an already-parsed YAML mapping into a WeightsConfig.

    Split from `load_weights` so tests can exercise every fault path on an
    in-memory dict without writing files (the same split S1-09 uses).
    """
    where = path if path is not None else Path("<in-memory config>")
    body = _require_mapping(raw, where)

    entries = body.get("criteria")
    if not isinstance(entries, list) or not entries:
        raise ScoringConfigError(
            f"{where}: 'criteria' must be a non-empty list of criterion mappings"
        )

    criteria = tuple(_parse_criterion(e, i, where) for i, e in enumerate(entries))

    duplicates = sorted({c.feature for c in criteria if
                         sum(1 for o in criteria if o.feature == c.feature) > 1})
    if duplicates:
        raise ScoringConfigError(
            f"{where}: duplicate criterion feature(s) {duplicates}; each feature "
            f"may be weighted once, otherwise its influence is silently doubled"
        )

    total = sum(c.weight for c in criteria)
    if total <= 0:
        raise ScoringConfigError(
            f"{where}: configured weights sum to {total}; at least one criterion "
            f"must carry a positive weight or no cell can be scored"
        )

    discount = body.get("confidence_discount", False)
    if not isinstance(discount, bool):
        raise ScoringConfigError(
            f"{where}: 'confidence_discount' must be true or false, got {discount!r}"
        )

    factors = _parse_confidence_factors(body.get("confidence_factors"), where)
    if discount:
        missing = [lvl for lvl in config.CONFIDENCE_LEVELS if lvl not in factors]
        if missing:
            raise ScoringConfigError(
                f"{where}: confidence discounting is enabled but "
                f"'confidence_factors' has no entry for {missing}; every value in "
                f"the S1-09 vocabulary {list(config.CONFIDENCE_LEVELS)} needs a factor"
            )

    version = body.get("version")
    return WeightsConfig(
        criteria=criteria,
        confidence_discount=discount,
        confidence_factors=factors,
        config_id=config_id,
        version=str(version) if version is not None else None,
        path=Path(path) if path is not None else None,
    )


def load_weights(path: Path | str) -> WeightsConfig:
    """
    Load and validate a criteria weights YAML file.

    Raises ScoringConfigError (a ValueError) on a missing file, unparsable
    YAML, an invalid direction, a negative or non-numeric weight, a duplicate
    criterion, a missing rationale, or weights summing to zero — always
    before the stage reads the feature table or writes any output.

    `config_id` is the SHA-256 of the file's bytes, so the method report and
    manifest identify exactly which weights produced a given set of scores.
    """
    path = Path(path)
    if not path.exists():
        raise ScoringConfigError(f"Scoring weights file not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ScoringConfigError(f"{path} is not valid YAML: {exc}") from exc
    return parse_weights(raw, path=path, config_id=sha256_file(path))
