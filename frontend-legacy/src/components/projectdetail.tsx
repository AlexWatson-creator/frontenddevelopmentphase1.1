import { useEffect, useState } from "react";
import { fetchProjectDetail } from "../api/projects";
import {
  deriveStatus,
  formatDate,
  getStatusClass,
  getStatusLabel,
  getTotalElements,
} from "../api/types";
import type {
  ProjectDetail as ApiProjectDetail,
  ProjectFileDetail,
  LevelWithCounts,
  ProjectGroup,
} from "../api/types";

function ProjectDetail({
  project,
  onBack,
  onRundown,
}: {
  project: ProjectGroup;
  onBack: () => void;
  onRundown: (fileId?: number, levelId?: number) => void;
}) {
  const [detail, setDetail] = useState<ApiProjectDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(true);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [expandedFiles, setExpandedFiles] = useState<Set<number>>(new Set());
  const [copiedFileId, setCopiedFileId] = useState<number | null>(null);
  const [copyErrorFileId, setCopyErrorFileId] = useState<number | null>(null);

  function toggleLevels(fileId: number) {
    setExpandedFiles((prev) => {
      const next = new Set(prev);
      if (next.has(fileId)) next.delete(fileId);
      else next.add(fileId);
      return next;
    });
  }

  function copyLevels(e: React.MouseEvent, file: ProjectFileDetail) {
    e.stopPropagation();
    const headers = [
      "Level",
      "Elevation (mm)",
      "Height (mm)",
      "Col",
      "Wall",
      "Beam",
      "Floor",
    ];
    const rows = file.levels.map((level) => [
      level.name,
      String(Math.round(level.elevation)),
      level.story_height != null ? String(level.story_height) : "—",
      level.counts.columns > 0 ? String(level.counts.columns) : "—",
      level.counts.walls > 0 ? String(level.counts.walls) : "—",
      level.counts.beams > 0 ? String(level.counts.beams) : "—",
      level.counts.floors > 0 ? String(level.counts.floors) : "—",
    ]);
    const tsv = [headers, ...rows].map((r) => r.join("\t")).join("\n");
    navigator.clipboard
      .writeText(tsv)
      .then(() => {
        setCopiedFileId(file.id);
        setTimeout(() => setCopiedFileId(null), 2000);
      })
      .catch(() => {
        setCopyErrorFileId(file.id);
        setTimeout(() => setCopyErrorFileId(null), 2000);
      });
  }

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
        {/* Back button */}
        <button
          onClick={onBack}
          className="mb-5 flex items-center gap-1.5 transition text-[#5C5D61] hover:text-[#CE1B22]"
          style={{ fontSize: "14.67px" }}
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
            {/* Headline — 30 pt = 40 px */}
            <div className="flex flex-wrap items-center gap-3">
              <h1
                className="font-bold tracking-tight text-[#231F20]"
                style={{ fontSize: "40px", lineHeight: "1.15" }}
              >
                {project.job_name ?? project.number}
              </h1>
              <span
                className={`rounded-full border px-3 py-1 text-xs font-extrabold ${getStatusClass(status)}`}
              >
                {getStatusLabel(status)}
              </span>
            </div>

            {/* Project number — eyebrow */}
            <p
              className="mt-1 font-semibold text-[#5C5D61]"
              style={{ fontSize: "14.67px" }}
            >
              {project.number}
            </p>

            {/* Meta row — file / element count / address */}
            <p className="mt-3 text-[#5C5D61]" style={{ fontSize: "14.67px" }}>
              <span className="font-semibold text-[#231F20]">
                {project.file_count}{" "}
                {project.file_count === 1 ? "file" : "files"}
              </span>
              <span className="mx-2 text-[#CFCCCC]">·</span>
              <span className="font-semibold text-[#231F20]">
                {totalElements.toLocaleString()} elements
              </span>
              {project.address && (
                <>
                  <span className="mx-2 text-[#CFCCCC]">·</span>
                  <span>{project.address}</span>
                </>
              )}
            </p>

            <p className="mt-1 text-[#5C5D61]" style={{ fontSize: "14.67px" }}>
              Lead: {project.designer ?? "—"}
            </p>
          </div>

          {/* Action buttons */}
          <div className="flex shrink-0 gap-3">
            <button
              onClick={() => onRundown()}
              className="rounded-lg bg-[#CE1B22] px-5 py-2.5 font-bold text-white shadow-sm transition hover:bg-[#ad151b]"
              style={{ fontSize: "14.67px" }}
            >
              Rundown
            </button>
            <button
              className="rounded-lg border border-[#CFCCCC] bg-white px-5 py-2.5 font-bold text-[#231F20] shadow-sm transition hover:bg-[#f8f6f3]"
              style={{ fontSize: "14.67px" }}
            >
              Delete Project
            </button>
          </div>
        </div>
      </header>

      <section>
        {/* Section label */}
        <p
          className="mb-3 font-bold uppercase tracking-[0.18em] text-[#5C5D61]"
          style={{ fontSize: "11px" }}
        >
          Files
        </p>

        {/* Loading state */}
        {loadingDetail && (
          <div className="flex items-center justify-center rounded-xl border border-[#CFCCCC] bg-white py-16 shadow-sm">
            <div className="h-6 w-6 animate-spin rounded-full border-4 border-[#CFCCCC] border-t-[#CE1B22]" />
            <span
              className="ml-3 text-[#5C5D61]"
              style={{ fontSize: "14.67px" }}
            >
              Loading file data…
            </span>
          </div>
        )}

        {/* Error state */}
        {detailError && (
          <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-center">
            <p
              className="font-semibold text-red-700"
              style={{ fontSize: "14.67px" }}
            >
              Failed to load project detail
            </p>
            <p className="mt-1 text-red-600" style={{ fontSize: "12px" }}>
              {detailError}
            </p>
          </div>
        )}

        {/* File cards */}
        {detail &&
          detail.files.map((file: ProjectFileDetail) => {
            const fileTotalElements = getTotalElements(file.counts);
            return (
              <div
                key={file.id}
                className="mb-5 overflow-hidden rounded-xl border border-[#CFCCCC] bg-white shadow-sm"
              >
                <div className="border-b border-[#CFCCCC] p-5">
                  <div className="flex flex-col justify-between gap-4 sm:flex-row sm:items-start">
                    <div>
                      {/* File name — sub-header 13 pt */}
                      <div className="flex flex-wrap items-center gap-3">
                        <h2
                          className="font-bold text-[#231F20]"
                          style={{ fontSize: "17.33px" }}
                        >
                          {file.file_name ?? project.number}
                        </h2>
                        {file.software && (
                          <span
                            className="rounded border border-[#CFCCCC] bg-[#f8f6f3] px-2 py-0.5 font-bold uppercase tracking-wider text-[#5C5D61]"
                            style={{ fontSize: "10px" }}
                          >
                            {file.software}
                          </span>
                        )}
                      </div>

                      {/* File location */}
                      {file.file_location && (
                        <p
                          className="mt-1.5 text-[#5C5D61]"
                          style={{ fontSize: "14.67px" }}
                        >
                          {file.file_location}
                        </p>
                      )}

                      {/* Element counts */}
                      <p
                        className="mt-2.5 text-[#231F20]"
                        style={{ fontSize: "14.67px" }}
                      >
                        <span className="font-semibold">
                          {file.counts.columns}
                        </span>{" "}
                        col
                        <span className="mx-2 text-[#CFCCCC]">·</span>
                        <span className="font-semibold">
                          {file.counts.walls}
                        </span>{" "}
                        wall
                        <span className="mx-2 text-[#CFCCCC]">·</span>
                        <span className="font-semibold">
                          {file.counts.beams}
                        </span>{" "}
                        beam
                        <span className="mx-2 text-[#CFCCCC]">·</span>
                        <span className="font-semibold">
                          {file.counts.floors}
                        </span>{" "}
                        flr
                      </p>

                      {/* Last updated */}
                      <p
                        className="mt-1.5 text-[#5C5D61]"
                        style={{ fontSize: "14.67px" }}
                      >
                        Updated {formatDate(file.last_run_time)}
                      </p>
                    </div>

                    {/* Right side: action links + total */}
                    <div className="flex shrink-0 flex-col items-end gap-2">
                      <div className="flex items-center gap-4">
                        <button
                          className="font-semibold text-[#CE1B22] transition hover:underline"
                          style={{ fontSize: "14.67px" }}
                        >
                          Load Table
                        </button>
                        <button
                          className="transition text-[#5C5D61] hover:text-[#231F20]"
                          style={{ fontSize: "14.67px" }}
                        >
                          Delete
                        </button>
                      </div>
                      <p
                        className="font-bold text-[#231F20]"
                        style={{ fontSize: "14.67px" }}
                      >
                        {fileTotalElements.toLocaleString()} total
                      </p>
                    </div>
                  </div>
                </div>

                {/* Levels toggle */}
                {file.levels.length > 0 && (
                  <>
                    <div
                      className="flex cursor-pointer items-center justify-between border-t border-[#CFCCCC] px-5 py-3 transition hover:bg-[#f8f6f3]"
                      onClick={() => toggleLevels(file.id)}
                    >
                      <p
                        className="font-bold uppercase tracking-[0.18em] text-[#5C5D61]"
                        style={{ fontSize: "11px" }}
                      >
                        Levels ({file.levels.length})
                      </p>
                      <div className="flex items-center gap-3">
                        <button
                          onClick={(e) => copyLevels(e, file)}
                          className={`rounded px-2.5 py-1 font-semibold transition ${
                            copiedFileId === file.id
                              ? "bg-green-100 text-green-700"
                              : copyErrorFileId === file.id
                                ? "bg-red-100 text-red-700"
                                : "border border-[#CFCCCC] bg-white text-[#5C5D61] hover:border-[#CE1B22] hover:text-[#CE1B22]"
                          }`}
                          style={{ fontSize: "11px" }}
                        >
                          {copiedFileId === file.id
                            ? "Copied!"
                            : copyErrorFileId === file.id
                              ? "Copy failed"
                              : "Copy Table"}
                        </button>
                        <svg
                          className={`h-4 w-4 text-[#5C5D61] transition-transform duration-200 ${
                            expandedFiles.has(file.id) ? "rotate-180" : ""
                          }`}
                          fill="none"
                          viewBox="0 0 24 24"
                          stroke="currentColor"
                          strokeWidth={2}
                        >
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            d="M19 9l-7 7-7-7"
                          />
                        </svg>
                      </div>
                    </div>

                    {expandedFiles.has(file.id) && (
                      <div className="overflow-x-auto">
                        <table
                          className="w-full min-w-[600px] border-collapse text-left"
                          style={{ fontSize: "14.67px" }}
                        >
                          <thead
                            className="bg-[#f8f6f3] uppercase tracking-wider text-[#5C5D61]"
                            style={{ fontSize: "11px" }}
                          >
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
                          <tbody className="divide-y divide-[#CFCCCC]">
                            {file.levels.map((level: LevelWithCounts) => (
                              <tr
                                key={level.id}
                                className="odd:bg-white even:bg-[#f8f6f3] transition hover:brightness-95 cursor-pointer"
                                onClick={() => onRundown(file.id, level.id)}
                              >
                                <td className="px-5 py-3 font-semibold text-[#231F20]">
                                  {level.name}
                                </td>
                                <td className="px-5 py-3 text-[#5C5D61]">
                                  {Math.round(level.elevation).toLocaleString()}{" "}
                                  mm
                                </td>
                                <td className="px-5 py-3 text-[#5C5D61]">
                                  {level.story_height != null
                                    ? `${level.story_height.toLocaleString()} mm`
                                    : "—"}
                                </td>
                                <td className="px-5 py-3 text-[#231F20]">
                                  {level.counts.columns > 0
                                    ? level.counts.columns
                                    : "—"}
                                </td>
                                <td className="px-5 py-3 text-[#231F20]">
                                  {level.counts.walls > 0
                                    ? level.counts.walls
                                    : "—"}
                                </td>
                                <td className="px-5 py-3 text-[#231F20]">
                                  {level.counts.beams > 0
                                    ? level.counts.beams
                                    : "—"}
                                </td>
                                <td className="px-5 py-3 text-[#231F20]">
                                  {level.counts.floors > 0
                                    ? level.counts.floors
                                    : "—"}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </>
                )}
              </div>
            );
          })}
      </section>
    </>
  );
}

export default ProjectDetail;
