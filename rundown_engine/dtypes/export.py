"""Dataclasses for spreadsheet export.

Self-contained input structure — no DB or backend imports.
The backend adapter maps ORM rows to these dataclasses.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExportMetadata:
    """Project-level metadata."""
    project_number: str
    job_name: str = ""
    designer: str = ""


@dataclass(frozen=True)
class ExportLoadType:
    """One load type definition."""
    code: str
    description: str = ""
    dead_kpa: float = 0.0
    live_kpa: float = 0.0
    llrf_type: str = "N"


@dataclass(frozen=True)
class ExportLevelPair:
    """One level span (ordered top-to-bottom)."""
    bot_level: str
    top_level: str
    story_height_m: float = 0.0
    concrete_mpa: float = 30.0


@dataclass(frozen=True)
class ExportTransfer:
    """One transfer received entry."""
    source_element: str
    target_level: str
    percent: float
    dl_kn: float | None = None
    ll_kn: float | None = None
    cum_area_m2: float | None = None


@dataclass(frozen=True)
class ExportFloor:
    """One floor row of one element — maps 1:1 to Excel row 7+."""
    bot_level: str
    top_level: str
    story_height_m: float = 0.0
    concrete_mpa: float = 30.0

    # Geometry
    dim_x_mm: float | None = None
    dim_y: str | float | None = None
    cross_section_m2: float | None = None

    # Computed loads
    dl_cumulative_kn: float = 0.0
    ll_cumulative_kn: float = 0.0
    pw_kn: float = 0.0
    pf_kn: float = 0.0

    # Design
    f_over_a_mpa: float | None = None
    alpha: float | None = None
    pct_steel: float | None = None

    # Rebar
    as_mm2: float | None = None
    bar_size: str | None = None
    qty: int | None = None
    n_bars: int | None = None
    c_bars: int | None = None
    rebar_design: str | None = None

    # Areas
    area_this_floor_m2: float = 0.0
    transfer_area_m2: float = 0.0
    cum_area_m2: float = 0.0

    # Inputs
    beam_weight_kn: float = 0.0
    cladding_perimeter_m: float = 0.0

    # Per-type breakdowns
    area_by_type: dict[str, float] = field(default_factory=dict)
    cum_area_by_type: dict[str, float] = field(default_factory=dict)
    llrf_by_type: dict[str, float] = field(default_factory=dict)
    ll_non_reducible_by_type: dict[str, float] = field(default_factory=dict)
    dy_cumulative_kn: float = 0.0


@dataclass(frozen=True)
class ExportElement:
    """Complete data for one element sheet."""
    mark: str
    element_type: str
    floors: list[ExportFloor]
    transfers_received: list[ExportTransfer] = field(default_factory=list)
    cladding_kpa: float = 0.0


@dataclass(frozen=True)
class ExportInput:
    """Complete input for generating one .xlsm export file."""
    metadata: ExportMetadata
    load_types: list[ExportLoadType]
    levels: list[ExportLevelPair]
    elements: list[ExportElement]
    template_path: str