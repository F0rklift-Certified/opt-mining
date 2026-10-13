"""S3-10 demo rehearsal harness — drive the running MVP through the §10 flow.

This is the S3-10 rehearsal tool (design Decision 1-H / 1-I). Like
``app/smoke_test.py`` it speaks to the running web/API stack over HTTP using
ONLY Python's standard library, so it runs identically on a stack-only host.

Run from the repository root against the running stack::

    python app/rehearse_demo.py --output docs/release/rehearsal.json

Set ``NEXT_PUBLIC_API_BASE_URL`` / ``CORS_ALLOW_ORIGINS`` for non-default ports
(exactly as ``smoke_test.py`` does).

Design contract (see .agents/tasks/s3-10-final-demo/design.md):

* ALL fatal invariants are computed from the HTTP responses alone — ranks
  ordered, scores in ``[0, 1]``, site detail agrees with the ranked row and
  carries a non-empty verbatim explanation, the contribution-sum reconciles to
  ``suitability_score`` within ``RECONCILE_TOLERANCE`` (``1e-9``), exclusions
  are non-empty and each carries a reason, ``/scenario-comparison`` returns
  non-empty rows each carrying ``cell_id``/``rank_a``/``rank_b``/``rank_delta``
  keys (values may be null), and the sanity result is present with its caveat.
  None of this needs the ``pipeline`` engine to be importable.
* Whether a cell moves between scenarios is DATA-DEPENDENT and is CAPTURED as
  evidence (a count of cells with ``|rank_a - rank_b| >= 1``), never asserted.
* The engine recompute (``--external-sanity``) is feature-detected with
  ``try/except ImportError``; when ``pipeline`` is absent the harness records
  ``"engine_recompute": "skipped (engine not importable)"`` and still runs every
  HTTP invariant and exits normally.
* ``--require-final`` yields a DISTINCT non-zero exit when the review/merge/
  client gates are unresolved, so a green technical run is never mistaken for
  Checkpoint D acceptance.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

# The engine's own reconciliation tolerance for "contributions sum to the
# score" (pipeline/scoring/config.py::RECONCILE_TOLERANCE). Mirrored as a
# module literal so the harness never needs to import the engine to run the
# fatal contribution-sum invariant.
RECONCILE_TOLERANCE = 1e-9

# Readiness-matrix acceptance criteria this rehearsal must be able to evidence
# (AC1..AC12 — the Must set plus AC10/AC12; see design Decision 4).
EXPECTED_AC_KEYS = tuple(f"AC{n}" for n in range(1, 13))

# Stale tokens from the OLD lineage's demo-script that must NEVER leak into an
# S3-10 artifact (design "Baseline divergence" / "Stale-value leakage").
STALE_TOKENS = (
    "outside_nsw_land",
    "23,266",
    "604d051bb2deb7d8",
    "e43fd84cddd53cb5",
)

READINESS_TIMEOUT_S = 90

# The S1-10/S2-01 documented default ("Baseline") weights, mirrored verbatim
# from pipeline/scoring/scoring_weights.yaml exactly as the web client mirrors
# them in app/web/app/shell/AnalysisControls.tsx (BASELINE_CRITERIA). The API
# has NO "baseline" named scenario — the app's Baseline run is a POST /runs with
# an explicit default-weights body (AppShell.buildRunRequest), so the rehearsal
# must request it the same way the real web client does, not as a scenario key.
BASELINE_CRITERIA = [
    {"feature": "wind_speed", "weight": 0.35, "direction": "higher_is_better",
     "rationale": "Primary resource indicator; energy yield scales roughly with the cube of wind speed."},
    {"feature": "dist_transmission_km", "weight": 0.20, "direction": "lower_is_better",
     "rationale": "Connection cost is a major capex component and scales with distance to the nearest >=132 kV line."},
    {"feature": "demand_proxy", "weight": 0.15, "direction": "higher_is_better",
     "rationale": "Proximity to electrical demand improves offtake prospects (a NEM-region annual mean proxy)."},
    {"feature": "dist_substation_km", "weight": 0.10, "direction": "lower_is_better",
     "rationale": "Substation proximity reduces interconnection complexity; weighted below transmission distance because the two are partly collinear."},
    {"feature": "slope_deg", "weight": 0.10, "direction": "lower_is_better",
     "rationale": "Flatter terrain lowers civil-works and turbine-siting cost, complementing the hard slope exclusion."},
    {"feature": "inside_rez", "weight": 0.10, "direction": "higher_is_better",
     "rationale": "Cells inside a declared NSW Renewable Energy Zone benefit from coordinated network planning."},
]


# ---------------------------------------------------------------------------
# A distinct non-zero exit code so a technically-green run under --require-final
# is never mistaken for Checkpoint D (human) acceptance.
# ---------------------------------------------------------------------------
EXIT_OK = 0
EXIT_RUNTIME = 1          # stack not ready / service error / invariant violated
EXIT_NOT_FINAL = 3        # technical success, but review/merge/client gates open


# ===========================================================================
# Pure predicates & JSON-shaping helpers (importable, unit-testable with no
# running stack — FEAT-001's fast tests and FEAT-003's readiness test depend on
# these function names/signatures).
# ===========================================================================


def ranks_are_ordered(rows: list[dict]) -> bool:
    """True if ``rows`` are strictly rank-ordered (ascending ``rank``).

    An empty list is NOT ordered-valid for a demo (a packaged scenario must
    return ranked cells), so this returns False on empty input.
    """
    if not rows:
        return False
    ranks = [row.get("rank") for row in rows]
    if any(r is None for r in ranks):
        return False
    return all(a < b for a, b in zip(ranks, ranks[1:]))


def scores_in_unit_interval(rows: list[dict]) -> bool:
    """True if every row's ``suitability_score`` is a number in ``[0, 1]``."""
    if not rows:
        return False
    for row in rows:
        score = row.get("suitability_score")
        if not isinstance(score, (int, float)):
            return False
        if score < 0.0 or score > 1.0:
            return False
    return True


