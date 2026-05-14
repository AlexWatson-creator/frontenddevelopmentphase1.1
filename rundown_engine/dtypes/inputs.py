"""Input dataclasses for the rundown computation engine.

Source-agnostic: same structure regardless of CAD, Revit, or spreadsheet origin.
Every field includes its Excel column/range reference for traceability.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LoadTypeDef:
    """One of up to 25 load types.

    Source: IMPORT sheet B3:F27 (exactly 25 rows, never add/delete).
    """

    code: str
    # IMPORT col C (row 3:27) — e.g., "RES", "BAL", "PAR", "MEC", "STA"
    # Must match element sheet AA$3:AY$3 codes exactly

    description: str
    # IMPORT col B — "RESIDENTIAL", "BALCONY", "PARKING", etc.

    dead_kpa: float
    # IMPORT col D — dead load intensity (kPa)
    # Propagated to element sheet $AA$4:$AY$4

    live_kpa: float
    # IMPORT col E — live load intensity (kPa)
    # Propagated to element sheet $BA$4:$BY$4

    llrf_type: str
    # IMPORT col F — "N", "R0.3", or "R0.5"
    # Propagated to element sheet $CA$4:$CY$4


@dataclass(frozen=True)
class LevelPair:
    """One floor span (bot-to-top).

    Source: IMPORT sheet H3:J{last} for level names,
            element sheet cols D, E for per-floor values.
    """

    bot_level: str
    # IMPORT col H / element col A: BOT LEVEL name

    top_level: str
    # IMPORT col J / element col C: TOP LEVEL name

    story_height_m: float
    # Element col D: HT above (m) — story height for this span

    concrete_mpa: float
    # Element col E: Conc. Str. (MPa) — concrete strength at this level


@dataclass(frozen=True)
class ElementDimensions:
    """Element cross-section at a floor.

    Source: element sheet cols X, Y.
    """

    dim_x_mm: float
    # Col X: width (mm) for rectangular, diameter (mm) for circular,
    #         or steel area (m²) for steel sections

    dim_y: str | float
    # Col Y: depth/length (mm) for rectangular,
    #         "D" = circular column, "S" = steel section, "W" = special case


@dataclass(frozen=True)
class FloorInput:
    """Input data for one floor of one element.

    One row in the element sheet (rows 7+), ordered top-to-bottom
    (roof = index 0, footings = last).
    """

    level: LevelPair

    dimensions: ElementDimensions | None
    # None = element absent at this floor (no cross-section → Z=0)

    area_by_type: dict[str, float]
    # Cols AA:AY — {code: area_m2}, up to 25 load types
    # From CAD text "A{code}= {value} m2" or Voronoi tributary

    beam_weight_kn: float
    # Col V: B-WT (kN), from CAD "BM= xx kN"

    cladding_perimeter_m: float
    # Col W: C-WALL (m), from CAD "P= xx m"

    # Rebar inputs (user-editable, may be None on initial computation)
    bar_size: str | None = None
    # Col N: rebar designation (e.g., "20M")

    qty: int | None = None
    # Col O: quantity

    n_bars: int | None = None
    # Col P: Nbars — normal lap bars

    c_bars: int | None = None
    # Col Q: Cbars — coupler bars


@dataclass(frozen=True)
class TransferDef:
    """One transfer relationship.

    Source: TRANSFERS RECEIVED section below level data in element sheet.
    Cols A-C always present. Cols D-F optional:
      - Provided when importing from spreadsheet (already computed).
      - None when computing from Revit/CAD (engine resolves from source
        element's results during topological-order computation).
    """

    source_element: str
    # Col A of transfer row: source element mark (e.g., "C1A", "W1")

    target_level: str
    # Col B of transfer row: TOP LEVEL where transfer occurs
    # Must match element sheet col C (TOP LEVEL) for lookup

    percent: float
    # Col C of transfer row: 1.0 = 100%, 0.5 = 50%

    # Resolved values — optional (engine computes if None)
    dl_kn: float | None = None
    # Col D: source DL at this level × percent (kN)

    ll_kn: float | None = None
    # Col E: source LL at this level × percent (kN)

    cum_area_m2: float | None = None
    # Col F: source CUM AREA at this level × percent (m²)


@dataclass(frozen=True)
class ElementInput:
    """Complete input for one vertical element (one sheet in Excel).

    Sheet name examples: "C1", "W12-W13-W14", "PC104", "!FDNW1"
    """

    mark: str
    # Sheet name — the element's mark identifier

    element_type: str
    # "Column" or "Wall" (derived from mark parser)

    floors: list[FloorInput]
    # Top-to-bottom (roof = index 0, footings = last)

    transfers_received: list[TransferDef]
    # From TRANSFERS RECEIVED section below level data

    cladding_kpa: float
    # From "Cladding Wall:" row in TRANSFERS RECEIVED section
    # Position varies: $F$28 (19-level) / $F$59 (50-level)
    # Typically 1.5 kPa (glass) to 2.0–3.0 kPa (brick/precast)


@dataclass(frozen=True)
class RundownInput:
    """Complete input for the entire rundown computation (all elements, all floors)."""

    project_number: str

    load_types: list[LoadTypeDef]
    # Up to 25. Source: IMPORT B3:F27

    elements: list[ElementInput]
