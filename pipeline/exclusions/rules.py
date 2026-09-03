"""
Exclusion rule engine (S1-07).

Rules are data, not code: they are loaded from a YAML file (default
`pipeline/exclusions/exclusion_rules.yaml`) and evaluated generically
against a per-cell field dictionary. This module has no knowledge of what
"protected area" or "slope" mean — adding, removing, reordering or
retuning a rule never touches this file, only the YAML config.

Public API
----------
load_rules(path) -> list[dict]
    Load + validate the rules config. Raises RuleConfigError (not a silent
    skip / partial rule set) on any malformed rule.

evaluate_cell(cell_fields, rules) -> (eligible, exclusion_reason, triggered_rule_names)
    Evaluate every rule against one cell's fields. A cell is eligible iff no
    rule triggers. Rules are evaluated independently (a cell can fail
    multiple rules) and reasons are joined in rule-config order.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import yaml

REQUIRED_RULE_KEYS = {"name", "description", "field", "condition"}

# Matches the ticket's own Output Format example ("Slope exceeds 15°, Protected
# area: Barrington Tops NP") and acceptance criterion "comma-separated or list".
REASON_DELIMITER = ", "

_CONDITION_RE = re.compile(r"^\s*(==|!=|>=|<=|>|<|is_null|is_not_null)\s*(.*)$")


class RuleConfigError(ValueError):
    """Raised when the exclusion rules file is missing or malformed.

    A malformed rules file must halt the run loudly — evaluating cells
    against a partial or mis-parsed rule set would silently under-exclude,
    which is exactly the "poor data passing as good" the Constitution
    forbids.
    """


# ---------------------------------------------------------------------------
# Loading and validating the rules config
# ---------------------------------------------------------------------------


def load_rules(path: Path) -> list[dict]:
    """Load and validate the exclusion rules YAML file at `path`."""
    if not path.exists():
        raise RuleConfigError(f"Exclusion rules file not found: {path}")

    try:
        raw = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise RuleConfigError(f"Exclusion rules file is not valid YAML: {path} ({exc})") from exc

    if not isinstance(raw, dict) or "exclusions" not in raw:
        raise RuleConfigError(
            f"Exclusion rules file must have a top-level 'exclusions' list: {path}"
        )

    rules = raw["exclusions"]
    if not isinstance(rules, list) or not rules:
        raise RuleConfigError(f"'exclusions' must be a non-empty list of rules: {path}")

    seen_names: set[str] = set()
    for i, rule in enumerate(rules):
        if not isinstance(rule, dict):
            raise RuleConfigError(f"Rule #{i} is not a mapping: {rule!r}")

        missing = REQUIRED_RULE_KEYS - rule.keys()
        if missing:
            raise RuleConfigError(
                f"Rule #{i} ({rule.get('name', '?')!r}) missing required key(s): {sorted(missing)}"
            )

        name = rule["name"]
        if not isinstance(name, str) or not name.strip():
            raise RuleConfigError(f"Rule #{i} has an invalid 'name': {name!r}")
        if name in seen_names:
            raise RuleConfigError(f"Duplicate rule name: {name!r}")
        seen_names.add(name)

        if not isinstance(rule["field"], str) or not rule["field"].strip():
            raise RuleConfigError(f"Rule {name!r} has an invalid 'field': {rule['field']!r}")

        # Validate the condition parses now, rather than failing per-cell later.
        _parse_condition(rule["condition"])

    return rules


# ---------------------------------------------------------------------------
# Condition parsing and evaluation
# ---------------------------------------------------------------------------


def _parse_condition(condition: Any) -> tuple[str, str]:
    if not isinstance(condition, str):
        raise RuleConfigError(f"Condition must be a string: {condition!r}")
    match = _CONDITION_RE.match(condition)
    if not match:
        raise RuleConfigError(f"Unparseable condition: {condition!r}")
    op, rhs = match.group(1), match.group(2).strip()
    if op not in ("is_null", "is_not_null") and not rhs:
        raise RuleConfigError(f"Condition {condition!r} is missing a comparison value")
    return op, rhs


def _coerce_rhs(rhs: str) -> Any:
    """Coerce a condition's right-hand side text to bool / number / string."""
    if rhs == "True":
        return True
    if rhs == "False":
        return False
    if rhs == "None":
        return None
    try:
        if any(c in rhs for c in (".", "e", "E")):
            return float(rhs)
        return int(rhs)
    except ValueError:
        return rhs.strip("'\"")


def _is_missing(value: Any) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def evaluate_condition(value: Any, condition: str) -> bool:
    """
    Evaluate one rule condition against one field value.

    Supported forms: "== X", "!= X", "> N", ">= N", "< N", "<= N",
    "is_null", "is_not_null".

    A missing value (None or NaN) matches only "is_null" / "is_not_null" —
    it never satisfies a numeric or equality comparison. This means a cell
    with genuinely unavailable data is never silently swept into an
    unrelated rule by an accidental type/None comparison.
    """
    op, rhs = _parse_condition(condition)

    if op == "is_null":
        return _is_missing(value)
    if op == "is_not_null":
        return not _is_missing(value)

    if _is_missing(value):
        return False

    target = _coerce_rhs(rhs)
    if op == "==":
        return value == target
    if op == "!=":
        return value != target
    if op == ">":
        return value > target
    if op == ">=":
        return value >= target
    if op == "<":
        return value < target
    if op == "<=":
        return value <= target
    raise RuleConfigError(f"Unsupported operator: {op!r}")  # pragma: no cover — guarded above


def evaluate_rule(rule: dict, cell_fields: dict) -> tuple[bool, str | None]:
    """
    Evaluate one rule against one cell's fields.

    Returns (triggered, reason). When triggered, `reason` is the rule's
    `reason_template` (falling back to `description`) formatted against the
    cell's fields plus the rule's own `threshold` (if any), e.g.
    "Slope exceeds {threshold}°" -> "Slope exceeds 15°".
    """
    value = cell_fields.get(rule["field"])
    if not evaluate_condition(value, rule["condition"]):
        return False, None

    template = rule.get("reason_template") or rule["description"]
    format_fields = {**cell_fields, "threshold": rule.get("threshold")}
    try:
        reason = template.format(**format_fields)
    except (KeyError, IndexError):
        # A template referencing a field this cell doesn't have — fall back
        # to the raw template rather than crash the whole run over one cell.
        reason = template

    return True, reason


# ---------------------------------------------------------------------------
# Per-cell evaluation
# ---------------------------------------------------------------------------


def evaluate_cell(cell_fields: dict, rules: list[dict]) -> tuple[bool, str | None, list[str]]:
    """
    Evaluate every rule against one cell.

    Rules are evaluated independently — a cell can fail multiple rules.
    Returns (eligible, exclusion_reason, triggered_rule_names):
      - eligible is True iff no rule triggered.
      - exclusion_reason is None when eligible, else every triggered rule's
        reason joined with REASON_DELIMITER, in rule-config order
        (deterministic).
      - triggered_rule_names lists the `name` of every triggered rule, for
        machine-readable auditing independent of the human-readable text.
    """
    reasons: list[str] = []
    triggered_names: list[str] = []

    for rule in rules:
        triggered, reason = evaluate_rule(rule, cell_fields)
        if triggered:
            reasons.append(reason)
            triggered_names.append(rule["name"])

    if not reasons:
        return True, None, []
    return False, REASON_DELIMITER.join(reasons), triggered_names
