"""
The Run store — resolve weights, drive the engine, materialise a Run (S2-08).

A Run is "execute the S2-05 scoring engine with these weights and materialise
the outputs" (design.md). This module does exactly that and nothing more: it
resolves a weights configuration (from explicit weights OR a named Scenario),
derives a stable content-addressed `run_id`, drives the ENGINE UNCHANGED to
score and rank, and writes the resulting Scored_Table to a per-run directory so
the read operations (tasks 3.x) can serve it.

NO DECISION ARITHMETIC LIVES HERE. Scoring, normalisation and ranking are the
S2-05 pure core (`pipeline/scoring/score.py::score_and_rank`); the Scored_Table
is assembled by the S2-05 writer (`pipeline/scoring/write.py::build_scored_table`);
weights and scenarios are validated by the S2-05 parser
(`pipeline/scoring/weights.py::parse_weights` /
`pipeline/scoring/scenarios.py::load_scenarios`). This module reuses all of them
and adds only orchestration and I/O. That reuse is the no-recompute structural
guarantee (CONTRACT.md §1, Requirement 4.3): there is no second scorer to drift
from the engine.

FAIL BEFORE WRITE. The weights/scenario are resolved and validated (by the
engine parser) before the feature table is opened, and the feature table is
loaded and checked before anything is scored or written, so an invalid request
raises without materialising a partial or misleading Run (Requirement 4.4).

PROVENANCE. Each materialised Run carries a `run.json` manifest recording the
weights identity, the scenario (if any), the integrated-input hash and the UTC
timestamp — the same provenance discipline every other data path in the
pipeline follows. Writes are atomic (tmp file + `os.replace`), via the engine's
own writers and `common.geo`.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import yaml

from ..common.geo import sha256_file, utc_now
from ..scoring import config as _scoring_config
from ..scoring.load import load_integrated
from ..scoring.normalise import compute_bounds
from ..scoring.scenarios import load_scenarios
from ..scoring.score import eligible_mask, score_and_rank
from ..scoring.weights import ScoringConfigError, WeightsConfig, parse_weights
from ..scoring.write import build_scored_table, write_scored_table
from . import config
from .models import RunHandle


def _canonical_weights_bytes(weights: WeightsConfig) -> bytes:
    """
    Deterministic byte serialisation of a resolved weights configuration.

    Used to derive a content-addressed `run_id` so two requests with the same
    resolved weights map to the same Run. The criteria are serialised in
    configured order with their feature/weight/direction — the fields that
    actually change a score or a ranking — plus the confidence-discount flag
    and factors. Rationale text is excluded: it documents a weight but does not
    change any score, so two weight sets that differ only in prose are the same
    Run.
    """
    payload = {
        "criteria": [
            {
                "feature": c.feature,
                "weight": c.weight,
                "direction": c.direction,
            }
            for c in weights.criteria
        ],
        "confidence_discount": weights.confidence_discount,
        "confidence_factors": dict(sorted(weights.confidence_factors.items())),
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _run_id_for(weights: WeightsConfig, scenario: str | None) -> str:
    """
    Stable `run_id` for a resolved Run.

    Content-addressed on the resolved weights (and the scenario name, when the
    Run came from one, so the same weight set requested two ways stays
    distinguishable in its handle without materialising twice). Deterministic:
    the same request yields the same id across sessions.
    """
    digest = hashlib.sha256()
    digest.update(_canonical_weights_bytes(weights))
    if scenario is not None:
        digest.update(b"\x00scenario=")
        digest.update(scenario.encode("utf-8"))
    return digest.hexdigest()[: config.RUN_ID_LENGTH]


def resolve_weights(
    weights: dict | None = None,
    scenario: str | None = None,
) -> tuple[WeightsConfig, str | None, str]:
    """
    Resolve a run request to a validated ``WeightsConfig`` using the ENGINE's
    own parser — never a duplicate validator (Requirement 4.3, 4.4).

    Exactly one of ``weights`` / ``scenario`` must be supplied. Returns the
    resolved ``WeightsConfig``, the scenario key (or ``None``), and the
    ``weights_id`` (the scenario key, or a content-derived id for explicit
    weights).

    Raises ``ScoringConfigError`` (a ``ValueError``) — identifying the fault
    and creating no Run — when:
      - neither or both of ``weights`` / ``scenario`` are given;
      - a named ``scenario`` is unknown;
      - an explicit ``weights`` mapping fails the engine's ``parse_weights``
        (a negative or non-numeric weight, weights summing to zero, an invalid
        direction, a duplicate or missing criterion, a missing rationale).
    """
    if (weights is None) == (scenario is None):
        raise ScoringConfigError(
            "run_analysis requires exactly one of 'weights' or 'scenario': "
            f"got weights={'set' if weights is not None else 'None'}, "
            f"scenario={scenario!r}. Supply an explicit weights configuration "
            f"or a named scenario, not both and not neither."
        )

    if scenario is not None:
        scenarios = load_scenarios(config.DEFAULT_SCENARIOS_PATH)
        if scenario not in scenarios:
            known = ", ".join(sorted(scenarios)) or "(none)"
            raise ScoringConfigError(
                f"unknown scenario {scenario!r}; known scenarios: {known}"
            )
        resolved = scenarios[scenario].weights
        return resolved, scenario, scenario

    # Explicit weights: validated by the SAME parser as the packaged weights.
    resolved = parse_weights(weights, path=None, config_id="")
    weights_id = hashlib.sha256(_canonical_weights_bytes(resolved)).hexdigest()[
        : config.RUN_ID_LENGTH
    ]
    # Stamp the content-derived identity onto the config so downstream reports
    # can trace which weights produced the Run.
    resolved = replace(resolved, config_id=weights_id)
    return resolved, None, weights_id


def run_dir(run_id: str) -> Path:
    """Directory holding a materialised Run's artefacts."""
    return config.RUNS_DIR / run_id


