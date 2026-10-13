"""
Explanation templates — loading and validation (S2-06a).

Phrases, band labels and band thresholds are USER INPUTS read from a YAML file
at runtime. No phrase or band label appears in this module or anywhere else in
`pipeline/explanation/` source; `load_templates` is the only way the engine
learns how to phrase a factor. This mirrors `pipeline/scoring/weights.py`
(weights as data) and `pipeline/integration/confidence.py`.

Every validation here runs BEFORE the stage reads the Scored_Table or writes
anything, so a malformed template file fails the run without leaving a partial
or stale explanation artefact behind (fail before write).
"""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Real
from pathlib import Path

import yaml

from ..common.geo import sha256_file
from . import config

# Superlatives an explanation must never use — this is a screening tool, not a
# recommendation of a "best" site. Enforced here at config-load time (the
# headline and phrases cannot contain them) and again by validate.py over the
# rendered output, so a banned word cannot enter from either the template file
# or a future engine change.
BANNED_SUPERLATIVES = ("best site", "best-site", "optimal site", "ideal site", "perfect site")


class ExplanationConfigError(ValueError):
    """
    An explanation template configuration is missing, unparsable or invalid.

    Subclasses ValueError so callers that catch ValueError (the pipeline's
    convention for bad input data) still catch it, while `except
    ExplanationConfigError` can distinguish a config fault from a data fault —
    the same split `scoring.weights.ScoringConfigError` uses.
    """


@dataclass(frozen=True)
class Band:
    """One qualitative band: a label and the minimum normalised value for it."""

    label: str
    min_norm: float


@dataclass(frozen=True)
class CriterionPhrases:
    """
    The positive and weakness phrasing for one criterion feature.

    A criterion may also be marked a PROXY (S2-06b): a variable that stands in
    for something not measured directly. When `is_proxy` is true, `proxy_caveat`
    is the (required) sentence surfaced whenever this criterion actually took
    part in a cell's score, so the proxy is never presented as a direct
    measurement. Non-proxy criteria carry `is_proxy=False` and no caveat.
    """

    feature: str
    positive: str
    weakness: str
    is_proxy: bool = False
    proxy_caveat: str | None = None


@dataclass(frozen=True)
class DataQualityPhrases:
    """
    Phrasing for the data-quality / confidence caveat (S2-06b).

    `level_template` is formatted with `{level}` (e.g. "Confidence: {level}");
    `notes_template` joins the level note with the S1-09 `confidence_notes`
    reasons, formatted with `{level_note}` and `{notes}` (e.g.
    "{level_note} — {notes}"). Both are USER INPUT, superlative-checked.
    """

    level_template: str
    notes_template: str


@dataclass(frozen=True)
class ExplanationTemplates:
    """A validated template/rule set and the identity of its source file."""

    headline: str
    bands: tuple[Band, ...]  # descending by min_norm
    boolean_true_label: str
    boolean_false_label: str
    phrases: dict[str, CriterionPhrases]  # keyed by feature
    data_quality: DataQualityPhrases  # S2-06b confidence caveat phrasing
    config_id: str  # SHA-256 of the source YAML — the traceable templates identity
    version: str | None = None
    path: Path | None = None

    def phrases_for(self, feature: str) -> CriterionPhrases:
        """Phrasing for a criterion, or a loud error if it is unconfigured."""
        try:
            return self.phrases[feature]
        except KeyError as exc:
            raise ExplanationConfigError(
                f"no explanation phrasing configured for criterion '{feature}'; "
                f"every scored criterion needs an entry in the templates file"
            ) from exc

    def band_label(self, norm: float) -> str:
        """
        Band label for a normalised value in [0, 1].

        Bands are checked in descending `min_norm` order (validated at load),
        so the first band the value clears is the tightest one that applies.
        A value below every threshold falls to the lowest band, which is
        validated to have `min_norm == 0.0`, so every value lands in a band.
        """
        for band in self.bands:
            if norm >= band.min_norm:
                return band.label
        # Unreachable when the lowest band is 0.0 (enforced at load), but a
        # defensive fallback is safer than an implicit None.
        return self.bands[-1].label


