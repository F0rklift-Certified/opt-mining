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
import {
  bboxFromCorners,
  cellCenters,
  cellGridIndex,
  cellIdsInBbox,
} from "./cell-geometry";

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

describe("cellGridIndex (S4-02 constant-time hover + selection lookups)", () => {
  // Three cells on the real 0.05° lattice (centres end in .x3625 like the grid).
  const grid = collection([
    { id: "a", lng: 150.03625, lat: -30.03625 },
    { id: "b", lng: 150.08625, lat: -30.03625 },
    { id: "c", lng: 150.03625, lat: -30.08625 },
  ]);

  it("finds the cell whose square holds the point, anywhere in its footprint", () => {
    const index = cellGridIndex(grid);
    expect(index.containing(150.03625, -30.03625)).toEqual([150.03625, -30.03625]);
    // Near a corner of a's square but still inside it (half-width 0.025).
    expect(index.containing(150.06, -30.015)).toEqual([150.03625, -30.03625]);
    // Just across the edge into b's square.
    expect(index.containing(150.0625, -30.03625)).toEqual([150.08625, -30.03625]);
    expect(index.containing(150.04, -30.09)).toEqual([150.03625, -30.08625]);
  });

  it("returns null in an empty slot or far from every cell", () => {
    const index = cellGridIndex(grid);
    expect(index.containing(150.08625, -30.08625)).toBeNull(); // no cell there
    expect(index.containing(145, -33)).toBeNull();
    expect(cellGridIndex(collection([])).containing(150, -30)).toBeNull();
  });

  it("agrees with a brute-force square scan on random points", () => {
    const cells = [];
    for (let i = 0; i < 12; i++) {
      for (let j = 0; j < 9; j++) {
        if ((i * 7 + j * 3) % 5 === 0) continue; // leave holes in the grid
        cells.push({ id: `${i}-${j}`, lng: 148.01 + i * 0.05, lat: -32.02 - j * 0.05 });
      }
    }
    const fc = collection(cells);
    const index = cellGridIndex(fc);
    let seed = 7;
    const random = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
    for (let n = 0; n < 500; n++) {
      const lng = 147.95 + random() * 0.7;
      const lat = -32.5 + random() * 0.55;
      const brute =
        cells.find(
          (c) => Math.abs(lng - c.lng) <= 0.025 && Math.abs(lat - c.lat) <= 0.025,
        ) ?? null;
      const found = index.containing(lng, lat);
      expect(found === null).toBe(brute === null);
      if (brute && found) {
        expect(Math.max(Math.abs(found[0] - lng), Math.abs(found[1] - lat))).toBeLessThanOrEqual(0.025);
      }
    }
  });

  it("looks up a cell's centre by cell_id", () => {
    const index = cellGridIndex(grid);
    expect(index.centerOf("b")).toEqual([150.08625, -30.03625]);
    expect(index.centerOf("missing")).toBeNull();
  });
});
