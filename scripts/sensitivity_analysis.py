#!/usr/bin/env python3
"""
Sensitivity analysis of the baseline ranking (S4-08).

How much does the ranked shortlist depend on the exact weights? This runner
re-scores the frozen integrated NSW table with the real engine
(``pipeline.scoring.score.score_and_rank``) under:

  1. one-at-a-time weight perturbations — each criterion's weight scaled by
     -20 %, -10 %, +10 % and +20 % with every other weight unchanged (weights
     are relative, so this shifts that criterion's share of the score); and
  2. the two named scenarios in ``pipeline/scoring/scenarios.yaml``.

Every run shares ONE set of normalisation bounds computed from the eligible
cells, exactly as ``compare_scenarios`` does, so only the weights differ. Each
run is compared with the baseline ranking:

  - Spearman rank correlation over all eligible cells;
  - Kendall tau over the union of the two top-100 sets;
  - top-20 and top-50 overlap (share of the baseline set still present);
  - whether the baseline rank-1 cell stays rank 1;
  - the largest rank shift among the baseline top-20 cells.

Nothing is written into the engine's outputs. Results go to:

    DATA/sensitivity/optmining_sensitivity_2026_nsw.json
    DATA/sensitivity/optmining_sensitivity_2026_nsw.md

Usage:
    python -m scripts.sensitivity_analysis
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.common.geo import atomic_write_text, sha256_file
from pipeline.sanity.checks import _correlation
from pipeline.scoring import config as scoring_config
from pipeline.scoring.load import load_integrated
from pipeline.scoring.normalise import compute_bounds
from pipeline.scoring.scenarios import load_scenarios, run_scenario
from pipeline.scoring.score import eligible_mask, score_and_rank
from pipeline.scoring.weights import WeightsConfig, load_weights

PERTURBATIONS = (-0.20, -0.10, 0.10, 0.20)
TOP_SETS = (20, 50)
KENDALL_TOP_N = 100
SHIFT_TOP_N = 20

OUTPUT_DIR = scoring_config.PROJECT_ROOT / "DATA" / "sensitivity"
OUTPUT_STEM = f"optmining_sensitivity_{scoring_config.SCORING_VINTAGE}_nsw"


def perturb(weights: WeightsConfig, feature: str, change: float) -> WeightsConfig:
    """`weights` with one criterion's weight scaled by (1 + change)."""
    criteria = tuple(
        dataclasses.replace(c, weight=c.weight * (1.0 + change)) if c.feature == feature else c
        for c in weights.criteria
    )
    return dataclasses.replace(
        weights, criteria=criteria, config_id=f"{weights.config_id}:{feature}{change:+.0%}"
    )


def eligible_ranks(scored: pd.DataFrame, mask: pd.Series) -> pd.Series:
    """Engine rank of every eligible cell, indexed by cell_id."""
    ranked = scored.loc[mask, [scoring_config.CELL_ID_COLUMN, scoring_config.RANK_COLUMN]]
    return ranked.set_index(scoring_config.CELL_ID_COLUMN)[scoring_config.RANK_COLUMN].astype(int)


def _top(ranks: pd.Series, n: int) -> set[str]:
    return set(ranks.nsmallest(n).index)


def kendall_tau(a: np.ndarray, b: np.ndarray) -> float | None:
    """Kendall tau-a of two equal-length rank vectors (O(n^2); n is small)."""
    n = len(a)
    if n < 2:
        return None
    da = np.sign(a[:, None] - a[None, :])
    db = np.sign(b[:, None] - b[None, :])
    upper = np.triu_indices(n, k=1)
    return float((da[upper] * db[upper]).sum() / len(upper[0]))


def compare_rankings(base: pd.Series, alt: pd.Series) -> dict:
    """Rank-stability metrics of `alt` against `base` (both indexed by cell_id)."""
    alt = alt.reindex(base.index)
    spearman = _correlation(base.to_numpy(float), alt.to_numpy(float), "spearman")

    union = sorted(_top(base, KENDALL_TOP_N) | _top(alt, KENDALL_TOP_N))
    tau = kendall_tau(base.loc[union].to_numpy(float), alt.loc[union].to_numpy(float))

    base_top = base.nsmallest(SHIFT_TOP_N)
    shifts = (alt.loc[base_top.index] - base_top).abs()

    metrics = {
        "spearman_all_eligible": spearman,
        f"kendall_tau_top{KENDALL_TOP_N}_union": tau,
        "rank1_unchanged": bool(base.idxmin() == alt.idxmin()),
        "alt_rank1_cell": str(alt.idxmin()),
        f"max_rank_shift_base_top{SHIFT_TOP_N}": int(shifts.max()),
    }
    for n in TOP_SETS:
        metrics[f"top{n}_overlap"] = len(_top(base, n) & _top(alt, n)) / n
    return metrics


