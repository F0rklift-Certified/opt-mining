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

  it("falls back to 'lineage metadata unavailable' when run_metadata is null", () => {
    const noLineage: SanityCheck = { ...PASSING_SANITY, run_metadata: null };
    render(
      <SanityCheckPanel sanity={noLineage} error={null} loading={false} isBaselineRun />,
    );
    expect(screen.getByText("lineage metadata unavailable")).toBeInTheDocument();
  });
});
