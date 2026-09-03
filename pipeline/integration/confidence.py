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
