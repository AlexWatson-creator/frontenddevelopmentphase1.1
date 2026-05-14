import type { ProjectDetail, ProjectGroup } from "./types";

const API_BASE = (import.meta.env.VITE_API_BASE_URL as string) || "";

export async function fetchProjects(params?: {
  search?: string;
  sort_by?: string;
}): Promise<ProjectGroup[]> {
  const qs = new URLSearchParams();
  if (params?.search) qs.set("search", params.search);
  if (params?.sort_by) qs.set("sort_by", params.sort_by);
  const query = qs.toString();
  const res = await fetch(`${API_BASE}/api/projects${query ? `?${query}` : ""}`);
  if (!res.ok) throw new Error(`Failed to load projects (${res.status})`);
  return res.json() as Promise<ProjectGroup[]>;
}

export async function fetchProjectDetail(number: string): Promise<ProjectDetail> {
  const res = await fetch(`${API_BASE}/api/projects/${encodeURIComponent(number)}`);
  if (!res.ok) throw new Error(`Failed to load project "${number}" (${res.status})`);
  return res.json() as Promise<ProjectDetail>;
}
