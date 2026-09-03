"""
Full-NSW-grid-scale integration test for the S1-11 shortlist stage (task 15.1).

Where ``tests/test_shortlist_run.py`` exercises the ``run()`` contract over
small synthetic inputs, this module drives ONE realistic, grid-scale end-to-end
run of ``pipeline.shortlist.run.run`` and ties together every downstream
concern in a single exercise: selection, the coordinate join, the CSV/GeoJSON
formatting, the Summary_Report + metadata sidecar, provenance, and the
no-silent-passes validation.

A LARGE synthetic Scored_Table GeoPackage and a matching Analysis_Grid
GeoPackage are built under ``tmp_path`` to emulate the full NSW analysis grid
(47,311 cells) at a size that still runs in a few seconds. The Scored_Table
carries a realistic mix of Eligible_Cells (non-null ``suitability_score`` AND
non-null ``rank``, with contiguous ranks ``1..N_eligible``) and Excluded_Cells
(null score AND null rank). The grid covers EVERY scored ``cell_id`` so the
coordinate join succeeds.

The stage's output directories (``config.SHORTLIST_DIR`` /
``config.SHORTLIST_META_DIR``) are monkeypatched to ``tmp_path`` subdirs, so no
real ``DATA/`` is ever written — same convention as
``tests/test_shortlist_run.py``.

End-to-end assertions (all against a single well-formed run):
  * the returned counts — ``n_eligible`` == eligible cells, ``n_shortlisted``
    == ``min(top_n, n_eligible)``, ``effective_top_n`` == ``top_n``;
  * the CSV and GeoJSON both exist, carry the same ``cell_id`` sequence
    element-for-element, every row has non-null ``centroid_lat``/
    ``centroid_lon``, and the shortlist is ordered by ascending ``rank`` from 1;
  * every shortlisted ``cell_id`` is in the scored table AND the grid, and the
    joined coordinates equal the grid's values for those cell_ids;
  * the GeoJSON carries the ``preliminary_disclaimer`` + ``analysis_resolution``
    file-level members, and the Summary_Report and metadata sidecar carry them;
  * provenance is recorded — the manifest, ``DATA_PROVENANCE.md`` and
    ``source_register.csv`` all exist, label the outputs derived, and the
    sidecar's ``scored_table_id`` sha256 equals ``common.geo.sha256_file`` of
    the scored file;
  * ``run()`` emits the validation report and reports 0 failures for this
    well-formed run.

A second parametrised case drives ``top_n`` ABOVE the eligible count to confirm
every eligible cell is shortlisted with no padding.
"""

from __future__ import annotations

import json
from pathlib import Path

import geopandas as gpd
import pytest
from shapely.geometry import Point

from pipeline.common.geo import sha256_file
from pipeline.shortlist import config
from pipeline.shortlist.run import run

# ---------------------------------------------------------------------------
# Grid-scale synthetic inputs
# ---------------------------------------------------------------------------

# A size that represents "grid scale" (thousands of cells) while still running
# in a few seconds — the real NSW grid is 47,311 cells.
N_CELLS = 4_000
# A realistic ~25% of the cells are Excluded_Cells (null score AND null rank);
# the remaining ~75% are contiguously ranked Eligible_Cells.
EXCLUDED_EVERY = 4


def _cell_id(i: int) -> str:
    """Deterministic, stable cell_id for index ``i`` (byte-for-byte reused)."""
    return f"C{i:06d}"


def _lat(i: int) -> float:
    """Deterministic centroid latitude for index ``i`` (inside NSW-ish bounds)."""
    return round(-37.0 + (i % 200) * 0.05, 6)


