import { useEffect, useState } from "react";
import { fetchProjectDetail } from "../api/projects";
import {
  deriveStatus,
  formatDate,
  getStatusClass,
  getStatusLabel,
  getTotalElements,
} from "../api/types";
import type { ProjectDetail as ApiProjectDetail, ProjectFileDetail, LevelWithCounts, ProjectGroup } from "../api/types";

function ProjectDetail({
  project,
  onBack,
  onRundown,
}: {
  project: ProjectGroup;
  onBack: () => void;
  onRundown: () => void;
}) {
  const [detail, setDetail] = useState<ApiProjectDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(true);
  const [detailError, setDetailError] = useState<string | null>(null);

  useEffect(() => {
    setLoadingDetail(true);
    setDetailError(null);
    fetchProjectDetail(project.number)
      .then(setDetail)
      .catch((err: unknown) =>
        setDetailError(err instanceof Error ? err.message : "Unknown error"),
      )
      .finally(() => setLoadingDetail(false));
  }, [project.number]);

  const status = deriveStatus(project.last_run_time);
  const totalElements = getTotalElements(project.counts);

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
              <h1 className="text-4xl font-bold tracking-tight">
                {project.job_name ?? project.number}
              </h1>
              <span
                className={`rounded-full border px-3 py-1 text-xs font-extrabold ${getStatusClass(status)}`}
              >
                {getStatusLabel(status)}
              </span>
            </div>

            <p className="mt-1 text-sm font-semibold text-stone-400">
              {project.number}
            </p>

            <p className="mt-3 text-sm text-stone-500">
              <span className="font-semibold text-stone-700">
                {project.file_count}{" "}
                {project.file_count === 1 ? "file" : "files"}
              </span>
              <span className="mx-2 text-stone-300">·</span>
              <span className="font-semibold text-stone-700">
                {totalElements.toLocaleString()} elements
              </span>
              {project.address && (
                <>
                  <span className="mx-2 text-stone-300">·</span>
                  <span>{project.address}</span>
                </>
              )}
            </p>

            <p className="mt-1 text-sm text-stone-400">
              Lead: {project.designer ?? "—"}
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

        {loadingDetail && (
          <div className="flex items-center justify-center rounded-xl border border-stone-200 bg-white py-16 shadow-sm">
            <div className="h-6 w-6 animate-spin rounded-full border-4 border-stone-200 border-t-[#ce1b22]" />
            <span className="ml-3 text-stone-500">Loading file data…</span>
          </div>
        )}

        {detailError && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-center">
            <p className="text-sm font-semibold text-red-700">
              Failed to load project detail
            </p>
            <p className="mt-1 text-xs text-red-600">{detailError}</p>
          </div>
        )}

        {detail &&
          detail.files.map((file: ProjectFileDetail) => {
            const fileTotalElements = getTotalElements(file.counts);
            return (
              <div
                key={file.id}
                className="mb-5 overflow-hidden rounded-xl border border-stone-200 bg-white shadow-sm"
              >
                <div className="border-b border-stone-200 p-5">
                  <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
                    <div>
                      <div className="flex flex-wrap items-center gap-3">
                        <h2 className="text-base font-bold text-stone-800">
                          {file.file_name ?? project.number}
                        </h2>
                        {file.software && (
                          <span className="rounded border border-stone-200 bg-stone-100 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-stone-500">
                            {file.software}
                          </span>
                        )}
                      </div>

                      {file.file_location && (
                        <p className="mt-1.5 text-xs text-stone-400">
                          {file.file_location}
                        </p>
                      )}

                      <p className="mt-2.5 text-xs text-stone-600">
                        <span className="font-semibold">
                          {file.counts.columns}
                        </span>{" "}
                        col
                        <span className="mx-2 text-stone-300">·</span>
                        <span className="font-semibold">
                          {file.counts.walls}
                        </span>{" "}
                        wall
                        <span className="mx-2 text-stone-300">·</span>
                        <span className="font-semibold">
                          {file.counts.beams}
                        </span>{" "}
                        beam
                        <span className="mx-2 text-stone-300">·</span>
                        <span className="font-semibold">
                          {file.counts.floors}
                        </span>{" "}
                        flr
                      </p>

                      <p className="mt-1.5 text-xs text-stone-400">
                        Updated {formatDate(file.last_run_time)}
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
                        {fileTotalElements.toLocaleString()} total
                      </p>
                    </div>
                  </div>
                </div>

                {file.levels.length > 0 && (
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
                          {file.levels.map((level: LevelWithCounts) => (
                            <tr
                              key={level.id}
                              className="transition hover:bg-stone-50"
                            >
                              <td className="px-5 py-3 font-semibold text-stone-800">
                                {level.name}
                              </td>
                              <td className="px-5 py-3 text-stone-500">
                                {Math.round(level.elevation).toLocaleString()} mm
                              </td>
                              <td className="px-5 py-3 text-stone-500">
                                {level.story_height != null
                                  ? `${level.story_height.toLocaleString()} mm`
                                  : "—"}
                              </td>
                              <td className="px-5 py-3 text-stone-700">
                                {level.counts.columns > 0
                                  ? level.counts.columns
                                  : "—"}
                              </td>
                              <td className="px-5 py-3 text-stone-700">
                                {level.counts.walls > 0
                                  ? level.counts.walls
                                  : "—"}
                              </td>
                              <td className="px-5 py-3 text-stone-700">
                                {level.counts.beams > 0
                                  ? level.counts.beams
                                  : "—"}
                              </td>
                              <td className="px-5 py-3 text-stone-700">
                                {level.counts.floors > 0
                                  ? level.counts.floors
                                  : "—"}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}

                {file.levels.length === 0 && (
                  <div className="p-8 text-center">
                    <p className="text-sm text-stone-400">
                      No level data available for this file.
                    </p>
                  </div>
                )}
              </div>
            );
          })}
      </section>
    </>
  );
}

export default ProjectDetail;
