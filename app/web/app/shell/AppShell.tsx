/**
 * AppShell — the fixed four-region layout of the Frontend_App (S3-01a, task 6.4).
 *
 * This component lays out the four MVP `PlaceholderRegion`s in a fixed CSS-grid
 * (Requirements 3.1–3.4):
 *   1. Analysis controls
 *   2. Interactive map
 *   3. Ranked results
 *   4. Site detail / explanation
 *
 * It also surfaces the configured backend base URL (`NEXT_PUBLIC_API_BASE_URL`)
 * as a static on-screen config line so the env plumbing is proven end-to-end
 * (Requirement 4.3). The value is read ONLY from `process.env` — no host address
 * is hard-coded — and it is displayed only; NO request is made in this ticket
 * (calling the backend is S3-01b).
 *
 * Scope boundary (Requirements 3.5, 8.1, 8.3):
 *   - NO data fetching (no fetch, no effects, no network calls).
 *   - NO typed service client (S3-01b).
 *   - NO decision logic — no scoring, normalisation, ranking, or exclusion.
 *   - NO data-quality banner (S3-01b).
 *
 * The four regions are the fixed, empty substrate that S3-02 … S3-06 populate
 * without restructuring the app (Requirement 8.3).
 */
import PlaceholderRegion from "./PlaceholderRegion";

/**
 * The backend base URL, read from the environment only (Requirement 4.3).
 *
 * `NEXT_PUBLIC_`-prefixed variables are inlined by Next.js at build time. When
 * the variable is unset we surface a plain "(not configured)" marker rather than
 * a hard-coded host address, so no literal host ever appears in source.
 */
const API_BASE_URL: string =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "(not configured)";

/**
 * Render the fixed four-region application shell.
 *
 * Pure, function-first render (Requirement 1.3): a CSS-grid of four labelled
 * `PlaceholderRegion`s plus a static config line. No side effects, no data
 * access.
 */
export default function AppShell(): JSX.Element {
  return (
    <div className="om-shell">
      <p className="om-shell__config">
        API base URL:{" "}
        <code className="om-shell__config-value">{API_BASE_URL}</code>
      </p>
      <div className="om-shell__grid">
        <PlaceholderRegion
          id="region-analysis-controls"
          label="Analysis controls"
          ariaLabel="Analysis controls"
        />
        <PlaceholderRegion
          id="region-interactive-map"
          label="Interactive map"
          ariaLabel="Interactive map"
        />
        <PlaceholderRegion
          id="region-ranked-results"
          label="Ranked results"
          ariaLabel="Ranked results"
        />
        <PlaceholderRegion
          id="region-site-detail"
          label="Site detail / explanation"
          ariaLabel="Site detail and explanation"
        />
      </div>
    </div>
  );
}
