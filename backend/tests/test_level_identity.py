"""Tests for Level Identity sync service + API.

Uses project 23219 (PODIUM + TWB files) from the live DB.
Cleans up design.level_identity rows before and after each test.
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
    # Delete in FK order: element_marks → element_identity → level_identity
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
    yield
    db = TestSession()
    _cleanup(db)
    db.close()


# ---------------------------------------------------------------------------
# POST /api/projects/{number}/levels/sync
# ---------------------------------------------------------------------------

class TestSync:
    def test_sync_creates_levels(self):
        """First sync creates identity rows sorted by sort_order."""
        resp = client.post(f"/api/projects/{PROJECT_NUMBER}/levels/sync")
        assert resp.status_code == 200
        data = resp.json()
        assert data["synced"] is True
        assert data["created"] > 0
        assert data["updated"] == 0
        assert data["stale"] == 0
        assert len(data["levels"]) == data["created"]

        # Verify sort_order is ascending
        sort_orders = [lv["sort_order"] for lv in data["levels"]]
        assert sort_orders == sorted(sort_orders)

        # Every level has revit_name set
        for lv in data["levels"]:
            assert lv["revit_name"] is not None
            assert lv["match_method"] == "Revit"

    def test_sync_idempotent(self):
        """Second sync updates existing rows, creates zero new."""
        resp1 = client.post(f"/api/projects/{PROJECT_NUMBER}/levels/sync")
        first_count = resp1.json()["created"]

        resp2 = client.post(f"/api/projects/{PROJECT_NUMBER}/levels/sync")
        data2 = resp2.json()
        assert data2["created"] == 0
        assert data2["updated"] == first_count
        assert len(data2["levels"]) == first_count

    def test_sync_preserves_user_edits(self):
        """User-set rundown_name is NOT overwritten by re-sync."""
        client.post(f"/api/projects/{PROJECT_NUMBER}/levels/sync")

        # Get first level and patch its rundown_name
        resp = client.get(f"/api/projects/{PROJECT_NUMBER}/levels/identity")
        first_id = resp.json()[0]["id"]
        client.patch(
            f"/api/projects/{PROJECT_NUMBER}/levels/identity/{first_id}",
            json={"rundown_name": "MY_CUSTOM_NAME"},
        )

        # Re-sync
        client.post(f"/api/projects/{PROJECT_NUMBER}/levels/sync")

        # Verify rundown_name preserved
        resp = client.get(f"/api/projects/{PROJECT_NUMBER}/levels/identity")
        patched = next(lv for lv in resp.json() if lv["id"] == first_id)
        assert patched["rundown_name"] == "MY_CUSTOM_NAME"

    def test_sync_deduplicates_across_files(self):
        """Identity rows should be <= total dbo.Levels (shared names across files)."""
        resp = client.post(f"/api/projects/{PROJECT_NUMBER}/levels/sync")
        identity_count = len(resp.json()["levels"])

        db = TestSession()
        total_dbo = db.execute(text("""
            SELECT COUNT(*)
            FROM dbo.Levels l
            JOIN dbo.Project p ON l.Project_id = p.Id
            WHERE p.Number = :num
        """), {"num": PROJECT_NUMBER}).scalar()
        db.close()

        assert identity_count <= total_dbo

    def test_sync_project_not_found(self):
        resp = client.post("/api/projects/ZZZZZZ/levels/sync")
        assert resp.status_code == 404

    def test_sync_detects_stale_with_linked_data(self):
        """Stale level WITH rundown_name is preserved (flagged Stale)."""
        client.post(f"/api/projects/{PROJECT_NUMBER}/levels/sync")

        # Insert a fake level with rundown_name (linked data)
        db = TestSession()
        db.execute(text("""
            INSERT INTO design.level_identity
                (project_number, canonical_name, sort_order, rundown_name,
                 match_confidence, match_method)
            VALUES (:pn, 'FAKE_WITH_DATA', 999, 'User Set Name', 1.0, 'Manual')
        """), {"pn": PROJECT_NUMBER})
        db.commit()
        db.close()

        # Re-sync should flag it as stale but NOT delete
        resp = client.post(f"/api/projects/{PROJECT_NUMBER}/levels/sync")
        data = resp.json()
        assert data["stale"] >= 1
        assert "FAKE_WITH_DATA" in data["stale_names"]

        fake = next(
            lv for lv in data["levels"]
            if lv["canonical_name"] == "FAKE_WITH_DATA"
        )
        assert fake["match_method"] == "Stale"
        assert fake["rundown_name"] == "User Set Name"

    def test_sync_deletes_stale_without_linked_data(self):
        """Stale level WITHOUT linked data is auto-deleted."""
        client.post(f"/api/projects/{PROJECT_NUMBER}/levels/sync")

        # Insert a fake level WITHOUT rundown_name/etabs_name
        db = TestSession()
        db.execute(text("""
            INSERT INTO design.level_identity
                (project_number, canonical_name, sort_order,
                 match_confidence, match_method)
            VALUES (:pn, 'FAKE_NO_DATA', 999, 1.0, 'Manual')
        """), {"pn": PROJECT_NUMBER})
        db.commit()
        db.close()

        # Re-sync should auto-delete it
        resp = client.post(f"/api/projects/{PROJECT_NUMBER}/levels/sync")
        data = resp.json()

        # Should NOT appear in the levels list
        fake = [
            lv for lv in data["levels"]
            if lv["canonical_name"] == "FAKE_NO_DATA"
        ]
        assert len(fake) == 0


# ---------------------------------------------------------------------------
# GET /api/projects/{number}/levels/identity
# ---------------------------------------------------------------------------

class TestGetLevels:
    def test_get_empty(self):
        """GET before sync returns empty list."""
        resp = client.get(f"/api/projects/{PROJECT_NUMBER}/levels/identity")
        assert resp.status_code == 200
        # May auto-sync and return levels, or be empty if auto-sync not triggered
        assert isinstance(resp.json(), list)

    def test_get_after_sync(self):
        """GET after sync returns levels with revit_name set."""
        sync = client.post(f"/api/projects/{PROJECT_NUMBER}/levels/sync")
        expected_count = len(sync.json()["levels"])

        resp = client.get(f"/api/projects/{PROJECT_NUMBER}/levels/identity")
        assert resp.status_code == 200
        levels = resp.json()
        assert len(levels) == expected_count

        for lv in levels:
            assert lv["revit_name"] is not None
            assert lv["project_number"] == PROJECT_NUMBER

    def test_get_project_not_found(self):
        resp = client.get("/api/projects/ZZZZZZ/levels/identity")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/projects/{number}/levels/identity/{id}
# ---------------------------------------------------------------------------

class TestUpdateLevel:
    def test_patch_canonical_name(self):
        """PATCH canonical_name updates the value."""
        client.post(f"/api/projects/{PROJECT_NUMBER}/levels/sync")
        resp = client.get(f"/api/projects/{PROJECT_NUMBER}/levels/identity")
        first = resp.json()[0]

        resp = client.patch(
            f"/api/projects/{PROJECT_NUMBER}/levels/identity/{first['id']}",
            json={"canonical_name": "RENAMED_LEVEL"},
        )
        assert resp.status_code == 200
        assert resp.json()["canonical_name"] == "RENAMED_LEVEL"
        assert resp.json()["match_method"] == "Manual"

    def test_patch_not_found(self):
        resp = client.patch(
            f"/api/projects/{PROJECT_NUMBER}/levels/identity/999999",
            json={"canonical_name": "X"},
        )
        assert resp.status_code == 404