def _require_mapping(raw: object, path: Path) -> dict:
    if raw is None:
        raise ExplanationConfigError(f"{path} is empty — expected a YAML mapping")
    if not isinstance(raw, dict):
        raise ExplanationConfigError(
            f"{path} must be a YAML mapping at the top level, got {type(raw).__name__}"
        )
    return raw


def _clean_text(value: object, what: str, path: Path) -> str:
    """A required non-empty string, whitespace-normalised, superlative-free."""
    if not isinstance(value, str) or not value.strip():
        raise ExplanationConfigError(f"{path}: {what} must be a non-empty string")
    text = " ".join(value.split())
    lowered = text.lower()
    for banned in BANNED_SUPERLATIVES:
        if banned in lowered:
            raise ExplanationConfigError(
                f"{path}: {what} contains the non-screening phrase '{banned}'. This "
                f"is a screening tool — use 'higher-ranked candidate' language, "
                f"never a 'best'/'optimal'/'ideal' site claim."
            )
    return text


def _parse_bands(raw: object, path: Path) -> tuple[Band, ...]:
    if not isinstance(raw, list) or not raw:
        raise ExplanationConfigError(
            f"{path}: 'bands' must be a non-empty list of {{label, min_norm}} entries"
        )
    bands: list[Band] = []
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ExplanationConfigError(
                f"{path}: bands[{i}] must be a mapping with 'label' and 'min_norm'"
            )
        label = _clean_text(entry.get("label"), f"bands[{i}].label", path)
        value = entry.get("min_norm")
        if isinstance(value, bool) or not isinstance(value, Real):
            raise ExplanationConfigError(
                f"{path}: bands[{i}] ('{label}') has a non-numeric min_norm {value!r}"
            )
        min_norm = float(value)
        if not 0.0 <= min_norm <= 1.0:
            raise ExplanationConfigError(
                f"{path}: bands[{i}] ('{label}') has min_norm {min_norm} outside "
                f"[0, 1]; a normalised value is always in [0, 1]"
            )
        bands.append(Band(label=label, min_norm=min_norm))

    ordered = sorted(bands, key=lambda b: b.min_norm, reverse=True)
    if min(b.min_norm for b in bands) != 0.0:
        raise ExplanationConfigError(
            f"{path}: the lowest band must have min_norm 0.0 so every normalised "
            f"value lands in exactly one band; lowest was "
            f"{min(b.min_norm for b in bands)}"
        )
    labels = [b.label for b in ordered]
    if len(set(labels)) != len(labels):
        raise ExplanationConfigError(f"{path}: duplicate band label(s) in {labels}")
    return tuple(ordered)


def _parse_boolean_labels(raw: object, path: Path) -> tuple[str, str]:
    body = raw if isinstance(raw, dict) else {}
    true_label = _clean_text(
        body.get("true_label", "present"), "boolean_labels.true_label", path
    )
    false_label = _clean_text(
        body.get("false_label", "absent"), "boolean_labels.false_label", path
    )
    return true_label, false_label


def _parse_phrases(raw: object, path: Path) -> dict[str, CriterionPhrases]:
    if not isinstance(raw, list) or not raw:
        raise ExplanationConfigError(
            f"{path}: 'criteria' must be a non-empty list of criterion phrase mappings"
        )
    phrases: dict[str, CriterionPhrases] = {}
    for i, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise ExplanationConfigError(
                f"{path}: criteria[{i}] must be a mapping with feature/positive/weakness"
            )
        feature = entry.get("feature")
        if not isinstance(feature, str) or not feature.strip():
            raise ExplanationConfigError(
                f"{path}: criteria[{i}] is missing a non-empty 'feature' name"
            )
        feature = feature.strip()
        if feature in phrases:
            raise ExplanationConfigError(
                f"{path}: duplicate phrasing for criterion '{feature}'"
            )
        positive = _clean_text(entry.get("positive"), f"criteria['{feature}'].positive", path)
        weakness = _clean_text(entry.get("weakness"), f"criteria['{feature}'].weakness", path)

        # S2-06b: an optional proxy marker. When present and true, a
        # proxy_caveat sentence is REQUIRED, so a proxy variable can never be
        # left unlabelled. A non-proxy criterion may not carry a caveat.
        proxy_raw = entry.get("proxy", False)
        if not isinstance(proxy_raw, bool):
            raise ExplanationConfigError(
                f"{path}: criteria['{feature}'].proxy must be true or false, "
                f"got {proxy_raw!r}"
            )
        caveat_raw = entry.get("proxy_caveat")
        if proxy_raw:
            proxy_caveat = _clean_text(
                caveat_raw, f"criteria['{feature}'].proxy_caveat", path
            )
        else:
            if caveat_raw is not None:
                raise ExplanationConfigError(
                    f"{path}: criteria['{feature}'] carries a proxy_caveat but is "
                    f"not marked 'proxy: true'; only proxy criteria may carry a "
                    f"caveat, or the caveat would never be shown"
                )
            proxy_caveat = None

        phrases[feature] = CriterionPhrases(
            feature=feature, positive=positive, weakness=weakness,
            is_proxy=proxy_raw, proxy_caveat=proxy_caveat,
        )
    return phrases


