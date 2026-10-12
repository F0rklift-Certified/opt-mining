"use client";

/** Service-backed shell for S3-01b/S3-02/S3-04. All decision values arrive over HTTP. */
import { useCallback, useEffect, useRef, useState } from "react";

import AnalysisControls, {
  BASELINE_CRITERIA,
  DEFAULT_OPTION_ID,
  WEIGHTING_OPTIONS,
} from "./AnalysisControls";
import {
  createDecisionServiceClient,
  type Criterion,
  type DataQualityStatus,
  type DecisionService,
  type ExcludedRow,
  type RankedRow,
  type RunHandle,
  type RunRequest,
  type ScenarioComparison as ScenarioComparisonResult,
  type ScenarioComparisonRequest,
  type SiteDetail,
} from "../api/decision-service";
import CellMap from "./CellMap";
import DataQualityBanner from "./DataQualityBanner";
import PlaceholderRegion from "./PlaceholderRegion";
import RankedShortlist from "./RankedShortlist";
import ScenarioComparison, { CUSTOM_SIDE } from "./ScenarioComparison";
import type { SelectSite, SiteSelection } from "./siteSelection";

/**
 * The named S2-07 weighting presets available to the scenario-comparison UI.
 * `compare_scenarios` only accepts named scenario keys, so the editable
 * Baseline (which runs via explicit weights, not a scenario key) is excluded.
 */
const COMPARISON_PRESETS = WEIGHTING_OPTIONS.filter((option) => !option.editable);

/**
 * Seed weights for a Custom comparison side. The six frozen criteria and their
 * directions are fixed; the user adjusts only the weights, starting from a
 * sensible preset (the first named preset, or the Baseline if no preset is
 * available). This is a plain copy of a known-valid criteria set — no decision
 * math — so the Custom editor opens on real values rather than blanks.
 */
const CUSTOM_SEED_CRITERIA: Criterion[] = (
  COMPARISON_PRESETS[0]?.criteria ?? BASELINE_CRITERIA
).map((criterion) => ({ ...criterion }));

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

/** Build the `run_analysis` request for the given weighting option (S3-02). */
function buildRunRequest(optionId: string, baselineCriteria: Criterion[]): RunRequest {
  const option = WEIGHTING_OPTIONS.find((candidate) => candidate.id === optionId);
  if (option?.editable) {
    return { weights: { criteria: baselineCriteria } };
  }
  return { scenario: optionId };
}

