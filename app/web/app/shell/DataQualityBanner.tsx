/** Render the S2-02 status exactly as returned by `get_data_quality`. */
import type { DataQualityStatus } from "../api/decision-service";

export interface DataQualityBannerProps {
  status: DataQualityStatus | null;
  error: string | null;
  loading: boolean;
}

export default function DataQualityBanner({
  status,
  error,
  loading,
}: DataQualityBannerProps): JSX.Element {
  if (loading) {
    return (
      <section className="om-quality om-quality--loading" role="status">
        Checking the frozen dataset quality status…
      </section>
    );
  }

  if (error) {
    return (
      <section className="om-quality om-quality--failed" role="alert">
        <strong>Data-quality status is unavailable.</strong> {error}
      </section>
    );
  }

  if (!status) return <></>;

  if (status.passed) {
    return (
      <section className="om-quality om-quality--passed" role="status">
        <strong>Data-quality checks passed.</strong> The decision service
        reported {status.checks?.length ?? 0} checks for the frozen dataset.
      </section>
    );
  }

  const failedChecks = (status.checks ?? []).filter((check) => !check.passed);
  return (
    <section className="om-quality om-quality--failed" role="alert">
      <strong>Data-quality warning.</strong> The decision service flagged the
      frozen dataset. Review the failed checks before relying on rankings.
      {failedChecks.length > 0 && (
        <ul className="om-quality__checks">
          {failedChecks.map((check) => (
            <li key={check.name}>
              {check.name}: expected {check.expected}; observed {check.observed}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
