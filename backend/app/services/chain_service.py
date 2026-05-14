"""Vertical Chain service — compute chains on-the-fly from identity hub.

A vertical chain = all element_identity rows sharing the same canonical_mark
within a project, ordered by level_identity.sort_order.  No materialised
storage — always derived from current identity data so manual overrides
in the identity hub take immediate effect.
"""
from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.design import ElementIdentity, LevelIdentity, Rundown
from app.schemas.chain import (
    BuildChainsResult,
    ChainDetail,
    ChainFloor,
    ChainSummary,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _query_chain_rows(
    db: Session,
    project_number: str,
) -> list[tuple]:
    """Return (element_identity, level_identity) pairs, sorted by mark then sort_order.

    Excludes stale elements.
    """
    return (
        db.query(ElementIdentity, LevelIdentity)
        .join(LevelIdentity, ElementIdentity.level_identity_id == LevelIdentity.id)
        .filter(
            ElementIdentity.project_number == project_number,
            ElementIdentity.match_method != "Stale",
        )
        .order_by(ElementIdentity.canonical_mark, LevelIdentity.sort_order)
        .all()
    )


def _all_sort_orders(db: Session, project_number: str) -> set[int]:
    """Return every sort_order that exists in level_identity for this project."""
    rows = (
        db.query(LevelIdentity.sort_order)
        .filter(LevelIdentity.project_number == project_number)
        .all()
    )
    return {r[0] for r in rows}


def _sort_order_to_name(db: Session, project_number: str) -> dict[int, str]:
    """Map sort_order → canonical_name for gap reporting."""
    rows = (
        db.query(LevelIdentity.sort_order, LevelIdentity.canonical_name)
        .filter(LevelIdentity.project_number == project_number)
        .all()
    )
    return {r[0]: r[1] for r in rows}


def _rundown_marks(db: Session, project_number: str) -> set[str]:
    """Return set of element_mark values that have rundown data."""
    rows = (
        db.query(Rundown.element_mark)
        .filter(
            Rundown.project_number == project_number,
            Rundown.element_mark.isnot(None),
        )
        .distinct()
        .all()
    )
    return {r[0] for r in rows}


def _group_chains(
    rows: list[tuple],
) -> dict[tuple[str, str], list[tuple]]:
    """Group (element_identity, level_identity) pairs by (canonical_mark, element_type)."""
    chains: dict[tuple[str, str], list[tuple]] = {}
    for ei, li in rows:
        key = (ei.canonical_mark, ei.element_type)
        chains.setdefault(key, []).append((ei, li))
    return chains


def _detect_gaps(
    chain_sort_orders: list[int],
    all_orders: set[int],
    order_to_name: dict[int, str],
) -> list[str]:
    """Return level names where a gap exists in the chain.

    A gap = a sort_order that exists in level_identity between the chain's
    min and max sort_order but is NOT present in the chain.
    """
    if len(chain_sort_orders) <= 1:
        return []
    min_o, max_o = min(chain_sort_orders), max(chain_sort_orders)
    chain_set = set(chain_sort_orders)
    gaps = []
    for o in sorted(all_orders):
        if min_o < o < max_o and o not in chain_set:
            name = order_to_name.get(o, f"sort_order={o}")
            gaps.append(name)
    return gaps


def _build_summary(
    mark: str,
    etype: str,
    floors: list[tuple],
    gaps: list[str],
) -> ChainSummary:
    """Build a ChainSummary from sorted (element_identity, level_identity) pairs."""
    return ChainSummary(
        canonical_mark=mark,
        element_type=etype,
        floor_count=len(floors),
        min_level=floors[0][1].canonical_name,
        max_level=floors[-1][1].canonical_name,
        has_gaps=len(gaps) > 0,
        gap_count=len(gaps),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_chains(db: Session, project_number: str) -> BuildChainsResult:
    """Compute all vertical chains for a project.

    Returns summary statistics + chain list.  This is the "action" endpoint
    that the user triggers via the Build Chains button.
    """
    rows = _query_chain_rows(db, project_number)
    if not rows:
        return BuildChainsResult(
            total_chains=0,
            total_elements=0,
            chains_with_gaps=0,
            single_floor_elements=0,
            chains=[],
        )

    all_orders = _all_sort_orders(db, project_number)
    order_to_name = _sort_order_to_name(db, project_number)
    grouped = _group_chains(rows)

    summaries: list[ChainSummary] = []
    chains_with_gaps = 0
    single_floor = 0

    for (mark, etype), chain_rows in sorted(grouped.items()):
        sort_orders = [li.sort_order for _, li in chain_rows]
        gaps = _detect_gaps(sort_orders, all_orders, order_to_name)
        summary = _build_summary(mark, etype, chain_rows, gaps)
        summaries.append(summary)

        if gaps:
            chains_with_gaps += 1
        if len(chain_rows) == 1:
            single_floor += 1

    return BuildChainsResult(
        total_chains=len(summaries),
        total_elements=len(rows),
        chains_with_gaps=chains_with_gaps,
        single_floor_elements=single_floor,
        chains=summaries,
    )


def get_chains(db: Session, project_number: str) -> list[ChainSummary]:
    """Return all chain summaries for a project."""
    rows = _query_chain_rows(db, project_number)
    if not rows:
        return []

    all_orders = _all_sort_orders(db, project_number)
    order_to_name = _sort_order_to_name(db, project_number)
    grouped = _group_chains(rows)

    summaries: list[ChainSummary] = []
    for (mark, etype), chain_rows in sorted(grouped.items()):
        sort_orders = [li.sort_order for _, li in chain_rows]
        gaps = _detect_gaps(sort_orders, all_orders, order_to_name)
        summaries.append(_build_summary(mark, etype, chain_rows, gaps))

    return summaries


def get_chain_detail(
    db: Session,
    project_number: str,
    element_identity_id: int,
) -> ChainDetail | None:
    """Return full chain detail for the chain containing a given element.

    Looks up the element's canonical_mark, then returns all floors in that
    chain with gap analysis and rundown-data flags.
    """
    # Find the anchor element
    anchor = (
        db.query(ElementIdentity)
        .filter(
            ElementIdentity.id == element_identity_id,
            ElementIdentity.project_number == project_number,
        )
        .first()
    )
    if anchor is None:
        return None

    # Get all elements in this chain (same mark + type, non-stale)
    chain_rows = (
        db.query(ElementIdentity, LevelIdentity)
        .join(LevelIdentity, ElementIdentity.level_identity_id == LevelIdentity.id)
        .filter(
            ElementIdentity.project_number == project_number,
            ElementIdentity.canonical_mark == anchor.canonical_mark,
            ElementIdentity.element_type == anchor.element_type,
            ElementIdentity.match_method != "Stale",
        )
        .order_by(LevelIdentity.sort_order)
        .all()
    )

    if not chain_rows:
        return None

    # Gap detection
    all_orders = _all_sort_orders(db, project_number)
    order_to_name = _sort_order_to_name(db, project_number)
    sort_orders = [li.sort_order for _, li in chain_rows]
    gaps = _detect_gaps(sort_orders, all_orders, order_to_name)

    # Rundown existence check
    marks_with_rundown = _rundown_marks(db, project_number)

    floors = [
        ChainFloor(
            element_identity_id=ei.id,
            level_identity_id=li.id,
            level_name=li.canonical_name,
            sort_order=li.sort_order,
            revit_guid=ei.revit_guid,
            match_confidence=ei.match_confidence,
            has_rundown=ei.canonical_mark in marks_with_rundown,
        )
        for ei, li in chain_rows
    ]

    return ChainDetail(
        canonical_mark=anchor.canonical_mark,
        element_type=anchor.element_type,
        floor_count=len(floors),
        min_level=floors[0].level_name,
        max_level=floors[-1].level_name,
        has_gaps=len(gaps) > 0,
        gap_count=len(gaps),
        floors=floors,
        gaps=gaps,
    )