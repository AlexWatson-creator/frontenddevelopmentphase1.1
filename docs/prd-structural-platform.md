# Product Requirements Document
## Jablonsky Data Platform (JAPDP)

**Version:** 2.0
**Author:** Jili Peng
**Updated:** May 2026
**Status:** Phase 1 ✅ COMPLETE | Phase 2 ✅ COMPLETE (Step 6 pending) | Phase 3–5 Planned

---

## 1. Executive Summary

JAPDP is an internal web platform that transforms the firm's existing Revit model geometry (already synced to SQL Server via Clarity) into a centralized structural engineering design data layer. It enables:

- **Automated tributary area calculation** — Voronoi-based load assignment per element per floor, replacing manual CAD markup
- **Gravity load rundown** — cumulative DL/LL computation from roof to footing, replacing Excel VBA workflows. Every intermediate value is stored in the database — no black boxes.
- **Cross-source identity resolution** — mapping the same physical element across Revit GUIDs, spreadsheet marks, and future ETABS IDs
- **Spreadsheet + CAD upload** — importing existing .xlsm rundown files and AutoCAD DXF files into the platform

**Current state (May 2026):** Phase 1 and Phase 2 fully delivered (532 tests passing). One Phase 2 step remains (Step 6: Vertical Chains). The frontend is being redesigned from scratch; the legacy frontend is preserved in `frontend-legacy/` as reference.

---

## 2. Problem Statement

### Current Workflow Pain Points

**Manual Load Rundown (replaced by this platform):**
Engineers currently maintain gravity load rundowns in Excel (.xlsm files) with custom VBA macros. The workflow involves manually exporting Revit to CAD, marking tributary areas on plans, then hand-entering data into Excel. Each handoff introduces delays and version confusion.

**Fragmented Design Data:**
Load assignments, rebar schedules, and design results live in individual engineers' files. There is no single place to query "what are all the loads on column C-12 from Level 10 to footing?"

**Underutilized Geometry Database:**
The firm already syncs all Revit model geometry to SQL Server daily (JAPBIMDB). This data serves Power BI quantity reports and ETABS/SAFE model reconstruction — it can also serve as the geometry backbone for a full design data platform.

---

## 3. Vision

Click any structural element on the web platform and instantly see its complete engineering profile: tributary area, full gravity load history from roof to footing, rebar design, geometry, and connected elements above and below.

---

## 4. Users

| User Group | Count | Primary Use |
|---|---|---|
| Structural Designers | ~80 | Load area input, rundown workflow, element inspection |
| Project Engineers | ~40 | Review loads, design checks, approve rundown |
| Project Managers | ~30 | Progress tracking, report generation |
| All Staff (view) | ~500 | View element data, loads, quantities |

---

## 5. Architecture Overview

### 5.1 System Architecture

```
DATA SOURCES                BACKEND                         FRONTEND
────────────                ───────                         ────────

Revit Model                 ┌────────────────────┐
  │                         │    FastAPI Server   │         ┌──────────────┐
  └─► Clarity (daily) ────► │                    │ ◄──────► │  Web App     │
      JAPBIMDB [dbo]        │  /api/projects     │          │  (React +TS) │
      (READ-ONLY)           │  /api/elements     │          │              │
                            │  /api/tributary    │          │  - Projects  │
Spreadsheet (.xlsm)         │  /api/rundown      │          │  - Tributary │
  │                         │  /api/identity     │          │  - Rundown   │
  └─► Upload wizard ──────► │                    │          │  - Upload    │
                            │  Voronoi Service   │          └──────────────┘
CAD DXF (.dxf)              │  Rundown Engine    │
  │                         │  Identity Hub      │
  └─► Upload wizard ──────► │                    │
                            └─────────┬──────────┘
                                      │
                                      ▼
                            ┌─────────────────────┐
                            │  SQL Server (on-prem)│
                            │  JAPBIMDB            │
                            │                      │
                            │  [dbo]  = Revit geo  │
                            │  [design] = eng data  │
                            │  [management] = meta  │
                            └──────────────────────┘
```

### 5.2 Tech Stack

