import { useMemo, useState } from "react";

type LoadStatus = "passed" | "warning" | "failed";

type LoadItem = {
  id: string;

  level: string;

  element: string;

  elementType: "Column" | "Wall" | "Beam" | "Slab";

  gridLine: string;

  deadLoad: number;

  liveLoad: number;

  snowLoad: number;

  windLoad: number;

  totalLoad: number;

  status: LoadStatus;
};

const loadItems: LoadItem[] = [
  {
    id: "LR-001",

    level: "Roof",

    element: "C-ROOF-014",

    elementType: "Column",

    gridLine: "A-4",

    deadLoad: 82.4,

    liveLoad: 30.2,

    snowLoad: 48.7,

    windLoad: 12.5,

    totalLoad: 173.8,

    status: "passed",
  },

  {
    id: "LR-002",

    level: "Level 05",

    element: "W-L05-008",

    elementType: "Wall",

    gridLine: "B-7",

    deadLoad: 140.9,

    liveLoad: 58.4,

    snowLoad: 0,

    windLoad: 24.3,

    totalLoad: 223.6,

    status: "warning",
  },

  {
    id: "LR-003",

    level: "Level 04",

    element: "B-L04-021",

    elementType: "Beam",

    gridLine: "C-2",

    deadLoad: 66.8,

    liveLoad: 42.5,

    snowLoad: 0,

    windLoad: 10.1,

    totalLoad: 119.4,

    status: "passed",
  },

  {
    id: "LR-004",

    level: "Level 03",

    element: "S-L03-003",

    elementType: "Slab",

    gridLine: "D-9",

    deadLoad: 210.5,

    liveLoad: 95.2,

    snowLoad: 0,

    windLoad: 18.6,

    totalLoad: 324.3,

    status: "failed",
  },

  {
    id: "LR-005",

    level: "Level 02",

    element: "C-L02-017",

    elementType: "Column",

    gridLine: "E-5",

    deadLoad: 188.1,

    liveLoad: 70.4,

    snowLoad: 0,

    windLoad: 21.9,

    totalLoad: 280.4,

    status: "warning",
  },

  {
    id: "LR-006",

    level: "Level 01",

    element: "W-L01-002",

    elementType: "Wall",

    gridLine: "F-1",

    deadLoad: 260.7,

    liveLoad: 122.6,

    snowLoad: 0,

    windLoad: 30.5,

    totalLoad: 413.8,

    status: "passed",
  },
];

function getStatusClass(status: LoadStatus) {
  if (status === "passed") {
    return "border-green-200 bg-green-50 text-green-700";
  }

  if (status === "warning") {
    return "border-yellow-200 bg-yellow-50 text-yellow-700";
  }

  return "border-red-200 bg-red-50 text-red-700";
}

function getStatusLabel(status: LoadStatus) {
  if (status === "passed") return "Passed";

  if (status === "warning") return "Warning";

  return "Failed";
}

