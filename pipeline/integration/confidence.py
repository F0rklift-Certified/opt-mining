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

import numpy as np
import pandas as pd
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


# ---------------------------------------------------------------------------
# Scoring — pure functions over the integrated table
# ---------------------------------------------------------------------------

LEVEL_HIGH, LEVEL_MEDIUM, LEVEL_LOW = config.DATA_CONFIDENCE_LEVELS


def required_columns(weights: Weights) -> tuple[str, ...]:
    """Columns assess() reads: the scored features, the flag columns, data_flags."""
    columns = list(config.SCORED_FEATURE_COLUMNS) + [rule.column for rule in weights.flags]
    if weights.soft_flags:
        columns.append("data_flags")
    return tuple(dict.fromkeys(columns))


def _check_columns(table: pd.DataFrame, weights: Weights) -> None:
    missing = [c for c in required_columns(weights) if c not in table.columns]
    if missing:
        raise ValueError(
            f"integrated table lacks column(s) {missing} required for the confidence layer"
        )


def _flag_state(table: pd.DataFrame, rule: FlagRule) -> tuple[np.ndarray, np.ndarray]:
    """Per-row (factor, known): factor is 0 for a null or out-of-vocabulary flag."""
    values = table[rule.column]
    known = values.isin(list(rule.factors)).to_numpy()
    factor = values.map(rule.factors).to_numpy(dtype=float)
    return np.where(known, factor, 0.0), known


def _soft_state(table: pd.DataFrame, weights: Weights) -> tuple[np.ndarray, list[np.ndarray]]:
    """Per-row product of matched soft-flag factors, plus one hit mask per soft flag."""
    n = len(table)
    soft = np.ones(n)
    hits: list[np.ndarray] = []
    if weights.soft_flags and "data_flags" in table.columns:
        flags = table["data_flags"].fillna("").astype(str)
        for soft_flag in weights.soft_flags:
            hit = flags.str.contains(soft_flag.match, regex=False).to_numpy()
            soft = np.where(hit, soft * soft_flag.factor, soft)
            hits.append(hit)
    else:
        hits = [np.zeros(n, dtype=bool) for _ in weights.soft_flags]
    return soft, hits


def _components(table: pd.DataFrame, weights: Weights):
    """present (n×F bool), per-feature w·r·l (F), flag multipliers (n×F), soft (n)."""
    features = list(config.SCORED_FEATURE_COLUMNS)
    index = {name: i for i, name in enumerate(features)}
    present = table[features].notna().to_numpy()
    base = np.array([f.weight * f.factor for f in weights.features])
    multipliers = np.ones((len(table), len(features)))
    for rule in weights.flags:
        factor, _ = _flag_state(table, rule)
        for feature in rule.features:
            multipliers[:, index[feature]] = factor
    soft, _ = _soft_state(table, weights)
    return present, base, multipliers, soft


def score_raw(table: pd.DataFrame, weights: Weights) -> np.ndarray:
    """Unrounded confidence score per row (used directly by the property tests)."""
    _check_columns(table, weights)
    present, base, multipliers, soft = _components(table, weights)
    return soft * (present.astype(float) * multipliers * base).sum(axis=1) / weights.weight_sum


def categorise(scores, thresholds: Thresholds) -> np.ndarray:
    """high if score >= high, medium if score >= medium, else low (inclusive bounds)."""
    values = np.asarray(scores, dtype=float)
    return np.select(
        [values >= thresholds.high, values >= thresholds.medium],
        [LEVEL_HIGH, LEVEL_MEDIUM],
        default=LEVEL_LOW,
    )


