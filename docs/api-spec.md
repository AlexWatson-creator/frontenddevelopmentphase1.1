# JAPDP Backend API Specification

**Base URL:** `http://<host>/api`
**Authentication:** None (Phase 3 — Windows AD/LDAP planned)
**Content-Type:** `application/json` (except file upload endpoints — see multipart notes)

---

## Core Concepts

### Project identity

Two identifiers exist for a project and they mean different things:

| Identifier | Source | Stability | Use |
|---|---|---|---|
| `project_number` | e.g. `"20205"` — firm's project code | **Stable forever** | All platform writes, rundown, identity |
| `project_id` | `dbo.Project.Id` — integer PK | **Wiped and recreated daily by Clarity** | Only for reading Revit geometry (elements, levels, grids) |

**Never store `project_id` as a permanent reference.** Clarity calls `spProject_InitializeTables` daily, which deletes and recreates all `dbo` rows. After a sync, `project_id` integers change. Only `project_number` is stable.

### Element identity

Similarly, Revit element identifiers are ephemeral:

| Identifier | Source | Stability |
|---|---|---|
| `guid` (Revit UniqueId, VARCHAR 50) | `dbo.Columns.guid`, `dbo.Walls.guid` | Stable within a model lifecycle |
| `element_id` (ElementId, integer) | `dbo.Columns.id` / `dbo.Walls.id` | Changes on every Clarity reload |

All engineering data in the `design` schema references elements by `guid`, never by `element_id`.

### Database schemas

| Schema | Owner | Access |
|---|---|---|
| `dbo` | Clarity (Revit sync) | **READ-ONLY** from platform. Never write here. |
| `design` | Platform | Read/write. All engineering results. |
| `management` | Platform | Read/write. `project_meta` — stable project anchor. |

### Coordinates

All coordinates are in **millimetres** relative to the Revit project origin. Frontend conversions:
- Area display: `mm² / 1,000,000` → m²
- Load display: `area_m² × kPa` → kN

### Error format

All errors return standard FastAPI JSON:
```json
{"detail": "Human-readable message"}
```

HTTP codes: `200` OK, `204` No Content (DELETE), `404` Not Found, `422` Validation / parse error, `500` Computation failure.

---

## Data Flow Overview

```
REVIT (Clarity daily sync)
  └─► dbo.Project, dbo.Levels, dbo.Columns, dbo.Walls, dbo.Grids, dbo.Floors
        │
        ├─► GET /projects                  → project list from management.project_meta
        ├─► GET /projects/files/{id}/levels/{id}/elements  → canvas data
        │
        ├─► POST /tributary/compute        → Voronoi → design.tributary_results + load_assignments
        │
        ├─► POST /projects/{n}/levels/sync     → design.level_identity (cross-source level map)
        └─► POST /projects/{n}/elements/sync   → design.element_identity (cross-source element map)

SPREADSHEET (.xlsm)                     CAD DXF (.dxf)
  └─► POST /rundown/upload              └─► POST /rundown/cad-upload
        └─► POST /rundown/upload/confirm        (both paths → same rundown engine)
              └─► design.rundown (40+ columns)
                    ├─► GET /rundown                      → element summary list
                    ├─► GET /rundown/{mark}               → full floor-by-floor detail
                    ├─► GET /rundown/validation           → area balance + transfer checks
                    ├─► GET /rundown/summary              → cross-element pivot matrix
                    ├─► PATCH /rundown/rows/{id}          → rebar overrides
                    ├─► PUT /rundown/transfers/{mark}     → load transfer definitions
                    └─► POST /rundown/recompute           → re-run engine with transfers
```

---

## 1. Projects

Manages project metadata. Revit project files are read from `dbo.Project`. The editable metadata layer (`management.project_meta`) is auto-created by a DB trigger on `dbo.Project INSERT`.

### `GET /projects`

**List all projects grouped by project number.**

Query parameters: none

Response:
```json
[
  {
    "project_number": "20205",
    "display_name": "TEMPLE MIXED USE",
    "address": "123 Temple St",
    "job_name": "20205 TEMPLE MIXED USE",
    "designer": "JP",
    "file_count": 2,
    "files": [
      {
        "project_id": 14,
        "file_name": "20205 TEMPLE_S.rvt",
        "element_counts": {
          "columns": 210,
          "walls": 88,
          "beams": 340,
          "floors": 95,
          "foundations": 12
        },
        "last_synced": "2026-05-04T08:00:00"
      }
    ],
    "stat_totals": {
      "columns": 210,
      "walls": 88
    }
  }
]
```

