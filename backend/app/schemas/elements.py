"""Schemas for element position data — used by the canvas to render
columns, walls, grids, and slab boundary before Voronoi computation."""
from __future__ import annotations

from pydantic import BaseModel


class ColumnPosition(BaseModel):
    guid: str
    mark: str | None = None
    element_id: int
    level_name: str | None = None
    x: float  # mm
    y: float  # mm
    d: int | None = None       # diameter (circular column), mm
    b: int | None = None       # vertical plan dimension, mm
    h: int | None = None       # horizontal plan dimension, mm
    rotation: int = 0          # degrees


class WallPosition(BaseModel):
    guid: str
    mark: str | None = None
    element_id: int
    level_name: str | None = None
    x1: float  # mm
    y1: float  # mm
    x2: float  # mm
    y2: float  # mm
    thickness: int | None = None  # mm, from WallType


class GridLine(BaseModel):
    name: str
    x1: float  # mm
    y1: float  # mm
    x2: float  # mm
    y2: float  # mm


class LevelElements(BaseModel):
    project_id: int
    level_id: int
    columns: list[ColumnPosition]
    walls: list[WallPosition]
    grids: list[GridLine]
    slab_boundary_wkt: str | None = None
    slab_openings: list[str] = []  # WKT strings for opening polygons
