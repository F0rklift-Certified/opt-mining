"use client";

/** Service-backed shell for S3-01b. All decision values arrive over HTTP. */
import { useEffect, useState } from "react";

import {
  createDecisionServiceClient,
  type DataQualityStatus,
  type DecisionService,
  type ExcludedRow,
  type RankedRow,
  type RunHandle,
  type SiteDetail,
} from "../api/decision-service";
import DataQualityBanner from "./DataQualityBanner";
import PlaceholderRegion from "./PlaceholderRegion";

interface EngineView {
  run: RunHandle;
  results: RankedRow[];
  exclusions: ExcludedRow[];
  site: SiteDetail | null;
}

export interface AppShellProps {
  /** Test seam; production creates the shared client from the configured URL. */
  service?: DecisionService;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Unexpected service error.";
}

function RankedResults({ rows }: { rows: RankedRow[] }): JSX.Element {
  if (rows.length === 0) return <p>No eligible cells were returned.</p>;
  return (
    <table className="om-results">
      <thead>
        <tr>
          <th scope="col">Rank</th>
          <th scope="col">Cell</th>
          <th scope="col">Suitability</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.cell_id}>
            <td>{row.rank}</td>
            <td><code>{row.cell_id}</code></td>
            <td>{row.suitability_score.toFixed(3)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Render the fixed shell and populate it exclusively with service output. */
export default function AppShell({ service }: AppShellProps = {}): JSX.Element {
  const [engine, setEngine] = useState<EngineView | null>(null);
  const [engineError, setEngineError] = useState<string | null>(null);
  const [quality, setQuality] = useState<DataQualityStatus | null>(null);
  const [qualityError, setQualityError] = useState<string | null>(null);
  const [engineLoading, setEngineLoading] = useState(true);
  const [qualityLoading, setQualityLoading] = useState(true);

  useEffect(() => {
    let active = true;
    let api: DecisionService;
    try {
      api = service ?? createDecisionServiceClient();
    } catch (error) {
      if (active) {
        const message = errorMessage(error);
        setEngineError(message);
        setQualityError(message);
        setEngineLoading(false);
        setQualityLoading(false);
      }
      return () => { active = false; };
    }

    async function loadQuality(): Promise<void> {
      try {
        const status = await api.getDataQuality();
        if (active) setQuality(status);
      } catch (error) {
        if (active) setQualityError(errorMessage(error));
      } finally {
        if (active) setQualityLoading(false);
      }
    }

    async function loadEngine(): Promise<void> {
      try {
        const run = await api.runAnalysis({ scenario: "wind_led" });
        const [results, exclusions] = await Promise.all([
          api.getRankedResults(run.run_id, { top_n: 10 }),
          api.getExclusions(run.run_id),
        ]);
        const first = results[0];
        const site = first
          ? await api.getSiteDetail(run.run_id, first.cell_id)
          : null;
        if (active) setEngine({ run, results, exclusions, site });
      } catch (error) {
        if (active) setEngineError(errorMessage(error));
      } finally {
        if (active) setEngineLoading(false);
      }
    }

    void loadQuality();
    void loadEngine();
    return () => { active = false; };
  }, [service]);

  const loadingText = engineLoading ? "Loading decision-service output…" : null;
  const failureText = engineError ? `Decision service unavailable: ${engineError}` : null;

  return (
    <div className="om-shell">
      <DataQualityBanner
        status={quality}
        error={qualityError}
        loading={qualityLoading}
      />
      {failureText && <p className="om-service-error" role="alert">{failureText}</p>}
      <div className="om-shell__grid">
        <PlaceholderRegion
          id="region-analysis-controls"
          label="Analysis controls"
          ariaLabel="Analysis controls"
          body={engine ? (
            <dl className="om-facts">
              <div><dt>Scenario</dt><dd>{engine.run.scenario}</dd></div>
              <div><dt>Run</dt><dd><code>{engine.run.run_id}</code></dd></div>
              <div><dt>Weights</dt><dd><code>{engine.run.weights_id}</code></dd></div>
            </dl>
          ) : loadingText ?? "No run is available."}
        />
        <PlaceholderRegion
          id="region-interactive-map"
          label="Interactive map"
          ariaLabel="Interactive map"
          body={engine ? (
            <p>{engine.results.length} ranked cells loaded from the engine; map rendering follows in S3-03a.</p>
          ) : loadingText ?? "No engine output is available."}
        />
        <PlaceholderRegion
          id="region-ranked-results"
          label="Ranked results"
          ariaLabel="Ranked results"
          body={engine ? <RankedResults rows={engine.results} /> : loadingText ?? "No ranked results are available."}
        />
        <PlaceholderRegion
          id="region-site-detail"
          label="Site detail / explanation"
          ariaLabel="Site detail and explanation"
          body={engine?.site ? (
            <dl className="om-facts">
              <div><dt>Cell</dt><dd><code>{engine.site.cell_id}</code></dd></div>
              <div><dt>Rank</dt><dd>{engine.site.rank}</dd></div>
              <div><dt>Suitability</dt><dd>{engine.site.suitability_score?.toFixed(3) ?? "Not scored"}</dd></div>
              <div><dt>Eligible</dt><dd>{engine.site.eligible ? "Yes" : "No"}</dd></div>
              <div><dt>Excluded cells in run</dt><dd>{engine.exclusions.length.toLocaleString()}</dd></div>
            </dl>
          ) : loadingText ?? "No site detail is available."}
        />
      </div>
    </div>
  );
}