def assess(table: pd.DataFrame, weights: Weights) -> pd.DataFrame:
    """
    Compute data_confidence / confidence_score / confidence_notes for every row.

    Pure: never mutates `table`; the result is index-aligned to it. Raises
    ValueError only when a required column is absent — data values (nulls,
    out-of-vocabulary flags) are handled conservatively (factor 0 + a note),
    never by raising, because this runs before validate().

    Notes are '; '-joined in a fixed order that does not depend on the YAML's
    key order: missing-feature notes (SCORED_FEATURE_COLUMNS order), then
    flag notes (layer order) only when the factor is < 1 and a scoped feature
    is present, then soft-flag notes; '—' when there is nothing to say.
    """
    _check_columns(table, weights)
    n = len(table)
    features = list(config.SCORED_FEATURE_COLUMNS)
    index = {name: i for i, name in enumerate(features)}
    present, base, multipliers, soft = _components(table, weights)

    note_sources: list[tuple[np.ndarray, np.ndarray]] = []  # (row mask, per-row text)
    for feature in weights.features:
        missing = ~present[:, index[feature.name]]
        note_sources.append((missing, np.full(n, feature.note, dtype=object)))
    for rule in weights.flags:
        factor, known = _flag_state(table, rule)
        scoped_present = present[:, [index[f] for f in rule.features]].any(axis=1)
        texts = table[rule.column].map(rule.notes)
        note_sources.append((
            known & (factor < 1) & scoped_present & texts.notna().to_numpy(),
            texts.to_numpy(dtype=object),
        ))
        note_sources.append((
            ~known & scoped_present,
            np.full(n, f"{rule.column} outside vocabulary", dtype=object),
        ))
    _, hits = _soft_state(table, weights)
    for soft_flag, hit in zip(weights.soft_flags, hits):
        note_sources.append((hit, np.full(n, soft_flag.note, dtype=object)))

    raw = soft * (present.astype(float) * multipliers * base).sum(axis=1) / weights.weight_sum
    score = np.round(raw, config.CONFIDENCE_SCORE_DECIMALS)
    level = categorise(score, weights.thresholds)

    notes = []
    for row in range(n):
        parts = [str(text[row]) for mask, text in note_sources if mask[row]]
        notes.append(config.CONFIDENCE_NOTE_DELIMITER.join(parts) if parts else config.CONFIDENCE_NO_NOTES)

    return pd.DataFrame(
        {
            "data_confidence": level.astype(object),
            "confidence_score": score.astype("float64"),
            "confidence_notes": notes,
        },
        index=table.index,
    )


# ---------------------------------------------------------------------------
# Summary statistics — distribution, reasons, lattice clustering
# ---------------------------------------------------------------------------

LEVEL_ORDER = (LEVEL_HIGH, LEVEL_MEDIUM, LEVEL_LOW)
_LEVEL_CODE = {LEVEL_LOW: 0, LEVEL_MEDIUM: 1, LEVEL_HIGH: 2}
_NEIGHBOUR_OFFSETS = tuple((dr, dc) for dr in (-1, 0, 1) for dc in (-1, 0, 1) if (dr, dc) != (0, 0))


def lattice_index(
    table: pd.DataFrame, *, origin_lon: float, origin_lat: float, cell_deg: float,
) -> tuple[np.ndarray, np.ndarray]:
    """
    (row, col) integer indices of each cell on the regular analysis lattice,
    from its centroid: col counts cells east of the GWA origin, row counts
    cells south of it. Cell centroids sit at half-cell offsets, so floor() is
    robust to floating-point noise.
    """
    lon = table["centroid_lon"].to_numpy(dtype=float)
    lat = table["centroid_lat"].to_numpy(dtype=float)
    col = np.floor((lon - origin_lon) / cell_deg).astype(int)
    row = np.floor((origin_lat - lat) / cell_deg).astype(int)
    return row, col


def _level_counts(levels: pd.Series) -> dict[str, int]:
    return {level: int((levels == level).sum()) for level in LEVEL_ORDER}


def _reason_counts(notes: pd.Series, n: int) -> list[dict]:
    exploded = notes.astype(str).str.split(config.CONFIDENCE_NOTE_DELIMITER).explode()
    exploded = exploded[(exploded != config.CONFIDENCE_NO_NOTES) & (exploded != "")]
    counts = exploded.value_counts()
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [{"reason": reason, "count": int(count), "share": 100.0 * int(count) / n if n else 0.0}
            for reason, count in ranked]


