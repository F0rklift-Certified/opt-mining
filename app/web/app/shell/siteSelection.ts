/**
 * Site-selection contract shared by the ranked shortlist (S3-04), the map
 * (S3-03b) and the site-detail view (S3-05).
 *
 * A selection names one engine cell inside one engine run, so the table, the
 * map and the detail view always point at the same S2-08 output. Either the
 * table or the map may emit a selection; both highlight whichever cell is
 * currently selected.
 */

export interface SiteSelection {
  /** The engine run the selected cell belongs to. */
  runId: string;
  /** The engine `cell_id` (the Site ID shown in the UI). */
  cellId: string;
}

/** Callback a view invokes to select a site of the active run. */
export type SelectSite = (cellId: string) => void;
