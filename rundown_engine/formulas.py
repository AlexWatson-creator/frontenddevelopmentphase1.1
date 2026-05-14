"""Individual formula functions for the rundown computation engine.

Pure functions — no side effects, no DB, no I/O.
Each function independently testable with known Excel values.

Formula references point to rundown-spreadsheet-read-me.md Section 5.
"""

from __future__ import annotations

import math

from .dtypes.constants import BAR_SIZES
from .dtypes.inputs import LoadTypeDef


# ---------------------------------------------------------------------------
# Cross-Section Area — Col Z
# ---------------------------------------------------------------------------

def compute_cross_section(dim_x_mm: float, dim_y: str | float) -> float:
    """Compute element cross-section area in m².

    Excel formula (col Z):
        IF(Y="D", 0.25 × PI × (X/1000)²,     ← circular (diameter in mm)
        IF(Y="S", X,                           ← steel section (area directly in m²)
        IF(Y="W", X/24,                        ← special case
        X × Y / 1e6)))                         ← rectangular: width(mm) × depth(mm)

    Args:
        dim_x_mm: Col X value — width/diameter (mm) or steel area (m²).
        dim_y: Col Y value — depth (mm), or "D"/"S"/"W" string.

    Returns:
        Cross-section area in m².
    """
    if isinstance(dim_y, str):
        code = dim_y.upper()
        if code == "D":
            # Circular column: 0.25 × π × (diameter/1000)²
            return 0.25 * math.pi * (dim_x_mm / 1000.0) ** 2
        if code == "S":
            # Steel section: X is already area in m²
            return dim_x_mm
        if code == "W":
            # Special case
            return dim_x_mm / 24.0
    # Rectangular: width(mm) × depth(mm) → m²
    return dim_x_mm * float(dim_y) / 1e6


# ---------------------------------------------------------------------------
# LLRF (Live Load Reduction Factor) — Cols CA:CY
# ---------------------------------------------------------------------------

def compute_llrf(llrf_type: str, cum_area_m2: float) -> float:
    """Compute Live Load Reduction Factor for one load type at one floor.

    Excel formula (CA:CY):
        IF type = "R0.3": IF(cum_area > 20, 0.3 + SQRT(9.8/cum_area), 1.0)
        IF type = "R0.5": IF(cum_area > 80, 0.5 + SQRT(20/cum_area),  1.0)
        IF type = "N":    0   ← non-reducible (handled by DY path instead)

    Args:
        llrf_type: "R0.3", "R0.5", or "N".
        cum_area_m2: Cumulative area for this load type (BA:BY value) in m².

    Returns:
        LLRF factor (0.0 to 1.0).
    """
    if llrf_type == "R0.3":
        if cum_area_m2 > 20.0:
            return 0.3 + math.sqrt(9.8 / cum_area_m2)
        return 1.0
    if llrf_type == "R0.5":
        if cum_area_m2 > 80.0:
            return 0.5 + math.sqrt(20.0 / cum_area_m2)
        return 1.0
    # "N" → non-reducible: LLRF = 0 (LL flows through DY path)
    return 0.0


# ---------------------------------------------------------------------------
# Self-Weight — Z × D × 24
# ---------------------------------------------------------------------------

def compute_self_weight(z_m2: float, height_m: float) -> float:
    """Compute element self-weight for one floor.

    Excel formula: Z[N] × D[N] × 24
    Where Z = cross-section area (m²), D = story height (m), 24 = concrete density (kN/m³).

    Args:
        z_m2: Cross-section area (m²) from compute_cross_section().
        height_m: Story height (m) — col D.

    Returns:
        Self-weight in kN.
    """
    return z_m2 * height_m * 24.0


# ---------------------------------------------------------------------------
# Cladding Load — cladding_kPa × W × D[N-1]
# ---------------------------------------------------------------------------