def _histogram(scores: np.ndarray) -> list[dict]:
    edges = [round(i / 10, 1) for i in range(11)]
    bins = np.clip(np.floor(scores * 10 + 1e-9).astype(int), 0, 9) if len(scores) else np.array([], dtype=int)
    counts = np.bincount(bins, minlength=10) if len(scores) else np.zeros(10, dtype=int)
    out = []
    for i in range(10):
        closed = i == 9
        label = f"[{edges[i]:.1f}, {edges[i + 1]:.1f}{']' if closed else ')'}"
        out.append({"bin": label, "lower": edges[i], "upper": edges[i + 1], "count": int(counts[i])})
    return out


def _neighbour_agreement(levels: pd.Series, row: np.ndarray, col: np.ndarray) -> dict:
    n = len(levels)
    code = levels.map(_LEVEL_CODE).fillna(-1).to_numpy(dtype=int)
    if n == 0:
        return {level: {"n": 0, "all_neighbours_same": 0, "share_all_neighbours_same": None,
                        "mean_same_fraction": None, "expected_share_random": None, "clustered": None}
                for level in LEVEL_ORDER}
    r_off, c_off = row - row.min() + 1, col - col.min() + 1
    grid = np.full((r_off.max() + 2, c_off.max() + 2), -1, dtype=np.int8)
    grid[r_off, c_off] = code
    present = np.zeros(n, dtype=int)
    same = np.zeros(n, dtype=int)
    for dr, dc in _NEIGHBOUR_OFFSETS:
        neighbour = grid[r_off + dr, c_off + dc]
        present += neighbour != -1
        same += (neighbour == code) & (neighbour != -1)

    result = {}
    for level in LEVEL_ORDER:
        mask = code == _LEVEL_CODE[level]
        n_level = int(mask.sum())
        with_neighbours = mask & (present > 0)
        all_same = with_neighbours & (same == present)
        share = int(all_same.sum()) / n_level if n_level else None
        fractions = same[with_neighbours] / present[with_neighbours]
        p = n_level / n
        result[level] = {
            "n": n_level,
            "all_neighbours_same": int(all_same.sum()),
            "share_all_neighbours_same": share,
            "mean_same_fraction": float(fractions.mean()) if len(fractions) else None,
            "expected_share_random": p ** 8 if n_level else None,
            "clustered": (share > p ** 8) if n_level else None,
        }
    return result


