"""Load Table CRUD API router.

Load tables are per-file (project_id = dbo.Project.Id).
project_number FK → management.project_meta (resolved from Project.Number).
Unique constraint: (project_id, name) — one "RES" per file.

Dependent tables (load_areas, tributary_results, load_assignments, rundown)
use NO_ACTION on delete. Bulk replace and single delete clear dependents
first via application code — computation results will be recomputed.
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models import LoadTable, Project
from app.models.design import LoadArea, LoadAssignment, Rundown, TributaryResult
from app.schemas.load_table import LoadTableCreate, LoadTableEntry, LoadTableUpdate

router = APIRouter(tags=["load-tables"])

_CREATED_BY_DEFAULT = "system"


def _verify_file_exists(db: Session, file_id: int) -> Project:
    """Raise 404 if file not found."""
    project = db.query(Project).filter(Project.Id == file_id).first()
    if project is None:
        raise HTTPException(status_code=404, detail=f"File id {file_id} not found")
    return project


def _clear_dependents_for_file(db: Session, project_id: int) -> None:
    """Delete all computation results that reference load_tables for this file.

    Required because dependent FKs use NO_ACTION on delete.
    """
    db.query(LoadAssignment).filter(LoadAssignment.project_id == project_id).delete()
    db.query(Rundown).filter(Rundown.project_id == project_id).delete()
    db.query(TributaryResult).filter(TributaryResult.project_id == project_id).delete()
    db.query(LoadArea).filter(LoadArea.project_id == project_id).delete()


def _clear_dependents_for_entry(db: Session, entry: LoadTable) -> None:
    """Delete computation results that reference a specific load_table entry."""
    db.query(LoadAssignment).filter(
        LoadAssignment.project_id == entry.project_id,
        LoadAssignment.load_table_id == entry.id,
    ).delete()
    db.query(Rundown).filter(
        Rundown.project_id == entry.project_id,
        Rundown.load_table_id == entry.id,
    ).delete()
    db.query(TributaryResult).filter(
        TributaryResult.project_id == entry.project_id,
        TributaryResult.load_table_id == entry.id,
    ).delete()
    db.query(LoadArea).filter(
        LoadArea.project_id == entry.project_id,
        LoadArea.load_table_id == entry.id,
    ).delete()


@router.get(
    "/projects/files/{file_id}/load-table",
    response_model=list[LoadTableEntry],
)
def get_load_table(
    file_id: int,
    db: Session = Depends(get_db),
) -> list[LoadTableEntry]:
    """Get all load table entries for a file."""
    _verify_file_exists(db, file_id)
    entries = (
        db.query(LoadTable)
        .filter(LoadTable.project_id == file_id)
        .order_by(LoadTable.name)
        .all()
    )
    return [LoadTableEntry.model_validate(e) for e in entries]


@router.post(
    "/projects/files/{file_id}/load-table",
    response_model=list[LoadTableEntry],
    status_code=201,
)
def bulk_replace_load_table(
    file_id: int,
    entries: list[LoadTableCreate],
    db: Session = Depends(get_db),
) -> list[LoadTableEntry]:
    """Bulk create/replace load table entries for a file.

    Replaces ALL existing entries. Clears any dependent computation
    results (load_areas, tributary_results, load_assignments, rundown)
    since they reference the old load_table entries.
    """
    project = _verify_file_exists(db, file_id)

    if not entries:
        raise HTTPException(status_code=400, detail="At least one entry is required")

    # Check for duplicate names in the request
    names = [e.name for e in entries]
    if len(names) != len(set(names)):
        raise HTTPException(status_code=400, detail="Duplicate load table names in request")

    # Clear dependents first (NO_ACTION FKs), then existing entries
    _clear_dependents_for_file(db, file_id)
    db.query(LoadTable).filter(LoadTable.project_id == file_id).delete()

    # Insert new entries
    now = datetime.now(timezone.utc)
    new_rows = []
    for entry_data in entries:
        row = LoadTable(
            project_number=project.Number,
            project_id=file_id,
            name=entry_data.name,
            description=entry_data.description,
            dead_load_kpa=entry_data.dead_load_kpa,
            live_load_kpa=entry_data.live_load_kpa,
            llrf_type=entry_data.llrf_type,
            created_by=_CREATED_BY_DEFAULT,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        new_rows.append(row)

    db.commit()
    for row in new_rows:
        db.refresh(row)

    return [LoadTableEntry.model_validate(r) for r in new_rows]


@router.patch(
    "/projects/files/{file_id}/load-table/{entry_id}",
    response_model=LoadTableEntry,
)
def update_load_table_entry(
    file_id: int,
    entry_id: int,
    data: LoadTableUpdate,
    db: Session = Depends(get_db),
) -> LoadTableEntry:
    """Update a single load table entry."""
    entry = (
        db.query(LoadTable)
        .filter(LoadTable.id == entry_id, LoadTable.project_id == file_id)
        .first()
    )
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail=f"Load table entry {entry_id} not found for file {file_id}",
        )

    update_fields = data.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        setattr(entry, field, value)

    entry.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(entry)
    return LoadTableEntry.model_validate(entry)


@router.delete(
    "/projects/files/{file_id}/load-table/{entry_id}",
    status_code=204,
)
def delete_load_table_entry(
    file_id: int,
    entry_id: int,
    db: Session = Depends(get_db),
) -> None:
    """Delete a single load table entry.

    Clears dependent computation results for this entry first.
    """
    entry = (
        db.query(LoadTable)
        .filter(LoadTable.id == entry_id, LoadTable.project_id == file_id)
        .first()
    )
    if entry is None:
        raise HTTPException(
            status_code=404,
            detail=f"Load table entry {entry_id} not found for file {file_id}",
        )

    _clear_dependents_for_entry(db, entry)
    db.delete(entry)
    db.commit()