"""Rundown validation — area balance, transfer checks, data-gap detection.

Cross-checked against VBA source (D:/RESEARCH/Claude/RUNDOWN VBA/Transfers.bas):
  check_area_balance     ↔ CreateAreaChecks()
  check_transfers        ↔ CreateTransferChecks() + CreateTransferSummary()
  check_data_gaps        ↔ CreateWorksheetChecks() data-gap scan (lines 369-406)
  detect_circular_transfers ↔ topological sort failure in compute.py

Entry point: validate_rundown(input_data, result) -> ValidationResult.
"""

from __future__ import annotations

from .dtypes.inputs import ElementInput, RundownInput
from .dtypes.outputs import ElementResult, RundownResult
from .dtypes.validation import (
    AreaCheckRow,
    DataGapWarning,
    TransferCheckRow,
    ValidationResult,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_rundown(
    input_data: RundownInput,
    result: RundownResult,
) -> ValidationResult:
    """Run all validation checks and return a complete ValidationResult.

    Args:
        input_data: The original computation inputs.
        result: The computed results (elements + floors).

    Returns:
        ValidationResult with area checks, transfer checks, data gaps,
        errors, warnings, and overall is_valid flag.
    """
    area_checks = check_area_balance(result)
    transfer_checks = check_transfers(input_data)
    data_gaps = check_data_gaps(input_data)
    circular = detect_circular_transfers(input_data.elements)

    errors: list[str] = list(circular)
    warnings: list[str] = []

    # Area imbalance warnings
    for ac in area_checks:
        if not ac.is_balanced:
            warnings.append(
                f"Area imbalance at {ac.bot_level}–{ac.top_level}: "
                f"{ac.area_difference_m2:+.1f} m²"
            )

    # Data gap warnings
    for dg in data_gaps:
        warnings.append(f"{dg.element_mark}: {dg.message}")

    # Transfer status warnings
    for tc in transfer_checks:
        if tc.status == "over":
            warnings.append(
                f"{tc.element_mark}: {tc.pct_transferred * 100:.0f}% "
                f"transferred out (>105%)"
            )
        if not tc.all_within_range:
            warnings.append(
                f"{tc.element_mark}: transfer received outside active floor range"
            )

    return ValidationResult(
        area_checks=area_checks,
        transfer_checks=transfer_checks,
        data_gaps=data_gaps,
        errors=errors,
        warnings=warnings,
        is_valid=len(errors) == 0,
    )


# ---------------------------------------------------------------------------
# Area Balance Check — VBA: CreateAreaChecks()
# ---------------------------------------------------------------------------

def check_area_balance(result: RundownResult) -> list[AreaCheckRow]:
    """Check that tributary areas balance across all elements at each floor.

    VBA reference: Transfers.bas CreateAreaChecks() lines 511-617.
    For each floor level, sums AREA (col S) and CUM AREA (col U) across
    all elements.

    Area difference formula:
      Floor 0 (roof): CumArea_total[0] - TotArea_total[0]
      Floor i:        CumArea_total[i] - TotArea_total[i] - CumArea_total[i-1]

    When transfers are correct, area difference = 0.
    """
    if not result.elements:
        return []

    # Use first element's floor list as the level reference.
    # All elements should share the same level grid.
    ref_floors = result.elements[0].floors
    rows: list[AreaCheckRow] = []
    prev_cum_total = 0.0

    for i, ref in enumerate(ref_floors):
        total_area = 0.0
        total_cum = 0.0

        for elem in result.elements:
            if i < len(elem.floors):
                f = elem.floors[i]
                total_area += f.area_this_floor_m2
                total_cum += f.cum_area_m2

        # VBA formula: first floor has no "above", rest subtract previous
        if i == 0:
            diff = total_cum - total_area
        else:
            diff = total_cum - total_area - prev_cum_total

        rows.append(AreaCheckRow(
            bot_level=ref.bot_level,
            top_level=ref.top_level,
            total_area_m2=round(total_area, 4),
            cum_area_m2=round(total_cum, 4),
            area_difference_m2=round(diff, 4),
            is_balanced=abs(diff) <= 1.0,
        ))

        prev_cum_total = total_cum

    return rows


# ---------------------------------------------------------------------------
# Transfer Checks — VBA: CreateTransferChecks() + CreateTransferSummary()
# ---------------------------------------------------------------------------

def check_transfers(input_data: RundownInput) -> list[TransferCheckRow]:
    """Audit transfer relationships for each element.

    VBA reference: Transfers.bas CreateTransferChecks() lines 211-509.
    For each element computes:
      - % transferred OUT (sum of percentages where this element is the source)
      - List of target elements receiving from this element
      - Whether all transfers IN are at floors where the element has dimensions

    Status thresholds (from VBA conditional formatting):
      "none"  — 0% transferred (yellow in Excel)
      "ok"    — 100% ± 5%
      "under" — > 0% and < 95%
      "over"  — > 105% (blue in Excel)
    """
    # Build outgoing transfer map: source_mark -> [(target_mark, percent)]
    outgoing: dict[str, list[tuple[str, float]]] = {
        e.mark: [] for e in input_data.elements
    }
    for elem in input_data.elements:
        for t in elem.transfers_received:
            if t.source_element in outgoing:
                outgoing[t.source_element].append((elem.mark, t.percent))

    # Build active-level set per element (top_level where dimensions exist)
    active_levels: dict[str, set[str]] = {}
    for elem in input_data.elements:
        levels: set[str] = set()
        for f in elem.floors:
            if f.dimensions is not None:
                levels.add(f.level.top_level)
        active_levels[elem.mark] = levels

    rows: list[TransferCheckRow] = []

    for elem in input_data.elements:
        # Outgoing: how much of this element's load goes to others
        transfers_out = outgoing[elem.mark]
        pct = sum(p for _, p in transfers_out)
        to_elements = sorted(set(m for m, _ in transfers_out))

        # Status classification
        if pct == 0.0:
            status = "none"
        elif pct > 1.05:
            status = "over"
        elif pct < 0.95:
            status = "under"
        else:
            status = "ok"

        # Check: are all RECEIVED transfers at floors where this element
        # has dimensions?
        within_range = True
        if elem.transfers_received:
            my_levels = active_levels.get(elem.mark, set())
            for t in elem.transfers_received:
                if t.target_level not in my_levels:
                    within_range = False
                    break

        rows.append(TransferCheckRow(
            element_mark=elem.mark,
            pct_transferred=round(pct, 4),
            to_elements=to_elements,
            all_within_range=within_range,
            status=status,
        ))

    return rows


# ---------------------------------------------------------------------------
# Data Gap Detection — VBA: CreateTransferChecks() lines 369-406
# ---------------------------------------------------------------------------

def check_data_gaps(input_data: RundownInput) -> list[DataGapWarning]:
    """Detect non-contiguous dimension data in each element.

    VBA reference: Transfers.bas lines 369-406.
    Scans dimension cells top-to-bottom.  If data appears, then blank,
    then data again → gap detected (potential missing data in the middle).

    Having no dimensions at the top (starts late) or bottom (ends early)
    is normal — only interior gaps are flagged.
    """
    warnings: list[DataGapWarning] = []

    for elem in input_data.elements:
        found_data = False
        prev_blank = False

        for f in elem.floors:
            has_dims = f.dimensions is not None

            if has_dims:
                if found_data and prev_blank:
                    # Gap detected: data → blank → data
                    warnings.append(DataGapWarning(
                        element_mark=elem.mark,
                        message=(
                            f"non-contiguous dimensions — "
                            f"gap before level {f.level.top_level}"
                        ),
                    ))
                    break  # one warning per element
                found_data = True
                prev_blank = False
            else:
                if found_data:
                    prev_blank = True

    return warnings


# ---------------------------------------------------------------------------
# Circular Transfer Detection
# ---------------------------------------------------------------------------

def detect_circular_transfers(elements: list[ElementInput]) -> list[str]:
    """Detect circular dependencies in transfer relationships.

    Only considers non-pre-resolved transfers (dl_kn is None), since
    pre-resolved transfers (spreadsheet path) don't create computation
    dependencies.

    Returns:
        List of error messages describing each cycle found.
    """
    marks = {e.mark for e in elements}

    # Build adjacency: element -> set of elements it depends on
    deps: dict[str, set[str]] = {e.mark: set() for e in elements}
    for e in elements:
        for t in e.transfers_received:
            if t.dl_kn is not None:
                continue  # pre-resolved — no dependency
            if t.source_element in marks:
                deps[e.mark].add(t.source_element)

    # DFS cycle detection
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {m: WHITE for m in deps}
    errors: list[str] = []

    def _dfs(node: str, path: list[str]) -> None:
        color[node] = GRAY
        for dep in sorted(deps[node]):  # sorted for determinism
            if color[dep] == GRAY:
                # Cycle: trace back from dep in path
                cycle_start = path.index(dep)
                cycle = path[cycle_start:] + [dep]
                errors.append(
                    f"Circular transfer dependency: {' → '.join(cycle)}"
                )
            elif color[dep] == WHITE:
                _dfs(dep, path + [dep])
        color[node] = BLACK

    for m in sorted(deps):  # sorted for determinism
        if color[m] == WHITE:
            _dfs(m, [m])

    return errors
