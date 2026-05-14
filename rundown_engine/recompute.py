"""Rebar recomputation for user overrides.

Called when an engineer edits bar_size, qty, n_bars, or c_bars on a stored
rundown row. Recomputes only the downstream rebar chain — upstream values
(DL, LL, PF, f/A, %steel, As) are FROZEN.

Chain: bar_size → qty → n_bars → c_bars → rebar_design
Any step can be overridden (user supplies value), which freezes it and
recomputes only the steps below.
"""
from __future__ import annotations

from dataclasses import dataclass

from .dtypes.constants import BAR_SIZES
from .formulas import (
    compute_cbars,
    compute_nbars,
    compute_qty,
    format_rebar_design,
)


@dataclass
class RebarResult:
    """Output of a rebar recomputation."""
    bar_size: str | None
    qty: int | None
    n_bars: int | None
    c_bars: int | None
    rebar_design: str | None
    qty_auto: bool      # True = engine computed, False = user override
    n_bars_auto: bool
    c_bars_auto: bool


def recompute_rebar(
    bar_size: str | None,
    qty: int | None,
    n_bars: int | None,
    c_bars: int | None,
    qty_override: bool,
    n_bars_override: bool,
    c_bars_override: bool,
    as_mm2: float | None,
    dim_x_mm: float | None,
    dim_y: str | float | None,
    cross_section_m2: float | None,
) -> RebarResult:
    """Recompute rebar fields, respecting user overrides.

    Override flags indicate which values the user has explicitly set.
    Non-overridden fields are auto-computed from upstream values.

    Args:
        bar_size: Bar designation (e.g. "20M") or None.
        qty: Total bar count — user override or None for auto.
        n_bars: Normal lap bars — user override or None for auto.
        c_bars: Coupler bars — user override or None for auto.
        qty_override: If True, use qty as-is.
        n_bars_override: If True, use n_bars as-is.
        c_bars_override: If True, use c_bars as-is.
        as_mm2: Required steel area (frozen from stored row).
        dim_x_mm: Element width in mm (frozen).
        dim_y: Element depth in mm or "D"/"S"/"W" (frozen).
        cross_section_m2: Element cross-section in m² (frozen).

    Returns:
        RebarResult with all rebar fields and auto flags.
    """
    # No bar size → everything is None
    if not bar_size or bar_size not in BAR_SIZES:
        return RebarResult(
            bar_size=bar_size,
            qty=None, n_bars=None, c_bars=None,
            rebar_design=None,
            qty_auto=True, n_bars_auto=True, c_bars_auto=True,
        )

    # Need geometry for auto-computation
    if as_mm2 is None or dim_x_mm is None or dim_y is None or cross_section_m2 is None:
        return RebarResult(
            bar_size=bar_size,
            qty=qty, n_bars=n_bars, c_bars=c_bars,
            rebar_design=None,
            qty_auto=not qty_override,
            n_bars_auto=not n_bars_override,
            c_bars_auto=not c_bars_override,
        )

    # Step 1: QTY
    if qty_override and qty is not None:
        final_qty = qty
        qty_auto = False
    else:
        final_qty = compute_qty(as_mm2, bar_size, dim_x_mm, dim_y)
        qty_auto = True

    # Step 2: N_BARS
    if n_bars_override and n_bars is not None:
        final_n_bars = n_bars
        n_bars_auto = False
    else:
        final_n_bars = compute_nbars(final_qty, bar_size, cross_section_m2)
        n_bars_auto = True

    # Step 3: C_BARS
    if c_bars_override and c_bars is not None:
        final_c_bars = c_bars
        c_bars_auto = False
    else:
        final_c_bars = compute_cbars(final_qty, final_n_bars)
        c_bars_auto = True

    # Step 4: REBAR DESIGN (always auto)
    rebar_design = format_rebar_design(
        bar_size, final_n_bars, final_c_bars, cross_section_m2,
    )

    return RebarResult(
        bar_size=bar_size,
        qty=final_qty,
        n_bars=final_n_bars,
        c_bars=final_c_bars,
        rebar_design=rebar_design,
        qty_auto=qty_auto,
        n_bars_auto=n_bars_auto,
        c_bars_auto=c_bars_auto,
    )