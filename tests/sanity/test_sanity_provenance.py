"""Unit tests for the S1-12 sanity-check provenance recorder.

Covers task 11.2 of the s1-12-validation-sanity-check spec — the content of the
three derived-product provenance artefacts written by
``pipeline.sanity.report.record_provenance`` (Requirements 10.1–10.4):

  - the ``DATA_PROVENANCE.md`` block labels the outputs a DERIVED PRODUCT and
    lists all FIVE READ-ONLY inputs (shortlist, scored_table,
    integrated_feature_table, wind_generators, analysis_grid) + the UTC
    Run_Timestamp (10.1, 10.2);
  - the ``sanity_manifest.json`` record carries the report SHA-256 + byte count
    + the Run_Timestamp + a record of the five inputs, labelled
    ``product_type: "derived"`` (10.1, 10.3);
  - a ``source_register`` row is added in the derived category (10.3);
  - ``config.SIDECAR_FILENAME`` follows the
    ``{source}_{dataset}_{year/vintage}_{region}.{ext}`` convention with region
    slug ``nsw`` (10.4);
  - a rerun REPLACES rather than appends — a single manifest record for the
    report and a single register row (10.3).

All artefacts are written under ``tmp_path`` via the explicit
``manifest_path`` / ``provenance_path`` / ``register_path`` overrides, and the
report / sidecar / five inputs are small REAL files on disk so
``sha256_file`` / ``Path.stat()`` operate on genuine bytes (never mocked).
This file creates a NEW test file and does not modify existing tests, per the
task note. Follows the conventions of ``tests/shortlist/test_shortlist_report.py``.
"""

import csv
import io
import json
import re

from pipeline.common.geo import sha256_file
from pipeline.sanity import config
from pipeline.sanity.report import (
    INPUT_NAMES,
    PROVENANCE_BEGIN,
    PROVENANCE_END,
    record_provenance,
)

FIXED_TS = "2026-01-15T00:00:00Z"
FIXED_VERSION = "test-pipeline-v1.2.3"

# The five READ-ONLY inputs, in the documented order.
EXPECTED_INPUT_NAMES = {
    "shortlist",
    "scored_table",
    "integrated_feature_table",
    "wind_generators",
    "analysis_grid",
}


def _write_bytes(path, payload):
    """Write real bytes so sha256_file / stat() operate on genuine content."""
    path.write_bytes(payload)
    return path


def _make_inputs(tmp_path):
    """Create small REAL files for the report, sidecar, and five inputs.

    Returns a dict of the paths ``record_provenance`` needs. Each file has
    distinct, non-empty bytes so the SHA-256 digests and byte counts differ.
    """
    report_path = _write_bytes(
        tmp_path / "sprint1_validation_report.md",
        b"# Sprint 1 Validation Report\n\nsynthetic report body\n",
    )
    sidecar_path = _write_bytes(
        tmp_path / config.SIDECAR_FILENAME,
        b'{"product_type": "derived", "synthetic": true}\n',
    )
    shortlist_path = _write_bytes(
        tmp_path / "sprint1_shortlist_2026-01-15.geojson",
        b"synthetic shortlist bytes \x01\x02\x03",
    )
    scored_path = _write_bytes(
        tmp_path / "scored.gpkg", b"synthetic scored bytes \x04\x05\x06"
    )
    integrated_path = _write_bytes(
        tmp_path / "integrated.gpkg", b"synthetic integrated bytes \x07\x08\x09"
    )
    wind_generators_path = _write_bytes(
        tmp_path / "wind_generators.geojson",
        b"synthetic wind generators bytes \x0a\x0b\x0c",
    )
    grid_path = _write_bytes(
        tmp_path / "grid.gpkg", b"synthetic grid bytes \x0d\x0e\x0f"
    )
    return {
        "report_path": report_path,
        "sidecar_path": sidecar_path,
        "shortlist_path": shortlist_path,
        "scored_path": scored_path,
        "integrated_path": integrated_path,
        "wind_generators_path": wind_generators_path,
        "grid_path": grid_path,
    }


def _record(tmp_path, inputs, *, sidecar=True):
    """Call record_provenance with all artefacts written under tmp_path."""
    return record_provenance(
        report_path=inputs["report_path"],
        sidecar_path=inputs["sidecar_path"] if sidecar else None,
        shortlist_path=inputs["shortlist_path"],
        scored_path=inputs["scored_path"],
        integrated_path=inputs["integrated_path"],
        wind_generators_path=inputs["wind_generators_path"],
        grid_path=inputs["grid_path"],
        run_timestamp=FIXED_TS,
        pipeline_version=FIXED_VERSION,
        manifest_path=tmp_path / config.MANIFEST_FILENAME,
        provenance_path=tmp_path / config.PROVENANCE_FILENAME,
        register_path=tmp_path / config.SOURCE_REGISTER_FILENAME,
        scored_layer=config.SCORED_LAYER,
        integrated_layer=config.INTEGRATED_LAYER,
        grid_layer=config.GRID_LAYER,
    )


