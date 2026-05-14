"""Element Identity service — sync from Revit, detect stale elements.

Reads dbo.Columns + dbo.Walls (READ-ONLY) across all files for a project,
parses marks, and upserts into design.element_identity + design.element_marks.

Single sync function replaces populate + reconcile — always detects stale.

Stale handling:
  - If element has rundown_key or etabs_id linked → flag Stale, preserve.
  - If element has NO linked data → auto-delete (safe cleanup).
"""
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.design import ElementIdentity, ElementMark, LevelIdentity
from app.schemas.identity import (
    ElementIdentityRead,
    ElementIdentityUpdate,
    ElementSyncResult,
    ElementStatsResult,
)
from app.services.mark_parser import canonical_mark, detect_mark_error, parse_mark


def _needs_sync(db: Session, project_number: str) -> bool:
    """Check if dbo has changed since last identity sync."""
    last_run = db.execute(text("""
        SELECT MAX(p.LastRunTime)
        FROM dbo.Project p
        WHERE p.Number = :num
    """), {"num": project_number}).scalar()

    last_sync = db.execute(text("""
        SELECT MAX(ei.updated_at)
        FROM design.element_identity ei
        WHERE ei.project_number = :num
    """), {"num": project_number}).scalar()

    if last_sync is None:
        return True
    if last_run is None:
        return False
    return last_run > last_sync


def _has_linked_data(identity: ElementIdentity) -> bool:
    """Return True if this element has rundown or ETABS data linked."""
    return bool(identity.rundown_key) or bool(identity.etabs_id)


def sync_from_revit(db: Session, project_number: str) -> ElementSyncResult:
    """Sync element_identity from dbo.Columns + dbo.Walls.

    1. UNION query across both tables with level name JOIN.
    2. Dedup by guid, prefer non-null mark.
    3. Parse marks, detect type mismatches, link to level_identity.
    4. Upsert: updates existing, inserts new.
    5. Stale detection:
       - Has linked data (rundown_key/etabs_id) → flag Stale, preserve.
       - No linked data → auto-delete (safe cleanup).
    """
    # Query all elements with level names across all files
    rows = db.execute(text("""
        SELECT c.guid, c.Mark, c.BaseConstraint_id, c.Project_id,
               'Column' AS element_type, l.Name AS level_name
        FROM dbo.Columns c
        JOIN dbo.Project p ON c.Project_id = p.Id
        LEFT JOIN dbo.Levels l ON c.BaseConstraint_id = l.id AND l.Project_id = c.Project_id
        WHERE p.Number = :num AND c.guid IS NOT NULL

        UNION ALL

        SELECT w.guid, w.Mark, w.BaseConstraint_id, w.Project_id,
               'Wall' AS element_type, l.Name AS level_name
        FROM dbo.Walls w
        JOIN dbo.Project p ON w.Project_id = p.Id
        LEFT JOIN dbo.Levels l ON w.BaseConstraint_id = l.id AND l.Project_id = w.Project_id
        WHERE p.Number = :num AND w.guid IS NOT NULL
    """), {"num": project_number}).fetchall()

    # Dedup by guid — prefer row with non-null, non-empty mark
    elements: dict[str, tuple] = {}
    for guid, mark, base_id, proj_id, etype, lname in rows:
        if guid not in elements:
            elements[guid] = (guid, mark, base_id, proj_id, etype, lname)
        elif mark and not elements[guid][1]:
            elements[guid] = (guid, mark, base_id, proj_id, etype, lname)

    # Build level_identity lookup: canonical_name → id
    level_lookup: dict[str, int] = {}
    level_rows = (
        db.query(LevelIdentity)
        .filter(LevelIdentity.project_number == project_number)
        .all()
    )
    for lv in level_rows:
        level_lookup[lv.canonical_name] = lv.id

    dbo_guid_set = set(elements.keys())
    now = datetime.now(timezone.utc)
    created = 0
    updated = 0
    mark_errors = 0

    for guid, mark, base_id, proj_id, etype, lname in elements.values():
        parsed = parse_mark(mark)
        has_error = detect_mark_error(parsed, etype)
        canon = canonical_mark(parsed, etype)

        if has_error:
            mark_errors += 1

        # Confidence scoring
        if parsed.parsed_successfully and not has_error:
            confidence = 1.0
        elif parsed.parsed_successfully and has_error:
            confidence = 0.8
        else:
            confidence = 0.5

        # Fallback canonical for unparsed marks
        if not parsed.parsed_successfully:
            type_prefix = "C" if etype == "Column" else "W"
            canon = f"{type_prefix}-UNKNOWN-{guid[:8]}"

        # Link to level_identity
        level_id = level_lookup.get(lname) if lname else None

        # Notes for errors
        notes = None
        if has_error:
            notes = f"{etype} marked as {parsed.type_char}{parsed.element_number} (type corrected)"

        # Upsert element_identity
        existing = (
            db.query(ElementIdentity)
            .filter(
                ElementIdentity.project_number == project_number,
                ElementIdentity.revit_guid == guid,
            )
            .first()
        )
        if existing:
            existing.canonical_mark = canon
            existing.element_type = etype
            existing.level_identity_id = level_id
            existing.match_confidence = confidence
            existing.match_method = "Revit"
            existing.last_resolved = now
            existing.updated_at = now
            if has_error and not existing.notes:
                existing.notes = notes
            updated += 1
        else:
            identity = ElementIdentity(
                project_number=project_number,
                element_type=etype,
                canonical_mark=canon,
                level_identity_id=level_id,
                revit_guid=guid,
                match_confidence=confidence,
                match_method="Revit",
                last_resolved=now,
                notes=notes,
                created_at=now,
                updated_at=now,
            )
            db.add(identity)
            created += 1

        # Upsert element_marks
        existing_mark = (
            db.query(ElementMark)
            .filter(
                ElementMark.project_number == project_number,
                ElementMark.element_guid == guid,
            )
            .first()
        )
        if existing_mark:
            existing_mark.raw_mark = mark or ""
            existing_mark.prefix = parsed.prefix
            existing_mark.type_char = parsed.type_char or ("C" if etype == "Column" else "W")
            existing_mark.element_number = parsed.element_number or ""
            existing_mark.suffix = parsed.suffix
            existing_mark.comments = notes or parsed.comments
            existing_mark.parsed_successfully = parsed.parsed_successfully
            existing_mark.parsed_at = now
        else:
            em = ElementMark(
                project_number=project_number,
                element_guid=guid,
                element_type=etype,
                project_id=proj_id,
                raw_mark=mark or "",
                prefix=parsed.prefix,
                type_char=parsed.type_char or ("C" if etype == "Column" else "W"),
                element_number=parsed.element_number or "",
                suffix=parsed.suffix,
                comments=notes or parsed.comments,
                parsed_successfully=parsed.parsed_successfully,
                level_id=base_id or 0,
                parsed_at=now,
            )
            db.add(em)

    # Stale detection — elements whose guid no longer in dbo
    stale_count = 0
    stale_marks: list[str] = []
    all_identities = (
        db.query(ElementIdentity)
        .filter(ElementIdentity.project_number == project_number)
        .all()
    )
    for identity in all_identities:
        if identity.revit_guid and identity.revit_guid not in dbo_guid_set:
            if _has_linked_data(identity):
                # Preserve — has rundown/ETABS data
                if identity.match_method != "Stale":
                    identity.match_method = "Stale"
                    identity.match_confidence = 0.0
                    identity.updated_at = now
                stale_count += 1
                stale_marks.append(identity.canonical_mark)
            else:
                # Safe to delete — no linked data
                # Also delete associated element_marks
                db.query(ElementMark).filter(
                    ElementMark.project_number == project_number,
                    ElementMark.element_guid == identity.revit_guid,
                ).delete(synchronize_session=False)
                db.delete(identity)

    db.commit()

    all_elements = get_elements(db, project_number)
    return ElementSyncResult(
        synced=True,
        created=created,
        updated=updated,
        stale=stale_count,
        stale_marks=stale_marks,
        mark_errors=mark_errors,
        elements=[ElementIdentityRead.model_validate(e) for e in all_elements],
    )