def contributions_reconcile(detail: dict, tol: float = RECONCILE_TOLERANCE) -> bool:
    """True if ``sum(detail['contributions'].values())`` reconciles to the score.

    Reconciliation is ``abs(sum(contributions) - suitability_score) <= tol``,
    the engine's own ``RECONCILE_TOLERANCE`` rule — never bit-exact equality.
    Computed from the ``GET /runs/{run_id}/sites/{cell_id}`` response alone.
    """
    contributions = detail.get("contributions") or {}
    score = detail.get("suitability_score")
    if not contributions or not isinstance(score, (int, float)):
        return False
    total = sum(contributions.values())
    return abs(total - score) <= tol


def scenario_rows_have_keys(rows: list[dict]) -> bool:
    """True if ``rows`` is non-empty and each row carries the four required keys.

    The structural invariant for ``POST /scenario-comparison``: every row must
    carry ``cell_id``/``rank_a``/``rank_b``/``rank_delta``. Values MAY be null
    (a cell ranked under only one side), which is valid and does not fail.
    """
    if not rows:
        return False
    required = ("cell_id", "rank_a", "rank_b", "rank_delta")
    return all(all(key in row for key in required) for row in rows)


def count_moved_cells(rows: list[dict]) -> int:
    """Count cells whose rank moved between the two scenarios.

    A cell "moved" when ``abs(rank_a - rank_b) >= 1``. Rows where either rank is
    null (ranked under only one side) are not counted as moved. Captured as
    evidence only — never asserted as a gate.
    """
    moved = 0
    for row in rows:
        rank_a = row.get("rank_a")
        rank_b = row.get("rank_b")
        if rank_a is None or rank_b is None:
            continue
        if abs(rank_a - rank_b) >= 1:
            moved += 1
    return moved


def first_moved_example(rows: list[dict]) -> dict | None:
    """Return the first row with ``|rank_a - rank_b| >= 1``, else ``None``."""
    for row in rows:
        rank_a = row.get("rank_a")
        rank_b = row.get("rank_b")
        if rank_a is None or rank_b is None:
            continue
        if abs(rank_a - rank_b) >= 1:
            return row
    return None


