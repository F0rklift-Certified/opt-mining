"use client";

import { useEffect, useRef, useState } from "react";
import type { ExcludedRow, RankedRow } from "../api/decision-service";
import outline from "./nsw-outline.json";
import type { SelectSite } from "./siteSelection";

type MapCell = RankedRow | ExcludedRow;
const WIDTH = 640;
const HEIGHT = 480;
const WEST = 140.7;
const NORTH = -27.8;
const SPAN = 13.6;
const CELL_DEGREES = 0.05; // frozen grid size, not a scoring parameter

/** Offline lon/lat drawing. No reprojecting, eligibility calculation or ranking. */
export default function ScreeningMap({ rows, exclusions, selectedCellId, onSelect }: {
  rows: RankedRow[]; exclusions: ExcludedRow[]; selectedCellId: string | null; onSelect: SelectSite;
}): React.JSX.Element {
  const canvas = useRef<HTMLCanvasElement>(null);
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [showExcluded, setShowExcluded] = useState(true);
  const [lookup, setLookup] = useState("");
  const [lookupError, setLookupError] = useState("");
  const cells: MapCell[] = showExcluded ? [...rows, ...exclusions] : rows;
  const selected = [...rows, ...exclusions].find((cell) => cell.cell_id === selectedCellId);

  function project(lon: number, lat: number): [number, number] {
    return [((lon - WEST) / SPAN * WIDTH - WIDTH / 2) * zoom + WIDTH / 2 + pan.x,
      ((NORTH - lat) / SPAN * WIDTH - HEIGHT / 2) * zoom + HEIGHT / 2 + pan.y];
  }

  useEffect(() => {
    const context = canvas.current?.getContext("2d");
    if (!context) return;
    context.clearRect(0, 0, WIDTH, HEIGHT);
    context.fillStyle = "#eaf1f6";
    context.fillRect(0, 0, WIDTH, HEIGHT);
    context.fillStyle = "#fff";
    context.strokeStyle = "#596c77";
    // The committed outline is an ABS MultiPolygon in EPSG:4326.
    for (const polygon of outline.geometry.coordinates) {
      context.beginPath();
      for (const ring of polygon) {
        ring.forEach(([lon, lat], index) => {
          if (lon === undefined || lat === undefined) return;
          const [x, y] = project(lon, lat);
          if (index === 0) context.moveTo(x, y); else context.lineTo(x, y);
        });
        context.closePath();
      }
      context.fill("evenodd");
      context.stroke();
    }
    const size = CELL_DEGREES / SPAN * WIDTH * zoom;
    for (const cell of cells) {
      if (cell.centroid_lon == null || cell.centroid_lat == null) continue;
      const [x, y] = project(cell.centroid_lon, cell.centroid_lat);
      context.fillStyle = "suitability_score" in cell ? "#24785e" : "#b0a496";
      context.fillRect(x - size / 2, y - size / 2, size, size);
    }
    if (selected?.centroid_lon != null && selected.centroid_lat != null) {
      const [x, y] = project(selected.centroid_lon, selected.centroid_lat);
      context.strokeStyle = "#b42318";
      context.lineWidth = 2;
      context.strokeRect(x - Math.max(size, 8) / 2, y - Math.max(size, 8) / 2,
        Math.max(size, 8), Math.max(size, 8));
      context.lineWidth = 1;
    }
  });

  function selectAt(event: React.MouseEvent<HTMLCanvasElement>): void {
    const rect = event.currentTarget.getBoundingClientRect();
    const x = (event.clientX - rect.left) / rect.width * WIDTH;
    const y = (event.clientY - rect.top) / rect.height * HEIGHT;
    let closest: MapCell | null = null;
    let distance = Infinity;
    for (const cell of cells) {
      if (cell.centroid_lon == null || cell.centroid_lat == null) continue;
      const [cx, cy] = project(cell.centroid_lon, cell.centroid_lat);
      const delta = Math.hypot(cx - x, cy - y);
      if (delta < distance) { distance = delta; closest = cell; }
    }
    if (closest && distance <= Math.max(5, CELL_DEGREES / SPAN * WIDTH * zoom)) onSelect(closest.cell_id);
  }

  return <div className="om-map">
    <p>NSW screening grid · EPSG:4326 · 0.05° cells (approximately 5 km).</p>
    <p><span className="om-legend--eligible">■ Eligible</span> · <span className="om-legend--excluded">■ Excluded</span> · red outline: selected cell.</p>
    <div className="om-toolbar">
      <button onClick={() => setZoom((value) => Math.min(value * 1.5, 12))} aria-label="Zoom in">+</button>
      <button onClick={() => setZoom((value) => Math.max(value / 1.5, 1))} aria-label="Zoom out">−</button>
      <button onClick={() => { setZoom(1); setPan({ x: 0, y: 0 }); }}>Reset map</button>
      <button onClick={() => setPan((p) => ({ ...p, x: p.x + 80 }))} aria-label="Pan west">←</button>
      <button onClick={() => setPan((p) => ({ ...p, x: p.x - 80 }))} aria-label="Pan east">→</button>
      <button onClick={() => setPan((p) => ({ ...p, y: p.y + 80 }))} aria-label="Pan north">↑</button>
      <button onClick={() => setPan((p) => ({ ...p, y: p.y - 80 }))} aria-label="Pan south">↓</button>
      <label><input type="checkbox" checked={showExcluded} onChange={(e) => setShowExcluded(e.target.checked)} /> Show excluded cells</label>
    </div>
    <canvas ref={canvas} width={WIDTH} height={HEIGHT} onClick={selectAt}
      aria-label="NSW eligible and excluded screening cells" role="img" />
    <form onSubmit={(e) => { e.preventDefault(); const found = [...rows, ...exclusions].find((c) => c.cell_id === lookup.trim());
      if (found) { onSelect(found.cell_id); setLookupError(""); } else setLookupError("Cell ID not found in this run."); }}>
      <label>Inspect cell ID <input value={lookup} onChange={(e) => setLookup(e.target.value)} /></label>
      <button type="submit">Inspect cell</button>
    </form>
    {lookupError && <p role="alert">{lookupError}</p>}
    {selected && <p>Selected site: <code>{selected.cell_id}</code> · {"rank" in selected ? `Engine rank ${selected.rank}` : `Excluded: ${selected.reason_text}`}</p>}
    <small>{outline.attribution}. Offline outline is simplified for display only. Grid values and coordinates are supplied by the decision service.</small>
  </div>;
}
