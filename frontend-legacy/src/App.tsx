import { useState } from "react";
import jppLogo from "./assets/jpp.png";
import "./App.css";
import Projects from "./components/projects";
import ProjectDetail from "./components/projectdetail";
import RundownWorkspace from "./pages/RundownWorkspace";
import type { ProjectGroup } from "./api/types";

const TEST_USERS = [
  { email: "admin@jablonsky.ca", password: "Jpp@2024!", name: "Admin User" },
];

type User = { email: string; name: string };

function LoginPage({ onLogin }: { onLogin: (user: User) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  function handleSubmit(e: { preventDefault(): void }) {
    e.preventDefault();
    setError("");
    setLoading(true);
    setTimeout(() => {
      const match = TEST_USERS.find(
        (u) => u.email === email.trim().toLowerCase() && u.password === password
      );
      if (match) {
        onLogin({ email: match.email, name: match.name });
      } else {
        setError("Invalid email or password.");
      }
      setLoading(false);
    }, 400);
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#f8f6f3] px-4">
      {/* Card */}
      <div className="w-full max-w-sm rounded-2xl bg-white p-8 shadow-lg">
        {/* Brand */}
        <div className="mb-8 flex items-center gap-3">
          <div className="grid h-11 w-11 flex-shrink-0 place-items-center overflow-hidden rounded-lg bg-[#CE1B22]">
            <img src={jppLogo} alt="JPP logo" className="h-full w-full object-cover" />
          </div>
          <div>
            <p className="font-bold text-[#231F20]" style={{ fontSize: "17.33px" }}>
              Jablonsky
            </p>
            <p className="text-[#5C5D61]" style={{ fontSize: "12px" }}>
              Data Platform
            </p>
          </div>
        </div>

        <h1 className="mb-1 font-bold text-[#231F20]" style={{ fontSize: "22px" }}>
          Sign in to your account
        </h1>
        <p className="mb-7 text-[#5C5D61]" style={{ fontSize: "14px" }}>
          Enter your credentials to access the platform.
        </p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <label className="font-medium text-[#231F20]" style={{ fontSize: "13px" }}>
              Email address
            </label>
            <input
              type="email"
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              required
              className="h-11 rounded-lg border border-[#CFCCCC] px-4 outline-none transition placeholder:text-[#CFCCCC] focus:border-[#CE1B22] focus:ring-2 focus:ring-[#CE1B22]/10"
              style={{ fontSize: "14.67px", color: "#231F20" }}
            />
          </div>

          <div className="flex flex-col gap-1">
            <label className="font-medium text-[#231F20]" style={{ fontSize: "13px" }}>
              Password
            </label>
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              required
              className="h-11 rounded-lg border border-[#CFCCCC] px-4 outline-none transition placeholder:text-[#CFCCCC] focus:border-[#CE1B22] focus:ring-2 focus:ring-[#CE1B22]/10"
              style={{ fontSize: "14.67px", color: "#231F20" }}
            />
          </div>

          {error && (
            <p
              className="rounded-lg bg-red-50 px-3 py-2 text-[#CE1B22]"
              style={{ fontSize: "13px" }}
            >
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="mt-1 h-11 rounded-lg bg-[#CE1B22] font-bold text-white transition hover:bg-[#ad151b] disabled:opacity-60"
            style={{ fontSize: "14.67px" }}
          >
            {loading ? "Signing in…" : "Sign in"}
          </button>
        </form>
      </div>
    </div>
  );
}

function Dashboard({
  user,
  onLogout,
}: {
  user: User;
  onLogout: () => void;
}) {
  const [page, setPage] = useState("projects");
  const [selectedProject, setSelectedProject] = useState<ProjectGroup | null>(null);
  const [rundownProject, setRundownProject] = useState<ProjectGroup | null>(null);
  const [rundownFileId, setRundownFileId] = useState<number | undefined>(undefined);
  const [rundownLevelId, setRundownLevelId] = useState<number | undefined>(undefined);
  const [sidebarOpen, setSidebarOpen] = useState(true);

  const initials = user.name
    .split(" ")
    .map((n) => n[0])
    .join("")
    .toUpperCase()
    .slice(0, 2);

  return (
    <main className="min-h-screen bg-[#f8f6f3] text-[#231F20] lg:flex">
      {/* Sidebar */}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex flex-col bg-[#302D27] text-white transition-all duration-300 ease-in-out ${
          sidebarOpen ? "w-64" : "w-16"
        }`}
      >
        {/* Toggle */}
        <button
          onClick={() => setSidebarOpen((o) => !o)}
          className="mt-4 ml-auto mr-3 flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-md text-[#CFCCCC] transition hover:bg-white/10 hover:text-white"
          aria-label={sidebarOpen ? "Collapse sidebar" : "Expand sidebar"}
        >
          {sidebarOpen ? (
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="15 18 9 12 15 6" />
            </svg>
          ) : (
            <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="9 18 15 12 9 6" />
            </svg>
          )}
        </button>

        <div className="flex flex-1 flex-col justify-between overflow-hidden px-3 pb-6">
          <div>
            {/* Brand mark */}
            <div className="mb-10 flex items-center gap-3 overflow-hidden">
              <div className="grid h-11 w-11 flex-shrink-0 place-items-center overflow-hidden rounded-lg bg-[#CE1B22]">
                <img src={jppLogo} alt="JPP logo" className="h-full w-full object-cover" />
              </div>
              {sidebarOpen && (
                <div className="min-w-0">
                  <h2 className="truncate font-bold tracking-wide text-white" style={{ fontSize: "17.33px" }}>
                    Jablonsky
                  </h2>
                  <p className="truncate text-[#CFCCCC]" style={{ fontSize: "14.67px" }}>
                    Data Platform
                  </p>
                </div>
              )}
            </div>

            {/* Navigation */}
            <nav className="flex flex-col gap-2">
              {[
                {
                  label: "Projects",
                  action: () => { setPage("projects"); setSelectedProject(null); },
                  active: page === "projects",
                  icon: <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>,
                },
                {
                  label: "Uploads",
                  action: undefined,
                  active: false,
                  icon: <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/><path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/></svg>,
                },
                {
                  label: "Validation",
                  action: undefined,
                  active: false,
                  icon: <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"/></svg>,
                },
                {
                  label: "Settings",
                  action: undefined,
                  active: false,
                  icon: <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>,
                },
              ].map(({ label, action, active, icon }) => (
                <a
                  key={label}
                  href="#"
                  onClick={action}
                  title={!sidebarOpen ? label : undefined}
                  className={`flex items-center gap-3 rounded-lg px-3 py-3 font-medium transition ${
                    active ? "bg-white/10 text-white" : "text-[#CFCCCC] hover:bg-white/10 hover:text-white"
                  } ${!sidebarOpen ? "justify-center" : ""}`}
                  style={{ fontSize: "14.67px" }}
                >
                  <span className="flex-shrink-0">{icon}</span>
                  {sidebarOpen && <span className="truncate">{label}</span>}
                </a>
              ))}
            </nav>
          </div>

          {/* User profile + sign out */}
          <div className="border-t border-white/10 pt-4">
            <div className={`flex flex-col gap-1 ${!sidebarOpen ? "items-center" : ""}`}>
              <div
                className={`flex items-center gap-3 rounded-lg px-3 py-2 ${!sidebarOpen ? "justify-center" : ""}`}
                title={!sidebarOpen ? user.name : undefined}
              >
                <div className="grid h-8 w-8 flex-shrink-0 place-items-center rounded-full bg-[#CE1B22] text-xs font-bold text-white">
                  {initials}
                </div>
                {sidebarOpen && (
                  <div className="min-w-0">
                    <p className="truncate font-medium text-white" style={{ fontSize: "13px" }}>
                      {user.name}
                    </p>
                    <p className="truncate text-[#CFCCCC]" style={{ fontSize: "11px" }}>
                      {user.email}
                    </p>
                  </div>
                )}
              </div>
              <button
                onClick={onLogout}
                title={!sidebarOpen ? "Sign out" : undefined}
                className={`flex w-full items-center gap-3 rounded-lg px-3 py-2 font-medium text-[#CFCCCC] transition hover:bg-white/10 hover:text-white ${!sidebarOpen ? "justify-center" : ""}`}
                style={{ fontSize: "13px" }}
              >
                <span className="flex-shrink-0">
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
                    <polyline points="16 17 21 12 16 7"/>
                    <line x1="21" y1="12" x2="9" y2="12"/>
                  </svg>
                </span>
                {sidebarOpen && <span>Sign out</span>}
              </button>
            </div>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <section
        className={`w-full p-5 transition-all duration-300 ease-in-out lg:p-8 ${
          sidebarOpen ? "lg:ml-64" : "lg:ml-16"
        }`}
      >
        {page === "projects" && selectedProject && (
          <ProjectDetail
            project={selectedProject}
            onBack={() => setSelectedProject(null)}
            onRundown={(fileId, levelId) => {
              setRundownFileId(fileId);
              setRundownLevelId(levelId);
              setRundownProject(selectedProject);
            }}
          />
        )}
        {page === "projects" && !selectedProject && (
          <Projects onSelectProject={(p) => { setSelectedProject(p); setPage("projects"); }} />
        )}
      </section>

      {/* Full-screen Rundown drawing workspace overlay */}
      {rundownProject && (
        <RundownWorkspace
          project={rundownProject}
          onBack={() => setRundownProject(null)}
          initialFileId={rundownFileId}
          initialLevelId={rundownLevelId}
        />
      )}
    </main>
  );
}

function App() {
  const [user, setUser] = useState<User | null>(null);

  if (!user) {
    return <LoginPage onLogin={setUser} />;
  }

  return <Dashboard user={user} onLogout={() => setUser(null)} />;
}

export default App;
