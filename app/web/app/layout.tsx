/**
 * Global App Router layout for the Opt-Mining Frontend_App (S3-01a).
 *
 * This is the root layout that wraps the whole application. It renders a fixed
 * global title bar and the page content beneath it.
 *
 * Requirement 1.2 — the region is FIXED to NSW for the MVP. The region is shown
 * as a static label in the title bar; there is deliberately NO region selector
 * (no dropdown, no toggle, no control) anywhere in this shell.
 *
 * Requirement 1.3 — function-first, clarity over visual effects: a plain title
 * bar, a static region label, and no decorative animation or embellishment.
 *
 * The four placeholder regions and the CSS-grid app shell are added by the
 * AppShell component / page (task 6.3–6.4); this file only provides the global
 * frame.
 */
import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

/** The MVP is fixed to a single region (Requirement 1.2). */
const FIXED_REGION = "NSW";

export const metadata: Metadata = {
  title: "Opt-Mining — Site Suitability (NSW)",
  description:
    "Decision-support shell for renewable site suitability in NSW. " +
    "Function-first application shell (S3-01a).",
};

export default function RootLayout({
  children,
}: {
  children: ReactNode;
}): JSX.Element {
  return (
    <html lang="en">
      <body>
        <header className="om-titlebar">
          <h1 className="om-titlebar__title">
            Opt-Mining — Site Suitability
          </h1>
          {/* Fixed region label — NOT a selector (Requirement 1.2). */}
          <span
            className="om-titlebar__region"
            aria-label={`Region (fixed): ${FIXED_REGION}`}
          >
            Region: {FIXED_REGION}
          </span>
        </header>
        <main className="om-main">{children}</main>
      </body>
    </html>
  );
}
