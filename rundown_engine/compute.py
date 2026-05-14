"""Rundown computation orchestrator — computes all elements top-to-bottom.

Entry point: compute_rundown(RundownInput) -> RundownResult.

Handles:
  1. Build load type lookup
  2. Topological sort by transfer dependencies
  3. Per-element, per-floor iteration calling formula functions
  4. Transfer resolution (pre-resolved or computed from source element results)
"""

from __future__ import annotations

from . import formulas
from .dtypes.inputs import (
    ElementInput,
    FloorInput,
    RundownInput,
    TransferDef,
)
from .dtypes.outputs import ElementResult, FloorResult, RundownResult
from .dtypes.validation import ValidationResult
from .validate import validate_rundown as _validate_rundown


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_rundown(input_data: RundownInput) -> RundownResult:
    """Compute the full rundown for all elements.

    Args:
        input_data: Complete input for the entire project.

    Returns:
        RundownResult with all elements computed and validated.
    """
    # 1. Build load type lookup
    lt_lookup = {lt.code: lt for lt in input_data.load_types}

    # 2. Topological sort elements by transfer dependencies
    sorted_elements = _topological_sort(input_data.elements)

    # 3. Compute each element in dependency order
    computed: dict[str, ElementResult] = {}
    for element in sorted_elements:
        result = _compute_element(element, lt_lookup, computed)
        computed[element.mark] = result

    # 4. Return results in original input order (not topo order)
    ordered = [computed[e.mark] for e in input_data.elements if e.mark in computed]

    run_result = RundownResult(
        project_number=input_data.project_number,
        elements=ordered,
        validation=ValidationResult(),
    )

    # 5. Run validation checks
    run_result.validation = _validate_rundown(input_data, run_result)

    return run_result


# ---------------------------------------------------------------------------
# Topological Sort
# ---------------------------------------------------------------------------

def _topological_sort(elements: list[ElementInput]) -> list[ElementInput]:
    """Sort elements so that transfer sources are computed before targets.

    If B receives from A, A must be computed first.
    Elements with no transfers come first (arbitrary stable order).
    Circular dependencies are detected and those elements are appended last.
    """
    by_mark = {e.mark: e for e in elements}

    # Build adjacency: target -> set of sources it depends on
    deps: dict[str, set[str]] = {e.mark: set() for e in elements}
    for e in elements:
        for t in e.transfers_received:
            if t.dl_kn is not None:
                # Pre-resolved (spreadsheet path) — no dependency needed
                continue
            if t.source_element in by_mark:
                deps[e.mark].add(t.source_element)

    # Kahn's algorithm
    in_degree = {m: len(d) for m, d in deps.items()}
    queue = [m for m, deg in in_degree.items() if deg == 0]
    result: list[str] = []

    while queue:
        # Stable: process in queue order (alphabetical for determinism)
        queue.sort()
        mark = queue.pop(0)
        result.append(mark)
        # Reduce in-degree of dependents
        for m, d in deps.items():
            if mark in d:
                d.discard(mark)
                in_degree[m] -= 1
                if in_degree[m] == 0:
                    queue.append(m)

    # Anything not in result has circular dependency — append anyway
    for e in elements:
        if e.mark not in result:
            result.append(e.mark)

    return [by_mark[m] for m in result]


# ---------------------------------------------------------------------------
# Per-Element Computation
# ---------------------------------------------------------------------------

def _compute_element(
    element: ElementInput,
    lt_lookup: dict[str, object],
    computed: dict[str, ElementResult],
) -> ElementResult:
    """Compute all floors for one element, top-to-bottom."""
    floor_results: list[FloorResult] = []

    # Running state across floors (cumulative values)
    prev_dl = 0.0            # F[N-1]
    prev_dy = 0.0            # DY[N-1]
    prev_cum_area = 0.0      # U[N-1]
    prev_height = 0.0        # D[N-1] for cladding
    cum_area_by_type: dict[str, float] = {}  # BA:BY running totals

    for floor in element.floors:
        fr = _compute_floor(
            floor=floor,
            element=element,
            lt_lookup=lt_lookup,
            computed=computed,
            prev_dl=prev_dl,
            prev_dy=prev_dy,
            prev_cum_area=prev_cum_area,
            prev_height=prev_height,
            cum_area_by_type=cum_area_by_type,
        )
        floor_results.append(fr)

        # Update running state for next floor
        prev_dl = fr.dl_cumulative_kn
        prev_dy = fr.dy_cumulative_kn
        prev_cum_area = fr.cum_area_m2
        prev_height = fr.story_height_m
        # cum_area_by_type is mutated in-place by _compute_floor

    return ElementResult(
        mark=element.mark,
        element_type=element.element_type,
        floors=floor_results,
        cladding_kpa=element.cladding_kpa,
        transfers_received=element.transfers_received,
    )


