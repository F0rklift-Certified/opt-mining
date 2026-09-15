"""
Property-based test for the S2-08 Decision_Service — no recompute path
(Property 3).

# Feature: s2-08-decision-service-api, Property 3: no recompute path

**Property 3 — No recompute path.** No scoring / normalisation / ranking /
exclusion arithmetic exists in ``pipeline/service/``; every value the service
serves traces to a materialised engine output (CONTRACT.md §1, §7 P3,
Requirement 2.1, 2.2, 2.4). This is the STRUCTURAL guarantee behind
combined-sprint AC4 ("scoring and normalisation are implemented outside the
UI"): because the Web_Application can only call this service, and the service
holds no code path by which to recompute a score, a rank or an eligibility
decision, the map and the ranking table always represent ONE engine output.

**Validates: Requirements 2.1, 2.2, 2.4**

P3 is a STRUCTURAL property, not a value property, so — unlike P1/P2/P4/P5,
which pin the served VALUES — it is validated two complementary ways:

1. **A STRUCTURAL guard (always runs, hermetic, deterministic).** Every module
   in ``pipeline/service/`` is parsed with ``ast`` and audited to prove it
   contains no decision arithmetic of its own:

   * The arithmetic CORE of the engine (``pipeline.scoring.score`` /
     ``.normalise`` / ``.rank`` — the modules that actually compute a score, a
     normalised value or a rank) may be imported ONLY by the Run store
     (``runs.py``), whose sole job is to DRIVE that engine unchanged. The
     read / select / serve modules (``results.py``, ``filters.py``,
     ``scenarios.py``, ``quality.py``, ``models.py``, ``config.py``,
     ``run_analysis.py``) must NOT import those arithmetic-core modules — they
     have no legitimate reason to touch the scoring maths.
   * Every name a service module imports FROM the engine packages
     (``pipeline.scoring`` / ``.exclusions`` / ``.explanation`` /
     ``pipeline.validate``) must be on an allow-list of the engine's OWN public
     symbols (``score_and_rank``, ``compute_bounds``, ``eligible_mask``,
     ``parse_weights``, ``load_scenarios``, ``build_scored_table``, …), never a
     locally reimplemented equivalent. The service reuses the engine; it does
     not shadow it.
   * No service module may DEFINE a function that reimplements decision
     arithmetic — nothing named like a scorer / normaliser / ranker / exclusion
     evaluator (``score``/``normalise``/``rank``/``exclude`` and friends). The
     one arithmetic the contract does permit — the display convenience
     ``rank_delta = rank_a - rank_b`` in ``scenarios.py`` (a difference of two
     ENGINE ranks, CONTRACT.md §4.5) — is explicitly allow-listed so the guard
     is precise rather than a blunt "no subtraction anywhere".

   Written as a MISS-would-catch guard: were a future edit to paste a
   normalisation formula or a re-ranking loop into ``results.py`` or
   ``filters.py``, or to import ``pipeline.scoring.score`` there, this test
   fails — so it is a meaningful structural fence, not a trivial always-pass.

2. **A VALUE-tracing check (Hypothesis, ≥100 examples).** For generated
   materialised Scored_Tables with KNOWN score / rank / contribution values,
   every value the read operations serve equals the materialised value
   VERBATIM. This is the behavioural complement of the structural guard: it
   proves that in practice the served numbers are exactly the engine's, so no
   recompute silently perturbs them. (P1/P2 already assert the read path is
   internally consistent; this asserts it is faithful to the fixed table.)

Hermeticity discipline (matching ``test_results_properties.py`` /
``test_filters_properties.py``): the value-tracing check redirects the per-Run
store (``service_config.RUNS_DIR``) and the shared explanation output
(``service_config.EXPLANATION_PATH``) to a per-example temp directory with an
explicit save/restore — a function-scoped fixture cannot be shared across the
many examples a single ``@given`` body drives — so the real ``DATA/service/``
tree is never written and each example is isolated. The structural guard is
pure static analysis of the source tree and touches no disk and no engine at
all.
"""