def run_analysis(features: pd.DataFrame, weights: WeightsConfig, scenarios: dict) -> dict:
    """Score the baseline, every perturbation and every scenario; compare each to the baseline."""
    mask = eligible_mask(features)
    bounds = compute_bounds(features.loc[mask], weights.criteria)
    base = eligible_ranks(score_and_rank(features, weights, bounds=bounds), mask)

    runs = []
    for criterion in weights.criteria:
        for change in PERTURBATIONS:
            alt = eligible_ranks(
                score_and_rank(features, perturb(weights, criterion.feature, change), bounds=bounds),
                mask,
            )
            runs.append({
                "kind": "perturbation",
                "criterion": criterion.feature,
                "change": change,
                "weight": criterion.weight * (1.0 + change),
                **compare_rankings(base, alt),
            })
    for name, scenario in scenarios.items():
        alt = eligible_ranks(run_scenario(features, scenario, bounds=bounds), mask)
        runs.append({"kind": "scenario", "scenario": name, "label": scenario.label,
                     **compare_rankings(base, alt)})

    return {
        "n_eligible": int(mask.sum()),
        "baseline_rank1_cell": str(base.idxmin()),
        "baseline_top20": list(base.nsmallest(20).index),
        "baseline_weights": {c.feature: c.weight for c in weights.criteria},
        "perturbations": list(PERTURBATIONS),
        "runs": runs,
    }


def _fmt(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def render_markdown(result: dict) -> str:
    tau_key = f"kendall_tau_top{KENDALL_TOP_N}_union"
    shift_key = f"max_rank_shift_base_top{SHIFT_TOP_N}"
    lines = [
        "# Sensitivity analysis — baseline ranking (S4-08)",
        "",
        f"- Integrated table SHA-256: `{result['integrated_sha256']}`",
        f"- Code version: `{result['code_version']}`",
        f"- Eligible cells: {result['n_eligible']:,}",
        f"- Baseline rank-1 cell: `{result['baseline_rank1_cell']}`",
        "",
        "Each row re-scores every eligible cell with one change and compares the",
        "ranking with the baseline. Normalisation bounds are shared, so only the",
        "weights differ. Overlap is the share of the baseline top-N still in the",
        "top-N.",
        "",
        "| Run | Spearman (all) | Kendall τ (top-100 union) | Top-20 overlap | Top-50 overlap"
        " | Rank 1 unchanged | Max shift of baseline top-20 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for run in result["runs"]:
        name = (
            f"{run['criterion']} {run['change']:+.0%}"
            if run["kind"] == "perturbation"
            else f"Scenario: {run['label']}"
        )
        lines.append(
            f"| {name} | {_fmt(run['spearman_all_eligible'])} | {_fmt(run[tau_key])} "
            f"| {_fmt(run['top20_overlap'])} | {_fmt(run['top50_overlap'])} "
            f"| {_fmt(run['rank1_unchanged'])} | {_fmt(run[shift_key])} |"
        )
    return "\n".join(lines) + "\n"


def _code_version() -> str:
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                             check=True, cwd=scoring_config.PROJECT_ROOT).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"],
                               capture_output=True, text=True, check=True,
                               cwd=scoring_config.PROJECT_ROOT).stdout.strip()
        return f"{sha}-dirty" if dirty else sha
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main(argv: list[str] | None = None) -> dict:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args(argv)

    weights = load_weights(scoring_config.DEFAULT_WEIGHTS_PATH)
    features = load_integrated(scoring_config.INTEGRATED_PATH, weights.criteria)
    result = run_analysis(features, weights, load_scenarios())
    result["integrated_sha256"] = sha256_file(Path(scoring_config.INTEGRATED_PATH))
    result["code_version"] = _code_version()

    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / f"{OUTPUT_STEM}.json"
    md_path = args.output_dir / f"{OUTPUT_STEM}.md"
    atomic_write_text(json_path, json.dumps(result, indent=2) + "\n")
    atomic_write_text(md_path, render_markdown(result))
    print(f"  -> {json_path}\n  -> {md_path}")
    return result


if __name__ == "__main__":
    main()