# ---------------------------------------------------------------------------
# Per-Floor Computation
# ---------------------------------------------------------------------------

def _compute_floor(
    floor: FloorInput,
    element: ElementInput,
    lt_lookup: dict[str, object],
    computed: dict[str, ElementResult],
    prev_dl: float,
    prev_dy: float,
    prev_cum_area: float,
    prev_height: float,
    cum_area_by_type: dict[str, float],
) -> FloorResult:
    """Compute one floor of one element.

    Follows the exact Excel computation order (see plan Section "Computation Flow").
    """
    level = floor.level
    dims = floor.dimensions

    # --- Cross-section (col Z) ---
    if dims is not None:
        dim_x = dims.dim_x_mm
        dim_y = dims.dim_y
        z = formulas.compute_cross_section(dim_x, dim_y)
    else:
        dim_x = None
        dim_y = None
        z = 0.0
    has_section = z > 0.0

    # --- Areas per type (AA:AY → S) ---
    area_this_floor = sum(floor.area_by_type.values())  # col S

    # --- Cumulative area per type (BA:BY) — mutate running dict ---
    for code, area in floor.area_by_type.items():
        cum_area_by_type[code] = cum_area_by_type.get(code, 0.0) + area

    # --- Transfer resolution (T, transfer DL, transfer LL) ---
    transfer_dl = 0.0
    transfer_ll = 0.0
    transfer_area = 0.0
    for t in element.transfers_received:
        if t.target_level != level.top_level:
            continue
        dl, ll, cum_a = _resolve_transfer(t, computed)
        transfer_dl += dl
        transfer_ll += ll
        transfer_area += cum_a

    # --- Cumulative area (col U) ---
    cum_area = formulas.compute_cum_area(
        area_this_floor, transfer_area, prev_cum_area, has_section
    )

    # --- LLRF per type (CA:CY) ---
    llrf_by_type: dict[str, float] = {}
    for code in cum_area_by_type:
        lt = lt_lookup.get(code)
        if lt is not None:
            llrf_by_type[code] = formulas.compute_llrf(
                lt.llrf_type, cum_area_by_type[code]
            )

    # --- Dead Load (col F) — 6 terms ---
    dl_from_above = prev_dl
    dl_floor_load = formulas.compute_dl_floor_load(floor.area_by_type, lt_lookup)
    dl_transfer = transfer_dl
    dl_self_weight = formulas.compute_self_weight(z, level.story_height_m)
    dl_cladding = formulas.compute_cladding(
        element.cladding_kpa, floor.cladding_perimeter_m, prev_height
    )
    dl_beam_weight = floor.beam_weight_kn
    dl_cumulative = (
        dl_from_above + dl_floor_load + dl_transfer
        + dl_self_weight + dl_cladding + dl_beam_weight
    )

    # --- Live Load (col G) — two-path system ---
    # Non-reducible per type (CZ:DX)
    ll_nr_by_type = formulas.compute_ll_non_reducible_by_type(
        floor.area_by_type, lt_lookup
    )
    ll_nr_this_floor = sum(ll_nr_by_type.values())

    # DY accumulator: non-reducible LL + transfer LL + DY[N-1]
    dy_cumulative = ll_nr_this_floor + transfer_ll + prev_dy

    # Reducible LL (recomputed fresh each floor)
    ll_reducible = formulas.compute_ll_reducible(
        cum_area_by_type, lt_lookup, llrf_by_type
    )

    # Total LL = reducible + DY
    ll_cumulative = ll_reducible + dy_cumulative

    # --- Derived loads ---
    pw = formulas.compute_pw(dl_cumulative, ll_cumulative)
    pf = formulas.compute_pf(dl_cumulative, ll_cumulative)

    # --- Design outputs (cols J, K, L, M) ---
    f_over_a = formulas.compute_f_over_a(pf, z) if has_section else None
    alpha = formulas.compute_alpha(level.concrete_mpa) if has_section else None
    phi = formulas.compute_phi(dim_x, dim_y) if has_section and dim_x is not None else None

    if f_over_a is not None and alpha is not None and dim_x is not None:
        pct_steel = formulas.compute_pct_steel(f_over_a, alpha, level.concrete_mpa, dim_x, dim_y)
        as_mm2 = formulas.compute_as(pct_steel, z)
    else:
        pct_steel = None
        as_mm2 = None

    # --- Rebar (cols N-R) — from input if engineer provided, else auto-compute ---
    bar_size = floor.bar_size
    qty = floor.qty
    n_bars = floor.n_bars
    c_bars = floor.c_bars
    rebar_design = None

    if bar_size is not None and as_mm2 is not None and dim_x is not None:
        # Auto-compute O, P, Q if not overridden
        if qty is None:
            qty = formulas.compute_qty(as_mm2, bar_size, dim_x, dim_y)
        if n_bars is None:
            n_bars = formulas.compute_nbars(qty, bar_size, z)
        if c_bars is None:
            c_bars = formulas.compute_cbars(qty, n_bars)
        rebar_design = formulas.format_rebar_design(bar_size, n_bars, c_bars, z)

    return FloorResult(
        # Identity
        bot_level=level.bot_level,
        top_level=level.top_level,
        # Geometry
        story_height_m=level.story_height_m,
        concrete_mpa=level.concrete_mpa,
        dim_x_mm=dim_x,
        dim_y=dim_y,
        cross_section_m2=z if has_section else None,
        # Areas
        area_by_type=dict(floor.area_by_type),
        cum_area_by_type=dict(cum_area_by_type),
        area_this_floor_m2=area_this_floor,
        transfer_area_m2=transfer_area,
        cum_area_m2=cum_area,
        # DL breakdown
        dl_from_above_kn=dl_from_above,
        dl_floor_load_kn=dl_floor_load,
        dl_transfer_kn=dl_transfer,
        dl_self_weight_kn=dl_self_weight,
        dl_cladding_kn=dl_cladding,
        dl_beam_weight_kn=dl_beam_weight,
        dl_cumulative_kn=dl_cumulative,
        # LL breakdown
        llrf_by_type=llrf_by_type,
        ll_reducible_kn=ll_reducible,
        ll_non_reducible_by_type=ll_nr_by_type,
        ll_non_reducible_this_floor_kn=ll_nr_this_floor,
        ll_transfer_kn=transfer_ll,
        dy_cumulative_kn=dy_cumulative,
        ll_cumulative_kn=ll_cumulative,
        # Derived loads
        pw_kn=pw,
        pf_kn=pf,
        # Design outputs
        f_over_a_mpa=f_over_a,
        alpha=alpha,
        phi=phi,
        pct_steel=pct_steel,
        # Rebar
        as_mm2=as_mm2,
        bar_size=bar_size,
        qty=qty,
        n_bars=n_bars,
        c_bars=c_bars,
        rebar_design=rebar_design,
        # Input carried through
        beam_weight_kn=floor.beam_weight_kn,
        cladding_perimeter_m=floor.cladding_perimeter_m,
    )


