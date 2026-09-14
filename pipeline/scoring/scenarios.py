"""
Scenario / weight-comparison engine (S2-07).

A SCENARIO IS A PREFERENCE, NOT AN UNCERTAINTY. A scenario is a named weight
set — one documented ordering of screening priorities (for example "Wind-led"
vs "Grid-led"). Running the engine under two scenarios shows that the ranking
depends on the user's PREFERENCES, not on any objectively correct answer and
not on probabilistic uncertainty in the data. These are explicitly
preference/weighting scenarios; nothing here models uncertainty.

A SCENARIO IS DATA, NOT CODE. Presets live in `scenarios.yaml`, exactly as the
default weights live in `scoring_weights.yaml`. This module carries no weight
literal: each preset's weight set is validated by the SAME validator as the
default weights (`weights.parse_weights`), so an invalid preset fails loudly
before any output is produced.

THE ENGINE IS REUSED UNCHANGED. Every scenario is scored by the S2-05 pure
core (`score.score_and_rank`); this module adds no scoring, normalisation or
ranking arithmetic of its own. `run_scenario` is a thin pass-through, and
`compare_scenarios` runs the engine once per scenario and diffs the ranks.

COMPARABILITY (only weights differ). `compare_scenarios` requires the two
scenarios to score the SAME criteria feature set, computes the normalisation
bounds ONCE from the eligible population, and passes those shared bounds to
both runs. The bounds depend only on the eligible population and the criterion
directions, never on the weights, so a ranking change between two scenarios is
attributable purely to the change in preferences (the consistency guarantee
S2-07 requires).

The comparison structure (`ScenarioComparison`) is the contract the S2-08
Decision_Service wraps as `compare_scenarios` and the S3-06 UI renders. Its
`to_dict()` emits exactly the S2-08 field names (`cell_id`, `rank_a`, `rank_b`,
`rank_delta`, `labels`) plus additive score fields (`score_a`, `score_b`,
`score_delta`); no S2-08 field is renamed.

The engine surfaces "higher-ranked candidate cells under the selected
assumptions and criteria" (Screening_Language) — a different scenario is a
different, equally documented set of assumptions, not a more or less "correct"
answer.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import yaml

from . import config
from .normalise import Bounds, compute_bounds
from .score import eligible_mask, score_and_rank
from .weights import ScoringConfigError, WeightsConfig, parse_weights


@dataclass(frozen=True)
class Scenario:
    """
    One named weighting scenario: a preference expressed as a validated weight
    set over the scored criteria.

    `weights` is a full `WeightsConfig`, so a scenario is fed to the scoring
    engine exactly like the default weights — no scenario-specific scoring path
    exists.
    """

    name: str  # the preset key, e.g. "wind_led"
    label: str  # human-readable label, e.g. "Wind-led"
    description: str  # what preference this scenario encodes
    weights: WeightsConfig

    @property
    def features(self) -> tuple[str, ...]:
        """The criteria feature columns this scenario scores, in config order."""
        return self.weights.features


def _require_mapping(raw: object, path: Path) -> dict:
    if raw is None:
        raise ScoringConfigError(f"{path} is empty — expected a YAML mapping")
    if not isinstance(raw, dict):
        raise ScoringConfigError(
            f"{path} must be a YAML mapping at the top level, got {type(raw).__name__}"
        )
    return raw


def _parse_scenario(name: str, entry: object, path: Path, config_id: str) -> Scenario:
    """
    Build one validated Scenario from a preset entry.

    The weight set is validated through `weights.parse_weights`, so every
    weight rule (invalid direction, negative/non-numeric weight, zero weight
    sum, duplicate criterion, missing rationale) applies to a scenario exactly
    as it does to the default weights. Any failure names the offending
    scenario so a malformed preset is unambiguous.
    """
    if not isinstance(entry, dict):
        raise ScoringConfigError(
            f"{path}: scenario '{name}' must be a mapping with label/description/"
            f"criteria, got {type(entry).__name__}"
        )

    label = entry.get("label")
    if not isinstance(label, str) or not label.strip():
        raise ScoringConfigError(
            f"{path}: scenario '{name}' is missing a non-empty 'label'"
        )

    description = entry.get("description")
    if not isinstance(description, str) or not description.strip():
        raise ScoringConfigError(
            f"{path}: scenario '{name}' is missing a non-empty 'description'. Every "
            f"scenario must document the preference it encodes."
        )

    if "criteria" not in entry:
        raise ScoringConfigError(
            f"{path}: scenario '{name}' has no 'criteria' weight set"
        )

    try:
        weights = parse_weights(
            {"criteria": entry["criteria"], "version": entry.get("version")},
            path=path,
            config_id=config_id,
        )
    except ScoringConfigError as exc:
        # Re-raise naming the scenario, so a bad weight set is traced to the
        # preset that carried it rather than to an anonymous criteria block.
        raise ScoringConfigError(
            f"{path}: scenario '{name}' has an invalid weight set: {exc}"
        ) from exc

    return Scenario(
        name=name,
        label=" ".join(label.split()),
        description=" ".join(description.split()),
        weights=weights,
    )


def parse_scenarios(
    raw: object,
    *,
    path: Path | None = None,
    config_id: str = "",
) -> dict[str, Scenario]:
    """
    Validate an already-parsed YAML mapping into named Scenarios.

    Split from `load_scenarios` so tests can exercise every fault path on an
    in-memory dict without writing files (the same split `weights.py` uses).
    """
    where = path if path is not None else Path("<in-memory scenarios>")
    body = _require_mapping(raw, where)

    presets = body.get("scenarios")
    if not isinstance(presets, dict) or not presets:
        raise ScoringConfigError(
            f"{where}: 'scenarios' must be a non-empty mapping of name -> preset"
        )

    scenarios = {
        str(name): _parse_scenario(str(name), entry, where, config_id)
        for name, entry in presets.items()
    }
    return scenarios


def load_scenarios(path: Path | str | None = None) -> dict[str, Scenario]:
    """
    Load and validate the named weighting scenarios from a YAML file.

    Defaults to the packaged `pipeline/scoring/scenarios.yaml`. Raises
    ScoringConfigError (a ValueError) on a missing file, unparsable YAML, no
    presets, a preset missing its label/description/criteria, or any invalid
    weight set — always naming the offending scenario, and always before any
    scoring is attempted.
    """
    path = Path(path) if path is not None else config.DEFAULT_SCENARIOS_PATH
    if not path.exists():
        raise ScoringConfigError(f"Scenarios file not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ScoringConfigError(f"{path} is not valid YAML: {exc}") from exc
    from ..common.geo import sha256_file

    return parse_scenarios(raw, path=path, config_id=sha256_file(path))
