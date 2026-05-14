"""Tests for Element Identity sync service + API.

Uses project 23219 (PODIUM + TWB files) from the live DB.
Cleans up design.element_identity and design.element_marks before/after.
Pre-syncs level_identity (required for level linking).
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.dependencies import get_db
from app.main import app
from tests.conftest import TestSession

PROJECT_NUMBER = "23219"


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def _cleanup(db):
    db.execute(
        text("DELETE FROM design.element_marks WHERE project_number = :pn"),
        {"pn": PROJECT_NUMBER},
    )
    db.execute(
        text("DELETE FROM design.element_identity WHERE project_number = :pn"),
        {"pn": PROJECT_NUMBER},
    )
    db.execute(
        text("DELETE FROM design.level_identity WHERE project_number = :pn"),
        {"pn": PROJECT_NUMBER},
    )
    db.commit()


@pytest.fixture(autouse=True)
def cleanup():
    db = TestSession()
    _cleanup(db)
    db.close()
    # Pre-sync level_identity (element identity links to it)
    client.post(f"/api/projects/{PROJECT_NUMBER}/levels/sync")
    yield
    db = TestSession()
    _cleanup(db)
    db.close()


# ---------------------------------------------------------------------------
# POST /api/projects/{number}/elements/sync
# ---------------------------------------------------------------------------

class TestElementSync:
    def test_sync_creates_elements(self):
        resp = client.post(f"/api/projects/{PROJECT_NUMBER}/elements/sync")
        assert resp.status_code == 200
        data = resp.json()
        assert data["synced"] is True
        assert data["created"] > 0
        assert data["updated"] == 0
        assert data["stale"] == 0
        assert len(data["elements"]) == data["created"]

        for elem in data["elements"]:
            assert elem["element_type"] in ("Column", "Wall")
            assert elem["canonical_mark"]
            assert elem["revit_guid"]

    def test_sync_idempotent(self):
        resp1 = client.post(f"/api/projects/{PROJECT_NUMBER}/elements/sync")
        first_count = resp1.json()["created"]

        resp2 = client.post(f"/api/projects/{PROJECT_NUMBER}/elements/sync")
        data2 = resp2.json()
        assert data2["created"] == 0
        assert data2["updated"] == first_count
        assert len(data2["elements"]) == first_count

    def test_sync_deduplicates_across_files(self):
        """Identity count should be <= total dbo elements across files."""
        resp = client.post(f"/api/projects/{PROJECT_NUMBER}/elements/sync")
        identity_count = len(resp.json()["elements"])

        db = TestSession()
        total_dbo = db.execute(text("""
            SELECT
                (SELECT COUNT(*) FROM dbo.Columns c
                 JOIN dbo.Project p ON c.Project_id = p.Id
                 WHERE p.Number = :num AND c.guid IS NOT NULL)
                +
                (SELECT COUNT(*) FROM dbo.Walls w
                 JOIN dbo.Project p ON w.Project_id = p.Id
                 WHERE p.Number = :num AND w.guid IS NOT NULL)
        """), {"num": PROJECT_NUMBER}).scalar()
        db.close()

        assert identity_count <= total_dbo

    def test_sync_creates_marks(self):
        """Element marks should be created matching identity count."""
        client.post(f"/api/projects/{PROJECT_NUMBER}/elements/sync")

        db = TestSession()
        mark_count = db.execute(
            text("SELECT COUNT(*) FROM design.element_marks WHERE project_number = :pn"),
            {"pn": PROJECT_NUMBER},
        ).scalar()
        identity_count = db.execute(
            text("SELECT COUNT(*) FROM design.element_identity WHERE project_number = :pn"),
            {"pn": PROJECT_NUMBER},
        ).scalar()
        db.close()

        assert mark_count == identity_count

    def test_sync_links_to_level_identity(self):
        """At least some elements should have level_identity_id set."""
        resp = client.post(f"/api/projects/{PROJECT_NUMBER}/elements/sync")
        elements = resp.json()["elements"]
        linked = [e for e in elements if e["level_identity_id"] is not None]
        assert len(linked) > 0

    def test_sync_project_not_found(self):
        resp = client.post("/api/projects/ZZZZZZ/elements/sync")
        assert resp.status_code == 404

    def test_sync_detects_stale_with_linked_data(self):
        """Fake element WITH rundown_key is preserved (flagged Stale)."""
        client.post(f"/api/projects/{PROJECT_NUMBER}/elements/sync")

        db = TestSession()
        db.execute(text("""
            INSERT INTO design.element_identity
                (project_number, element_type, canonical_mark, revit_guid,
                 rundown_key, match_confidence, match_method)
            VALUES (:pn, 'Column', 'C999', 'fake-guid-does-not-exist',
                    'C999-linked', 1.0, 'Manual')
        """), {"pn": PROJECT_NUMBER})
        db.commit()
        db.close()

        resp = client.post(f"/api/projects/{PROJECT_NUMBER}/elements/sync")
        assert resp.status_code == 200
        data = resp.json()
        assert data["stale"] >= 1
        assert "C999" in data["stale_marks"]

        stale = [e for e in data["elements"] if e["revit_guid"] == "fake-guid-does-not-exist"]
        assert len(stale) == 1
        assert stale[0]["match_method"] == "Stale"
        assert stale[0]["rundown_key"] == "C999-linked"

    def test_sync_deletes_stale_without_linked_data(self):
        """Fake element WITHOUT linked data is auto-deleted."""
        client.post(f"/api/projects/{PROJECT_NUMBER}/elements/sync")

        db = TestSession()
        db.execute(text("""
            INSERT INTO design.element_identity
                (project_number, element_type, canonical_mark, revit_guid,
                 match_confidence, match_method)
            VALUES (:pn, 'Column', 'C888', 'fake-guid-no-links',
                    1.0, 'Manual')
        """), {"pn": PROJECT_NUMBER})
        db.commit()
        db.close()

        resp = client.post(f"/api/projects/{PROJECT_NUMBER}/elements/sync")
        data = resp.json()

        # Should NOT appear in the elements list
        fake = [e for e in data["elements"] if e["revit_guid"] == "fake-guid-no-links"]
        assert len(fake) == 0


# ---------------------------------------------------------------------------
# GET /api/projects/{number}/elements/identity
# ---------------------------------------------------------------------------

class TestGetElements:
    def test_get_with_type_filter(self):
        client.post(f"/api/projects/{PROJECT_NUMBER}/elements/sync")

        resp = client.get(f"/api/projects/{PROJECT_NUMBER}/elements/identity?type=Column")
        assert resp.status_code == 200
        elements = resp.json()
        assert len(elements) > 0
        assert all(e["element_type"] == "Column" for e in elements)

    def test_get_with_search(self):
        client.post(f"/api/projects/{PROJECT_NUMBER}/elements/sync")

        resp = client.get(f"/api/projects/{PROJECT_NUMBER}/elements/identity?search=C10")
        assert resp.status_code == 200
        elements = resp.json()
        assert len(elements) > 0
        assert all("C10" in e["canonical_mark"].upper() for e in elements)


# ---------------------------------------------------------------------------
# PATCH /api/projects/{number}/elements/identity/{id}
# ---------------------------------------------------------------------------

class TestUpdateElement:
    def test_patch_canonical_mark(self):
        client.post(f"/api/projects/{PROJECT_NUMBER}/elements/sync")

        resp = client.get(f"/api/projects/{PROJECT_NUMBER}/elements/identity")
        first = resp.json()[0]

        resp = client.patch(
            f"/api/projects/{PROJECT_NUMBER}/elements/identity/{first['id']}",
            json={"canonical_mark": "CUSTOM_MARK"},
        )
        assert resp.status_code == 200
        assert resp.json()["canonical_mark"] == "CUSTOM_MARK"
        assert resp.json()["match_method"] == "Manual"


# ---------------------------------------------------------------------------
# GET /api/projects/{number}/elements/identity/stats
# ---------------------------------------------------------------------------

class TestElementStats:
    def test_stats_after_sync(self):
        resp = client.post(f"/api/projects/{PROJECT_NUMBER}/elements/sync")
        total = len(resp.json()["elements"])
        cols = sum(1 for e in resp.json()["elements"] if e["element_type"] == "Column")
        walls = sum(1 for e in resp.json()["elements"] if e["element_type"] == "Wall")

        resp = client.get(f"/api/projects/{PROJECT_NUMBER}/elements/identity/stats")
        assert resp.status_code == 200
        stats = resp.json()
        assert stats["total"] == total
        assert stats["columns"] == cols
        assert stats["walls"] == walls
        assert "high" in stats["by_confidence"]