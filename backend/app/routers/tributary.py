"""Tributary area computation API router.

POST /api/tributary/compute:
  1. Build slab boundary from level_above (or accept WKT)
  2. Query columns/walls from level_below
  3. Compute Voronoi tributary areas
  4. If load_areas provided: intersect, compute load assignments, write to DB
  5. Return results

GET /api/tributary/results/{project_id}/{level_id}:
  Return stored tributary results.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from shapely import wkt as shapely_wkt
from shapely.geometry import Polygon
from shapely.ops import unary_union
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import ColumnType, DboColumn, Level, LoadTable, Project, Wall, WallType
from app.schemas.tributary import (
    ComputeRequest,
    ComputeResponse,
    LoadAssignmentResult,
    StoredTributaryResult,
    TributaryCellResult,
)
from app.services.beam_weight import compute_beam_weights
from app.services.coordinate_parser import parse_column_location, parse_wall_locations
from app.services.slab_boundary import get_slab_boundary
from app.services.voronoi import ColumnSeed, WallSeed, compute_tributary_areas

router = APIRouter(tags=["tributary"])


def _verify_project_and_levels(
    db: Session, project_id: int, level_above_id: int, level_below_id: int,
) -> Project:
    """Raise 404 if project or either level doesn't exist. Returns project."""
    project = db.query(Project).filter(Project.Id == project_id).first()
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")
    for lid, label in [(level_above_id, "above"), (level_below_id, "below")]:
        level = db.query(Level).filter(
            Level.id == lid, Level.Project_id == project_id,
        ).first()
        if level is None:
            raise HTTPException(
                404, f"Level {label} ({lid}) not found for project {project_id}",
            )
    return project


def _get_columns_for_level(
    db: Session, project_id: int, level_id: int,
) -> list[ColumnSeed]:
    """Query columns where BaseConstraint_id = level_id."""
    rows = db.query(DboColumn).filter(
        DboColumn.Project_id == project_id,
        DboColumn.BaseConstraint_id == level_id,
    ).all()
    seeds = []
    for col in rows:
        loc = parse_column_location(col.BaseLocation)
        if loc is None:
            continue
        seeds.append(ColumnSeed(guid=col.guid, x=loc[0], y=loc[1]))
    return seeds


def _get_walls_for_level(
    db: Session, project_id: int, level_id: int,
) -> list[WallSeed]:
    """Query walls where BaseConstraint_id = level_id."""
    rows = db.query(Wall).filter(
        Wall.Project_id == project_id,
        Wall.BaseConstraint_id == level_id,
    ).all()
    seeds = []
    for wall in rows:
        locs = parse_wall_locations(wall.StartLocation, wall.Endlocation)
        if locs is None:
            continue
        (x1, y1), (x2, y2) = locs
        seeds.append(WallSeed(guid=wall.guid, x1=x1, y1=y1, x2=x2, y2=y2))
    return seeds


