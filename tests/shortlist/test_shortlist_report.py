"""
Unit tests for the S1-11 shortlist report, metadata sidecar, and provenance
content (task 10.5).

These are example-based unit tests over ``tmp_path`` with synthetic inputs; the
universal invariants (disclaimer/resolution presence, Run_Timestamp reuse) are
covered by the property tests P14/P15. They exercise the three
metadata-carrying artefacts written by ``pipeline.shortlist.report``:

  * the Summary_Report (``write_summary_report``) — banner-stamped, recording
    the effective Top_N + eligible/included counts (2.5), the geometry choice
    (5.4), each optional-context column's definition/source (4.3), and the
    name-collision outcome (7.4), and stamped with the do-not-edit banner
    (11.4);
  * the metadata sidecar (``write_metadata_sidecar``) — recording
    ``pipeline_version`` and UTC ``run_timestamp`` (9.1), ``effective_top_n`` /
    ``n_shortlisted`` (9.2), and the ``scored_table_id`` (path + sha256, 9.3),
    with Pipeline_Version + Run_Timestamp recorded identically to the report
    (9.4);
  * provenance (``record_provenance``) — a ``shortlist_manifest.json`` record
    labelled ``product_type: "derived"`` with sha256/bytes + generation params,
    a ``DATA_PROVENANCE.md`` derived-product block listing both inputs + Top_N +
    Run_Timestamp, and a ``source_register.csv`` row in the derived category,
    all idempotent by key on rerun (11.1, 11.3).

Conventions follow ``tests/test_shortlist_writers.py`` (tmp_path, synthetic
frames) and ``tests/test_integration_table.py::TestProvenance`` (manifest /
DATA_PROVENANCE idempotency assertions).
"""

from __future__ import annotations

import csv
import io
import json

import pytest

from pipeline.common.geo import banner, sha256_file
from pipeline.shortlist import config
from pipeline.shortlist.assemble import OptionalContextColumn
from pipeline.shortlist.naming import CollisionOutcome
from pipeline.shortlist.report import (
    PROVENANCE_BEGIN,
    PROVENANCE_END,
    record_provenance,
    write_metadata_sidecar,
    write_summary_report,
)
from pipeline.shortlist.summary import SummaryStats

# Fixed run identity, so the tests are deterministic regardless of wall clock.
FIXED_TS = "2026-03-14T09:30:15+00:00"
FIXED_VERSION = "abc1234-dirty"
EFFECTIVE_TOP_N = 20
N_SHORTLISTED = 3


def _stats() -> SummaryStats:
    """A synthetic SummaryStats with distinct eligible / scored / total counts."""
    return SummaryStats(
        score_dist={"min": 0.10, "max": 0.90, "mean": 0.50, "std": 0.30},
        lat_range=(-31.0, -30.0),
        lon_range=(151.0, 152.0),
        rez_represented=["New England"],
        confidence_dist={"high": 2, "low": 1},
        n_cells=47311,
        n_eligible=12345,
        n_scored=20000,
    )


def _optional_context() -> tuple[OptionalContextColumn, ...]:
    return (
        OptionalContextColumn(
            name="rez",
            definition="Renewable Energy Zone the cell lies within.",
            source="AEMO ISP REZ boundaries (S1-04).",
        ),
        OptionalContextColumn(
            name="nearby_wind_farm",
            definition="Whether an operating wind farm lies within the cell.",
            source="GA operating-generators layer (S1-05).",
        ),
    )


def _collision(occurred: bool) -> CollisionOutcome:
    if occurred:
        return CollisionOutcome(
            occurred=True,
            base_stem="sprint1_shortlist_20260314",
            resolved_stem="sprint1_shortlist_20260314T093015",
            precision="second",
        )
    return CollisionOutcome(
        occurred=False,
        base_stem="sprint1_shortlist_20260314",
        resolved_stem="sprint1_shortlist_20260314",
        precision="date",
    )


def _write_scored_file(tmp_path):
    """A small stand-in Scored_Table file so ``sha256_file`` has real bytes."""
    scored = tmp_path / "scored_input.gpkg"
    scored.write_bytes(b"synthetic scored table bytes \x00\x01\x02")
    return scored


def _write_outputs(tmp_path):
    """Synthetic CSV + GeoJSON output files to fingerprint in the manifest."""
    csv_path = tmp_path / "sprint1_shortlist_20260314.csv"
    geojson_path = tmp_path / "sprint1_shortlist_20260314.geojson"
    csv_path.write_text("rank,cell_id\n1,C0001\n")
    geojson_path.write_text('{"type": "FeatureCollection", "features": []}\n')
    return csv_path, geojson_path


