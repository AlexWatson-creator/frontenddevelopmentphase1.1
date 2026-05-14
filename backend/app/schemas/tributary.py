"""Pydantic v2 schem0as for Tributary Area computation API.

Compute endpoint accepts two level ids:
  - level_above_id: slab boundary (the floor plate being loaded)
  - level_below_id: columns/walls (supporting elements below the slab)
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class LoadAreaInput(BaseModel):
    """A user-drawn load area for the compute request."""
    polygon_wkt: str = Field(..., description="WKT polygon string (mm coordinates)")
    load_table_id: int


class ComputeRequest(BaseModel):
    """Request body for POST /api/tributary/compute."""
    project_id: int
    level_above_id: int = Field(..., description="Level id for slab boundary (floor plate)")
    level_below_id: int = Field(..., description="Level id for columns/walls (supporting elements)")
    floor_boundary_source: str = Field("slab_db", pattern=r"^(slab_db|json_upload|drawn_areas)$")
    floor_boundary_wkt: Optional[str] = Field(
        None, description="WKT boundary polygon when source=json_upload"
    )
    load_areas: list[LoadAreaInput] = Field(default_factory=list)
    wall_spacing_mm: float = Field(200.0, gt=0)


class TributaryCellResult(BaseModel):
    """One element's tributary area in the compute response."""
    element_guid: str
    element_type: str
    polygon_wkt: str
    area_m2: Decimal
    beam_weights_detail: Optional[str] = None
    # Comma-separated individual beam kN values e.g. "80.5,49.8".
    # None = no concrete beams in this cell.


class LoadAssignmentResult(BaseModel):
    """Load assignment for one element-loadtype combination."""
    element_guid: str
    element_type: str
    load_table_id: int
    tributary_area_m2: Decimal
    dead_load_kn: Decimal
    live_load_kn: Decimal


class ComputeResponse(BaseModel):
    """Response from POST /api/tributary/compute."""
    project_id: int
    level_above_id: int
    level_below_id: int
    boundary_area_m2: Decimal
    column_count: int
    wall_count: int
    cells: list[TributaryCellResult]
    load_assignments: list[LoadAssignmentResult] = Field(default_factory=list)


class StoredTributaryResult(BaseModel):
    """Read model for a stored tributary result row."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    element_guid: str
    element_type: str
    project_id: int
    level_id: int
    load_table_id: int
    tributary_area_m2: Decimal
    polygon_wkt: Optional[str] = None
    computed_at: datetime
