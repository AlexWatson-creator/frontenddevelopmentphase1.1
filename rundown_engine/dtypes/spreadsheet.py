"""Spreadsheet parser types for the rundown engine.

Used by parsers/spreadsheet.py for dual-mode import:
  1. Import computed values AS-IS for immediate use.
  2. Recompute from extracted inputs to verify/compare.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .inputs import ElementInput, LevelPair, LoadTypeDef


@dataclass
class SpreadsheetFloorValues:
    """Raw computed values extracted from a spreadsheet.

    These are the COMPUTED values in the Excel file, NOT inputs.
    Used to compare against engine-recomputed values.
    """

    dl_kn: float                          # col F: cumulative dead load
    ll_kn: float                          # col G: cumulative live load (with LLRF)
    pw_kn: float                          # col H: service load
    pf_kn: float                          # col I: factored load
    f_over_a_mpa: float | None            # col J: axial stress
    alpha: float | None                   # col K: concrete alpha factor
    pct_steel: float | None               # col L: reinforcement ratio
    as_mm2: float | None                  # col M: area of steel
    area_m2: float                        # col S: this-floor area
    xfer_area_m2: float                   # col T: transfer area
    cum_area_m2: float                    # col U: cumulative area
    cross_section_m2: float | None        # col Z: element cross-section


@dataclass
class DiscrepancyRow:
    """One discrepancy between engine-computed and spreadsheet-imported values."""

    element_mark: str
    floor_index: int
    top_level: str
    field_name: str                       # e.g., "dl_kn", "ll_kn", "pf_kn"
    computed_value: float
    imported_value: float
    difference: float


@dataclass
class SpreadsheetParseResult:
    """Result of parsing a completed rundown .xlsm file."""

    project_number: str
    job_name: str
    designer: str
    load_types: list[LoadTypeDef]
    levels: list[LevelPair]
    elements: list[ElementInput]          # INPUT data → feed to compute_rundown()
    imported_values: dict[str, list[SpreadsheetFloorValues]]
    # COMPUTED values from Excel, keyed by element mark
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    discrepancies: list[DiscrepancyRow] = field(default_factory=list)