@router.post(
    "/tributary/compute",
    response_model=ComputeResponse,
    status_code=201,
)
def compute_tributary(
    req: ComputeRequest,
    db: Session = Depends(get_db),
) -> ComputeResponse:
    """Compute Voronoi tributary areas.

    Optionally intersects with user-drawn load areas and writes
    tributary_results + load_assignments to the design schema.
    """
    project = _verify_project_and_levels(db, req.project_id, req.level_above_id, req.level_below_id)

    # --- 1. Build boundary ---------------------------------------------------
    if req.floor_boundary_source == "json_upload":
        if not req.floor_boundary_wkt:
            raise HTTPException(400, "floor_boundary_wkt required when source=json_upload")
        try:
            boundary = shapely_wkt.loads(req.floor_boundary_wkt)
        except Exception:
            raise HTTPException(400, "Invalid boundary WKT")
        if not isinstance(boundary, Polygon) or boundary.is_empty:
            raise HTTPException(400, "Boundary must be a non-empty Polygon")
    elif req.floor_boundary_source == "drawn_areas":
        if not req.load_areas:
            raise HTTPException(400, "load_areas required when source=drawn_areas")
        try:
            polys = [shapely_wkt.loads(la.polygon_wkt) for la in req.load_areas]
        except Exception:
            raise HTTPException(400, "Invalid load area WKT")
        boundary = unary_union(polys)
        if boundary.is_empty:
            raise HTTPException(400, "Drawn areas produce an empty boundary")
        # If union produces MultiPolygon, take convex hull to get single Polygon
        if boundary.geom_type == "MultiPolygon":
            boundary = boundary.convex_hull
    else:
        boundary = get_slab_boundary(db, req.project_id, req.level_above_id)
        if boundary is None:
            raise HTTPException(
                400, f"No slab geometry found for level {req.level_above_id}",
            )

    # --- 2. Get elements ------------------------------------------------------
    columns = _get_columns_for_level(db, req.project_id, req.level_below_id)
    walls = _get_walls_for_level(db, req.project_id, req.level_below_id)

    if not columns and not walls:
        raise HTTPException(
            400, f"No columns or walls found for level {req.level_below_id}",
        )

    # --- 3. Compute Voronoi ---------------------------------------------------
    cells = compute_tributary_areas(boundary, columns, walls, req.wall_spacing_mm)

    # --- 3b. Beam weight per element -----------------------------------------
    beam_weights = compute_beam_weights(db, req.project_id, req.level_below_id, cells)

    cell_results = [
        TributaryCellResult(
            element_guid=c.element_guid,
            element_type=c.element_type,
            polygon_wkt=c.polygon.wkt,
            area_m2=Decimal(str(round(c.area_m2, 4))),
            beam_weights_detail=",".join(
                str(v) for v in beam_weights.get(c.element_guid, [])
            ) or None,
        )
        for c in cells
    ]

    # --- 4. Load area intersection (optional) ---------------------------------
    load_assignment_results: list[LoadAssignmentResult] = []

    if req.load_areas:
        # Clear previous results for this project+level (raw SQL to avoid
        # GeoAlchemy2 geometry column issues on SQL Server)
        db.execute(text("""
            DELETE FROM design.load_assignments
            WHERE project_id = :pid AND level_id = :lid
        """), {"pid": req.project_id, "lid": req.level_below_id})
        db.execute(text("""
            DELETE FROM design.tributary_results
            WHERE project_id = :pid AND level_id = :lid
        """), {"pid": req.project_id, "lid": req.level_below_id})

        now = datetime.now(timezone.utc)

        for la_input in req.load_areas:
            # Validate load table exists for this project
            load_table = db.query(LoadTable).filter(
                LoadTable.id == la_input.load_table_id,
                LoadTable.project_id == req.project_id,
            ).first()
            if load_table is None:
                raise HTTPException(
                    400, f"Load table {la_input.load_table_id} not found for project",
                )

            try:
                la_poly = shapely_wkt.loads(la_input.polygon_wkt)
            except Exception:
                raise HTTPException(400, "Invalid load area WKT")
            if not la_poly.is_valid:
                la_poly = la_poly.buffer(0)
            if la_poly.is_empty:
                continue

            dead_kpa = float(load_table.dead_load_kpa or 0)
            live_kpa = float(load_table.live_load_kpa or 0)

            # Intersect each cell with this load area
            for cell in cells:
                intersection = cell.polygon.intersection(la_poly)
                if intersection.is_empty:
                    continue
                if intersection.geom_type not in ("Polygon", "MultiPolygon"):
                    continue

                area_m2 = intersection.area / 1e6
                dead_kn = area_m2 * dead_kpa
                live_kn = area_m2 * live_kpa

                # Raw SQL to avoid GeoAlchemy2 PostGIS functions on SQL Server.
                poly_wkt = intersection.wkt
                bm_list = beam_weights.get(cell.element_guid, [])
                bm_detail = ",".join(str(v) for v in bm_list) or None
                db.execute(text("""
                    INSERT INTO design.tributary_results
                    (project_number, element_guid, element_type, project_id, level_id,
                     load_table_id, tributary_polygon, tributary_area_m2,
                     beam_weights_detail, computed_at)
                    VALUES (:pnum, :guid, :etype, :pid, :lid, :ltid,
                            geometry::STGeomFromText(:poly_wkt, 0), :area,
                            :bm_detail, :at)
                """), {
                    "pnum": project.Number,
                    "guid": cell.element_guid,
                    "etype": cell.element_type,
                    "pid": req.project_id,
                    "lid": req.level_below_id,
                    "ltid": la_input.load_table_id,
                    "poly_wkt": poly_wkt,
                    "area": round(area_m2, 4),
                    "bm_detail": bm_detail,
                    "at": now,
                })

                db.execute(text("""
                    INSERT INTO design.load_assignments
                    (project_number, element_guid, element_type, project_id, level_id,
                     load_table_id, tributary_area_m2, dead_load_kn,
                     live_load_kn, computed_at)
                    VALUES (:pnum, :guid, :etype, :pid, :lid, :ltid, :area,
                            :dead, :live, :at)
                """), {
                    "pnum": project.Number,
                    "guid": cell.element_guid,
                    "etype": cell.element_type,
                    "pid": req.project_id,
                    "lid": req.level_below_id,
                    "ltid": la_input.load_table_id,
                    "area": round(area_m2, 4),
                    "dead": round(dead_kn, 4),
                    "live": round(live_kn, 4),
                    "at": now,
                })

                load_assignment_results.append(LoadAssignmentResult(
                    element_guid=cell.element_guid,
                    element_type=cell.element_type,
                    load_table_id=la_input.load_table_id,
                    tributary_area_m2=Decimal(str(round(area_m2, 4))),
                    dead_load_kn=Decimal(str(round(dead_kn, 4))),
                    live_load_kn=Decimal(str(round(live_kn, 4))),
                ))

        db.commit()

    # --- 5. Response ----------------------------------------------------------
    boundary_area_m2 = boundary.area / 1e6
    col_count = sum(1 for c in cells if c.element_type == "column")
    wall_count = sum(1 for c in cells if c.element_type == "wall")

    return ComputeResponse(
        project_id=req.project_id,
        level_above_id=req.level_above_id,
        level_below_id=req.level_below_id,
        boundary_area_m2=Decimal(str(round(boundary_area_m2, 4))),
        column_count=col_count,
        wall_count=wall_count,
        cells=cell_results,
        load_assignments=load_assignment_results,
    )


