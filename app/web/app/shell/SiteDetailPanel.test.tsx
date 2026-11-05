/**
 * Render tests for the site-detail / "Why this site?" panel (S3-05, S4-03).
 *
 * The panel is a pure view over `GET /runs/{run_id}/sites/{cell_id}`. For an
 * eligible site it must show every S4-03 field — cell id, suitability score,
 * rank, wind value and contribution, demand proxy, infrastructure and
 * geographic/environmental indicators, criterion contributions, positive
 * factors, weaknesses and data quality — and render the S2-06 explanation text
 * VERBATIM. For an excluded site it must show the not-eligible status, the
 * exclusion reasons and data quality, and NO score or rank. It must never emit
 * "best site" wording.
 */
import { render, screen, within } from "@testing-library/react";

import type { SiteDetail } from "../api/decision-service";
import SiteDetailPanel from "./SiteDetailPanel";

const PROXY_CAVEAT =
  "Demand shown is a spatial proxy allocated below the AEMO region, not measured local demand";

/** The integrated-row context the service now serves after the criteria. */
const CONTEXT = {
  centroid_lat: -31.18625,
  centroid_lon: 151.68625,
  area_km2: 27.2,
  source_region: "NSW1",
  dist_connection_km: 12.34,
  rez_name: "New England",
  elevation_m: 1210.4,
  tri: 4.21,
  land_use: "2.1.0 Grazing native vegetation",
  protected_area: false,
  protected_area_name: "",
  wind_confidence: "valid",
  demand_confidence: "high",
  infra_confidence: "high",
  geo_confidence: "high",
  data_confidence: "high",
  confidence_score: 0.83,
  confidence_notes: "Missing connection-point distance",
  n_missing_features: 1,
  exclusion_reason: null,
  triggered_rules: null,
};