def summarise(table: pd.DataFrame, weights: Weights) -> dict:
    """
    Distribution of the confidence columns plus the reasons and a geographic
    pattern read-out. `table` must carry the confidence columns, `eligible`
    and the grid centroids. Pure; returns plain Python values.
    """
    n = len(table)
    levels = table["data_confidence"].astype(str)
    scores = table["confidence_score"].to_numpy(dtype=float)

    counts = _level_counts(levels)
    shares = {level: (100.0 * counts[level] / n if n else 0.0) for level in LEVEL_ORDER}
    score_stats = (
        {"min": float(scores.min()), "max": float(scores.max()),
         "mean": float(scores.mean()), "median": float(np.median(scores))}
        if n else {"min": None, "max": None, "mean": None, "median": None}
    )

    distinct = (
        table.groupby(["confidence_score", "data_confidence"]).size().reset_index(name="count")
        .sort_values("confidence_score", ascending=False)
    )
    distinct_scores = [
        {"score": float(r.confidence_score), "level": str(r.data_confidence), "count": int(r.count)}
        for r in distinct.itertuples(index=False)
    ]

    reasons = _reason_counts(table["confidence_notes"], n)
    if "eligible" in table.columns:
        eligible = table["eligible"].fillna(False).astype(bool)
        reasons_eligible = _reason_counts(table.loc[eligible, "confidence_notes"], int(eligible.sum()))
        by_eligibility = {
            "eligible": _level_counts(levels[eligible]),
            "excluded": _level_counts(levels[~eligible]),
        }
    else:
        reasons_eligible, by_eligibility = [], None

    row, col = lattice_index(
        table, origin_lon=config.GRID_ORIGIN_LON, origin_lat=config.GRID_ORIGIN_LAT,
        cell_deg=config.CELL_DEG,
    )
    lat = table["centroid_lat"].to_numpy(dtype=float)
    lon = table["centroid_lon"].to_numpy(dtype=float)
    blocks_frame = pd.DataFrame({
        "lat_block": np.floor(lat).astype(int) if n else np.array([], dtype=int),
        "lon_block": np.floor(lon).astype(int) if n else np.array([], dtype=int),
        "level": levels.to_numpy(),
    })
    blocks = []
    for (lat_block, lon_block), group in blocks_frame.groupby(["lat_block", "lon_block"], sort=False):
        size = len(group)
        blocks.append({
            "lat_block": int(lat_block), "lon_block": int(lon_block), "n": int(size),
            **{f"pct_{level}": 100.0 * int((group["level"] == level).sum()) / size for level in LEVEL_ORDER},
        })
    blocks.sort(key=lambda b: (-b["lat_block"], b["lon_block"]))

    bounding_boxes = {}
    for level in LEVEL_ORDER:
        mask = (levels == level).to_numpy()
        if not mask.any():
            bounding_boxes[level] = None
            continue
        bounding_boxes[level] = {
            "n": int(mask.sum()),
            "lat_min": float(lat[mask].min()), "lat_max": float(lat[mask].max()),
            "lon_min": float(lon[mask].min()), "lon_max": float(lon[mask].max()),
            "centroid_lat_mean": float(lat[mask].mean()), "centroid_lon_mean": float(lon[mask].mean()),
        }

    return {
        "n_cells": n,
        "counts": counts,
        "shares": shares,
        "score_stats": score_stats,
        "histogram": _histogram(scores),
        "distinct_scores": distinct_scores,
        "reasons": reasons,
        "reasons_eligible": reasons_eligible,
        "top_reason": reasons[0]["reason"] if reasons else None,
        "by_eligibility": by_eligibility,
        "geographic": {
            "lattice": {
                "origin_lon": config.GRID_ORIGIN_LON, "origin_lat": config.GRID_ORIGIN_LAT,
                "cell_deg": config.CELL_DEG,
                "n_rows": int(row.max() - row.min() + 1) if n else 0,
                "n_cols": int(col.max() - col.min() + 1) if n else 0,
            },
            "neighbour_agreement": _neighbour_agreement(levels, row, col),
            "blocks": blocks,
            "bounding_boxes": bounding_boxes,
        },
        "thresholds": {"high": weights.thresholds.high, "medium": weights.thresholds.medium},
        "max_attainable": weights.max_attainable,
        "weights_version": weights.version,
        "weights_sha256": weights.sha256,
    }


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

MODULE_NAME = "integration.confidence"


def _banner(generated_utc: str) -> str:
    return (f"*Generated by `pipeline.{MODULE_NAME}` on {generated_utc}. "
            f"Do not edit by hand.*\n")


def _fmt(value: float) -> str:
    return f"{value:g}"


