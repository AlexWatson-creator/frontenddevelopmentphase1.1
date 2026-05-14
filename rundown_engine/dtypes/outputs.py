"""Output dataclasses for the rundown computation engine.

FULLY TRANSPARENT — every intermediate value exposed with Excel column refs.
"""

from __future__ import annotations

from dataclasses import dataclass

from .inputs import TransferDef
from .validation import ValidationResult


@dataclass
class FloorResult:
    """Complete output for one floor of one element.

    Every intermediate value is exposed — no black boxes.
    Excel column references in comments.
    """

    # Identity
    bot_level: str                        # col A: BOT LEVEL
    top_level: str                        # col C: TOP LEVEL

    # Geometry at this floor
    story_height_m: float                 # col D: HT above (m)
    concrete_mpa: float                   # col E: Conc. Str. (MPa)
    dim_x_mm: float | None               # col X: Col/Wall dimension 1 (mm)
    dim_y: str | float | None            # col Y: dimension 2 (mm, "D", "S", "W")
    cross_section_m2: float | None        # col Z: element cross-section area (m²)

    # --- Areas (cols S, T, U, AA:AY, BA:BY) ---
    area_by_type: dict[str, float]        # cols AA:AY — per-type area this floor (m²)
    cum_area_by_type: dict[str, float]    # cols BA:BY — per-type cumulative area (m²)
    area_this_floor_m2: float             # col S = SUM(AA:AY)
    transfer_area_m2: float               # col T = SUMIF(xfer LVL, TOP LVL, xfer CUM AREA)
    cum_area_m2: float                    # col U = IF(Z=0, 0, S + T + U[N-1])

    # --- Dead Load breakdown — 6 terms → col F ---
    dl_from_above_kn: float               # F[N-1]: cumulative DL from floor above
    dl_floor_load_kn: float               # SUMPRODUCT($AA$4:$AY$4, AA[N]:AY[N])
    dl_transfer_kn: float                 # SUMIF(TransfersReceivedRange, C[N], DL_col)
    dl_self_weight_kn: float              # Z[N] × D[N] × 24
    dl_cladding_kn: float                 # cladding_kPa × W[N] × D[N-1]
    dl_beam_weight_kn: float              # V[N]: beam weight (kN)
    dl_cumulative_kn: float               # col F: sum of all 6 terms

    # --- Live Load breakdown — cols G, CA:CY, CZ:DX, DY ---
    llrf_by_type: dict[str, float]        # cols CA:CY — per-type LLRF factor
    ll_reducible_kn: float                # SUMPRODUCT(BA:BY × $BA$4:$BY$4 × CA:CY)
    ll_non_reducible_by_type: dict[str, float]   # cols CZ:DX per type
    ll_non_reducible_this_floor_kn: float        # SUM(CZ[N]:DX[N])
    ll_transfer_kn: float                 # SUMIF(TransfersReceivedRange, C[N], LL_col)
    dy_cumulative_kn: float               # col DY: non-reducible LL accumulator
    ll_cumulative_kn: float               # col G = ll_reducible + DY

    # --- Derived loads ---
    pw_kn: float                          # col H = DL + LL
    pf_kn: float                          # col I = MAX(1.25×DL + 1.5×LL, 1.4×DL)

    # --- Design outputs — cols J, K, L ---
    f_over_a_mpa: float | None            # col J = IFERROR(PF/1000/Z, "")
    alpha: float | None                   # col K = MAX(0.85 - 0.0015×f'c, 0.67)
    phi: float | None                     # capacity reduction factor (shape-dependent)
    pct_steel: float | None               # col L = reinforcement ratio

    # --- Rebar design — cols M, N, O, P, Q, R (USER-EDITABLE) ---
    as_mm2: float | None                  # col M: area of steel (mm²)
    bar_size: str | None                  # col N: rebar designation (e.g., "20M")
    qty: int | None                       # col O: quantity
    n_bars: int | None                    # col P: Nbars — normal lap bars
    c_bars: int | None                    # col Q: Cbars — coupler bars
    rebar_design: str | None              # col R: rebar string (e.g., "8-20")

    # --- Input data carried through ---
    beam_weight_kn: float                 # col V: B-WT (kN)
    cladding_perimeter_m: float           # col W: C-WALL (m)


@dataclass
class ElementResult:
    """Complete output for one vertical element (all floors)."""

    mark: str
    element_type: str
    floors: list[FloorResult]             # top-to-bottom (roof = index 0)
    cladding_kpa: float
    transfers_received: list[TransferDef]


@dataclass
class RundownResult:
    """Complete output for the entire rundown computation."""

    project_number: str
    elements: list[ElementResult]
    validation: ValidationResult