def _lon(i: int) -> float:
    """Deterministic centroid longitude for index ``i`` (inside NSW-ish bounds)."""
    return round(141.0 + (i // 200) * 0.05, 6)


def _grid_scale_frames(n: int = N_CELLS):
    """
    Build a grid-scale Scored_Table frame and a matching Analysis_Grid frame.

    Scored_Table: cell_id, suitability_score, rank, confidence + Point geometry
    (EPSG:4326). Eligible_Cells (index not divisible by ``EXCLUDED_EVERY``)
    carry a non-null score and a CONTIGUOUS rank ``1..N_eligible`` assigned in
    descending-score order; Excluded_Cells carry null score AND null rank.

    Analysis_Grid: cell_id, centroid_lat, centroid_lon + Point geometry
    (EPSG:4326), one row for EVERY scored cell_id so the join always succeeds.

    Returns ``(scored_gdf, grid_gdf, n_eligible)``.
    """
    cell_ids, scores, confidences, geoms = [], [], [], []
    grid_lats, grid_lons, grid_geoms = [], [], []
    eligible_indices = []

    for i in range(n):
        cid = _cell_id(i)
        lat, lon = _lat(i), _lon(i)
        cell_ids.append(cid)
        geoms.append(Point(lon, lat))
        grid_lats.append(lat)
        grid_lons.append(lon)
        grid_geoms.append(Point(lon, lat))

        if i % EXCLUDED_EVERY == 0:
            # Excluded_Cell: null score AND null rank.
            scores.append(None)
            confidences.append(None)
        else:
            # Eligible_Cell: a non-null, monotone-with-index score so ranks are
            # deterministic; confidence alternates high/low.
            scores.append(round(0.999 - i * 1e-5, 6))
            confidences.append("high" if i % 2 else "low")
            eligible_indices.append(i)

    n_eligible = len(eligible_indices)

    # Assign contiguous ranks 1..N_eligible by DESCENDING score (highest score
    # gets rank 1). Since score decreases with index, ascending index == best
    # score first, so ranks follow index order among eligible cells.
    ranks = [None] * n
    for rank, i in enumerate(sorted(eligible_indices, key=lambda k: -scores[k]), start=1):
        ranks[i] = rank

    scored = gpd.GeoDataFrame(
        {
            "cell_id": cell_ids,
            "suitability_score": scores,
            "rank": ranks,
            "confidence": confidences,
        },
        geometry=geoms,
        crs="EPSG:4326",
    )
    grid = gpd.GeoDataFrame(
        {
            "cell_id": cell_ids,
            "centroid_lat": grid_lats,
            "centroid_lon": grid_lons,
        },
        geometry=grid_geoms,
        crs="EPSG:4326",
    )
    return scored, grid, n_eligible


def _write_inputs(tmp_path: Path, scored: gpd.GeoDataFrame, grid: gpd.GeoDataFrame):
    """Write the two synthetic frames to GeoPackages with the stage's layers."""
    scored_path = tmp_path / "scored.gpkg"
    grid_path = tmp_path / "grid.gpkg"
    scored.to_file(scored_path, driver="GPKG", layer=config.SCORED_LAYER)
    grid.to_file(grid_path, driver="GPKG", layer=config.GRID_LAYER)
    return scored_path, grid_path


def _redirect_output_dirs(tmp_path: Path, monkeypatch):
    """Point the stage's output dirs at tmp_path subdirs (no real DATA/ write)."""
    out_dir = tmp_path / "out"
    meta_dir = out_dir / "metadata"
    monkeypatch.setattr(config, "SHORTLIST_DIR", out_dir)
    monkeypatch.setattr(config, "SHORTLIST_META_DIR", meta_dir)
    return out_dir, meta_dir


# ---------------------------------------------------------------------------
# CSV / GeoJSON readers
# ---------------------------------------------------------------------------


def _csv_rows(csv_path: Path) -> list[dict]:
    """Parse a Shortlist_CSV into a list of ordered {column: value} dicts."""
    lines = csv_path.read_text().splitlines()
    header = lines[0].split(",")
    return [dict(zip(header, line.split(","))) for line in lines[1:]]


def _geojson(geojson_path: Path) -> dict:
    return json.loads(geojson_path.read_text())


# ---------------------------------------------------------------------------
# The grid-scale end-to-end run
# ---------------------------------------------------------------------------

# Two geometry choices are covered; "centroid" is the primary (default) case.
@pytest.mark.parametrize("geometry", ["centroid", "polygon"])
def test_full_grid_scale_run_end_to_end(tmp_path, monkeypatch, geometry):
    out_dir, meta_dir = _redirect_output_dirs(tmp_path, monkeypatch)
    scored, grid, n_eligible = _grid_scale_frames()
    scored_path, grid_path = _write_inputs(tmp_path, scored, grid)

    top_n = 250  # comfortably below the eligible population
    result = run(
        top_n=top_n,
        scored_path=scored_path,
        grid_path=grid_path,
        geometry=geometry,
    )

    # --- returned counts ---------------------------------------------------
    assert result["n_eligible"] == n_eligible
    assert result["n_shortlisted"] == min(top_n, n_eligible)
    assert result["effective_top_n"] == top_n
    assert result["n_scored"] == n_eligible  # scored == eligible in this input
    assert result["n_cells"] == N_CELLS
    assert result["geometry"] == geometry

    # --- both headline outputs exist --------------------------------------
    csv_path = Path(result["shortlist_csv_path"])
    geojson_path = Path(result["shortlist_geojson_path"])
    assert csv_path.exists()
    assert geojson_path.exists()

    csv_rows = _csv_rows(csv_path)
    collection = _geojson(geojson_path)
    features = collection["features"]

    assert len(csv_rows) == min(top_n, n_eligible)
    assert len(features) == min(top_n, n_eligible)

    # --- CSV and GeoJSON agree on the cell_id sequence, element-for-element -
    csv_ids = [row["cell_id"] for row in csv_rows]
    geojson_ids = [str(f["properties"]["cell_id"]) for f in features]
    assert csv_ids == geojson_ids

    # --- ordering is ascending rank starting at 1 -------------------------
    # rank is serialised as a float (the source column is float-typed because
    # Excluded_Cells carry null ranks), so parse via float before comparing.
    csv_ranks = [int(float(row["rank"])) for row in csv_rows]
    assert csv_ranks == list(range(1, len(csv_ranks) + 1))

    # --- every row has non-null coordinates, joined from the grid ---------
    grid_lat = dict(zip(grid["cell_id"], grid["centroid_lat"]))
    grid_lon = dict(zip(grid["cell_id"], grid["centroid_lon"]))
    scored_ids = set(scored["cell_id"])
    grid_ids = set(grid["cell_id"])

    for row in csv_rows:
        cid = row["cell_id"]
        # present in BOTH scored table and grid
        assert cid in scored_ids
        assert cid in grid_ids
        # non-null coordinates
        assert row["centroid_lat"] not in ("", "None")
        assert row["centroid_lon"] not in ("", "None")
        # coordinates equal the grid's values for that cell_id
        assert float(row["centroid_lat"]) == pytest.approx(grid_lat[cid])
        assert float(row["centroid_lon"]) == pytest.approx(grid_lon[cid])

    # --- disclaimer + resolution carried in the GeoJSON, report, sidecar ---
    assert collection["preliminary_disclaimer"] == config.PRELIMINARY_DISCLAIMER
    assert collection["analysis_resolution"] == config.ANALYSIS_RESOLUTION

    report_text = Path(result["summary_report_path"]).read_text()
    assert config.PRELIMINARY_DISCLAIMER in report_text
    assert config.ANALYSIS_RESOLUTION in report_text

    sidecar = json.loads(Path(result["metadata_sidecar_path"]).read_text())
    assert sidecar["preliminary_disclaimer"] == config.PRELIMINARY_DISCLAIMER
    assert sidecar["analysis_resolution"] == config.ANALYSIS_RESOLUTION

    # --- provenance recorded ----------------------------------------------
    manifest_path = meta_dir / config.MANIFEST_FILENAME
    provenance_path = out_dir / config.PROVENANCE_FILENAME
    register_path = meta_dir / config.SOURCE_REGISTER_FILENAME
    assert manifest_path.exists()
    assert provenance_path.exists()
    assert register_path.exists()

    # The outputs are labelled DERIVED in the manifest and DATA_PROVENANCE.md.
    manifest = json.loads(manifest_path.read_text())
    derived = manifest["derived_features"]
    assert len(derived) == 1
    assert derived[0]["product_type"] == "derived"
    assert derived[0]["effective_top_n"] == top_n
    provenance_text = provenance_path.read_text()
    assert "DERIVED PRODUCT" in provenance_text
    register_text = register_path.read_text()
    assert "derived" in register_text.lower()

    # --- sidecar scored_table_id sha256 == sha256_file of the scored file --
    assert sidecar["scored_table_id"]["sha256"] == sha256_file(scored_path)

    # --- validation report emitted, 0 failures for this well-formed run ----
    validation_path = Path(result["validation_report_path"])
    assert validation_path.exists()
    assert result["validation"]["failed"] == 0
    assert result["validation"]["failed_names"] == []

    # runtime is recorded
    assert result["runtime_seconds"] >= 0.0


# ---------------------------------------------------------------------------
# Top_N exceeding the eligible count: clamp, no padding
# ---------------------------------------------------------------------------


def test_top_n_exceeding_eligible_count_shortlists_all_without_padding(tmp_path, monkeypatch):
    _redirect_output_dirs(tmp_path, monkeypatch)
    scored, grid, n_eligible = _grid_scale_frames()
    scored_path, grid_path = _write_inputs(tmp_path, scored, grid)

    # A Top_N comfortably ABOVE the eligible population.
    top_n = n_eligible + 500
    result = run(top_n=top_n, scored_path=scored_path, grid_path=grid_path)

    # Every eligible cell is included, clamped to the eligible count, no padding.
    assert result["effective_top_n"] == top_n
    assert result["n_eligible"] == n_eligible
    assert result["n_shortlisted"] == n_eligible

    csv_rows = _csv_rows(Path(result["shortlist_csv_path"]))
    assert len(csv_rows) == n_eligible
    # Contiguous ranks 1..n_eligible — nothing fabricated or padded.
    assert [int(float(r["rank"])) for r in csv_rows] == list(range(1, n_eligible + 1))
    # Still a clean validation.
    assert result["validation"]["failed"] == 0
