"""Slab boundary construction from dbo.Floors.

Queries floors for a given level, unions all slab polygons,
and subtracts OPENING-type floors to produce the net boundary.
All coordinates in mm.
"""
from __future__ import annotations

from shapely.geometry import Polygon
from shapely.ops import unary_union
from sqlalchemy.orm import Session

from app.models import Floor, FloorType
from app.services.coordinate_parser import parse_slab_polygon


def get_slab_boundary(
    db: Session,
    project_id: int,
    level_id: int,
) -> Polygon | None:
    """Build net slab boundary polygon for a level.

    1. Query all floors at the given level
    2. Parse LocationPoints into polygon loops
    3. Union all slab polygons (non-OPENING types)
    4. Subtract all OPENING polygons

    Returns None if no valid slab geometry is found.
    """
    floors_with_type = (
        db.query(Floor, FloorType.TypeName)
        .join(FloorType, Floor.Section_id == FloorType.id)
        .filter(Floor.Project_id == project_id, Floor.Level_id == level_id)
        .all()
    )

    slab_polys: list[Polygon] = []
    opening_polys: list[Polygon] = []

    for floor, type_name in floors_with_type:
        is_opening = type_name and "OPENING" in type_name.upper()
        loops = parse_slab_polygon(floor.LocationPoints)
        if not loops:
            continue

        for loop in loops:
            poly = Polygon(loop)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if poly.is_empty or poly.area <= 0:
                continue
            if is_opening:
                opening_polys.append(poly)
            else:
                slab_polys.append(poly)

    if not slab_polys:
        return None

    boundary = unary_union(slab_polys)

    if opening_polys:
        boundary = boundary.difference(unary_union(opening_polys))

    if boundary.is_empty:
        return None

    if not boundary.is_valid:
        boundary = boundary.buffer(0)

    return boundary


def get_slab_and_openings(
    db: Session,
    project_id: int,
    level_id: int,
) -> tuple[Polygon | None, list[Polygon]]:
    """Return full slab boundary (without subtracting openings) and opening polygons separately.

    Used by the elements endpoint so the canvas can render the full slab
    and show openings as rectangular indicators.
    """
    floors_with_type = (
        db.query(Floor, FloorType.TypeName)
        .join(FloorType, Floor.Section_id == FloorType.id)
        .filter(Floor.Project_id == project_id, Floor.Level_id == level_id)
        .all()
    )

    slab_polys: list[Polygon] = []
    opening_polys: list[Polygon] = []

    for floor, type_name in floors_with_type:
        is_opening = type_name and "OPENING" in type_name.upper()
        loops = parse_slab_polygon(floor.LocationPoints)
        if not loops:
            continue

        for loop in loops:
            poly = Polygon(loop)
            if not poly.is_valid:
                poly = poly.buffer(0)
            if poly.is_empty or poly.area <= 0:
                continue
            if is_opening:
                opening_polys.append(poly)
            else:
                slab_polys.append(poly)

    if not slab_polys:
        return None, opening_polys

    boundary = unary_union(slab_polys)
    if boundary.is_empty:
        return None, opening_polys
    if not boundary.is_valid:
        boundary = boundary.buffer(0)

    return boundary, opening_polys