function Rundown() {
  const [search, setSearch] = useState("");

  const [elementType, setElementType] = useState("all");

  const [status, setStatus] = useState("all");

  const filteredLoadItems = useMemo(() => {
    return loadItems.filter((item) => {
      const searchText = search.toLowerCase();

      const matchesSearch =
        item.id.toLowerCase().includes(searchText) ||
        item.level.toLowerCase().includes(searchText) ||
        item.element.toLowerCase().includes(searchText) ||
        item.elementType.toLowerCase().includes(searchText) ||
        item.gridLine.toLowerCase().includes(searchText);

      const matchesElementType =
        elementType === "all" || item.elementType === elementType;

      const matchesStatus = status === "all" || item.status === status;

      return matchesSearch && matchesElementType && matchesStatus;
    });
  }, [search, elementType, status]);

  const stats = useMemo(() => {
    const totalLoad = loadItems.reduce((total, item) => {
      return total + item.totalLoad;
    }, 0);

    const passed = loadItems.filter((item) => item.status === "passed").length;

    const warnings = loadItems.filter(
      (item) => item.status === "warning",
    ).length;

    const failed = loadItems.filter((item) => item.status === "failed").length;

    return {
      totalItems: loadItems.length,

      totalLoad,

      passed,

      warnings,

      failed,
    };
  }, []);

  return (
    <section className="min-h-screen bg-[#f8f6f3] p-5 text-[#302d27] lg:p-8">
      <header className="mb-6 flex flex-col justify-between gap-5 md:flex-row md:items-start">
        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-[0.18em] text-stone-500">
            Structural Analysis
          </p>

          <h1 className="text-3xl font-bold tracking-tight md:text-4xl">
            Load Rundown
          </h1>

          <p className="mt-2 max-w-2xl leading-6 text-stone-500">
            Review element-level loads across floors, gridlines, and structural
            systems. Track dead, live, snow, and wind loads from one workspace.
          </p>
        </div>

        <div className="flex gap-3">
          <button className="rounded-lg border border-stone-300 bg-white px-4 py-3 text-sm font-bold text-stone-700 shadow-sm transition hover:bg-stone-50">
            Export CSV
          </button>

          <button className="rounded-lg bg-[#ce1b22] px-4 py-3 text-sm font-bold text-white shadow-sm transition hover:bg-[#ad151b]">
            Run Validation
          </button>
        </div>
      </header>

      <section className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-wider text-stone-500">
            Total Items
          </p>
          <h3 className="my-3 text-3xl font-bold">{stats.totalItems}</h3>
          <span className="text-sm text-stone-500">
            Elements included in rundown
          </span>
        </div>

        <div className="rounded-xl border border-l-4 border-stone-200 border-l-[#ce1b22] bg-white p-5 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-wider text-stone-500">
            Total Load
          </p>
          <h3 className="my-3 text-3xl font-bold">
            {stats.totalLoad.toFixed(1)}
          </h3>
          <span className="text-sm text-stone-500">Combined load value</span>
        </div>

        <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-wider text-stone-500">
            Passed
          </p>
          <h3 className="my-3 text-3xl font-bold text-green-700">
            {stats.passed}
          </h3>
          <span className="text-sm text-stone-500">No issues detected</span>
        </div>

        <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-sm">
          <p className="text-xs font-bold uppercase tracking-wider text-stone-500">
            Needs Review
          </p>
          <h3 className="my-3 text-3xl font-bold text-yellow-700">
            {stats.warnings + stats.failed}
          </h3>
          <span className="text-sm text-stone-500">
            Warnings and failed checks
          </span>
        </div>
      </section>

      <section className="mb-5 rounded-xl border border-stone-200 bg-white p-4 shadow-sm">
        <div className="grid gap-3 md:grid-cols-[1fr_180px_180px]">
          <input
            type="text"
            placeholder="Search by level, element, gridline..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="h-11 rounded-lg border border-stone-300 bg-white px-4 text-sm outline-none transition placeholder:text-stone-400 focus:border-[#ce1b22] focus:ring-2 focus:ring-[#ce1b22]/10"
          />

          <select
            value={elementType}
            onChange={(event) => setElementType(event.target.value)}
            className="h-11 rounded-lg border border-stone-300 bg-white px-4 text-sm outline-none transition focus:border-[#ce1b22] focus:ring-2 focus:ring-[#ce1b22]/10"
          >
            <option value="all">All elements</option>
            <option value="Column">Column</option>
            <option value="Wall">Wall</option>
            <option value="Beam">Beam</option>
            <option value="Slab">Slab</option>
          </select>

          <select
            value={status}
            onChange={(event) => setStatus(event.target.value)}
            className="h-11 rounded-lg border border-stone-300 bg-white px-4 text-sm outline-none transition focus:border-[#ce1b22] focus:ring-2 focus:ring-[#ce1b22]/10"
          >
            <option value="all">All statuses</option>
            <option value="passed">Passed</option>
            <option value="warning">Warning</option>
            <option value="failed">Failed</option>
          </select>
        </div>
      </section>

      <section className="overflow-hidden rounded-xl border border-stone-200 bg-white shadow-sm">
        <div className="border-b border-stone-200 px-5 py-4">
          <h2 className="text-lg font-bold">Load Rundown Table</h2>
          <p className="mt-1 text-sm text-stone-500">
            Showing {filteredLoadItems.length} of {loadItems.length} records.
          </p>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[980px] border-collapse text-left text-sm">
            <thead className="bg-stone-50 text-xs uppercase tracking-wider text-stone-500">
              <tr>
                <th className="px-5 py-4 font-bold">ID</th>
                <th className="px-5 py-4 font-bold">Level</th>
                <th className="px-5 py-4 font-bold">Element</th>
                <th className="px-5 py-4 font-bold">Type</th>
                <th className="px-5 py-4 font-bold">Grid</th>
                <th className="px-5 py-4 font-bold">Dead</th>
                <th className="px-5 py-4 font-bold">Live</th>
                <th className="px-5 py-4 font-bold">Snow</th>
                <th className="px-5 py-4 font-bold">Wind</th>
                <th className="px-5 py-4 font-bold">Total</th>
                <th className="px-5 py-4 font-bold">Status</th>
              </tr>
            </thead>

            <tbody className="divide-y divide-stone-200">
              {filteredLoadItems.map((item) => (
                <tr key={item.id} className="transition hover:bg-stone-50">
                  <td className="px-5 py-4 font-bold text-stone-700">
                    {item.id}
                  </td>

                  <td className="px-5 py-4 text-stone-600">{item.level}</td>

                  <td className="px-5 py-4 font-semibold text-stone-800">
                    {item.element}
                  </td>

                  <td className="px-5 py-4 text-stone-600">
                    {item.elementType}
                  </td>

                  <td className="px-5 py-4 text-stone-600">{item.gridLine}</td>

                  <td className="px-5 py-4 text-stone-600">
                    {item.deadLoad.toFixed(1)}
                  </td>

                  <td className="px-5 py-4 text-stone-600">
                    {item.liveLoad.toFixed(1)}
                  </td>

                  <td className="px-5 py-4 text-stone-600">
                    {item.snowLoad.toFixed(1)}
                  </td>

                  <td className="px-5 py-4 text-stone-600">
                    {item.windLoad.toFixed(1)}
                  </td>

                  <td className="px-5 py-4 font-bold text-stone-900">
                    {item.totalLoad.toFixed(1)}
                  </td>

                  <td className="px-5 py-4">
                    <span
                      className={`rounded-full border px-3 py-1 text-xs font-bold ${getStatusClass(
                        item.status,
                      )}`}
                    >
                      {getStatusLabel(item.status)}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {filteredLoadItems.length === 0 && (
          <div className="p-10 text-center">
            <h3 className="text-lg font-bold">No load records found</h3>
            <p className="mt-2 text-sm text-stone-500">
              Try changing your search or filter options.
            </p>
          </div>
        )}
      </section>
    </section>
  );
}

export default Rundown;