def _materialise(
    run_id: str,
    weights: WeightsConfig,
    scenario: str | None,
    weights_id: str,
    verbose: bool,
) -> RunHandle:
    """
    Drive the engine under ``weights`` and write the Scored_Table for this Run.

    Reuses the S2-05 pure core and writer unchanged; the only work added here is
    computing the normalisation bounds once from the eligible population (as the
    scoring stage itself does) and writing the outputs to the per-run directory.
    """
    integrated_path = Path(config.INTEGRATED_PATH)

    # Load + validate the feature table (engine loader; fails before write).
    features = load_integrated(integrated_path, weights.criteria)

    # Bounds from the eligible population only — computed once so a later read
    # of this Run's table can never disagree with what the engine scored.
    mask = eligible_mask(features)
    bounds = compute_bounds(features.loc[mask], weights.criteria)

    # THE ENGINE, UNCHANGED.
    scored = score_and_rank(features, weights, bounds=bounds)
    table = build_scored_table(features, scored, weights)

    target = run_dir(run_id)
    gpkg_path = target / config.SCORED_GPKG_FILENAME
    csv_path = target / config.SCORED_CSV_FILENAME
    write_scored_table(table, gpkg_path, csv_path)

    manifest = {
        "run_id": run_id,
        "weights_id": weights_id,
        "scenario": scenario,
        "criteria": [
            {"feature": c.feature, "weight": c.weight, "direction": c.direction}
            for c in weights.criteria
        ],
        "confidence_discount": weights.confidence_discount,
        "scored_table_gpkg": config.SCORED_GPKG_FILENAME,
        "scored_table_csv": config.SCORED_CSV_FILENAME,
        "scored_table_layer": config.SCORED_LAYER,
        "n_cells": int(len(table)),
        "integrated_path": str(integrated_path),
        "integrated_layer": config.INTEGRATED_LAYER,
        "integrated_sha256": sha256_file(integrated_path),
        "generated_utc": utc_now(),
    }
    manifest_path = target / config.RUN_MANIFEST_FILENAME
    _atomic_write_json(manifest_path, manifest)

    if verbose:
        print(
            f"  materialised run {run_id} "
            f"({'scenario ' + scenario if scenario else 'explicit weights'}, "
            f"{len(table):,} cells) -> {gpkg_path}"
        )

    return RunHandle(run_id=run_id, weights_id=weights_id, scenario=scenario)


def _atomic_write_json(path: Path, obj: dict) -> None:
    """Atomic JSON write into the run directory (tmp sibling + os.replace)."""
    import os

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def materialise_run(
    weights: dict | None = None,
    scenario: str | None = None,
    *,
    verbose: bool = False,
) -> RunHandle:
    """
    Resolve a run request, drive the engine, materialise the Run, return its
    handle.

    Idempotent by content: if a Run with the derived ``run_id`` is already
    materialised (its ``run.json`` and Scored_Table present), it is reused
    rather than re-scored, so repeated identical requests do not proliferate
    materialisations. Raises ``ScoringConfigError`` on an invalid
    weights/scenario, creating no Run (Requirement 4.4).
    """
    resolved, scenario_key, weights_id = resolve_weights(weights, scenario)
    run_id = _run_id_for(resolved, scenario_key)

    target = run_dir(run_id)
    manifest_path = target / config.RUN_MANIFEST_FILENAME
    gpkg_path = target / config.SCORED_GPKG_FILENAME
    if manifest_path.exists() and gpkg_path.exists():
        if verbose:
            print(f"  reusing materialised run {run_id}")
        return RunHandle(run_id=run_id, weights_id=weights_id, scenario=scenario_key)

    return _materialise(run_id, resolved, scenario_key, weights_id, verbose)
