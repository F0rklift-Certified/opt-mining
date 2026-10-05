/**
 * Render test for the stable Opt-Mining application shell.
 *
 * Asserts the fixed, decision-free substrate this ticket stands up:
 *   - the App_Shell renders all four labelled `PlaceholderRegion`s — analysis
 *     controls, interactive map, ranked results, and site detail/explanation
 *     (Requirements 3.1–3.4);
 *   - the region is FIXED to NSW and shown as a static label, with NO region
 *     selector — no <select>, no combobox, no listbox control anywhere in the
 *     shell (Requirement 1.2).
 *
 * These are example/render assertions (not property-based): the shell content
 * is fixed, so the right tool is a concrete render check per the design's
 * Testing Strategy.
 */
import { render, screen, within } from "@testing-library/react";

import RootLayout from "../layout";
import AppShell from "./AppShell";

describe("AppShell — four fixed regions (R3.1–3.4)", () => {
  const REGION_LABELS = [
    "Analysis controls",
    "Interactive map",
    "Ranked results",
    "Site detail / explanation",
  ];

  it("renders all four labelled regions as headings", () => {
    render(<AppShell />);

    for (const label of REGION_LABELS) {
      // Each region is a labelled <section> with a heading naming it.
      expect(
        screen.getByRole("heading", { name: label }),
      ).toBeInTheDocument();
    }
  });

  it("exposes exactly four region landmarks", () => {
    render(<AppShell />);

    // PlaceholderRegion renders a <section aria-label=...>, which is a region
    // landmark. There must be exactly the four fixed regions.
    const regions = screen.getAllByRole("region");
    expect(regions).toHaveLength(REGION_LABELS.length);
  });

  it("renders no region-selector control in the shell (R1.2)", () => {
    render(<AppShell />);

    // No dropdown / combobox / listbox for choosing a region.
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /region/i }),
    ).not.toBeInTheDocument();
  });
});

describe("RootLayout — fixed NSW region, no selector (R1.2)", () => {
  it("shows the fixed NSW region as a static label", () => {
    // Render the real layout so the header markup is exercised as in the app.
    render(
      <RootLayout>
        <AppShell />
      </RootLayout>,
      { container: document },
    );

    const banner = screen.getByRole("banner");
    expect(within(banner).getByText(/Region:\s*NSW/i)).toBeInTheDocument();
  });

  it("provides no region selector anywhere (no combobox/listbox/select)", () => {
    render(
      <RootLayout>
        <AppShell />
      </RootLayout>,
      { container: document },
    );

    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    // Belt-and-braces: no raw <select> element in the rendered shell either.
    expect(document.querySelector("select")).toBeNull();
  });
});
