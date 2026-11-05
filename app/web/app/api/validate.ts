/**
 * Runtime shape guards for decision-service responses (QA F-14).
 *
 * `generated.ts` types what the contract promises, but a proxy error page, a
 * half-written run or a mismatched API version can still return a 2xx body of
 * the wrong shape — e.g. `{}` where an array was expected — and the views would
 * then crash while rendering. Each guard checks only the top-level shape a view
 * relies on and throws a {@link MalformedResponseError}, which the shell
 * already reports like any other service error. No value is transformed.
 */
import type {
  CellCollection,
  DataQualityStatus,
  ExcludedRow,
  RankedRow,
  RunHandle,
  SanityCheck,
  ScenarioComparison,
  SiteDetail,
} from "./decision-service";

/** A 2xx response whose body does not have the contract's shape. */
export class MalformedResponseError extends Error {
  readonly status: number;
  readonly operation: string;

  constructor(operation: string, status: number) {
    super(
      `The decision service returned an unexpected response for ${operation}. ` +
        "Check that the API is running the matching version, then try again.",
    );
    this.name = "MalformedResponseError";
    this.operation = operation;
    this.status = status;
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasString(value: Record<string, unknown>, key: string): boolean {
  return typeof value[key] === "string";
}

function rowsWithCellId(value: unknown): boolean {
  return Array.isArray(value) && value.every((row) => isObject(row) && hasString(row, "cell_id"));
}

export function expectRunHandle(op: string, status: number, data: unknown): RunHandle {
  if (isObject(data) && hasString(data, "run_id")) return data as RunHandle;
  throw new MalformedResponseError(op, status);
}

export function expectRankedRows(op: string, status: number, data: unknown): RankedRow[] {
  if (rowsWithCellId(data)) return data as RankedRow[];
  throw new MalformedResponseError(op, status);
}

export function expectExcludedRows(op: string, status: number, data: unknown): ExcludedRow[] {
  if (rowsWithCellId(data)) return data as ExcludedRow[];
  throw new MalformedResponseError(op, status);
}

export function expectSiteDetail(op: string, status: number, data: unknown): SiteDetail {
  if (isObject(data) && hasString(data, "cell_id") && typeof data.eligible === "boolean") {
    return data as SiteDetail;
  }
  throw new MalformedResponseError(op, status);
}

export function expectComparison(op: string, status: number, data: unknown): ScenarioComparison {
  if (isObject(data) && (data.rows === undefined || Array.isArray(data.rows))) {
    return data as ScenarioComparison;
  }
  throw new MalformedResponseError(op, status);
}

export function expectDataQuality(op: string, status: number, data: unknown): DataQualityStatus {
  if (
    isObject(data) &&
    typeof data.passed === "boolean" &&
    (data.checks === undefined || Array.isArray(data.checks))
  ) {
    return data as DataQualityStatus;
  }
  throw new MalformedResponseError(op, status);
}

export function expectCellCollection(op: string, status: number, data: unknown): CellCollection {
  if (isObject(data) && data.type === "FeatureCollection" && Array.isArray(data.features)) {
    return data as CellCollection;
  }
  throw new MalformedResponseError(op, status);
}

export function expectSanityCheck(op: string, status: number, data: unknown): SanityCheck {
  if (
    isObject(data) &&
    hasString(data, "caveat") &&
    (data.checks === undefined || Array.isArray(data.checks))
  ) {
    return data as SanityCheck;
  }
  throw new MalformedResponseError(op, status);
}
