/**
 * PlaceholderRegion — a single labelled, empty region of the App_Shell (S3-01a).
 *
 * This ticket stands up the four fixed MVP regions (analysis controls,
 * interactive map, ranked results, site detail/explanation) as EMPTY, labelled
 * boxes only. `PlaceholderRegion` renders one such box: a bordered container
 * with a heading naming the region and a plain "populated in a later ticket"
 * body.
 *
 * Scope boundary (Requirements 3.5, 8.1, 8.3):
 *   - NO data fetching (no fetch, no effects, no network calls).
 *   - NO typed service client (S3-01b).
 *   - NO decision logic — no scoring, normalisation, ranking, or exclusion
 *     arithmetic. The frontend obtains decision data only from the Backend_App
 *     over HTTP, and not in this ticket at all.
 *   - NO data-quality banner (S3-01b).
 *
 * The component is a pure, function-first render of its props — matching the
 * clarity-over-effects style of the rest of the shell (Requirement 1.3). It is
 * the fixed substrate that S3-02 … S3-06 populate without restructuring the app
 * (Requirement 8.3).
 */
import type { ReactNode } from "react";

/** Props for a single labelled placeholder region. */
export interface PlaceholderRegionProps {
  /** Human-readable heading naming the region (e.g. "Analysis controls"). */
  label: string;
  /**
   * Optional DOM id for the region's container. When provided it is also used
   * to associate the heading with the region for assistive technology.
   */
  id?: string;
  /**
   * Optional accessible label for the region landmark. Defaults to `label`
   * when omitted.
   */
  ariaLabel?: string;
  /**
   * Optional override for the placeholder body text. Defaults to a plain
   * "populated in a later ticket" message; no view logic is embedded here.
   */
  body?: ReactNode;
}

/** Default placeholder body — deliberately static, no decision content. */
const DEFAULT_BODY = "This region is populated in a later ticket.";

/**
 * Render one bordered, labelled empty region.
 *
 * Pure function of props: given the same props it always renders the same
 * markup. No side effects, no data access.
 */
export default function PlaceholderRegion({
  label,
  id,
  ariaLabel,
  body = DEFAULT_BODY,
}: PlaceholderRegionProps): JSX.Element {
  const headingId = id ? `${id}-heading` : undefined;
  return (
    <section
      className="om-region"
      id={id}
      aria-label={ariaLabel ?? label}
      aria-labelledby={headingId}
    >
      <h2 className="om-region__heading" id={headingId}>
        {label}
      </h2>
      <p className="om-region__body">{body}</p>
    </section>
  );
}