@router.get(
    "/tributary/results/{project_id}/{level_id}",
    response_model=list[StoredTributaryResult],
)
def get_tributary_results(
    project_id: int,
    level_id: int,
    db: Session = Depends(get_db),
) -> list[StoredTributaryResult]:
    """Get stored tributary results for a project/level."""
    project = db.query(Project).filter(Project.Id == project_id).first()
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")

    # Raw SQL to avoid GeoAlchemy2 geometry column issues on SQL Server.
    # Use .STAsText() to convert GEOMETRY → WKT (same pattern as download endpoint).
    rows = db.execute(text("""
        SELECT id, element_guid, element_type, project_id, level_id,
               load_table_id, tributary_area_m2,
               tributary_polygon.STAsText() AS polygon_wkt,
               computed_at
        FROM design.tributary_results
        WHERE project_id = :pid AND level_id = :lid
    """), {"pid": project_id, "lid": level_id}).fetchall()

    return [
        StoredTributaryResult(
            id=r.id, element_guid=r.element_guid, element_type=r.element_type,
            project_id=r.project_id, level_id=r.level_id,
            load_table_id=r.load_table_id, tributary_area_m2=r.tributary_area_m2,
            polygon_wkt=r.polygon_wkt, computed_at=r.computed_at,
        )
        for r in rows
    ]


