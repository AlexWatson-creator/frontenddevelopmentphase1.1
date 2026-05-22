import { useState } from "react";
import jppLogo from "./assets/jpp.png";
import "./App.css";
import Rundown from "./components/rundown";
import Projects from "./components/projects";
import ProjectDetail from "./components/projectdetail";
import Login from "./components/login";
import Settings from "./components/settings";
import type { ProjectGroup } from "./api/types";
import type { UserRead } from "./api/users";

function App() {
  const [page, setPage] = useState<"projects" | "rundown" | "settings" | "login">("projects");
  const [selectedProject, setSelectedProject] = useState<ProjectGroup | null>(null);
  const [loggedInUser, setLoggedInUser] = useState<UserRead | null>(() => {
    const saved = localStorage.getItem("currentUser");
    return saved ? (JSON.parse(saved) as UserRead) : null;
  });

  const isLoggedIn = !!loggedInUser;

  function handleSelectProject(project: ProjectGroup) {
    setSelectedProject(project);
    setPage("projects");
  }

  function handleBack() {
    setSelectedProject(null);
  }

  function handleLogin(user: UserRead) {
    localStorage.setItem("currentUser", JSON.stringify(user));
    setLoggedInUser(user);
    setPage("projects");
  }

  function handleLogout() {
    localStorage.removeItem("currentUser");
    setLoggedInUser(null);
    setPage("projects");
  }

  return (
    <main className="min-h-screen bg-[#f8f6f3] text-[#302d27] lg:flex">
      <aside className="flex flex-col bg-[#302d27] p-6 text-white lg:fixed lg:inset-y-0 lg:left-0 lg:w-64">
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

          {(isLoggedIn &&
            <a
              href="#"
              onClick={() => { setPage("settings"); setSelectedProject(null); }}
              className={`rounded-lg px-3 py-3 text-sm font-medium ${page === "settings" ? "bg-white/10 text-white" : "text-stone-300 hover:bg-white/10 hover:text-white"}`}
            >
              Settings
            </a>
          )}
        </nav>

        <div className="mt-auto border-t border-white/10 pt-5">
          <div className="mb-3 flex items-center gap-3 px-1">
            {loggedInUser ? (
              <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-[#ce1b22] text-sm font-bold text-white">
                {loggedInUser.email[0].toUpperCase()}
              </div>
            ) : (
              <div className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-white/10">
                <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="h-5 w-5 text-stone-400">
                  <path fillRule="evenodd" d="M7.5 6a4.5 4.5 0 1 1 9 0 4.5 4.5 0 0 1-9 0ZM3.751 20.105a8.25 8.25 0 0 1 16.498 0 .75.75 0 0 1-.437.695A18.683 18.683 0 0 1 12 22.5c-2.786 0-5.433-.608-7.812-1.7a.75.75 0 0 1-.437-.695Z" clipRule="evenodd" />
                </svg>
              </div>
            )}
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-white">
                {loggedInUser?.email ?? "Not signed in"}
              </p>
              <p className="text-xs text-stone-400">
                {loggedInUser ? "Signed in" : "Guest"}
              </p>
            </div>
          </div>

          {loggedInUser ? (
            <button
              onClick={handleLogout}
              className="w-full rounded-lg border border-white/20 px-3 py-2 text-sm font-medium text-stone-300 transition hover:bg-white/10 hover:text-white"
            >
              Sign out
            </button>
          ) : (
            <button
              onClick={() => setPage("login")}
              className="w-full rounded-lg bg-[#ce1b22] px-3 py-2 text-sm font-semibold text-white transition hover:bg-[#b01820]"
            >
              Sign in
            </button>
          )}
        </div>
      </aside>

      <section className="w-full p-5 lg:ml-64 lg:p-8">
        {page === "login" && <Login onLogin={handleLogin} />}
        {page === "rundown" && <Rundown />}
        {page === "settings" && <Settings />}
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
