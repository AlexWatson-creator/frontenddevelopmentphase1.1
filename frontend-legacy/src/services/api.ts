import type { ProjectDetail, ProjectGroup } from "../api/types";

// Use relative URLs so Vite's /api proxy routes to localhost:8000,
// or an explicit base URL if VITE_API_BASE_URL is set.
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL as string) || "";

export const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA === "true";

// ─── Types ────────────────────────────────────────────────────────────────────

export type ColumnElement = {
  guid: string;
  mark: string | null;
  element_id: number;
  level_name: string | null;
  x: number;
  y: number;
  d: number | null;
  b: number | null;
  h: number | null;
  rotation: number;
};

export type WallElement = {
  guid: string;
  mark: string | null;
  element_id: number;
  level_name: string | null;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  thickness: number | null;
};

export type GridElement = {
  name: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
};

export type LevelElements = {
  project_id: number;
  level_id: number;
  columns: ColumnElement[];
  walls: WallElement[];
  grids: GridElement[];
  slab_boundary_wkt: string | null;
  slab_openings: string[];
};

export type LoadTableEntry = {
  id: number;
  project_number: string;
  project_id: number;
  name: string;
  description: string | null;
  dead_load_kpa: number | null;
  live_load_kpa: number | null;
  llrf_type: string;
};

// ─── Projects ────────────────────────────────────────────────────────────────

export async function fetchProjects(params?: {
  search?: string;
  sort_by?: string;
}): Promise<ProjectGroup[]> {
  if (USE_MOCK_DATA) return [];
  const qs = new URLSearchParams();
  if (params?.search) qs.set("search", params.search);
  if (params?.sort_by) qs.set("sort_by", params.sort_by);
  const query = qs.toString();
  const res = await fetch(
    `${API_BASE_URL}/api/projects${query ? `?${query}` : ""}`
  );
  if (!res.ok) throw new Error(`Failed to load projects (${res.status})`);
  return res.json() as Promise<ProjectGroup[]>;
}

export async function fetchProjectDetail(
  number: string
): Promise<ProjectDetail> {
  if (USE_MOCK_DATA) throw new Error("Mock data not configured");
  const res = await fetch(
    `${API_BASE_URL}/api/projects/${encodeURIComponent(number)}`
  );
  if (!res.ok)
    throw new Error(`Failed to load project "${number}" (${res.status})`);
  return res.json() as Promise<ProjectDetail>;
}

// ─── Level elements (floor plan geometry) ────────────────────────────────────

export async function fetchLevelElements(
  fileId: number,
  levelId: number
): Promise<LevelElements> {
  const res = await fetch(
    `${API_BASE_URL}/api/projects/files/${fileId}/levels/${levelId}/elements`
  );
  if (!res.ok)
    throw new Error(`Failed to load level elements (${res.status})`);
  return res.json() as Promise<LevelElements>;
}

// ─── Load table ───────────────────────────────────────────────────────────────

export async function fetchLoadTable(
  fileId: number
): Promise<LoadTableEntry[]> {
  const res = await fetch(
    `${API_BASE_URL}/api/projects/files/${fileId}/load-table`
  );
  if (!res.ok) throw new Error(`Failed to load load table (${res.status})`);
  return res.json() as Promise<LoadTableEntry[]>;
}
