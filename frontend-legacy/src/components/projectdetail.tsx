import type { Project, ProjectStatus } from "./projects";

type Level = {
  name: string;
  elevation: string;
  height: string;
  col: number;
  wall: number;
  beam: number;
  floor: number;
};

function buildLevels(project: Project): Level[] {
  if (project.levels === 0) return [];

  const floorHeight = 3500;
  const roofWeight = 0.4;
  const totalWeight = roofWeight + project.levels;

  function share(total: number, weight: number) {
    return Math.round((total * weight) / totalWeight);
  }

  const rows: Level[] = [];

  rows.push({
    name: "Roof",
    elevation: `${project.levels * floorHeight} mm`,
    height: "---",
    col: share(project.counts.columns, roofWeight),
    wall: share(project.counts.walls, roofWeight),
    beam: share(project.counts.beams, roofWeight),
    floor: share(project.counts.floors, roofWeight),
  });

  for (let i = project.levels; i >= 1; i--) {
    rows.push({
      name: `Level ${String(i).padStart(2, "0")}`,
      elevation: `${(i - 1) * floorHeight} mm`,
      height: `${floorHeight} mm`,
      col: share(project.counts.columns, 1),
      wall: share(project.counts.walls, 1),
      beam: share(project.counts.beams, 1),
      floor: share(project.counts.floors, 1),
    });
  }

  return rows;
}

function getStatusLabel(status: ProjectStatus) {
  if (status === "in_review") return "In Review";
  return status.charAt(0).toUpperCase() + status.slice(1);
}

function getStatusClass(status: ProjectStatus) {
  if (status === "active") return "text-green-700 bg-green-50 border-green-200";
  if (status === "in_review") return "text-yellow-700 bg-yellow-50 border-yellow-200";
  if (status === "draft") return "text-stone-600 bg-stone-50 border-stone-200";
  return "text-purple-700 bg-purple-50 border-purple-200";
}