# ===========================================================================
# sanity_manifest.json — sha256 + bytes + Run_Timestamp + the five inputs (10.1, 10.3)
# ===========================================================================


def test_manifest_labels_report_derived_with_digest_bytes_and_inputs(tmp_path):
    """The manifest record has sha256/bytes + Run_Timestamp + the five inputs,
    labelled ``product_type: "derived"`` (10.1, 10.3)."""
    inputs = _make_inputs(tmp_path)
    record = _record(tmp_path, inputs)

    manifest = json.loads((tmp_path / config.MANIFEST_FILENAME).read_text())
    assert len(manifest["derived_products"]) == 1
    entry = manifest["derived_products"][0]
    assert entry == record

    assert entry["stage"] == config.STAGE_NAME
    assert entry["product_type"] == "derived"
    assert entry["run_timestamp"] == FIXED_TS
    assert entry["pipeline_version"] == FIXED_VERSION

    # Report fingerprint matches the file on disk (sha256 + bytes — 10.1).
    assert entry["sha256_report"] == sha256_file(inputs["report_path"])
    assert entry["bytes_report"] == inputs["report_path"].stat().st_size
    assert len(entry["sha256_report"]) == 64
    assert entry["bytes_report"] > 0

    # The sidecar is fingerprinted alongside the report when written.
    assert entry["sha256_sidecar"] == sha256_file(inputs["sidecar_path"])
    assert entry["bytes_sidecar"] == inputs["sidecar_path"].stat().st_size


def test_manifest_records_all_five_inputs_with_digests(tmp_path):
    """The manifest generation params list ALL FIVE inputs, each with a path +
    sha256 + bytes matching the file on disk (10.1, 10.3)."""
    inputs = _make_inputs(tmp_path)
    record = _record(tmp_path, inputs)

    names = {i["name"] for i in record["inputs"]}
    assert names == EXPECTED_INPUT_NAMES
    assert set(INPUT_NAMES) == EXPECTED_INPUT_NAMES
    assert len(record["inputs"]) == 5

    by_name = {i["name"]: i for i in record["inputs"]}
    # Multi-layer inputs record the layer they were read from.
    assert by_name["scored_table"]["layer"] == config.SCORED_LAYER
    assert by_name["integrated_feature_table"]["layer"] == config.INTEGRATED_LAYER
    assert by_name["analysis_grid"]["layer"] == config.GRID_LAYER

    # Digests + byte counts match the real files.
    path_by_key = {
        "shortlist": inputs["shortlist_path"],
        "scored_table": inputs["scored_path"],
        "integrated_feature_table": inputs["integrated_path"],
        "wind_generators": inputs["wind_generators_path"],
        "analysis_grid": inputs["grid_path"],
    }
    for name, path in path_by_key.items():
        assert by_name[name]["sha256"] == sha256_file(path)
        assert by_name[name]["bytes"] == path.stat().st_size
    assert all(len(i["sha256"]) == 64 for i in record["inputs"])
    assert all(i["bytes"] > 0 for i in record["inputs"])


# ===========================================================================
# DATA_PROVENANCE.md — derived-product row lists five inputs + Run_Timestamp (10.1, 10.2)
# ===========================================================================


def test_data_provenance_labels_derived_and_lists_all_inputs_and_timestamp(tmp_path):
    """DATA_PROVENANCE.md marks the outputs a DERIVED product and lists all five
    input names + the UTC Run_Timestamp inside one BEGIN/END block, preserving
    any handwritten header (10.1, 10.2)."""
    inputs = _make_inputs(tmp_path)
    provenance_path = tmp_path / config.PROVENANCE_FILENAME
    provenance_path.write_text("# Handwritten header\n\nKeep me.\n", encoding="utf-8")

    record = _record(tmp_path, inputs)
    text = provenance_path.read_text()

    # Handwritten content above the generated block is preserved.
    assert text.startswith("# Handwritten header")
    assert "Keep me." in text
    # Exactly one generated block.
    assert text.count(PROVENANCE_BEGIN) == 1
    assert text.count(PROVENANCE_END) == 1

    # Explicitly a derived product (10.2).
    assert "DERIVED PRODUCT" in text

    # All FIVE input names are listed (10.1).
    for name in EXPECTED_INPUT_NAMES:
        assert name in text, f"missing input name in DATA_PROVENANCE.md: {name!r}"
    # Each input's project-relative path appears too.
    for i in record["inputs"]:
        assert i["path"] in text

    # The UTC Run_Timestamp is present (10.1).
    assert FIXED_TS in text
    # The report and sidecar digests are recorded.
    assert record["sha256_report"] in text
    assert record["sha256_sidecar"] in text