def readiness_keys_cover_acs(
    matrix: dict, expected: tuple[str, ...] = EXPECTED_AC_KEYS
) -> bool:
    """True if ``matrix`` has an entry for every expected acceptance-criterion key.

    Used by the AC-evidence readiness matrix (``docs/release/readiness.json``)
    so a dropped criterion is caught. FEAT-003's readiness test depends on this.
    """
    return all(key in matrix for key in expected)


def find_stale_tokens(text: str, tokens: tuple[str, ...] = STALE_TOKENS) -> list[str]:
    """Return the stale old-lineage tokens that appear in ``text`` (order-stable).

    A non-empty result means a stale value from the divergent lineage leaked
    into an artifact; the demo/docs must never contain any of these.
    """
    return [token for token in tokens if token in text]


# ---------------------------------------------------------------------------
# A non-fatal invariant failure the rehearsal records and then exits non-zero.
# ---------------------------------------------------------------------------
class RehearsalError(RuntimeError):
    """A fatal rehearsal condition (invariant violated / service error)."""


# ===========================================================================
# HTTP driver (stdlib only, mirroring smoke_test.py).
# ===========================================================================


def _resolve_endpoints() -> tuple[str, str]:
    """Resolve the API base URL and the browser origin from the environment."""
    api = os.environ.get("NEXT_PUBLIC_API_BASE_URL", "http://localhost:8000").rstrip("/")
    web = os.environ.get("CORS_ALLOW_ORIGINS", "http://localhost:3000").split(",")[0].strip()
    return api, web


def _wait_ready(api: str, web: str, timeout: float = READINESS_TIMEOUT_S) -> None:
    """Bounded readiness loop; raise ``RehearsalError`` if the stack never answers."""
    for url in (api + "/openapi.json", web):
        deadline = time.monotonic() + timeout
        while True:
            try:
                with urllib.request.urlopen(url, timeout=5) as response:
                    if response.status == 200:
                        break
            except (OSError, urllib.error.URLError):
                pass
            if time.monotonic() >= deadline:
                raise RehearsalError(
                    f"Service did not become ready within {timeout:.0f}s: {url}"
                )
            time.sleep(1)


class _Client:
    """A thin HTTP client that records any service-error body verbatim."""

    def __init__(self, api: str, web: str) -> None:
        self.api = api
        self.web = web

    def request(self, path: str, payload: dict | None = None) -> Any:
        """GET (payload=None) or POST ``path``; raise RehearsalError on error status.

        On a non-200 the status and the ``detail`` body are carried verbatim in
        the raised error so the caller can record them into the evidence JSON.
        """
        req = urllib.request.Request(
            self.api + path,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={"Origin": self.web, "Content-Type": "application/json"},
            method="GET" if payload is None else "POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=90) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            raise RehearsalError(
                f"{req.get_method()} {path} returned HTTP {exc.code}: {body}"
            ) from exc
        except (OSError, urllib.error.URLError) as exc:
            raise RehearsalError(f"{req.get_method()} {path} failed: {exc}") from exc


# ===========================================================================
# The rehearsal (drives the §10 sequence, asserts the fatal invariants, and
# returns the full evidence set as a JSON-serialisable dict).
# ===========================================================================


