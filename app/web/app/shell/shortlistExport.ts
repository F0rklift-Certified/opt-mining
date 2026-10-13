/**
 * Pure CSV serialiser for the ranked shortlist (S3-07 Shortlist Export).
 *
 * This module turns the shortlist the user already sees in `RankedShortlist`
 * into a CSV string. It performs no recomputation, no network call and no
 * engine call: it only serialises the `RankedRow[]` already held in UI state,
 * so an export is byte-for-byte a view of the current engine output.
 *
 * The output mirrors the on-screen panel exactly:
 *   - rows stay in served order (never re-sorted);
 *   - `rank` is the integer the engine served;
 *   - `suitability_score` and every component value are formatted with
 *     `toFixed(3)`, the same formatting `RankedShortlist.formatValue` uses;
 *   - a component the engine omitted for a row is an empty field (not "—",
 *     which is a display-only placeholder, and not 0, so the CSV stays
 *     machine-readable).
 *
 * Columns reuse the S1-11 Shortlist_CSV lowercase engine keys
 * (`rank,cell_id,suitability_score,…`). Confidence/centroid columns from the
 * S1-11 sidecar are not in `RankedRow`, so they are not emitted here. One
 * column per component key is added in first-served order (the same union
 * `RankedShortlist.componentKeys` builds), followed by an `eligible` column.
 *
 * Eligibility is a constant `true`: `GET /runs/{id}/results` returns only the
 * eligible ranked cells (exclusions come from a separate endpoint), so every
 * row the shortlist shows — and therefore every exported row — is eligible by
 * construction. There is no per-row eligibility source to read.
 */
import type { RankedRow } from "../api/decision-service";

/**
 * Preliminary-screening disclaimer, emitted as a leading `#` metadata line
 * above the column header row (AC12 / Preliminary_Disclaimer).
 *
 * The S1-11 Shortlist_CSV does not carry the disclaimer in-file (it lives in
 * the shortlist metadata sidecar), and the S2-08 HTTP contract does not surface
 * it, so this mirrors the exact S1-11 sidecar wording as a frontend constant.
 * If a future ticket serves the disclaimer over the API, swap this constant for
 * the served value.
 */
export const PRELIMINARY_DISCLAIMER =
  "This shortlist is a preliminary screening output. It indicates where to look next; it is not a site approval, an engineering assessment, or a final recommendation.";

/** Component keys in first-served order — matches `RankedShortlist.componentKeys`. */
function componentKeys(rows: RankedRow[]): string[] {
  const keys = new Set<string>();
  for (const row of rows) {
    for (const key of Object.keys(row.key_components ?? {})) keys.add(key);
  }
  return Array.from(keys);
}

/** `toFixed(3)` formatting, mirroring the panel; missing value → empty field. */
function formatNumber(value: number | undefined): string {
  return value === undefined ? "" : value.toFixed(3);
}

/**
 * RFC-4180 field escaping: a field containing a comma, double-quote, CR or LF
 * is wrapped in double quotes and its embedded double-quotes are doubled.
 */
function escapeField(field: string): string {
  if (/[",\r\n]/.test(field)) {
    return `"${field.replace(/"/g, '""')}"`;
  }
  return field;
}

/** Join one record's already-stringified fields into an RFC-4180 CSV row. */
function toRecord(fields: string[]): string {
  return fields.map(escapeField).join(",");
}

/**
 * Serialise the current shortlist to a CSV string.
 *
 * Shape: a leading `#`-prefixed disclaimer metadata line, then the column
 * header row, then one record per row in input order. Records are joined with
 * CRLF (`\r\n`) per RFC-4180. An empty shortlist yields the disclaimer line and
 * the base header row only (no component columns, no data rows).
 */
export function serializeShortlistCsv(
  rows: RankedRow[],
  disclaimer: string,
): string {
  const components = componentKeys(rows);
  const lines: string[] = [];

  // Disclaimer metadata line. It is not escaped as a CSV field: it is a
  // comment line, read by humans, that a CSV reader skips via the `#` prefix.
  lines.push(`# ${disclaimer}`);

  lines.push(toRecord(["rank", "cell_id", "suitability_score", ...components, "eligible"]));

  for (const row of rows) {
    lines.push(
      toRecord([
        String(row.rank),
        row.cell_id,
        formatNumber(row.suitability_score),
        ...components.map((key) => formatNumber(row.key_components?.[key])),
        "true",
      ]),
    );
  }

  return lines.join("\r\n");
}
