/**
 * Render tests for the S3-08 sanity-check / validation panel.
 *
 * The panel is a pure view over `GET /sanity-check`: it must show the
 * model-not-trained caveat on EVERY state (incl. a passing result), render the
 * lineage line (or "lineage metadata unavailable"), an explicit PASS/FAIL badge
 * per check, the wind-farm table with the band-N column header, and the FULL
 * contradictions list — all verbatim, with no decision arithmetic.
 */
import { render, screen, within } from "@testing-library/react";

import type { SanityCheck } from "../api/decision-service";
import SanityCheckPanel from "./SanityCheckPanel";

const PASSING_SANITY: SanityCheck = {
  caveat:
    "The model is not trained to reproduce the known wind/REZ locations; overlap is corroboration, not a target.",
  preliminary_disclaimer: "Screening-level result — not a siting decision.",
  run_metadata: {
    run_timestamp: "2026-10-12T09:30:00Z",
    pipeline_version: "1.4.2",
    resolved_shortlist_path: "DATA/shortlist/optmining_shortlist_2026_nsw.csv",
    n_cells: 1000,
    n_eligible: 420,
  },
  checks: [
    {
      name: "Known-wind-farm top-ranked band",
      expected: "≥ 50% of farms in band",
      observed: "60% in band",
      passed: true,
    },
    {
      name: "REZ representation among top cells",
      expected: "≥ 30% inside a REZ",
      observed: "10% inside a REZ",
      passed: false,
    },
  ],
  contradictions: [
    {
      check: "Known wind farm comparison",
      description: "Sapphire wind farm fell on excluded land.",
      kind: "data_issue",
      investigation_note: "Protected-area overlap flagged for Sprint-2 review.",
    },
  ],
  wind_farms: [
    {
      wind_farm: "Sapphire",
      cell_id: "S30.100_E151.200",
      score: 0.812,
      rank: 3,
      percentile: 0.98,
      in_upper_quartile: true,
      in_top_band: true,
      notes: "",
    },
  ],
  top_band_n: 20,
  exclusion_assertions: [],
};

