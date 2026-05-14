"""Test fixtures and shared configuration.

Resolves file/level IDs dynamically from the live DB so tests survive
DB rebuilds. The TWB file (23219 project) is used as the reference.
"""
import pytest
from unittest.mock import MagicMock

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

engine = create_engine(settings.DATABASE_URL)
TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)


@pytest.fixture
def mock_db() -> MagicMock:
    """Return a mock SQLAlchemy session for unit tests."""
    session = MagicMock(spec=Session)
    return session


def _resolve_twb_ids():
    """Find TWB file ID and two adjacent levels with elements + floors.

    Returns (file_id, level_above_id, level_below_id) where:
      - level_above has floors (slab boundary)
      - level_below has columns and walls
    """
    with Session(engine) as db:
        # Find the TWB file (23219 project, filename contains TWB)
        row = db.execute(text("""
            SELECT Id FROM dbo.Project
            WHERE FileName LIKE '%TWB%' AND Number = '23219'
        """)).first()
        if row is None:
            # Fallback: use first project
            row = db.execute(text("SELECT TOP 1 Id FROM dbo.Project")).first()
        file_id = row[0]

        # Find a level with 12 columns and 17 walls (LEVEL 13_TOWER B equivalent)
        level_below = db.execute(text("""
            SELECT l.id
            FROM dbo.Levels l
            WHERE l.Project_id = :fid
              AND (SELECT COUNT(*) FROM dbo.Columns c WHERE c.Project_id = :fid AND c.BaseConstraint_id = l.id) = 12
              AND (SELECT COUNT(*) FROM dbo.Walls w WHERE w.Project_id = :fid AND w.BaseConstraint_id = l.id) = 17
            ORDER BY l.Elevation DESC
        """), {"fid": file_id}).first()

        # Find the level directly above it (has floors for slab boundary)
        if level_below:
            level_below_id = level_below[0]
            level_above = db.execute(text("""
                SELECT TOP 1 l.id
                FROM dbo.Levels l
                WHERE l.Project_id = :fid
                  AND l.Elevation > (SELECT Elevation FROM dbo.Levels WHERE id = :lid)
                  AND (SELECT COUNT(*) FROM dbo.Floors f WHERE f.Project_id = :fid AND f.Level_id = l.id) > 0
                ORDER BY l.Elevation ASC
            """), {"fid": file_id, "lid": level_below_id}).first()
            level_above_id = level_above[0] if level_above else level_below_id
        else:
            # Fallback: find any two adjacent levels with data
            levels = db.execute(text("""
                SELECT l.id, l.Elevation,
                    (SELECT COUNT(*) FROM dbo.Columns c WHERE c.Project_id = :fid AND c.BaseConstraint_id = l.id) as cols,
                    (SELECT COUNT(*) FROM dbo.Walls w WHERE w.Project_id = :fid AND w.BaseConstraint_id = l.id) as walls,
                    (SELECT COUNT(*) FROM dbo.Floors f WHERE f.Project_id = :fid AND f.Level_id = l.id) as floors
                FROM dbo.Levels l
                WHERE l.Project_id = :fid
                ORDER BY l.Elevation
            """), {"fid": file_id}).fetchall()

            level_below_id = None
            level_above_id = None
            for i, lev in enumerate(levels):
                if lev[2] > 0 and lev[3] > 0:  # has columns and walls
                    level_below_id = lev[0]
                    # Find next level up with floors
                    for j in range(i + 1, len(levels)):
                        if levels[j][4] > 0:
                            level_above_id = levels[j][0]
                            break
                    if level_above_id:
                        break

            if not level_below_id or not level_above_id:
                raise RuntimeError("Could not find suitable test levels in DB")

    return file_id, level_above_id, level_below_id


# Resolve once at import time
TWB_FILE_ID, TWB_LEVEL_ABOVE, TWB_LEVEL_BELOW = _resolve_twb_ids()