Notes:
- Data is joined from `dbo.Project` (Clarity) and `management.project_meta` (platform edits)
- `project_number` is the firm's stable code (e.g. `"20205"`); `project_id` is the Clarity integer PK
- Multiple files per project number are grouped under one object

---

### `GET /projects/{number}`

**Get full detail for one project by project number.**

Path: `number` — project number string (e.g. `"20205"`)

Response — same shape as one item from the list, with levels added to each file:
```json
{
  "project_number": "20205",
  "display_name": "...",
  "files": [
    {
      "project_id": 14,
      "file_name": "...",
      "levels": [
        {"id": 101, "name": "L01", "elevation": 0.0, "story_height": 3200.0}
      ],
      "element_counts": { "columns": 210, "walls": 88, "beams": 340, "floors": 95, "foundations": 12 }
    }
  ]
}
```

---

### `PATCH /projects/{number}`

**Edit project metadata.** Writes ONLY to `management.project_meta` — never touches `dbo.Project`.

Request body (all fields optional):
```json
{
  "display_name": "string",
  "address": "string",
  "job_name": "string",
  "designer": "string"
}
```

Response: updated project detail object.

---

### `DELETE /projects/{number}`

**Delete a project** and all associated design data.

Returns `204 No Content`.

Cascade deletes: `management.project_meta`, all `design.*` rows for this project number.
Does NOT delete `dbo` rows — those are Clarity-owned.

---

### `DELETE /projects/files/{file_id}`

**Delete one Revit file** (one `dbo.Project` row) and its associated design data.

Path: `file_id` — integer `project_id` (Clarity PK)

Returns `204 No Content`.

Notes:
- Deletes the `dbo.Project` record and cascades into `dbo.Columns`, `dbo.Walls`, etc. (one of the three permitted Clarity-table deletes)
- If this is the last file for a project number, `project_meta` is also cleaned up

---

### `POST /projects/{number}/merge`

**Merge a duplicate project number** into the canonical project number.

Request body:
```json
{
  "source_number": "20205A"
}
```

Response: updated project detail for the target number.

Notes:
- Re-assigns all `design.*` rows from `source_number` to `number`
- Removes `management.project_meta` for `source_number`
- Use when Clarity created the same physical project under two different numbers

---

## 2. Elements

Returns Revit geometry for one floor, used to render the tributary canvas.

### `GET /projects/files/{file_id}/levels/{level_id}/elements`

**Get all structural elements for one level — columns, walls, grids, and slab boundary.**

Path parameters:
- `file_id` — integer `project_id` (Clarity PK)
- `level_id` — integer level id from `dbo.Levels`

Response:
```json
{
  "project_id": 14,
  "level_id": 101,
  "columns": [
    {
      "guid": "abc123",
      "mark": "C1",
      "element_id": 550023,
      "level_name": "L01",
      "x": 8878.0,
      "y": 6675.0,
      "d": null,
      "b": 600,
      "h": 600,
      "rotation": 0
    }
  ],
  "walls": [
    {
      "guid": "def456",
      "mark": "W22",
      "element_id": 550100,
      "level_name": "L01",
      "x1": 0.0, "y1": 0.0,
      "x2": 5000.0, "y2": 0.0,
      "thickness": 200
    }
  ],
  "grids": [
    {"name": "A", "x1": 0.0, "y1": -1000.0, "x2": 0.0, "y2": 20000.0}
  ],
  "slab_boundary_wkt": "POLYGON ((0 0, 10000 0, 10000 8000, 0 8000, 0 0))",
  "slab_openings": ["POLYGON ((4000 3000, 5000 3000, 5000 4000, 4000 4000, 4000 3000))"]
}
```

Field notes:
- `x`, `y` — column centre in mm (parsed from `dbo.Columns.BaseLocation` text `"x,y,z"`)
- `d` — diameter for circular columns; `null` for rectangular (use `b` × `h`)
- `b` — vertical plan dimension (mm); `h` — horizontal plan dimension (mm); `rotation` — degrees
- `x1/y1`, `x2/y2` — wall centreline endpoints in mm (parsed from `dbo.Walls.StartLocation` / `EndLocation`)
- `slab_boundary_wkt` — WKT polygon of the slab boundary, from `dbo.Floors` where `FloorType.TypeName != 'OPENING'`
- `slab_openings` — WKT polygons where `FloorType.TypeName = 'OPENING'` — these are slab holes to be excluded from boundary

---

## 3. Load Tables

