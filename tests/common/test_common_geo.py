"""
Unit tests for pipeline.common.geo utilities.
"""

import json
import tempfile
from pathlib import Path

import pytest

from pipeline.common.geo import (
    atomic_write_text, atomic_write_json, banner, human_bytes, sha256_file, utc_now,
)


class TestHumanBytes:
    """human_bytes formats byte counts correctly."""

    def test_bytes(self):
        assert human_bytes(0) == "0.0 B"
        assert human_bytes(512) == "512.0 B"

    def test_kilobytes(self):
        assert human_bytes(1_000) == "1.0 KB"
        assert human_bytes(1_500) == "1.5 KB"

    def test_megabytes(self):
        assert human_bytes(1_000_000) == "1.0 MB"
        assert human_bytes(2_500_000) == "2.5 MB"

    def test_gigabytes(self):
        assert human_bytes(1_000_000_000) == "1.0 GB"
        assert human_bytes(600_000_000) == "600.0 MB"


class TestAtomicWriteText:
    """atomic_write_text writes safely."""

    def test_creates_file(self, tmp_path):
        path = tmp_path / "test.txt"
        atomic_write_text(path, "hello world")
        assert path.read_text() == "hello world"

    def test_creates_parent_dirs(self, tmp_path):
        path = tmp_path / "sub" / "dir" / "file.txt"
        atomic_write_text(path, "nested")
        assert path.read_text() == "nested"

    def test_overwrites_existing(self, tmp_path):
        path = tmp_path / "test.txt"
        path.write_text("old")
        atomic_write_text(path, "new")
        assert path.read_text() == "new"

    def test_no_tmp_left_behind(self, tmp_path):
        path = tmp_path / "test.txt"
        atomic_write_text(path, "content")
        # No .tmp files should remain
        tmp_files = list(tmp_path.glob("*.tmp"))
        assert tmp_files == []


class TestAtomicWriteJson:
    """atomic_write_json writes valid JSON."""

    def test_writes_json(self, tmp_path):
        path = tmp_path / "data.json"
        atomic_write_json(path, {"key": "value", "count": 42})
        data = json.loads(path.read_text())
        assert data == {"key": "value", "count": 42}

    def test_pretty_printed(self, tmp_path):
        path = tmp_path / "data.json"
        atomic_write_json(path, {"a": 1})
        text = path.read_text()
        assert "  " in text  # 2-space indent
        assert text.endswith("\n")


class TestBanner:
    """banner generates a markdown do-not-edit notice."""

    def test_contains_module_name(self):
        result = banner("wind.probe")
        assert "pipeline.wind.probe" in result

    def test_contains_timestamp(self):
        result = banner("test")
        # Should contain a date-like string
        assert "202" in result  # year prefix

    def test_contains_warning(self):
        result = banner("test")
        assert "Do not edit by hand" in result


class TestUtcNow:
    """utc_now returns an ISO timestamp."""

    def test_format(self):
        ts = utc_now()
        assert "T" in ts
        assert "+" in ts or "Z" in ts or ts.endswith("+00:00")


class TestSha256File:
    """sha256_file hashes a file's bytes (chunked, so large files are safe)."""

    def test_known_digest(self, tmp_path):
        path = tmp_path / "abc.bin"
        path.write_bytes(b"abc")
        assert sha256_file(path) == (
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
        )

    def test_matches_hashlib_over_chunk_boundary(self, tmp_path):
        import hashlib
        data = bytes(range(256)) * 8194  # ~2 MiB: spans the 1 MiB read chunks
        path = tmp_path / "big.bin"
        path.write_bytes(data)
        assert sha256_file(path) == hashlib.sha256(data).hexdigest()

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            sha256_file(tmp_path / "missing.bin")