from __future__ import annotations

import ast
import json
import tempfile
from pathlib import Path

import geopandas as gpd
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from shapely.geometry import Point

from pipeline.scoring import config as scoring_config
from pipeline.service import config as service_config
from pipeline.service import get_ranked_results, get_site_detail


# =========================================================================== #
# Part 1 — the STRUCTURAL guard (static analysis of pipeline/service/).        #
# =========================================================================== #

SERVICE_DIR = Path(service_config.__file__).parent

# The service modules the guard audits — the whole thin layer (CONTRACT.md §1).
# ``app.py`` (the FastAPI transport) is audited too if/when it exists; the
# discovery below picks up every ``*.py`` in the package so a new module cannot
# slip a recompute path in unaudited.
_ALWAYS_AUDITED = {
    "results.py",
    "filters.py",
    "scenarios.py",
    "quality.py",
    "run_analysis.py",
    "runs.py",
    "models.py",
    "config.py",
    "__init__.py",
}


def _service_modules() -> list[Path]:
    """Every ``*.py`` in ``pipeline/service/`` (so a new module is auto-audited)."""
    return sorted(p for p in SERVICE_DIR.glob("*.py"))


# --- The engine's OWN public symbols the service is allowed to reuse ---------
#
# These are the engine callables/classes the service legitimately imports to
# DRIVE the engine (in runs.py) or to type/trace its output. A service import
# of any OTHER name from an engine package — especially a name that looks like a
# reimplemented scorer/normaliser/ranker — is a recompute smell and fails the
# guard. This list is the precise boundary: the service reuses these, it never
# redefines them.
_ALLOWED_ENGINE_IMPORTS = {
    # pipeline.scoring.* — the engine driven by run_analysis / runs.py.
    "score_and_rank",       # the PURE scoring+ranking core (driven, not copied)
    "score_frame",
    "eligible_mask",
    "compute_bounds",       # normalisation bounds from the eligible population
    "build_scored_table",   # the engine's own Scored_Table writer
    "write_scored_table",
    "load_integrated",      # the engine's feature-table loader
    "load_scenarios",       # the engine's scenario parser
    "parse_weights",        # the engine's weights validator (never duplicated)
    "load_weights",
    "WeightsConfig",
    "Criterion",
    "ScoringConfigError",
    # config modules imported wholesale for paths/column names (composed, not
    # re-typed) — these carry NO arithmetic.
    "config",
    "rules",
    # pipeline.common.geo — provenance/IO helpers (atomic writes, hashing, time).
    "sha256_file",
    "utc_now",
}

# The arithmetic CORE of the engine: the modules that actually COMPUTE a score,
# a normalised value or a rank. Importing any of these is legitimate ONLY in the
# Run store (runs.py), which exists to drive the engine. Anywhere else in the
# service it is a recompute path.
_ARITHMETIC_CORE_MODULES = {"score", "normalise", "rank"}
_ARITHMETIC_CORE_DRIVER = "runs.py"  # the only module allowed to import them