Defines load types (RES, BALC, MEC, ROOF, etc.) per Revit file. Load types carry dead/live kPa values and an LLRF type that controls live load reduction factor behaviour in the rundown engine.

**Important:** The POST (bulk replace) endpoint clears all downstream computed data for that file: `design.load_areas`, `design.tributary_results`, `design.load_assignments`, and `design.rundown` rows. Load type changes invalidate all computed results by design.

### `GET /projects/files/{file_id}/load-table`

**Get all load table entries for a file.**

Response:
```json
[
  {
    "id": 12,
    "project_number": "20205",
    "project_id": 14,
    "name": "RES",
    "description": "Residential",
    "dead_load_kpa": "2.0000",
    "live_load_kpa": "1.9000",
    "llrf_type": "R",
    "created_by": "system",
    "created_at": "2026-05-01T10:00:00",
    "updated_at": "2026-05-01T10:00:00"
  }
]
```

`llrf_type` values: `"R"` (reducible per NBC/NBCC), `"N"` (non-reducible), or custom code.

---

### `POST /projects/files/{file_id}/load-table`

**Replace all load table entries for a file (bulk replace).**

Request body:
```json
[
  {
    "name": "RES",
    "description": "Residential",
    "dead_load_kpa": 2.0,
    "live_load_kpa": 1.9,
    "llrf_type": "R"
  },
  {
    "name": "ROOF",
    "description": "Roof",
    "dead_load_kpa": 3.5,
    "live_load_kpa": 1.0,
    "llrf_type": "N"
  }
]
```

Response: list of created entries (same shape as GET).

**Side effects (cascade delete before insert):**
Deletes all `design.load_areas`, `design.tributary_results`, `design.load_assignments`, and `design.rundown` rows for this `project_id`. The FK constraints are `NO_ACTION` so the service deletes dependents explicitly before replacing the load table.

---

### `PATCH /projects/files/{file_id}/load-table/{entry_id}`

**Edit one load table entry in-place.**

Request body (all fields optional):
```json
{
  "name": "RES",
  "description": "Residential — updated",
  "dead_load_kpa": 2.5,
  "live_load_kpa": 1.9,
  "llrf_type": "R"
}
```

Response: updated entry object.

---

### `DELETE /projects/files/{file_id}/load-table/{entry_id}`

**Delete one load table entry.**

Returns `204 No Content`.

---

## 4. Tributary

Computes Voronoi-based tributary areas for one floor. Takes element positions from `dbo` (Revit), optionally intersects user-drawn load area polygons, and writes results into `design.tributary_results` and `design.load_assignments`.

### `POST /tributary/compute`

**Run Voronoi computation for one floor.**

Request body:
```json
{
  "project_id": 14,
  "level_above_id": 105,
  "level_below_id": 101,
  "floor_boundary_source": "slab_db",
  "floor_boundary_wkt": null,
  "load_areas": [
    {
      "polygon_wkt": "POLYGON ((0 0, 5000 0, 5000 5000, 0 5000, 0 0))",
      "load_table_id": 12
    }
  ],
  "wall_spacing_mm": 200.0
}
```

`floor_boundary_source` options:
- `"slab_db"` — use slab boundary from `dbo.Floors` at `level_above_id`
- `"json_upload"` — use the WKT polygon supplied in `floor_boundary_wkt`
- `"drawn_areas"` — use the union of user-drawn areas from `design.load_areas`

`level_above_id` — the floor plate being loaded (slab boundary comes from this level)
`level_below_id` — the supporting elements below (column/wall positions come from this level)
`wall_spacing_mm` — sample point spacing along wall centrelines for Voronoi seed generation

Response:
```json
{
  "project_id": 14,
  "level_above_id": 105,
  "level_below_id": 101,
  "boundary_area_m2": "320.450",
  "column_count": 18,
  "wall_count": 6,
  "cells": [
    {
      "element_guid": "abc123",
      "element_type": "column",
      "polygon_wkt": "POLYGON ((...))",
      "area_m2": "14.200",
      "beam_weights_detail": "80.5,49.8"
    }
  ],
  "load_assignments": [
    {
      "element_guid": "abc123",
      "element_type": "column",
      "load_table_id": 12,
      "tributary_area_m2": "14.200",
      "dead_load_kn": "28.400",
      "live_load_kn": "26.980"
    }
  ]
}
```

`beam_weights_detail` — comma-separated concrete beam kN values intersecting this cell; `null` if no concrete beams.

Side effects: Writes cells to `design.tributary_results` and assignments to `design.load_assignments`, replacing any existing records for this `project_id` + `level_id` combination.

