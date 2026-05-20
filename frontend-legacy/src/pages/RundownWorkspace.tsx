import { useState, useRef, useEffect, useMemo } from "react";
import type { ProjectGroup, ProjectFileDetail, LevelWithCounts } from "../api/types";
import { fetchProjectDetail } from "../api/projects";
import {
  fetchLevelElements,
  fetchLoadTable,
  saveLoadTable,
  computeTributary,
} from "../services/api";
import type {
  LevelElements,
  LoadTableEntry,
  TributaryComputeResponse,
  TributaryCell,
} from "../services/api";

// ─── Local types ──────────────────────────────────────────────────────────────

type LoadRow = {
  id: string;
  dbId?: number;
  name: string;
  description: string;
  dead: string;
  live: string;
  llrf: "N" | "R0.3" | "R0.5";
};

type DrawnArea = {
  id: string;
  type: "rect" | "poly";
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  points?: { x: number; y: number }[];
  loadRowId: string;
  createdAt: string;
};

type ViewBox = { x: number; y: number; w: number; h: number };

type PanStart = { screenX: number; screenY: number; vbX: number; vbY: number };

// ─── Helpers ──────────────────────────────────────────────────────────────────

function parseWKT(wkt: string): { x: number; y: number }[] {
  const match = wkt.match(/POLYGON\s*\(\(([^)]+)\)/i);
  if (!match) return [];
  return match[1].split(",").map((pair) => {
    const [px, py] = pair.trim().split(/\s+/).map(Number);
    return { x: px, y: py };
  });
}

function ptsToStr(pts: { x: number; y: number }[]): string {
  return pts.map((p) => `${p.x},${p.y}`).join(" ");
}

function vbStr(vb: ViewBox): string {
  return `${vb.x} ${vb.y} ${vb.w} ${vb.h}`;
}

function toSVGCoords(
  e: React.MouseEvent,
  svg: SVGSVGElement,
  group?: SVGGElement | null
): { x: number; y: number } {
  const pt = svg.createSVGPoint();
  pt.x = e.clientX;
  pt.y = e.clientY;
  const target: SVGSVGElement | SVGGElement = group ?? svg;
  const ctm = target.getScreenCTM();
  if (!ctm) return { x: 0, y: 0 };
  const r = pt.matrixTransform(ctm.inverse());
  return { x: r.x, y: r.y };
}

function elementsToViewBox(el: LevelElements): ViewBox {
  const xs: number[] = [];
  const ys: number[] = [];
  el.columns.forEach((c) => { xs.push(c.x); ys.push(c.y); });
  el.walls.forEach((w) => { xs.push(w.x1, w.x2); ys.push(w.y1, w.y2); });
  el.grids.forEach((g) => { xs.push(g.x1, g.x2); ys.push(g.y1, g.y2); });
  if (el.slab_boundary_wkt) {
    parseWKT(el.slab_boundary_wkt).forEach((p) => { xs.push(p.x); ys.push(p.y); });
  }
  if (xs.length === 0) return { x: -10000, y: 0, w: 100000, h: 30000 };
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const w = Math.max(maxX - minX, 1000);
  const h = Math.max(maxY - minY, 1000);
  const pad = 0.08;
  return {
    x: minX - w * pad,
    y: minY - h * pad,
    w: w * (1 + 2 * pad),
    h: h * (1 + 2 * pad),
  };
}


function dbEntryToRow(e: LoadTableEntry): LoadRow {
  const llrf = (["N", "R0.3", "R0.5"].includes(e.llrf_type)
    ? e.llrf_type
    : "N") as "N" | "R0.3" | "R0.5";
  return {
    id: `db-${e.id}`,
    dbId: e.id,
    name: e.name,
    description: e.description ?? "",
    dead: e.dead_load_kpa != null ? e.dead_load_kpa.toFixed(2) : "0.00",
    live: e.live_load_kpa != null ? e.live_load_kpa.toFixed(2) : "0.00",
    llrf,
  };
}

// ─── Component ────────────────────────────────────────────────────────────────

