"""
Full-NSW-grid integration tests for the S1-10 scoring stage.

These run against the real generated products under `DATA/`, so they are
skipped when those products are absent (a fresh clone, or a checkout where
the pipeline has not been run). They verify the properties that only show up
at full scale: one row per cell across all 47,311 cells, agreement with the
S1-07 eligibility flag, and byte-identical regeneration.
"""

from __future__ import annotations

import pandas as pd
import pytest

from pipeline.scoring import config as scfg

pytestmark = pytest.mark.skipif(
    not (scfg.SCORING_DIR / scfg.CSV_FILENAME).exists()
    or not scfg.INTEGRATED_PATH.exists(),
    reason="scored table or integrated table not generated in this checkout",
)


@pytest.fixture(scope="module")
def scored() -> pd.DataFrame:
    return pd.read_csv(scfg.SCORING_DIR / scfg.CSV_FILENAME)


@pytest.fixture(scope="module")
def integrated() -> pd.DataFrame:
    path = scfg.INTEGRATED_PATH.with_suffix(".csv")
    return pd.read_csv(path, usecols=["cell_id", "eligible", "data_confidence"])


class TestFullGrid:
    def test_one_row_per_grid_cell(self, scored, integrated):
        assert len(scored) == len(integrated)
        assert not scored["cell_id"].duplicated().any()
        assert set(scored["cell_id"]) == set(integrated["cell_id"])

    def test_scored_cells_match_the_eligibility_flag(self, scored, integrated):
        merged = scored[["cell_id", "suitability_score"]].merge(
            integrated, on="cell_id", validate="one_to_one"
        )
        eligible = merged["eligible"].astype(bool)
        has_score = merged["suitability_score"].notna()
        assert (eligible == has_score).all()

    def test_scores_lie_in_the_unit_interval(self, scored):
        values = scored["suitability_score"].dropna()
        assert len(values) > 0
        assert values.between(0.0, 1.0).all()

    def test_rank_is_contiguous_over_scored_cells(self, scored):
        ranked = scored["rank"].dropna().astype(int)
        n_scored = int(scored["suitability_score"].notna().sum())
        assert sorted(ranked) == list(range(1, n_scored + 1))

    def test_contributions_reconcile_for_every_scored_cell(self, scored):
        columns = [c for c in scored.columns if c.startswith(scfg.CONTRIBUTION_PREFIX)]
        assert columns
        rows = scored[scored["suitability_score"].notna()]
        residual = (rows[columns].sum(axis=1) - rows["suitability_score"]).abs()
        assert residual.max() <= scfg.RECONCILE_TOLERANCE

    def test_confidence_is_carried_through_unchanged(self, scored, integrated):
        merged = scored[["cell_id", "confidence"]].merge(
            integrated, on="cell_id", validate="one_to_one"
        )
        assert (merged["confidence"] == merged["data_confidence"]).all()
        assert merged["confidence"].isin(list(scfg.CONFIDENCE_LEVELS)).all()

    def test_excluded_cells_carry_no_score_rank_or_contributions(self, scored, integrated):
        merged = scored.merge(integrated, on="cell_id", validate="one_to_one")
        excluded = merged[~merged["eligible"].astype(bool)]
        assert excluded["suitability_score"].isna().all()
        assert excluded["rank"].isna().all()
        for column in [c for c in scored.columns
                       if c.startswith(scfg.CONTRIBUTION_PREFIX)]:
            assert excluded[column].isna().all()

    def test_method_report_and_provenance_exist(self):
        meta = scfg.SCORING_META_DIR
        assert (meta / scfg.METHOD_REPORT_FILENAME).exists()
        assert (meta / scfg.VALIDATION_REPORT_FILENAME).exists()
        assert (meta / scfg.MANIFEST_FILENAME).exists()
        assert (scfg.SCORING_DIR / scfg.PROVENANCE_FILENAME).exists()

    def test_method_report_records_the_required_content(self):
        """
        Requirement 13 — the report is the document a reviewer reads, so its
        content is asserted rather than assumed.
        """
        text = (scfg.SCORING_META_DIR / scfg.METHOD_REPORT_FILENAME).read_text(
            encoding="utf-8"
        )
        assert "Do not edit by hand" in text  # banner (12.4)
        for fragment in (
            "Scoring formula",
            "Criteria, weights and rationale",
            "Normalisation bounds applied on this run",
            "contributions",
            "Confidence",
            "What was scored",
            "Deviations from the S1-10 ticket",
        ):
            assert fragment in text, fragment
        assert "LINEAR" in text  # 13.5 — the normalisation form is stated

    def test_provenance_labels_the_table_a_derived_product(self):
        text = (scfg.SCORING_DIR / scfg.PROVENANCE_FILENAME).read_text(encoding="utf-8")
        assert "DERIVED PRODUCT" in text
        assert "weights" in text.lower()

    def test_regeneration_is_byte_identical(self, tmp_path):
        """
        Requirement 6.9 — the scored table is a fully regenerable derived
        product. The CSV is the deterministic artefact (a GeoPackage's hash
        drifts with its internal last_change timestamp).
        """
        from pipeline.scoring.run import run

        csv_path = scfg.SCORING_DIR / scfg.CSV_FILENAME
        before = csv_path.read_bytes()
        run()
        assert csv_path.read_bytes() == before


class TestValidateAgainstReality:
    """
    Constitution: "Validate against reality. Check that known successful wind
    development areas score highly, using public operational and existing wind
    farm data."

    S1-12 formalises this. The check here is a cheap regression guard: if a
    change to the scoring logic ever pushes the two operating New England wind
    farms out of the top quartile of scored cells, that is a signal to
    investigate the model before shipping. The threshold is deliberately loose
    — this asserts the model is not obviously wrong, not that it is calibrated.
    """

    def test_operating_wind_farms_score_in_the_top_quartile(self):
        import geopandas as gpd
        from shapely.geometry import Point

        from pipeline.wind import config as wind_config

        farms_path = wind_config.WIND_REF_DIR / "nsw_wind_farms_new_england.csv"
        if not farms_path.exists():
            pytest.skip("wind farm reference data not present in this checkout")

        farms = pd.read_csv(farms_path)
        operating = farms[farms["status"].str.lower() == "operational"]
        if operating.empty:
            pytest.skip("no operational wind farms in the reference data")

        scored = gpd.read_file(
            scfg.SCORING_DIR / scfg.OUTPUT_FILENAME, layer=scfg.OUTPUT_LAYER
        )
        n_scored = int(scored[scfg.SCORE_COLUMN].notna().sum())
        assert n_scored > 0

        points = gpd.GeoDataFrame(
            operating,
            geometry=[Point(x, y) for x, y in
                      zip(operating["longitude"], operating["latitude"])],
            crs=scfg.STORAGE_CRS,
        )
        joined = gpd.sjoin(points, scored, how="left", predicate="within")

        for _, row in joined.iterrows():
            name = row["name"]
            assert pd.notna(row[scfg.SCORE_COLUMN]), (
                f"{name} sits in a cell with no score — an operating wind farm "
                f"should not land on land the model treats as ineligible"
            )
            percentile = (row[scfg.RANK_COLUMN] - 1) / n_scored
            assert percentile <= 0.25, (
                f"{name} ranks at the {percentile:.1%} mark of scored cells; a "
                f"known successful development area should score highly"
            )
