"""
Full-NSW-grid integration test for the S1-12 sanity stage (task 15.1).

Unlike the synthetic-input tests in ``tests/sanity/test_sanity_run.py``, this
module runs ``pipeline.sanity.run.run`` over the REAL Sprint 1 outputs — the
per-cell Scored_Table (S1-10), the latest timestamped Shortlist (S1-11), the
Integrated_Feature_Table (S1-08), the Geoscience Australia Wind_Generators, and
the Analysis_Grid — resolved from the ``pipeline.sanity.config`` default paths.

The Scored_Table (S1-10) and the Shortlist (S1-11) are produced by SIBLING
specs that may not yet be present on this branch, so the whole class SKIPS
gracefully when any of the five real inputs is absent (mirroring the opt-in
``TestRealDataIntegration`` class in
``tests/integration/test_integration_table.py``, which skips on missing real
DATA files). When the inputs DO exist the test redirects every FIXED sanity
output location under ``tmp_path`` (monkeypatching the ``config`` module
attributes ``REPORT_PATH`` / ``SIDECAR_PATH`` / ``SANITY_DIR`` /
``SANITY_META_DIR``) so the committed ``outputs/`` report and ``DATA/sanity/``
provenance are never rewritten by a test run.

It asserts, over the real 47,311-cell grid:
  * the Validation_Report is written to the (redirected) report path with all
    SIX numbered sections (Requirements 1.1, 9.2);
  * the Known_Wind_Farm_Comparison table has one row per wind generator
    (Requirement 2.5);
  * the Upper_Quartile count and the distribution statistics are recorded with
    an explicit PASS/FAIL (Requirements 2.5, 5.1);
  * NO input file is modified — SHA-256 of all five inputs is unchanged
    pre/post (Requirement 8.1);
  * a second run reproduces the automated structured results — the stage is a
    deterministic derived product (Requirement 12.3).

Requirements: 1.1, 2.5, 5.1, 8.1, 9.2, 12.3
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from pipeline.sanity import config

# The five READ-ONLY inputs, keyed the way the loader/run resolve them. The
# Shortlist is a directory (a timestamped file is resolved from it); the other
# four are concrete file paths.
_REAL_INPUT_PATHS: dict[str, Path] = {
    "Scored_Table": config.SCORED_PATH,
    "Shortlist_dir": config.SHORTLIST_DIR,
    "Integrated_Feature_Table": config.INTEGRATED_PATH,
    "Wind_Generators": config.WIND_GENERATORS_PATH,
    "Analysis_Grid": config.GRID_PATH,
}

# The six numbered section headers the report must contain, in order
# (report.py ``render_report`` / ``_render_*``).
_REQUIRED_SECTION_HEADERS = (
    "## 1. Known Wind Farm Comparison",
    "## 2. Exclusion Validation",
    "## 3. Feature Value Spot-Checks",
    "## 4. Score Distribution",
    "## 5. Issues for Sprint 2",
    "## 6. Conclusion",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _missing_real_inputs() -> list[str]:
    """Names of any of the five real inputs that are absent.

    The Shortlist entry is a DIRECTORY; it counts as present only when it exists
    AND holds at least one resolvable ``sprint1_shortlist_*`` file, so a run
    would not later halt in ``resolve_shortlist``.
    """
    missing: list[str] = []
    for name, path in _REAL_INPUT_PATHS.items():
        if name == "Shortlist_dir":
            if not (
                path.exists()
                and any(path.glob(f"{config.SHORTLIST_OUTPUT_PREFIX}_*"))
            ):
                missing.append(name)
        elif not path.exists():
            missing.append(name)
    return missing


# Collection-time guard: skip the whole module unless all five real inputs are
# present (S1-10 / S1-11 are sibling specs and may not exist on this branch).
_MISSING = _missing_real_inputs()

pytestmark = pytest.mark.skipif(
    bool(_MISSING),
    reason=(
        "real Sprint 1 inputs not present (S1-10 Scored_Table / S1-11 Shortlist "
        f"are sibling specs): missing {_MISSING}"
    ),
)


@pytest.fixture
def redirect_outputs(tmp_path, monkeypatch):
    """Point every FIXED sanity output location under ``tmp_path``.

    ``run.py`` / ``report.py`` read ``config.REPORT_PATH`` / ``SIDECAR_PATH`` /
    ``SANITY_DIR`` / ``SANITY_META_DIR`` as ``config.<ATTR>`` at call time, so
    patching the ``config`` module attributes redirects every write here and the
    committed ``outputs/sprint1_validation_report.md`` and ``DATA/sanity/``
    provenance are never touched. Mirrors the redirect fixture in
    ``tests/sanity/test_sanity_run.py``.
    """
    out_dir = tmp_path / "outputs"
    sanity_dir = tmp_path / "DATA" / "sanity"
    meta_dir = sanity_dir / "metadata"
    report_path = out_dir / "sprint1_validation_report.md"
    sidecar_path = sanity_dir / config.SIDECAR_FILENAME

    monkeypatch.setattr(config, "REPORT_PATH", report_path)
    monkeypatch.setattr(config, "SIDECAR_PATH", sidecar_path)
    monkeypatch.setattr(config, "SANITY_DIR", sanity_dir)
    monkeypatch.setattr(config, "SANITY_META_DIR", meta_dir)
    return {
        "out_dir": out_dir,
        "sanity_dir": sanity_dir,
        "meta_dir": meta_dir,
        "report_path": report_path,
        "sidecar_path": sidecar_path,
    }


def _resolved_input_paths() -> list[Path]:
    """The five concrete files a run reads, with the Shortlist directory
    resolved to the single timestamped file the run will actually open."""
    from pipeline.sanity.load import resolve_shortlist

    resolved_shortlist = resolve_shortlist(config.SHORTLIST_DIR)
    return [
        config.SCORED_PATH,
        config.INTEGRATED_PATH,
        config.WIND_GENERATORS_PATH,
        config.GRID_PATH,
        resolved_shortlist,
    ]


def _n_wind_generators() -> int:
    """The number of Wind_Generators features — the expected row count of the
    Known_Wind_Farm_Comparison table (one row per generator)."""
    gpd = pytest.importorskip("geopandas")
    return int(len(gpd.read_file(config.WIND_GENERATORS_PATH)))


class TestFullNswGridIntegration:
    """Run the sanity stage over the real 47,311-cell Sprint 1 outputs."""

    def test_report_written_with_all_six_sections(self, redirect_outputs):
        """The report is written to the (redirected) report path and contains
        all six numbered sections (Requirements 1.1, 9.2)."""
        result = run_sanity(redirect_outputs)

        report_path = Path(result["report_path"])
        assert report_path == redirect_outputs["report_path"]
        assert report_path.exists()

        text = report_path.read_text(encoding="utf-8")
        for header in _REQUIRED_SECTION_HEADERS:
            assert header in text, f"missing report section: {header!r}"

        # The report is the banner-stamped derived product, not a stray file.
        assert "Do not edit" in text or "do not edit" in text.lower()

    def test_known_wind_farm_table_has_one_row_per_generator(self, redirect_outputs):
        """The Known_Wind_Farm_Comparison table has exactly one row per wind
        generator (Requirement 2.5)."""
        result = run_sanity(redirect_outputs)

        expected_rows = _n_wind_generators()
        # The run summary counts one located farm row per generator.
        assert result["n_known_farms"] == expected_rows

        # And the rendered Markdown table carries that many data rows. Parse the
        # "## 1." section's table body: rows after the header + separator.
        text = Path(result["report_path"]).read_text(encoding="utf-8")
        section = _slice_section(text, "## 1. Known Wind Farm Comparison")
        data_rows = _markdown_table_data_rows(section)
        assert len(data_rows) == expected_rows

        # The machine-readable sidecar table agrees, one entry per generator.
        import json

        sidecar = json.loads(Path(result["sidecar_path"]).read_text(encoding="utf-8"))
        table = sidecar["checks"]["known_wind_farm_comparison"]["table"]
        assert len(table) == expected_rows

    def test_upper_quartile_and_distribution_recorded_with_pass_fail(self, redirect_outputs):
        """The Upper_Quartile count and the distribution statistics are recorded
        with an explicit PASS/FAIL (Requirements 2.5, 5.1)."""
        result = run_sanity(redirect_outputs)
        text = Path(result["report_path"]).read_text(encoding="utf-8")

        # Check 1 — Upper_Quartile count recorded with an explicit PASS/FAIL.
        assert isinstance(result["n_farms_upper_quartile"], int)
        assert 0 <= result["n_farms_upper_quartile"] <= result["n_known_farms"]
        assert isinstance(result["check1_pass"], bool)
        wind_section = _slice_section(text, "## 1. Known Wind Farm Comparison")
        assert "Upper_Quartile" in wind_section
        assert "PASS" in wind_section or "FAIL" in wind_section

        # Check 4 — distribution statistics recorded, with the clustering and
        # correlation outcomes reported as explicit PASS/FAIL (5.1).
        dist_section = _slice_section(text, "## 4. Score Distribution")
        for stat in ("min", "Q1", "median", "mean", "Q3", "max", "std"):
            assert f"| {stat} |" in dist_section, f"missing distribution stat: {stat}"
        assert "PASS" in dist_section or "FAIL" in dist_section
        assert isinstance(result["check4_pass"], bool)

        # The sidecar records the same statistics as structured values.
        import json

        sidecar = json.loads(Path(result["sidecar_path"]).read_text(encoding="utf-8"))
        stats = sidecar["checks"]["score_distribution"]["stats"]
        for stat in ("min", "max", "mean", "std", "q1", "median", "q3"):
            assert stat in stats

    def test_no_input_file_is_modified(self, redirect_outputs):
        """No input file is modified: SHA-256 of all five inputs is unchanged
        pre/post run (Requirement 8.1)."""
        input_paths = _resolved_input_paths()
        before = {p: _sha256(p) for p in input_paths}

        run_sanity(redirect_outputs)

        after = {p: _sha256(p) for p in input_paths}
        assert before == after, "run() mutated a read-only input"

    def test_second_run_reproduces_automated_results(self, redirect_outputs):
        """A second run reproduces the automated structured results — the stage
        is a deterministic derived product (Requirement 12.3)."""
        first = _deterministic_view(run_sanity(redirect_outputs))
        second = _deterministic_view(run_sanity(redirect_outputs))
        assert first == second


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run_sanity(redirect_outputs) -> dict:
    """Run the sanity stage over the real inputs with the sidecar enabled.

    Inputs are the ``config`` default paths (the real Sprint 1 outputs); only
    the OUTPUT locations are redirected (by the fixture) under ``tmp_path``.
    """
    from pipeline.sanity.run import run

    return run(write_sidecar=True)


def _deterministic_view(result: dict) -> dict:
    """Drop the wall-clock-dependent keys so two runs over fixed inputs compare
    equal on the automated structured results only."""
    volatile = {"runtime_seconds", "run_timestamp", "pipeline_version"}
    return {k: v for k, v in result.items() if k not in volatile}


def _slice_section(text: str, header: str) -> str:
    """Return the text of the ``## `` section starting at ``header`` up to the
    next ``## `` header (or end of document)."""
    start = text.index(header)
    rest = text[start + len(header):]
    m = re.search(r"\n## ", rest)
    end = len(rest) if m is None else m.start()
    return header + rest[:end]


def _markdown_table_data_rows(section: str) -> list[str]:
    """Extract the DATA rows of the first Markdown table in ``section``.

    A table row is a line starting with ``|``; the header row and the
    ``|---|`` separator row are excluded, leaving one line per data row.
    """
    table_lines = [
        ln.strip() for ln in section.splitlines() if ln.strip().startswith("|")
    ]
    data_rows = [
        ln
        for ln in table_lines
        if not re.fullmatch(r"\|[\s:|-]+\|", ln)  # drop the |---|---| separator
    ]
    # Drop the header row (the first remaining row).
    return data_rows[1:] if data_rows else []