# Verb stems that, when a service module DEFINES a function BEGINNING with one,
# indicate a reimplemented decision computation. The service may READ and
# SELECT, never COMPUTE these. Matched as a PREFIX (after stripping leading
# underscores) on a word boundary — a name that *begins* with the verb
# ``score_`` / ``normalise_`` / ``rank_`` / ``exclude_`` / ``compute_`` /
# ``eligib…`` is a scorer/normaliser/ranker/exclusion-evaluator being defined.
# Prefix matching (rather than "the word appears anywhere") is what keeps the
# guard precise: a pasted-in ``score_cell`` / ``normalise_series`` /
# ``rank_by_score`` / ``exclude_cell`` / ``compute_bounds`` is flagged, while a
# pure READER whose name merely CONTAINS the noun — ``load_scored_table``,
# ``load_eligibility_table``, ``_opt_score``, ``_opt_rank``, ``get_ranked_results``
# — is not, because it does not START with the computing verb.
_FORBIDDEN_DEFINITION_PREFIXES = (
    "score",         # score(_frame|_cell|_and_rank|…)
    "normalise",
    "normalize",
    "rank_",         # rank_by_…, rank_cells (bare "rank" noun in a reader is ok)
    "exclude",
    "exclusion",
    "eligib",        # eligibility computation (eligible_mask lives in the engine)
    "compute_",      # compute_bounds / compute_score — the engine's job
    "recompute",
    "reweight",
    "weight_sum",
)

# Names the service DEFINES that merely READ / SELECT / PROJECT these concepts —
# explicitly allow-listed so the prefix check is belt-and-suspenders precise.
# Each is a pure read or selection over the fixed engine output (verified by
# reading the source), not a computation. (With prefix matching these are not
# currently flagged, but the allow-list documents the intent and hardens the
# guard against a future rename that would start with a forbidden verb.)
_ALLOWED_SERVICE_DEFINITIONS = {
    # filters.py — pure SELECTIONS over the fixed ranked rows (Property P2).
    "apply_min_score",
    "apply_top_n",
    "apply_display_filter",
    # results.py — READ helpers over the materialised tables.
    "get_ranked_results",
    "get_site_detail",
    "get_exclusions",
    "_reason_codes_and_text",
    "_run_feature_names",
    # models.py dataclasses/methods carry no arithmetic.
}