# ---------------------------------------------------------------------------
# Summary_Report content (Requirements 2.5, 4.3, 5.4, 7.4, 11.4)
# ---------------------------------------------------------------------------


class TestSummaryReport:
    def _report(self, tmp_path, *, collision):
        path = tmp_path / config.SUMMARY_REPORT_FILENAME
        write_summary_report(
            path,
            stats=_stats(),
            effective_top_n=EFFECTIVE_TOP_N,
            n_shortlisted=N_SHORTLISTED,
            geometry="centroid",
            optional_context=_optional_context(),
            collision=collision,
            pipeline_version=FIXED_VERSION,
            run_timestamp=FIXED_TS,
        )
        return path.read_text()

    def test_report_is_banner_stamped(self, tmp_path):
        """
        The report carries the do-not-edit banner for the shortlist stage,
        matching ``common.geo.banner("shortlist")`` (11.4).

        The banner embeds a live timestamp, so compare on its stable prefix and
        trailer rather than the whole string.
        """
        report = self._report(tmp_path, collision=_collision(False))

        stamp = banner(config.STAGE_NAME)
        prefix, _, trailer = stamp.partition("on ")
        assert prefix in report  # "*Generated by `pipeline.shortlist` "
        assert "Do not edit by hand.*" in report
        assert config.STAGE_NAME == "shortlist"
        assert trailer  # sanity: the banner shape is unchanged

    def test_records_effective_top_n_and_eligible_vs_included(self, tmp_path):
        """Effective Top_N and the eligible-vs-included counts are recorded (2.5)."""
        report = self._report(tmp_path, collision=_collision(False))

        assert f"**Effective Top_N:** {EFFECTIVE_TOP_N}" in report
        # Eligible (candidate) count and the included count, thousands-formatted.
        assert "12,345" in report  # n_eligible
        assert f"**Included in shortlist:** {N_SHORTLISTED:,}" in report
        # Included count is distinct from the eligible count (clamped, not padded).
        assert str(N_SHORTLISTED) in report

    def test_records_geometry_choice(self, tmp_path):
        """The GeoJSON geometry choice is stated for the reviewer (5.4)."""
        report = self._report(tmp_path, collision=_collision(False))
        assert "centroid" in report
        assert "EPSG:4326" in report

    def test_records_each_optional_context_definition_and_source(self, tmp_path):
        """Each optional-context column's definition and source is documented (4.3)."""
        report = self._report(tmp_path, collision=_collision(False))
        for col in _optional_context():
            assert f"`{col.name}`" in report
            assert col.definition in report
            assert col.source in report

    def test_records_collision_outcome_when_occurred(self, tmp_path):
        """When a collision occurred the finer-grained UTC outcome is recorded (7.4)."""
        collision = _collision(True)
        report = self._report(tmp_path, collision=collision)

        assert "collision" in report.lower()
        assert collision.base_stem in report
        assert collision.resolved_stem in report
        assert collision.precision in report

    def test_records_no_collision_when_none_occurred(self, tmp_path):
        """With no collision the report says so rather than omitting the section (7.4)."""
        report = self._report(tmp_path, collision=_collision(False))
        assert "none" in report.lower()


# ---------------------------------------------------------------------------
# Metadata sidecar content (Requirements 9.1, 9.3, 9.4 + 5.4, 9.2)
# ---------------------------------------------------------------------------


