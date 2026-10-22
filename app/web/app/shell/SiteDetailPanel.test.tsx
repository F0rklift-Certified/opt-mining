/**
 * Render tests for the S3-05 site-detail & explanation panel.
 *
 * The panel is a pure view over `GET /runs/{run_id}/sites/{cell_id}`: it must
 * show the engine's features, component scores, total score and eligibility,
 * and render the S2-06 explanation text VERBATIM — positive factors,
 * weaknesses, proxy caveats, data-quality notes, and (for excluded cells)
 * exclusion reasons. It must never emit "best site" wording and must handle a
 * null score/rank gracefully.
 */
import { render, screen } from "@testing-library/react";

import type { SiteDetail } from "../api/decision-service";
import SiteDetailPanel from "./SiteDetailPanel";

const PROXY_CAVEAT =
  "Demand shown is a spatial proxy allocated below the AEMO region, not measured local demand";

const ELIGIBLE: SiteDetail = {
  cell_id: "S28.186_E141.036",
  eligible: true,
  rank: 1,
  suitability_score: 0.912,
  demand_load_mva: 128.4,
  contributions: {
    wind_speed: 0.501,
    dist_transmission_km: 0.2,
    demand_proxy: 0.15,
  },
  features: {
    wind_speed: 8.4,
    demand_proxy: 0.73,
    inside_rez: false,
  },
  explanation: {
    headline: "Higher-ranked candidate under the selected assumptions and criteria",
    positive_factors: ["Strong wind resource (strong)", "Gentle terrain (top decile)"],
    weaknesses: ["Outside any Renewable Energy Zone (absent)"],
    proxy_caveats: [PROXY_CAVEAT],
    data_quality_notes: ["Confidence: high — Missing connection-point distance"],
  },
};

const EXCLUDED: SiteDetail = {
  cell_id: "S28.186_E152.386",
  eligible: false,
  rank: null,
  suitability_score: null,
  explanation: {
    exclusion_reasons: [{ code: "excessive_slope", text: "Slope exceeds 15°" }],
    proxy_caveats: [PROXY_CAVEAT],
    data_quality_notes: ["Confidence: high — Missing connection-point distance"],
  },
};

describe("SiteDetailPanel", () => {
  it("renders an eligible site's scores, features and explanation verbatim", () => {
    const { container } = render(<SiteDetailPanel site={ELIGIBLE} />);

    // Header facts: eligibility and the total suitability score.
    expect(screen.getByText("Yes")).toBeInTheDocument();
    expect(screen.getByText("0.912")).toBeInTheDocument();

    // Component scores: labelled criteria with their served values. The
    // "Wind speed" label appears in both the component-score and feature
    // tables, so assert on a label unique to contributions plus the values.
    expect(screen.getByText("Transmission distance")).toBeInTheDocument();
    // "Demand" labels the demand_proxy row in both the component-score table
    // (contribution) and the Features table (proxy index), so assert presence.
    expect(screen.getAllByText("Demand").length).toBeGreaterThan(0);
    expect(screen.getByText("0.501")).toBeInTheDocument();
    expect(screen.getAllByText("Wind speed").length).toBeGreaterThan(0);

    // A raw/derived feature value appears with its unit of measurement.
    expect(screen.getByText("8.400 m/s")).toBeInTheDocument();

    // The DISPLAY-ONLY network-load read-out: the served MVA figure rounded to
    // whole MVA, labelled with the search radius, shown as an estimate.
    expect(
      screen.getByText("≈ 128 MVA network load within ~40 km"),
    ).toBeInTheDocument();
    expect(screen.getByText("Nearby network load")).toBeInTheDocument();

    // The scored demand signal (the proxy index) is still shown alongside the
    // tangible MVA figure — as a bare value, since the tangible meaning now
    // lives in the "Nearby network load" (MVA) section above.
    expect(screen.getByText("0.730")).toBeInTheDocument();

    // Verbatim explanation strings.
    expect(screen.getByText("Higher-ranked candidate under the selected assumptions and criteria")).toBeInTheDocument();
    expect(screen.getByText("Strong wind resource (strong)")).toBeInTheDocument();
    expect(screen.getByText("Outside any Renewable Energy Zone (absent)")).toBeInTheDocument();
    expect(screen.getByText(PROXY_CAVEAT)).toBeInTheDocument();
    expect(screen.getByText("Confidence: high — Missing connection-point distance")).toBeInTheDocument();

    // Screening-level language only — never "best site".
    expect(container.textContent).not.toMatch(/best site/i);
  });

  it("renders an excluded site's reasons and handles null score/rank gracefully", () => {
    const { container } = render(<SiteDetailPanel site={EXCLUDED} />);

    expect(screen.getByText("No")).toBeInTheDocument();
    expect(screen.getByText("Not scored")).toBeInTheDocument();
    expect(screen.getByText("Not ranked")).toBeInTheDocument();

    // The exclusion reason text is shown verbatim.
    expect(screen.getByText("Slope exceeds 15°")).toBeInTheDocument();
    expect(screen.getByText("Why excluded")).toBeInTheDocument();

    // Proxy caveat still shown; null values never render as "null".
    expect(screen.getByText(PROXY_CAVEAT)).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/null/);
    expect(container.textContent).not.toMatch(/best site/i);

    // The network-load read-out is absent when no MVA figure is served.
    expect(screen.queryByText("Nearby network load")).not.toBeInTheDocument();
    expect(container.textContent).not.toMatch(/MVA/);
  });

  it("omits the network-load read-out when demand_load_mva is null", () => {
    const nullMva: SiteDetail = { ...ELIGIBLE, demand_load_mva: null };
    render(<SiteDetailPanel site={nullMva} />);

    expect(screen.queryByText("Nearby network load")).not.toBeInTheDocument();
    expect(screen.queryByText(/MVA network load/)).not.toBeInTheDocument();
    // The other facts still render.
    expect(screen.getByText("0.912")).toBeInTheDocument();
  });

  it("renders without throwing when optional explanation arrays are absent", () => {
    const minimal: SiteDetail = {
      cell_id: "S30.000_E150.000",
      eligible: true,
      rank: 3,
      suitability_score: 0.5,
    };
    render(<SiteDetailPanel site={minimal} />);

    expect(screen.getByText("0.500")).toBeInTheDocument();
    // No empty explanation section headings are rendered.
    expect(screen.queryByText("Positive factors")).not.toBeInTheDocument();
    expect(screen.queryByText("Why excluded")).not.toBeInTheDocument();
    expect(screen.queryByText("Component scores")).not.toBeInTheDocument();
  });
});