def auto_sync_if_needed(db: Session, project_number: str) -> ElementSyncResult | None:
    """Auto-sync if dbo has changed since last sync. Returns None if no sync needed."""
    if _needs_sync(db, project_number):
        return sync_from_revit(db, project_number)
    return None


def get_elements(
    db: Session,
    project_number: str,
    element_type: str | None = None,
    search: str | None = None,
) -> list[ElementIdentity]:
    """Get element identity rows with optional type/search filter."""
    query = db.query(ElementIdentity).filter(
        ElementIdentity.project_number == project_number
    )
    if element_type:
        query = query.filter(ElementIdentity.element_type == element_type)
    if search:
        query = query.filter(ElementIdentity.canonical_mark.ilike(f"%{search}%"))
    return query.order_by(ElementIdentity.canonical_mark).all()


def get_element_stats(db: Session, project_number: str) -> ElementStatsResult:
    """Return counts by type, confidence bands, stale, and mark errors."""
    all_rows = (
        db.query(ElementIdentity)
        .filter(ElementIdentity.project_number == project_number)
        .all()
    )

    columns = sum(1 for r in all_rows if r.element_type == "Column")
    walls = sum(1 for r in all_rows if r.element_type == "Wall")
    stale = sum(1 for r in all_rows if r.match_method == "Stale")

    high = sum(1 for r in all_rows if float(r.match_confidence) >= 0.90)
    medium = sum(1 for r in all_rows if 0.50 <= float(r.match_confidence) < 0.90)
    low = sum(1 for r in all_rows if float(r.match_confidence) < 0.50)

    mark_errors = sum(1 for r in all_rows if r.notes and "type corrected" in r.notes)

    return ElementStatsResult(
        total=len(all_rows),
        columns=columns,
        walls=walls,
        by_confidence={"high": high, "medium": medium, "low": low},
        stale=stale,
        mark_errors=mark_errors,
    )


def update_element(
    db: Session,
    project_number: str,
    element_id: int,
    data: ElementIdentityUpdate,
) -> ElementIdentity | None:
    """Update a single element identity row. Returns None if not found."""
    entry = (
        db.query(ElementIdentity)
        .filter(
            ElementIdentity.id == element_id,
            ElementIdentity.project_number == project_number,
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