def rehearse(client: _Client, *, external_sanity: bool = False) -> dict:
    """Drive the §10 flow over HTTP and return the evidence dict.

    Raises ``RehearsalError`` on the first violated fatal invariant or service
    error (with the status/detail captured in the message).
    """
    evidence: dict[str, Any] = {
        "api_base_url": client.api,
        "web_origin": client.web,
        "runs": {},
    }

    # §10 step 1 — data-quality (the banner source).
    quality = client.request("/data-quality")
    if not quality.get("checks"):
        raise RehearsalError("GET /data-quality returned no checks")
    evidence["data_quality"] = {
        "passed": quality.get("passed"),
        "check_count": len(quality["checks"]),
    }

    # §10 steps 2/3/7 — baseline, wind_led, grid_led runs. The API has no
    # "baseline" named scenario; the app's Baseline run is an explicit
    # default-weights POST /runs (exactly what the web client sends via
    # buildRunRequest), while wind_led / grid_led are named scenarios.
    run_requests: dict[str, dict] = {
        "baseline": {"weights": {"criteria": BASELINE_CRITERIA}},
        "wind_led": {"scenario": "wind_led"},
        "grid_led": {"scenario": "grid_led"},
    }
    run_ids: dict[str, str] = {}
    for label, payload in run_requests.items():
        run = client.request("/runs", payload)
        run_id = run.get("run_id")
        if not run_id:
            raise RehearsalError(f"POST /runs ({label}) returned no run_id")
        run_ids[label] = run_id

    # Capture the frozen input SHA when the service surfaces it on a run handle.
    evidence["run_ids"] = run_ids

    # Drive the run-scoped surfaces off the wind_led run (the §10 lead run).
    primary = run_ids["wind_led"]
    prefix = "/runs/" + primary

    # §10 steps 5/6 — ranked results + site detail (fatal invariants).
    rows = client.request(prefix + "/results?top_n=10")
    if not ranks_are_ordered(rows):
        raise RehearsalError("ranked rows are not strictly rank-ordered")
    if not scores_in_unit_interval(rows):
        raise RehearsalError("a suitability_score is outside [0, 1]")

    top = rows[0]
    detail = client.request(prefix + "/sites/" + top["cell_id"])
    if detail.get("cell_id") != top["cell_id"]:
        raise RehearsalError("site detail cell_id does not agree with the ranked row")
    if detail.get("suitability_score") != top.get("suitability_score"):
        raise RehearsalError("site detail score does not agree with the ranked row")
    if not detail.get("explanation"):
        raise RehearsalError("site detail carries no verbatim explanation")
    if not contributions_reconcile(detail):
        raise RehearsalError(
            "contributions do not reconcile to suitability_score within "
            f"{RECONCILE_TOLERANCE}"
        )

    evidence["top_cells"] = [
        {
            "cell_id": row["cell_id"],
            "suitability_score": row["suitability_score"],
            "rank": row["rank"],
        }
        for row in rows
    ]
    evidence["rank_1_detail"] = {
        "cell_id": detail["cell_id"],
        "suitability_score": detail["suitability_score"],
        "rank": detail.get("rank"),
        "contributions": detail.get("contributions", {}),
    }

    # §10 step 4 — exclusions (fatal: non-empty, each carries a reason).
    exclusions = client.request(prefix + "/exclusions")
    if not exclusions:
        raise RehearsalError("GET /exclusions returned no excluded cells")
    for excluded in exclusions:
        if not (excluded.get("reason_codes") or excluded.get("reason_text")):
            raise RehearsalError(
                f"excluded cell {excluded.get('cell_id')} carries no reason"
            )
    sample_excluded = exclusions[0]
    excluded_detail = client.request(prefix + "/sites/" + sample_excluded["cell_id"])
    evidence["excluded_example"] = {
        "cell_id": sample_excluded["cell_id"],
        "reason_codes": sample_excluded.get("reason_codes", []),
        "reason_text": sample_excluded.get("reason_text", ""),
        "suitability_score": excluded_detail.get("suitability_score"),
        "rank": excluded_detail.get("rank"),
    }
    evidence["exclusion_count"] = len(exclusions)

    # §10 step 5 — map cells (run-scoped GeoJSON FeatureCollection).
    cells = client.request(prefix + "/cells")
    features = cells.get("features", [])
    eligible_count = sum(
        1 for f in features if (f.get("properties") or {}).get("eligible")
    )
    evidence["cells"] = {
        "total": len(features),
        "eligible": eligible_count,
        "excluded": len(features) - eligible_count,
    }

    # §10 step 7 — scenario comparison (structural invariant + captured moves).
    comparison = client.request(
        "/scenario-comparison",
        {"scenario_a": "wind_led", "scenario_b": "grid_led"},
    )
    comparison_rows = comparison.get("rows", [])
    if not scenario_rows_have_keys(comparison_rows):
        raise RehearsalError(
            "/scenario-comparison rows empty or missing "
            "cell_id/rank_a/rank_b/rank_delta keys"
        )
    moved = count_moved_cells(comparison_rows)
    example = first_moved_example(comparison_rows)
    evidence["scenario_comparison"] = {
        "labels": comparison.get("labels", {}),
        "row_count": len(comparison_rows),
        "moved_cell_count": moved,
        "moved_example": example,  # may be None (zero movement is honest, not fatal)
    }

    # §10 step 8 — sanity check (fatal: present with its caveat).
    sanity = client.request("/sanity-check")
    if not sanity.get("caveat"):
        raise RehearsalError("GET /sanity-check returned no caveat")
    wind_farms = sanity.get("wind_farms", [])
    evidence["sanity"] = {
        "caveat": sanity["caveat"],
        "top_band_n": sanity.get("top_band_n"),
        "wind_farms": [
            {
                "wind_farm": wf.get("wind_farm"),
                "cell_id": wf.get("cell_id"),
                "rank": wf.get("rank"),
                "percentile": wf.get("percentile"),
                "in_upper_quartile": wf.get("in_upper_quartile"),
                "in_top_band": wf.get("in_top_band"),
            }
            for wf in wind_farms
        ],
        "contradiction_count": len(sanity.get("contradictions", [])),
    }

    # Optional, feature-detected engine recompute (Should-level evidence only).
    evidence["engine_recompute"] = _maybe_recompute(external_sanity)

    return evidence


