"""Identity Hub API router — level + element identity sync, CRUD.

Single sync endpoint replaces separate populate/reconcile.
GET endpoints auto-sync if dbo has changed since last sync.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import Project
from app.schemas.identity import (
    ElementIdentityRead,
    ElementIdentityUpdate,
    ElementStatsResult,
    ElementSyncResult,
    LevelIdentityRead,
    LevelIdentityUpdate,
    LevelSyncResult,
)
from app.services import element_identity as elem_svc
from app.services import level_identity as level_svc

router = APIRouter(tags=["identity"])


def _verify_project_exists(db: Session, number: str) -> None:
    """Raise 404 if no dbo.Project rows exist for this project number."""
    exists = db.query(Project).filter(Project.Number == number).first()
    if exists is None:
        raise HTTPException(status_code=404, detail=f"Project '{number}' not found")


# ---------------------------------------------------------------------------
# Level Identity — Sync / GET / PATCH
# ---------------------------------------------------------------------------

@router.post(
    "/projects/{number}/levels/sync",
    response_model=LevelSyncResult,
)
def sync_levels(
    number: str,
    db: Session = Depends(get_db),
) -> LevelSyncResult:
    """Sync level_identity from Revit (dbo.Levels).

    Unified populate + stale detection. Stale levels with linked
    rundown/ETABS data are preserved; unlinked stale levels are auto-deleted.
    """
    _verify_project_exists(db, number)
    return level_svc.sync_from_revit(db, number)


@router.get(
    "/projects/{number}/levels/identity",
    response_model=list[LevelIdentityRead],
)
def get_level_identities(
    number: str,
    db: Session = Depends(get_db),
) -> list[LevelIdentityRead]:
    """Get all level identity rows. Auto-syncs if dbo has changed."""
    _verify_project_exists(db, number)
    # Auto-sync if dbo is newer than last sync
    level_svc.auto_sync_if_needed(db, number)
    levels = level_svc.get_levels(db, number)
    return [LevelIdentityRead.model_validate(lv) for lv in levels]


@router.patch(
    "/projects/{number}/levels/identity/{level_id}",
    response_model=LevelIdentityRead,
)
def update_level_identity(
    number: str,
    level_id: int,
    data: LevelIdentityUpdate,
    db: Session = Depends(get_db),
) -> LevelIdentityRead:
    """Update a single level identity row (canonical_name, sort_order, rundown_name, etabs_name)."""
    _verify_project_exists(db, number)
    entry = level_svc.update_level(db, number, level_id, data)
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail=f"Level identity {level_id} not found for project '{number}'",
        )
    return LevelIdentityRead.model_validate(entry)


# ---------------------------------------------------------------------------
# Element Identity — Sync / GET / PATCH / Stats
# ---------------------------------------------------------------------------

@router.post(
    "/projects/{number}/elements/sync",
    response_model=ElementSyncResult,
)
def sync_elements(
    number: str,
    db: Session = Depends(get_db),
) -> ElementSyncResult:
    """Sync element_identity from Revit (dbo.Columns + dbo.Walls).

    Unified populate + stale detection. Stale elements with linked
    rundown/ETABS data are preserved; unlinked stale elements are auto-deleted.
    """
    _verify_project_exists(db, number)
    return elem_svc.sync_from_revit(db, number)


@router.get(
    "/projects/{number}/elements/identity/stats",
    response_model=ElementStatsResult,
)
def get_element_stats(
    number: str,
    db: Session = Depends(get_db),
) -> ElementStatsResult:
    """Return element identity counts by type, confidence bands, and errors."""
    _verify_project_exists(db, number)
    return elem_svc.get_element_stats(db, number)


@router.get(
    "/projects/{number}/elements/identity",
    response_model=list[ElementIdentityRead],
)
def get_element_identities(
    number: str,
    type: str | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
) -> list[ElementIdentityRead]:
    """Get element identity rows. Auto-syncs if dbo has changed."""
    _verify_project_exists(db, number)
    # Auto-sync if dbo is newer than last sync
    elem_svc.auto_sync_if_needed(db, number)
    elements = elem_svc.get_elements(db, number, element_type=type, search=search)
    return [ElementIdentityRead.model_validate(e) for e in elements]


@router.patch(
    "/projects/{number}/elements/identity/{element_id}",
    response_model=ElementIdentityRead,
)
def update_element_identity(
    number: str,
    element_id: int,
    data: ElementIdentityUpdate,
    db: Session = Depends(get_db),
) -> ElementIdentityRead:
    """Update a single element identity row."""
    _verify_project_exists(db, number)
    entry = elem_svc.update_element(db, number, element_id, data)
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail=f"Element identity {element_id} not found for project '{number}'",
        )
    return ElementIdentityRead.model_validate(entry)