---

### `GET /tributary/results/{project_id}/{level_id}`

**Get stored tributary area results for one floor.**

Response:
```json
[
  {
    "id": 201,
    "element_guid": "abc123",
    "element_type": "column",
    "project_id": 14,
    "level_id": 101,
    "load_table_id": 12,
    "tributary_area_m2": "14.200",
    "polygon_wkt": "POLYGON ((...))",
    "computed_at": "2026-05-01T10:00:00"
  }
]
```

---

### `GET /tributary/assignments/{project_id}/{level_id}`

**Get stored load assignments for one floor.**

Response:
```json
[
  {
    "element_guid": "abc123",
    "element_type": "column",
    "load_table_id": 12,
    "tributary_area_m2": "14.200",
    "dead_load_kn": "28.400",
    "live_load_kn": "26.980"
  }
]
```

---

### `GET /tributary/download/{project_id}/{level_id}`

**Download tributary results as CSV.**

Response: CSV file attachment.
- `Content-Disposition: attachment; filename="tributary_<project_id>_<level_id>.csv"`
- Columns: `element_guid`, `element_type`, `load_type`, `tributary_area_m2`, `dead_load_kn`, `live_load_kn`

---

## 5. Identity Hub

Cross-source identity resolution — maps the same physical element across Revit GUIDs, spreadsheet marks, and future ETABS IDs. Tables are scoped to `project_number` (stable) so they survive Clarity wipe-reload cycles.

**Auto-sync behaviour:** All GET endpoints call `auto_sync_if_needed()` internally. If Clarity has synced new data since the last identity update, the identity tables are refreshed before returning. An explicit POST sync is also available for forcing a refresh.

**Confidence scale:**
- `>= 0.90` — auto-matched (green, high confidence)
- `0.70–0.89` — fuzzy match (yellow, needs review)
- `< 0.70` — no match found (red, manual correction required)

### `POST /projects/{number}/levels/sync`

**Populate or refresh `design.level_identity` from Revit levels.**

No request body.

Response:
```json
{
  "synced": true,
  "created": 19,
  "updated": 0,
  "stale": 0,
  "stale_names": [],
  "levels": [
    {
      "id": 301,
      "project_number": "20205",
      "canonical_name": "L01",
      "sort_order": 1,
      "revit_level_id": 101,
      "revit_name": "Level 1",
      "rundown_name": "GF",
      "etabs_name": null,
      "revit_elevation_mm": 0.0,
      "match_confidence": "0.95",
      "match_method": "exact",
      "created_at": "...",
      "updated_at": "..."
    }
  ]
}
```

Notes:
- Level matching uses `sort_order` (ordinal position), **not** elevation. Revit elevations are unreliable for cross-source matching — two sources rarely agree on the exact elevation value.
- `canonical_name` is the platform's authoritative name; `revit_name` and `rundown_name` may differ (e.g. Revit calls it `"Level 1"`, the spreadsheet calls it `"GF"`).
- `stale_names` lists levels present in `design.level_identity` but no longer in `dbo.Levels` — likely deleted from the Revit model.

---

### `GET /projects/{number}/levels/identity`

**List all level identities for a project.** Auto-syncs if Revit data has changed.

Response: `LevelSyncResult` (same shape as POST sync response above).

---

### `PATCH /projects/{number}/levels/identity/{level_id}`

**Manually correct a level identity record.**

Path: `level_id` — integer `design.level_identity.id`

Request body (all optional):
```json
{
  "canonical_name": "GF",
  "sort_order": 1,
  "rundown_name": "Ground",
  "etabs_name": "Story1"
}
```

Response: updated `LevelIdentityRead` object.

---

### `POST /projects/{number}/elements/sync`

**Populate or refresh `design.element_identity` from Revit elements.**

No request body.

Response:
```json
{
  "synced": true,
  "created": 298,
  "updated": 0,
  "stale": 2,
  "stale_marks": ["C99", "W14"],
  "mark_errors": 3,
  "elements": [ ... ]
}
```

`mark_errors` — elements whose Revit mark failed to parse (e.g. a wall marked `"C12"` — column naming pattern on a wall type). The mark parser flags these; they appear in the identity table for manual review.

---

### `GET /projects/{number}/elements/identity/stats`

**Summary statistics for element identity coverage.**

Response:
```json
{
  "total": 298,
  "columns": 210,
  "walls": 88,
  "by_confidence": {
    "high": 270,
    "medium": 20,
    "low": 8
  },
  "stale": 2,
  "mark_errors": 3
}
```