const ELIGIBLE: SiteDetail = {
  cell_id: "S31.186_E151.686",
  eligible: true,
  rank: 1,
  suitability_score: 0.921,
  demand_load_mva: 128.4,
  contributions: {
    wind_speed: 0.501,
    dist_transmission_km: 0.2,
    demand_proxy: 0.15,
    dist_substation_km: 0.02,
    slope_deg: 0.05,
    inside_rez: 0.0,
  },
  features: {
    wind_speed: 8.412,
    dist_transmission_km: 3.27,
    demand_proxy: 1,
    dist_substation_km: 6.5,
    slope_deg: 2.44,
    inside_rez: true,
    ...CONTEXT,
  },
  explanation: {
    headline: "Eligible candidate under the selected assumptions and criteria",
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
  contributions: {},
  features: {
    wind_speed: 7.1,
    slope_deg: 18.2,
    ...CONTEXT,
    data_confidence: "medium",
    confidence_score: 0.61,
    exclusion_reason: "Slope exceeds 15°",
    triggered_rules: "excessive_slope",
  },
  explanation: {
    exclusion_reasons: [{ code: "excessive_slope", text: "Slope exceeds 15°" }],
    proxy_caveats: [PROXY_CAVEAT],
    data_quality_notes: ["Confidence: medium — Low geographic confidence"],
  },
};

/** The table row whose header cell starts with `label`. */
function rowFor(label: string): HTMLElement {
  const header = screen
    .getAllByRole("rowheader")
    .find((cell) => cell.textContent?.startsWith(label));
  if (!header) throw new Error(`no row for ${label}`);
  return header.closest("tr") as HTMLElement;
}

describe("SiteDetailPanel — eligible site (S4-03 AC2)", () => {
  it("shows id, status, location, score, rank and data confidence up front", () => {
    render(<SiteDetailPanel site={ELIGIBLE} />);

    expect(screen.getByText("S31.186_E151.686")).toBeInTheDocument();
    expect(screen.getByText("Eligible candidate")).toBeInTheDocument();
    expect(screen.getByText("31.186° S, 151.686° E")).toBeInTheDocument();
    expect(screen.getByText("0.921")).toBeInTheDocument();
    expect(screen.getByText("#1")).toBeInTheDocument();
    expect(screen.getAllByText("high")[0]).toHaveClass("om-confidence--high");
    expect(screen.getByText("(0.83)", { exact: false })).toBeInTheDocument();
  });

  it("lists each criterion's value with units, its theme and its contribution", () => {
    render(<SiteDetailPanel site={ELIGIBLE} />);

    expect(screen.getByText("Criterion values and contributions")).toBeInTheDocument();
    const wind = within(rowFor("Wind speed"));
    expect(wind.getByText("Wind resource")).toBeInTheDocument();
    expect(wind.getByText("8.41 m/s")).toBeInTheDocument();
    expect(wind.getByText("0.501")).toBeInTheDocument();

    const demand = within(rowFor("Demand proxy"));
    expect(demand.getByText("Demand · proxy")).toBeInTheDocument();
    expect(demand.getByText("1.000 index 0–1")).toBeInTheDocument();

    const transmission = within(rowFor("Distance to transmission"));
    expect(transmission.getByText("Grid infrastructure")).toBeInTheDocument();
    expect(transmission.getByText("3.3 km")).toBeInTheDocument();
    expect(within(rowFor("Inside a REZ")).getByText("Yes")).toBeInTheDocument();
    expect(within(rowFor("Slope")).getByText("2.4 °")).toBeInTheDocument();
  });

  it("groups the served context: demand, infrastructure, geography/environment, data quality", () => {
    render(<SiteDetailPanel site={ELIGIBLE} />);

    expect(screen.getByText("Site context — Demand")).toBeInTheDocument();
    expect(within(rowFor("AEMO demand region")).getByText("NSW1")).toBeInTheDocument();
    expect(screen.getByText("Site context — Grid infrastructure")).toBeInTheDocument();
    expect(within(rowFor("Renewable Energy Zone")).getByText("New England")).toBeInTheDocument();
    expect(
      within(rowFor("Distance to connection point")).getByText("12.3 km"),
    ).toBeInTheDocument();
    expect(screen.getByText("Site context — Geography & environment")).toBeInTheDocument();
    expect(within(rowFor("Elevation")).getByText("1210 m")).toBeInTheDocument();
    expect(
      within(rowFor("Land use")).getByText("2.1.0 Grazing native vegetation"),
    ).toBeInTheDocument();
    expect(within(rowFor("In a protected area")).getByText("No")).toBeInTheDocument();
    expect(within(rowFor("Protected area")).getByText("—")).toBeInTheDocument();
    expect(screen.getByText("Data quality & confidence")).toBeInTheDocument();
    expect(within(rowFor("Geographic data")).getByText("high")).toBeInTheDocument();
    expect(
      within(rowFor("Confidence notes")).getByText("Missing connection-point distance"),
    ).toBeInTheDocument();
    // The centroid is the Location line, not a context row.
    expect(screen.queryByText("centroid_lat")).not.toBeInTheDocument();
  });

  it("renders the explanation text verbatim, with no 'best site' language", () => {
    const { container } = render(<SiteDetailPanel site={ELIGIBLE} />);

    // The DISPLAY-ONLY network-load read-out: the served MVA figure rounded to
    // whole MVA, labelled with the search radius, shown as an estimate.
    expect(
      screen.getByText("≈ 128 MVA network load within ~40 km"),
    ).toBeInTheDocument();
    expect(screen.getByText("Nearby network load")).toBeInTheDocument();

    expect(
      screen.getByText("Eligible candidate under the selected assumptions and criteria"),
    ).toBeInTheDocument();
    expect(screen.getByText("Strong wind resource (strong)")).toBeInTheDocument();
    expect(screen.getByText("Outside any Renewable Energy Zone (absent)")).toBeInTheDocument();
    expect(screen.getByText(PROXY_CAVEAT)).toBeInTheDocument();
    expect(
      screen.getByText("Confidence: high — Missing connection-point distance"),
    ).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/best site/i);
  });
});

