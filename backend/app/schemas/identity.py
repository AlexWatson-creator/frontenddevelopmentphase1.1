"""Pydantic v2 schemas for Identity Hub APIs.

Level identity: cross-source level name resolution (Revit, spreadsheet, ETABS).
Element identity: cross-source element resolution (Revit guid, spreadsheet mark, ETABS id).
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class LevelIdentityRead(BaseModel):
    """Read model for a single level_identity row."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_number: str
    canonical_name: str
    sort_order: int
    revit_level_id: Optional[int] = None
    revit_name: Optional[str] = None
    rundown_name: Optional[str] = None
    etabs_name: Optional[str] = None
    revit_elevation_mm: Optional[float] = None
    match_confidence: Decimal
    match_method: str
    created_at: datetime
    updated_at: datetime


class LevelIdentityUpdate(BaseModel):
    """PATCH schema — only user-editable fields, all optional."""
    canonical_name: Optional[str] = Field(None, max_length=100)
    sort_order: Optional[int] = None
    rundown_name: Optional[str] = Field(None, max_length=100)
    etabs_name: Optional[str] = Field(None, max_length=100)


class LevelSyncResult(BaseModel):
    """Response from POST .../levels/sync and auto-sync on GET."""
    synced: bool
    created: int
    updated: int
    stale: int
    stale_names: list[str]
    levels: list[LevelIdentityRead]


# ---------------------------------------------------------------------------
# Element Identity Schemas (Step 3)
# ---------------------------------------------------------------------------

class ElementIdentityRead(BaseModel):
    """Read model for a single element_identity row."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_number: str
    element_type: str
    canonical_mark: str
    level_identity_id: Optional[int] = None
    revit_guid: Optional[str] = None
    rundown_key: Optional[str] = None
    etabs_id: Optional[str] = None
    match_confidence: Decimal
    match_method: str
    last_resolved: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class ElementIdentityUpdate(BaseModel):
    """PATCH schema — only user-editable fields."""
    canonical_mark: Optional[str] = Field(None, max_length=50)
    element_type: Optional[str] = Field(None, max_length=10)
    level_identity_id: Optional[int] = None
    rundown_key: Optional[str] = Field(None, max_length=100)
    etabs_id: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = Field(None, max_length=500)


class ElementSyncResult(BaseModel):
    """Response from POST .../elements/sync and auto-sync on GET."""
    synced: bool
    created: int
    updated: int
    stale: int
    stale_marks: list[str]
    mark_errors: int
    elements: list[ElementIdentityRead]


class ElementStatsResult(BaseModel):
    """Response from GET .../elements/identity/stats."""
    total: int
    columns: int
    walls: int
    by_confidence: dict[str, int]
    stale: int
    mark_errors: int
