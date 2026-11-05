/**
 * Display metadata for the values a site-detail payload carries (S4-03): the
 * engine's scored criteria and the rest of the cell's integrated row.
 *
 * Presentation only — labels, units, decimal places, grouping and the proxy
 * flag. Every value shown next to them comes from the decision service
 * verbatim; nothing here derives, rescales or reorders a value. Units follow
 * the integrated feature table's data dictionary (S1-08). Labels and units for
 * the six criteria come from the S3-05 reference work (5d6e94e).
 */

/** The S4-03 themes a site's indicators are grouped under. */
export type FieldGroup = "wind" | "demand" | "infrastructure" | "geography" | "quality";

export interface FieldDisplay {
  label: string;
  /** Unit appended to a numeric value; null for text or a yes/no flag. */
  unit: string | null;
  /** Decimal places for a numeric value. */
  digits: number;
  group: FieldGroup;
  /** A proxy variable must never be presented as a direct measurement. */
  isProxy?: boolean;
}

/** The engine's scored criteria, in the order they are usually configured. */
export const CRITERIA: Readonly<Record<string, FieldDisplay>> = {
  wind_speed: { label: "Wind speed", unit: "m/s", digits: 2, group: "wind" },
  demand_proxy: {
    label: "Demand proxy",
    unit: "index 0–1",
    digits: 3,
    group: "demand",
    isProxy: true,
  },
  dist_transmission_km: {
    label: "Distance to transmission",
    unit: "km",
    digits: 1,
    group: "infrastructure",
  },
  dist_substation_km: {
    label: "Distance to substation",
    unit: "km",
    digits: 1,
    group: "infrastructure",
  },
  inside_rez: { label: "Inside a REZ", unit: null, digits: 0, group: "infrastructure" },
  slope_deg: { label: "Slope", unit: "°", digits: 1, group: "geography" },
};

/** Other integrated-table columns the detail view shows as site context. */
export const CONTEXT_FIELDS: Readonly<Record<string, FieldDisplay>> = {
  source_region: { label: "AEMO demand region", unit: null, digits: 0, group: "demand" },
  demand_coord_confidence: {
    label: "Demand location confidence",
    unit: null,
    digits: 0,
    group: "demand",
  },
  dist_connection_km: {
    label: "Distance to connection point",
    unit: "km",
    digits: 1,
    group: "infrastructure",
  },
  rez_name: { label: "Renewable Energy Zone", unit: null, digits: 0, group: "infrastructure" },
  elevation_m: { label: "Elevation", unit: "m", digits: 0, group: "geography" },
  tri: { label: "Terrain ruggedness (TRI)", unit: null, digits: 1, group: "geography" },
  land_use: { label: "Land use", unit: null, digits: 0, group: "geography" },
  protected_area: { label: "In a protected area", unit: null, digits: 0, group: "geography" },
  protected_area_name: { label: "Protected area", unit: null, digits: 0, group: "geography" },
  area_km2: { label: "Cell area", unit: "km²", digits: 1, group: "geography" },
  data_confidence: { label: "Overall data confidence", unit: null, digits: 0, group: "quality" },
  confidence_score: { label: "Confidence score (0–1)", unit: null, digits: 2, group: "quality" },
  wind_confidence: { label: "Wind data", unit: null, digits: 0, group: "quality" },
  demand_confidence: { label: "Demand data", unit: null, digits: 0, group: "quality" },
  infra_confidence: { label: "Infrastructure data", unit: null, digits: 0, group: "quality" },
  geo_confidence: { label: "Geographic data", unit: null, digits: 0, group: "quality" },
  n_missing_features: { label: "Missing inputs", unit: null, digits: 0, group: "quality" },
  confidence_notes: { label: "Confidence notes", unit: null, digits: 0, group: "quality" },
  data_flags: { label: "Data flags", unit: null, digits: 0, group: "quality" },
};

/**
 * Columns never shown as context: the centroid (rendered as the Location
 * line), the raw exclusion columns (rendered from the explanation's
 * `exclusion_reasons`, which carries the same reasons as code + text pairs)
 * and `load_within_radius_mva` (rendered as the "Nearby network load" read-out
 * from the served `demand_load_mva`).
 */
export const HIDDEN_CONTEXT_FIELDS: ReadonlySet<string> = new Set([
  "centroid_lat",
  "centroid_lon",
  "exclusion_reason",
  "triggered_rules",
  "load_within_radius_mva",
]);

export const GROUP_LABELS: Readonly<Record<FieldGroup, string>> = {
  wind: "Wind resource",
  demand: "Demand",
  infrastructure: "Grid infrastructure",
  geography: "Geography & environment",
  quality: "Data quality & confidence",
};

/** Display metadata for any payload key; unknown keys show as served. */
export function fieldDisplay(key: string): FieldDisplay {
  return (
    CRITERIA[key] ??
    CONTEXT_FIELDS[key] ?? { label: key, unit: null, digits: 3, group: "geography" }
  );
}

/**
 * A served value as text: numbers at the field's precision with its unit,
 * booleans as Yes/No, empty strings and nulls as "—". Never alters the value
 * beyond rounding for display.
 */
export function formatValue(key: string, value: unknown): string {
  const display = fieldDisplay(key);
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return "—";
    const text = value.toFixed(display.digits);
    return display.unit ? `${text} ${display.unit}` : text;
  }
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "string") return value.trim() === "" ? "—" : value;
  if (value === null || value === undefined) return "—";
  return String(value);
}