describe("SiteDetailPanel — excluded site (S4-03 AC3)", () => {
  it("shows not-eligible status and reasons, and no suitability score or rank", () => {
    const { container } = render(<SiteDetailPanel site={EXCLUDED} />);

    expect(screen.getByText("Not eligible — excluded")).toBeInTheDocument();
    expect(screen.getByText("Why excluded")).toBeInTheDocument();
    expect(screen.getByText("Slope exceeds 15°")).toBeInTheDocument();
    expect(
      screen.getByText("None — excluded cells are not scored or ranked"),
    ).toBeInTheDocument();
    // No score/rank rows at all — an excluded cell is never shown ranked.
    expect(screen.queryByText("Suitability score")).not.toBeInTheDocument();
    expect(screen.queryByText("Rank")).not.toBeInTheDocument();
    expect(screen.queryByText(/^#\d/)).not.toBeInTheDocument();
    expect(screen.queryByText("Contribution to score")).not.toBeInTheDocument();
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
    expect(screen.getByText("0.921")).toBeInTheDocument();
  });

  it("still shows the criterion values and the data quality that apply", () => {
    render(<SiteDetailPanel site={EXCLUDED} />);

    expect(screen.getByText("Criterion values")).toBeInTheDocument();
    expect(within(rowFor("Slope")).getByText("18.2 °")).toBeInTheDocument();
    expect(screen.getAllByText("medium")[0]).toHaveClass("om-confidence--medium");
    expect(
      screen.getByText("Confidence: medium — Low geographic confidence"),
    ).toBeInTheDocument();
    expect(screen.getByText(PROXY_CAVEAT)).toBeInTheDocument();
    // The raw exclusion columns are not repeated as context rows.
    expect(screen.queryByText("triggered_rules")).not.toBeInTheDocument();
  });
});

describe("SiteDetailPanel — sparse payloads", () => {
  it("renders without throwing when optional explanation arrays are absent", () => {
    const minimal: SiteDetail = {
      cell_id: "S30.000_E150.000",
      eligible: true,
      rank: 3,
      suitability_score: 0.5,
    };
    render(<SiteDetailPanel site={minimal} />);

    expect(screen.getByText("0.500")).toBeInTheDocument();
    expect(screen.getByText("#3")).toBeInTheDocument();
    // No empty sections are rendered.
    expect(screen.queryByText("Positive factors")).not.toBeInTheDocument();
    expect(screen.queryByText("Why excluded")).not.toBeInTheDocument();
    expect(screen.queryByText(/Criterion values/)).not.toBeInTheDocument();
    expect(screen.queryByText("Location")).not.toBeInTheDocument();
  });

  it("shows an unknown served column as-is rather than dropping it", () => {
    render(
      <SiteDetailPanel
        site={{ ...ELIGIBLE, features: { ...ELIGIBLE.features, new_indicator: 4.5 } }}
      />,
    );
    expect(within(rowFor("new_indicator")).getByText("4.500")).toBeInTheDocument();
  });
});

describe("SiteDetailPanel — demand columns from the integrated row", () => {
  it("labels demand location confidence and shows the MVA figure only once", () => {
    const site: SiteDetail = {
      ...ELIGIBLE,
      features: { ...ELIGIBLE.features, load_within_radius_mva: 128.4, demand_coord_confidence: "low" },
    };
    const { container } = render(<SiteDetailPanel site={site} />);
    expect(screen.getByText("Demand location confidence")).toBeInTheDocument();
    expect(screen.queryByText("load_within_radius_mva")).not.toBeInTheDocument();
    expect(screen.queryByText("demand_coord_confidence")).not.toBeInTheDocument();
    expect(container.textContent?.match(/MVA/g)?.length).toBe(1);
  });
});

