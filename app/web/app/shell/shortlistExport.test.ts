/**
 * Unit tests for the S3-07 shortlist CSV serialiser.
 *
 * The serialiser is a pure view over the `RankedRow[]` already in UI state:
 * these tests pin the column set/order, that row order mirrors input order
 * (no re-sort), the on-screen numeric formatting, RFC-4180 escaping, the
 * leading disclaimer metadata line, and the empty-shortlist case.
 */
import type { RankedRow } from "../api/decision-service";
import { PRELIMINARY_DISCLAIMER, serializeShortlistCsv } from "./shortlistExport";

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

/** CSV records (RFC-4180 CRLF), dropping the leading `#` disclaimer line. */
function records(csv: string): string[] {
  const lines = csv.split("\r\n");
  return lines.slice(1);
}

describe("serializeShortlistCsv", () => {
  it("emits the column set in first-served order: rank,cell_id,suitability_score,<components>,eligible", () => {
    const csv = serializeShortlistCsv(ROWS, PRELIMINARY_DISCLAIMER);
    const [header] = records(csv);
    expect(header).toBe(
      "rank,cell_id,suitability_score,wind_speed,dist_transmission_km,inside_rez,eligible",
    );
  });

  it("keeps rows in input order, never re-sorting by score", () => {
    // Deliberately inconsistent scores: a serialiser that sorted by score would
    // put rank 2 first. It must trust the engine's order as given.
    const rows: RankedRow[] = [
      { cell_id: "S31.000_E150.000", rank: 1, suitability_score: 0.5 },
      { cell_id: "S31.100_E150.100", rank: 2, suitability_score: 0.9 },
    ];
    const data = records(serializeShortlistCsv(rows, PRELIMINARY_DISCLAIMER)).slice(1);
    expect(data).toEqual([
      "1,S31.000_E150.000,0.500,true",
      "2,S31.100_E150.100,0.900,true",
    ]);
  });

  it("formats rank as integer, score/components with toFixed(3), missing component as empty, eligible as true", () => {
    const csv = serializeShortlistCsv(ROWS, PRELIMINARY_DISCLAIMER);
    const [, first, second] = records(csv);
    expect(first).toBe("1,S30.100_E151.200,0.912,0.501,0.200,0.100,true");
    // The engine did not serve dist_transmission_km for this row → empty field.
    expect(second).toBe("2,S30.200_E151.300,0.874,0.474,,0.100,true");
  });

  it("applies RFC-4180 escaping to fields with commas, quotes and newlines", () => {
    const rows: RankedRow[] = [
      {
        cell_id: 'odd,"id"\nwith breaks',
        rank: 1,
        suitability_score: 0.5,
        key_components: { "comma,key": 0.25 },
      },
    ];
    const csv = serializeShortlistCsv(rows, PRELIMINARY_DISCLAIMER);
    const [header, data] = records(csv);
    // A component key with a comma is quoted in the header.
    expect(header).toBe('rank,cell_id,suitability_score,"comma,key",eligible');
    // The cell_id's comma/quote/newline are escaped: quotes doubled, field wrapped.
    expect(data).toBe('1,"odd,""id""\nwith breaks",0.500,0.250,true');
  });

  it("carries the preliminary disclaimer as the leading # metadata line", () => {
    const csv = serializeShortlistCsv(ROWS, PRELIMINARY_DISCLAIMER);
    const [first] = csv.split("\r\n");
    expect(first).toBe(`# ${PRELIMINARY_DISCLAIMER}`);
    expect(PRELIMINARY_DISCLAIMER).toContain("preliminary screening output");
  });

  it("emits only the disclaimer line and base header for an empty shortlist", () => {
    const csv = serializeShortlistCsv([], PRELIMINARY_DISCLAIMER);
    expect(csv.split("\r\n")).toEqual([
      `# ${PRELIMINARY_DISCLAIMER}`,
      "rank,cell_id,suitability_score,eligible",
    ]);
  });
});
