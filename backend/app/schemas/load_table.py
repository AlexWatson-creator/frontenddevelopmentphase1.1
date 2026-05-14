"""Pydantic v2 schemas for Load Table CRUD API.

Load tables define project-level load types (RES, BALC, MEC, ROOF, etc.)
with dead/live kPa values and LLRF type. Each entry is scoped to a single
dbo.Project file (project_id).

Unique constraint: (project_id, name) — one "RES" per file.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class LoadTableEntry(BaseModel):
    """Read model for a single load table row."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_number: str
    project_id: int
    name: str
    description: Optional[str] = None
    dead_load_kpa: Optional[Decimal] = None
    live_load_kpa: Optional[Decimal] = None
    llrf_type: str = "N"
    created_by: str
    created_at: datetime
    updated_at: datetime


class LoadTableCreate(BaseModel):
    """Schema for creating a single load table entry (used in bulk array)."""
    name: str = Field(..., max_length=20)
    description: Optional[str] = Field(None, max_length=100)
    dead_load_kpa: Optional[Decimal] = Field(None, decimal_places=4)
    live_load_kpa: Optional[Decimal] = Field(None, decimal_places=4)
    llrf_type: str = Field("N", max_length=10)


class LoadTableUpdate(BaseModel):
    """Schema for PATCH — all fields optional."""
    name: Optional[str] = Field(None, max_length=20)
    description: Optional[str] = Field(None, max_length=100)
    dead_load_kpa: Optional[Decimal] = Field(None, decimal_places=4)
    live_load_kpa: Optional[Decimal] = Field(None, decimal_places=4)
    llrf_type: Optional[str] = Field(None, max_length=10)