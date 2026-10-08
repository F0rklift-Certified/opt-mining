/**
 * Ranked shortlist panel (S3-04).
 *
 * A pure view over the S2-08 ranked results for one run. Rows are rendered in
 * the order the decision service returns them — the engine's S2-05 rank, ties
 * already broken by the engine — and every rank, score and component value is
 * shown exactly as served. Selecting a row reports the site through the shared
 * selection contract, so the map (S3-03b) and site detail (S3-05) follow it.
 */
import { useId } from "react";

import type { RankedRow } from "../api/decision-service";
import type { SelectSite } from "./siteSelection";

export interface RankedShortlistProps {
  /** Ranked results for the active run, in service order. */
  rows: RankedRow[];
  /** Currently selected cell, from this table or the map; null for none. */
  selectedCellId: string | null;
  onSelect: SelectSite;
}

/** Display labels for the engine's criteria; unknown keys show as served. */
const COMPONENT_LABELS: Readonly<Record<string, string>> = {
  wind_speed: "Wind speed",
  dist_transmission_km: "Transmission distance",
  demand_proxy: "Demand",
  dist_substation_km: "Substation distance",
  slope_deg: "Slope",
  inside_rez: "Inside REZ",
};

/** Component keys in first-served order, which is the engine's criterion order. */
function componentKeys(rows: RankedRow[]): string[] {
  const keys = new Set<string>();
  for (const row of rows) {
    for (const key of Object.keys(row.key_components ?? {})) keys.add(key);
  }
  return Array.from(keys);
}

function formatValue(value: number | undefined): string {
  return value === undefined ? "—" : value.toFixed(3);
}

export default function RankedShortlist({
  rows,
  selectedCellId,
  onSelect,
}: RankedShortlistProps): JSX.Element {
  const noteId = useId();
  if (rows.length === 0) return <p>No eligible cells were returned.</p>;

  const components = componentKeys(rows);

  return (
    <div className="om-shortlist">
      <p className="om-shortlist__note" id={noteId}>
        Engine rank order. Component columns show each criterion&apos;s
        contribution to the suitability score.
      </p>
      <div className="om-results__scroll">
        <table className="om-results" aria-describedby={noteId}>
          <thead>
            <tr>
              <th scope="col">Rank</th>
              <th scope="col">Site ID</th>
              <th scope="col" className="om-results__num">Suitability</th>
              {components.map((key) => (
                <th scope="col" className="om-results__num" key={key}>
                  {COMPONENT_LABELS[key] ?? key}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => {
              const selected = row.cell_id === selectedCellId;
              return (
                <tr
                  key={row.cell_id}
                  className={
                    selected
                      ? "om-results__row om-results__row--selected"
                      : "om-results__row"
                  }
                  onClick={() => onSelect(row.cell_id)}
                >
                  <td className="om-results__num">{row.rank}</td>
                  <th scope="row">
                    {/* Keyboard access; the click bubbles to the row handler. */}
                    <button
                      type="button"
                      className="om-results__select"
                      aria-pressed={selected}
                    >
                      <code>{row.cell_id}</code>
                    </button>
                  </th>
                  <td className="om-results__num">{formatValue(row.suitability_score)}</td>
                  {components.map((key) => (
                    <td className="om-results__num" key={key}>
                      {formatValue(row.key_components?.[key])}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
