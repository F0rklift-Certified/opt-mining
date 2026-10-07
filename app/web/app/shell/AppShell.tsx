"use client";

/** Service-backed shell for S3-01b/S3-02. All decision values arrive over HTTP. */
import { useCallback, useEffect, useRef, useState } from "react";

import AnalysisControls, {
  BASELINE_CRITERIA,
  DEFAULT_OPTION_ID,
  WEIGHTING_OPTIONS,
} from "./AnalysisControls";
import {
  createDecisionServiceClient,
  type CellSelection,
  type Criterion,
  type DataQualityStatus,
  type DecisionService,
  type ExcludedRow,
  type RankedResultsFilter,
  type RankedRow,
  type RunHandle,
  type RunRequest,
  type SiteDetail,
} from "../api/decision-service";
import CellMap from "./CellMap";
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

/**
 * The default display filter — the top ten ranked sites — matching the S3-03a
 * ranked-results fetch. A display query over fixed engine output: changing it
 * only re-queries `getRankedResults`, never re-runs scoring/normalisation.
 */
const DEFAULT_FILTER: RankedResultsFilter = { top_n: 10 };

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Unexpected service error.";
}

/**
 * Project a ranked-table row onto the shared {@link CellSelection} contract —
 * the SAME shape a map click produces (S3-03b). A `RankedRow` is always an
 * eligible cell, so `eligible` is true and both score and rank are present.
 */
function selectionFromRow(row: RankedRow): CellSelection {
  return {
    cell_id: row.cell_id,
    eligible: true,
    suitability_score: row.suitability_score,
    rank: row.rank,
  };
}

