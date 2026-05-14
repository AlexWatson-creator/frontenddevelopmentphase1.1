"""Pydantic v2 schemas for Vertical Chain APIs.

A vertical chain = all instances of the same canonical_mark stacked across
building levels.  Computed on-the-fly from element_identity + level_identity.
Manual overrides always take priority.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class ChainFloor(BaseModel):
    """One floor in a vertical chain."""

    element_identity_id: int
    level_identity_id: int
    level_name: str
    sort_order: int
    revit_guid: Optional[str] = None
    match_confidence: Decimal
    has_rundown: bool


class ChainSummary(BaseModel):
    """Summary of one vertical chain (one canonical_mark)."""

    canonical_mark: str
    element_type: str
    floor_count: int
    min_level: str
    max_level: str
    has_gaps: bool
    gap_count: int


class ChainDetail(ChainSummary):
    """Full detail for one chain — floors + gap names."""

    floors: list[ChainFloor]
    gaps: list[str]


class BuildChainsResult(BaseModel):
    """Response from POST .../chains/build."""

    total_chains: int
    total_elements: int
    chains_with_gaps: int
    single_floor_elements: int
    chains: list[ChainSummary]
