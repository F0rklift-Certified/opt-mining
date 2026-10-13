"""
Proxy and data-quality caveat rules (S2-06b) — PURE rule layer.

AC7 requires the explanation to (a) call out any PROXY variable so it is never
read as a direct measurement, and (b) surface the relevant DATA-QUALITY /
confidence limitation for the cell. Both caveats appear on EVERY record —
eligible and excluded alike — because a proxy is a proxy and a low-confidence
cell is low-confidence regardless of whether it survived the exclusion filter.

Everything here is a pure function of (per-cell facts, templates): identical
inputs always yield identical caveat lists, which is the determinism the
explanation contract requires. Nothing opens a file or reads mutable global
state, and no phrase literal lives here — the phrasing is DATA carried on the
`ExplanationTemplates` loaded from YAML.

PROXY CAVEAT
------------
A criterion is a proxy when its templates entry is marked `proxy: true` (and
therefore carries a `proxy_caveat`). The caveat is emitted ONLY when that
criterion actually TOOK PART in the cell — i.e. the cell has a non-null value
for it — because a criterion the cell contributed nothing to (a null value that
is excluded from the score under the missing-value policy) is not "shown" for
the cell and needs no caveat. Caveats are emitted in configured criterion order
so the output is a deterministic permutation.

DATA-QUALITY CAVEAT
-------------------
The cell's S1-09 composite confidence LEVEL is always surfaced (design decision
3C — transparency on every record, including `high`). When S1-09 recorded
reasons for reduced confidence (`confidence_notes` is not the no-notes
sentinel), those reasons are appended via the notes template; otherwise the
level alone is shown.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from . import config
from .templates import ExplanationTemplates


@dataclass(frozen=True)
class CriterionParticipation:
    """
    Whether one criterion took part in a cell's score, plus its proxy identity.

    `participated` is true when the cell had a non-null value for the criterion
    (so it contributed to the score under the scoring stage's missing-value
    policy). `is_proxy` and `feature` come from the templates; the loader
    resolves them per cell so the pure builder needs no template lookup for
    participation.
    """

    feature: str
    participated: bool


def proxy_caveats(
    participation: Sequence[CriterionParticipation],
    templates: ExplanationTemplates,
) -> list[str]:
    """
    The proxy caveats for one cell, in configured criterion order.

    A criterion contributes its `proxy_caveat` iff it is marked a proxy in the
    templates AND it participated for this cell. Non-proxy criteria and proxy
    criteria the cell had no value for contribute nothing. Deterministic:
    ordered by `participation` (the loader supplies configured order).
    """
    caveats: list[str] = []
    for item in participation:
        if not item.participated:
            continue
        phrases = templates.phrases_for(item.feature)
        if phrases.is_proxy and phrases.proxy_caveat:
            caveats.append(phrases.proxy_caveat)
    return caveats


def data_quality_notes(
    level: str | None,
    notes: str | None,
    templates: ExplanationTemplates,
) -> list[str]:
    """
    The data-quality note(s) for one cell — always exactly one entry.

    The confidence LEVEL is always surfaced. When `notes` carries S1-09 reasons
    for reduced confidence (anything other than the no-notes sentinel or an
    empty/null value), they are appended via the notes template; otherwise the
    level note stands alone.

    `level` is the cell's `data_confidence`. A missing level is rendered as the
    string "unknown" rather than dropped, so the transparency guarantee (a note
    on every record) holds even for a malformed cell — validation then flags the
    unknown level rather than the record silently lacking a note.
    """
    level_text = str(level).strip() if level is not None and str(level).strip() else "unknown"
    level_note = templates.data_quality.level_template.format(level=level_text)

    reasons = "" if notes is None else str(notes).strip()
    if reasons and reasons != config.CONFIDENCE_NO_NOTES:
        return [
            templates.data_quality.notes_template.format(
                level_note=level_note, notes=reasons
            )
        ]
    return [level_note]
