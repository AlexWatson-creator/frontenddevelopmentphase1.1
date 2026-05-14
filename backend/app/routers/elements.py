"""Element positions API router.

GET /api/projects/files/{file_id}/levels/{level_id}/elements
  Returns column, wall, grid positions and slab boundary WKT
  for rendering on the SVG canvas before Voronoi computation.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import ColumnType, DboColumn, Grid, Level, Project, Wall, WallType
from app.schemas.elements import (
    ColumnPosition,
    GridLine,
    LevelElements,
    WallPosition,
)
from app.services.coordinate_parser import (
    parse_column_location,
    parse_point,
    parse_wall_locations,
)
from app.services.slab_boundary import get_slab_and_openings, get_slab_boundary

router = APIRouter(tags=["elements"])


@router.get(
    "/projects/files/{file_id}/levels/{level_id}/elements",
    response_model=LevelElements,
)
def get_level_elements(
    file_id: int,
    level_id: int,
    db: Session = Depends(get_db),
) -> LevelElements:
    """Return all renderable elements for a file + level pair."""
    # Verify file exists
    project = db.query(Project).filter(Project.Id == file_id).first()
    if project is None:
        raise HTTPException(404, f"File (project) {file_id} not found")

    # Verify level belongs to this file
    level = db.query(Level).filter(
        Level.id == level_id,
        Level.Project_id == file_id,
    ).first()
    if level is None:
        raise HTTPException(
            404, f"Level {level_id} not found for file {file_id}",
        )

    # Build level name lookup for this project
    level_rows = db.query(Level.id, Level.Name).filter(
        Level.Project_id == file_id,
    ).all()
    level_names: dict[int, str | None] = {lid: name for lid, name in level_rows}

    # --- Columns (BaseConstraint_id = level_id) ---
    col_rows = (
        db.query(DboColumn, ColumnType.D, ColumnType.B, ColumnType.H)
        .outerjoin(ColumnType, DboColumn.Section_id == ColumnType.id)
        .filter(
            DboColumn.Project_id == file_id,
            DboColumn.BaseConstraint_id == level_id,
        ).all()
    )

    columns: list[ColumnPosition] = []
    for col, ct_d, ct_b, ct_h in col_rows:
        loc = parse_column_location(col.BaseLocation)
        if loc is None:
            continue
        columns.append(ColumnPosition(
            guid=col.guid,
            mark=col.Mark,
            element_id=col.id,
            level_name=level_names.get(col.BaseConstraint_id),
            x=loc[0],
            y=loc[1],
            d=ct_d,
            b=ct_b,
            h=ct_h,
            rotation=col.Rotation or 0,
        ))

    # --- Walls (BaseConstraint_id = level_id) ---
    wall_rows = (
        db.query(Wall, WallType.Thickness)
        .outerjoin(WallType, Wall.Section_id == WallType.id)
        .filter(
            Wall.Project_id == file_id,
            Wall.BaseConstraint_id == level_id,
        )
        .all()
    )

    walls: list[WallPosition] = []
    for wall, thickness in wall_rows:
        locs = parse_wall_locations(wall.StartLocation, wall.Endlocation)
        if locs is None:
            continue
        (x1, y1), (x2, y2) = locs
        walls.append(WallPosition(
            guid=wall.guid,
            mark=wall.Mark,
            element_id=wall.id,
            level_name=level_names.get(wall.BaseConstraint_id),
            x1=x1, y1=y1,
            x2=x2, y2=y2,
            thickness=thickness,
        ))

    # --- Grids (project-wide, not level-specific) ---
    grid_rows = db.query(Grid).filter(Grid.Project_id == file_id).all()

    grids: list[GridLine] = []
    for grid in grid_rows:
        start = parse_point(grid.StartLocation)
        end = parse_point(grid.EndLocation)
        if start is None or end is None:
            continue
        grids.append(GridLine(
            name=grid.Name or "",
            x1=start[0], y1=start[1],
            x2=end[0], y2=end[1],
        ))

    # --- Slab boundary + openings ---
    slab_boundary_wkt: str | None = None
    slab_openings: list[str] = []
    boundary, opening_polys = get_slab_and_openings(db, file_id, level_id)
    if boundary is not None:
        slab_boundary_wkt = boundary.wkt
    slab_openings = [p.wkt for p in opening_polys]

    return LevelElements(
        project_id=file_id,
        level_id=level_id,
        columns=columns,
        walls=walls,
        grids=grids,
        slab_boundary_wkt=slab_boundary_wkt,
        slab_openings=slab_openings,
    )