class TestMetadataSidecar:
    def _sidecar(self, tmp_path):
        scored = _write_scored_file(tmp_path)
        path = tmp_path / config.METADATA_SIDECAR_FILENAME
        write_metadata_sidecar(
            path,
            scored_path=scored,
            effective_top_n=EFFECTIVE_TOP_N,
            n_shortlisted=N_SHORTLISTED,
            geometry="centroid",
            pipeline_version=FIXED_VERSION,
            run_timestamp=FIXED_TS,
        )
        return scored, json.loads(path.read_text())

    def test_records_pipeline_version_and_utc_run_timestamp(self, tmp_path):
        """The sidecar records pipeline_version and the UTC run_timestamp (9.1)."""
        _, record = self._sidecar(tmp_path)
        assert record["pipeline_version"] == FIXED_VERSION
        assert record["run_timestamp"] == FIXED_TS
        assert record["run_timestamp"].endswith("+00:00")  # UTC

    def test_records_effective_top_n_and_n_shortlisted(self, tmp_path):
        """The sidecar records effective_top_n and n_shortlisted (9.2)."""
        _, record = self._sidecar(tmp_path)
        assert record["effective_top_n"] == EFFECTIVE_TOP_N
        assert record["n_shortlisted"] == N_SHORTLISTED

    def test_scored_table_id_digest_matches_sha256_file(self, tmp_path):
        """
        The scored_table_id carries the Scored_Table path + its correct SHA-256,
        equal to ``common.geo.sha256_file`` of the scored file (9.3).
        """
        scored, record = self._sidecar(tmp_path)
        table_id = record["scored_table_id"]
        assert set(table_id) == {"path", "sha256"}
        assert table_id["sha256"] == sha256_file(scored)
        assert len(table_id["sha256"]) == 64
        # The path names the scored file that was fingerprinted.
        assert scored.name in table_id["path"]

    def test_records_geometry_choice(self, tmp_path):
        """The sidecar records the GeoJSON geometry choice (5.4)."""
        _, record = self._sidecar(tmp_path)
        assert record["geometry"] == "centroid"

    def test_version_and_timestamp_match_report(self, tmp_path):
        """
        Pipeline_Version + Run_Timestamp are recorded identically in the sidecar
        and the Summary_Report for one run, so the two artefacts never disagree
        (9.4).
        """
        scored, record = self._sidecar(tmp_path)

        report_path = tmp_path / config.SUMMARY_REPORT_FILENAME
        write_summary_report(
            report_path,
            stats=_stats(),
            effective_top_n=EFFECTIVE_TOP_N,
            n_shortlisted=N_SHORTLISTED,
            geometry="centroid",
            optional_context=_optional_context(),
            collision=_collision(False),
            pipeline_version=FIXED_VERSION,
            run_timestamp=FIXED_TS,
        )
        report = report_path.read_text()

        # The exact values threaded into the sidecar also appear in the report.
        assert record["pipeline_version"] == FIXED_VERSION
        assert record["run_timestamp"] == FIXED_TS
        assert FIXED_VERSION in report
        assert FIXED_TS in report


# ---------------------------------------------------------------------------
# Provenance: manifest, DATA_PROVENANCE.md, source_register (11.1, 11.3)
# ---------------------------------------------------------------------------