/** Render the fixed shell and populate it exclusively with service output. */
export default function AppShell({ service: injectedService }: AppShellProps = {}): JSX.Element {
  const [optionId, setOptionId] = useState(DEFAULT_OPTION_ID);
  const [baselineCriteria, setBaselineCriteria] = useState<Criterion[]>(BASELINE_CRITERIA);
  const [engine, setEngine] = useState<EngineView | null>(null);
  const [engineError, setEngineError] = useState<string | null>(null);
  const [quality, setQuality] = useState<DataQualityStatus | null>(null);
  const [qualityError, setQualityError] = useState<string | null>(null);
  const [engineLoading, setEngineLoading] = useState(true);
  const [qualityLoading, setQualityLoading] = useState(true);
  // One selected site shared by the shortlist, the map and the detail view.
  const [selection, setSelection] = useState<SiteSelection | null>(null);
  const [detail, setDetail] = useState<SiteDetailView | null>(null);
  // The shared client exposed to CellMap (same object held in apiRef); null
  // until the client is built (or if building it fails for lack of config).
  const [service, setService] = useState<DecisionService | null>(null);
  // Scenario-comparison (S3-06): two chosen preset keys and the engine result.
  const [scenarioA, setScenarioA] = useState<string>(COMPARISON_PRESETS[0]?.id ?? "");
  const [scenarioB, setScenarioB] = useState<string>(
    COMPARISON_PRESETS[1]?.id ?? COMPARISON_PRESETS[0]?.id ?? "",
  );
  const [comparison, setComparison] = useState<ScenarioComparisonResult | null>(null);
  const [comparisonError, setComparisonError] = useState<string | null>(null);
  const [comparisonLoading, setComparisonLoading] = useState(false);
  // Per-side Custom weight sets, seeded from a preset so the editor opens on
  // real values. Only used when the matching side is set to CUSTOM_SIDE.
  const [customCriteriaA, setCustomCriteriaA] = useState<Criterion[]>(CUSTOM_SEED_CRITERIA);
  const [customCriteriaB, setCustomCriteriaB] = useState<Criterion[]>(CUSTOM_SEED_CRITERIA);
  // Rectangle-selected cell ids scoping the comparison TABLE (S3-06 cell
  // selection). A DISPLAY FILTER local to the comparison feature — it never
  // alters the compare request, re-ranks, or touches the shared SiteSelection.
  // `null` means no rectangle selection (table shows all engine rows).
  const [comparisonCellIds, setComparisonCellIds] = useState<string[] | null>(null);

  // Stable across renders; set once the client is ready (or fails to build).
  const apiRef = useRef<DecisionService | null>(null);
  // Guards a stale response (e.g. the mount run) from overwriting a later one
  // (e.g. a Run-button click) should they ever resolve out of order.
  const requestIdRef = useRef(0);
  // Independent staleness guard for the scenario-comparison request.
  const comparisonRequestIdRef = useRef(0);

  const runWith = useCallback(async (request: RunRequest) => {
    const api = apiRef.current;
    if (!api) return;
    const requestId = ++requestIdRef.current;
    // A new run clears any prior selection; it reopens on the new run's rank 1.
    setSelection(null);
    // A new run invalidates any comparison-table cell selection (the cells it
    // referred to belong to the previous run).
    setComparisonCellIds(null);
    setEngineLoading(true);
    setEngineError(null);
    try {
      const run = await api.runAnalysis(request);
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
      api = injectedService ?? createDecisionServiceClient();
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
    setService(api);

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
    void runWith(buildRunRequest(DEFAULT_OPTION_ID, BASELINE_CRITERIA));
    return () => { active = false; };
  }, [injectedService, runWith]);

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
    void runWith(buildRunRequest(optionId, baselineCriteria));
  }, [runWith, optionId, baselineCriteria]);

  // Fetch the S2-07 scenario comparison for the chosen pair (S3-06). All
  // comparison math is server-side; this only shapes each side as a scenario
  // key OR an explicit weights configuration and renders the returned
  // ranks/deltas via the single shared client. A Custom side sends weights; a
  // preset side sends its scenario key — never both for the same side, so the
  // engine's exactly-one-of-per-side guard stays satisfied.
  const handleCompareScenarios = useCallback(() => {
    const api = apiRef.current;
    if (!api) return;
    // Two different presets, or any Custom side, are comparable; two identical
    // presets are not.
    const samePreset = scenarioA === scenarioB && scenarioA !== CUSTOM_SIDE;
    if (samePreset) return;
    const request: ScenarioComparisonRequest =
      scenarioA === CUSTOM_SIDE
        ? { weights_a: { criteria: customCriteriaA } }
        : { scenario_a: scenarioA };
    if (scenarioB === CUSTOM_SIDE) {
      request.weights_b = { criteria: customCriteriaB };
    } else {
      request.scenario_b = scenarioB;
    }
    const requestId = ++comparisonRequestIdRef.current;
    // A fresh comparison supersedes any prior rectangle selection, so a stale
    // selection never scopes a different pair's results.
    setComparisonCellIds(null);
    setComparisonLoading(true);
    setComparisonError(null);
    api.compareScenarios(request).then(
      (result) => {
        if (comparisonRequestIdRef.current === requestId) {
          setComparison(result);
          setComparisonLoading(false);
        }
      },
      (error: unknown) => {
        if (comparisonRequestIdRef.current === requestId) {
          setComparisonError(errorMessage(error));
          setComparisonLoading(false);
        }
      },
    );
  }, [scenarioA, scenarioB, customCriteriaA, customCriteriaB]);

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
              optionId={optionId}
              onOptionChange={setOptionId}
              baselineCriteria={baselineCriteria}
              onBaselineCriteriaChange={setBaselineCriteria}
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
          body={
            service
              ? (
                  <CellMap
                    runId={engine?.run.run_id ?? null}
                    service={service}
                    onSelectCell={(sel) => handleSelectSite(sel.cell_id)}
                  />
                )
              : loadingText ?? "No engine output is available."
          }
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
        <PlaceholderRegion
          id="region-scenario-comparison"
          label="Scenario comparison"
          ariaLabel="Scenario comparison"
          body={
            <ScenarioComparison
              presets={COMPARISON_PRESETS}
              scenarioA={scenarioA}
              onScenarioAChange={setScenarioA}
              scenarioB={scenarioB}
              onScenarioBChange={setScenarioB}
              customCriteriaA={customCriteriaA}
              onCustomCriteriaAChange={setCustomCriteriaA}
              customCriteriaB={customCriteriaB}
              onCustomCriteriaBChange={setCustomCriteriaB}
              onCompare={handleCompareScenarios}
              loading={comparisonLoading}
              error={comparisonError}
              comparison={comparison}
              runId={engine?.run.run_id ?? null}
              service={service}
              selectedCellIds={comparisonCellIds}
              onSelectedCellIdsChange={setComparisonCellIds}
            />
          }
        />
      </div>
    </div>
  );
}
