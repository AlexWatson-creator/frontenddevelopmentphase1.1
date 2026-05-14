export type ProjectStatus = "active" | "in_review" | "draft" | "archived";

export type ElementCounts = {
  columns: number;
  walls: number;
  beams: number;
  floors: number;
  foundations: number;
};

export type ProjectFile = {
  id: number;
  file_name: string | null;
  file_location: string | null;
  software: string | null;
  last_run_time: string | null;
  counts: ElementCounts;
};

export type LevelWithCounts = {
  id: number;
  name: string;
  elevation: number;
  story_height: number | null;
  counts: ElementCounts;
};

export type ProjectFileDetail = ProjectFile & {
  levels: LevelWithCounts[];
};

export type ProjectGroup = {
  number: string;
  address: string | null;
  job_name: string | null;
  designer: string | null;
  file_count: number;
  last_run_time: string | null;
  counts: ElementCounts;
  files: ProjectFile[];
};

export type ProjectDetail = {
  number: string;
  address: string | null;
  job_name: string | null;
  designer: string | null;
  files: ProjectFileDetail[];
  counts: ElementCounts;
};

// Derive a display status from last_run_time since the DB has no status field.
// null last_run_time → draft; updated within 30 days → active; older → in_review.
export function deriveStatus(lastRunTime: string | null): ProjectStatus {
  if (!lastRunTime) return "draft";
  const ageMs = Date.now() - new Date(lastRunTime).getTime();
  return ageMs < 30 * 24 * 60 * 60 * 1000 ? "active" : "in_review";
}

export function formatDate(isoString: string | null): string {
  if (!isoString) return "—";
  return new Date(isoString).toLocaleDateString("en-CA");
}

export function getTotalElements(counts: ElementCounts): number {
  return counts.columns + counts.walls + counts.beams + counts.floors;
}

export function getStatusLabel(status: ProjectStatus): string {
  if (status === "in_review") return "In Review";
  return status.charAt(0).toUpperCase() + status.slice(1);
}

export function getStatusClass(status: ProjectStatus): string {
  if (status === "active") return "text-green-700 bg-green-50 border-green-200";
  if (status === "in_review") return "text-yellow-700 bg-yellow-50 border-yellow-200";
  if (status === "draft") return "text-stone-600 bg-stone-50 border-stone-200";
  return "text-purple-700 bg-purple-50 border-purple-200";
}