function RankedResults({
  rows,
  onSelect,
}: {
  rows: RankedRow[];
  onSelect: (selection: CellSelection) => void;
}): JSX.Element {
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
            <td>
              <button
                type="button"
                className="om-results__select"
                onClick={() => onSelect(selectionFromRow(row))}
              >
                <code>{row.cell_id}</code>
              </button>
            </td>
            <td>{row.suitability_score.toFixed(3)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/**
 * The display-filter control (S3-03b): a top-N and a minimum-suitability input
 * that narrow ONLY the ranked display. Each change hands the new
 * {@link RankedResultsFilter} up to AppShell, which re-queries
 * `getRankedResults` — it never re-runs scoring/normalisation. An empty input
 * clears that bound (null), so the two inputs compose or stand alone.
 */
function DisplayFilterControls({
  filter,
  onFilterChange,
  disabled,
}: {
  filter: RankedResultsFilter;
  onFilterChange: (filter: RankedResultsFilter) => void;
  disabled: boolean;
}): JSX.Element {
  function parseField(value: string): number | null {
    const trimmed = value.trim();
    if (trimmed === "") return null;
    const parsed = Number(trimmed);
    return Number.isNaN(parsed) ? null : parsed;
  }

  return (
    <fieldset className="om-filter" disabled={disabled}>
      <legend className="om-filter__legend">Display filters</legend>
      <label className="om-filter__field">
        <span>Top N sites</span>
        <input
          type="number"
          min={1}
          step={1}
          className="om-filter__input"
          value={filter.top_n ?? ""}
          onChange={(event) =>
            onFilterChange({ ...filter, top_n: parseField(event.target.value) })
          }
        />
      </label>
      <label className="om-filter__field">
        <span>Min suitability</span>
        <input
          type="number"
          min={0}
          max={1}
          step={0.01}
          className="om-filter__input"
          value={filter.min_score ?? ""}
          onChange={(event) =>
            onFilterChange({ ...filter, min_score: parseField(event.target.value) })
          }
        />
      </label>
    </fieldset>
  );
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
  // The active display filter and the shared cell selection (S3-03b). The
  // filter is a display query over the fixed engine output (never a re-run);
  // the selection is lifted here so map and ranked table drive the same
  // Site-detail region through one typed `CellSelection`.
  const [filter, setFilter] = useState<RankedResultsFilter>(DEFAULT_FILTER);
  const [selection, setSelection] = useState<CellSelection | null>(null);
  // The shared client exposed to CellMap (same object held in apiRef); null
  // until the client is built (or if building it fails for lack of config).
  const [service, setService] = useState<DecisionService | null>(null);

  // Stable across renders; set once the client is ready (or fails to build).
  const apiRef = useRef<DecisionService | null>(null);
  // Guards a stale response (e.g. the mount run) from overwriting a later one
  // (e.g. a Run-button click) should they ever resolve out of order.
  const requestIdRef = useRef(0);
  // A SEPARATE staleness guard for the display-filter re-query, so an older
  // filter response cannot overwrite a newer one. Independent of the run guard
  // above: a filter change re-queries results only, never a new run.
  const filterRequestIdRef = useRef(0);

  const runWith = useCallback(async (request: RunRequest) => {
    const api = apiRef.current;
    if (!api) return;
    const requestId = ++requestIdRef.current;
    // A new run resets the display back to the default filter and clears any
    // prior selection; `filterRequestIdRef` is bumped so a late in-flight
    // filter re-query from the previous run cannot land on the new one.
    filterRequestIdRef.current++;
    setFilter(DEFAULT_FILTER);
    setSelection(null);
    setEngineLoading(true);
    setEngineError(null);
    try {
      const run = await api.runAnalysis(request);
      const [results, exclusions] = await Promise.all([
        api.getRankedResults(run.run_id, DEFAULT_FILTER),
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

  const handleRun = useCallback(() => {
    void runWith(buildRunRequest(optionId, baselineCriteria));
  }, [runWith, optionId, baselineCriteria]);

  // Apply a new display filter (S3-03b): re-query ONLY the ranked results for
  // the current run with the new filter. This never calls `runAnalysis`,
  // `getRunCells` or `getSiteDetail`, so it cannot re-trigger scoring,
  // normalisation or ranking — it is a pure display query over fixed output.
  // The `filterRequestIdRef` guard drops a stale response if a newer filter (or
  // a new run) supersedes this one before it resolves.
  const handleFilterChange = useCallback(
    (nextFilter: RankedResultsFilter) => {
      setFilter(nextFilter);
      const api = apiRef.current;
      const runId = engine?.run.run_id;
      if (!api || !runId) return;
      const requestId = ++filterRequestIdRef.current;
      void api
        .getRankedResults(runId, nextFilter)
        .then((results) => {
          if (filterRequestIdRef.current !== requestId) return;
          setEngine((current) =>
            current && current.run.run_id === runId
              ? { ...current, results }
              : current,
          );
        })
        .catch((error) => {
          if (filterRequestIdRef.current !== requestId) return;
          setEngineError(errorMessage(error));
        });
    },
    [engine?.run.run_id],
  );

  const loadingText = engineLoading ? "Loading decision-service output…" : null;
  const failureText = engineError ? `Decision service unavailable: ${engineError}` : null;

  // Site-detail is driven by the shared selection (S3-03b): a map click or a
  // ranked-row click both set the same `CellSelection`. When nothing is
  // selected yet, fall back to the first-ranked site (`engine.site`) projected
  // onto the same four fields, so the region keeps its S3-03a default view.
  const siteFacts: CellSelection | null = selection
    ? selection
    : engine?.site
      ? {
          cell_id: engine.site.cell_id,
          eligible: engine.site.eligible,
          suitability_score: engine.site.suitability_score ?? null,
          rank: engine.site.rank ?? null,
        }
      : null;

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
                    onSelectCell={setSelection}
                  />
                )
              : loadingText ?? "No engine output is available."
          }
        />
        <PlaceholderRegion
          id="region-ranked-results"
          label="Ranked results"
          ariaLabel="Ranked results"
          body={
            engine ? (
              <div className="om-ranked">
                <DisplayFilterControls
                  filter={filter}
                  onFilterChange={handleFilterChange}
                  disabled={engineLoading}
                />
                <RankedResults rows={engine.results} onSelect={setSelection} />
              </div>
            ) : (
              loadingText ?? "No ranked results are available."
            )
          }
        />
        <PlaceholderRegion
          id="region-site-detail"
          label="Site detail / explanation"
          ariaLabel="Site detail and explanation"
          body={
            siteFacts ? (
              <dl className="om-facts">
                <div><dt>Cell</dt><dd><code>{siteFacts.cell_id}</code></dd></div>
                <div><dt>Rank</dt><dd>{siteFacts.rank ?? "Not ranked"}</dd></div>
                <div><dt>Suitability</dt><dd>{siteFacts.suitability_score?.toFixed(3) ?? "Not scored"}</dd></div>
                <div><dt>Eligible</dt><dd>{siteFacts.eligible ? "Yes" : "No"}</dd></div>
                <div><dt>Excluded cells in run</dt><dd>{engine?.exclusions.length.toLocaleString() ?? "0"}</dd></div>
              </dl>
            ) : (
              loadingText ?? "No site detail is available."
            )
          }
        />
      </div>
    </div>
  );
}
