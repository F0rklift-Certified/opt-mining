/**
 * The single browser integration point for the frozen S2-08 HTTP contract.
 *
 * Request and response shapes come exclusively from `generated.ts`, which is
 * produced from the live FastAPI OpenAPI document.  This wrapper only names
 * the seven service operations and turns non-2xx responses into one consistent
 * error; it contains no decision or data-transformation logic.
 *
 * S3-03a adds the seventh operation, `getRunCells`, the map's single data path.
 */
import createClient from "openapi-fetch";

import type { components, paths } from "./generated";

export type RunRequest = components["schemas"]["RunRequest"];
export type RunHandle = components["schemas"]["RunHandle"];
export type Criterion = components["schemas"]["Criterion"];
export type Weights = components["schemas"]["Weights"];
export type RankedRow = components["schemas"]["RankedRow"];
export type SiteDetail = components["schemas"]["SiteDetail"];
export type ExcludedRow = components["schemas"]["ExcludedRow"];
export type ScenarioComparisonRequest =
  components["schemas"]["ScenarioComparisonRequest"];
export type ScenarioComparison = components["schemas"]["ScenarioComparison"];
export type DataQualityStatus = components["schemas"]["DataQualityStatus"];
export type CellCollection = components["schemas"]["CellCollection"];

export interface RankedResultsFilter {
  top_n?: number | null;
  min_score?: number | null;
}

/**
 * The stable, typed selection a view surfaces when a single cell is inspected
 * (S3-03b). It is the shared cross-view contract the future Site-detail view
 * (S3-05) consumes: both a map `click` (reading a feature's `CellProperties`)
 * and a ranked-table row (a `RankedRow`) produce this same shape, so map
 * selection and table selection are interchangeable. It carries only the
 * engine-produced identity/score/eligibility already in memory — no decision
 * math, no network call — keyed on the stable `cell_id` the detail view uses to
 * fetch its richer explanation on demand via `getSiteDetail`. For an excluded
 * cell `suitability_score` and `rank` are null.
 */
export interface CellSelection {
  cell_id: string;
  eligible: boolean;
  suitability_score: number | null;
  rank: number | null;
}

export interface DecisionService {
  runAnalysis(request: RunRequest): Promise<RunHandle>;
  getRankedResults(
    runId: string,
    filter?: RankedResultsFilter,
  ): Promise<RankedRow[]>;
  getSiteDetail(runId: string, cellId: string): Promise<SiteDetail>;
  getExclusions(runId: string): Promise<ExcludedRow[]>;
  compareScenarios(
    request: ScenarioComparisonRequest,
  ): Promise<ScenarioComparison>;
  getDataQuality(): Promise<DataQualityStatus>;
  getRunCells(runId: string): Promise<CellCollection>;
}

export class DecisionServiceError extends Error {
  readonly status: number;
  readonly payload: unknown;

  constructor(status: number, payload: unknown) {
    super(`Decision service request failed with HTTP ${status}`);
    this.name = "DecisionServiceError";
    this.status = status;
    this.payload = payload;
  }
}

function apiBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_API_BASE_URL?.trim();
  if (!configured) {
    throw new Error(
      "NEXT_PUBLIC_API_BASE_URL is not configured; set it before starting the web app.",
    );
  }
  return configured.replace(/\/+$/, "");
}

export interface DecisionServiceClientOptions {
  baseUrl?: string;
  fetch?: typeof globalThis.fetch;
}

/** Build a contract-typed client; callers normally use the env-based URL. */
export function createDecisionServiceClient(
  options: DecisionServiceClientOptions = {},
): DecisionService {
  const client = createClient<paths>({
    baseUrl: (options.baseUrl ?? apiBaseUrl()).replace(/\/+$/, ""),
    fetch: options.fetch,
  });

  return {
    async runAnalysis(request) {
      const { data, error, response } = await client.POST("/runs", {
        body: request,
      });
      if (data === undefined) throw new DecisionServiceError(response.status, error);
      return data;
    },

    async getRankedResults(runId, filter = {}) {
      const { data, error, response } = await client.GET(
        "/runs/{run_id}/results",
        {
          params: {
            path: { run_id: runId },
            query: filter,
          },
        },
      );
      if (data === undefined) throw new DecisionServiceError(response.status, error);
      return data;
    },

    async getSiteDetail(runId, cellId) {
      const { data, error, response } = await client.GET(
        "/runs/{run_id}/sites/{cell_id}",
        { params: { path: { run_id: runId, cell_id: cellId } } },
      );
      if (data === undefined) throw new DecisionServiceError(response.status, error);
      return data;
    },

    async getExclusions(runId) {
      const { data, error, response } = await client.GET(
        "/runs/{run_id}/exclusions",
        { params: { path: { run_id: runId } } },
      );
      if (data === undefined) throw new DecisionServiceError(response.status, error);
      return data;
    },

    async compareScenarios(request) {
      const { data, error, response } = await client.POST(
        "/scenario-comparison",
        { body: request },
      );
      if (data === undefined) throw new DecisionServiceError(response.status, error);
      return data;
    },

    async getDataQuality() {
      const { data, error, response } = await client.GET("/data-quality");
      if (data === undefined) throw new DecisionServiceError(response.status, error);
      return data;
    },

    async getRunCells(runId) {
      const { data, error, response } = await client.GET(
        "/runs/{run_id}/cells",
        { params: { path: { run_id: runId } } },
      );
      if (data === undefined) throw new DecisionServiceError(response.status, error);
      return data;
    },
  };
}
