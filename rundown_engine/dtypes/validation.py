"""Validation output types for the rundown computation engine.

Source: TRANSFERS sheet in rundown spreadsheet — Area Checks, Transfer Checks,
Worksheet Checks.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AreaCheckRow:
    """Per-level area balance check.

    Source: TRANSFERS sheet → Area Checks (cols K-P).
    Formula: Cum.Area[top floor] - Tot.Area = diff
             Cum.Area[other] - Tot.Area - Cum.Area[above] = diff
    Area Difference must be 0 when transfers are correct.
    """

    bot_level: str
    top_level: str
    total_area_m2: float          # SUM all elements' S this floor
    cum_area_m2: float            # SUM all elements' U this floor
    area_difference_m2: float     # Must be 0 when transfers correct
    is_balanced: bool             # |diff| <= 1.0


@dataclass
class TransferCheckRow:
    """Per-element transfer audit.

    Source: TRANSFERS sheet → Transfer Checks (cols G-J).
    Color coding: Yellow=0%, Blue=>110%, Red=<100%.
    """

    element_mark: str
    pct_transferred: float        # outgoing %
    to_elements: list[str]
    all_within_range: bool
    status: str                   # "ok" / "under" / "over" / "none"


@dataclass
class DataGapWarning:
    """Missing or inconsistent data for an element."""

    element_mark: str
    message: str                  # e.g., "missing dimensions at Level 5"


@dataclass
class ValidationResult:
    """Complete validation output for a rundown computation."""

    area_checks: list[AreaCheckRow] = field(default_factory=list)
    transfer_checks: list[TransferCheckRow] = field(default_factory=list)
    data_gaps: list[DataGapWarning] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    is_valid: bool = True