| Layer | Technology |
|---|---|
| Backend API | Python 3.11+ / FastAPI / uvicorn |
| Database | SQL Server on-prem (JAPBIMDB) |
| ORM | SQLAlchemy + pyodbc (sync, Windows trusted auth) |
| Computation | scipy + shapely (Voronoi), rundown_engine (standalone Python) |
| Web Frontend | React 19 + TypeScript + Vite + Tailwind CSS v3 |
| Plan View | Inline SVG (React) — rendered from DB coordinates |
| Authentication | Planned — Phase 3 (Windows AD/LDAP) |

### 5.3 Database Strategy

Three schemas in JAPBIMDB:

**`dbo` (Clarity-owned — READ-ONLY from platform perspective):**
All Revit model elements (columns, walls, beams, floors, foundations, grids) with locations, marks, dimensions, and levels. Synced daily via Clarity. Existing consumers (Power BI, ETABS/SAFE plugin) must remain unaffected — the platform never writes to `dbo`.

**`design` (platform-owned):**
All engineering data: load tables, load areas, tributary results, load assignments, element marks and links, rundown results (fully transparent — every intermediate value), identity hub, rebar, design results, ETABS imports, audit log.

**`management` (platform-owned):**
`project_meta` table — one row per unique project Number (the stable anchor). Auto-synced via trigger on `dbo.Project INSERT`.

### 5.4 Element Identity Strategy

Three data sources identify the same physical element differently:

| Source | Identity | Lifecycle |
|---|---|---|
| Revit/Clarity | GUID (stable) + Mark (human-error-prone) | Wiped daily |
| Rundown Spreadsheet | Mark + Level Name | Uploaded manually |
| ETABS (Phase 4) | ETABS label/ID | Imported on-demand |

**Solution:** Two identity hub tables (`design.level_identity`, `design.element_identity`) scoped to `project_number`. No FK to `dbo` — they survive wipe-reload. All downstream design data references identity hub IDs.

Level matching uses `sort_order` (ordinal position), not elevation. Revit elevations are unreliable.

---

## 6. Database Schema

See `sql_migration_scripts/setup_db.sql` for the complete, deployable schema. See `developer-guide.md` for the architectural explanation.

### Design schema tables

| Table | Purpose |
|---|---|
| `load_tables` | Load type definitions (RES, BALC, MEC, ROOF) per project file |
| `load_areas` | User-drawn load area polygons per floor |
| `tributary_results` | Voronoi-computed tributary area per element per floor per load type |
| `load_assignments` | Resolved load per element (area × kPa × LLRF) |
| `element_marks` | Parsed element labels following firm naming convention |
| `element_links` | Vertical chain mapping across floors |
| `rebar` | Reinforcement records per element (Phase 4) |
| `design_results` | Design check outputs (Phase 4) |
| `etabs_imports` | ETABS/SAFE data (Phase 4) |
| `audit_log` | Full change history |
| `level_identity` | Cross-source level name resolution |
| `element_identity` | Cross-source element "golden records" |
| `rundown_uploads` | Raw spreadsheet data before identity matching |
| `rundown` | Full-transparency gravity load results (40+ columns, 1:1 with Excel) |
| `rundown_transfers` | Engineer-defined load transfer relationships |

---

## 7. Phase 1 — Voronoi Tributary Service ✅ COMPLETE

**Objective achieved:** Demonstrate that existing Python engineering tools can be deployed as platform services backed by Revit geometry, replacing manual CAD markup.

### Delivered

**Project Management:**
- Project listing grouped by Number, search/filter/sort
- View/edit project metadata (address via `management.project_meta`)
- Delete projects or individual files, merge duplicate projects
- Stat cards (total projects, files, elements, last synced)

**Load Table CRUD:**
- Inline editing table (name, description, dead/live kPa, LLRF type)
- Bulk create/replace per project file

**Tributary Service (Backend):**
- Voronoi computation from `dbo` element locations (columns + walls)
- Load area polygons (web-drawn or JSON upload) → Voronoi cells clipped to floor boundary
- Intersect cells with load area polygons → tributary area by load type
- Stores results in `design.tributary_results` and `design.load_assignments`

**Tributary Canvas (Frontend):**
- Layered SVG floor plan: slab, openings, grids, walls, columns, drawn areas, Voronoi overlay
- Drawing tools: Rectangle (R), Polygon (P) with snap to structure
- Select + drag to reposition drawn areas
- CTM-based pan/zoom, fit-to-view, keyboard shortcuts
- Element mark labels, hover highlight, element info panel