def build_confidence_method(weights: Weights, *, generated_utc: str, git_commit: str) -> str:
    """Render confidence_method.md — the methodology document (static given the config)."""
    total = weights.weight_sum
    feature_rows = "\n".join(
        f"| `{f.name}` | {_fmt(f.weight)} | {100 * f.weight / total:.1f}% | {_fmt(f.resolution)} | "
        f"{_fmt(f.limitation)} | {f.factor:.4f} | {f.note} |"
        for f in weights.features
    )
    basis_rows = "\n".join(
        f"- `{f.name}` — resolution {_fmt(f.resolution)}: {f.resolution_basis or '(no basis recorded)'}; "
        f"limitation {_fmt(f.limitation)}: {f.limitation_basis or '(no basis recorded)'}"
        for f in weights.features
    )
    flag_rows = "\n".join(
        f"| {rule.layer} | `{rule.column}` | {', '.join(f'`{x}`' for x in rule.features)} | "
        + ", ".join(f"{value} → {_fmt(factor)}" for value, factor in rule.factors.items())
        + " | " + ("; ".join(f"{v}: {t}" for v, t in rule.notes.items()) or "—") + " |"
        for rule in weights.flags
    )
    soft_rows = "\n".join(
        f"| `{sf.match}` | {_fmt(sf.factor)} | {sf.note} |" for sf in weights.soft_flags
    ) or "| — | — | (none configured) |"
    t = weights.thresholds
    config_path = str(weights.path) if weights.path else "(in-memory config)"

    return f"""# Data confidence layer — methodology (S1-09)

{_banner(generated_utc)}

## 1. Purpose

Every cell of the Integrated NSW Feature Table carries a composite data
confidence so that scoring (S1-10) and the shortlist (S1-11) can report — and
optionally discount by — how well evidenced each cell is. This is a
metadata/quality layer, not a filter: no cell is removed and eligibility is
untouched (Constitution: "retain and flag"; "report confidence alongside every
score"). The composite reflects (a) which of the ten scored features are
present, (b) each source's spatial resolution relative to the 0.05° (~5 km)
analysis cell, (c) the source's documented limitations in the S1-01 data
specification, (d) the upstream layers' own confidence flags, and (e) S1-07's
soft data flags.

## 2. Formula

For each cell and each scored feature f with configured weight w_f:

```
avail_f          = 1 if the feature value is present, 0 if null
flag_f           = factor for the value of f's layer flag (1 if f is not scoped by a layer;
                   0 with a note if the flag value is null or outside the vocabulary)
s_f              = avail_f × resolution_f × limitation_f × flag_f
soft             = Π factor_k over soft flags whose match string occurs in data_flags
confidence_score = round( soft × Σ_f w_f · s_f / Σ_f w_f , 3 )
data_confidence  = high   if confidence_score ≥ {_fmt(t.high)}
                   medium if confidence_score ≥ {_fmt(t.medium)}
                   low    otherwise
```

Flag factors multiply only a layer's PRESENT features: a null feature already
contributes 0 through `avail_f`, so missingness is never counted twice. The
maximum attainable score under this configuration — every feature present,
every flag at 1.0 — is **{weights.max_attainable:.3f}** (= Σ w·r·l / Σ w);
1.0 would require every source to be at native resolution with no documented
limitation.

## 3. Feature weights, resolution and limitation factors

Σ w = {_fmt(total)} (the score normalises by the sum, so it need not be 1).
Weights mirror the S1-10 baseline scoring weights for its six criteria; the
remaining four scored columns carry 0.05 each.

| Feature | Weight | Share | Resolution | Limitation | r × l | Note when missing |
|---------|--------|-------|------------|------------|-------|-------------------|
{feature_rows}

Resolution scale (ticket S1-09): 1.0 = source native resolution at or finer
than the cell (exact nesting or many pixels per cell); 0.5 = value allocated or
interpolated from a unit coarser than the cell. Limitation scale: 1.00 none;
0.95 minor caveats; 0.90 known systematic bias or stale vintage; 0.75 value must
be labelled "estimated"; 0.50 severe (reserved). Bases (S1-01 data
specification sections):

{basis_rows}

## 4. Upstream flag factors

| Layer | Flag column | Scoped features | Factors | Notes |
|-------|-------------|-----------------|---------|-------|
{flag_rows}

The infrastructure flag is `low` whenever any of its four required features is
null; in the 2026 snapshot that is an artefact of `dist_connection_km` being
null everywhere (the AEMO KCI workbook has no coordinates), the missingness is
already counted through `avail_f`, and the flag carries no information beyond
it — hence factor 1.0 for both values. The geographic scope mirrors the S1-06
rule (elevation, slope, NLUM); `protected_area` comes from CAPAD, which covers
all of NSW, and is not governed by that flag.

## 5. Soft flags (S1-07 `data_flags`)

| Match (substring) | Factor on the whole score | Note |
|-------------------|---------------------------|------|
{soft_rows}

## 6. Notes column

`confidence_notes` lists, `'; '`-joined and in a fixed order independent of the
config file's key order: missing-feature notes (scored-column order), then
flag notes (layer order wind → geographic → infrastructure → demand, only when
the factor is below 1 and a scoped feature is present), then soft-flag notes;
`—` when there is nothing to report.

## 7. What is deliberately NOT an input

- **Distance to the nearest measured or modelled data point** (ticket
  criterion "if applicable"): **not applicable** to any Sprint 1 source. GWA is
  a modelled field defined at every pixel; the GA lines/substations, CAPAD and
  REZ layers are exact geometries and the distance to them IS the feature;
  SRTM and NLUM are complete rasters; demand is a regional aggregate.
- `tri` (Glen-Innes sub-window only by design; excluded from S1-06's flag for
  the same reason), `rez_name`, `source_region`, `protected_area_name`.
- Eligibility, `triggered_rules` and `exclusion_reason`: S1-07's "Missing wind
  data" exclusions come from its own New-England-REZ wind clip, whereas
  `wind_speed` is populated for every cell; the canonical wind evidence is the
  S1-03 layer.

## 8. Temporal disclosure

Per the data specification §6, wind (GWA 2008–2017 ten-year mean) and demand
(AEMO 2025–26 operational demand) are long-run indicators with a ~8-year
offset; this gap is a documented limitation (demand limitation factor
{_fmt(weights.feature('demand_proxy').limitation)}) and must be stated wherever
the two criteria are combined.

## 9. Configuration and reproducibility

- Config file: `{config_path}` — version `{weights.version}`, SHA-256 `{weights.sha256}`
- Override: `python -m pipeline --only integration --confidence-weights path/to/file.yaml`
- Generated (UTC): {generated_utc}; git commit `{git_commit}`
"""


