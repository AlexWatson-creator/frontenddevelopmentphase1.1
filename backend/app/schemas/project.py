"""Pydantic v2 schemas for Project Management API.

Domain model: each dbo.Project row = a Revit model file.
Project.Number is the real project identifier.
Metadata (address) lives in management.project_meta.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Element counts — reusable
# ---------------------------------------------------------------------------

class ElementCounts(BaseModel):
    """Aggregate element counts."""
    columns: int = 0
    walls: int = 0
    beams: int = 0
    floors: int = 0
    foundations: int = 0

    @property
    def total(self) -> int:
        return self.columns + self.walls + self.beams + self.floors + self.foundations


# ---------------------------------------------------------------------------
# Level with per-level counts
# ---------------------------------------------------------------------------

class LevelWithCounts(BaseModel):
    """A single level with element counts at that level."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    elevation: float
    story_height: Optional[int] = None
    counts: ElementCounts = Field(default_factory=ElementCounts)


# ---------------------------------------------------------------------------
# ProjectFile — a single dbo.Project row (Revit model file)
# ---------------------------------------------------------------------------

class ProjectFile(BaseModel):
    """Single dbo.Project row = one Revit model file."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_name: Optional[str] = None
    file_location: Optional[str] = None
    software: Optional[str] = None
    last_run_time: Optional[datetime] = None
    counts: ElementCounts = Field(default_factory=ElementCounts)


class ProjectFileDetail(ProjectFile):
    """ProjectFile with levels and per-level element counts."""
    levels: list[LevelWithCounts] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# ProjectGroup — grouped by Number (list endpoint)
# ---------------------------------------------------------------------------

class ProjectGroup(BaseModel):
    """Projects grouped by Number — used in the list endpoint."""
    number: str
    address: Optional[str] = None
    job_name: Optional[str] = None
    designer: Optional[str] = None
    file_count: int = 0
    last_run_time: Optional[datetime] = None
    counts: ElementCounts = Field(default_factory=ElementCounts)
    files: list[ProjectFile] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# ProjectDetail — full detail for a single project number
# ---------------------------------------------------------------------------

class ProjectDetail(BaseModel):
    """Full detail for a project number, including levels per file."""
    number: str
    address: Optional[str] = None
    job_name: Optional[str] = None
    designer: Optional[str] = None
    files: list[ProjectFileDetail] = Field(default_factory=list)
    counts: ElementCounts = Field(default_factory=ElementCounts)


# ---------------------------------------------------------------------------
# ProjectUpdate — writable fields (writes to management.project_meta)
# ---------------------------------------------------------------------------

class ProjectUpdate(BaseModel):
    """Fields that can be updated via PATCH /api/projects/{number}."""
    address: Optional[str] = Field(None, max_length=255)
    job_name: Optional[str] = Field(None, max_length=255)
    designer: Optional[str] = Field(None, max_length=100)


# ---------------------------------------------------------------------------
# Merge request
# ---------------------------------------------------------------------------

class MergeRequest(BaseModel):
    """Request body for POST /api/projects/{number}/merge."""
    source_number: str = Field(..., description="Project number to merge FROM (will be deleted)")