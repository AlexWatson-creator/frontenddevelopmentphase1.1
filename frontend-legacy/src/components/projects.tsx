import { useMemo, useState } from "react";

export type ProjectStatus = "active" | "in_review" | "draft" | "archived";

export type Project = {
  id: string;
  code: string;
  name: string;
  client: string;
  location: string;
  status: ProjectStatus;
  updatedAt: string;
  leadEngineer: string;
  counts: {
    columns: number;
    walls: number;
    beams: number;
    floors: number;
  };
  levels: number;
};

const projects: Project[] = [
  {
    id: "p-001",
    code: "JAP-2024-018",
    name: "Harbour Point Tower",
    client: "Atlas Real Estate",
    location: "Toronto, ON",
    status: "active",
    updatedAt: "2026-02-04",
    leadEngineer: "M. Jablonsky",
    counts: {
      columns: 312,
      walls: 88,
      beams: 426,
      floors: 24,
    },
    levels: 5,
  },
  {
    id: "p-002",
    code: "JAP-2024-022",
    name: "Westbrook Civic Centre",
    client: "City of Westbrook",
    location: "Calgary, AB",
    status: "in_review",
    updatedAt: "2026-02-02",
    leadEngineer: "A. Petrova",
    counts: {
      columns: 96,
      walls: 42,
      beams: 184,
      floors: 4,
    },
    levels: 4,
  },
  {
    id: "p-003",
    code: "JAP-2025-004",
    name: "Riverside Logistics Hub",
    client: "Northwind Logistics",
    location: "Hamilton, ON",
    status: "active",
    updatedAt: "2026-01-30",
    leadEngineer: "D. Okafor",
    counts: {
      columns: 220,
      walls: 12,
      beams: 360,
      floors: 2,
    },
    levels: 2,
  },
  {
    id: "p-004",
    code: "JAP-2025-011",
    name: "Greenfield Residences",
    client: "Maple Living Co.",
    location: "Mississauga, ON",
    status: "draft",
    updatedAt: "2026-02-05",
    leadEngineer: "M. Jablonsky",
    counts: {
      columns: 0,
      walls: 0,
      beams: 0,
      floors: 0,
    },
    levels: 0,
  },
  {
    id: "p-005",
    code: "JAP-2023-090",
    name: "Eastgate Industrial Retrofit",
    client: "Eastgate Holdings",
    location: "Windsor, ON",
    status: "archived",
    updatedAt: "2025-11-12",
    leadEngineer: "S. Rao",
    counts: {
      columns: 142,
      walls: 36,
      beams: 198,
      floors: 3,
    },
    levels: 3,
  },
];

function getStatusLabel(status: ProjectStatus) {
  if (status === "in_review") {
    return "In Review";
  }

  return status.charAt(0).toUpperCase() + status.slice(1);
}

function getStatusClass(status: ProjectStatus) {
  if (status === "active") {
    return "text-green-700 bg-green-50 border-green-200";
  }

  if (status === "in_review") {
    return "text-yellow-700 bg-yellow-50 border-yellow-200";
  }

  if (status === "draft") {
    return "text-stone-600 bg-stone-50 border-stone-200";
  }

  return "text-purple-700 bg-purple-50 border-purple-200";
}

function getTotalElements(project: Project) {
  return (
    project.counts.columns +
    project.counts.walls +
    project.counts.beams +
    project.counts.floors
  );
}

