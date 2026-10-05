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
import ScreeningMap from "./ScreeningMap";
import SiteExplanation from "./SiteExplanation";
import ScenarioPanel from "./ScenarioPanel";
import type { SelectSite, SiteSelection } from "./siteSelection";

interface EngineView {
  run: RunHandle;
  results: RankedRow[];
  allResults: RankedRow[];
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
export default function AppShell({ service }: AppShellProps = {}): React.JSX.Element {
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
  const [topN, setTopN] = useState("10");
  const [minimumScore, setMinimumScore] = useState("");
  const [filterApplied, setFilterApplied] = useState(false);
  const [filterLoading, setFilterLoading] = useState(false);
  const filterIdRef = useRef(0);

  // Stable across renders; set once the client is ready (or fails to build).
  const apiRef = useRef<DecisionService | null>(null);
  // Guards a stale response (e.g. the mount run) from overwriting a later one
  // (e.g. a Run-button click) should they ever resolve out of order.
  const requestIdRef = useRef(0);

  const runScenario = useCallback(async (scenarioId: string) => {
    const api = apiRef.current;
    if (!api) return;
    const requestId = ++requestIdRef.current;
    ++filterIdRef.current;
    setFilterLoading(false);
    setEngineLoading(true);
    setEngineError(null);
    try {
      const run = await api.runAnalysis({ scenario: scenarioId });
      const [results, exclusions, allResults] = await Promise.all([
        api.getRankedResults(run.run_id, { top_n: 10 }),
        api.getExclusions(run.run_id),
        api.getRankedResults(run.run_id),
      ]);
      if (requestIdRef.current === requestId) {
        setEngine({ run, results, exclusions, allResults });
        setTopN("10"); setMinimumScore(""); setFilterApplied(false);
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

  async function applyFilters(): Promise<void> {
    const api = apiRef.current;
    if (!api || !engine) return;
    const runId = engine.run.run_id;
    const requestId = ++filterIdRef.current;
    const runRequestId = requestIdRef.current;
    setFilterLoading(true); setEngineError(null);
    try {
      const results = await api.getRankedResults(runId, {
        top_n: topN === "" ? null : Number(topN),
        min_score: minimumScore === "" ? null : Number(minimumScore),
      });
      if (requestId === filterIdRef.current && runRequestId === requestIdRef.current) {
        setEngine((current) => current?.run.run_id === runId ? { ...current, results } : current);
        setFilterApplied(true);
      }
    } catch (error) {
      if (requestId === filterIdRef.current) setEngineError(errorMessage(error));
    } finally { if (requestId === filterIdRef.current) setFilterLoading(false); }
  }

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
            <ScreeningMap rows={filterApplied ? engine.results : engine.allResults}
              exclusions={engine.exclusions} selectedCellId={selection?.cellId ?? null}
              onSelect={handleSelectSite} />
          ) : loadingText ?? "No engine output is available."}
        />
        <PlaceholderRegion
          id="region-ranked-results"
          label="Ranked results"
          ariaLabel="Ranked results"
          body={engine ? (
            <>
            <p>{engine.allResults.length.toLocaleString()} eligible cells. The initial map shows all eligible cells; the shortlist opens at top 10. Applying display filters narrows both without rerunning analysis.</p>
            <form className="om-toolbar" onSubmit={(e) => { e.preventDefault(); void applyFilters(); }}>
              <label>Top N <input type="number" min="1" step="1" value={topN} onChange={(e) => setTopN(e.target.value)} /></label>
              <label>Minimum score <input type="number" min="0" max="1" step="0.01" value={minimumScore} onChange={(e) => setMinimumScore(e.target.value)} /></label>
              <button disabled={engineLoading || filterLoading} type="submit">{filterLoading ? "Filtering…" : "Apply display filters"}</button>
            </form>
            <RankedShortlist
              rows={engine.results}
              selectedCellId={selection?.cellId ?? null}
              onSelect={handleSelectSite}
            />
            <details><summary>Inspect exclusions ({engine.exclusions.length.toLocaleString()} cells)</summary>
              <p>All exclusions are shown on the map and searchable by cell ID. First 20 records:</p>
              <ul>{engine.exclusions.slice(0, 20).map((row) => <li key={row.cell_id}>
                <button onClick={() => handleSelectSite(row.cell_id)}>Inspect excluded {row.cell_id}</button> — {row.reason_text}
              </li>)}</ul>
            </details>
            </>
          ) : loadingText ?? "No ranked results are available."}
        />
        <PlaceholderRegion
          id="region-site-detail"
          label="Site detail / explanation"
          ariaLabel="Site detail and explanation"
          body={selectedDetail?.error ? (
            <p className="om-service-error" role="alert">Site detail unavailable: {selectedDetail.error}</p>
          ) : engine && selectedDetail?.site ? (
            <SiteExplanation site={selectedDetail.site} excludedCount={engine.exclusions.length} />
          ) : selection ? (
            "Loading site detail…"
          ) : loadingText ?? "No site detail is available."}
        />
      </div>
      <div className="om-region"><ScenarioPanel service={apiRef.current} selectedCellId={selection?.cellId ?? null} /></div>
      <div className="om-region">
        <h2>Validation and screening limits</h2>
        <p>The banner reports the actual S2-02 input checks. Missing context such as connection-point geometry stays flagged. Default weights are screening preferences, not forecasts or project approvals.</p>
        <p>External GA operational wind-farm checks are recorded in docs/release/rehearsal.json and the release demo script. An unfavourable reference result is evidence to investigate, not a reason to retune weights until it passes.</p>
      </div>
    </div>
  );
}