def _parse_data_quality(raw: object, path: Path) -> DataQualityPhrases:
    """
    Parse the S2-06b `data_quality` block.

    Both templates are required non-empty strings, superlative-checked. The
    level template must contain a `{level}` placeholder and the notes template
    both `{level_note}` and `{notes}`, so a misconfigured template fails at load
    rather than producing a caveat missing its data.
    """
    body = raw if isinstance(raw, dict) else {}
    level_template = _clean_text(
        body.get("level_template"), "data_quality.level_template", path
    )
    notes_template = _clean_text(
        body.get("notes_template"), "data_quality.notes_template", path
    )
    if "{level}" not in level_template:
        raise ExplanationConfigError(
            f"{path}: data_quality.level_template must contain a '{{level}}' "
            f"placeholder; got {level_template!r}"
        )
    for token in ("{level_note}", "{notes}"):
        if token not in notes_template:
            raise ExplanationConfigError(
                f"{path}: data_quality.notes_template must contain a "
                f"'{token}' placeholder; got {notes_template!r}"
            )
    return DataQualityPhrases(
        level_template=level_template, notes_template=notes_template
    )


def parse_templates(
    raw: object,
    *,
    path: Path | None = None,
    config_id: str = "",
) -> ExplanationTemplates:
    """
    Validate an already-parsed YAML mapping into an ExplanationTemplates.

    Split from `load_templates` so tests can exercise every fault path on an
    in-memory dict without writing files (the same split scoring.weights uses).
    """
    where = path if path is not None else Path("<in-memory config>")
    body = _require_mapping(raw, where)

    headline = _clean_text(body.get("headline"), "headline", where)
    bands = _parse_bands(body.get("bands"), where)
    true_label, false_label = _parse_boolean_labels(body.get("boolean_labels"), where)
    phrases = _parse_phrases(body.get("criteria"), where)
    data_quality = _parse_data_quality(body.get("data_quality"), where)

    version = body.get("version")
    return ExplanationTemplates(
        headline=headline,
        bands=bands,
        boolean_true_label=true_label,
        boolean_false_label=false_label,
        phrases=phrases,
        data_quality=data_quality,
        config_id=config_id,
        version=str(version) if version is not None else None,
        path=Path(path) if path is not None else None,
    )


def load_templates(path: Path | str | None = None) -> ExplanationTemplates:
    """
    Load and validate an explanation templates YAML file.

    Raises ExplanationConfigError (a ValueError) on a missing file, unparsable
    YAML, a missing/empty headline, a band threshold outside [0, 1], a lowest
    band that is not 0.0, a missing per-criterion phrase, or a banned
    superlative — always before the stage reads the Scored_Table or writes any
    output.

    `config_id` is the SHA-256 of the file's bytes, so the method report and
    manifest identify exactly which templates produced a given set of
    explanations.
    """
    path = Path(path) if path is not None else config.DEFAULT_TEMPLATES_PATH
    if not path.exists():
        raise ExplanationConfigError(f"Explanation templates file not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ExplanationConfigError(f"{path} is not valid YAML: {exc}") from exc
    return parse_templates(raw, path=path, config_id=sha256_file(path))
