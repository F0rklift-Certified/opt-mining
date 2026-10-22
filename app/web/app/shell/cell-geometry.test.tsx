/**
 * Unit tests for the decision-free geometry helpers (S3-06 cell picker).
 *
 * These prove the PURE rectangle hit-test used by the mini-map picker in
 * isolation (the MapLibre component is tested separately with the jsdom mock):
 *   - `cellCenters` extracts `[lng, lat]` from Point features;
 *   - `bboxFromCorners` orders two drag corners into min/max regardless of
 *     drag direction;
 *   - `cellIdsInBbox` returns exactly the cells whose centre is inside (or on
 *     the edge of) the box, in the collection's original order, and never
 *     re-orders or recomputes anything.
 */
import type { CellCollection } from "../api/decision-service";
import { bboxFromCorners, cellCenters, cellIdsInBbox } from "./cell-geometry";

function collection(
  cells: { id: string; lng: number; lat: number }[],
): CellCollection {
  return {
    type: "FeatureCollection",
    run_id: "run-1",
    features: cells.map((cell) => ({
      type: "Feature",
      geometry: { type: "Point", coordinates: [cell.lng, cell.lat] },
      properties: {
        cell_id: cell.id,
        eligible: true,
        suitability_score: 0.5,
        rank: 1,
      },
    })),
  } as CellCollection;
}

describe("cellCenters", () => {
  it("extracts [lng, lat] for every Point feature", () => {
    const centers = cellCenters(
      collection([
        { id: "a", lng: 151.2, lat: -30.1 },
        { id: "b", lng: 149.0, lat: -33.5 },
      ]),
    );
    expect(centers).toEqual([
      [151.2, -30.1],
      [149.0, -33.5],
    ]);
  });

  it("returns an empty array for an empty collection", () => {
    expect(cellCenters(collection([]))).toEqual([]);
  });
});

describe("bboxFromCorners", () => {
  it("orders corners into min/max regardless of drag direction", () => {
    const topLeftToBottomRight = bboxFromCorners([149.0, -30.0], [151.0, -34.0]);
    const bottomRightToTopLeft = bboxFromCorners([151.0, -34.0], [149.0, -30.0]);
    const expected = { minLng: 149.0, minLat: -34.0, maxLng: 151.0, maxLat: -30.0 };
    expect(topLeftToBottomRight).toEqual(expected);
    // Dragging the opposite way yields the identical normalised box.
    expect(bottomRightToTopLeft).toEqual(expected);
  });
});

describe("cellIdsInBbox", () => {
  const cells = collection([
    { id: "inside-1", lng: 150.0, lat: -32.0 },
    { id: "inside-2", lng: 150.5, lat: -31.5 },
    { id: "outside-west", lng: 145.0, lat: -32.0 },
    { id: "outside-north", lng: 150.0, lat: -28.0 },
    { id: "on-edge", lng: 149.0, lat: -34.0 }, // exactly on the box corner
  ]);

  const bbox = { minLng: 149.0, minLat: -34.0, maxLng: 151.0, maxLat: -30.0 };

  it("returns the cells whose centre falls inside the box, in collection order", () => {
    expect(cellIdsInBbox(cells, bbox)).toEqual(["inside-1", "inside-2", "on-edge"]);
  });

  it("includes a cell sitting exactly on the box edge (inclusive test)", () => {
    expect(cellIdsInBbox(cells, bbox)).toContain("on-edge");
  });

  it("excludes cells outside the box on any axis", () => {
    const ids = cellIdsInBbox(cells, bbox);
    expect(ids).not.toContain("outside-west");
    expect(ids).not.toContain("outside-north");
  });

  it("returns an empty array when no cell falls inside", () => {
    expect(
      cellIdsInBbox(cells, { minLng: 100, minLat: -10, maxLng: 101, maxLat: -9 }),
    ).toEqual([]);
  });

  it("returns an empty array for an empty collection", () => {
    expect(cellIdsInBbox(collection([]), bbox)).toEqual([]);
  });
});