**Tests:** 90 backend tests at Phase 1 close; 142 after Phase 2 Steps 1–3.

---

## 8. Phase 2 — Identity Resolution + Load Rundown ✅ COMPLETE (Step 6 pending)

### Step Summary

| Step | Description | Status | Tests |
|------|-------------|--------|-------|
| 1 | DB migration + identity ORM models | ✅ | 97 backend |
| 2 | Level identity service + API | ✅ | 109 backend |
| 3 | Element identity service + mark parser | ✅ | 142 backend |
| 4 | Element identity management UI | ✅ | frontend only |
| RE | Rundown engine standalone module | ✅ | 340 engine |
| F | DB migration — full transparency rundown schema | ✅ | — |
| G | Backend rundown integration (adapter + API) | ✅ | 180 backend |
| 5 | Spreadsheet upload (2-step wizard) | ✅ | incl. in G |
| CAD | CAD DXF upload (5-step wizard) | ✅ | incl. in G |
| 7 | Load rundown results UI (dashboard + table + detail) | ✅ | frontend |
| **6** | **Vertical chain mapping** | **⏳ PENDING** | — |

### Rundown Engine (standalone — `rundown_engine/`)

Pure-Python migration of all Excel/VBA rundown formulas. Zero backend imports — reusable across CLI scripts, Jupyter notebooks, and future microservices.

Three data source parsers feed the same `compute_rundown()` engine:
- **CAD DXF** — `parsers/cad_dxf.py` via ezdxf (replicates `ImportRundown.bas`)
- **Spreadsheet** — `parsers/spreadsheet.py` via openpyxl (dual-mode: import AS-IS + recompute from inputs to verify)
- **Revit** — assembled in `backend/app/services/rundown_service.py` from `dbo` geometry + Voronoi results

**Verified against production data:**
- 20205 TEMPLE (19 floors): W22, C2, W10A — DL/LL/PF match Excel within 0.5 kN tolerance
- 24043 (50 floors, zero-padded marks): C029, C031, W008, W004, W008.3 — all floors match
- Area balance: both projects balanced (Σ = 0 within tolerance)

**340 engine tests — all passing.**

### Key Phase 2 API Endpoints

**Identity:**
```
POST /api/projects/{number}/levels/populate          — populate level_identity from Revit
GET  /api/projects/{number}/levels/identity          — list level identities
PATCH /api/projects/{number}/levels/identity/{id}    — manual override
POST /api/projects/{number}/elements/populate        — populate element_identity from Revit
GET  /api/projects/{number}/elements/identity        — list with filters
PATCH /api/projects/{number}/elements/identity/{id}  — manual correction
```

**Rundown:**
```
POST /api/projects/{number}/rundown/upload                    — spreadsheet preview
POST /api/projects/{number}/rundown/upload/{batch}/confirm    — confirm + write to DB
POST /api/projects/{number}/rundown/cad-upload               — CAD DXF upload + compute
GET  /api/projects/{number}/rundown                           — list element summaries
GET  /api/projects/{number}/rundown/{element_id}              — full element stack
GET  /api/projects/{number}/rundown/validation                — area/transfer checks
DELETE /api/projects/{number}/rundown/{batch}                 — delete batch
```

### Step 6 (Pending): Vertical Chain Mapping

Build vertical element chains per project:
- Group elements by `canonical_mark` (from `element_identity`)
- Sort by `sort_order` (from `level_identity`)
- Link adjacent pairs → store in `design.element_links`
- Geometric proximity fallback (500mm tolerance for columns)
- API: build chains, list chains, get single chain

---

## 9. Phase 3 — Web Platform MVP (Planned)

- Full element inspector panel: loads, tributary, rebar, linked elements, history
- Vertical chain viewer (click element → see full roof-to-footing stack)
- Manual link override interface
- User authentication (Windows AD/LDAP)
- Floor-level optimistic locking
- Persist drawn load areas to `design.load_areas`

---

## 10. Phase 4 — ETABS, Design & Rebar (Planned)

- Expand ETABS/SAFE C# plugin to write lateral forces, drift, modal data to `design` schema
- Rebar calculation service: rundown loads + element geometry → required rebar (size, spacing, qty)
- Design check modules: footing, wall/column, slab utilization ratio
- Combined gravity + lateral load view per element

---

## 11. Phase 5 — 3D Visualization & Revit Sync (Planned)