def build_confidence_summary(
    summary: dict, weights: Weights, *, generated_utc: str, git_commit: str, outputs: dict,
) -> str:
    """Render confidence_summary.md — the data-quality distribution report."""
    n = summary["n_cells"]
    counts, shares = summary["counts"], summary["shares"]
    t = weights.thresholds

    level_rows = "\n".join(
        f"| {level} | {counts[level]} | {shares[level]:.1f}% |" for level in LEVEL_ORDER
    )
    empty_levels = [level for level in LEVEL_ORDER if counts[level] == 0]
    empty_note = "\n".join(
        f"- {level}: 0 cells — no cell reaches this level under the current thresholds."
        for level in empty_levels
    ) or "- Every level is populated."

    histogram_rows = "\n".join(f"| {b['bin']} | {b['count']} |" for b in summary["histogram"])
    distinct_rows = "\n".join(
        f"| {d['score']:.3f} | {d['level']} | {d['count']} |" for d in summary["distinct_scores"]
    )

    def reason_table(entries):
        return "\n".join(
            f"| {i + 1} | {r['reason']} | {r['count']} | {r['share']:.1f}% |"
            for i, r in enumerate(entries)
        ) or "| — | (no reduced-confidence reasons) | 0 | 0.0% |"

    by_elig = summary.get("by_eligibility")
    eligibility_rows = (
        "\n".join(
            f"| {group} | " + " | ".join(str(by_elig[group][level]) for level in LEVEL_ORDER) + " |"
            for group in ("eligible", "excluded")
        ) if by_elig else "| — | — | — | — |"
    )

    geo = summary["geographic"]
    agreement_rows = []
    verdicts = []
    for level in LEVEL_ORDER:
        a = geo["neighbour_agreement"][level]
        if a["n"] == 0:
            agreement_rows.append(f"| {level} | 0 | — | — | — | — |")
            verdicts.append(f"- {level}: 0 cells — no spatial pattern to assess.")
            continue
        share = a["share_all_neighbours_same"]
        mean_frac = a["mean_same_fraction"]
        agreement_rows.append(
            f"| {level} | {a['n']} | {a['all_neighbours_same']} | "
            f"{share:.3f} | {a['expected_share_random']:.4f} | "
            f"{'—' if mean_frac is None else f'{mean_frac:.3f}'} |"
        )
        verdict = "clustered" if a["clustered"] else "not clustered"
        verdicts.append(
            f"- {level}: {verdict} — {share:.1%} of these cells have every lattice neighbour at "
            f"the same level versus {a['expected_share_random']:.2%} expected if levels were "
            f"scattered at random."
        )
    block_rows = "\n".join(
        f"| {b['lat_block']} | {b['lon_block']} | {b['n']} | {b['pct_high']:.1f} | "
        f"{b['pct_medium']:.1f} | {b['pct_low']:.1f} |"
        for b in geo["blocks"]
    ) or "| — | — | 0 | — | — | — |"
    box_rows = "\n".join(
        (f"| {level} | {box['n']} | {box['lat_min']:.3f} to {box['lat_max']:.3f} | "
         f"{box['lon_min']:.3f} to {box['lon_max']:.3f} | "
         f"{box['centroid_lat_mean']:.3f}, {box['centroid_lon_mean']:.3f} |")
        if box else f"| {level} | 0 | — | — | — |"
        for level, box in ((lvl, geo["bounding_boxes"][lvl]) for lvl in LEVEL_ORDER)
    )
    stats = summary["score_stats"]
    stats_line = (
        f"min {stats['min']:.3f} / median {stats['median']:.3f} / mean {stats['mean']:.3f} / "
        f"max {stats['max']:.3f} (max attainable {summary['max_attainable']:.3f})"
        if stats["min"] is not None else "no cells"
    )

    return f"""# Data quality summary — Integrated NSW Feature Table (S1-09)

{_banner(generated_utc)}

Total cells: **{n:,}**. Confidence score {stats_line}. Thresholds: high ≥
{_fmt(t.high)}, medium ≥ {_fmt(t.medium)}, else low. Methodology, weights and
factors: `{outputs['method'].name}`. Config version `{summary['weights_version']}`
(SHA-256 `{summary['weights_sha256']}`); git commit `{git_commit}`.

## 1. Confidence distribution

| Level | Cells | Share |
|-------|-------|-------|
{level_rows}

{empty_note}

Score histogram (last bin closed at 1.0):

| Score bin | Cells |
|-----------|-------|
{histogram_rows}

Distinct score profiles (identical scores mean identical evidence profiles):

| Score | Level | Cells |
|-------|-------|-------|
{distinct_rows}

## 2. Most common reasons for reduced confidence

All cells:

| # | Reason | Cells | Share of cells |
|---|--------|-------|----------------|
{reason_table(summary["reasons"])}

Eligible cells only (the shortlist candidates):

| # | Reason | Cells | Share of eligible cells |
|---|--------|-------|-------------------------|
{reason_table(summary["reasons_eligible"])}

## 3. Confidence by eligibility

| Eligibility | high | medium | low |
|-------------|------|--------|-----|
{eligibility_rows}

Low confidence never excludes a cell; eligibility comes from the S1-07
exclusion layer alone.

## 4. Geographic pattern

Neighbour agreement on the 0.05° lattice (each cell has up to 8 neighbours;
neighbours outside the table are ignored):

| Level | Cells | All neighbours same | Share | Random baseline (p⁸) | Mean same-neighbour fraction |
|-------|-------|---------------------|-------|----------------------|------------------------------|
{"\n".join(agreement_rows)}

{"\n".join(verdicts)}

Share of each level per 1° × 1° block (row = latitude block, north to south):

| Lat block | Lon block | Cells | % high | % medium | % low |
|-----------|-----------|-------|--------|----------|-------|
{block_rows}

Bounding boxes and mean centroid per level:

| Level | Cells | Latitude range | Longitude range | Mean centroid (lat, lon) |
|-------|-------|----------------|-----------------|--------------------------|
{box_rows}

## 5. Outputs

- Table with the confidence columns: `{outputs['table'].name}`
- Methodology: `{outputs['method'].name}`
- Generated (UTC): {generated_utc}
"""
