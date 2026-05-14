"""Integration tests for Phase 2 identity hub tables.

Tests INSERT/SELECT/DELETE on design.level_identity, design.element_identity,
and design.rundown_uploads against live JAPBIMDB.

Uses explicit cleanup (DELETE WHERE project_number='99999') instead of rollback
to avoid holding DB locks that block other test files.
"""
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.config import settings
from app.models import LevelIdentity, ElementIdentity, RundownUpload


TEST_PROJECT = "99999"

engine = create_engine(settings.DATABASE_URL)


def _cleanup(session: Session):
    """Delete all test data for project 99999 (respects FK order)."""
    session.execute(
        text("DELETE FROM design.rundown_uploads WHERE project_number = :pn"),
        {"pn": TEST_PROJECT},
    )
    session.execute(
        text("DELETE FROM design.element_identity WHERE project_number = :pn"),
        {"pn": TEST_PROJECT},
    )
    session.execute(
        text("DELETE FROM design.level_identity WHERE project_number = :pn"),
        {"pn": TEST_PROJECT},
    )
    session.commit()


def _ensure_project_meta(session: Session):
    """Ensure management.project_meta has a row for TEST_PROJECT (FK target)."""
    exists = session.execute(
        text("SELECT 1 FROM management.project_meta WHERE project_number = :pn"),
        {"pn": TEST_PROJECT},
    ).first()
    if not exists:
        session.execute(
            text("INSERT INTO management.project_meta (project_number) VALUES (:pn)"),
            {"pn": TEST_PROJECT},
        )
        session.commit()


@pytest.fixture
def db():
    """Live DB session with explicit cleanup before and after each test."""
    with Session(engine) as session:
        _ensure_project_meta(session)
        _cleanup(session)
        yield session
        _cleanup(session)


# ---------------------------------------------------------------------------
# design.level_identity
# ---------------------------------------------------------------------------

def test_level_identity_insert_and_query(db: Session):
    """Insert a level_identity row and read it back."""
    row = LevelIdentity(
        project_number=TEST_PROJECT,
        canonical_name="Level 5",
        sort_order=5,
        revit_name="Level 5",
        rundown_name="5",
        revit_elevation_mm=15000.0,
        match_confidence=0.95,
        match_method="Auto_Exact",
    )
    db.add(row)
    db.commit()

    assert row.id is not None
    assert row.id > 0

    queried = db.query(LevelIdentity).filter(
        LevelIdentity.id == row.id
    ).first()
    assert queried is not None
    assert queried.project_number == TEST_PROJECT
    assert queried.canonical_name == "Level 5"
    assert queried.sort_order == 5
    assert queried.revit_name == "Level 5"
    assert queried.rundown_name == "5"
    assert queried.etabs_name is None  # nullable
    assert float(queried.match_confidence) == 0.95
    assert queried.match_method == "Auto_Exact"


def test_level_identity_unique_constraint(db: Session):
    """Duplicate (project_number, canonical_name) should fail."""
    row1 = LevelIdentity(
        project_number=TEST_PROJECT,
        canonical_name="Level 1",
        sort_order=1,
        match_confidence=1.0,
        match_method="Manual",
    )
    db.add(row1)
    db.commit()

    row2 = LevelIdentity(
        project_number=TEST_PROJECT,
        canonical_name="Level 1",
        sort_order=1,
        match_confidence=1.0,
        match_method="Manual",
    )
    db.add(row2)
    with pytest.raises(Exception):
        db.commit()
    db.rollback()  # reset session state after expected error


# ---------------------------------------------------------------------------
# design.element_identity
# ---------------------------------------------------------------------------

