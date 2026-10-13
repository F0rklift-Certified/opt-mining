"""
S3-09 documentation-consistency test — screening language, demand-proxy framing
and the consolidated-doc links.

S3-09 adds a consolidated technical reference (``docs/technical-reference.md``), a
screening-level + consolidated-limitations block in ``pipeline/README.md``, and a
§4.11 subsection in the data specification, and links the new doc from both
``pipeline/README.md`` and ``app/README.md``. These are **documentation
surfaces** (fixed content, not universal properties), so — following the
example-assertion style of ``tests/backend/test_adr_and_run_commands_docs.py`` —
this test pins the acceptance-criteria guarantees so a future edit cannot
silently regress them:

* AC: a clean install/run path and technical documentation are provided — the
  consolidated doc exists and is linked from BOTH READMEs.
* AC12 / screening language: across the consolidated doc, the new
  ``pipeline/README.md`` screening block and the new data-spec §4.11 subsection,
  every "best site" / "best place" phrase is a NEGATION, and the screening-level
  framing ("preliminary screening" / "screening-level") is present.
* AC (demand proxy): each of those surfaces frames the demand layer as a PROXY
  (never measured / actual local demand).
* AC (consolidated docs): the consolidated doc links the Decision-Engine
  Specification and the integration / scoring / explanation ``DATA_PROVENANCE.md``
  files.

This test is unmarked, so CI's ``pytest -v -m "not integration" tests/backend``
step collects and runs it.

Validates: S3-09 AC11, AC12, the demand-proxy AC and the consolidated-doc AC.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest


def _collapse_ws(text: str) -> str:
    """Collapse all runs of whitespace to single spaces (line-wrap agnostic)."""
    return re.sub(r"\s+", " ", text)


def _section(text: str, start_marker: str, *, end_markers: tuple[str, ...]) -> str:
    """
    Return the slice of ``text`` from ``start_marker`` up to the first of
    ``end_markers`` that follows it. Used to isolate the specific block S3-09
    added to a shared document, so the assertions never scan unrelated prose
    elsewhere in the same file.
    """
    start = text.index(start_marker)
    rest = text[start:]
    ends = []
    for m in end_markers:
        idx = rest.find(m, len(start_marker))
        if idx != -1:
            ends.append(idx)
    cut = min(ends) if ends else len(rest)
    return rest[:cut]


def _assert_best_site_is_only_negated(block: str, where: str) -> None:
    """
    Assert every "best site" / "best place" occurrence in ``block`` is a
    negation (sits adjacent to "not"/"never"). Collapse whitespace first so the
    check is agnostic to Markdown line wrapping.
    """
    collapsed = _collapse_ws(block.lower())
    for phrase in ("best site", "best place"):
        start = 0
        while True:
            idx = collapsed.find(phrase, start)
            if idx == -1:
                break
            window = collapsed[max(0, idx - 60):idx]
            assert ("not" in window) or ("never" in window), (
                f"{where}: '{phrase}' appears without an adjacent negation "
                f"near: ...{collapsed[max(0, idx - 60):idx + 20]}..."
            )
            start = idx + len(phrase)


def _assert_demand_is_framed_as_proxy(block: str, where: str) -> None:
    """Assert ``block`` frames the demand layer as a proxy, never measured/actual."""
    collapsed = _collapse_ws(block.lower())
    assert "proxy" in collapsed, f"{where}: expected the demand layer called a proxy"
    assert ("never" in collapsed) or ("not" in collapsed), (
        f"{where}: expected a negation around the demand framing"
    )
    assert ("measured" in collapsed) or ("actual" in collapsed), (
        f"{where}: expected 'measured'/'actual' local demand to be negated"
    )


PROJECT_ROOT = Path(__file__).resolve().parents[2]

TECH_REF_PATH = PROJECT_ROOT / "docs" / "technical-reference.md"
PIPELINE_README_PATH = PROJECT_ROOT / "pipeline" / "README.md"
APP_README_PATH = PROJECT_ROOT / "app" / "README.md"
DATA_SPEC_PATH = (
    PROJECT_ROOT / "DATA" / "data-specification" / "sprint1_data_specification.md"
)


@pytest.fixture(scope="module")
def tech_ref_text() -> str:
    assert TECH_REF_PATH.exists(), f"consolidated doc is missing at {TECH_REF_PATH}"
    return TECH_REF_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def pipeline_readme_text() -> str:
    assert PIPELINE_README_PATH.exists(), f"missing {PIPELINE_README_PATH}"
    return PIPELINE_README_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def app_readme_text() -> str:
    assert APP_README_PATH.exists(), f"missing {APP_README_PATH}"
    return APP_README_PATH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def data_spec_text() -> str:
    assert DATA_SPEC_PATH.exists(), f"missing {DATA_SPEC_PATH}"
    return DATA_SPEC_PATH.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# AC11 — the consolidated doc exists and is linked from BOTH READMEs.          #
# --------------------------------------------------------------------------- #


def test_consolidated_doc_exists(tech_ref_text: str):
    assert tech_ref_text.strip(), "docs/technical-reference.md must have content"


def test_consolidated_doc_linked_from_pipeline_readme(pipeline_readme_text: str):
    assert "docs/technical-reference.md" in pipeline_readme_text


def test_consolidated_doc_linked_from_app_readme(app_readme_text: str):
    assert "docs/technical-reference.md" in app_readme_text


# --------------------------------------------------------------------------- #
# AC12 — screening-level language; no un-negated "best site"/"best place".     #
# --------------------------------------------------------------------------- #


def test_consolidated_doc_uses_screening_language(tech_ref_text: str):
    lowered = tech_ref_text.lower()
    assert ("preliminary screening" in lowered) or ("screening-level" in lowered)
    _assert_best_site_is_only_negated(tech_ref_text, "docs/technical-reference.md")


def test_pipeline_readme_screening_block_uses_screening_language(
    pipeline_readme_text: str,
):
    block = _section(
        pipeline_readme_text,
        "## Screening-level use & limitations",
        end_markers=("## Clean install", "## Architecture"),
    )
    lowered = block.lower()
    assert ("preliminary screening" in lowered) or ("screening-level" in lowered), (
        "the pipeline README screening block must state the screening-level use"
    )
    _assert_best_site_is_only_negated(block, "pipeline/README.md screening block")


def test_data_spec_s309_subsection_uses_screening_language(data_spec_text: str):
    block = _section(
        data_spec_text,
        "### 4.11 Screening-level use",
        end_markers=("## 5. CRS Alignment Strategy",),
    )
    lowered = block.lower()
    assert ("preliminary screening" in lowered) or ("screening-level" in lowered)
    _assert_best_site_is_only_negated(block, "data spec §4.11")


# --------------------------------------------------------------------------- #
# AC — the demand layer is framed as a proxy on each S3-09 surface.            #
# --------------------------------------------------------------------------- #


def test_consolidated_doc_frames_demand_as_proxy(tech_ref_text: str):
    _assert_demand_is_framed_as_proxy(tech_ref_text, "docs/technical-reference.md")


def test_pipeline_readme_screening_block_frames_demand_as_proxy(
    pipeline_readme_text: str,
):
    block = _section(
        pipeline_readme_text,
        "## Screening-level use & limitations",
        end_markers=("## Clean install", "## Architecture"),
    )
    _assert_demand_is_framed_as_proxy(block, "pipeline/README.md screening block")


def test_data_spec_s309_subsection_frames_demand_as_proxy(data_spec_text: str):
    block = _section(
        data_spec_text,
        "### 4.11 Screening-level use",
        end_markers=("## 5. CRS Alignment Strategy",),
    )
    _assert_demand_is_framed_as_proxy(block, "data spec §4.11")


# --------------------------------------------------------------------------- #
# AC — the consolidated doc links the authoritative sources.                   #
# --------------------------------------------------------------------------- #


def test_consolidated_doc_links_decision_engine_spec(tech_ref_text: str):
    assert "decision_engine_specification.md" in tech_ref_text


def test_consolidated_doc_links_key_provenance_files(tech_ref_text: str):
    for provenance in (
        "DATA/integration/DATA_PROVENANCE.md",
        "DATA/scoring/DATA_PROVENANCE.md",
        "DATA/explanation/DATA_PROVENANCE.md",
    ):
        assert provenance in tech_ref_text, f"consolidated doc must link {provenance}"


def test_consolidated_doc_links_demand_proxy_method(tech_ref_text: str):
    # The proxy framing must be traceable to its method report.
    assert "DATA/electricity-demand/demand_feature_method.md" in tech_ref_text


# --------------------------------------------------------------------------- #
# S3-10 widening — the new docs/release/*.md surfaces are held to the SAME     #
# screening-language and demand-proxy guard once they exist.                   #
#                                                                              #
# S3-10 (FEAT-003) adds release-package docs under docs/release/. They are      #
# subject to the identical AC12 framing: "preliminary screening"/"screening-   #
# level" present, every "best site"/"best place" negated, and the demand layer #
# framed as a proxy (never measured/actual). To keep this suite GREEN before   #
# FEAT-003 lands the docs — and to assert for real once they do — each release #
# doc that does NOT yet exist is SKIPPED with a clear reason rather than        #
# failing. The pre-existing assertions on the fixed S3-09 surfaces above stay   #
# intact and unconditional.                                                     #
# --------------------------------------------------------------------------- #

RELEASE_DIR = PROJECT_ROOT / "docs" / "release"

# The release docs that must pass the screening/proxy guard once authored. Each
# is a prose surface (README / limitations) that makes screening-level claims
# and references the demand proxy; the pure-JSON evidence files (readiness.json,
# rehearsal.json) and the command log (verification.md) are not prose-guarded
# here.
RELEASE_PROSE_DOCS = ("README.md", "limitations.md")


def _release_doc_text_or_skip(filename: str) -> str:
    """Return the release doc's text, or ``pytest.skip`` if it does not yet exist.

    Lets the suite stay green before FEAT-003 lands docs/release/*.md while
    asserting for real once a given doc is present.
    """
    path = RELEASE_DIR / filename
    if not path.exists():
        pytest.skip(
            f"docs/release/{filename} does not exist yet (authored by S3-10 "
            "FEAT-003); the release-doc guard applies once it lands"
        )
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("filename", RELEASE_PROSE_DOCS)
def test_release_doc_uses_screening_language(filename: str):
    text = _release_doc_text_or_skip(filename)
    lowered = text.lower()
    assert ("preliminary screening" in lowered) or ("screening-level" in lowered), (
        f"docs/release/{filename} must state the screening-level framing"
    )


@pytest.mark.parametrize("filename", RELEASE_PROSE_DOCS)
def test_release_doc_best_site_only_negated(filename: str):
    text = _release_doc_text_or_skip(filename)
    _assert_best_site_is_only_negated(text, f"docs/release/{filename}")


@pytest.mark.parametrize("filename", RELEASE_PROSE_DOCS)
def test_release_doc_frames_demand_as_proxy(filename: str):
    text = _release_doc_text_or_skip(filename)
    _assert_demand_is_framed_as_proxy(text, f"docs/release/{filename}")
