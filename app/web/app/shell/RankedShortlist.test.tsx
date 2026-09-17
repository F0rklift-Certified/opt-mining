/**
 * Render/interaction tests for the S3-04 ranked shortlist panel.
 *
 * The panel is a pure view over `GET /runs/{run_id}/results`: it must keep
 * the engine's order, show the engine's rank/score/contribution values as
 * served, and report row selection through the shared selection contract.
 */
import { fireEvent, render, screen, within } from "@testing-library/react";

import type { RankedRow } from "../api/decision-service";
import RankedShortlist from "./RankedShortlist";

const ROWS: RankedRow[] = [
  {
    cell_id: "S30.100_E151.200",
    rank: 1,
    suitability_score: 0.912,
    key_components: { wind_speed: 0.501, dist_transmission_km: 0.2, inside_rez: 0.1 },
  },
  {
    cell_id: "S30.200_E151.300",
    rank: 2,
    suitability_score: 0.874,
    // The engine omits null contributions rather than sending 0.0.
    key_components: { wind_speed: 0.474, inside_rez: 0.1 },
  },
];

function bodyRows(): HTMLElement[] {
  const [, body] = screen.getAllByRole("rowgroup");
  return within(body!).getAllByRole("row");
}

describe("RankedShortlist", () => {
  it("renders rows in exactly the served order, never re-sorting by score", () => {
    // Deliberately inconsistent scores: a UI that sorted by score would put
    // rank 2 first. The panel must trust the engine's order as given.
    const rows: RankedRow[] = [
      { cell_id: "S31.000_E150.000", rank: 1, suitability_score: 0.5 },
      { cell_id: "S31.100_E150.100", rank: 2, suitability_score: 0.9 },
    ];
    render(<RankedShortlist rows={rows} selectedCellId={null} onSelect={jest.fn()} />);

    const rendered = bodyRows();
    expect(rendered).toHaveLength(2);
    expect(rendered[0]).toHaveTextContent("S31.000_E150.000");
    expect(rendered[1]).toHaveTextContent("S31.100_E150.100");
  });

  it("shows Site ID, rank, score and one column per engine component", () => {
    render(<RankedShortlist rows={ROWS} selectedCellId={null} onSelect={jest.fn()} />);

    // Component values are contributions, not raw measurements; say so.
    expect(screen.getByRole("table")).toHaveAccessibleDescription(
      /contribution to the suitability score/,
    );

    const headers = screen
      .getAllByRole("columnheader")
      .map((header) => header.textContent);
    expect(headers).toEqual([
      "Rank",
      "Site ID",
      "Suitability",
      "Wind speed",
      "Transmission distance",
      "Inside REZ",
    ]);

    const [first, second] = bodyRows();
    const firstCells = within(first!)
      .getAllByRole("cell")
      .map((cell) => cell.textContent);
    expect(within(first!).getByRole("rowheader")).toHaveTextContent("S30.100_E151.200");
    expect(firstCells).toEqual(["1", "0.912", "0.501", "0.200", "0.100"]);

    // A contribution the engine did not serve is shown as missing, not zero.
    const secondCells = within(second!)
      .getAllByRole("cell")
      .map((cell) => cell.textContent);
    expect(secondCells).toEqual(["2", "0.874", "0.474", "—", "0.100"]);
  });

  it("labels an unrecognised component with its engine key", () => {
    const rows: RankedRow[] = [
      { cell_id: "S30.100_E151.200", rank: 1, suitability_score: 0.4, key_components: { new_criterion: 0.4 } },
    ];
    render(<RankedShortlist rows={rows} selectedCellId={null} onSelect={jest.fn()} />);

    expect(screen.getByRole("columnheader", { name: "new_criterion" })).toBeInTheDocument();
  });

  it("selects a site by clicking its row or its Site ID button", () => {
    const onSelect = jest.fn();
    render(<RankedShortlist rows={ROWS} selectedCellId={null} onSelect={onSelect} />);

    const [, second] = bodyRows();
    fireEvent.click(within(second!).getByText("0.874"));
    expect(onSelect).toHaveBeenLastCalledWith("S30.200_E151.300");

    fireEvent.click(screen.getByRole("button", { name: "S30.100_E151.200" }));
    expect(onSelect).toHaveBeenLastCalledWith("S30.100_E151.200");
    expect(onSelect).toHaveBeenCalledTimes(2);
  });

  it("marks only the selected site as pressed", () => {
    render(
      <RankedShortlist rows={ROWS} selectedCellId="S30.200_E151.300" onSelect={jest.fn()} />,
    );

    expect(screen.getByRole("button", { name: "S30.200_E151.300" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.getByRole("button", { name: "S30.100_E151.200" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
  });

  it("marks no row when the selected site is outside the shortlist", () => {
    render(
      <RankedShortlist rows={ROWS} selectedCellId="S35.000_E149.000" onSelect={jest.fn()} />,
    );

    for (const button of screen.getAllByRole("button")) {
      expect(button).toHaveAttribute("aria-pressed", "false");
    }
  });

  it("says so when the engine returned no eligible cells", () => {
    render(<RankedShortlist rows={[]} selectedCellId={null} onSelect={jest.fn()} />);

    expect(screen.getByText("No eligible cells were returned.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});
