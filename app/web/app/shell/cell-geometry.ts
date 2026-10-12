/**
 * Decision-free geometric helpers shared by the interactive CellMap (S3-03a/b)
 * and the S3-06 scenario-comparison cell picker.
 *
 * Every function here is a PURE read of coordinates already in memory — no
 * network call, no decision math (no scoring, ranking or weight scaling), no
 * `.sort`/`.reduce` (so the scope-guard stays satisfied). The engine owns all
 * ranking; these helpers only answer geometric membership questions
 * ("which cells fall inside this box?") so the UI can filter which rows it
 * displays without ever re-ordering or recomputing anything.
 */
import type { CellCollection } from "../api/decision-service";

/**
 * Extract the `[lng, lat]` centre of every Point feature in a cell collection.
 * Used to seed the map hover test and the picker's rectangle hit-test off the
 * same served data the map draws. A pure coordinate read — a plain `for` loop,
 * never `.reduce`/`.sort`.
 */
export function cellCenters(collection: CellCollection): [number, number][] {
  const centers: [number, number][] = [];
  const features = collection.features ?? [];
  for (let i = 0; i < features.length; i++) {
    const geometry = features[i]?.geometry;
    if (geometry?.type !== "Point") continue;
    const lng = geometry.coordinates[0];
    const lat = geometry.coordinates[1];
    if (lng !== undefined && lat !== undefined) centers.push([lng, lat]);
  }
  return centers;
}

/** An axis-aligned bounding box in lon/lat degrees (EPSG:4326). */
export interface Bbox {
  minLng: number;
  minLat: number;
  maxLng: number;
  maxLat: number;
}

/**
 * Order two drag corners `[lng, lat]` into an ordered {@link Bbox} with
 * min/max on each axis, regardless of drag direction (so dragging bottom-right
 * to top-left yields the same box as top-left to bottom-right). Named
 * `bboxFromCorners` (not any banned compute word) so it never trips the
 * scope-guard's banned-identifier check. Pure arithmetic over two points.
 */
export function bboxFromCorners(
  a: [number, number],
  b: [number, number],
): Bbox {
  return {
    minLng: Math.min(a[0], b[0]),
    minLat: Math.min(a[1], b[1]),
    maxLng: Math.max(a[0], b[0]),
    maxLat: Math.max(a[1], b[1]),
  };
}

/**
 * The `cell_id`s of every cell whose CENTRE falls inside (or on the edge of)
 * the given bounding box. A pure point-in-bbox test (inclusive `>=`/`<=` on
 * both axes) over `feature.geometry.coordinates` / `feature.properties.cell_id`
 * — the same coordinates already drawn on the map. Uses `.filter`/`.map` only
 * (never `.sort`/`.reduce`); returns the ids in the collection's original
 * feature order, so the caller never gains a re-ordering from this function.
 */
export function cellIdsInBbox(
  collection: CellCollection,
  bbox: Bbox,
): string[] {
  const features = collection.features ?? [];
  return features
    .filter((feature) => {
      if (feature.geometry.type !== "Point") return false;
      const lng = feature.geometry.coordinates[0];
      const lat = feature.geometry.coordinates[1];
      if (lng === undefined || lat === undefined) return false;
      return (
        lng >= bbox.minLng &&
        lng <= bbox.maxLng &&
        lat >= bbox.minLat &&
        lat <= bbox.maxLat
      );
    })
    .map((feature) => feature.properties.cell_id);
}