export default function RundownWorkspace({
  project,
  onBack,
  initialFileId,
  initialLevelId,
}: {
  project: ProjectGroup;
  onBack: () => void;
  initialFileId?: number;
  initialLevelId?: number;
}) {
  // ── Project / file / level data from backend ─────────────────────────────

  const [detail, setDetail] = useState<{ files: ProjectFileDetail[] } | null>(null);
  const [isLoadingDetail, setIsLoadingDetail] = useState(true);
  const [detailError, setDetailError] = useState<string | null>(null);

  const [selectedFileId, setSelectedFileId] = useState<number | null>(null);
  const [selectedLevelId, setSelectedLevelId] = useState<number | null>(null);
  const [belowLevelId, setBelowLevelId] = useState<number | null>(null);

  const [levelElements, setLevelElements] = useState<LevelElements | null>(null);
  const [isLoadingElements, setIsLoadingElements] = useState(false);
  const [elementsError, setElementsError] = useState<string | null>(null);

  // ── Load table rows (editable, seeded from backend) ──────────────────────

  const [loadRows, setLoadRows] = useState<LoadRow[]>([]);
  const [selectedLoadRowId, setSelectedLoadRowId] = useState<string>("");

  // ── Sidebars ─────────────────────────────────────────────────────────────

  const [isLeftOpen, setIsLeftOpen] = useState(true);
  const [isRightOpen, setIsRightOpen] = useState(true);
  // true = load table editor visible; false = collapsed (submitted state)
  const [loadTableOpen, setLoadTableOpen] = useState(true);

  // ── Drawing tools ─────────────────────────────────────────────────────────

  const [selectedTool, setSelectedTool] = useState<"Select" | "Rect" | "Poly">("Select");
  // Areas stored per-level: { [levelId]: DrawnArea[] }
  const [areasByLevel, setAreasByLevel] = useState<Record<number, DrawnArea[]>>({});
  const [selectedAreaId, setSelectedAreaId] = useState<string | null>(null);

  // ── Snap & layers ─────────────────────────────────────────────────────────

  const [snapEnabled, setSnapEnabled] = useState(true);
  const [snapOpts, setSnapOpts] = useState({
    columnCenters: true, wallEndpoints: false, wallEdges: false,
    slabVertices: false, slabEdges: false,
  });
  const [layers, setLayers] = useState({
    slabs: true, grids: true, walls: true, columns: true, voronoi: false,
  });
  const [boundarySource, setBoundarySource] = useState<"From Slab" | "From Drawn Areas">("From Slab");

  // ── In-progress drawing ───────────────────────────────────────────────────

  const [polyPoints, setPolyPoints] = useState<{ x: number; y: number }[]>([]);
  const [mousePos, setMousePos] = useState<{ x: number; y: number } | null>(null);
  const [rectStart, setRectStart] = useState<{ x: number; y: number } | null>(null);
  const [rectPreview, setRectPreview] = useState<{ x: number; y: number; width: number; height: number } | null>(null);

  // ── Canvas state ─────────────────────────────────────────────────────────

  const [coords, setCoords] = useState<{ x: number; y: number } | null>(null);
  const [viewBox, setViewBox] = useState<ViewBox>({ x: -10000, y: 0, w: 100000, h: 30000 });
  const [isPanning, setIsPanning] = useState(false);
  const panStartRef = useRef<PanStart | null>(null);

  // ── Feedback / async state ────────────────────────────────────────────────

  // Backend tributary response — drives both Voronoi rendering and results panel
  const [tributaryResponse, setTributaryResponse] = useState<TributaryComputeResponse | null>(null);
  const [isComputing, setIsComputing] = useState(false);
  const [computeError, setComputeError] = useState<string | null>(null);
  // Load table save state
  const [isSavingTable, setIsSavingTable] = useState(false);
  const [tableSaveError, setTableSaveError] = useState<string | null>(null);

  const svgRef = useRef<SVGSVGElement>(null);
  const contentGroupRef = useRef<SVGGElement>(null);

  // ── Derived ──────────────────────────────────────────────────────────────

  const currentFile = useMemo(
    () => detail?.files.find((f) => f.id === selectedFileId) ?? null,
    [detail, selectedFileId]
  );

  // Levels sorted by elevation descending (roof at top)
  const sortedLevels = useMemo((): LevelWithCounts[] => {
    if (!currentFile) return [];
    return [...currentFile.levels].sort((a, b) => b.elevation - a.elevation);
  }, [currentFile]);

  const belowLevelObj = useMemo(
    () => sortedLevels.find((l) => l.id === belowLevelId) ?? null,
    [sortedLevels, belowLevelId]
  );

  const belowOptions = useMemo((): LevelWithCounts[] => {
    if (!sortedLevels.length || selectedLevelId == null) return [];
    const idx = sortedLevels.findIndex((l) => l.id === selectedLevelId);
    return idx >= 0 ? sortedLevels.slice(idx + 1) : sortedLevels;
  }, [sortedLevels, selectedLevelId]);

  const canDraw = loadRows.some((r) => r.name.trim() !== "");

  // Areas for the currently selected level only
  const drawnAreas: DrawnArea[] = selectedLevelId != null ? (areasByLevel[selectedLevelId] ?? []) : [];

  function setDrawnAreas(updater: (prev: DrawnArea[]) => DrawnArea[]) {
    if (selectedLevelId == null) return;
    const lvlId = selectedLevelId;
    setAreasByLevel((all) => ({ ...all, [lvlId]: updater(all[lvlId] ?? []) }));
  }

  const selectedArea = drawnAreas.find((a) => a.id === selectedAreaId);

  // ── Boot: fetch project detail ────────────────────────────────────────────

  useEffect(() => {
    setIsLoadingDetail(true);
    setDetailError(null);
    fetchProjectDetail(project.number)
      .then((d) => {
        setDetail(d);
        if (d.files.length > 0) {
          const targetFile = initialFileId
            ? (d.files.find((f) => f.id === initialFileId) ?? d.files[0])
            : d.files[0];
          setSelectedFileId(targetFile.id);
          const sorted = [...targetFile.levels].sort((a, b) => b.elevation - a.elevation);
          if (sorted.length > 0) {
            const targetLevel = initialLevelId
              ? (sorted.find((l) => l.id === initialLevelId) ?? sorted[0])
              : sorted[0];
            setSelectedLevelId(targetLevel.id);
            const belowIdx = sorted.findIndex((l) => l.id === targetLevel.id);
            setBelowLevelId(belowIdx >= 0 && belowIdx < sorted.length - 1 ? sorted[belowIdx + 1].id : null);
          }
        }
      })
      .catch((err: unknown) =>
        setDetailError(err instanceof Error ? err.message : "Failed to load project")
      )
      .finally(() => setIsLoadingDetail(false));
  }, [project.number]);

  // ── When file changes: load its load table ───────────────────────────────

  useEffect(() => {
    if (selectedFileId == null) return;
    let cancelled = false;
    fetchLoadTable(selectedFileId)
      .then((entries) => {
        if (cancelled) return;
        const rows = entries.map(dbEntryToRow);
        setLoadRows(rows);
        if (rows.length > 0) {
          setSelectedLoadRowId(rows[0].id);
          setLoadTableOpen(false); // already have data — start collapsed
        } else {
          setSelectedLoadRowId("");
          setLoadTableOpen(true); // no data yet — open editor for user to fill in
        }
      })
      .catch(() => {
        if (!cancelled) { setLoadRows([]); setSelectedLoadRowId(""); setLoadTableOpen(true); }
      });
    return () => { cancelled = true; };
  }, [selectedFileId]);

  // ── When level changes: auto-compute below, fetch elements ───────────────

  useEffect(() => {
    if (selectedLevelId == null || !sortedLevels.length) return;
    const idx = sortedLevels.findIndex((l) => l.id === selectedLevelId);
    setBelowLevelId(idx >= 0 && idx < sortedLevels.length - 1 ? sortedLevels[idx + 1].id : null);
  }, [selectedLevelId, sortedLevels]);

  useEffect(() => {
    if (selectedFileId == null || selectedLevelId == null) return;
    // Clear any cross-level selection when the floor changes
    setSelectedAreaId(null);
    let cancelled = false;
    setIsLoadingElements(true);
    setElementsError(null);
    setLevelElements(null);
    fetchLevelElements(selectedFileId, selectedLevelId)
      .then((data) => {
        if (cancelled) return;
        console.log(
          `[Rundown] Level elements loaded — file ${selectedFileId}, level ${selectedLevelId}:`,
          `${data.columns.length} columns, ${data.walls.length} walls, ${data.grids.length} grids,`,
          `slab: ${data.slab_boundary_wkt ? "yes" : "no"}`
        );
        setLevelElements(data);
        setViewBox(elementsToViewBox(data));
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const msg = err instanceof Error ? err.message : String(err);
        console.error("[Rundown] Failed to load level elements:", msg);
        setElementsError(msg);
      })
      .finally(() => { if (!cancelled) setIsLoadingElements(false); });
    return () => { cancelled = true; };
  }, [selectedFileId, selectedLevelId]);

  // ── When selectedLoadRowId becomes stale, reset to first valid row ────────

  useEffect(() => {
    if (!selectedLoadRowId || !loadRows.find((r) => r.id === selectedLoadRowId)) {
      const first = loadRows.find((r) => r.name.trim() !== "");
      setSelectedLoadRowId(first?.id ?? "");
    }
  }, [loadRows, selectedLoadRowId]);

  // ── Global mouseup to end right-click pan even when released outside SVG ──
  useEffect(() => {
    function handleWindowMouseUp(e: MouseEvent) {
      if (e.button === 2) {
        setIsPanning(false);
        panStartRef.current = null;
      }
    }
    window.addEventListener("mouseup", handleWindowMouseUp);
    return () => window.removeEventListener("mouseup", handleWindowMouseUp);
  }, []);

  // ── Load table handlers ───────────────────────────────────────────────────

  function updateRow(id: string, field: keyof LoadRow, value: string) {
    setLoadRows((rows) => rows.map((r) => (r.id === id ? { ...r, [field]: value } : r)));
  }

  function blurNumber(id: string, field: "dead" | "live", raw: string) {
    const n = parseFloat(raw);
    updateRow(id, field, (isNaN(n) || n < 0 ? 0 : n).toFixed(2));
  }

  function addRow() {
    const newId = `local-${Date.now()}`;
    const newRow: LoadRow = { id: newId, name: "", description: "", dead: "0.00", live: "0.00", llrf: "N" };
    setLoadRows((rows) => [...rows, newRow]);
  }

  function deleteRow(id: string) {
    setLoadRows((rows) => rows.filter((r) => r.id !== id));
    if (selectedLoadRowId === id) {
      const remaining = loadRows.filter((r) => r.id !== id);
      setSelectedLoadRowId(remaining.length > 0 ? remaining[0].id : "");
    }
  }

  // ── Zoom handlers ─────────────────────────────────────────────────────────

  function zoom(factor: number) {
    setViewBox((vb) => {
      const cx = vb.x + vb.w / 2;
      const cy = vb.y + vb.h / 2;
      const nw = vb.w * factor;
      const nh = vb.h * factor;
      return { x: cx - nw / 2, y: cy - nh / 2, w: nw, h: nh };
    });
  }

  function onSVGWheel(e: React.WheelEvent<SVGSVGElement>) {
    e.preventDefault();
    const svg = svgRef.current;
    if (!svg) return;
    const factor = e.deltaY > 0 ? 1.12 : 1 / 1.12;
    // Zoom toward the mouse cursor in SVG coords
    const pt = toSVGCoords(e as unknown as React.MouseEvent<SVGSVGElement>, svg, contentGroupRef.current);
    setViewBox((vb) => {
      const nw = vb.w * factor;
      const nh = vb.h * factor;
      // Keep pt fixed: pt.x = vb.x + (pt.x - vb.x) * (nw / vb.w)  →  solve for new x
      return {
        x: pt.x - (pt.x - vb.x) * (nw / vb.w),
        y: pt.y - (pt.y - vb.y) * (nh / vb.h),
        w: nw,
        h: nh,
      };
    });
  }

  function handleFit() {
    if (levelElements) {
      setViewBox(elementsToViewBox(levelElements));
    } else {
      const p = 0.06;
      setViewBox((vb) => ({
        x: vb.x - vb.w * p,
        y: vb.y - vb.h * p,
        w: vb.w * (1 + 2 * p),
        h: vb.h * (1 + 2 * p),
      }));
    }
  }

  // ── SVG event handlers ────────────────────────────────────────────────────

  function onSVGContextMenu(e: React.MouseEvent) {
    e.preventDefault();
  }

  function onSVGMouseDown(e: React.MouseEvent<SVGSVGElement>) {
    // Right-click: start pan
    if (e.button === 2) {
      e.preventDefault();
      setIsPanning(true);
      panStartRef.current = {
        screenX: e.clientX,
        screenY: e.clientY,
        vbX: viewBox.x,
        vbY: viewBox.y,
      };
      return;
    }
    // Left-click: Rect tool
    if (selectedTool !== "Rect" || !canDraw || !selectedLoadRowId) return;
    const svg = svgRef.current;
    if (!svg) return;
    setRectStart(toSVGCoords(e, svg, contentGroupRef.current));
    setRectPreview(null);
  }

  function onSVGMouseMove(e: React.MouseEvent<SVGSVGElement>) {
    const svg = svgRef.current;
    if (!svg) return;

    // Pan mode — capture ref values synchronously to avoid null access in async updater
    if (isPanning && panStartRef.current) {
      const rect = svg.getBoundingClientRect();
      const scaleX = viewBox.w / rect.width;
      const scaleY = viewBox.h / rect.height;
      const dx = (e.clientX - panStartRef.current.screenX) * scaleX;
      const dy = (e.clientY - panStartRef.current.screenY) * scaleY;
      const originX = panStartRef.current.vbX;
      const originY = panStartRef.current.vbY;
      setViewBox((vb) => ({ ...vb, x: originX - dx, y: originY - dy }));
      return;
    }

    const c = toSVGCoords(e, svg, contentGroupRef.current);
    setCoords(c);
    setMousePos(c);

    if (selectedTool === "Rect" && rectStart) {
      setRectPreview({
        x: Math.min(rectStart.x, c.x),
        y: Math.min(rectStart.y, c.y),
        width: Math.abs(c.x - rectStart.x),
        height: Math.abs(c.y - rectStart.y),
      });
    }
  }

  function onSVGMouseUp(e: React.MouseEvent<SVGSVGElement>) {
    if (e.button === 2) {
      setIsPanning(false);
      panStartRef.current = null;
      return;
    }
    if (selectedTool !== "Rect" || !rectStart || !rectPreview || !selectedLoadRowId) return;
    if (rectPreview.width > 50 && rectPreview.height > 50) {
      setDrawnAreas((a) => [
        ...a,
        {
          id: `area-${Date.now()}`,
          type: "rect",
          ...rectPreview,
          loadRowId: selectedLoadRowId,
          createdAt: new Date().toISOString(),
        },
      ]);
    }
    setRectStart(null);
    setRectPreview(null);
  }

  function onSVGMouseLeave() {
    setCoords(null);
    setMousePos(null);
    // Stop panning if mouse leaves canvas
    if (isPanning) {
      setIsPanning(false);
      panStartRef.current = null;
    }
  }

  function onSVGClick(e: React.MouseEvent<SVGSVGElement>) {
    if (e.detail !== 1 || isPanning) return;
    const svg = svgRef.current;
    if (!svg) return;
    const c = toSVGCoords(e, svg, contentGroupRef.current);
    if (selectedTool === "Poly" && canDraw && selectedLoadRowId) {
      setPolyPoints((pts) => [...pts, c]);
    } else if (selectedTool === "Select") {
      setSelectedAreaId(null);
    }
  }

  function onSVGDblClick() {
    if (selectedTool === "Poly" && polyPoints.length >= 2 && selectedLoadRowId) {
      setDrawnAreas((a) => [
        ...a,
        {
          id: `area-${Date.now()}`,
          type: "poly",
          points: [...polyPoints],
          loadRowId: selectedLoadRowId,
          createdAt: new Date().toISOString(),
        },
      ]);
      setPolyPoints([]);
    }
  }

  // ── Compute & delete ─────────────────────────────────────────────────────

  async function handleCompute() {
    // Finish any in-progress polygon first
    if (selectedTool === "Poly" && polyPoints.length >= 3 && selectedLoadRowId) {
      setDrawnAreas((a) => [
        ...a,
        { id: `area-${Date.now()}`, type: "poly", points: [...polyPoints],
          loadRowId: selectedLoadRowId, createdAt: new Date().toISOString() },
      ]);
      setPolyPoints([]);
    }

    if (!levelElements) { setComputeError("Floor plan not loaded yet."); return; }
    if (drawnAreas.length === 0) { setComputeError("Draw load areas on the canvas first."); return; }
    if (selectedLevelId == null) { setComputeError("Select a level first."); return; }

    // Convert drawn areas to WKT polygons, using the DB id of each load row
    const loadAreaPayload = drawnAreas.flatMap((area) => {
      const row = loadRows.find((r) => r.id === area.loadRowId);
      if (!row?.dbId) return [];
      let wkt: string;
      if (area.type === "rect") {
        const x1 = area.x ?? 0, y1 = area.y ?? 0;
        const x2 = x1 + (area.width ?? 0), y2 = y1 + (area.height ?? 0);
        wkt = `POLYGON ((${x1} ${y1}, ${x2} ${y1}, ${x2} ${y2}, ${x1} ${y2}, ${x1} ${y1}))`;
      } else {
        const pts = area.points ?? [];
        if (pts.length < 3) return [];
        const ring = [...pts, pts[0]].map((p) => `${p.x} ${p.y}`).join(", ");
        wkt = `POLYGON ((${ring}))`;
      }
      return [{ polygon_wkt: wkt, load_table_id: row.dbId }];
    });

    if (loadAreaPayload.length === 0) {
      setComputeError("Save the load table first (Submit), then draw areas and compute.");
      return;
    }

    setIsComputing(true);
    setComputeError(null);
    try {
      const resp = await computeTributary({
        project_id: levelElements.project_id,
        level_above_id: selectedLevelId,
        level_below_id: belowLevelId ?? selectedLevelId,
        floor_boundary_source: boundarySource === "From Drawn Areas" ? "drawn_areas" : "slab_db",
        load_areas: loadAreaPayload,
        wall_spacing_mm: 200,
      });
      setTributaryResponse(resp);
      setLayers((l) => ({ ...l, voronoi: true }));
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Compute failed";
      setComputeError(msg);
    } finally {
      setIsComputing(false);
    }
  }

  function handleDeleteSelected() {
    if (!selectedAreaId) return;
    setDrawnAreas((a) => a.filter((area) => area.id !== selectedAreaId));
    setSelectedAreaId(null);
  }

  // ── Cursor style ──────────────────────────────────────────────────────────

  const cursorStyle = isPanning
    ? "grabbing"
    : !canDraw && selectedTool !== "Select"
    ? "not-allowed"
    : selectedTool === "Select"
    ? "default"
    : "crosshair";

  // Y-flip: SVG Y increases down but BIM Y increases up — flip the content group
  // so the plan renders in the correct architectural orientation.
  const flipTransform = useMemo(() => {
    if (!levelElements) return "scale(1,1)";
    const ys: number[] = [];
    levelElements.columns.forEach((c) => ys.push(c.y));
    levelElements.walls.forEach((w) => ys.push(w.y1, w.y2));
    levelElements.grids.forEach((g) => ys.push(g.y1, g.y2));
    if (ys.length === 0) return "scale(1,1)";
    const minY = Math.min(...ys);
    const maxY = Math.max(...ys);
    return `translate(0, ${minY + maxY}) scale(1,-1)`;
  }, [levelElements]);

  // ── Slab geometry ─────────────────────────────────────────────────────────

  const slabPts = levelElements?.slab_boundary_wkt
    ? parseWKT(levelElements.slab_boundary_wkt)
    : null;

  const openingPts = useMemo(
    () => (levelElements?.slab_openings ?? []).map(parseWKT),
    [levelElements]
  );


  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div
      className="fixed inset-0 z-50 flex flex-col bg-[#f0ede8]"
      style={{ fontFamily: "Calibri, 'Source Sans Pro', sans-serif" }}
    >
      {/* ── TOP CONTROL ROW ─────────────────────────────────────────────── */}
      <div className="flex shrink-0 items-center gap-3 border-b border-stone-200 bg-white px-4 py-2">
        <button
          onClick={onBack}
          className="mr-1 flex items-center gap-1 text-sm text-[#5C5D61] transition hover:text-[#CE1B22]"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M15.75 19.5L8.25 12l7.5-7.5" />
          </svg>
          Back
        </button>

        <span className="mr-1 text-sm font-bold text-[#231F20]">
          {project.job_name ?? project.number}
        </span>

        <span className="text-stone-200">|</span>

        {/* File dropdown */}
        <label className="ml-1 text-[11px] font-semibold text-[#5C5D61]">File</label>
        {isLoadingDetail ? (
          <span className="text-[11px] text-stone-400">Loading…</span>
        ) : detailError ? (
          <span className="text-[11px] text-red-500">{detailError}</span>
        ) : (
          <select
            value={selectedFileId ?? ""}
            onChange={(e) => {
              const fid = Number(e.target.value);
              setSelectedFileId(fid);
              const file = detail?.files.find((f) => f.id === fid);
              if (file) {
                const sorted = [...file.levels].sort((a, b) => b.elevation - a.elevation);
                setSelectedLevelId(sorted[0]?.id ?? null);
                setBelowLevelId(sorted[1]?.id ?? null);
              }
            }}
            className="rounded border border-stone-200 bg-white px-2 py-1 text-xs text-[#231F20] outline-none focus:border-[#CE1B22]"
          >
            {(detail?.files ?? []).map((f) => (
              <option key={f.id} value={f.id}>
                {f.file_name ?? `File ${f.id}`}
              </option>
            ))}
          </select>
        )}

        {/* Current Level dropdown */}
        <label className="text-[11px] font-semibold text-[#5C5D61]">Current Level</label>
        <select
          value={selectedLevelId ?? ""}
          onChange={(e) => setSelectedLevelId(Number(e.target.value))}
          className="rounded border border-stone-200 bg-white px-2 py-1 text-xs text-[#231F20] outline-none focus:border-[#CE1B22]"
        >
          {sortedLevels.map((l) => (
            <option key={l.id} value={l.id}>{l.name}</option>
          ))}
        </select>

        {/* Below dropdown */}
        <label className="text-[11px] font-semibold text-[#5C5D61]">Below</label>
        <select
          value={belowLevelId ?? ""}
          onChange={(e) => setBelowLevelId(Number(e.target.value) || null)}
          className="rounded border border-stone-200 bg-white px-2 py-1 text-xs text-[#231F20] outline-none focus:border-[#CE1B22]"
        >
          <option value="">—</option>
          {belowOptions.map((l) => (
            <option key={l.id} value={l.id}>{l.name}</option>
          ))}
        </select>

        {isLoadingElements && (
          <span className="ml-2 flex items-center gap-1 text-[11px] text-[#5C5D61]">
            <span className="h-3 w-3 animate-spin rounded-full border-2 border-stone-300 border-t-[#CE1B22]" />
            Loading…
          </span>
        )}
      </div>

      {/* ── WORKSPACE ROW ───────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">

        {/* ── LEFT SIDEBAR ──────────────────────────────────────────────── */}
        {/* Outer wrapper: gives positioning context for the toggle tab, NO overflow clip */}
        <div
          className={`relative flex shrink-0 flex-col transition-all duration-300 ${
            isLeftOpen ? "w-[340px]" : "w-12"
          }`}
        >
          {/* Toggle tab — sits outside the content box, sticking into the canvas */}
          <button
            onClick={() => setIsLeftOpen((o) => !o)}
            aria-label={isLeftOpen ? "Collapse left panel" : "Expand left panel"}
            className="absolute right-0 top-1/2 z-20 flex h-10 w-5 translate-x-full -translate-y-1/2 cursor-pointer items-center justify-center rounded-r-lg bg-[#302D27] text-white shadow-lg transition hover:bg-[#CE1B22]"
            style={{ zIndex: 30 }}
          >
            {isLeftOpen ? (
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="15 18 9 12 15 6" /></svg>
            ) : (
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="9 18 15 12 9 6" /></svg>
            )}
          </button>
          {/* Inner content box: clips content, has the border and bg */}
          <div className="flex h-full flex-1 flex-col overflow-hidden border-r border-stone-200 bg-white">

          {isLeftOpen ? (
            <div className="flex flex-1 flex-col overflow-hidden">

              {loadTableOpen ? (
                /* ── EDITOR MODE: fill in load types then submit ── */
                <div className="flex flex-1 flex-col overflow-hidden">
                  {/* Header */}
                  <div className="shrink-0 flex items-center justify-between border-b border-stone-200 px-3 py-2.5">
                    <p className="text-[10px] font-bold uppercase tracking-widest text-[#5C5D61]">
                      Load Table
                    </p>
                  </div>

                  {/* Rows */}
                  <div className="flex flex-1 flex-col gap-2 overflow-y-auto px-3 py-3">
                    {loadRows.length === 0 && (
                      <p className="text-[11px] italic text-stone-400 py-1">
                        No load types yet. Add one below.
                      </p>
                    )}
                    {loadRows.map((row) => (
                      <div key={row.id} className="rounded-lg border border-stone-200 bg-stone-50 p-2">
                        <div className="mb-1.5 flex items-center gap-1.5">
                          <input
                            type="text"
                            value={row.name}
                            onChange={(e) => updateRow(row.id, "name", e.target.value)}
                            placeholder="Name (e.g. RES)"
                            className="min-w-0 flex-1 rounded border border-stone-200 bg-white px-1.5 py-1 text-[11px] font-semibold text-[#231F20] outline-none focus:border-[#CE1B22]"
                          />
                          <input
                            type="text"
                            value={row.description}
                            onChange={(e) => updateRow(row.id, "description", e.target.value)}
                            placeholder="Description"
                            className="min-w-0 flex-[2] rounded border border-stone-200 bg-white px-1.5 py-1 text-[11px] text-[#5C5D61] outline-none focus:border-[#CE1B22]"
                          />
                          <button
                            onClick={() => deleteRow(row.id)}
                            className="shrink-0 text-sm leading-none text-stone-300 transition hover:text-[#CE1B22]"
                          >
                            ×
                          </button>
                        </div>
                        <div className="flex items-center gap-1.5">
                          <label className="shrink-0 text-[10px] text-[#5C5D61]">Dead</label>
                          <input
                            type="number"
                            value={row.dead}
                            min={0}
                            step={0.01}
                            onChange={(e) => updateRow(row.id, "dead", e.target.value)}
                            onBlur={(e) => blurNumber(row.id, "dead", e.target.value)}
                            className="w-[52px] rounded border border-stone-200 bg-white px-1.5 py-1 text-center text-[11px] outline-none focus:border-[#CE1B22]"
                          />
                          <label className="shrink-0 text-[10px] text-[#5C5D61]">Live</label>
                          <input
                            type="number"
                            value={row.live}
                            min={0}
                            step={0.01}
                            onChange={(e) => updateRow(row.id, "live", e.target.value)}
                            onBlur={(e) => blurNumber(row.id, "live", e.target.value)}
                            className="w-[52px] rounded border border-stone-200 bg-white px-1.5 py-1 text-center text-[11px] outline-none focus:border-[#CE1B22]"
                          />
                          <label className="shrink-0 text-[10px] text-[#5C5D61]">LLRF</label>
                          <select
                            value={row.llrf}
                            onChange={(e) =>
                              updateRow(row.id, "llrf", e.target.value as "N" | "R0.3" | "R0.5")
                            }
                            className="w-[58px] rounded border border-stone-200 bg-white px-1 py-1 text-[11px] outline-none focus:border-[#CE1B22]"
                          >
                            <option>N</option>
                            <option>R0.3</option>
                            <option>R0.5</option>
                          </select>
                        </div>
                      </div>
                    ))}

                    <button
                      onClick={addRow}
                      className="mt-1 flex items-center gap-1 text-[11px] font-semibold text-[#CE1B22] transition hover:text-[#ad151b]"
                    >
                      <span className="text-base leading-none">+</span> Add Load Type
                    </button>
                  </div>

                  {/* Submit */}
                  <div className="shrink-0 border-t border-stone-200 px-3 py-3">
                    <button
                      onClick={async () => {
                        if (!canDraw || selectedFileId == null) return;
                        setIsSavingTable(true);
                        setTableSaveError(null);
                        try {
                          const saved = await saveLoadTable(
                            selectedFileId,
                            loadRows
                              .filter((r) => r.name.trim() !== "")
                              .map((r) => ({
                                name: r.name.trim(),
                                description: r.description,
                                dead_load_kpa: parseFloat(r.dead) || 0,
                                live_load_kpa: parseFloat(r.live) || 0,
                                llrf_type: r.llrf,
                              }))
                          );
                          // Re-hydrate rows with DB ids
                          const hydrated = saved.map((e) => ({
                            id: `db-${e.id}`,
                            dbId: e.id,
                            name: e.name,
                            description: e.description ?? "",
                            dead: e.dead_load_kpa != null ? Number(e.dead_load_kpa).toFixed(2) : "0.00",
                            live: e.live_load_kpa != null ? Number(e.live_load_kpa).toFixed(2) : "0.00",
                            llrf: (["N","R0.3","R0.5"].includes(e.llrf_type) ? e.llrf_type : "N") as "N"|"R0.3"|"R0.5",
                          }));
                          setLoadRows(hydrated);
                          const first = hydrated[0];
                          if (first) setSelectedLoadRowId(first.id);
                          setLoadTableOpen(false);
                        } catch (err) {
                          setTableSaveError(err instanceof Error ? err.message : "Save failed");
                        } finally {
                          setIsSavingTable(false);
                        }
                      }}
                      disabled={!canDraw || isSavingTable}
                      className="w-full rounded-lg bg-[#CE1B22] py-2 text-xs font-bold text-white transition hover:bg-[#ad151b] disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      {isSavingTable ? "Saving…" : "Submit Load Table"}
                    </button>
                    {tableSaveError && (
                      <p className="mt-1.5 text-center text-[10px] text-red-600">{tableSaveError}</p>
                    )}
                    {!canDraw && (
                      <p className="mt-1.5 text-center text-[10px] text-amber-600">
                        Add at least one named load type to submit.
                      </p>
                    )}
                  </div>
                </div>
              ) : (
                /* ── SUBMITTED MODE: show load type selector ── */
                <div className="flex flex-1 flex-col overflow-hidden">
                  {/* Active Load Type header + edit button */}
                  <div className="shrink-0 flex items-center justify-between border-b border-stone-200 px-3 py-2.5">
                    <p className="text-[10px] font-bold uppercase tracking-widest text-[#5C5D61]">
                      Active Load Type
                    </p>
                    <button
                      onClick={() => setLoadTableOpen(true)}
                      className="text-[10px] font-semibold text-[#CE1B22] transition hover:text-[#ad151b]"
                    >
                      Edit Table
                    </button>
                  </div>

                  {/* Load type selector buttons */}
                  <div className="flex flex-1 flex-col gap-1.5 overflow-y-auto px-3 py-3">
                    {loadRows.filter((r) => r.name.trim() !== "").map((row) => (
                      <button
                        key={row.id}
                        onClick={() => setSelectedLoadRowId(row.id)}
                        className={`rounded px-3 py-2 text-left text-xs font-semibold transition ${
                          selectedLoadRowId === row.id
                            ? "bg-[#CE1B22] text-white"
                            : "border border-stone-200 bg-stone-50 text-[#5C5D61] hover:bg-stone-100"
                        }`}
                      >
                        <span className="block text-sm font-bold">{row.name}</span>
                        <span className="mt-0.5 block text-xs font-normal opacity-80">
                          D {row.dead} · L {row.live} · {row.llrf}
                        </span>
                      </button>
                    ))}
                  </div>

                  {/* Add more load types */}
                  <div className="shrink-0 border-t border-stone-200 px-3 py-2.5">
                    <button
                      onClick={() => setLoadTableOpen(true)}
                      className="flex items-center gap-1 text-[11px] font-semibold text-[#CE1B22] transition hover:text-[#ad151b]"
                    >
                      <span className="text-base leading-none">+</span> Add Load Type
                    </button>
                  </div>
                </div>
              )}

            </div>
          ) : (
            <div className="flex flex-col items-center gap-6 pt-14">
              <span
                className="text-[10px] font-bold uppercase tracking-widest text-stone-400"
                style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}
              >
                Loads
              </span>
            </div>
          )}
          </div>{/* end inner content box */}
        </div>{/* end left sidebar outer wrapper */}

        {/* ── CENTER CANVAS ─────────────────────────────────────────────── */}
        <div className="relative flex-1 overflow-hidden bg-[#9a9793]">
          {/* Loading overlay */}
          {isLoadingElements && (
            <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center">
              <div className="flex items-center gap-2 rounded-xl border border-stone-200 bg-white/90 px-5 py-3 shadow">
                <span className="h-4 w-4 animate-spin rounded-full border-2 border-stone-200 border-t-[#CE1B22]" />
                <span className="text-sm text-[#5C5D61]">Loading floor plan…</span>
              </div>
            </div>
          )}

          {/* Error overlay */}
          {elementsError && !isLoadingElements && (
            <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center">
              <div className="max-w-sm rounded-xl border border-red-200 bg-red-50/95 px-6 py-4 text-center shadow">
                <p className="text-sm font-semibold text-red-700">Failed to load floor plan</p>
                <p className="mt-1 font-mono text-[11px] text-red-500">{elementsError}</p>
                <p className="mt-2 text-[11px] text-red-400">Check the browser console for details.</p>
              </div>
            </div>
          )}

          {/* No-draw overlay when load table is empty and non-Select tool */}
          {!canDraw && selectedTool !== "Select" && (
            <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center">
              <div className="rounded-xl border border-amber-200 bg-amber-50/90 px-6 py-4 text-center shadow">
                <p className="text-sm font-semibold text-amber-700">
                  Add a named load type in the left panel to start drawing.
                </p>
              </div>
            </div>
          )}

          <svg
            ref={svgRef}
            viewBox={vbStr(viewBox)}
            className="h-full w-full"
            style={{ cursor: cursorStyle, display: "block" }}
            onContextMenu={onSVGContextMenu}
            onWheel={onSVGWheel}
            onMouseMove={onSVGMouseMove}
            onMouseLeave={onSVGMouseLeave}
            onMouseDown={onSVGMouseDown}
            onMouseUp={onSVGMouseUp}
            onClick={onSVGClick}
            onDoubleClick={onSVGDblClick}
          >
            {/* Grid background */}
            <defs>
              <pattern id="rw-grid" width="1000" height="1000" patternUnits="userSpaceOnUse">
                <rect width="1000" height="1000" fill="#e8e5e2" />
                <path d="M 1000 0 L 0 0 0 1000" fill="none" stroke="#e0ddd9" strokeWidth="12" />
              </pattern>
            </defs>
            <rect
              x={viewBox.x - viewBox.w}
              y={viewBox.y - viewBox.h}
              width={viewBox.w * 3}
              height={viewBox.h * 3}
              fill="url(#rw-grid)"
            />

            {/* ── STRUCTURAL ELEMENTS — wrapped in Y-flip group ── */}
            <g ref={contentGroupRef} transform={flipTransform}>

            {/* Slab boundary */}
            {layers.slabs && slabPts && slabPts.length > 0 && (
              <polygon
                points={ptsToStr(slabPts)}
                fill="#f0ede8"
                stroke="#000000"
                strokeWidth={30}
                strokeLinejoin="round"
              />
            )}

            {/* Slab openings */}
            {layers.slabs &&
              openingPts.map((pts, i) => {
                if (pts.length === 0) return null;
                const xs = pts.map(p => p.x);
                const ys = pts.map(p => p.y);
                const minX = Math.min(...xs);
                const maxX = Math.max(...xs);
                const minY = Math.min(...ys);
                const maxY = Math.max(...ys);
                return (
                  <g key={`opening-${i}`}>
                    <polygon points={ptsToStr(pts)} fill="white" stroke="#000000" strokeWidth={30} strokeLinejoin="round" />
                    <polygon points={ptsToStr(pts)} fill="none" stroke="#CE1B22" strokeWidth="22" strokeDasharray="120 60" />
                    <line x1={minX} y1={minY} x2={maxX} y2={maxY} stroke="#CE1B22" strokeWidth="22" strokeDasharray="120 60" />
                    <line x1={maxX} y1={minY} x2={minX} y2={maxY} stroke="#CE1B22" strokeWidth="22" strokeDasharray="120 60" />
                  </g>
                );
              })}

            {/* Grids */}
            {layers.grids &&
              (levelElements?.grids ?? []).map((g, i) => (
                <g key={`grid-${i}`}>
                  <line
                    x1={g.x1} y1={g.y1} x2={g.x2} y2={g.y2}
                    stroke="#8b9bb4"
                    strokeWidth="15"
                    strokeDasharray="500 250"
                    opacity="0.6"
                  />
                  <text
                    x={g.x1}
                    y={-(Math.max(g.y1, g.y2) + 250)}
                    transform="scale(1,-1)"
                    fill="#8b9bb4"
                    fontSize="400"
                    fontWeight="bold"
                    textAnchor="middle"
                  >
                    {g.name}
                  </text>
                </g>
              ))}

            {/* ── WALLS ─────────────────────────────────────────────────────────
                 Rendering strategy:
                 1. Sort longest-first so shorter (entering) walls are painted on top.
                 2. Each wall renders fill THEN border inside the same <g>, so a shorter
                    wall's opaque white fill paints over the longer wall's border at
                    every junction — no overlapping lines, clean maze-like connections.
                 3. Labels are in a second pass so they always sit above every fill/border.
                 4. Label angle is normalized to (-90, 90] so text aligns with the wall
                    direction and is never upside-down (vertical walls → bottom-to-top).
            ──────────────────────────────────────────────────────────────────── */}
            {layers.walls && (() => {
              type WGeo = {
                len: number; cx: number; cy: number;
                angle: number; labelAngle: number;
                t: number; fontSize: number; label: string;
              };

              const geos: WGeo[] = (levelElements?.walls ?? [])
                .flatMap(w => {
                  const dx = w.x2 - w.x1, dy = w.y2 - w.y1;
                  const len = Math.hypot(dx, dy);
                  if (len < 1) return [];
                  const cx = (w.x1 + w.x2) / 2, cy = (w.y1 + w.y2) / 2;
                  const angle = Math.atan2(dy, dx) * 180 / Math.PI;
                  // Normalize label angle to (-90, 90] — text aligns with wall, never upside-down
                  let labelAngle = angle;
                  if (labelAngle >= 90)  labelAngle -= 180;
                  if (labelAngle < -90)  labelAngle += 180;
                  const t = w.thickness ?? 200;
                  // Font scaled to wall thickness, capped so it fits inside the band
                  const fontSize = Math.max(60, Math.min(t * 0.62, len * 0.08, 260));
                  const label = w.mark ?? String(w.element_id);
                  return [{ len, cx, cy, angle, labelAngle, t, fontSize, label }];
                })
                .sort((a, b) => b.len - a.len); // longest first → shorter walls paint on top

              return (
                <>
                  {/* Pass 1 — fill + border per wall (interleaved so white fill of a
                      shorter wall erases the longer wall's border at junctions) */}
                  {geos.map((g, i) => {
                    const rx = g.cx - g.len / 2, ry = g.cy - g.t / 2;
                    return (
                      <g key={`wall-${i}`} transform={`rotate(${g.angle},${g.cx},${g.cy})`}>
                        {/* Opaque white fill — covers grid and any underlying borders */}
                        <rect x={rx} y={ry} width={g.len} height={g.t} fill="white" />
                        {/* Dashed red border */}
                        <rect x={rx} y={ry} width={g.len} height={g.t}
                          fill="none" stroke="#CE1B22" strokeWidth="20" strokeDasharray="120 55" />
                      </g>
                    );
                  })}

                  {/* Pass 2 — labels on top of everything, aligned with wall direction */}
                  {geos.map((g, i) => {
                    // Skip if label won't visually fit inside the band
                    const approxTextLen = g.label.length * g.fontSize * 0.6;
                    if (approxTextLen > g.len * 0.92 || g.t < 100) return null;
                    return (
                      <text key={`wlbl-${i}`}
                        x={g.cx} y={-g.cy}
                        fill="#CE1B22"
                        fontSize={g.fontSize}
                        fontWeight="600"
                        textAnchor="middle"
                        dominantBaseline="central"
                        transform={`scale(1,-1) rotate(${g.labelAngle},${g.cx},${-g.cy})`}
                      >{g.label}</text>
                    );
                  })}
                </>
              );
            })()}

            {/* Columns — dashed outline only, no X marks, label centered inside */}
            {layers.columns &&
              (levelElements?.columns ?? []).map((c, i) => {
                const label = c.mark ?? String(c.element_id);
                if (c.d) {
                  const s = c.d;
                  const x0 = c.x - s / 2;
                  const y0 = c.y - s / 2;
                  return (
                    <g key={`col-${i}`}>
                      <rect x={x0} y={y0} width={s} height={s} fill="white" />
                      <rect x={x0} y={y0} width={s} height={s}
                        fill="none" stroke="#CE1B22" strokeWidth="22" strokeDasharray="120 60" />
                      <text x={c.x} y={-c.y} transform="scale(1,-1)"
                        fill="#CE1B22" fontSize={Math.min(s * 0.52, 260)}
                        fontWeight="600" textAnchor="middle" dominantBaseline="central">
                        {label}
                      </text>
                    </g>
                  );
                }
                const bw = c.b ?? 300;
                const bh = c.h ?? 300;
                const x0 = c.x - bw / 2;
                const y0 = c.y - bh / 2;
                return (
                  <g key={`col-${i}`}
                    transform={c.rotation ? `rotate(${-c.rotation},${c.x},${c.y})` : undefined}
                  >
                    <rect x={x0} y={y0} width={bw} height={bh} fill="white" />
                    <rect x={x0} y={y0} width={bw} height={bh}
                      fill="none" stroke="#CE1B22" strokeWidth="22" strokeDasharray="120 60" />
                    <text x={c.x} y={-c.y} transform="scale(1,-1)"
                      fill="#CE1B22" fontSize={Math.min(bw, bh) * 0.52}
                      fontWeight="600" textAnchor="middle" dominantBaseline="central">
                      {label}
                    </text>
                  </g>
                );
              })}

            {/* ── VORONOI CELLS (from backend) ── */}
            {layers.voronoi && tributaryResponse?.cells.map((cell: TributaryCell, i: number) => {
              const pts = parseWKT(cell.polygon_wkt);
              if (pts.length < 3) return null;
              return (
                <polygon
                  key={`vor-${i}`}
                  points={ptsToStr(pts)}
                  fill="rgba(100,149,220,0.08)"
                  stroke="rgba(70,120,210,0.6)"
                  strokeWidth="20"
                />
              );
            })}

            {/* ── DRAWN AREAS ── */}
            {drawnAreas.map((area) => {
              const sel = area.id === selectedAreaId;
              const rowName = loadRows.find((r) => r.id === area.loadRowId)?.name ?? "";
              const fill = "rgba(206,27,34,0.13)";
              const stroke = sel ? "#CE1B22" : "rgba(206,27,34,0.55)";
              const sw = sel ? 180 : 90;
              const dash = sel ? "500 250" : undefined;
              const clickProps = {
                fill, stroke, strokeWidth: sw, strokeDasharray: dash,
                style: { cursor: "pointer" as const },
                onClick: (e: React.MouseEvent) => {
                  e.stopPropagation();
                  setSelectedAreaId(area.id === selectedAreaId ? null : area.id);
                },
              };
              if (area.type === "rect") {
                return (
                  <g key={area.id}>
                    <rect x={area.x} y={area.y} width={area.width} height={area.height} {...clickProps} />
                    {rowName && (
                      <text
                        x={(area.x ?? 0) + (area.width ?? 0) / 2}
                        y={-((area.y ?? 0) + (area.height ?? 0) / 2)}
                        transform="scale(1,-1)"
                        textAnchor="middle"
                        dominantBaseline="middle"
                        fill="#CE1B22"
                        fontSize={Math.min(area.width ?? 2000, area.height ?? 2000) * 0.18}
                        fontWeight="bold"
                        style={{ pointerEvents: "none" }}
                      >
                        {rowName}
                      </text>
                    )}
                  </g>
                );
              }
              if (area.type === "poly" && area.points) {
                const cx = area.points.reduce((s, p) => s + p.x, 0) / area.points.length;
                const cy = area.points.reduce((s, p) => s + p.y, 0) / area.points.length;
                return (
                  <g key={area.id}>
                    <polygon points={ptsToStr(area.points)} {...clickProps} />
                    {rowName && (
                      <text
                        x={cx} y={-cy}
                        transform="scale(1,-1)"
                        textAnchor="middle"
                        dominantBaseline="middle"
                        fill="#CE1B22"
                        fontSize="600"
                        fontWeight="bold"
                        style={{ pointerEvents: "none" }}
                      >
                        {rowName}
                      </text>
                    )}
                  </g>
                );
              }
              return null;
            })}

            {/* Rect preview */}
            {rectPreview && (
              <rect
                x={rectPreview.x} y={rectPreview.y}
                width={rectPreview.width} height={rectPreview.height}
                fill="rgba(206,27,34,0.08)" stroke="#CE1B22"
                strokeWidth="70" strokeDasharray="300 150"
              />
            )}

            {/* Poly in-progress */}
            {polyPoints.length > 0 && (
              <>
                {polyPoints.length > 1 && (
                  <polyline
                    points={ptsToStr(polyPoints)}
                    fill="none" stroke="#CE1B22"
                    strokeWidth="70" strokeDasharray="300 150"
                  />
                )}
                {mousePos && (
                  <line
                    x1={polyPoints[polyPoints.length - 1].x}
                    y1={polyPoints[polyPoints.length - 1].y}
                    x2={mousePos.x} y2={mousePos.y}
                    stroke="#CE1B22" strokeWidth="50"
                    strokeDasharray="200 100" opacity="0.7"
                  />
                )}
                {polyPoints.map((p, i) => (
                  <circle key={i} cx={p.x} cy={p.y} r="150" fill="#CE1B22" opacity="0.75" />
                ))}
              </>
            )}
            </g>{/* end Y-flip content group */}
          </svg>

          {/* Coordinate display */}
          <div className="pointer-events-none absolute bottom-3 left-3 rounded bg-white/85 px-2 py-1 font-mono text-[10px] text-[#5C5D61] shadow-sm backdrop-blur-sm border border-stone-200">
            {coords
              ? `X: ${coords.x.toFixed(2)}    Y: ${coords.y.toFixed(2)}`
              : "X: --    Y: --"}
          </div>

          {/* Pan hint */}
          <div className="pointer-events-none absolute bottom-3 left-1/2 -translate-x-1/2 rounded bg-white/70 px-2 py-0.5 text-[10px] text-stone-400 backdrop-blur-sm">
            Right-click + drag to pan
          </div>

          {/* Zoom controls */}
          <div className="absolute bottom-3 right-3 flex items-center gap-1">
            <button onClick={() => zoom(0.75)} className="flex h-7 w-7 items-center justify-center rounded border border-stone-200 bg-white text-base font-bold text-[#5C5D61] shadow-sm transition hover:border-[#CE1B22] hover:text-[#CE1B22]" title="Zoom in">+</button>
            <button onClick={() => zoom(1.33)} className="flex h-7 w-7 items-center justify-center rounded border border-stone-200 bg-white text-base font-bold text-[#5C5D61] shadow-sm transition hover:border-[#CE1B22] hover:text-[#CE1B22]" title="Zoom out">−</button>
            <button onClick={handleFit} className="h-7 rounded border border-stone-200 bg-white px-2.5 text-[10px] font-bold text-[#5C5D61] shadow-sm transition hover:border-[#CE1B22] hover:text-[#CE1B22]" title="Fit to view">Fit</button>
          </div>
        </div>

        {/* ── RIGHT SIDEBAR ─────────────────────────────────────────────── */}
        {/* Outer wrapper: NO overflow clip so the toggle tab is visible */}
        <div
          className={`relative flex shrink-0 flex-col transition-all duration-300 ${
            isRightOpen ? "w-[290px]" : "w-12"
          }`}
        >
          {/* Toggle tab — sticks out to the left onto the canvas */}
          <button
            onClick={() => setIsRightOpen((o) => !o)}
            aria-label={isRightOpen ? "Collapse right panel" : "Expand right panel"}
            className="absolute left-0 top-1/2 z-30 flex h-10 w-5 -translate-x-full -translate-y-1/2 cursor-pointer items-center justify-center rounded-l-lg bg-[#302D27] text-white shadow-lg transition hover:bg-[#CE1B22]"
          >
            {isRightOpen ? (
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="9 18 15 12 9 6" /></svg>
            ) : (
              <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5"><polyline points="15 18 9 12 15 6" /></svg>
            )}
          </button>
          {/* Inner content box: clips content, has the border and bg */}
          <div className="flex h-full flex-1 flex-col overflow-hidden border-l border-stone-200 bg-white">

          {isRightOpen ? (
            <div className="flex flex-1 flex-col overflow-y-auto">

              {/* Tools */}
              <div className="border-b border-stone-200 px-3 py-3">
                <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-[#5C5D61]">Tools</p>
                <div className="flex gap-1.5">
                  {(["Select", "Rect", "Poly"] as const).map((tool) => (
                    <button
                      key={tool}
                      onClick={() => {
                        setSelectedTool(tool);
                        if (tool !== "Poly") setPolyPoints([]);
                        if (tool !== "Rect") { setRectStart(null); setRectPreview(null); }
                      }}
                      title={!canDraw && tool !== "Select" ? "Add a load type first" : undefined}
                      className={`rounded border px-3 py-1.5 text-xs font-bold transition ${
                        selectedTool === tool
                          ? "border-[#CE1B22] bg-[#CE1B22] text-white"
                          : "border-stone-200 text-[#5C5D61] hover:border-[#CE1B22] hover:text-[#CE1B22]"
                      } ${!canDraw && tool !== "Select" ? "opacity-40" : ""}`}
                    >
                      {tool}
                    </button>
                  ))}
                </div>
                {!canDraw && (
                  <p className="mt-1.5 text-[10px] text-amber-600">
                    Add a named load type to enable Rect / Poly.
                  </p>
                )}
              </div>

              {/* Snap */}
              <div className="border-b border-stone-200 px-3 py-3">
                <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-[#5C5D61]">Snap</p>
                <div className="flex flex-col gap-1.5">
                  <label className="flex cursor-pointer items-center gap-2 text-xs text-[#5C5D61]">
                    <input type="checkbox" checked={snapEnabled} onChange={(e) => setSnapEnabled(e.target.checked)} className="accent-[#CE1B22]" />
                    Enabled
                  </label>
                  {(
                    [
                      ["columnCenters", "Column Centers"],
                      ["wallEndpoints", "Wall Endpoints"],
                      ["wallEdges", "Wall Edges"],
                      ["slabVertices", "Slab Vertices"],
                      ["slabEdges", "Slab Edges"],
                    ] as Array<[keyof typeof snapOpts, string]>
                  ).map(([k, lbl]) => (
                    <label key={k} className="flex cursor-pointer items-center gap-2 text-xs text-[#5C5D61]">
                      <input type="checkbox" checked={snapOpts[k]} onChange={() => setSnapOpts((s) => ({ ...s, [k]: !s[k] }))} className="accent-[#CE1B22]" />
                      {lbl}
                    </label>
                  ))}
                </div>
              </div>

              {/* Drawn Areas */}
              <div className="border-b border-stone-200 px-3 py-3">
                <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-[#5C5D61]">
                  Drawn Areas ({drawnAreas.length})
                </p>
                {drawnAreas.length === 0 ? (
                  <p className="text-[11px] italic text-stone-400">No areas drawn yet.</p>
                ) : (
                  <div className="flex flex-col gap-1">
                    {drawnAreas.map((area, i) => {
                      const rowName = loadRows.find((r) => r.id === area.loadRowId)?.name ?? "–";
                      return (
                        <button
                          key={area.id}
                          onClick={() => setSelectedAreaId(area.id === selectedAreaId ? null : area.id)}
                          className={`flex items-center justify-between rounded border px-2 py-1.5 text-left text-[11px] transition ${
                            selectedAreaId === area.id
                              ? "border-[#CE1B22] bg-[#CE1B22]/10 text-[#CE1B22]"
                              : "border-stone-200 text-[#5C5D61] hover:bg-stone-50"
                          }`}
                        >
                          <span>{rowName || `Area ${i + 1}`} – {area.type === "rect" ? "Rect" : "Poly"}</span>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>

              {/* Layers */}
              <div className="border-b border-stone-200 px-3 py-3">
                <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-[#5C5D61]">Layers</p>
                <div className="flex flex-col gap-1.5">
                  {(
                    [
                      ["slabs", "Slabs"],
                      ["grids", "Grids"],
                      ["walls", "Walls"],
                      ["columns", "Columns"],
                      ["voronoi", "Voronoi"],
                    ] as Array<[keyof typeof layers, string]>
                  ).map(([k, lbl]) => (
                    <label key={k} className="flex cursor-pointer items-center gap-2 text-xs text-[#5C5D61]">
                      <input type="checkbox" checked={layers[k]} onChange={() => setLayers((l) => ({ ...l, [k]: !l[k] }))} className="accent-[#CE1B22]" />
                      {lbl}
                    </label>
                  ))}
                </div>
              </div>

              {/* Element Info */}
              <div className="border-b border-stone-200 px-3 py-3">
                <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-[#5C5D61]">Element Info</p>
                {selectedArea ? (
                  <div className="flex flex-col gap-1 text-[11px] text-[#231F20]">
                    <div className="flex justify-between">
                      <span className="text-[#5C5D61]">ID</span>
                      <span className="font-mono text-[10px]">{selectedArea.id}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-[#5C5D61]">Type</span>
                      <span className="font-semibold">{selectedArea.type === "rect" ? "Rectangle" : "Polygon"}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-[#5C5D61]">Load Type</span>
                      <span className="font-semibold">
                        {loadRows.find((r) => r.id === selectedArea.loadRowId)?.name ?? "–"}
                      </span>
                    </div>
                    {selectedArea.type === "rect" && (
                      <>
                        <div className="flex justify-between"><span className="text-[#5C5D61]">Width</span><span>{selectedArea.width?.toFixed(0)} u</span></div>
                        <div className="flex justify-between"><span className="text-[#5C5D61]">Height</span><span>{selectedArea.height?.toFixed(0)} u</span></div>
                      </>
                    )}
                    {selectedArea.type === "poly" && selectedArea.points && (
                      <div className="flex justify-between"><span className="text-[#5C5D61]">Points</span><span>{selectedArea.points.length}</span></div>
                    )}
                  </div>
                ) : (
                  <p className="text-[11px] italic text-stone-400">Select an area to see details.</p>
                )}
              </div>

              {/* Boundary Source */}
              <div className="border-b border-stone-200 px-3 py-3">
                <p className="mb-2 text-[10px] font-bold uppercase tracking-widest text-[#5C5D61]">Boundary Source</p>
                <div className="flex flex-col gap-1.5">
                  {(["From Slab", "From Drawn Areas"] as const).map((src) => (
                    <label key={src} className="flex cursor-pointer items-center gap-2 text-xs text-[#5C5D61]">
                      <input type="radio" name="bSrc" value={src} checked={boundarySource === src} onChange={() => setBoundarySource(src)} className="accent-[#CE1B22]" />
                      {src}
                    </label>
                  ))}
                </div>
              </div>

              {/* Delete Selected */}
              <div className="border-b border-stone-200 px-3 py-2">
                <button
                  onClick={handleDeleteSelected}
                  disabled={!selectedAreaId}
                  className="w-full rounded border border-stone-200 py-1.5 text-xs font-semibold text-[#5C5D61] transition hover:border-red-300 hover:bg-red-50 hover:text-[#CE1B22] disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Delete Selected
                </button>
              </div>

              <div className="flex-1" />

              {/* Compute */}
              <div className="sticky bottom-0 mt-auto border-t border-stone-200 bg-white px-3 py-3">
                {computeError && (
                  <p className="mb-2 rounded bg-red-50 px-2 py-1.5 text-center text-[10px] text-red-600">{computeError}</p>
                )}
                <button
                  onClick={handleCompute}
                  disabled={isComputing}
                  className="w-full rounded-lg bg-[#CE1B22] py-2.5 text-sm font-bold text-white transition hover:bg-[#ad151b] disabled:opacity-60"
                >
                  {isComputing ? (
                    <span className="flex items-center justify-center gap-2">
                      <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/40 border-t-white" />
                      Computing…
                    </span>
                  ) : "Compute"}
                </button>
              </div>
            </div>
          ) : (
            <div className="flex flex-col items-center gap-6 pt-14">
              <span
                className="text-[10px] font-bold uppercase tracking-widest text-stone-400"
                style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}
              >
                Tools
              </span>
            </div>
          )}
          </div>{/* end right inner content box */}
        </div>{/* end right sidebar outer wrapper */}
      </div>

    </div>
  );
}
