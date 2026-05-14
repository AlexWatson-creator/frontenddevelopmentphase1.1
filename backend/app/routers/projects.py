"""Project Management API router.

Domain model: dbo.Project rows = Revit model files.
Project.Number = real project identifier.
Metadata in management.project_meta.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.schemas.project import (
    MergeRequest,
    ProjectDetail,
    ProjectGroup,
    ProjectUpdate,
)
from app.services import project_service

router = APIRouter(tags=["projects"])


@router.get("/projects", response_model=list[ProjectGroup])
def list_projects(
    search: Optional[str] = Query(None, description="Search Number, FileName, or Address"),
    software: Optional[str] = Query(None, description="Filter by exact Software value"),
    sort_by: str = Query("last_run_time", description="Sort: last_run_time, number, elements, levels"),
    db: Session = Depends(get_db),
) -> list[ProjectGroup]:
    """List all projects grouped by Number."""
    return project_service.get_projects(
        db, search=search, software=software, sort_by=sort_by
    )


@router.get("/projects/{number}", response_model=ProjectDetail)
def get_project(number: str, db: Session = Depends(get_db)) -> ProjectDetail:
    """Get full detail for a project number."""
    detail = project_service.get_project_detail(db, number)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Project number '{number}' not found")
    return detail


@router.patch("/projects/{number}", response_model=ProjectDetail)
def update_project(
    number: str,
    data: ProjectUpdate,
    db: Session = Depends(get_db),
) -> ProjectDetail:
    """Update project metadata (writes to management.project_meta only)."""
    meta = project_service.update_project(db, number, data)
    if meta is None:
        raise HTTPException(status_code=404, detail=f"Project number '{number}' not found")
    # Return full detail after update
    detail = project_service.get_project_detail(db, number)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Project number '{number}' not found")
    return detail


@router.delete("/projects/{number}", status_code=204)
def delete_project(number: str, db: Session = Depends(get_db)) -> None:
    """Delete all files for a project number (cascade) + project_meta."""
    deleted = project_service.delete_project(db, number)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Project number '{number}' not found")


@router.delete("/projects/files/{file_id}", status_code=204)
def delete_file(file_id: int, db: Session = Depends(get_db)) -> None:
    """Delete a single file (cascade). If last file, also deletes project_meta."""
    deleted = project_service.delete_file(db, file_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"File id {file_id} not found")


@router.post("/projects/{number}/merge", response_model=ProjectDetail)
def merge_projects(
    number: str,
    body: MergeRequest,
    db: Session = Depends(get_db),
) -> ProjectDetail:
    """Merge source project into this one (target).

    Reassigns design records from source to target, then deletes source.
    """
    if body.source_number == number:
        raise HTTPException(status_code=400, detail="Cannot merge a project into itself")
    merged = project_service.merge_projects(db, number, body.source_number)
    if not merged:
        raise HTTPException(
            status_code=404,
            detail=f"Source '{body.source_number}' or target '{number}' not found",
        )
    detail = project_service.get_project_detail(db, number)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"Project number '{number}' not found")
    return detail