def compute_cladding(kpa: float, perimeter_m: float, height_above_m: float) -> float:
    """Compute cladding load for one floor.

    Excel formula: $F$28 × W[N] × D[N-1]
    CRITICAL: Uses D[N-1] (height of story ABOVE, not current).
    At the topmost floor (row 7), D[N-1] = 0 → no cladding.

    Args:
        kpa: Cladding intensity (kPa) from TRANSFERS RECEIVED section.
        perimeter_m: Cladding perimeter (m) — col W.
        height_above_m: Story height of the floor ABOVE — D[N-1].

    Returns:
        Cladding load in kN.
    """
    return kpa * perimeter_m * height_above_m


# ---------------------------------------------------------------------------
# Dead Load — Floor Load Component — SUMPRODUCT($AA$4:$AY$4, AA[N]:AY[N])
# ---------------------------------------------------------------------------

def compute_dl_floor_load(
    area_by_type: dict[str, float],
    load_type_lookup: dict[str, LoadTypeDef],
) -> float:
    """Compute dead load from tributary areas for one floor.

    Excel formula: SUMPRODUCT($AA$4:$AY$4, AA[N]:AY[N])
    Where $AA$4:$AY$4 = DL kPa per type, AA[N]:AY[N] = area per type this floor.

    Args:
        area_by_type: {code: area_m2} from FloorInput.area_by_type.
        load_type_lookup: {code: LoadTypeDef} for DL kPa lookup.

    Returns:
        Floor dead load contribution in kN.
    """
    total = 0.0
    for code, area_m2 in area_by_type.items():
        lt = load_type_lookup.get(code)
        if lt is not None:
            total += lt.dead_kpa * area_m2
    return total


# ---------------------------------------------------------------------------
# Live Load — Reducible Component — SUMPRODUCT(BA:BY × $BA$4:$BY$4 × CA:CY)
# ---------------------------------------------------------------------------

def compute_ll_reducible(
    cum_area_by_type: dict[str, float],
    load_type_lookup: dict[str, LoadTypeDef],
    llrf_by_type: dict[str, float],
) -> float:
    """Compute reducible live load for one floor.

    Excel formula: SUMPRODUCT(BA[N]:BY[N], $BA$4:$BY$4, CA[N]:CY[N])
    Where BA:BY = cumulative area per type, $BA$4:$BY$4 = LIVE kPa, CA:CY = LLRF.

    NOTE: $BA$4:$BY$4 are LIVE load kPa (from IMPORT col E),
          NOT the same as $AA$4:$AY$4 which are DEAD load kPa.

    Args:
        cum_area_by_type: {code: cum_area_m2} — cumulative area per type (BA:BY).
        load_type_lookup: {code: LoadTypeDef} for LL kPa lookup.
        llrf_by_type: {code: llrf_factor} from compute_llrf().

    Returns:
        Reducible live load in kN.
    """
    total = 0.0
    for code, cum_area in cum_area_by_type.items():
        lt = load_type_lookup.get(code)
        llrf = llrf_by_type.get(code, 0.0)
        if lt is not None:
            total += cum_area * lt.live_kpa * llrf
    return total


# ---------------------------------------------------------------------------
# Live Load — Non-Reducible per Type — Cols CZ:DX
# ---------------------------------------------------------------------------

def compute_ll_non_reducible_by_type(
    area_by_type: dict[str, float],
    load_type_lookup: dict[str, LoadTypeDef],
) -> dict[str, float]:
    """Compute non-reducible live load per type for one floor.

    Excel formula (CZ:DX):
        IF(OR(type="R0.3", type="R0.5"), 0, AA[N] × LL_kPa)
    Only type "N" contributes.

    Args:
        area_by_type: {code: area_m2} — this floor area per type (AA:AY).
        load_type_lookup: {code: LoadTypeDef} for LL kPa and llrf_type.

    Returns:
        {code: non_reducible_kn} — only "N" types have non-zero values.
    """
    result: dict[str, float] = {}
    for code, area_m2 in area_by_type.items():
        lt = load_type_lookup.get(code)
        if lt is not None and lt.llrf_type == "N":
            result[code] = area_m2 * lt.live_kpa
        else:
            result[code] = 0.0
    return result


# ---------------------------------------------------------------------------
# Service Load (PW) — Col H
# ---------------------------------------------------------------------------

def compute_pw(dl_kn: float, ll_kn: float) -> float:
    """Compute service load.

    Excel formula: PW = DL + LL (col H = col F + col G).
    """
    return dl_kn + ll_kn