function ProjectDetail({
  project,
  onBack,
  onRundown,
}: {
  project: Project;
  onBack: () => void;
  onRundown: () => void;
}) {
  const totalElements =
    project.counts.columns +
    project.counts.walls +
    project.counts.beams +
    project.counts.floors;

  const levels = buildLevels(project);

  return (
    <>
      <header className="mb-8">
        <button
          onClick={onBack}
          className="mb-5 flex items-center gap-1.5 text-sm text-stone-500 transition hover:text-[#ce1b22]"
        >
          <svg
            className="h-4 w-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M15.75 19.5L8.25 12l7.5-7.5"
            />
          </svg>
          Projects
        </button>

        <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
          <div>
            <div className="flex flex-wrap items-center gap-3">
              <h1 className="text-4xl font-bold tracking-tight">{project.name}</h1>
              <span
                className={`rounded-full border px-3 py-1 text-xs font-extrabold ${getStatusClass(project.status)}`}
              >
                {getStatusLabel(project.status)}
              </span>
            </div>

            <p className="mt-1 text-sm font-semibold text-stone-400">{project.code}</p>

            <p className="mt-3 text-sm text-stone-500">
              <span className="font-semibold text-stone-700">1 file</span>
              <span className="mx-2 text-stone-300">·</span>
              <span className="font-semibold text-stone-700">
                {totalElements.toLocaleString()} elements
              </span>
              <span className="mx-2 text-stone-300">·</span>
              <span>{project.client}</span>
              <span className="mx-2 text-stone-300">·</span>
              <span>{project.location}</span>
            </p>

            <p className="mt-1 text-sm text-stone-400">
              Lead: {project.leadEngineer}
            </p>
          </div>

          <div className="flex shrink-0 gap-3">
            <button
              onClick={onRundown}
              className="rounded-lg bg-[#ce1b22] px-5 py-2.5 text-sm font-bold text-white shadow-sm transition hover:bg-[#ad151b]"
            >
              Rundown
            </button>
            <button className="rounded-lg border border-stone-300 bg-white px-5 py-2.5 text-sm font-bold text-stone-700 shadow-sm transition hover:bg-stone-50">
              Delete Project
            </button>
          </div>
        </div>
      </header>

      <section>
        <p className="mb-3 text-xs font-bold uppercase tracking-[0.18em] text-stone-500">
          Files
        </p>

        <div className="overflow-hidden rounded-xl border border-stone-200 bg-white shadow-sm">
          <div className="border-b border-stone-200 p-5">
            <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
              <div>
                <div className="flex flex-wrap items-center gap-3">
                  <h2 className="text-base font-bold text-stone-800">
                    S-{project.code}
                  </h2>
                  <span className="rounded border border-stone-200 bg-stone-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-stone-500">
                    Autodesk Revit 2025
                  </span>
                </div>

                <p className="mt-1.5 text-xs text-stone-400">
                  Autodesk Docs://{project.code}/S-{project.code}.rvt
                </p>

                <p className="mt-2.5 text-xs text-stone-600">
                  <span className="font-semibold">{project.counts.columns}</span>
                  {" "}col
                  <span className="mx-2 text-stone-300">·</span>
                  <span className="font-semibold">{project.counts.walls}</span>
                  {" "}wall
                  <span className="mx-2 text-stone-300">·</span>
                  <span className="font-semibold">{project.counts.beams}</span>
                  {" "}beam
                  <span className="mx-2 text-stone-300">·</span>
                  <span className="font-semibold">{project.counts.floors}</span>
                  {" "}flr
                </p>

                <p className="mt-1.5 text-xs text-stone-400">
                  Updated {project.updatedAt}
                </p>
              </div>

              <div className="flex shrink-0 flex-col items-end gap-2">
                <div className="flex items-center gap-4">
                  <button className="text-sm font-semibold text-[#ce1b22] transition hover:underline">
                    Load Table
                  </button>
                  <button className="text-sm text-stone-400 transition hover:text-stone-700">
                    Delete
                  </button>
                </div>
                <p className="text-sm font-bold text-stone-700">
                  {totalElements.toLocaleString()} total
                </p>
              </div>
            </div>
          </div>

          {levels.length > 0 && (
            <>
              <div className="border-b border-stone-100 px-5 py-3">
                <p className="text-xs font-bold uppercase tracking-[0.18em] text-stone-400">
                  Levels
                </p>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full min-w-[600px] border-collapse text-left text-sm">
                  <thead className="bg-stone-50 text-xs uppercase tracking-wider text-stone-400">
                    <tr>
                      <th className="px-5 py-3 font-bold">Level</th>
                      <th className="px-5 py-3 font-bold">Elevation</th>
                      <th className="px-5 py-3 font-bold">Height</th>
                      <th className="px-5 py-3 font-bold">Col</th>
                      <th className="px-5 py-3 font-bold">Wall</th>
                      <th className="px-5 py-3 font-bold">Beam</th>
                      <th className="px-5 py-3 font-bold">Floor</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-stone-100">
                    {levels.map((level) => (
                      <tr key={level.name} className="transition hover:bg-stone-50">
                        <td className="px-5 py-3 font-semibold text-stone-800">
                          {level.name}
                        </td>
                        <td className="px-5 py-3 text-stone-500">{level.elevation}</td>
                        <td className="px-5 py-3 text-stone-500">{level.height}</td>
                        <td className="px-5 py-3 text-stone-700">
                          {level.col > 0 ? level.col : "—"}
                        </td>
                        <td className="px-5 py-3 text-stone-700">
                          {level.wall > 0 ? level.wall : "—"}
                        </td>
                        <td className="px-5 py-3 text-stone-700">
                          {level.beam > 0 ? level.beam : "—"}
                        </td>
                        <td className="px-5 py-3 text-stone-700">
                          {level.floor > 0 ? level.floor : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {levels.length === 0 && (
            <div className="p-8 text-center">
              <p className="text-sm text-stone-400">No level data available for this project.</p>
            </div>
          )}
        </div>
      </section>
    </>
  );
}

export default ProjectDetail;
