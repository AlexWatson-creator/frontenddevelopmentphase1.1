"""Rundown engine types — re-exports for convenient access.

Package named 'dtypes' (not 'types') to avoid conflict with Python stdlib types module.

Usage:
    from rundown_engine.dtypes import RundownInput, RundownResult, FloorResult
"""

from .cad import CadTextBlock
from .constants import BAR_SIZES, SYSTEM_SHEETS
from .inputs import (
    ElementDimensions,
    ElementInput,
    FloorInput,
    LevelPair,
    LoadTypeDef,
    RundownInput,
    TransferDef,
)
from .outputs import ElementResult, FloorResult, RundownResult
from .spreadsheet import (
    DiscrepancyRow,
    SpreadsheetFloorValues,
    SpreadsheetParseResult,
)
from .validation import (
    AreaCheckRow,
    DataGapWarning,
    TransferCheckRow,
    ValidationResult,
)

__all__ = [
    # Constants
    "BAR_SIZES",
    "SYSTEM_SHEETS",
    # Inputs
    "LoadTypeDef",
    "LevelPair",
    "ElementDimensions",
    "FloorInput",
    "TransferDef",
    "ElementInput",
    "RundownInput",
    # Outputs
    "FloorResult",
    "ElementResult",
    "RundownResult",
    # Validation
    "AreaCheckRow",
    "TransferCheckRow",
    "DataGapWarning",
    "ValidationResult",
    # Spreadsheet
    "SpreadsheetFloorValues",
    "DiscrepancyRow",
    "SpreadsheetParseResult",
    # CAD
    "CadTextBlock",
]