# ---------------------------------------------------------------------------
# Factored Load (PF) — Col I
# ---------------------------------------------------------------------------

def compute_pf(dl_kn: float, ll_kn: float) -> float:
    """Compute factored load.

    Excel formula: PF = MAX(1.25 × DL + 1.5 × LL, 1.4 × DL)
    Verified: C1 row 10 in 20205:
        MAX(165.682×1.25 + 44.63×1.5, 1.4×165.682) = MAX(274.048, 231.955) = 274.048
    """
    return max(1.25 * dl_kn + 1.5 * ll_kn, 1.4 * dl_kn)


# ---------------------------------------------------------------------------
# Axial Stress (f/A) — Col J
# ---------------------------------------------------------------------------

def compute_f_over_a(pf_kn: float, z_m2: float) -> float | None:
    """Compute axial stress.

    Excel formula: IFERROR(PF / 1000 / Z, "")
    PF in kN → /1000 → MN, then /Z(m²) → MPa.

    Returns None if Z is zero or near-zero (element absent at this floor).
    """
    if z_m2 <= 0.0:
        return None
    return pf_kn / 1000.0 / z_m2


# ---------------------------------------------------------------------------
# Alpha Factor — Col K
# ---------------------------------------------------------------------------

def compute_alpha(fc_mpa: float) -> float:
    """Compute concrete alpha factor.

    Excel formula: alpha = MAX(0.85 - 0.0015 × f'c, 0.67)
    Where f'c = concrete strength (MPa) from col E.
    """
    return max(0.85 - 0.0015 * fc_mpa, 0.67)


# ---------------------------------------------------------------------------
# Cumulative Area — Col U
# ---------------------------------------------------------------------------

def compute_cum_area(
    area_this_floor: float,
    transfer_area: float,
    prev_cum_area: float,
    has_section: bool,
) -> float:
    """Compute cumulative area.

    Excel formula: U[N] = IF(Z[N]=0, 0, S[N] + T[N] + U[N-1])
    Only accumulates if element has a cross-section at this floor.

    Args:
        area_this_floor: Col S — total area this floor.
        transfer_area: Col T — transfer area this floor.
        prev_cum_area: U[N-1] — cumulative area from floor above.
        has_section: True if Z[N] > 0 (element has cross-section).

    Returns:
        Cumulative area in m².
    """
    if not has_section:
        return 0.0
    return area_this_floor + transfer_area + prev_cum_area


# ---------------------------------------------------------------------------
# Capacity Reduction Factor (phi) — used in % Steel calculation
# ---------------------------------------------------------------------------

def compute_phi(dim_x_mm: float, dim_y: str | float) -> float:
    """Compute capacity reduction factor (phi).

    Excel formula (inline in L7):
        IF(Y="D", 0.8,
           IF(MIN(X:Y) > 300, 0.8,
              0.2 + 0.002 × MIN(X, Y)))

    NOTE: Excel MIN() ignores text values. When Y is "S" or "W",
    MIN(X:Y) = X. No special-casing for square columns — the check
    is purely MIN(X,Y) > 300.

    Args:
        dim_x_mm: Col X dimension (mm).
        dim_y: Col Y — depth (mm) or "D"/"S"/"W".

    Returns:
        Capacity reduction factor.
    """
    if isinstance(dim_y, str):
        if dim_y.upper() == "D":
            return 0.8
        # "S" or "W": Excel MIN() ignores text → uses X only
        min_dim = dim_x_mm
    else:
        min_dim = min(dim_x_mm, float(dim_y))
    if min_dim > 300.0:
        return 0.8
    return 0.2 + 0.002 * min_dim


# ---------------------------------------------------------------------------
# % Steel — Col L
# ---------------------------------------------------------------------------