function Projects({ onSelectProject }: { onSelectProject: (project: Project) => void }) {
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("all");

  const filteredProjects = useMemo(() => {
    return projects.filter((project) => {
      const searchText = search.toLowerCase();

      const matchesSearch =
        project.name.toLowerCase().includes(searchText) ||
        project.code.toLowerCase().includes(searchText) ||
        project.client.toLowerCase().includes(searchText) ||
        project.location.toLowerCase().includes(searchText);

      const matchesStatus = status === "all" || project.status === status;

      return matchesSearch && matchesStatus;
    });
  }, [search, status]);

  const stats = useMemo(() => {
    const totalProjects = projects.length;

    const activeProjects = projects.filter(
      (project) => project.status === "active",
    ).length;

    const inReviewProjects = projects.filter(
      (project) => project.status === "in_review",
    ).length;

    const totalElements = projects.reduce((total, project) => {
      return total + getTotalElements(project);
    }, 0);

    return {
      totalProjects,
      activeProjects,
      inReviewProjects,
      totalElements,
    };
  }, []);

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
            All structural projects ingested from Revit. Review models,
            levels, elements, and load rundowns from one workspace.
          </p>
        </div>
      </header>

      <section className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-wider text-stone-500">
            Total Projects
          </p>

          <h3 className="my-3 text-3xl font-bold">
            {stats.totalProjects}
          </h3>

          <span className="text-sm text-stone-500">
            Across all clients
          </span>
        </div>

        <div className="rounded-xl border border-l-4 border-stone-200 border-l-[#ce1b22] bg-white p-5 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-wider text-stone-500">
            Active
          </p>

          <h3 className="my-3 text-3xl font-bold">
            {stats.activeProjects}
          </h3>

          <span className="text-sm text-stone-500">
            In production review
          </span>
        </div>

        <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-wider text-stone-500">
            In Review
          </p>

          <h3 className="my-3 text-3xl font-bold">
            {stats.inReviewProjects}
          </h3>

          <span className="text-sm text-stone-500">
            Awaiting engineer sign-off
          </span>
        </div>

        <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-wider text-stone-500">
            Structural Elements
          </p>

          <h3 className="my-3 text-3xl font-bold">
            {stats.totalElements.toLocaleString()}
          </h3>

          <span className="text-sm text-stone-500">
            Columns · Walls · Beams · Floors
          </span>
        </div>
      </section>

      <section className="mb-5 flex flex-col gap-3 md:flex-row">
        <input
          type="text"
          placeholder="Search project name, code, client..."
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          className="h-11 w-full rounded-lg border border-stone-300 bg-white px-4 text-sm outline-none transition placeholder:text-stone-400 focus:border-[#ce1b22] focus:ring-2 focus:ring-[#ce1b22]/10 md:max-w-md"
        />

        <select
          value={status}
          onChange={(event) => setStatus(event.target.value)}
          className="h-11 rounded-lg border border-stone-300 bg-white px-4 text-sm outline-none transition focus:border-[#ce1b22] focus:ring-2 focus:ring-[#ce1b22]/10 md:w-44"
        >
          <option value="all">All statuses</option>
          <option value="active">Active</option>
          <option value="in_review">In Review</option>
          <option value="draft">Draft</option>
          <option value="archived">Archived</option>
        </select>
        <select
          value={status}
          onChange={(event) => setStatus(event.target.value)}
          className="h-11 rounded-lg border border-stone-300 bg-white px-4 text-sm outline-none transition focus:border-[#ce1b22] focus:ring-2 focus:ring-[#ce1b22]/10 md:w-44"
        >
          <option value="all">All statuses</option>
          <option value="active">Active</option>
          <option value="in_review">In Review</option>
          <option value="draft">Draft</option>
          <option value="archived">Archived</option>
        </select>
        <button className="h-11  rounded-lg bg-[#ce1b22] px-4 py-3 font-bold text-white shadow-sm transition hover:bg-[#ad151b]">
          + New Project
        </button>
      </section>

      <section className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        {filteredProjects.map((project) => (
          <article
            key={project.id}
            onClick={() => onSelectProject(project)}
            className="cursor-pointer overflow-hidden rounded-xl border border-stone-200 bg-white shadow-sm transition duration-200 hover:-translate-y-1 hover:shadow-xl"
          >
            <div className="relative h-28 border-b border-stone-200 bg-[#f7eee9]">
              <div className="absolute inset-0 bg-[linear-gradient(to_right,rgba(48,45,39,0.06)_1px,transparent_1px),linear-gradient(to_bottom,rgba(48,45,39,0.06)_1px,transparent_1px)] bg-[size:18px_18px]" />

              <span
                className={`absolute left-4 top-4 rounded-full border px-3 py-1 text-xs font-extrabold ${getStatusClass(
                  project.status,
                )}`}
              >
                {getStatusLabel(project.status)}
              </span>

              <div className="absolute bottom-5 right-7 h-12 w-20 -skew-y-12 border-2 border-stone-500/50">
                <div className="h-1/3 border-b border-stone-500/30" />
                <div className="h-1/3 border-b border-stone-500/30" />
                <div className="h-1/3" />
              </div>
            </div>

            <div className="p-5">
              <p className="mb-2 text-xs font-extrabold uppercase tracking-widest text-stone-500">
                {project.code}
              </p>

              <h2 className="mb-4 text-xl font-bold tracking-tight">
                {project.name}
              </h2>

              <div className="mb-5 grid gap-2 text-sm text-stone-500">
                <p>Client: {project.client}</p>
                <p>Location: {project.location}</p>
                <p>Lead: {project.leadEngineer}</p>
              </div>

              <div className="flex flex-col justify-between gap-2 border-t border-stone-200 pt-4 text-xs text-stone-500 sm:flex-row">
                <span>
                  {getTotalElements(project).toLocaleString()} elements ·{" "}
                  {project.levels} levels
                </span>

                <span>Updated {project.updatedAt}</span>
              </div>
            </div>
          </article>
        ))}
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