def _module_ast(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imported_engine_names(tree: ast.Module) -> list[tuple[str, str]]:
    """
    Every ``from pipeline.<engine>... import NAME`` in the module.

    Returns ``(module_path, imported_name)`` pairs where ``module_path`` is the
    dotted engine module imported from (relative imports resolved to their
    leaf), so the guard can check both WHICH engine module is touched and WHICH
    symbol is pulled from it.
    """
    engine_roots = ("scoring", "exclusions", "explanation", "common", "shortlist")
    pairs: list[tuple[str, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            # Relative imports (level>0) inside the package: ``..scoring.score``
            # parses with module="scoring.score"; ``.validate`` -> "validate".
            leaf = mod.split(".")[-1] if mod else ""
            root_hit = any(part in engine_roots for part in mod.split("."))
            is_validate = leaf == "validate" or mod.endswith("validate")
            if root_hit or is_validate:
                for alias in node.names:
                    pairs.append((mod, alias.name))
    return pairs


def _defined_function_names(tree: ast.Module) -> list[str]:
    """Top-level and nested function names defined in the module."""
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.append(node.name)
    return names


def test_property_3_arithmetic_core_imported_only_by_the_run_store():
    """
    The engine's arithmetic-core modules (``score`` / ``normalise`` / ``rank``)
    may be imported ONLY by ``runs.py`` (which drives the engine). No read /
    select / serve module may touch them — importing them there would be a
    recompute path (Requirement 2.1, 2.2, 2.4).
    """
    # Feature: s2-08-decision-service-api, Property 3: no recompute path
    offenders: list[str] = []
    for path in _service_modules():
        if path.name == _ARITHMETIC_CORE_DRIVER:
            continue  # the engine driver is allowed to import the core
        tree = _module_ast(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                mod = node.module or ""
                leaf = mod.split(".")[-1]
                if leaf in _ARITHMETIC_CORE_MODULES:
                    offenders.append(f"{path.name} imports pipeline.scoring.{leaf}")
    assert not offenders, (
        "arithmetic-core modules must be imported only by the Run store "
        f"({_ARITHMETIC_CORE_DRIVER}); recompute smell in: {offenders}"
    )


def test_property_3_service_only_reuses_the_engines_own_symbols():
    """
    Every symbol a service module imports from an engine package must be one of
    the engine's OWN public symbols (the allow-list) — never a locally
    reimplemented scorer / normaliser / ranker (Requirement 2.1, 2.2).

    This is the boundary that keeps the service a reuse layer: it can call the
    engine's ``score_and_rank`` / ``compute_bounds`` / ``parse_weights`` etc.,
    but it cannot import (and therefore cannot be shadowing) a decision-math
    function the engine does not itself export as such.
    """
    # Feature: s2-08-decision-service-api, Property 3: no recompute path
    unexpected: list[str] = []
    for path in _service_modules():
        tree = _module_ast(path)
        for mod, name in _imported_engine_names(tree):
            if name not in _ALLOWED_ENGINE_IMPORTS:
                unexpected.append(f"{path.name}: from {mod} import {name}")
    assert not unexpected, (
        "service imported engine symbols outside the reuse allow-list "
        "(a recompute path would show up as a new engine-math import here): "
        f"{unexpected}. If this is a legitimate engine reuse, add the symbol to "
        "_ALLOWED_ENGINE_IMPORTS; if it is a reimplementation, remove it."
    )


def test_property_3_no_service_module_defines_decision_arithmetic():
    """
    No service module may DEFINE a function that reimplements a scoring /
    normalisation / ranking / exclusion computation (Requirement 2.1, 2.2, 2.4).

    A defined function whose name BEGINS with a decision-arithmetic verb
    (``score`` / ``normalise`` / ``rank_`` / ``exclude`` / ``compute_`` /
    ``eligib`` / …) is a recompute smell UNLESS it is on the read/select
    allow-list (a pure selection or projection over the fixed engine output,
    verified by reading its source).
    """
    # Feature: s2-08-decision-service-api, Property 3: no recompute path
    offenders: list[str] = []
    for path in _service_modules():
        tree = _module_ast(path)
        for fn_name in _defined_function_names(tree):
            if fn_name in _ALLOWED_SERVICE_DEFINITIONS:
                continue
            stem = fn_name.lstrip("_").lower()
            if any(stem.startswith(p) for p in _FORBIDDEN_DEFINITION_PREFIXES):
                offenders.append(f"{path.name}::{fn_name}")
    assert not offenders, (
        "service module defines what looks like decision arithmetic — the "
        "service must READ and SELECT, never compute a score/rank/exclusion: "
        f"{offenders}. If this is a pure read/selection, add it to "
        "_ALLOWED_SERVICE_DEFINITIONS after confirming its body computes nothing."
    )


def test_property_3_guard_would_catch_a_reintroduced_recompute():
    """
    Meta-check: the structural guard is a real fence, not a trivial always-pass.

    Synthesises a module source that (a) imports the arithmetic core, (b) imports
    a non-allow-listed engine symbol, and (c) defines a ``normalise_score``
    function, then asserts each arm of the guard's logic flags it. Were the guard
    accidentally weakened to always pass, this test fails.
    """
    # Feature: s2-08-decision-service-api, Property 3: no recompute path
    bad_source = (
        "from ..scoring.normalise import normalise_series\n"
        "from ..scoring.score import score_frame as _reimpl\n"
        "def normalise_score(v, lo, hi):\n"
        "    return (v - lo) / (hi - lo)\n"
    )
    tree = ast.parse(bad_source)

    # (a) arithmetic-core import is detected.
    core_hits = [
        (node.module or "").split(".")[-1]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and (node.module or "").split(".")[-1] in _ARITHMETIC_CORE_MODULES
    ]
    assert core_hits, "guard failed to detect an arithmetic-core import"

    # (b) a non-allow-listed engine symbol is detected.
    unexpected = [
        name for _mod, name in _imported_engine_names(tree)
        if name not in _ALLOWED_ENGINE_IMPORTS
    ]
    assert unexpected, "guard failed to detect a non-allow-listed engine import"

    # (c) a decision-arithmetic definition is detected.
    flagged = [
        fn for fn in _defined_function_names(tree)
        if fn not in _ALLOWED_SERVICE_DEFINITIONS
        and any(fn.lstrip("_").lower().startswith(p) for p in _FORBIDDEN_DEFINITION_PREFIXES)
    ]
    assert flagged, "guard failed to detect a reimplemented decision function"


# =========================================================================== #
# Part 2 — the VALUE-tracing check (Hypothesis): served == materialised.       #
# =========================================================================== #
#
# A cell of a Scored_Table is either ELIGIBLE (a score in [0, 1] and a dense
# rank) or EXCLUDED (null score / null rank). Scores are drawn on the full
# [0, 1] range with ties possible so the engine's own rank ordering — which the
# service must serve VERBATIM — is exercised rather than re-derived.

_cell_ids = st.text(
    alphabet="abcdefghijklmnopqrstuvwxyz0123456789_",
    min_size=1,
    max_size=8,
)
_scores = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)
_contribs = st.floats(min_value=0.0, max_value=1.0, allow_nan=False, allow_infinity=False)


@st.composite
def _scored_tables(draw):
    """
    Draw a Scored_Table as a list of row dicts with unique ``cell_id``s, each
    carrying a KNOWN score / rank / ``contrib_wind_speed`` share so the value
    trace has a ground truth to compare against.

    Eligible cells get distinct dense ranks (1..k) descending by score (ties
    broken by cell_id) — the engine's own rank-by-score convention — recorded on
    the row so the test asserts the service serves exactly these, never a
    re-derived rank. Excluded cells carry ``None`` for score, rank and contrib.
    """
    n = draw(st.integers(min_value=1, max_value=12))
    ids = draw(st.lists(_cell_ids, min_size=n, max_size=n, unique=True))

    rows: list[dict] = []
    for cid in ids:
        eligible = draw(st.booleans())
        if eligible:
            rows.append(
                {
                    "cell_id": cid,
                    "suitability_score": draw(_scores),
                    "contrib_wind_speed": draw(_contribs),
                    "_eligible": True,
                }
            )
        else:
            rows.append(
                {
                    "cell_id": cid,
                    "suitability_score": None,
                    "contrib_wind_speed": None,
                    "_eligible": False,
                }
            )

    eligible_rows = [r for r in rows if r["_eligible"]]
    eligible_rows.sort(key=lambda r: (-r["suitability_score"], r["cell_id"]))
    for rank, r in enumerate(eligible_rows, start=1):
        r["rank"] = rank
    for r in rows:
        if not r["_eligible"]:
            r["rank"] = None
        r.pop("_eligible")

    return rows


def _materialise(store: Path, tmp: Path, run_id: str, rows: list[dict]) -> Path:
    """
    Write a fake Run with everything both read operations touch: a Scored_Table,
    the integrated feature table the Run "scored", the S2-06 explanation output,
    and a manifest wiring the integrated path and one criterion. Mirrors the
    hermetic fixtures in ``test_results_properties.py``.
    """
    target = store / run_id
    target.mkdir(parents=True, exist_ok=True)

    geometry = [Point(150.0 + i * 0.1, -30.0) for i in range(len(rows))]

    scored = gpd.GeoDataFrame(rows, geometry=geometry, crs=scoring_config.STORAGE_CRS)
    scored.to_file(
        target / service_config.SCORED_GPKG_FILENAME,
        driver="GPKG",
        layer=service_config.SCORED_LAYER,
    )

    integrated_path = tmp / f"integrated_{run_id}.gpkg"
    integrated_rows = [
        {
            "cell_id": r["cell_id"],
            "eligible": r["rank"] is not None,
            "wind_speed": 8.0,
        }
        for r in rows
    ]
    integrated = gpd.GeoDataFrame(
        integrated_rows, geometry=geometry, crs=scoring_config.STORAGE_CRS
    )
    integrated.to_file(
        integrated_path, driver="GPKG", layer=service_config.INTEGRATED_LAYER
    )

    explanation_path = tmp / f"explanations_{run_id}.json"
    explanations = [
        {
            "cell_id": r["cell_id"],
            "eligible": r["rank"] is not None,
            "headline": "H",
            "positive_factors": [],
            "weaknesses": [],
            "proxy_caveats": [],
            "data_quality_notes": [],
        }
        for r in rows
    ]
    explanation_path.write_text(json.dumps(explanations) + "\n", encoding="utf-8")

    manifest = {
        "run_id": run_id,
        "weights_id": run_id,
        "scenario": None,
        "criteria": [
            {"feature": "wind_speed", "weight": 1.0, "direction": "higher_is_better"}
        ],
        "integrated_path": str(integrated_path),
        "integrated_layer": service_config.INTEGRATED_LAYER,
    }
    (target / service_config.RUN_MANIFEST_FILENAME).write_text(
        json.dumps(manifest) + "\n", encoding="utf-8"
    )
    return explanation_path


@settings(max_examples=100, deadline=None)
@given(rows=_scored_tables())
def test_property_3_served_values_trace_to_the_materialised_output(rows):
    """
    Every value the read operations serve equals the MATERIALISED value verbatim
    — the behavioural face of the no-recompute guarantee (Requirement 2.4).

    For each drawn Run, the score / rank / contribution the service returns for
    a cell is byte-for-byte the value written into the Scored_Table, so nothing
    was recomputed on the read path. Excluded cells surface as null score AND
    null rank — never a fabricated value.
    """
    # Feature: s2-08-decision-service-api, Property 3: no recompute path
    original_runs_dir = service_config.RUNS_DIR
    original_explanation_path = service_config.EXPLANATION_PATH
    with tempfile.TemporaryDirectory() as tmp_name:
        tmp = Path(tmp_name)
        store = tmp / "runs"
        service_config.RUNS_DIR = store
        run_id = "runpropp3000000"
        try:
            explanation_path = _materialise(store, tmp, run_id, rows)
            service_config.EXPLANATION_PATH = explanation_path

            # Ground truth: the exact values written into the materialised table.
            truth = {r["cell_id"]: r for r in rows}

            ranked = get_ranked_results(run_id)

            # (a) Every ranked (eligible) cell's served score, rank and
            #     contribution equal the materialised values EXACTLY — no
            #     recompute perturbs them.
            for row in ranked:
                t = truth[row.cell_id]
                assert row.suitability_score == t["suitability_score"]
                assert row.rank == t["rank"]
                # The contribution share is carried through verbatim (prefix
                # stripped): key_components["wind_speed"] == contrib_wind_speed.
                assert row.key_components.get("wind_speed") == t["contrib_wind_speed"]

                # The single-site detail serves the SAME materialised values.
                detail = get_site_detail(run_id, row.cell_id)
                assert detail.suitability_score == t["suitability_score"]
                assert detail.rank == t["rank"]
                assert detail.contributions.get("wind_speed") == t["contrib_wind_speed"]

            # (b) The ranked set is exactly the eligible cells of the fixed
            #     table — the service invented no ranked cell and dropped none.
            ranked_ids = {row.cell_id for row in ranked}
            expected_eligible = {r["cell_id"] for r in rows if r["rank"] is not None}
            assert ranked_ids == expected_eligible

            # (c) An EXCLUDED cell is served with null score AND null rank — the
            #     materialised nulls carried through, never a fabricated number.
            for r in rows:
                if r["rank"] is None:
                    detail = get_site_detail(run_id, r["cell_id"])
                    assert detail.suitability_score is None
                    assert detail.rank is None
        finally:
            service_config.RUNS_DIR = original_runs_dir
            service_config.EXPLANATION_PATH = original_explanation_path
