"use client";

/** Service-backed shell for S3-01b/S3-02/S3-04. All decision values arrive over HTTP. */
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
import RankedShortlist from "./RankedShortlist";
import type { SelectSite, SiteSelection } from "./siteSelection";

interface EngineView {
  run: RunHandle;
  results: RankedRow[];
  exclusions: ExcludedRow[];
}

/** Site detail (or its failure), tagged with the selection it was loaded for. */
type SiteDetailView =
  | { selection: SiteSelection; site: SiteDetail; error?: undefined }
  | { selection: SiteSelection; site?: undefined; error: string };

export interface AppShellProps {
  /** Test seam; production creates the shared client from the configured URL. */
  service?: DecisionService;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Unexpected service error.";
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
  // One selected site shared by the shortlist, the map and the detail view.
  const [selection, setSelection] = useState<SiteSelection | null>(null);
  const [detail, setDetail] = useState<SiteDetailView | null>(null);

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
      if (requestIdRef.current === requestId) {
        setEngine({ run, results, exclusions });
        // Each run opens on its engine rank 1 site.
        const first = results[0];
        setSelection(first ? { runId: run.run_id, cellId: first.cell_id } : null);
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

  // Load the detail of whichever site is selected. Changing the selection
  // deactivates the previous request, so a slow response for an earlier site
  // can never replace the detail of the site now selected.
  useEffect(() => {
    const api = apiRef.current;
    if (!api || !selection) return;
    let active = true;
    api.getSiteDetail(selection.runId, selection.cellId).then(
      (site) => { if (active) setDetail({ selection, site }); },
      (error: unknown) => { if (active) setDetail({ selection, error: errorMessage(error) }); },
    );
    return () => { active = false; };
  }, [selection]);

  const handleRun = useCallback(() => {
    void runScenario(scenario);
  }, [runScenario, scenario]);

  const activeRunId = engine?.run.run_id ?? null;
  const handleSelectSite = useCallback<SelectSite>((cellId) => {
    if (!activeRunId) return;
    setSelection((current) =>
      current?.runId === activeRunId && current.cellId === cellId
        ? current
        : { runId: activeRunId, cellId },
    );
  }, [activeRunId]);

  // Only show detail loaded for the current selection, never a previous one.
  const selectedDetail = detail?.selection === selection ? detail : null;

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
            <>
              <p>{engine.results.length} ranked cells loaded from the engine; map rendering follows in S3-03a.</p>
              {selection && <p>Selected site: <code>{selection.cellId}</code></p>}
            </>
          ) : loadingText ?? "No engine output is available."}
        />
        <PlaceholderRegion
          id="region-ranked-results"
          label="Ranked results"
          ariaLabel="Ranked results"
          body={engine ? (
            <RankedShortlist
              rows={engine.results}
              selectedCellId={selection?.cellId ?? null}
              onSelect={handleSelectSite}
            />
          ) : loadingText ?? "No ranked results are available."}
        />
        <PlaceholderRegion
          id="region-site-detail"
          label="Site detail / explanation"
          ariaLabel="Site detail and explanation"
          body={selectedDetail?.error ? (
            <p className="om-service-error" role="alert">Site detail unavailable: {selectedDetail.error}</p>
          ) : engine && selectedDetail?.site ? (
            <dl className="om-facts">
              <div><dt>Site ID</dt><dd><code>{selectedDetail.site.cell_id}</code></dd></div>
              <div><dt>Rank</dt><dd>{selectedDetail.site.rank}</dd></div>
              <div><dt>Suitability</dt><dd>{selectedDetail.site.suitability_score?.toFixed(3) ?? "Not scored"}</dd></div>
              <div><dt>Eligible</dt><dd>{selectedDetail.site.eligible ? "Yes" : "No"}</dd></div>
              <div><dt>Excluded cells in run</dt><dd>{engine.exclusions.length.toLocaleString()}</dd></div>
            </dl>
          ) : selection ? (
            "Loading site detail…"
          ) : loadingText ?? "No site detail is available."}
        />
      </div>
    </div>
  );
}