def compute_pct_steel(
    f_over_a_mpa: float,
    alpha: float,
    fc_mpa: float,
    dim_x_mm: float,
    dim_y: str | float,
) -> float:
    """Compute reinforcement ratio (% steel).

    Excel formula:
        L = IFERROR(MAX(
            (f_over_A / phi - alpha × 0.65 × f'c) / (0.85 × 400 - alpha × 0.65 × f'c),
            0.01
        ), 0)

    Where phi = compute_phi(dim_x, dim_y).

    Args:
        f_over_a_mpa: Axial stress (MPa) from compute_f_over_a().
        alpha: Alpha factor from compute_alpha().
        fc_mpa: Concrete strength (MPa).
        dim_x_mm: Col X dimension (mm).
        dim_y: Col Y dimension or code.

    Returns:
        Reinforcement ratio (decimal, e.g. 0.01 = 1%).
    """
    phi = compute_phi(dim_x_mm, dim_y)
    denominator = 0.85 * 400.0 - alpha * 0.65 * fc_mpa
    if abs(denominator) < 1e-10:
        return 0.0
    numerator = f_over_a_mpa / phi - alpha * 0.65 * fc_mpa
    ratio = numerator / denominator
    return max(ratio, 0.01)


# ---------------------------------------------------------------------------
# Area of Steel (As) — Col M
# ---------------------------------------------------------------------------

def compute_as(pct_steel: float, cross_section_m2: float) -> float:
    """Compute area of steel.

    Formula: As = %steel × Z × 1e6 (mm²)
    Where Z = cross-section area (m²).

    Args:
        pct_steel: Reinforcement ratio from compute_pct_steel().
        cross_section_m2: Cross-section area (m²) from column Z by compute_cross_section().

    Returns:
        Area of steel in mm².
    """
    return pct_steel * cross_section_m2 * 1e6


# ---------------------------------------------------------------------------
# Bar Area Lookup
# ---------------------------------------------------------------------------

def bar_area(bar_size: str) -> int:
    """Look up bar cross-sectional area from Canadian standard rebar table.

    Source: DATA sheet K4:L11.

    Args:
        bar_size: Rebar designation (e.g., "10M", "20M", "55M").

    Returns:
        Cross-sectional area in mm².

    Raises:
        KeyError: If bar_size not in BAR_SIZES table.
    """
    return BAR_SIZES[bar_size]


# ---------------------------------------------------------------------------
# Rebar Auto-Population — Cols O, P, Q (auto from N + As)
# Engineer selects bar_size (col N). O, P, Q auto-populate but are
# overridable — engineer adjusts if capacity not satisfied.
# ---------------------------------------------------------------------------

def _face_multiplier(dim_x_mm: float, dim_y: str | float) -> int:
    """Determine bar distribution multiplier based on element geometry.

    Circular (Y="D"): 1 — bars evenly spaced around perimeter.
    Square (X=Y):     4 — bars distributed across 4 equal faces.
    Rectangular:      2 — bars on 2 long faces.

    Used by compute_qty to ensure even bar distribution per face.
    """
    if isinstance(dim_y, str) and dim_y.upper() == "D":
        return 1
    if dim_x_mm == float(dim_y):
        return 4
    return 2


def compute_qty(
    as_mm2: float,
    bar_size: str,
    dim_x_mm: float,
    dim_y: str | float,
) -> int:
    """Auto-compute total bar quantity from required steel area.

    Excel formula (col O):
        =IF(Y="D", 1, IF(X=Y, 4, 2))
         * ROUNDUP(M / bar_area(N) / IF(Y="D", 1, IF(X=Y, 4, 2)), 0)

    Distributes bars evenly across faces:
      - Circular: 1 group, total = ROUNDUP(As/bar_area, 0)
      - Square:   4 faces, per_face = ROUNDUP(As/bar_area/4, 0), total = 4 × per_face
      - Rect:     2 faces, per_face = ROUNDUP(As/bar_area/2, 0), total = 2 × per_face

    Args:
        as_mm2: Required area of steel (mm²) from compute_as().
        bar_size: Engineer-selected bar designation (col N).
        dim_x_mm: Col X dimension (mm).
        dim_y: Col Y — depth (mm) or "D"/"S"/"W".

    Returns:
        Total number of bars.
    """
    single_bar = BAR_SIZES[bar_size]
    if single_bar <= 0 or as_mm2 <= 0:
        return 0
    mult = _face_multiplier(dim_x_mm, dim_y)
    per_face = math.ceil(as_mm2 / single_bar / mult)
    return mult * per_face


