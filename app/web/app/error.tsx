"use client";
/**
 * App Router error boundary for the single page (QA F-14 backstop).
 *
 * Service responses are shape-checked in `api/validate.ts` and reported in the
 * shell's own alert regions, so this should never show in normal use. It
 * exists so that any rendering fault the checks miss replaces the page with a
 * plain message and a retry, instead of a blank screen.
 */
import { useEffect } from "react";

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}): JSX.Element {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <main className="om-fatal">
      <p className="om-service-error" role="alert">
        Something went wrong while showing the results. No analysis data was changed.
      </p>
      <button type="button" onClick={reset}>
        Try again
      </button>
    </main>
  );
}