class TestProvenance:
    def _record(self, tmp_path, *, scored, grid, csv_path, geojson_path):
        return record_provenance(
            csv_path=csv_path,
            geojson_path=geojson_path,
            scored_path=scored,
            grid_path=grid,
            effective_top_n=EFFECTIVE_TOP_N,
            n_shortlisted=N_SHORTLISTED,
            run_timestamp=FIXED_TS,
            pipeline_version=FIXED_VERSION,
            manifest_path=tmp_path / config.MANIFEST_FILENAME,
            provenance_path=tmp_path / config.PROVENANCE_FILENAME,
            register_path=tmp_path / config.SOURCE_REGISTER_FILENAME,
            scored_layer=config.SCORED_LAYER,
            grid_layer=config.GRID_LAYER,
        )

    def _inputs(self, tmp_path):
        scored = _write_scored_file(tmp_path)
        grid = tmp_path / "grid_input.gpkg"
        grid.write_bytes(b"synthetic grid bytes \x03\x04\x05")
        csv_path, geojson_path = _write_outputs(tmp_path)
        return scored, grid, csv_path, geojson_path

    def test_manifest_labels_outputs_derived_with_params_and_digests(self, tmp_path):
        """
        The manifest record labels the outputs ``derived`` and carries the
        sha256/bytes of each output plus the generation params — the two inputs
        (path + layer + sha256 + bytes) and the effective Top_N (11.1, 11.3).
        """
        scored, grid, csv_path, geojson_path = self._inputs(tmp_path)
        record = self._record(
            tmp_path, scored=scored, grid=grid, csv_path=csv_path, geojson_path=geojson_path
        )

        manifest = json.loads((tmp_path / config.MANIFEST_FILENAME).read_text())
        assert len(manifest["derived_features"]) == 1
        entry = manifest["derived_features"][0]
        assert entry == record

        assert entry["stage"] == config.STAGE_NAME
        assert entry["product_type"] == "derived"
        assert entry["effective_top_n"] == EFFECTIVE_TOP_N
        assert entry["n_shortlisted"] == N_SHORTLISTED
        assert entry["run_timestamp"] == FIXED_TS
        assert entry["pipeline_version"] == FIXED_VERSION

        # Output fingerprints match the files on disk.
        assert entry["sha256_csv"] == sha256_file(csv_path)
        assert entry["sha256_geojson"] == sha256_file(geojson_path)
        assert entry["bytes_csv"] == csv_path.stat().st_size
        assert entry["bytes_geojson"] == geojson_path.stat().st_size

        # Both inputs recorded as generation params with layer + sha256 + bytes.
        names = {i["name"] for i in entry["inputs"]}
        assert names == {"scored_table", "analysis_grid"}
        by_name = {i["name"]: i for i in entry["inputs"]}
        assert by_name["scored_table"]["layer"] == config.SCORED_LAYER
        assert by_name["analysis_grid"]["layer"] == config.GRID_LAYER
        assert by_name["scored_table"]["sha256"] == sha256_file(scored)
        assert by_name["analysis_grid"]["sha256"] == sha256_file(grid)
        assert all(len(i["sha256"]) == 64 for i in entry["inputs"])
        assert all(i["bytes"] > 0 for i in entry["inputs"])

    def test_data_provenance_labels_derived_product_with_inputs_and_params(self, tmp_path):
        """
        DATA_PROVENANCE.md calls the outputs a derived product and lists both
        inputs + the effective Top_N + the UTC Run_Timestamp, inside one
        BEGIN/END block, preserving any handwritten header (11.1, 11.2, 11.3).
        """
        scored, grid, csv_path, geojson_path = self._inputs(tmp_path)
        provenance_path = tmp_path / config.PROVENANCE_FILENAME
        provenance_path.write_text("# Handwritten header\n\nKeep me.\n", encoding="utf-8")

        record = self._record(
            tmp_path, scored=scored, grid=grid, csv_path=csv_path, geojson_path=geojson_path
        )
        text = provenance_path.read_text()

        # Handwritten content above the generated block is preserved.
        assert text.startswith("# Handwritten header")
        assert "Keep me." in text
        # Exactly one generated block.
        assert text.count(PROVENANCE_BEGIN) == 1
        assert text.count(PROVENANCE_END) == 1

        # Explicitly labelled a derived product.
        assert "DERIVED PRODUCT" in text
        # Both inputs listed.
        assert record["inputs"][0]["path"] in text
        assert record["inputs"][1]["path"] in text
        assert "scored_table" in text
        assert "analysis_grid" in text
        # Effective Top_N and UTC Run_Timestamp present.
        assert str(EFFECTIVE_TOP_N) in text
        assert FIXED_TS in text
        # Output digests present.
        assert record["sha256_csv"] in text

    def test_source_register_row_is_derived_category(self, tmp_path):
        """
        The source_register carries one row for the shortlist in the derived
        category, naming it a derived product (11.3).
        """
        scored, grid, csv_path, geojson_path = self._inputs(tmp_path)
        self._record(
            tmp_path, scored=scored, grid=grid, csv_path=csv_path, geojson_path=geojson_path
        )

        register_path = tmp_path / config.SOURCE_REGISTER_FILENAME
        rows = list(csv.DictReader(io.StringIO(register_path.read_text())))
        assert len(rows) == 1
        row = rows[0]
        assert row["dataset_id"] == "optmining_shortlist"
        assert row["category"] == "derived-shortlist"
        assert "DERIVED" in row["custodian"]
        assert str(EFFECTIVE_TOP_N) in row["size_or_count"]

    def test_rerun_replaces_rather_than_appends(self, tmp_path):
        """
        Rerunning is idempotent by key: the manifest keeps a single derived
        record and the source_register a single row rather than appending
        duplicates (11.1, 11.3).
        """
        scored, grid, csv_path, geojson_path = self._inputs(tmp_path)

        for _ in range(2):
            record = self._record(
                tmp_path, scored=scored, grid=grid, csv_path=csv_path, geojson_path=geojson_path
            )

        manifest = json.loads((tmp_path / config.MANIFEST_FILENAME).read_text())
        assert len(manifest["derived_features"]) == 1
        assert manifest["derived_features"][0] == record

        register_path = tmp_path / config.SOURCE_REGISTER_FILENAME
        rows = list(csv.DictReader(io.StringIO(register_path.read_text())))
        assert len(rows) == 1

        provenance_path = tmp_path / config.PROVENANCE_FILENAME
        text = provenance_path.read_text()
        assert text.count(PROVENANCE_BEGIN) == 1
        assert text.count(PROVENANCE_END) == 1
