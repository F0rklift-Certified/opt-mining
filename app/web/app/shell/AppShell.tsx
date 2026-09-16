"use client";

/** Service-backed shell for S3-01b/S3-02. All decision values arrive over HTTP. */
import { useCallback, useEffect, useRef, useState } from "react";

import AnalysisControls, { DEFAULT_SCENARIO } from "./AnalysisControls";
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
  const [scenario, setScenario] = useState(DEFAULT_SCENARIO);
  const [engine, setEngine] = useState<EngineView | null>(null);
  const [engineError, setEngineError] = useState<string | null>(null);
  const [quality, setQuality] = useState<DataQualityStatus | null>(null);
  const [qualityError, setQualityError] = useState<string | null>(null);
  const [engineLoading, setEngineLoading] = useState(true);
  const [qualityLoading, setQualityLoading] = useState(true);

  // Stable across renders; set once the client is ready (or fails to build).
  const apiRef = useRef<DecisionService | null>(null);
  // Guards a stale response (e.g. the mount run) from overwriting a later one
  // (e.g. a Run-button click) should they ever resolve out of order.
  const requestIdRef = useRef(0);

  const runScenario = useCallback(async (scenarioId: string) => {
    const api = apiRef.current;
    if (!api) return;
    const requestId = ++requestIdRef.current;
    setEngineLoading(true);
    setEngineError(null);
    try {
      const run = await api.runAnalysis({ scenario: scenarioId });
      const [results, exclusions] = await Promise.all([
        api.getRankedResults(run.run_id, { top_n: 10 }),
        api.getExclusions(run.run_id),
      ]);
      const first = results[0];
      const site = first
        ? await api.getSiteDetail(run.run_id, first.cell_id)
        : null;
      if (requestIdRef.current === requestId) {
        setEngine({ run, results, exclusions, site });
      }
    } catch (error) {
      if (requestIdRef.current === requestId) {
        setEngineError(errorMessage(error));
      }
    } finally {
      if (requestIdRef.current === requestId) {
        setEngineLoading(false);
      }
    }
  }, []);

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
    apiRef.current = api;

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

    void loadQuality();
    void runScenario(DEFAULT_SCENARIO);
    return () => { active = false; };
  }, [service, runScenario]);

  const handleRun = useCallback(() => {
    void runScenario(scenario);
  }, [runScenario, scenario]);

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
          body={
            <AnalysisControls
              scenario={scenario}
              onScenarioChange={setScenario}
              onRun={handleRun}
              running={engineLoading}
              activeRun={engine?.run ?? null}
            />
          }
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
