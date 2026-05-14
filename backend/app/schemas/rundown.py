"""Pydantic v2 schemas for the Rundown API.

All response models mirror the rundown engine output types (FloorResult,
ElementResult, RundownResult) to maintain 1:1 traceability with the engine.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------------------------
# Per-floor result (mirrors rundown_engine.dtypes.outputs.FloorResult)
# ---------------------------------------------------------------------------

class FloorResultRead(BaseModel):
    """Complete output for one floor — every intermediate value exposed."""
    model_config = ConfigDict(from_attributes=True)

    # Row ID (for PATCH targeting)
    id: Optional[int] = None

    # Identity
    bot_level: str
    top_level: str

    # Geometry (cols D, E, X, Y, Z)
    story_height_m:   Optional[float] = None
    concrete_mpa:     Optional[float] = None
    dim_x_mm:         Optional[float] = None
    dim_y:            Optional[str]   = None   # numeric or "D"/"S"/"W"
    cross_section_m2: Optional[float] = None

    # DL breakdown — 6 terms + cumulative (col F)
    dl_from_above_kn:   Optional[float] = None
    dl_floor_load_kn:   Optional[float] = None
    dl_transfer_kn:     Optional[float] = None
    dl_self_weight_kn:  Optional[float] = None
    dl_cladding_kn:     Optional[float] = None
    dl_beam_weight_kn:  Optional[float] = None
    dl_cumulative_kn:   Optional[float] = None

    # LL breakdown — 2-path + cumulative (col G)
    ll_reducible_kn:                Optional[float] = None
    ll_non_reducible_this_floor_kn: Optional[float] = None
    ll_transfer_kn:                 Optional[float] = None
    dy_cumulative_kn:               Optional[float] = None
    ll_cumulative_kn:               Optional[float] = None

    # Areas (cols S, T, U)
    area_this_floor_m2: Optional[float] = None
    transfer_area_m2:   Optional[float] = None
    cum_area_m2:        Optional[float] = None

    # Derived + capacity (cols H, I, J, K, L)
    pw_kn:        Optional[float] = None
    pf_kn:        Optional[float] = None
    f_over_a_mpa: Optional[float] = None
    alpha_factor: Optional[float] = None
    phi:          Optional[float] = None
    pct_steel:    Optional[float] = None

    # Input carry-through (cols V, W)
    beam_weight_kn:     Optional[float] = None
    cladding_perimeter_m: Optional[float] = None

    # Rebar design (cols M-R)
    as_mm2:       Optional[float] = None
    bar_size:     Optional[str]   = None
    qty:          Optional[int]   = None
    n_bars:       Optional[int]   = None
    c_bars:       Optional[int]   = None
    rebar_design: Optional[str]   = None

    # Override tracking
    qty_override:     bool = False
    n_bars_override:  bool = False
    c_bars_override:  bool = False

    # Per-type JSON breakdowns (parsed from stored JSON strings)
    area_by_type:             Optional[dict[str, float]] = None  # {code: m2}
    cum_area_by_type:         Optional[dict[str, float]] = None
    llrf_by_type:             Optional[dict[str, float]] = None
    ll_non_reducible_by_type: Optional[dict[str, float]] = None

    # Source
    data_source: Optional[str] = None
    floor_order: Optional[int] = None


# ---------------------------------------------------------------------------
# Element summary (for list endpoint)
# ---------------------------------------------------------------------------

class ElementSummary(BaseModel):
    """Lightweight summary for the element list endpoint."""
    mark: str
    element_type: str
    floor_count: int
    # Values at the lowest computed floor (footing level)
    dl_cumulative_kn:  Optional[float] = None
    ll_cumulative_kn:  Optional[float] = None
    pf_kn:             Optional[float] = None
    cross_section_m2:  Optional[float] = None
    data_source:       Optional[str]   = None


# ---------------------------------------------------------------------------
# Element detail (for single-element endpoint)
# ---------------------------------------------------------------------------

class ElementDetailRead(BaseModel):
    """Full floor-by-floor detail for one vertical element."""
    mark: str
    element_type: str
    floor_count: int
    floors: list[FloorResultRead]  # top-to-bottom (index 0 = roof)


# ---------------------------------------------------------------------------
# Rundown list (all elements for a project)
# ---------------------------------------------------------------------------

class RundownListRead(BaseModel):
    """Summary of all elements for a project."""
    project_number: str
    element_count: int
    load_type_count: int = 0
    data_source: Optional[str] = None
    computed_at: Optional[datetime] = None
    job_name: Optional[str] = None
    designer: Optional[str] = None
    elements: list[ElementSummary]


class RecentRundownItem(BaseModel):
    """One project in the recent rundowns list."""
    project_number: str
    element_count: int
    data_source: Optional[str] = None
    computed_at: Optional[datetime] = None


class RecentRundownList(BaseModel):
    """Response for GET /rundown/recent."""
    items: list[RecentRundownItem]


# ---------------------------------------------------------------------------
# Spreadsheet upload — preview (no DB write)
# ---------------------------------------------------------------------------

class DiscrepancyItem(BaseModel):
    """One discrepancy between engine-computed and Excel-imported values."""
    element_mark: str
    floor_index: int
    top_level: str
    field_name: str
    computed_value: float
    imported_value: float
    difference: float


class SpreadsheetUploadPreview(BaseModel):
    """Returned by POST /rundown/upload — parse only, no DB write."""
    project_number: str
    job_name: str
    designer: str
    element_count: int
    level_count: int
    load_type_count: int
    errors: list[str]
    warnings: list[str]
    discrepancy_count: int
    discrepancies: list[DiscrepancyItem]


# ---------------------------------------------------------------------------
# Compute + store result
# ---------------------------------------------------------------------------

class RundownComputeResult(BaseModel):
    """Returned by POST /rundown/upload/confirm — compute + store."""
    project_number: str
    rows_written: int
    element_count: int
    validation_is_valid: bool
    validation_errors: list[str]
    validation_warnings: list[str]


# ---------------------------------------------------------------------------
# Validation summary
# ---------------------------------------------------------------------------

class AreaCheckRow(BaseModel):
    bot_level: str
    top_level: str
    total_area_m2: float
    cum_area_m2: float
    area_difference_m2: float
    is_balanced: bool


class TransferCheckRow(BaseModel):
    element_mark: str
    pct_transferred: float
    to_elements: list[str]
    all_within_range: bool
    status: str       # "ok" / "under" / "over" / "none"


class DataGapWarning(BaseModel):
    element_mark: str
    message: str


class ValidationRead(BaseModel):
    """Returned by GET /rundown/validation."""
    project_number: str
    is_valid: bool
    area_checks: list[AreaCheckRow]
    transfer_checks: list[TransferCheckRow]
    data_gaps: list[DataGapWarning]
    errors: list[str]
    warnings: list[str]


# ---------------------------------------------------------------------------
# Load type replace (POST /rundown/load-types)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Summary matrix (GET /rundown/summary)
# ---------------------------------------------------------------------------

class SummaryColumn(BaseModel):
    """One element column in the summary matrix."""
    mark: str
    element_type: str


class SummaryLevel(BaseModel):
    """One level row in the summary matrix."""
    bot_level: str
    top_level: str


class SummaryMatrixRead(BaseModel):
    """Cross-element pivot: levels on rows, elements on columns."""
    columns: list[SummaryColumn]
    levels: list[SummaryLevel]
    metric: str
    values: list[list[float | None]]  # values[level_idx][col_idx]


# ---------------------------------------------------------------------------
# Load type replace (POST /rundown/load-types)
# ---------------------------------------------------------------------------

class LoadTypeInput(BaseModel):
    """One load type entry for the replace endpoint."""
    name: str
    description: str = ""
    dead_load_kpa: Optional[float] = None
    live_load_kpa: Optional[float] = None
    llrf_type: str = "N"


class LoadTypeReplaceRequest(BaseModel):
    """Body for POST /rundown/load-types."""
    entries: list[LoadTypeInput]


class LoadTypeReplaceResponse(BaseModel):
    """Response for POST /rundown/load-types."""
    count: int


# ---------------------------------------------------------------------------
# Rebar edit (PATCH /rundown/rows/{row_id})
# ---------------------------------------------------------------------------

class RundownRowPatch(BaseModel):
    """Body for PATCH /rundown/rows/{row_id} — rebar overrides."""
    bar_size: Optional[str] = None
    qty: Optional[int] = None
    n_bars: Optional[int] = None
    c_bars: Optional[int] = None
    qty_override: bool = False
    n_bars_override: bool = False
    c_bars_override: bool = False


class RundownRowUpdated(BaseModel):
    """Response for PATCH /rundown/rows/{row_id}."""
    id: int
    bar_size: Optional[str] = None
    qty: Optional[int] = None
    n_bars: Optional[int] = None
    c_bars: Optional[int] = None
    rebar_design: Optional[str] = None
    as_mm2: Optional[float] = None
    qty_override: bool = False
    n_bars_override: bool = False
    c_bars_override: bool = False


# ---------------------------------------------------------------------------
# Transfer management (CRUD + recompute)
# ---------------------------------------------------------------------------

class TransferDefInput(BaseModel):
    """One transfer definition for the replace endpoint."""
    source_element: str
    target_level: str
    percent: float = Field(gt=0, le=2.0)


class TransferReplaceRequest(BaseModel):
    """Body for PUT /rundown/transfers/{mark}."""
    transfers: list[TransferDefInput]


class TransferReplaceResponse(BaseModel):
    """Response for PUT /rundown/transfers/{mark}."""
    count: int
    target_element: str


class TransferDefRead(BaseModel):
    """One stored transfer definition."""
    id: int
    target_element: str
    source_element: str
    target_level: str
    percent: float
    created_by: str
    # Computed from source element at target_level (filled by router)
    dl_kn: float | None = None
    ll_kn: float | None = None
    cum_area_m2: float | None = None
