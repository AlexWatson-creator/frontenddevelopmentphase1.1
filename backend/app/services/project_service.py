"""Project management service layer.

Domain model: dbo.Project rows are Revit model files.
Project.Number is the real identifier. Metadata in management.project_meta.

dbo is READ-ONLY except for:
  - DELETE dbo.Project rows (FK cascades to elements + design)
PATCH writes ONLY to management.project_meta, never dbo.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.models import (
    Beam,
    DboColumn,
    Floor,
    Foundation,
    Level,
    Project,
    ProjectMeta,
    Wall,
)
from app.schemas.project import (
    ElementCounts,
    LevelWithCounts,
    MergeRequest,
    ProjectDetail,
    ProjectFile,
    ProjectFileDetail,
    ProjectGroup,
    ProjectUpdate,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _file_element_counts(db: Session, project_id: int) -> ElementCounts:
    """Count elements for a single dbo.Project file."""
    return ElementCounts(
        columns=db.query(DboColumn).filter(DboColumn.Project_id == project_id).count(),
        walls=db.query(Wall).filter(Wall.Project_id == project_id).count(),
        beams=db.query(Beam).filter(Beam.Project_id == project_id).count(),
        floors=db.query(Floor).filter(Floor.Project_id == project_id).count(),
        foundations=db.query(Foundation).filter(Foundation.Project_id == project_id).count(),
    )


def _level_element_counts(
    db: Session, project_id: int, level_id: int
) -> ElementCounts:
    """Count elements at a specific level for a file."""
    return ElementCounts(
        columns=db.query(DboColumn).filter(
            DboColumn.Project_id == project_id,
            DboColumn.BaseConstraint_id == level_id,
        ).count(),
        walls=db.query(Wall).filter(
            Wall.Project_id == project_id,
            Wall.BaseConstraint_id == level_id,
        ).count(),
        beams=db.query(Beam).filter(
            Beam.Project_id == project_id,
            Beam.Level_id == level_id,
        ).count(),
        floors=db.query(Floor).filter(
            Floor.Project_id == project_id,
            Floor.Level_id == level_id,
        ).count(),
        foundations=0,  # Foundations have no level location data
    )


def _aggregate_counts(counts_list: list[ElementCounts]) -> ElementCounts:
    """Sum element counts across multiple files."""
    return ElementCounts(
        columns=sum(c.columns for c in counts_list),
        walls=sum(c.walls for c in counts_list),
        beams=sum(c.beams for c in counts_list),
        floors=sum(c.floors for c in counts_list),
        foundations=sum(c.foundations for c in counts_list),
    )


# ---------------------------------------------------------------------------
# get_projects — list grouped by Number
# ---------------------------------------------------------------------------

def get_projects(
    db: Session,
    *,
    search: Optional[str] = None,
    software: Optional[str] = None,
    sort_by: str = "last_run_time",
) -> list[ProjectGroup]:
    """List all projects grouped by Number.

    Args:
        search: Filter by Number, FileName, or Address (case-insensitive).
        software: Filter by exact Software value.
        sort_by: One of 'last_run_time', 'number', 'elements', 'levels'.
    """
    # Start with all projects joined to project_meta for address
    query = (
        db.query(Project, ProjectMeta.address, ProjectMeta.job_name, ProjectMeta.designer)
        .outerjoin(ProjectMeta, Project.Number == ProjectMeta.project_number)
    )

    # Apply search filter
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            (Project.Number.ilike(pattern))
            | (Project.FileName.ilike(pattern))
            | (ProjectMeta.address.ilike(pattern))
        )

    # Apply software filter
    if software:
        query = query.filter(Project.Software == software)

    rows = query.all()

    # Group by Number
    groups: dict[str, dict] = {}
    for project, address, job_name, designer in rows:
        number = project.Number or ""
        if number not in groups:
            groups[number] = {
                "number": number,
                "address": address,
                "job_name": job_name,
                "designer": designer,
                "files": [],
                "last_run_time": None,
            }
        counts = _file_element_counts(db, project.Id)
        file_obj = ProjectFile(
            id=project.Id,
            file_name=project.FileName,
            file_location=project.FileLocation,
            software=project.Software,
            last_run_time=project.LastRunTime,
            counts=counts,
        )
        groups[number]["files"].append(file_obj)

        # Track latest LastRunTime across files
        if project.LastRunTime:
            current_max = groups[number]["last_run_time"]
            if current_max is None or project.LastRunTime > current_max:
                groups[number]["last_run_time"] = project.LastRunTime

    # Build ProjectGroup objects
    result: list[ProjectGroup] = []
    for g in groups.values():
        file_counts = [f.counts for f in g["files"]]
        total = _aggregate_counts(file_counts)
        result.append(ProjectGroup(
            number=g["number"],
            address=g["address"],
            job_name=g["job_name"],
            designer=g["designer"],
            file_count=len(g["files"]),
            last_run_time=g["last_run_time"],
            counts=total,
            files=g["files"],
        ))

    # Sort
    if sort_by == "number":
        result.sort(key=lambda g: g.number)
    elif sort_by == "elements":
        result.sort(key=lambda g: g.counts.total, reverse=True)
    elif sort_by == "levels":
        # Sort by total level count across files — compute on-the-fly
        def _level_count(g: ProjectGroup) -> int:
            return sum(
                db.query(Level).filter(Level.Project_id == f.id).count()
                for f in g.files
            )
        result.sort(key=_level_count, reverse=True)
    else:  # default: last_run_time descending
        result.sort(
            key=lambda g: g.last_run_time or datetime.min,
            reverse=True,
        )

    return result


# ---------------------------------------------------------------------------
# get_project_detail — full detail for a single Number
# ---------------------------------------------------------------------------

def get_project_detail(db: Session, number: str) -> Optional[ProjectDetail]:
    """Get full detail for a project number: metadata + files + levels + counts."""
    meta = (
        db.query(ProjectMeta)
        .filter(ProjectMeta.project_number == number)
        .first()
    )

    files = (
        db.query(Project)
        .filter(Project.Number == number)
        .order_by(Project.FileName)
        .all()
    )

    if not files:
        return None

    file_details: list[ProjectFileDetail] = []
    all_file_counts: list[ElementCounts] = []

    for project in files:
        file_counts = _file_element_counts(db, project.Id)
        all_file_counts.append(file_counts)

        # Get levels ordered by elevation descending (top to bottom)
        levels = (
            db.query(Level)
            .filter(Level.Project_id == project.Id)
            .order_by(Level.Elevation.desc())
            .all()
        )

        level_schemas: list[LevelWithCounts] = []
        for lv in levels:
            lv_counts = _level_element_counts(db, project.Id, lv.id)
            level_schemas.append(LevelWithCounts(
                id=lv.id,
                name=lv.Name or "",
                elevation=lv.Elevation or 0.0,
                story_height=lv.StoryHeight,
                counts=lv_counts,
            ))

        file_details.append(ProjectFileDetail(
            id=project.Id,
            file_name=project.FileName,
            file_location=project.FileLocation,
            software=project.Software,
            last_run_time=project.LastRunTime,
            counts=file_counts,
            levels=level_schemas,
        ))

    return ProjectDetail(
        number=number,
        address=meta.address if meta else None,
        job_name=meta.job_name if meta else None,
        designer=meta.designer if meta else None,
        files=file_details,
        counts=_aggregate_counts(all_file_counts),
    )


# ---------------------------------------------------------------------------
# update_project — write to management.project_meta ONLY
# ---------------------------------------------------------------------------

def update_project(
    db: Session, number: str, data: ProjectUpdate
) -> Optional[ProjectMeta]:
    """Update project metadata in management.project_meta.

    Never writes to dbo.Project.
    """
    meta = (
        db.query(ProjectMeta)
        .filter(ProjectMeta.project_number == number)
        .first()
    )
    if meta is None:
        return None

    update_fields = data.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        setattr(meta, field, value)

    meta.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(meta)
    return meta


# ---------------------------------------------------------------------------
# delete_project — delete all files for a Number + project_meta
# ---------------------------------------------------------------------------

def delete_project(db: Session, number: str) -> bool:
    """Delete all dbo.Project rows for a Number (FK cascades) + project_meta.

    Returns True if something was deleted, False if Number not found.
    """
    files = db.query(Project).filter(Project.Number == number).all()
    if not files:
        return False

    # Delete dbo.Project rows — FK CASCADE handles elements + design
    for f in files:
        db.delete(f)

    # Delete management.project_meta
    meta = (
        db.query(ProjectMeta)
        .filter(ProjectMeta.project_number == number)
        .first()
    )
    if meta:
        db.delete(meta)

    db.commit()
    logger.info("Deleted project number %s (%d files)", number, len(files))
    return True


# ---------------------------------------------------------------------------
# delete_file — delete a single dbo.Project row
# ---------------------------------------------------------------------------

def delete_file(db: Session, file_id: int) -> bool:
    """Delete a single dbo.Project row (FK cascades).

    If it was the last file for that Number, also delete project_meta.
    Returns True if deleted, False if not found.
    """
    project = db.query(Project).filter(Project.Id == file_id).first()
    if project is None:
        return False

    number = project.Number
    db.delete(project)

    # Check if this was the last file for this Number
    remaining = (
        db.query(Project)
        .filter(Project.Number == number, Project.Id != file_id)
        .count()
    )
    if remaining == 0:
        meta = (
            db.query(ProjectMeta)
            .filter(ProjectMeta.project_number == number)
            .first()
        )
        if meta:
            db.delete(meta)
            logger.info(
                "Last file for number %s deleted — also removed project_meta", number
            )

    db.commit()
    logger.info("Deleted file id=%d (number=%s)", file_id, number)
    return True


# ---------------------------------------------------------------------------
# merge_projects — reassign design records from source to target
# ---------------------------------------------------------------------------

# All design tables that FK to dbo.Project.Id
_DESIGN_TABLES_WITH_PROJECT_ID = [
    "design.load_tables",
    "design.load_areas",
    "design.tributary_results",
    "design.load_assignments",
    "design.element_marks",
    "design.element_links",
    "design.rundown",
    "design.rebar",
    "design.design_results",
    "design.etabs_imports",
    "design.audit_log",
]


def merge_projects(
    db: Session, target_number: str, source_number: str
) -> bool:
    """Merge source project into target.

    Reassigns all design records from source file(s) to the first target file,
    then deletes source dbo.Project rows (cascade) + source project_meta.

    Returns True if merge succeeded, False if either number not found.
    """
    target_files = (
        db.query(Project)
        .filter(Project.Number == target_number)
        .order_by(Project.Id)
        .all()
    )
    source_files = (
        db.query(Project)
        .filter(Project.Number == source_number)
        .order_by(Project.Id)
        .all()
    )

    if not target_files or not source_files:
        return False

    target_id = target_files[0].Id
    source_ids = [f.Id for f in source_files]

    # Reassign design records from source project_ids to target
    for table_name in _DESIGN_TABLES_WITH_PROJECT_ID:
        for sid in source_ids:
            db.execute(
                text(
                    f"UPDATE {table_name} SET project_id = :target "
                    f"WHERE project_id = :source"
                ),
                {"target": target_id, "source": sid},
            )

    # Delete source dbo.Project rows (FK cascades will clean up any remaining
    # element records, but design records were already reassigned)
    for f in source_files:
        db.delete(f)

    # Delete source project_meta
    source_meta = (
        db.query(ProjectMeta)
        .filter(ProjectMeta.project_number == source_number)
        .first()
    )
    if source_meta:
        db.delete(source_meta)

    db.commit()
    logger.info(
        "Merged project %s into %s (%d files reassigned)",
        source_number, target_number, len(source_ids),
    )
    return True