def test_element_identity_insert_and_query(db: Session):
    """Insert an element_identity row with level FK and read it back."""
    level = LevelIdentity(
        project_number=TEST_PROJECT,
        canonical_name="Level 10",
        sort_order=10,
        match_confidence=1.0,
        match_method="Manual",
    )
    db.add(level)
    db.commit()

    elem = ElementIdentity(
        project_number=TEST_PROJECT,
        element_type="Column",
        canonical_mark="C12",
        level_identity_id=level.id,
        revit_guid="abc-def-123",
        match_confidence=0.92,
        match_method="Auto_Mark",
    )
    db.add(elem)
    db.commit()

    assert elem.id is not None
    queried = db.query(ElementIdentity).filter(
        ElementIdentity.id == elem.id
    ).first()
    assert queried.element_type == "Column"
    assert queried.canonical_mark == "C12"
    assert queried.revit_guid == "abc-def-123"
    assert queried.rundown_key is None
    assert queried.etabs_id is None
    assert float(queried.match_confidence) == 0.92


def test_element_identity_no_dbo_fk(db: Session):
    """element_identity has NO FK to dbo tables — just stores revit_guid as a string."""
    elem = ElementIdentity(
        project_number=TEST_PROJECT,
        element_type="Wall",
        canonical_mark="W5",
        revit_guid="nonexistent-guid-that-doesnt-exist-in-dbo",
        match_confidence=1.0,
        match_method="Manual",
    )
    db.add(elem)
    db.commit()  # Should NOT fail — no FK to dbo

    assert elem.id is not None


# ---------------------------------------------------------------------------
# design.rundown_uploads
# ---------------------------------------------------------------------------

def test_rundown_upload_insert_and_query(db: Session):
    """Insert a rundown_uploads row and read it back."""
    batch_id = uuid.uuid4()
    row = RundownUpload(
        project_number=TEST_PROJECT,
        upload_batch_id=batch_id,
        row_number=1,
        raw_mark="C12",
        raw_level="5",
        dead_kn=150.5,
        live_kn=45.2,
        match_status="Unmatched",
    )
    db.add(row)
    db.commit()

    assert row.id is not None
    queried = db.query(RundownUpload).filter(
        RundownUpload.id == row.id
    ).first()
    assert queried.project_number == TEST_PROJECT
    assert queried.upload_batch_id == batch_id
    assert queried.raw_mark == "C12"
    assert queried.raw_level == "5"
    assert float(queried.dead_kn) == 150.5
    assert float(queried.live_kn) == 45.2
    assert queried.match_status == "Unmatched"
    assert queried.element_identity_id is None


def test_rundown_upload_with_identity_fk(db: Session):
    """rundown_uploads can FK to element_identity and level_identity."""
    level = LevelIdentity(
        project_number=TEST_PROJECT,
        canonical_name="Level 5",
        sort_order=5,
        match_confidence=1.0,
        match_method="Manual",
    )
    db.add(level)
    db.commit()

    elem = ElementIdentity(
        project_number=TEST_PROJECT,
        element_type="Column",
        canonical_mark="C12",
        level_identity_id=level.id,
        match_confidence=1.0,
        match_method="Manual",
    )
    db.add(elem)
    db.commit()

    batch_id = uuid.uuid4()
    upload = RundownUpload(
        project_number=TEST_PROJECT,
        upload_batch_id=batch_id,
        row_number=1,
        raw_mark="C12",
        raw_level="5",
        dead_kn=200.0,
        live_kn=60.0,
        element_identity_id=elem.id,
        level_identity_id=level.id,
        match_status="Matched",
    )
    db.add(upload)
    db.commit()

    queried = db.query(RundownUpload).filter(
        RundownUpload.id == upload.id
    ).first()
    assert queried.element_identity_id == elem.id
    assert queried.level_identity_id == level.id
    assert queried.match_status == "Matched"


def test_rundown_upload_batch_query(db: Session):
    """Multiple rows with same batch_id can be queried together."""
    batch_id = uuid.uuid4()
    for i in range(5):
        db.add(RundownUpload(
            project_number=TEST_PROJECT,
            upload_batch_id=batch_id,
            row_number=i + 1,
            raw_mark=f"C{i + 1}",
            raw_level="5",
            dead_kn=100.0 + i * 10,
            live_kn=30.0 + i * 5,
        ))
    db.commit()

    rows = db.query(RundownUpload).filter(
        RundownUpload.upload_batch_id == batch_id
    ).order_by(RundownUpload.row_number).all()
    assert len(rows) == 5
    assert rows[0].raw_mark == "C1"
    assert rows[4].raw_mark == "C5"