# ---------------------------------------------------------------------------
# Transfer Resolution
# ---------------------------------------------------------------------------

def _resolve_transfer(
    transfer: TransferDef,
    computed: dict[str, ElementResult],
) -> tuple[float, float, float]:
    """Resolve a single transfer's DL, LL, and CUM AREA values.

    Two paths:
      - Spreadsheet: pre-resolved values in TransferDef (dl_kn, ll_kn, cum_area_m2).
      - Revit/CAD: look up source element's already-computed results.

    Returns:
        (dl_kn, ll_kn, cum_area_m2) — resolved transfer values.
    """
    if transfer.dl_kn is not None:
        # Spreadsheet path — use pre-resolved values
        return (
            transfer.dl_kn,
            transfer.ll_kn or 0.0,
            transfer.cum_area_m2 or 0.0,
        )

    # Revit/CAD path — look up from computed results
    source = computed.get(transfer.source_element)
    if source is None:
        # Source not yet computed (circular dep or missing) — return zeros
        return (0.0, 0.0, 0.0)

    source_floor = _find_floor_by_top_level(source, transfer.target_level)
    if source_floor is None:
        return (0.0, 0.0, 0.0)

    pct = transfer.percent
    return (
        source_floor.dl_cumulative_kn * pct,
        source_floor.ll_cumulative_kn * pct,
        source_floor.cum_area_m2 * pct,
    )


def _find_floor_by_top_level(
    element: ElementResult, top_level: str
) -> FloorResult | None:
    """Find a floor result by its TOP LEVEL name."""
    for f in element.floors:
        if f.top_level == top_level:
            return f
    return None