"""Constants for the rundown computation engine.

Source: DATA sheet in rundown spreadsheet template.
"""

# Canadian standard rebar — bar designation → cross-sectional area (mm²)
# Source: DATA sheet K4:L11
BAR_SIZES: dict[str, int] = {
    "10M": 100,
    "15M": 200,
    "20M": 300,
    "25M": 500,
    "30M": 700,
    "35M": 1000,
    "45M": 1500,
    "55M": 2500,
}

# 8 system sheets excluded from element iteration
# Source: DATA.rngWSExclude (H3:H11)
SYSTEM_SHEETS: frozenset[str] = frozenset({
    "TEMPLATE", "IMPORT", "LOAD FILE", "SUMMARY",
    "TRANSFERS", "DATA", "CW SCHEDULE", "Sheet1",
})