---

### `GET /projects/{number}/elements/identity`

**List all element identities.** Auto-syncs if Revit data has changed.

Query parameters (all optional):
- `element_type` — filter by `"column"` or `"wall"`
- `confidence` — filter by `"high"` / `"medium"` / `"low"`
- `has_errors` — `true` to show only elements with mark parse errors

Response:
```json
[
  {
    "id": 401,
    "project_number": "20205",
    "element_type": "column",
    "canonical_mark": "C1",
    "level_identity_id": 301,
    "revit_guid": "abc123-...",
    "rundown_key": "C1",
    "etabs_id": null,
    "match_confidence": "0.95",
    "match_method": "exact",
    "last_resolved": "2026-05-01T10:00:00",
    "notes": null,
    "created_at": "...",
    "updated_at": "..."
  }
]
```

---

### `PATCH /projects/{number}/elements/identity/{element_id}`

**Manually correct an element identity record.**

Path: `element_id` — integer `design.element_identity.id`

Request body (all optional):
```json
{
  "canonical_mark": "C1",
  "element_type": "column",
  "level_identity_id": 301,
  "rundown_key": "C1",
  "etabs_id": null,
  "notes": "Manually corrected — Revit mark was set to wall naming convention by mistake"
}
```

Response: updated `ElementIdentityRead` object.

---

## 6. Rundown

Gravity load rundown — cumulative DL/LL from roof to footing per element. Every intermediate value is stored in `design.rundown` (40+ columns). No black boxes; engineers can verify every computed value.

**Two data source paths lead to the same computation engine and the same DB tables:**

```
.xlsm spreadsheet  →  POST /rundown/upload (preview)
                   →  POST /rundown/upload/confirm (compute + store)

DXF files          →  POST /rundown/cad-upload (compute + store directly)
```

**Route registration order matters.** The `/{mark}` route is a catch-all and must be registered last. The following literal path segments are registered before it so they are not mistakenly captured as element marks: `upload`, `upload/confirm`, `cad-upload`, `recent`, `validation`, `summary`, `load-types`, `rows/{row_id}`, `transfers`, `recompute`, `export`.

---

### `GET /rundown/recent`

**List projects that have rundown data.** (Note: no `{number}` prefix — this is a cross-project query.)

Full path: `GET /api/rundown/recent`

Response:
```json
{
  "items": [
    {
      "project_number": "24043",
      "element_count": 12,
      "data_source": "spreadsheet",
      "computed_at": "2026-05-01T10:00:00"
    }
  ]
}
```

Items are ordered most-recently-computed first.

---

### `POST /projects/{number}/rundown/upload`

**Parse a rundown spreadsheet — preview only, no DB write.**

Content-Type: `multipart/form-data`
Form fields: `file` — `.xlsm` file

Response:
```json
{
  "project_number": "20205",
  "job_name": "20205 TEMPLE MIXED USE",
  "designer": "JP",
  "element_count": 22,
  "level_count": 19,
  "load_type_count": 4,
  "errors": [],
  "warnings": ["W10A: transfer percent exceeds 100%"],
  "discrepancy_count": 0,
  "discrepancies": []
}
```

`discrepancies` — differences between values stored in Excel and values recomputed by the engine from raw inputs. A non-zero `discrepancy_count` means the Excel file was likely manually edited after the VBA macro ran. Each item:
```json
{
  "element_mark": "C2",
  "floor_index": 3,
  "top_level": "L05",
  "field_name": "dl_cumulative_kn",
  "computed_value": 1842.3,
  "imported_value": 1840.0,
  "difference": 2.3
}
```

Notes:
- Project need not exist yet — upload is the onboarding path for new projects
- The file is parsed but nothing is written; call `/upload/confirm` with the same file to commit

---

### `POST /projects/{number}/rundown/upload/confirm`

**Re-parse the spreadsheet, compute all floor results, and store to DB.**

Content-Type: `multipart/form-data`
Form fields: `file` — same `.xlsm` file

The file is re-parsed (not cached), so the user must re-send the file.

Response:
```json
{
  "project_number": "20205",
  "rows_written": 418,
  "element_count": 22,
  "validation_is_valid": true,
  "validation_errors": [],
  "validation_warnings": []
}
```

Side effects:
- Replaces all `design.rundown` rows for this `project_number` (DELETE then INSERT)
- Creates `management.project_meta` entry if the project doesn't exist yet
- Stores load types in `design.load_tables` with `project_id = 0` (sentinel for rundown-path load types, distinct from Revit-path load types which have a real `project_id`)

