"""Tests for Project Management API endpoints.

Uses FastAPI TestClient with the real DB to verify the full stack.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.dependencies import get_db
from app.main import app
from app.models import Project, ProjectMeta


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

engine = create_engine(settings.DATABASE_URL)
TestSession = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture
def db():
    """Yield a test DB session."""
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


# ---------------------------------------------------------------------------
# GET /api/projects — list grouped by Number
# ---------------------------------------------------------------------------

class TestListProjects:
    def test_returns_grouped_projects(self):
        resp = client.get("/api/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1

        # Each group has the expected shape
        group = data[0]
        assert "number" in group
        assert "address" in group
        assert "file_count" in group
        assert "counts" in group
        assert "files" in group
        assert isinstance(group["files"], list)

    def test_project_23219_has_two_files(self):
        """Project 23219 has TWB + PODIUM files."""
        resp = client.get("/api/projects")
        data = resp.json()
        group_23219 = next((g for g in data if g["number"] == "23219"), None)
        assert group_23219 is not None
        assert group_23219["file_count"] == 2
        assert len(group_23219["files"]) == 2

    def test_element_counts_aggregated(self):
        resp = client.get("/api/projects")
        data = resp.json()
        for group in data:
            total = group["counts"]
            file_cols = sum(f["counts"]["columns"] for f in group["files"])
            assert total["columns"] == file_cols

    def test_search_by_number(self):
        resp = client.get("/api/projects", params={"search": "23219"})
        data = resp.json()
        assert len(data) == 1
        assert data[0]["number"] == "23219"

    def test_search_by_filename(self):
        resp = client.get("/api/projects", params={"search": "PODIUM"})
        data = resp.json()
        assert len(data) >= 1
        # The group containing PODIUM should be 23219
        assert any(g["number"] == "23219" for g in data)

    def test_search_no_results(self):
        resp = client.get("/api/projects", params={"search": "NONEXISTENT_99999"})
        data = resp.json()
        assert len(data) == 0

    def test_sort_by_number(self):
        resp = client.get("/api/projects", params={"sort_by": "number"})
        data = resp.json()
        numbers = [g["number"] for g in data]
        assert numbers == sorted(numbers)

    def test_sort_by_elements(self):
        resp = client.get("/api/projects", params={"sort_by": "elements"})
        data = resp.json()
        totals = [
            g["counts"]["columns"] + g["counts"]["walls"] + g["counts"]["beams"]
            + g["counts"]["floors"] + g["counts"]["foundations"]
            for g in data
        ]
        assert totals == sorted(totals, reverse=True)

    def test_software_filter(self):
        resp = client.get("/api/projects", params={"software": "Autodesk Revit 2025"})
        data = resp.json()
        for group in data:
            for f in group["files"]:
                assert f["software"] == "Autodesk Revit 2025"


# ---------------------------------------------------------------------------
# GET /api/projects/{number} — detail
# ---------------------------------------------------------------------------

class TestGetProjectDetail:
    def test_detail_has_files_with_levels(self):
        resp = client.get("/api/projects/23219")
        assert resp.status_code == 200
        data = resp.json()
        assert data["number"] == "23219"
        # address may be NULL for auto-seeded projects
        assert len(data["files"]) == 2

        # Each file has levels
        for f in data["files"]:
            assert "levels" in f
            assert isinstance(f["levels"], list)

    def test_levels_ordered_by_elevation_desc(self):
        resp = client.get("/api/projects/23219")
        data = resp.json()
        # TWB file (Id=1) has 33 levels
        twb = next(f for f in data["files"] if "TWB" in (f["file_name"] or ""))
        elevations = [lv["elevation"] for lv in twb["levels"]]
        assert elevations == sorted(elevations, reverse=True)

    def test_per_level_counts(self):
        resp = client.get("/api/projects/23219")
        data = resp.json()
        twb = next(f for f in data["files"] if "TWB" in (f["file_name"] or ""))
        # Total of per-level columns should match file total
        level_cols = sum(lv["counts"]["columns"] for lv in twb["levels"])
        assert level_cols == twb["counts"]["columns"]

    def test_not_found(self):
        resp = client.get("/api/projects/99999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# PATCH /api/projects/{number} — update metadata
# ---------------------------------------------------------------------------

class TestUpdateProject:
    def test_update_address(self, db):
        # Read original address
        meta = db.query(ProjectMeta).filter(ProjectMeta.project_number == "23219").first()
        original_address = meta.address
        db.close()

        try:
            resp = client.patch(
                "/api/projects/23219",
                json={"address": "Test Address 123"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["address"] == "Test Address 123"
        finally:
            # Restore original address
            client.patch(
                "/api/projects/23219",
                json={"address": original_address},
            )

    def test_update_not_found(self):
        resp = client.patch("/api/projects/99999", json={"address": "test"})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE endpoints — use carefully, rollback via transaction
# ---------------------------------------------------------------------------

class TestDeleteEndpoints:
    def test_delete_project_not_found(self):
        resp = client.delete("/api/projects/99999")
        assert resp.status_code == 404

    def test_delete_file_not_found(self):
        resp = client.delete("/api/projects/files/999999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/projects/{number}/merge
# ---------------------------------------------------------------------------

class TestMerge:
    def test_merge_self_rejected(self):
        resp = client.post(
            "/api/projects/23219/merge",
            json={"source_number": "23219"},
        )
        assert resp.status_code == 400

    def test_merge_not_found(self):
        resp = client.post(
            "/api/projects/23219/merge",
            json={"source_number": "99999"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Health check (regression)
# ---------------------------------------------------------------------------

class TestHealthCheck:
    def test_health(self):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}