def compute_nbars(
    qty: int,
    bar_size: str,
    cross_section_m2: float,
) -> int:
    """Auto-compute normal lap bars (col P — Nbars).

    Excel formula (col P):
        =IF(N > 35, 0,
            IF(O * bar_area(N) / (Z*10^6) > 0.04,
                ROUNDDOWN(0.08 * Z * 10^6 / bar_area(N), 0) - O,
                O))

    Logic:
      - Large bars (>35M i.e. 45M, 55M): P=0, all bars use couplers.
      - Steel ratio > 4%: split — P = (max bars at 8% cap) - O.
      - Otherwise: P = O (all bars are normal laps, none need couplers).

    Args:
        qty: Total bar quantity (col O) from compute_qty().
        bar_size: Bar designation (col N, e.g., "20M").
        cross_section_m2: Element cross-section area (col Z) in m².

    Returns:
        Number of normal lap bars (col P).
    """
    # Extract numeric bar size (e.g., "20M" → 20, "45M" → 45)
    bar_num = int(bar_size.replace("M", ""))
    single_bar = BAR_SIZES[bar_size]

    if bar_num > 35:
        return 0  # Large bars — all require couplers

    if cross_section_m2 <= 0 or qty <= 0:
        return 0

    steel_ratio = qty * single_bar / (cross_section_m2 * 1e6)
    if steel_ratio > 0.04:
        # High ratio: compute max bars at 8% limit, P = max - O
        max_bars_at_8pct = math.floor(0.08 * cross_section_m2 * 1e6 / single_bar)
        return max(max_bars_at_8pct - qty, 0)

    return qty  # Normal case: all bars are normal laps


def compute_cbars(qty: int, n_bars: int) -> int:
    """Auto-compute coupler bars (col Q — Cbars).

    Excel formula (col Q):
        =O - P

    Coupler bars = total bars minus normal lap bars.

    Args:
        qty: Total bar quantity (col O).
        n_bars: Normal lap bars (col P) from compute_nbars().

    Returns:
        Number of coupler bars.
    """
    return max(qty - n_bars, 0)


# ---------------------------------------------------------------------------
# Rebar Design String — Col R
# ---------------------------------------------------------------------------

def format_rebar_design(
    bar_size: str,
    n_bars: int,
    c_bars: int,
    cross_section_m2: float,
) -> str | None:
    """Format rebar design string with 8% steel ratio check.

    Excel formula (col R):
        =IFERROR(
            IF(INDEX(rngCrossSectionArea, MATCH(N, rngBarSizes, 0)) * O / Z / 10^6 <= 0.08,
                IF(P>0, P&"-"&N, "") & IF(AND(P>0, Q>0), ", ", "") & IF(Q>0, Q&"-"&N&"●", ""),
                "OVER 8%"),
            "")

    Firm standard format:
        "8-20M"          → 8 normal lap bars of 20M
        "8-20M, 4-20M●"  → 8 normal laps + 4 coupler bars (● = coupler symbol)
        "OVER 8%"        → steel ratio exceeds 8% limit

    Args:
        bar_size: Engineer-selected bar designation (col N, e.g., "20M").
        n_bars: Normal lap bars (col P).
        c_bars: Coupler bars (col Q).
        cross_section_m2: Element cross-section area (col Z) in m².

    Returns:
        Formatted rebar string, "OVER 8%", or None if inputs missing.
    """
    if bar_size not in BAR_SIZES:
        return None
    if cross_section_m2 <= 0:
        return None

    single_bar_area = BAR_SIZES[bar_size]
    total_bars = n_bars + c_bars
    total_steel_mm2 = single_bar_area * total_bars
    steel_ratio = total_steel_mm2 / (cross_section_m2 * 1e6)

    if steel_ratio > 0.08:
        return "OVER 8%"

    parts: list[str] = []
    if n_bars > 0:
        parts.append(f"{n_bars}-{bar_size}")
    if c_bars > 0:
        parts.append(f"{c_bars}-{bar_size}\u25cf")  # ● (BLACK CIRCLE) = coupler

    return ", ".join(parts) if parts else None