def _maybe_recompute(external_sanity: bool) -> str:
    """Optional reference-anomaly recompute, feature-detected via ImportError.

    When ``--external-sanity`` is not requested, this is not attempted. When it
    is requested but the ``pipeline`` engine is not importable (a stack-only
    host), record a skip and let the HTTP invariants stand alone.
    """
    if not external_sanity:
        return "not requested"
    try:
        import pipeline  # noqa: F401
    except ImportError:
        return "skipped (engine not importable)"
    # The engine is importable; the recompute itself is Should-level evidence
    # and intentionally not run here (no scoring/weights/baseline change is in
    # scope for S3-10). Record that the engine is available.
    return "engine importable (reference recompute not run; no baseline change in scope)"


# ===========================================================================
# CLI
# ===========================================================================


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="rehearse_demo.py",
        description=(
            "Drive the running Opt-Mining MVP through the §10 demo sequence over "
            "HTTP and capture the rehearsal evidence as JSON. Uses only Python's "
            "standard library (like app/smoke_test.py)."
        ),
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help=(
            "Path to write the rehearsal evidence JSON. Parent directories "
            "(e.g. docs/release/) are created if absent."
        ),
    )
    parser.add_argument(
        "--require-final",
        action="store_true",
        help=(
            "Exit with a DISTINCT non-zero code (3) when the review/merge/client "
            "gates are unresolved, so a technically-green run is never mistaken "
            "for Checkpoint D (human) acceptance."
        ),
    )
    parser.add_argument(
        "--external-sanity",
        action="store_true",
        help=(
            "Also attempt the optional engine reference-anomaly recompute "
            "(feature-detected; skipped with a recorded reason when the pipeline "
            "engine is not importable). The HTTP invariants always run regardless."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)

    api, web = _resolve_endpoints()
    client = _Client(api, web)

    evidence: dict[str, Any] = {}
    exit_code = EXIT_OK
    try:
        _wait_ready(api, web)
        evidence = rehearse(client, external_sanity=args.external_sanity)
        evidence["result"] = "PASS"
    except RehearsalError as exc:
        evidence["result"] = "FAIL"
        evidence["error"] = str(exc)
        exit_code = EXIT_RUNTIME

    # The --require-final gate: a technical PASS is still NOT Checkpoint D.
    if exit_code == EXIT_OK and args.require_final:
        evidence["final_gate"] = (
            "NOT FINAL: an automated green rehearsal is not Checkpoint D "
            "acceptance; review/merge/client sign-off gates remain open."
        )
        exit_code = EXIT_NOT_FINAL

    # Always write the evidence set (create docs/release/ etc. if absent).
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")

    if evidence.get("result") == "FAIL":
        print(f"FAIL: {evidence.get('error')}", file=sys.stderr)
    elif exit_code == EXIT_NOT_FINAL:
        print(f"PASS (technical) but NOT FINAL; evidence -> {args.output}")
    else:
        print(f"PASS: §10 rehearsal; evidence -> {args.output}")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
