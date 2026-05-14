"""Level Identity service — sync from Revit, detect stale levels.

Reads dbo.Levels (READ-ONLY) across all files for a project_number,
deduplicates by name, and upserts into design.level_identity.
Single sync function replaces populate + reconcile — always detects stale.

Stale handling:
  - If a level has rundown_name or etabs_name linked → flag as Stale, preserve.
  - If a level has NO linked data → auto-delete (safe cleanup).
"""
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import Project
from app.models.design import LevelIdentity
from app.schemas.identity import (
    LevelIdentityRead,
    LevelIdentityUpdate,
    LevelSyncResult,
)


def _needs_sync(db: Session, project_number: str) -> bool:
    """Check if dbo has changed since last identity sync.

    Compares MAX(dbo.Project.LastRunTime) vs MAX(level_identity.updated_at).
    Returns True if sync is needed (dbo newer, or no identity rows yet).
    """
    last_run = db.execute(text("""
        SELECT MAX(p.LastRunTime)
        FROM dbo.Project p
        WHERE p.Number = :num
    """), {"num": project_number}).scalar()

    last_sync = db.execute(text("""
        SELECT MAX(li.updated_at)
        FROM design.level_identity li
        WHERE li.project_number = :num
    """), {"num": project_number}).scalar()

    if last_sync is None:
        return True  # Never synced
    if last_run is None:
        return False  # No dbo data
    return last_run > last_sync


def _has_linked_data(identity: LevelIdentity) -> bool:
    """Return True if this level has rundown or ETABS data linked."""
    return bool(identity.rundown_name) or bool(identity.etabs_name)


def sync_from_revit(db: Session, project_number: str) -> LevelSyncResult:
    """Sync level_identity from dbo.Levels — unified populate + stale detection.

    1. Queries distinct level names + elevations across all files.
    2. Upserts: updates existing rows, inserts new ones.
    3. Detects stale: identity rows whose canonical_name no longer in dbo.
       - Has linked data (rundown_name/etabs_name) → flag Stale, preserve.
       - No linked data → auto-delete (safe cleanup).
    4. Never overwrites rundown_name or etabs_name on existing rows.
    """
    # Query distinct level names + max elevation across all files
    rows = db.execute(text("""
        SELECT l.Name, MAX(COALESCE(l.Elevation, 0)) AS Elevation
        FROM dbo.Levels l
        JOIN dbo.Project p ON l.Project_id = p.Id
        WHERE p.Number = :num
        GROUP BY l.Name
        ORDER BY MAX(COALESCE(l.Elevation, 0)) ASC
    """), {"num": project_number}).fetchall()

    dbo_name_set = {r[0] for r in rows}
    now = datetime.now(timezone.utc)
    created = 0
    updated = 0

    for sort_order, (name, elevation) in enumerate(rows, start=1):
        existing = (
            db.query(LevelIdentity)
            .filter(
                LevelIdentity.project_number == project_number,
                LevelIdentity.canonical_name == name,
            )
            .first()
        )
        if existing:
            existing.sort_order = sort_order
            existing.revit_name = name
            existing.revit_elevation_mm = float(elevation) if elevation is not None else None
            existing.match_confidence = 1.0
            existing.match_method = "Revit"
            existing.updated_at = now
            updated += 1
        else:
            row = LevelIdentity(
                project_number=project_number,
                canonical_name=name,
                sort_order=sort_order,
                revit_name=name,
                revit_elevation_mm=float(elevation) if elevation is not None else None,
                match_confidence=1.0,
                match_method="Revit",
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            created += 1

    # Stale detection — levels no longer in dbo
    stale_count = 0
    stale_names: list[str] = []
    deleted_count = 0
    all_identities = (
        db.query(LevelIdentity)
        .filter(LevelIdentity.project_number == project_number)
        .all()
    )
    for identity in all_identities:
        if identity.canonical_name not in dbo_name_set:
            if _has_linked_data(identity):
                # Preserve — has rundown/ETABS data
                if identity.match_method != "Stale":
                    identity.match_method = "Stale"
                    identity.match_confidence = 0.0
                    identity.updated_at = now
                stale_count += 1
                stale_names.append(identity.canonical_name)
            else:
                # Safe to delete — no linked data
                # Nullify FK references from element_identity first
                db.execute(
                    text("""
                        UPDATE design.element_identity
                        SET level_identity_id = NULL
                        WHERE level_identity_id = :lid
                    """),
                    {"lid": identity.id},
                )
                db.delete(identity)
                deleted_count += 1

    db.commit()

    levels = get_levels(db, project_number)
    return LevelSyncResult(
        synced=True,
        created=created,
        updated=updated,
        stale=stale_count,
        stale_names=stale_names,
        levels=[LevelIdentityRead.model_validate(lv) for lv in levels],
    )


def auto_sync_if_needed(db: Session, project_number: str) -> LevelSyncResult | None:
    """Auto-sync if dbo has changed since last sync. Returns None if no sync needed."""
    if _needs_sync(db, project_number):
        return sync_from_revit(db, project_number)
    return None


def get_levels(db: Session, project_number: str) -> list[LevelIdentity]:
    """Get all level identity rows for a project, ordered by sort_order."""
    return (
        db.query(LevelIdentity)
        .filter(LevelIdentity.project_number == project_number)
        .order_by(LevelIdentity.sort_order)
        .all()
    )


def update_level(
    db: Session,
    project_number: str,
    level_id: int,
    data: LevelIdentityUpdate,
) -> LevelIdentity | None:
    """Update a single level identity row. Returns None if not found."""
    entry = (
        db.query(LevelIdentity)
        .filter(
            LevelIdentity.id == level_id,
            LevelIdentity.project_number == project_number,
        )
        .first()
    )
    if entry is None:
        return None

    update_fields = data.model_dump(exclude_unset=True)
    for field, value in update_fields.items():
        setattr(entry, field, value)

    entry.match_method = "Manual"
    entry.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(entry)
    return entry