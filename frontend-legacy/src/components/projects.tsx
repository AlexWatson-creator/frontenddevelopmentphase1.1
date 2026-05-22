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
  const [softwareFilter, setSoftwareFilter] = useState("");

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
      const matchesSoftware =
        !softwareFilter ||
        project.files.some((f) => f.software === softwareFilter);
      return matchesSearch && matchesStatus && matchesSoftware;
    });
  }, [projects, search, statusFilter, softwareFilter]);

  const stats = useMemo(() => {
    const totalProjects = projects.length;
    const activeProjects = projects.filter(
      (p) => deriveStatus(p.last_run_time) === "active",
    ).length;
    const inReviewProjects = projects.filter(
      (p) => deriveStatus(p.last_run_time) === "in_review",
    ).length;
    const totalElements = projects.reduce(
      (sum, p) => sum + getTotalElements(p.counts),
      0,
    );
    return { totalProjects, activeProjects, inReviewProjects, totalElements };
  }, [projects]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-stone-200 border-t-[#ce1b22]" />
        <span className="ml-3 text-stone-500">Loading projects…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="mt-10 rounded-xl border border-red-200 bg-red-50 p-8 text-center">
        <h2 className="text-xl font-bold text-red-700">
          Failed to load projects
        </h2>
        <p className="mt-2 text-sm text-red-600">{error}</p>
        <button
          onClick={loadProjects}
          className="mt-4 rounded-lg bg-[#ce1b22] px-4 py-2 text-sm font-bold text-white hover:bg-[#ad151b]"
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
          <p className="mb-2 text-xs font-bold uppercase tracking-[0.18em] text-stone-500">
            Projects
          </p>

          <h1 className="text-3xl font-bold tracking-tight md:text-4xl">
            Project Dashboard
          </h1>

          <p className="mt-2 max-w-2xl leading-6 text-stone-500">
            All structural projects ingested from Revit. Review models, levels,
            elements, and load rundowns from one workspace.
          </p>
        </div>
      </header>

      <section className="mb-5 flex flex-col gap-3 md:flex-row">
        <input
          type="text"
          placeholder="Search project name, code, location..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-11 w-full rounded-lg border border-stone-300 bg-white px-4 text-sm outline-none transition placeholder:text-stone-400 focus:border-[#ce1b22] focus:ring-2 focus:ring-[#ce1b22]/10 md:max-w-475"
        />

        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="h-11 rounded-lg border border-stone-300 bg-white px-4 text-sm outline-none transition focus:border-[#ce1b22] focus:ring-2 focus:ring-[#ce1b22]/10 md:w-44"
        >
          <option value="all">All statuses</option>
          <option value="active">Active</option>
          <option value="in_review">In Review</option>
          <option value="draft">Draft</option>
          <option value="archived">Archived</option>
        </select>

        <button className="h-11 rounded-lg bg-[#ce1b22] px-4 py-3 font-bold text-white shadow-sm transition hover:bg-[#ad151b] md: w-35">
          + New Project
        </button>
      </section>
      <section
        aria-label="Project statistics"
        className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2"
      >
        <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-sm">
          <p
            id="stat-total-label"
            className="text-xs font-bold uppercase tracking-wider text-stone-500"
          >
            Total Projects
          </p>
          <p
            aria-labelledby="stat-total-label"
            className="my-3 text-3xl font-bold"
          >
            {stats.totalProjects}
          </p>
          <p className="text-sm text-stone-500">Across all clients</p>
        </div>

        <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-sm">
          <p
            id="revit-year-label"
            className="text-xs font-bold uppercase tracking-wider text-stone-500"
          >
            Revit Year
          </p>
          <div
            role="group"
            aria-labelledby="revit-year-label"
            className="mt-3 flex flex-wrap items-start gap-2"
          >
            <button
              type="button"
              className="rounded-xl border border-stone-200 bg-white p-2 text-sm shadow-sm transition hover:border-[#ce1b22] hover:text-[#ce1b22] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#ce1b22]"
              onClick={() => setSoftwareFilter("")}
            >
              All
            </button>
            <button
              type="button"
              className="rounded-xl border border-stone-200 bg-white p-2 text-sm shadow-sm transition hover:border-[#ce1b22] hover:text-[#ce1b22] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#ce1b22]"
              onClick={() => setSoftwareFilter("Autodesk Revit 2023")}
            >
              Revit 2023
            </button>
            <button
              type="button"
              className="rounded-xl border border-stone-200 bg-white p-2 text-sm shadow-sm transition hover:border-[#ce1b22] hover:text-[#ce1b22] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#ce1b22]"
              onClick={() => setSoftwareFilter("Autodesk Revit 2025")}
            >
              Revit 2025
            </button>
          </div>
          <p className="mt-3 text-sm text-stone-500">
            Columns · Walls · Beams · Floors
          </p>
        </div>
      </section>

      

      <section className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        {filteredProjects.map((project) => {
          const status = deriveStatus(project.last_run_time);
          return (
            <article
              key={project.number}
              onClick={() => onSelectProject(project)}
              className="cursor-pointer overflow-hidden rounded-xl border border-stone-200 bg-white shadow-sm transition duration-200 hover:-translate-y-1 hover:shadow-xl"
            >
              <div className="relative h-28 border-b border-stone-200 bg-[#f7eee9]">
                <div className="absolute inset-0 bg-[linear-gradient(to_right,rgba(48,45,39,0.06)_1px,transparent_1px),linear-gradient(to_bottom,rgba(48,45,39,0.06)_1px,transparent_1px)] bg-[size:18px_18px]" />

                <span
                  className={`absolute left-4 top-4 rounded-full border px-3 py-1 text-xs font-extrabold ${getStatusClass(status)}`}
                >
                  {getStatusLabel(status)}
                </span>

                <div className="absolute bottom-5 right-7 h-12 w-20 -skew-y-12 border-2 border-stone-500/50">
                  <div className="h-1/3 border-b border-stone-500/30" />
                  <div className="h-1/3 border-b border-stone-500/30" />
                  <div className="h-1/3" />
                </div>
              </div>

              <div className="p-5">
                <p className="mb-2 text-xs font-extrabold uppercase tracking-widest text-stone-500">
                  {project.number}
                </p>

                <h2 className="mb-4 text-xl font-bold tracking-tight">
                  {project.job_name ?? project.number}
                </h2>

                <div className="mb-5 grid gap-2 text-sm text-stone-500">
                  {project.address && <p>Location: {project.address}</p>}
                  <p>Lead: {project.designer ?? "—"}</p>
                </div>

                <div className="flex flex-col justify-between gap-2 border-t border-stone-200 pt-4 text-xs text-stone-500 sm:flex-row">
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
        <div className="mt-10 rounded-xl border border-dashed border-stone-300 bg-white p-8 text-center">
          <h2 className="text-xl font-bold">No projects found</h2>
          <p className="mt-2 text-stone-500">
            Try changing the search text or status filter.
          </p>
        </div>
      )}
    </>
  );
}

export default Projects;