def test_data_provenance_records_sidecar_naming_convention(tmp_path):
    """When a sidecar is written the block records it under the nsw naming
    convention; when it is not, the block says so (10.2, 10.4)."""
    inputs = _make_inputs(tmp_path)

    # With a sidecar: the block names the sidecar file + the convention slug.
    _record(tmp_path, inputs, sidecar=True)
    text = (tmp_path / config.PROVENANCE_FILENAME).read_text()
    assert config.SIDECAR_FILENAME in text
    assert config.REGION_SLUG in text

    # Without a sidecar: the block records it was not written for the run.
    (tmp_path / "no_sidecar_run").mkdir(exist_ok=True)
    inputs2 = _make_inputs(tmp_path / "no_sidecar_run")
    record = record_provenance(
        report_path=inputs2["report_path"],
        sidecar_path=None,
        shortlist_path=inputs2["shortlist_path"],
        scored_path=inputs2["scored_path"],
        integrated_path=inputs2["integrated_path"],
        wind_generators_path=inputs2["wind_generators_path"],
        grid_path=inputs2["grid_path"],
        run_timestamp=FIXED_TS,
        manifest_path=tmp_path / "no_sidecar_run" / config.MANIFEST_FILENAME,
        provenance_path=tmp_path / "no_sidecar_run" / config.PROVENANCE_FILENAME,
        register_path=tmp_path / "no_sidecar_run" / config.SOURCE_REGISTER_FILENAME,
    )
    assert record["sidecar_file"] is None
    text2 = (tmp_path / "no_sidecar_run" / config.PROVENANCE_FILENAME).read_text()
    assert "not written" in text2.lower()


# ===========================================================================
# source_register — a derived-category row is added (10.3)
# ===========================================================================


def test_source_register_row_is_derived_category(tmp_path):
    """The source_register carries one row for the validation report in the
    derived category, naming it a derived product and listing the five inputs
    (10.3)."""
    inputs = _make_inputs(tmp_path)
    _record(tmp_path, inputs)

    register_path = tmp_path / config.SOURCE_REGISTER_FILENAME
    rows = list(csv.DictReader(io.StringIO(register_path.read_text())))
    assert len(rows) == 1
    row = rows[0]
    assert row["dataset_id"] == "optmining_validation_report"
    assert row["category"] == "derived-validation"
    assert "DERIVED" in row["custodian"]
    # The notes column enumerates the five inputs.
    for name in EXPECTED_INPUT_NAMES:
        assert name in row["notes"]


# ===========================================================================
# Sidecar naming convention (10.4)
# ===========================================================================


def test_sidecar_filename_matches_nsw_convention(tmp_path):
    """``config.SIDECAR_FILENAME`` follows the
    ``{source}_{dataset}_{year/vintage}_{region}.{ext}`` convention with region
    slug ``nsw`` (10.4)."""
    # The exact documented name.
    assert config.SIDECAR_FILENAME == "optmining_validation-results_2026_nsw.json"

    # It also matches the general {source}_{dataset}_{year}_{region}.{ext}
    # pattern with region slug nsw and a 4-digit vintage.
    pattern = re.compile(
        r"^(?P<source>[a-z0-9]+)_(?P<dataset>[a-z0-9-]+)_"
        r"(?P<year>\d{4})_(?P<region>nsw)\.(?P<ext>[a-z0-9]+)$"
    )
    m = pattern.match(config.SIDECAR_FILENAME)
    assert m is not None, f"sidecar name off-convention: {config.SIDECAR_FILENAME}"
    assert m.group("region") == config.REGION_SLUG == "nsw"
    assert m.group("year") == config.SIDECAR_VINTAGE == "2026"
    assert m.group("ext") == "json"


# ===========================================================================
# Rerun replaces rather than appends (10.3)
# ===========================================================================


def test_rerun_replaces_rather_than_appends(tmp_path):
    """Rerunning is idempotent by key: the manifest keeps a SINGLE record for the
    report and the source_register a SINGLE row rather than appending duplicates
    (10.3)."""
    inputs = _make_inputs(tmp_path)

    record = None
    for _ in range(2):
        record = _record(tmp_path, inputs)

    manifest = json.loads((tmp_path / config.MANIFEST_FILENAME).read_text())
    assert len(manifest["derived_products"]) == 1
    assert manifest["derived_products"][0] == record

    register_path = tmp_path / config.SOURCE_REGISTER_FILENAME
    rows = list(csv.DictReader(io.StringIO(register_path.read_text())))
    assert len(rows) == 1

    provenance_path = tmp_path / config.PROVENANCE_FILENAME
    text = provenance_path.read_text()
    assert text.count(PROVENANCE_BEGIN) == 1
    assert text.count(PROVENANCE_END) == 1