- Three.js element 3D view with rebar overlay
- Vertical chain 3D view (roof to foundation)
- Revit add-in panel: click element in Revit → see platform data
- Bidirectional sync: push design results back to Revit parameters

---

## 12. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Clarity wipe-reload breaks design FK | GUID column provides stable reference; identity hub survives |
| SQL Server spatial query performance | Spatial indexes on all geometry columns; cache frequently accessed floors |
| Label parsing fails on non-standard marks | Geometric matching fallback; manual override always available |
| On-prem hosting constraints | Containerize (Docker) for easier future migration |

---

## 13. Timeline

| Phase | Status | Notes |
|---|---|---|
| Phase 1 — Voronoi POC | ✅ Complete | 180 backend tests. Canvas + drawing tools delivered early. |
| Phase 2 — Identity + Rundown | ✅ Near-complete | 532 tests (180 backend + 340 engine + 12 frontend). Step 6 pending. |
| Phase 3 — Web MVP | Planned | Auth + element inspector; canvas/drawing already done in Phase 1 |
| Phase 4 — ETABS & Rebar | Planned | Not started |
| Phase 5 — 3D & Revit Sync | Planned | Not started |

---

## Appendix A: JAPBIMDB Entity Relationship Summary

```
Project (Id PK, Number — the firm's project identifier)
  ├── Levels (id PK, Project_id FK) — Name, Elevation, StoryHeight
  ├── Grids (id PK, Project_id FK) — Name, StartLocation, EndLocation
  │
  ├── ColumnType (id PK, Project_id FK) — TypeName, D, B, H, Material_id
  │     └── Columns (id+Project_id PK, guid, Section_id FK)
  │           — BaseLocation, TopLocation, Mark, Height, Volume, Rotation, Area
  │
  ├── WallType (id PK, Project_id FK) — TypeName, Thickness, Material_id
  │     └── Walls (id+Project_id PK, guid, Section_id FK)
  │           — StartLocation, EndLocation, Mark, Area, Volume, Height
  │
  ├── BeamType (id PK, Project_id FK) — TypeName, Width, Depth, Material_id
  │     └── Beams (id+Project_id PK, guid, Section_id FK)
  │           — StartLocation, EndLocation, Mark, Length, Volume
  │
  ├── FloorType (id PK, Project_id FK) — TypeName, Thickness, Material_id
  │     └── Floors (id+Project_id PK, guid, Section_id FK)
  │           — LocationPoints, Mark, Perimeter, Area, Volume
  │           Note: FloorType.TypeName = 'OPENING' → slab holes, filter these out
  │
  └── FoundationType (id PK, Project_id FK) — TypeName, Material_id
        └── Foundations (id+Project_id PK, guid, Section_id FK)
              — Mark, Area, Volume (NO location data)
```

**Composite PKs:** All element tables use `(id, Project_id)` as composite PK. SQLAlchemy models must declare both as `primary_key=True`.

## Appendix B: Coordinate Format

All coordinates in JAPBIMDB stored as comma-separated text in millimetres (project-relative):

- **Column BaseLocation:** `"8878.0,6675.0,5540.0"` → X=8878mm, Y=6675mm, Z=5540mm
- **Wall Start/EndLocation:** same format, two endpoints define the wall centerline
- **Slab LocationPoints:** colon-separated vertices `"x,y,z:x,y,z:..."`, semicolons separate sketch loops (outer boundary + holes)

Display conversions: area in m² = `area_mm² / 1,000,000`, loads in kN = `area_m² × load_kPa`

## Appendix C: Firm Element Naming Convention

```
[PREFIX, optional]  [C or W, required]  [NUMBER]  [SUFFIX, optional]  .  [COMMENTS, optional]
```

Examples:
- `C1` — Column 1
- `W22` — Wall 22
- `C1A.1` — Column 1A, instance 1 (same chain as `C1A.2`)
- `W10A` — Wall 10, split A
- `PC376` — Foundation column (P prefix)
- `W10-W11-W12` — Grouped walls (single rundown entry, shared load)

**Rules:**
- Comments (`.1`, `.2`) = same chain, different schedule positions
- Suffixes (`A`, `B`) = split elements at partial floors
- `C{n}` and `W{n}` cannot share the same number on the same floor
- Foundation elements use `P` prefix (`PC###`, `PW###`)
