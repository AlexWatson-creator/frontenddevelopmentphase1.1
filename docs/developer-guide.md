# Jablonsky Data Platform — Developer Guide

**Version:** 2.0 | **Updated:** May 2026 | **Status:** Phase 1 + Phase 2 complete

This guide covers everything a new backend or frontend developer needs to set up, understand, and extend the platform. Read this before touching any code.

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Repository Structure](#2-repository-structure)
3. [Local Setup](#3-local-setup)
4. [Database Architecture](#4-database-architecture)
5. [Backend Architecture](#5-backend-architecture)
6. [Rundown Engine](#6-rundown-engine)
7. [Frontend Architecture](#7-frontend-architecture)
8. [Design System](#8-design-system)
9. [Critical Rules](#9-critical-rules)
10. [Testing](#10-testing)
11. [Adding New Features](#11-adding-new-features)

---

## 1. Project Overview

JAPDP is an internal web platform for Jablonsky structural engineering. It wraps API services around existing Revit model geometry (already in SQL Server via Clarity) to enable:

- **Tributary area calculation** — Voronoi-based load area assignment per element per floor
- **Gravity load rundown** — cumulative DL/LL computation from roof to footing, traceable to every formula
- **Identity resolution** — cross-source element matching (Revit GUIDs ↔ spreadsheet marks ↔ future ETABS IDs)

**What it is NOT:** a replacement for Revit, ETABS, or the existing Clarity sync. It is a design data layer that reads from the existing geometry database and stores engineering calculations.

---

## 2. Repository Structure

```
JAP_DATA_PLATFORM/
├── backend/                    # FastAPI server (Python 3.11+)
│   ├── app/
│   │   ├── main.py             # FastAPI app entry point
│   │   ├── config.py           # DB connection + settings
│   │   ├── dependencies.py     # get_db() session factory
│   │   ├── models/             # SQLAlchemy ORM models
│   │   │   ├── dbo.py          # READ-ONLY: 15 Revit geometry tables
│   │   │   └── design.py       # READ-WRITE: 14 engineering data tables
│   │   ├── routers/            # FastAPI route handlers
│   │   ├── schemas/            # Pydantic request/response models
│   │   └── services/           # Business logic
│   ├── tests/                  # 180 backend tests (live DB)
│   ├── .env                    # DB_SERVER (not committed)
│   ├── .env.example
│   └── pyproject.toml          # uv-managed dependencies
│
├── rundown_engine/             # Standalone computation module
│   ├── dtypes/                 # Input/output dataclasses
│   ├── formulas.py             # Pure formula functions
│   ├── compute.py              # compute_rundown() orchestrator
│   ├── validate.py             # Area balance + transfer checks
│   ├── parsers/
│   │   ├── cad_dxf.py          # DXF/MText parser (ezdxf)
│   │   └── spreadsheet.py      # .xlsm parser (openpyxl)
│   └── tests/                  # 340 engine tests (no DB)
│
├── frontend-legacy/            # React reference (for redesign context)
│   └── src/                    # Pages, components, hooks, utils, API client
│
├── docs/                       # Developer documentation
│   ├── developer-guide.md      # This file
│   ├── prd.md                  # Product requirements + phase history
│   ├── api-reference.md        # Full API endpoint documentation
│   ├── deployment.md           # IIS + Windows VM deployment
│   ├── JAPBIMDB.sql            # DB schema dump (reference)
│   └── production_JAPBIMDB.sql # Production schema snapshot
│
├── sql_migration_scripts/
│   ├── setup_db.sql            # Single script: fresh DB setup (run this)
│   └── archive/                # Original incremental migrations (history only)
│
├── assets/                     # Logo files (used in frontend)
└── CLAUDE.md                   # AI assistant codebase context
```

---

## 3. Local Setup

### Backend

```powershell
cd D:\RESEARCH\JAP_DATA_PLATFORM\backend
cp .env.example .env
# Edit .env: set DB_SERVER=YOUR_SERVER_NAME (e.g., J-PENG\SQLEXPRESS)

# Install uv (if not present): pip install uv
uv sync                  # Install dependencies + create .venv
uv run uvicorn app.main:app --reload --port 8000
```

The server starts at `http://localhost:8000`. Swagger UI (try all endpoints live): `http://localhost:8000/docs`.

**Dependencies (key packages):** FastAPI, SQLAlchemy, pyodbc, shapely, scipy, ezdxf, openpyxl

### Database

Requires an existing JAPBIMDB SQL Server instance with the `dbo` schema populated. For a fresh deployment:

1. Ensure JAPBIMDB database exists and is accessible via Windows Trusted Authentication
2. Confirm the `dbo` schema has Clarity-synced tables (Project, Levels, Columns, Walls, etc.)
3. Run `sql_migration_scripts/setup_db.sql` in SSMS — creates all `management` and `design` schema tables

**Connection string:**
```
mssql+pyodbc://{DB_SERVER}/JAPBIMDB?driver=ODBC+Driver+17+for+SQL+Server&trusted_connection=yes
```

### Rundown Engine (standalone)

```bash
cd rundown_engine
pip install -e .             # Install in editable mode
pytest tests/ -v             # 340 tests, no DB required
```

The backend installs it as a local editable package: `pip install -e ../rundown_engine`

### Frontend (legacy reference)

To run the existing frontend locally:

```powershell
cd D:\RESEARCH\JAP_DATA_PLATFORM\frontend-legacy
npm ci          # Install dependencies
npm run dev     # Start Vite dev server
```

Opens at `http://localhost:5173`.

### Running both together

Open two terminals in parallel:

**Terminal 1 — Backend**
```powershell
cd D:\RESEARCH\JAP_DATA_PLATFORM\backend
uv run uvicorn app.main:app --reload --port 8000
```

**Terminal 2 — Frontend**
```powershell
cd D:\RESEARCH\JAP_DATA_PLATFORM\frontend-legacy
npm run dev
```

| URL | What |
|---|---|
| `http://localhost:5173` | Frontend app |
| `http://localhost:8000/docs` | Swagger UI — try all API endpoints live |
| `http://localhost:8000/api/health` | Backend health check |

### Frontend (new)

The new `frontend/` will be built from scratch. Point it at `http://localhost:8000/api/` during development. See `docs/api-spec.md` for all endpoints.

---

## 4. Database Architecture

### Three schemas, one SQL Server instance (JAPBIMDB)

| Schema | Owner | Access | Purpose |
|--------|-------|--------|---------|
| `dbo` | Clarity (Revit sync) | READ-ONLY | All Revit geometry: elements, locations, marks, levels, grids |
| `design` | Platform | READ-WRITE | Engineering data: loads, rundown, identity, rebar, design results |
| `management` | Platform | READ-WRITE | Project metadata anchor (`project_meta` table) |

### The wipe-reload problem

Clarity calls `spProject_InitializeTables` before every sync — this **deletes all elements** for a project and re-inserts them. This means:
- `dbo.Columns.id` (Revit ElementId) **can change** between syncs
- `dbo.Columns.guid` (Revit UniqueId) is **stable** across wipe-reloads

**Rule:** The `design` schema references elements via `element_guid VARCHAR(50)`, never by `id` (ElementId). Design data survives Clarity syncs.

### Key tables

**`management.project_meta`** — one row per project Number (e.g., "23219"). The stable anchor. All design tables FK to this via `project_number`. Auto-populated by trigger on `dbo.Project INSERT`.

**`design.level_identity`** — maps level names across sources. "Level 5" (Revit) = "5" (Spreadsheet). Matched by `sort_order` (ordinal), NOT elevation (Revit elevations are unreliable).

**`design.element_identity`** — one "golden record" per element per project. No FK to dbo — reconciled by GUID lookup. Stores `revit_guid`, `rundown_key`, `etabs_id` (future).

**`design.rundown`** — full transparency rundown results. Every intermediate DL/LL term stored (6 DL breakdown columns, 2-path LL system, per-type JSON areas). See `setup_db.sql` for the full column map with Excel column references.

**`design.load_tables`** — load type definitions (RES, BALC, MEC, ROOF, etc.) per project file.

**`design.tributary_results`** — Voronoi-computed tributary area per element per floor.

### No FK to dbo

`design` tables use `(element_guid, project_id)` as loose references — there are no foreign key constraints pointing at `dbo` tables. This is intentional: FK constraints would be broken by every Clarity wipe-reload.

### SQL Server cascade path limitation

`design.load_areas`, `tributary_results`, `load_assignments`, and `rundown` each FK to both `dbo.Project` (via project_number → project_meta) AND `design.load_tables`. SQL Server forbids CASCADE on the `load_tables` FK because it creates two cascade paths to the same table.

**Solution:** `load_tables` FK uses `NO ACTION`. App code explicitly clears dependents before deleting load table entries. Do NOT attempt to change this to CASCADE.

### Geometry storage

SQL Server `GEOMETRY` type, SRID 0, units in millimetres (project-relative coordinates). GeoAlchemy2 does NOT work with SQL Server — it emits PostGIS syntax. Use raw SQL with `sqlalchemy.text()`:

```python
# INSERT geometry
db.execute(text("INSERT INTO design.load_areas (polygon_wkt, ...) VALUES (geometry::STGeomFromText(:wkt, 0), ...)"), {"wkt": polygon_wkt})

# SELECT geometry
row.polygon_wkt.STAsText()  # or parse from WKT string
```

---

## 5. Backend Architecture

### Project domain model

Each `dbo.Project` row = a **Revit model file**, not a project. `Project.Number` is the firm's project identifier (e.g., "23219"). One Number can have multiple files (e.g., TWB tower + podium).

- Metadata (address, job_name, designer) lives in `management.project_meta`, never in `dbo.Project`
- API groups by Number: `GET /api/projects` returns `{number, address, files: [...]}`
- `PATCH /api/projects/{number}` writes ONLY to `management.project_meta`
- Delete supports: entire Number (`DELETE /api/projects/{number}`) or single file (`DELETE /api/projects/files/{id}`)

### Routers + Services

| Router | Service | What it does |
|--------|---------|------|
| `projects.py` | `project_service.py` | Project list/detail/edit/delete/merge |
| `elements.py` | — | Columns, walls, grids, slab boundary per level |
| `load_tables.py` | — | Load type CRUD per file |
| `tributary.py` | `voronoi.py`, `slab_boundary.py` | Voronoi computation + results |
| `identity.py` | `level_identity.py`, `element_identity.py`, `mark_parser.py` | Identity hub population + resolution |
| `rundown.py` | `rundown_service.py` | Spreadsheet/CAD upload + compute + results |

### Mark parser

The firm's element naming convention: `[PREFIX?] [C or W] [NUMBER] [SUFFIX?] . [COMMENTS?]`

Examples: `C1`, `W22`, `C1A.1`, `PC376` (foundation), `W10-W11` (grouped walls)

- Comments (`.1`, `.2`) = same chain, different schedule positions
- Suffixes (`A`, `B`) = split elements (partial floors)
- `C{n}` and `W{n}` cannot share the same number on the same floor
- Parser detects human errors: wall element marked as `C##` is flagged

### Coordinate parsing

All JAPBIMDB coordinates are stored as comma-separated text in millimetres:
- Column: `"8878.0,6675.0,5540.0"` → X=8878mm, Y=6675mm, Z=5540mm
- Wall: `StartLocation` + `EndLocation` (same format)
- Slab: colon-separated vertices `"x,y,z:x,y,z:..."`, semicolons separate loops (holes)
- Display: area in m² (`area_mm2 / 1e6`), loads in kN (`area_m2 × kPa`)

### Pydantic + SQLAlchemy patterns

```python
# Pydantic v2 — always use this syntax
class MySchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    field: str

# pyodbc is synchronous — SQLAlchemy sessions are sync
# For async endpoints, wrap in run_in_executor or accept sync
```

---

## 6. Rundown Engine

**Location:** `rundown_engine/` at project root — zero backend imports, standalone.

**What it does:** Pure Python migration of all Excel/VBA gravity load rundown formulas. Accepts input from three sources (CAD DXF, spreadsheet, Revit) and produces fully transparent output — every intermediate value in the FloorResult dataclass maps 1:1 to an Excel cell.

### Data flow

```
CAD DXF (.dxf)    →  parsers/cad_dxf.py       ↘
Spreadsheet (.xlsm) → parsers/spreadsheet.py  → RundownInput → compute_rundown() → RundownResult
Revit (via backend) → rundown_service.py       ↗
```

### Key modules

- `dtypes/inputs.py` — `RundownInput`, `ElementInput`, `FloorInput`, `LoadTypeDef`, `TransferDef`
- `dtypes/outputs.py` — `RundownResult`, `ElementResult`, `FloorResult`
- `formulas.py` — 18 pure functions (cross-section, LLRF, DL 6 terms, LL 2-path, PF, rebar)
- `compute.py` — `compute_rundown()`: topological sort + floor-by-floor loop
- `validate.py` — area balance, transfer checks, data gap detection

### Verified against production data

- **20205 TEMPLE** (19 floors): W22, C2, W10A — all DL/LL/PF match Excel within 0.5 kN
- **24043** (50 floors, zero-padded marks): C029, C031, W008, W008.3 — all floors match
- Area balance: both projects balanced (Σ = 0 within tolerance)

### Spreadsheet reference

See `.claude/rundown-spreadsheet-read-me.md` for the complete Excel template spec: column maps, IMPORT sheet layout, VBA formula references, transfer mechanics, and system sheet names. This is the authoritative technical reference for the rundown feature.

---

## 7. Frontend Architecture (Legacy Reference)

The `frontend-legacy/` folder is the existing React app, kept as a reference for the new frontend build.

**Stack:** React 19 + TypeScript + Vite + Tailwind CSS v3

### Key pages

| Page | Route | Purpose |
|------|-------|---------|
| `ProjectsPage` | `/` | Project grid with search/filter/sort |
| `ProjectDetailPage` | `/projects/:number` | Files, levels, element counts, delete/merge |
| `RundownPage` | `/projects/:number/rundown` | Tabs: Load Table, Tributary, Load Rundown |
| `RundownDashboardPage` | `/rundown` | Recent rundowns + entry point |
| `RundownResultsPage` | `/rundown/:id` | Excel-like results table |
| `ElementDetailPage` | `/rundown/:id/element/:eid` | Single element floor-by-floor breakdown |
| `SpreadsheetUploadPage` | `/projects/:number/upload/spreadsheet` | 3-step wizard |
| `CadUploadPage` | `/projects/:number/upload/cad` | 5-step wizard |

### SVG Canvas (Tributary)

The tributary tab uses a layered SVG architecture. The canvas occupies all available space with a 240px right tool panel. Navigation uses CTM-based pan/zoom (not translate/scale) for uniform speed across zoom levels.

```
TributaryTab (state orchestrator)
└── FloorCanvas (SVG root)
    ├── SlabLayer       — slab boundary fill
    ├── OpeningLayer    — opening X-marks
    ├── GridLayer       — grid lines + bubble labels
    ├── WallLayer       — wall polygons with proper thickness
    ├── ColumnLayer     — circles (round) or rotated rects (rectangular)
    ├── DrawnAreasLayer — user-drawn load polygons
    └── VoronoiLayer    — computed Voronoi cells coloured by load type
```

### API client

`src/api/client.ts` — typed fetch wrapper. All endpoints use the base URL `http://localhost:8000/api`. The Vite proxy in `vite.config.ts` handles `/api` → `localhost:8000` during development.

---

## 8. Design System

These rules are non-negotiable. Any new frontend must follow them.

### Colour palette

```
Red (signature):  #CE1B22  — primary actions, active nav, selection states
Red hover:        #b8181e
Red tint:         #fdf2f2  — subtle background for active items

Black:            #231F20  — headings, strong emphasis
Charcoal:         #302D27  — primary body text, nav labels, card titles
Dark Grey:        #5C5D61  — secondary text, descriptions, section labels
Light Grey:       #CFCCCC  — placeholders, disabled, subtle borders

Background:       #f8f6f3  — warm off-white page background
Card surface:     #fffefa  — elevated card background
Border:           #ebe8e3  — card edges
Border light:     #f2f0ec  — dividers within cards
```

**Forbidden:**
- **Never pure white (`#ffffff`)** — use `#f8f6f3` or `#fffefa`
- **Never multiple accent colours** — only `#CE1B22` for primary actions
- **Never `#231F20` (Black) directly adjacent to `#CE1B22` (Red)** — buffer with charcoal or white

### Typography

```
Font stack: 'Calibri', 'Source Sans Pro', 'Source Sans 3', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif
```

**Never use Inter.** Font sizes: headings 40px/700, sub-headers 17px/600, body 15px/400, section labels 9px uppercase, captions 10px.

### Logo

Always an `<img>` tag — never "JAP" as plain text:
- Sidebar: `assets/JAP logo_rectangle.png`
- Compact nav: `assets/JAP logo_solo.png`

### Tributary page layout

The tributary tab uses a different layout than the rest of the app:
- 52px slim icon-only nav (not the full 210px sidebar)
- flex-1 SVG canvas area
- 240px right tool panel

---

## 9. Critical Rules

### Database

1. **`dbo` is READ-ONLY** except three specific delete operations (project delete, file delete, project merge). Never write to `dbo` for any other reason — it will break Power BI and the ETABS/SAFE plugin.
2. **Reference elements by `guid` (Revit UniqueId), never by `id` (ElementId).** ElementIds change on Clarity wipe-reload. GUIDs are stable.
3. **Never create FK constraints pointing at `dbo` tables.** They break on wipe-reload.
4. **GeoAlchemy2 does not work with SQL Server** — use raw SQL with `sqlalchemy.text()` for any geometry column operations.
5. **Filter `FloorType.TypeName = 'OPENING'`** when parsing slab boundaries — these are holes, not structural slabs.
6. **Filtered indexes require `SET QUOTED_IDENTIFIER ON`** in SQL Server migration scripts.

### Application logic

7. **Load table FK uses NO ACTION** (not CASCADE) — app code clears dependents before deleting load table entries.
8. **Level matching uses ordinal (`sort_order`), not elevation.** Revit elevations can be arbitrary numbers.
9. **Coordinates are always in millimetres** in the database. Convert: area in m² = `area_mm² / 1e6`, loads in kN = `area_m² × kPa`.
10. **`C{n}` and `W{n}` cannot share the same number on the same floor.** The parser enforces this.

### Code style

11. **Pydantic v2** — use `model_config = ConfigDict(from_attributes=True)`, `model_validator`, `field_validator`.
12. **pyodbc is synchronous** — SQLAlchemy sessions via pyodbc do not support async.
13. **Python:** PEP 8, type hints everywhere.
14. **TypeScript:** strict mode, functional React components with hooks, no class components.

---

## 10. Testing

### Backend tests (180 tests)

Located in `backend/tests/`. All tests hit a live database — no mocking.

```bash
cd backend
uv run pytest tests/ -v
```

Test isolation: each test file uses explicit `DELETE` cleanup (not rollback) to avoid DB lock issues. Test data uses `project_number='99999'` as the sentinel value.

```
test_projects.py        — 20 tests: project CRUD, merge, file delete
test_load_tables.py     — 16 tests: load type CRUD
test_elements.py        —  9 tests: elements endpoint
test_coordinate_parser.py — 12 tests: coordinate text parsing
test_level_identity.py  — 17 tests: level resolution
test_element_identity.py — 18 tests: element hub matching
test_mark_parser.py     —  8 tests: mark parsing
test_tributary.py       — 17 tests: Voronoi API round-trip
test_identity_tables.py —  7 tests: identity table queries
test_rundown_api.py     — 18 tests: upload, preview, confirm, delete
test_rundown_workflow.py — 20 tests: end-to-end rundown
test_chains.py          — (pending — Step 6)
```

### Rundown engine tests (340 tests)

```bash
cd rundown_engine
pytest tests/ -v
```

No database required. Tests use production fixture data from real projects.

```
test_formulas.py          — 112 tests: every formula function
test_compute.py           —  18 tests: integration, transfers, edge cases
test_validate.py          —  30 tests: area balance, circular transfers
test_cad_dxf_parser.py    —  44 tests: MText parsing, DXF extraction
test_spreadsheet_parser.py —  81 tests: 3 real .xlsm files (20205, 24025, 24043)
test_verification.py      —  13 tests: end-to-end vs real Excel values
test_recompute.py         —  (recompute logic)
```

---

## 11. Adding New Features

### New backend endpoint

1. Add Pydantic schemas to `backend/app/schemas/<feature>.py`
2. Add service logic to `backend/app/services/<feature>.py`
3. Add router to `backend/app/routers/<feature>.py`
4. Register router in `backend/app/main.py`
5. Add tests to `backend/tests/test_<feature>.py`

Skeleton:
```python
# routers/example.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..dependencies import get_db
from ..schemas.example import ExampleResponse

router = APIRouter(prefix="/api/projects/{number}/example", tags=["example"])

@router.get("", response_model=list[ExampleResponse])
def list_example(number: str, db: Session = Depends(get_db)):
    ...
```

### New DB table

1. Add `CREATE TABLE` statement to `sql_migration_scripts/setup_db.sql`
2. Add SQLAlchemy ORM model to `backend/app/models/design.py`
3. Export from `backend/app/models/__init__.py`

Always scope by `project_number` and FK to `management.project_meta(project_number)`. Never FK to `dbo` tables.

### New rundown formula

1. Add pure function to `rundown_engine/formulas.py` with Excel column reference in docstring
2. Add unit tests to `rundown_engine/tests/test_formulas.py`
3. Wire into `compute.py` floor loop

---

*For the rundown spreadsheet spec (Excel column map, IMPORT sheet layout, VBA formula references): `docs/rundown-spreadsheet-spec.md`*