---

### `POST /projects/{number}/rundown/cad-upload`

**Upload DXF files with level/load type config, compute and store rundown.**

Content-Type: `multipart/form-data`

Form fields:
- `files` — one or more `.dxf` file uploads (each file = one element's floor data)
- `file_level_map` — JSON string: `[{"filename": "C2_L01.dxf", "bot_level": "L01", "top_level": "L02"}]`
- `level_pairs` — JSON string: `[{"bot": "L01", "top": "L02", "height_m": 3.2, "concrete_mpa": 32}]`
- `load_types` — JSON string: `[{"code": "RES", "description": "Residential", "dead_kpa": 2.0, "live_kpa": 1.9, "llrf_type": "R"}]`
- `cladding_kpa` — float, default `0.0`

`file_level_map` maps each DXF filename to the bot/top level names for that sheet. `level_pairs` defines the full level stack with heights and concrete grades. Both are JSON strings embedded in the multipart form.

Response: `RundownComputeResult` (same shape as `/upload/confirm`).

Side effects: Same as `/upload/confirm` — replaces all `design.rundown` rows for this project.

---

### `DELETE /projects/{number}/rundown`

**Delete all rundown data for a project.**

Returns `204 No Content`.

Deletes:
- `design.rundown` rows for this `project_number`
- `design.rundown_transfers` for this `project_number`
- `design.load_tables` where `project_number = number AND project_id = 0` (rundown-uploaded load types)

Does NOT delete `management.project_meta` or `design.element_identity` / `design.level_identity` (shared with Revit path).

---

### `GET /projects/{number}/rundown/load-types`

**Get load types stored for a rundown project.**

Response:
```json
[
  {
    "id": 55,
    "code": "RES",
    "description": "Residential",
    "dead_kpa": 2.0,
    "live_kpa": 1.9,
    "llrf_type": "R"
  }
]
```

Returns `design.load_tables` rows where `project_id = 0` (the rundown-path sentinel).

---

### `POST /projects/{number}/rundown/load-types`

**Replace all load types for a rundown project.**

Request body:
```json
{
  "entries": [
    {
      "name": "RES",
      "description": "Residential",
      "dead_load_kpa": 2.0,
      "live_load_kpa": 1.9,
      "llrf_type": "R"
    }
  ]
}
```

Response:
```json
{"count": 4}
```

---

### `GET /projects/{number}/rundown`

**List all rundown elements — summary view.**

Response:
```json
{
  "project_number": "20205",
  "element_count": 22,
  "load_type_count": 4,
  "data_source": "spreadsheet",
  "computed_at": "2026-05-01T10:00:00",
  "job_name": "20205 TEMPLE MIXED USE",
  "designer": "JP",
  "elements": [
    {
      "mark": "C2",
      "element_type": "column",
      "floor_count": 19,
      "dl_cumulative_kn": 8420.5,
      "ll_cumulative_kn": 1180.3,
      "pf_kn": 9600.8,
      "cross_section_m2": 0.36,
      "data_source": "spreadsheet"
    }
  ]
}
```

`dl_cumulative_kn`, `ll_cumulative_kn`, `pf_kn` show values at the **lowest computed floor** (footing level).
`floor_order` is ascending — index `0` = roof, last index = footing.

---

### `GET /projects/{number}/rundown/validation`

**Re-run validation on stored results.** Registered before `/{mark}` — `"validation"` is a literal path.

Response:
```json
{
  "project_number": "20205",
  "is_valid": true,
  "area_checks": [
    {
      "bot_level": "L01",
      "top_level": "L02",
      "total_area_m2": 320.45,
      "cum_area_m2": 320.45,
      "area_difference_m2": 0.0,
      "is_balanced": true
    }
  ],
  "transfer_checks": [
    {
      "element_mark": "W22",
      "pct_transferred": 0.85,
      "to_elements": ["C2", "C3"],
      "all_within_range": true,
      "status": "ok"
    }
  ],
  "data_gaps": [],
  "errors": [],
  "warnings": []
}
```

`area_checks` — each floor level is checked: does the sum of all element tributary areas equal the slab boundary area? `area_difference_m2` should be near zero.

`transfer_checks.status` values: `"ok"`, `"under"` (< 0%), `"over"` (> 200%), `"none"` (no transfers defined for this element).

Returns `is_valid = false` with an error message if no rundown rows exist for the project.

---

### `GET /projects/{number}/rundown/summary`

**Cross-element summary matrix — pivot table.** Registered before `/{mark}`.

Query parameters:
- `metric` — one of: `DL`, `LL`, `PW`, `PF`, `F / A`, `% Steel`, `As`, `AREA`, `XFER AREA`, `CUM AREA` (default: `PF`)

Response:
```json
{
  "columns": [
    {"mark": "C2", "element_type": "column"},
    {"mark": "W22", "element_type": "wall"}
  ],
  "levels": [
    {"bot_level": "ROOF", "top_level": "L19"},
    {"bot_level": "L01", "top_level": "L02"}
  ],
  "metric": "PF",
  "values": [
    [450.2, 280.1],
    [9600.8, 6100.4]
  ]
}
```

`values[level_index][column_index]` — value of the selected metric at that floor for that element. `null` if no data.
Levels are ordered top-to-bottom (roof first). Columns follow the order elements appear in the DB.

---

### `PATCH /projects/{number}/rundown/rows/{row_id}`

**Edit rebar fields on a single rundown row.** Registered before `/{mark}`.

Path: `row_id` — integer `design.rundown.id` (the `id` field in `FloorResultRead`)

Request body:
```json
{
  "bar_size": "25M",
  "qty": 1,
  "n_bars": 12,
  "c_bars": 0,
  "qty_override": false,
  "n_bars_override": true,
  "c_bars_override": false
}
```

Override flags: when `true`, that value is user-set and the engine will not overwrite it during recompute.

Response:
```json
{
  "id": 501,
  "bar_size": "25M",
  "qty": 1,
  "n_bars": 12,
  "c_bars": 0,
  "rebar_design": "12-25M N",
  "as_mm2": 6000.0,
  "qty_override": false,
  "n_bars_override": true,
  "c_bars_override": false
}
```

Rebar terminology:
- `n_bars` — Nbars: normal lap bars
- `c_bars` — Cbars: coupler bars (not "corner" or "face")
- `rebar_design` — formatted string, e.g. `"12-25M N"` (all normal laps) or `"8-25M N + 4-25M C"` (mix)

---

### `GET /projects/{number}/rundown/transfers`

**Get all transfer definitions for a project.** Registered before `/{mark}`.

A transfer means: at level `target_level`, element `target_element` receives `percent` of the cumulative load from `source_element`. Transfers model load path changes where a wall or column's load is redistributed to adjacent elements.

Response:
```json
[
  {
    "id": 601,
    "target_element": "C2",
    "source_element": "W22",
    "target_level": "L08",
    "percent": 0.85,
    "created_by": "system",
    "dl_kn": null,
    "ll_kn": null,
    "cum_area_m2": null
  }
]
```

`dl_kn`, `ll_kn`, `cum_area_m2` are `null` on this endpoint (populated on per-element endpoint below).

---

### `GET /projects/{number}/rundown/transfers/{mark}`

**Get transfers received by one element, with computed load values.**

Path: `mark` — receiving element mark (e.g. `"C2"`)

Response: same shape as above, but `dl_kn`, `ll_kn`, `cum_area_m2` are computed from the source element's stored rundown data at `target_level`:
- `dl_kn` = `source.dl_cumulative_kn` × `percent`
- `ll_kn` = `source.ll_cumulative_kn` × `percent`
- `cum_area_m2` = `source.cum_area_m2` × `percent`

---

### `PUT /projects/{number}/rundown/transfers/{mark}`

**Replace all transfer definitions received by one element.**

Path: `mark` — the receiving element

Request body:
```json
{
  "transfers": [
    {
      "source_element": "W22",
      "target_level": "L08",
      "percent": 0.85
    }
  ]
}
```

`percent` is proportional: `0.85` = 85% of source cumulative load transferred. Range: `0.0 < percent <= 2.0`.

Response:
```json
{"count": 1, "target_element": "C2"}
```

**Does NOT recompute.** Call `POST /recompute` after updating transfers to propagate the load changes.

---

### `POST /projects/{number}/rundown/recompute`

**Recompute entire project from stored inputs + current transfer definitions.**

No request body.

Response: `RundownComputeResult` (same as `/upload/confirm`).

Use case: after editing transfers via `PUT /transfers/{mark}`, call this to re-run the engine and update DL/LL values for all affected elements.

---

### `GET /projects/{number}/rundown/export`

**Export rundown data as `.xlsx` for VBA import.** Registered before `/{mark}`.

Response: file download.
- `Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
- `Content-Disposition: attachment; filename="{number}_Rundown_Data.xlsx"`

Generates a data pack formatted for the `ImportFromPlatform` VBA macro in the Excel rundown template.
Returns `404` if no rundown data exists for the project.

---

### `GET /projects/{number}/rundown/{mark}`

**Get full floor-by-floor detail for one element.** Registered last — catch-all.

Path: `mark` — element mark (e.g. `"C2"`, `"W22"`, `"W10A"`)

Response:
```json
{
  "mark": "C2",
  "element_type": "column",
  "floor_count": 19,
  "floors": [
    {
      "id": 501,
      "bot_level": "ROOF",
      "top_level": "L19",
      "story_height_m": 3.2,
      "concrete_mpa": 32.0,
      "dim_x_mm": 600.0,
      "dim_y": "600",
      "cross_section_m2": 0.36,
      "dl_from_above_kn": 0.0,
      "dl_floor_load_kn": 450.2,
      "dl_transfer_kn": 0.0,
      "dl_self_weight_kn": 18.4,
      "dl_cladding_kn": 12.8,
      "dl_beam_weight_kn": 0.0,
      "dl_cumulative_kn": 481.4,
      "ll_reducible_kn": 180.3,
      "ll_non_reducible_this_floor_kn": 0.0,
      "ll_transfer_kn": 0.0,
      "dy_cumulative_kn": 0.0,
      "ll_cumulative_kn": 180.3,
      "area_this_floor_m2": 14.2,
      "transfer_area_m2": 0.0,
      "cum_area_m2": 14.2,
      "pw_kn": 481.4,
      "pf_kn": 661.7,
      "f_over_a_mpa": 1.84,
      "alpha_factor": null,
      "phi": null,
      "pct_steel": 1.2,
      "as_mm2": 4320.0,
      "bar_size": "25M",
      "qty": 1,
      "n_bars": 8,
      "c_bars": 4,
      "rebar_design": "8-25M N + 4-25M C",
      "qty_override": false,
      "n_bars_override": false,
      "c_bars_override": false,
      "area_by_type": {"RES": 14.2},
      "cum_area_by_type": {"RES": 14.2},
      "llrf_by_type": {"RES": 0.85},
      "ll_non_reducible_by_type": {"ROOF": 0.0},
      "data_source": "spreadsheet",
      "floor_order": 1
    }
  ]
}
```

`floors` is ordered top-to-bottom: index `0` = roof, last = footing. `floor_order = 1` corresponds to the roof.

`dim_y` is a string — may be a number (`"600"`) or a letter code:
- `"D"` — diameter (circular column, use `dim_x_mm` as diameter)
- `"S"` — square (use `dim_x_mm` for both dimensions)
- `"W"` — wall thickness

`id` is the `design.rundown` row PK — use it as `row_id` in `PATCH /rundown/rows/{row_id}`.

DL breakdown:
- `dl_from_above_kn` — load carried from the floor above (cumulative pass-through)
- `dl_floor_load_kn` — dead load from tributary area × dead kPa
- `dl_transfer_kn` — dead load received from transfers at this level
- `dl_self_weight_kn` — element self-weight (area × height × unit weight)
- `dl_cladding_kn` — cladding load (perimeter × height × cladding kPa)
- `dl_beam_weight_kn` — concrete beam weight in this cell
- `dl_cumulative_kn` — sum of all six terms

LL breakdown:
- `ll_reducible_kn` — reducible live load after LLRF applied
- `ll_non_reducible_this_floor_kn` — non-reducible LL contribution from this floor
- `ll_transfer_kn` — live load received from transfers
- `dy_cumulative_kn` — dynamic amplification (unused in current version)
- `ll_cumulative_kn` — total cumulative live load

---

## Appendix A: Element Naming Convention

```
[PREFIX optional] [C or W required] [NUMBER] [SUFFIX optional] . [COMMENTS optional]
```

Examples:
- `C1` — Column 1
- `W22` — Wall 22
- `C1A.1` — Column 1A, instance 1 (same vertical chain as `C1A.2`)
- `W10A` — Wall 10, split A
- `W10-W11-W12` — Grouped walls (single rundown entry, shared load)

Rules relevant to the API:
- Comments (`.1`, `.2`) represent the same physical element at different schedule positions — same `canonical_mark` in `element_identity`
- Suffixes (`A`, `B`) represent split elements at partial floors — separate `canonical_mark`
- `C{n}` and `W{n}` cannot share the same number on the same floor

---

## Appendix B: Interactive Docs

FastAPI auto-generates interactive documentation at:
- `http://<host>/docs` — Swagger UI (send requests directly in the browser)
- `http://<host>/redoc` — ReDoc (read-only reference view)
