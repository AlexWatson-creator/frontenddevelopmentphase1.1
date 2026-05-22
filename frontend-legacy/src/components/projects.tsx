import { useEffect, useMemo, useState } from "react";
import { fetchProjects } from "../api/projects";
import {
  deriveStatus,
  formatDate,
  getStatusClass,
  getStatusLabel,
  getTotalElements,
} from "../api/types";
import type { ProjectGroup } from "../api/types";

function Projects({
  onSelectProject,
}: {
  onSelectProject: (project: ProjectGroup) => void;
}) {
  const [projects, setProjects] = useState<ProjectGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [revitYearFilter, setRevitYearFilter] = useState<string | null>(null);

  function loadProjects() {
    setLoading(true);
    setError(null);
    fetchProjects()
      .then(setProjects)
      .catch((err: unknown) =>
        setError(err instanceof Error ? err.message : "Unknown error"),
      )
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadProjects();
  }, []);

  const filteredProjects = useMemo(() => {
    return projects.filter((project) => {
      const text = search.toLowerCase();
      const matchesSearch =
        (project.job_name ?? project.number).toLowerCase().includes(text) ||
        project.number.toLowerCase().includes(text) ||
        (project.address ?? "").toLowerCase().includes(text) ||
        (project.designer ?? "").toLowerCase().includes(text);
      const projectStatus = deriveStatus(project.last_run_time);
      const matchesStatus =
        statusFilter === "all" || projectStatus === statusFilter;
      const matchesRevit =
        !revitYearFilter ||
        project.files.some((f) => f.software?.includes(revitYearFilter) ?? false);
      return matchesSearch && matchesStatus && matchesRevit;
    });
  }, [projects, search, statusFilter, revitYearFilter]);

  const stats = useMemo(() => {
    return { totalProjects: projects.length };
  }, [projects]);

  const revitYearOptions = useMemo(() => {
    const countMap = new Map<string, number>();
    for (const project of projects) {
      const seenYears = new Set<string>();
      for (const file of project.files) {
        const match = file.software?.match(/20\d{2}/);
        if (match) seenYears.add(match[0]);
      }
      for (const yr of seenYears) {
        countMap.set(yr, (countMap.get(yr) ?? 0) + 1);
      }
    }
    return Array.from(countMap.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([year, count]) => ({ year, count }));
  }, [projects]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-[#CFCCCC] border-t-[#CE1B22]" />
        <span className="ml-3 text-[#5C5D61]">Loading projects…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="mt-10 rounded-xl border border-red-200 bg-red-50 p-8 text-center">
        <h2 className="text-xl font-bold text-red-700">
          Failed to load projects
        </h2>
        <p className="mt-2 text-red-600" style={{ fontSize: "14.67px" }}>{error}</p>
        <button
          onClick={loadProjects}
          className="mt-4 rounded-lg bg-[#CE1B22] px-4 py-2 font-bold text-white hover:bg-[#ad151b]"
          style={{ fontSize: "14.67px" }}
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <>
      <header className="mb-6 flex flex-col justify-between gap-5 md:flex-row md:items-start">
        <div>
          <p
            className="mb-2 font-bold uppercase tracking-[0.18em] text-[#5C5D61]"
            style={{ fontSize: "11px" }}
          >
            Projects
          </p>

          <h1
            className="font-bold tracking-tight text-[#231F20]"
            style={{ fontSize: "40px", lineHeight: "1.15" }}
          >
            Project Dashboard
          </h1>

          <p
            className="mt-2 max-w-2xl text-[#5C5D61]"
            style={{ fontSize: "14.67px", lineHeight: "1.55" }}
          >
            All structural projects ingested from Revit. Review models, levels,
            elements, and load rundowns from one workspace.
          </p>
        </div>
      </header>

      {/* Search / filter bar */}
      <section className="mb-5 flex w-full flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
        <input
          type="text"
          placeholder="Search project name, code, location..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-11 w-full min-w-0 flex-1 rounded-lg border border-[#CFCCCC] bg-white px-4 outline-none transition placeholder:text-[#5C5D61] focus:border-[#CE1B22] focus:ring-2 focus:ring-[#CE1B22]/10"
          style={{ fontSize: "14.67px", color: "#231F20" }}
        />

        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="h-11 w-full rounded-lg border border-[#CFCCCC] bg-white px-4 outline-none transition focus:border-[#CE1B22] focus:ring-2 focus:ring-[#CE1B22]/10 sm:w-44 sm:flex-shrink-0"
          style={{ fontSize: "14.67px", color: "#231F20" }}
        >
          <option value="all">All statuses</option>
          <option value="active">Active</option>
          <option value="in_review">In Review</option>
          <option value="draft">Draft</option>
          <option value="archived">Archived</option>
        </select>

        <button
          className="h-11 w-full rounded-lg bg-[#CE1B22] px-4 py-3 font-bold text-white shadow-sm transition hover:bg-[#ad151b] sm:w-auto sm:flex-shrink-0"
          style={{ fontSize: "14.67px" }}
        >
          + New Project
        </button>
      </section>

      {/* Stat cards */}
      <section className="mb-6 grid gap-4 sm:grid-cols-2">
        <div className="rounded-xl border border-[#CFCCCC] bg-white p-5 shadow-sm">
          <p className="font-bold uppercase tracking-wider text-[#5C5D61]" style={{ fontSize: "11px" }}>
            Total Projects
          </p>
          <p className="my-3 font-bold text-[#231F20]" style={{ fontSize: "30px" }}>
            {stats.totalProjects}
          </p>
          <span className="text-[#5C5D61]" style={{ fontSize: "14.67px" }}>Across all clients</span>
        </div>

        {/* Autodesk Revit Version filter */}
        <div className="rounded-xl border border-[#CFCCCC] bg-white p-5 shadow-sm">
          <p className="mb-3 font-bold uppercase tracking-wider text-[#5C5D61]" style={{ fontSize: "11px" }}>
            Autodesk Revit Version
          </p>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => setRevitYearFilter(null)}
              className={`rounded-lg border px-3 py-1.5 font-bold transition ${
                revitYearFilter === null
                  ? "border-[#CE1B22] bg-[#CE1B22] text-white"
                  : "border-[#CFCCCC] bg-white text-[#5C5D61] hover:border-[#CE1B22] hover:text-[#CE1B22]"
              }`}
              style={{ fontSize: "12px" }}
            >
              All
            </button>
            {revitYearOptions.map(({ year, count }) => (
              <button
                key={year}
                onClick={() => setRevitYearFilter(year)}
                className={`rounded-lg border px-3 py-1.5 font-bold transition ${
                  revitYearFilter === year
                    ? "border-[#CE1B22] bg-[#CE1B22] text-white"
                    : "border-[#CFCCCC] bg-white text-[#5C5D61] hover:border-[#CE1B22] hover:text-[#CE1B22]"
                }`}
                style={{ fontSize: "12px" }}
              >
                {year} ({count})
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* Project cards */}
      <section className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        {filteredProjects.map((project) => {
          const status = deriveStatus(project.last_run_time);
          return (
            <article
              key={project.number}
              onClick={() => onSelectProject(project)}
              className="cursor-pointer overflow-hidden rounded-xl border border-[#CFCCCC] bg-white shadow-sm transition duration-200 hover:-translate-y-1 hover:shadow-xl"
            >
              <div className="relative h-28 border-b border-[#CFCCCC] bg-[#f7eee9]">
                <div className="absolute inset-0 bg-[linear-gradient(to_right,rgba(48,45,39,0.06)_1px,transparent_1px),linear-gradient(to_bottom,rgba(48,45,39,0.06)_1px,transparent_1px)] bg-[size:18px_18px]" />

                <span
                  className={`absolute left-4 top-4 rounded-full border px-3 py-1 text-xs font-extrabold ${getStatusClass(status)}`}
                >
                  {getStatusLabel(status)}
                </span>

                <div className="absolute bottom-5 right-7 h-12 w-20 -skew-y-12 border-2 border-[#5C5D61]/50">
                  <div className="h-1/3 border-b border-[#5C5D61]/30" />
                  <div className="h-1/3 border-b border-[#5C5D61]/30" />
                  <div className="h-1/3" />
                </div>
              </div>

              <div className="p-5">
                <p
                  className="mb-2 font-extrabold uppercase tracking-widest text-[#5C5D61]"
                  style={{ fontSize: "11px" }}
                >
                  {project.number}
                </p>

                <h2
                  className="mb-4 font-bold tracking-tight text-[#231F20]"
                  style={{ fontSize: "17.33px" }}
                >
                  {project.job_name ?? project.number}
                </h2>

                <div
                  className="mb-5 grid gap-2 text-[#5C5D61]"
                  style={{ fontSize: "14.67px" }}
                >
                  {project.address && <p>Location: {project.address}</p>}
                  <p>Lead: {project.designer ?? "—"}</p>
                </div>

                <div
                  className="flex flex-col justify-between gap-2 border-t border-[#CFCCCC] pt-4 text-[#5C5D61] sm:flex-row"
                  style={{ fontSize: "12px" }}
                >
                  <span>
                    {getTotalElements(project.counts).toLocaleString()} elements
                    · {project.file_count}{" "}
                    {project.file_count === 1 ? "file" : "files"}
                  </span>
                  <span>Updated {formatDate(project.last_run_time)}</span>
                </div>
              </div>
            </article>
          );
        })}
      </section>

      {filteredProjects.length === 0 && (
        <div className="mt-10 rounded-xl border border-dashed border-[#CFCCCC] bg-white p-8 text-center">
          <h2 className="font-bold text-[#231F20]" style={{ fontSize: "17.33px" }}>
            No projects found
          </h2>
          <p className="mt-2 text-[#5C5D61]" style={{ fontSize: "14.67px" }}>
            Try changing the search text, status filter, or Revit year.
          </p>
        </div>
      )}
    </>
  );
}

export default Projects;