describe("SanityCheckPanel", () => {
  it("shows the loading state", () => {
    render(<SanityCheckPanel sanity={null} error={null} loading isBaselineRun />);
    expect(screen.getByRole("status")).toHaveTextContent(
      "Loading the sanity-check / validation result…",
    );
  });

  it("shows an error state like DataQualityBanner", () => {
    render(
      <SanityCheckPanel
        sanity={null}
        error="sidecar missing"
        loading={false}
        isBaselineRun
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Sanity-check result is unavailable. sidecar missing",
    );
  });

  it("renders the caveat even on a passing result", () => {
    const passing: SanityCheck = {
      ...PASSING_SANITY,
      checks: [
        {
          name: "Known-wind-farm top-ranked band",
          expected: "≥ 50% of farms in band",
          observed: "60% in band",
          passed: true,
        },
      ],
      contradictions: [],
    };
    render(<SanityCheckPanel sanity={passing} error={null} loading={false} isBaselineRun />);
    expect(screen.getByRole("note")).toHaveTextContent(/model is not trained/i);
  });

  it("renders the caveat, lineage, PASS/FAIL badges, wind-farm band header and contradictions", () => {
    render(
      <SanityCheckPanel sanity={PASSING_SANITY} error={null} loading={false} isBaselineRun />,
    );

    // Caveat always present.
    expect(screen.getByRole("note")).toHaveTextContent(/not trained to reproduce/i);

    // Lineage line from run_metadata.
    expect(screen.getByText(/pipeline 1\.4\.2/)).toBeInTheDocument();

    // Explicit PASS and FAIL badges, one per check.
    expect(screen.getAllByText(/^(PASS|FAIL)$/)).toHaveLength(2);
    expect(screen.getByText("PASS")).toBeInTheDocument();
    expect(screen.getByText("FAIL")).toBeInTheDocument();

    // Wind-farm band-N column header renders the engine's top_band_n (no math).
    expect(
      screen.getByRole("columnheader", { name: /In top-ranked band \(rank ≤ 20\)/ }),
    ).toBeInTheDocument();
    expect(screen.getByRole("rowheader", { name: "Sapphire" })).toBeInTheDocument();

    // Full contradictions list with the per-row check label.
    expect(screen.getByText("Known wind farm comparison")).toBeInTheDocument();
    expect(screen.getByText(/Sapphire wind farm fell on excluded land/)).toBeInTheDocument();
  });

  it("renders a failing check alongside its investigated contradictions", () => {
    const failing: SanityCheck = {
      ...PASSING_SANITY,
      checks: [
        {
          name: "Known-wind-farm top-ranked band",
          expected: "≥ 50% of farms in band",
          observed: "20% in band",
          passed: false,
        },
        {
          name: "REZ representation among top cells",
          expected: "≥ 30% inside a REZ",
          observed: "5% inside a REZ",
          passed: false,
        },
      ],
      contradictions: [
        {
          check: "Known wind farm comparison",
          description: "Sapphire wind farm fell on excluded land.",
          kind: "data_issue",
          investigation_note: "Protected-area overlap flagged for Sprint-2 review.",
        },
        {
          check: "Score distribution",
          description: "Top decile under-represents declared REZs.",
          kind: "distribution_anomaly",
          investigation_note: "REZ layer join rate is lower than expected.",
        },
      ],
    };
    render(
      <SanityCheckPanel sanity={failing} error={null} loading={false} isBaselineRun />,
    );

    // Both checks fail — two FAIL badges, no PASS badge.
    expect(screen.getAllByText("FAIL")).toHaveLength(2);
    expect(screen.queryByText("PASS")).not.toBeInTheDocument();

    // The caveat is still present on a failing result.
    expect(screen.getByRole("note")).toHaveTextContent(/not trained to reproduce/i);

    // The FULL contradictions list renders, each with its source-check label
    // and investigation note.
    expect(screen.getByText("Known wind farm comparison")).toBeInTheDocument();
    expect(screen.getByText("Score distribution")).toBeInTheDocument();
    expect(screen.getByText(/Top decile under-represents declared REZs/)).toBeInTheDocument();
    expect(
      screen.getByText(/REZ layer join rate is lower than expected/),
    ).toBeInTheDocument();
  });

  it("asserts single-lineage when the active run is the unmodified baseline", () => {
    render(
      <SanityCheckPanel sanity={PASSING_SANITY} error={null} loading={false} isBaselineRun />,
    );
    expect(screen.getByText(/same engine output as the map and/i)).toBeInTheDocument();
    expect(
      screen.queryByText(/Sanity reflects the BASELINE run, not the current scenario/),
    ).not.toBeInTheDocument();
  });

  it("warns that sanity reflects the baseline when the run is a scenario or edited baseline", () => {
    render(
      <SanityCheckPanel
        sanity={PASSING_SANITY}
        error={null}
        loading={false}
        isBaselineRun={false}
      />,
    );
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(/Sanity reflects the BASELINE run, not the current scenario/);
  });

  it("renders the in-band column from in_top_band, not in_upper_quartile", () => {
    // Two rows that would COINCIDE if the panel read in_upper_quartile: both are
    // in the Upper_Quartile, but only the rank ≤ 20 row is in the top-ranked
    // band. The panel must render band membership (in_top_band), so the two
    // columns can no longer silently agree.
    const divergent: SanityCheck = {
      ...PASSING_SANITY,
      wind_farms: [
        {
          wind_farm: "Bodangora",
          cell_id: "S32.000_E149.000",
          score: 0.9,
          rank: 2, // within the band (rank ≤ 20)
          percentile: 0.99,
          in_upper_quartile: true,
          in_top_band: true,
          notes: "",
        },
        {
          wind_farm: "Sapphire",
          cell_id: "S30.100_E151.200",
          score: 0.81,
          rank: 55, // outside the band (rank > 20) but still Upper_Quartile
          percentile: 0.98,
          in_upper_quartile: true,
          in_top_band: false,
          notes: "",
        },
      ],
    };
    render(
      <SanityCheckPanel sanity={divergent} error={null} loading={false} isBaselineRun />,
    );

    const bodangoraRow = screen.getByRole("rowheader", { name: "Bodangora" }).closest("tr");
    const sapphireRow = screen.getByRole("rowheader", { name: "Sapphire" }).closest("tr");
    expect(bodangoraRow).not.toBeNull();
    expect(sapphireRow).not.toBeNull();

    // The in-band cell is the LAST cell in each row.
    const bodangoraInBand = within(bodangoraRow as HTMLElement).getAllByRole("cell").at(-1);
    const sapphireInBand = within(sapphireRow as HTMLElement).getAllByRole("cell").at(-1);

    // rank ≤ 20 → "Yes"; rank > 20 → "No", even though both are Upper_Quartile.
    expect(bodangoraInBand).toHaveTextContent("Yes");
    expect(sapphireInBand).toHaveTextContent("No");
  });

  it("falls back to 'lineage metadata unavailable' when run_metadata is null", () => {
    const noLineage: SanityCheck = { ...PASSING_SANITY, run_metadata: null };
    render(
      <SanityCheckPanel sanity={noLineage} error={null} loading={false} isBaselineRun />,
    );
    expect(screen.getByText("lineage metadata unavailable")).toBeInTheDocument();
  });
});
