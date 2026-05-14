"""Standalone rundown computation engine — zero backend imports, reusable."""

from .compute import compute_rundown
from .dtypes import (
    AreaCheckRow,
    BAR_SIZES,
    CadTextBlock,
    DataGapWarning,
    DiscrepancyRow,
    ElementDimensions,
    ElementInput,
    ElementResult,
    FloorInput,
    FloorResult,
    LevelPair,
    LoadTypeDef,
    RundownInput,
    RundownResult,
    SYSTEM_SHEETS,
    SpreadsheetFloorValues,
    SpreadsheetParseResult,
    TransferCheckRow,
    TransferDef,
    ValidationResult,
)
from .validate import validate_rundown

__all__ = [
    # Main entry points
    "compute_rundown",
    "validate_rundown",
    # Inputs
    "RundownInput",
    "ElementInput",
    "FloorInput",
    "LoadTypeDef",
    "LevelPair",
    "ElementDimensions",
    "TransferDef",
    # Outputs
    "RundownResult",
    "ElementResult",
    "FloorResult",
    # Validation types
    "ValidationResult",
    "AreaCheckRow",
    "TransferCheckRow",
    "DataGapWarning",
    # Spreadsheet types
    "SpreadsheetParseResult",
    "SpreadsheetFloorValues",
    "DiscrepancyRow",
    # CAD types
    "CadTextBlock",
    # Constants
    "BAR_SIZES",
    "SYSTEM_SHEETS",
]