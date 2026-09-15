/**
 * Render test for the Opt-Mining application shell (S3-01a, task 6.5).
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

describe("AppShell — four fixed placeholder regions (R3.1–3.4)", () => {
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
  /**
   * RootLayout renders <html>/<body>. React warns about nesting <html> inside
   * Testing Library's default <div> container. That warning is expected and
   * harmless here — we intentionally render the real layout to exercise the
   * title-bar markup — so we silence just this one message to keep the test
   * output clean while still asserting on the live document.
   */
  let consoleErrorSpy: jest.SpyInstance;

  beforeEach(() => {
    consoleErrorSpy = jest
      .spyOn(console, "error")
      .mockImplementation((...args: unknown[]) => {
        const first = args[0];
        if (typeof first === "string" && first.includes("validateDOMNesting")) {
          return;
        }
        // Surface any other error so real problems are not hidden.
        // eslint-disable-next-line no-console
        console.warn(...(args as [unknown, ...unknown[]]));
      });
  });

  afterEach(() => {
    consoleErrorSpy.mockRestore();
  });

  it("shows the fixed NSW region as a static label", () => {
    // Render the real layout so the header markup is exercised as in the app.
    render(
      <RootLayout>
        <AppShell />
      </RootLayout>,
    );

    const banner = screen.getByRole("banner");
    expect(within(banner).getByText(/Region:\s*NSW/i)).toBeInTheDocument();
  });

  it("provides no region selector anywhere (no combobox/listbox/select)", () => {
    render(
      <RootLayout>
        <AppShell />
      </RootLayout>,
    );

    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    // Belt-and-braces: no raw <select> element in the rendered shell either.
    expect(document.querySelector("select")).toBeNull();
  });
});
