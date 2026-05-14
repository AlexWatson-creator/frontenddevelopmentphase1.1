import { useState } from "react";
import jppLogo from "./assets/jpp.png";
import "./App.css";
import Rundown from "./components/rundown";
import Projects from "./components/projects";
import ProjectDetail from "./components/projectdetail";
import type { ProjectGroup } from "./api/types";

function App() {
  const [page, setPage] = useState<"projects" | "rundown">("projects");
  const [selectedProject, setSelectedProject] = useState<ProjectGroup | null>(null);

  function handleSelectProject(project: ProjectGroup) {
    setSelectedProject(project);
    setPage("projects");
  }

  function handleBack() {
    setSelectedProject(null);
  }

  return (
    <main className="min-h-screen bg-[#f8f6f3] text-[#302d27] lg:flex">
      <aside className="bg-[#302d27] p-6 text-white lg:fixed lg:inset-y-0 lg:left-0 lg:w-64">
        <div className="mb-10 flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center overflow-hidden rounded-lg bg-[#ce1b22]">
            <img
              src={jppLogo}
              alt="JPP logo"
              className="h-full w-full object-cover"
            />
          </div>

          <div>
            <h2 className="text-lg font-bold tracking-wide">Jablonsky</h2>
            <p className="text-xs text-stone-300">Data Platform</p>
          </div>
        </div>

        <nav className="flex flex-col gap-2">
          <a
            href="#"
            onClick={() => { setPage("projects"); setSelectedProject(null); }}
            className={`rounded-lg px-3 py-3 text-sm font-medium ${page === "projects" ? "bg-white/10 text-white" : "text-stone-300 hover:bg-white/10 hover:text-white"}`}
          >
            Projects
          </a>

          <a
            href="#"
            onClick={() => { setPage("rundown"); setSelectedProject(null); }}
            className={`rounded-lg px-3 py-3 text-sm font-medium ${page === "rundown" ? "bg-white/10 text-white" : "text-stone-300 hover:bg-white/10 hover:text-white"}`}
          >
            Load Rundown
          </a>

          <a
            href="#"
            className="rounded-lg px-3 py-3 text-sm font-medium text-stone-300 hover:bg-white/10 hover:text-white"
          >
            Uploads
          </a>

          <a
            href="#"
            className="rounded-lg px-3 py-3 text-sm font-medium text-stone-300 hover:bg-white/10 hover:text-white"
          >
            Validation
          </a>

          <a
            href="#"
            className="rounded-lg px-3 py-3 text-sm font-medium text-stone-300 hover:bg-white/10 hover:text-white"
          >
            Settings
          </a>
        </nav>
      </aside>

      <section className="w-full p-5 lg:ml-64 lg:p-8">
        {page === "rundown" && <Rundown />}
        {page === "projects" && selectedProject && (
          <ProjectDetail
            project={selectedProject}
            onBack={handleBack}
            onRundown={() => { setPage("rundown"); setSelectedProject(null); }}
          />
        )}
        {page === "projects" && !selectedProject && (
          <Projects onSelectProject={handleSelectProject} />
        )}
      </section>
    </main>
  );
}

export default App;