@router.get(
    "/tributary/assignments/{project_id}/{level_id}",
    response_model=list[LoadAssignmentResult],
)
def get_tributary_assignments(
    project_id: int,
    level_id: int,
    db: Session = Depends(get_db),
) -> list[LoadAssignmentResult]:
    """Get stored load assignments for a project/level."""
    rows = db.execute(text("""
        SELECT element_guid, element_type, load_table_id,
               tributary_area_m2, dead_load_kn, live_load_kn
        FROM design.load_assignments
        WHERE project_id = :pid AND level_id = :lid
    """), {"pid": project_id, "lid": level_id}).fetchall()

    return [
        LoadAssignmentResult(
            element_guid=r.element_guid, element_type=r.element_type,
            load_table_id=r.load_table_id, tributary_area_m2=r.tributary_area_m2,
            dead_load_kn=r.dead_load_kn, live_load_kn=r.live_load_kn,
        )
        for r in rows
    ]


@router.get("/tributary/download/{project_id}/{level_id}")
def download_tributary_json(
    project_id: int,
    level_id: int,
    db: Session = Depends(get_db),
) -> Response:
    """Download tributary results as JSON for Dynamo/external tools.

    Returns a JSON file keyed by element_guid with surface coordinates,
    centroid, load table ids, and descriptive text.
    """
    # Verify project
    project = db.query(Project).filter(Project.Id == project_id).first()
    if project is None:
        raise HTTPException(404, f"Project {project_id} not found")

    # Get level name for filename
    level = db.query(Level).filter(
        Level.id == level_id, Level.Project_id == project_id,
    ).first()
    if level is None:
        raise HTTPException(404, f"Level {level_id} not found")

    # Query tributary results (with polygon WKT via STAsText)
    trib_rows = db.execute(text("""
        SELECT element_guid, element_type, load_table_id,
               tributary_polygon.STAsText() AS poly_wkt,
               tributary_area_m2,
               beam_weights_detail
        FROM design.tributary_results
        WHERE project_id = :pid AND level_id = :lid
    """), {"pid": project_id, "lid": level_id}).fetchall()

    if not trib_rows:
        raise HTTPException(404, "No tributary results found for this level")

    # Query load assignments for area per element+load_table
    assign_rows = db.execute(text("""
        SELECT element_guid, load_table_id, tributary_area_m2
        FROM design.load_assignments
        WHERE project_id = :pid AND level_id = :lid
    """), {"pid": project_id, "lid": level_id}).fetchall()

    # Build assignment lookup: {element_guid: [(load_table_id, area_m2), ...]}
    assignments: dict[str, list[tuple[int, float]]] = defaultdict(list)
    for row in assign_rows:
        assignments[row[0]].append((row[1], float(row[2])))

    # Build load table name lookup
    load_tables = db.query(LoadTable).filter(
        LoadTable.project_id == project_id,
    ).all()
    lt_names: dict[int, str] = {lt.id: lt.name for lt in load_tables}

    # Build element info lookups (mark, element_id, section dimensions)
    # Columns
    col_rows = (
        db.query(DboColumn.guid, DboColumn.id, DboColumn.Mark,
                 ColumnType.D, ColumnType.B)
        .outerjoin(ColumnType, DboColumn.Section_id == ColumnType.id)
        .filter(
            DboColumn.Project_id == project_id,
            DboColumn.BaseConstraint_id == level_id,
        ).all()
    )
    col_info: dict[str, dict] = {}
    for guid, eid, mark, d, b in col_rows:
        col_info[guid] = {"element_id": eid, "mark": mark, "D": d, "B": b}

    # Walls
    wall_rows = (
        db.query(Wall.guid, Wall.id, Wall.Mark, WallType.Thickness)
        .outerjoin(WallType, Wall.Section_id == WallType.id)
        .filter(
            Wall.Project_id == project_id,
            Wall.BaseConstraint_id == level_id,
        ).all()
    )
    wall_info: dict[str, dict] = {}
    for guid, eid, mark, thickness in wall_rows:
        wall_info[guid] = {"element_id": eid, "mark": mark, "thickness": thickness}

    # Build per-element beam weight detail lookup (first non-null row wins —
    # all rows for the same element share the same value)
    bm_detail_per_guid: dict[str, list[float]] = {}
    for row in trib_rows:
        guid = row[0]
        if guid not in bm_detail_per_guid and row.beam_weights_detail:
            bm_detail_per_guid[guid] = [
                float(v) for v in row.beam_weights_detail.split(",") if v
            ]

    # Group tributary results by element_guid — merge polygons per element
    # An element may have multiple trib results (one per load area)
    # Use the first polygon with valid WKT for the surface
    elem_polys: dict[str, str | None] = {}
    for row in trib_rows:
        guid = row[0]
        if guid not in elem_polys and row[3]:
            elem_polys[guid] = row[3]

    # Build JSON output
    result: dict[str, dict] = {}
    seen_guids: set[str] = set()

    for row in trib_rows:
        guid = row[0]
        if guid in seen_guids:
            continue
        seen_guids.add(guid)

        elem_type = row[1]
        poly_wkt = elem_polys.get(guid)

        # Parse polygon to get surface coordinates and centroid
        surface: list[list[float]] = []
        centroid: list[float] = [0, 0]
        if poly_wkt:
            try:
                poly = shapely_wkt.loads(poly_wkt)
                if poly.geom_type == "Polygon":
                    surface = [[round(x, 2), round(y, 2)]
                               for x, y in poly.exterior.coords]
                elif poly.geom_type == "MultiPolygon":
                    # Use largest polygon
                    largest = max(poly.geoms, key=lambda g: g.area)
                    surface = [[round(x, 2), round(y, 2)]
                               for x, y in largest.exterior.coords]
                centroid = [round(poly.centroid.x, 2), round(poly.centroid.y, 2)]
            except Exception:
                pass

        # Build s_id (comma-separated load_table_ids)
        elem_assigns = assignments.get(guid, [])
        s_ids = sorted(set(str(ltid) for ltid, _ in elem_assigns))
        s_id = ",".join(s_ids)

        # Build text lines
        text_lines: list[str] = []

        # Line 1: Mark or NO MARK (ID:element_id)
        info = col_info.get(guid) or wall_info.get(guid) or {}
        mark = info.get("mark")
        eid = info.get("element_id")
        if mark:
            text_lines.append(mark)
        elif eid:
            text_lines.append(f"NO MARK (ID:{eid})")
        else:
            text_lines.append(guid[:12])

        # Area lines: one per load assignment
        for ltid, area in elem_assigns:
            lt_name = lt_names.get(ltid, f"LT{ltid}")
            text_lines.append(f"{lt_name} = {area:.2f} m\u00b2")

        # Dimensions line
        if elem_type == "column" and guid in col_info:
            ci = col_info[guid]
            d_val = ci.get("D")
            b_val = ci.get("B")
            if d_val and b_val:
                text_lines.append(f"D = {d_val}x{b_val}")
        elif elem_type == "wall" and guid in wall_info:
            wi = wall_info[guid]
            t_val = wi.get("thickness")
            if t_val:
                text_lines.append(f"W = {t_val}")

        # Beam weight lines — one BM= line per contributing beam
        for bm in bm_detail_per_guid.get(guid, []):
            if bm > 0:
                text_lines.append(f"BM= {bm:.1f} kN")

        result[guid] = {
            "surface": surface,
            "centroid": centroid,
            "s_id": s_id,
            "text": "\n".join(text_lines),
        }

    # Build filename
    proj_num = project.Number or str(project_id)
    level_name = level.Name or str(level_id)
    filename = f"{proj_num}_{level_name}_Tributary_Area.json"

    content = json.dumps(result, indent=2)
    return Response(
        content=content,
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )