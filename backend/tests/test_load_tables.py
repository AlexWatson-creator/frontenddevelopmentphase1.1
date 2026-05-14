"""Tests for Load Table CRUD API.

Tests against the live DB using a real dbo.Project file.
Cleans up after itself — all created load_table entries are deleted.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.dependencies import get_db
from app.main import app
from app.models import LoadTable

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

# Use file id=1 (TWB) for all tests — known to exist
FILE_ID = 1

# Standard load types from the spec
STANDARD_ENTRIES = [
    {"name": "RES", "description": "Residential", "dead_load_kpa": 6.1, "live_load_kpa": 1.9, "llrf_type": "R0.3"},
    {"name": "BALC", "description": "Balcony", "dead_load_kpa": 5.3, "live_load_kpa": 4.8, "llrf_type": "R0.3"},
    {"name": "MEC", "description": "Mechanical", "dead_load_kpa": 9.26, "live_load_kpa": 7.2, "llrf_type": "N"},
    {"name": "ROOF", "description": "Roof", "dead_load_kpa": 7.275, "live_load_kpa": 2.35, "llrf_type": "N"},
]


@pytest.fixture(autouse=True)
def cleanup():
    """Ensure load_table is clean before and after each test."""
    db = TestSession()
    db.query(LoadTable).filter(LoadTable.project_id == FILE_ID).delete()
    db.commit()
    db.close()
    yield
    db = TestSession()
    db.query(LoadTable).filter(LoadTable.project_id == FILE_ID).delete()
    db.commit()
    db.close()


# ---------------------------------------------------------------------------
# GET /api/projects/files/{id}/load-table
# ---------------------------------------------------------------------------

class TestGetLoadTable:
    def test_empty_table(self):
        resp = client.get(f"/api/projects/files/{FILE_ID}/load-table")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_file_not_found(self):
        resp = client.get("/api/projects/files/999999/load-table")
        assert resp.status_code == 404

    def test_returns_entries_after_create(self):
        # Create entries first
        client.post(f"/api/projects/files/{FILE_ID}/load-table", json=STANDARD_ENTRIES)
        resp = client.get(f"/api/projects/files/{FILE_ID}/load-table")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 4
        # Ordered by name alphabetically
        names = [e["name"] for e in data]
        assert names == sorted(names)


# ---------------------------------------------------------------------------
# POST /api/projects/files/{id}/load-table — bulk create/replace
# ---------------------------------------------------------------------------

class TestBulkReplace:
    def test_create_standard_entries(self):
        resp = client.post(
            f"/api/projects/files/{FILE_ID}/load-table",
            json=STANDARD_ENTRIES,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert len(data) == 4

        # Verify each entry
        by_name = {e["name"]: e for e in data}
        assert by_name["RES"]["dead_load_kpa"] == "6.1000"
        assert by_name["RES"]["live_load_kpa"] == "1.9000"
        assert by_name["RES"]["llrf_type"] == "R0.3"
        assert by_name["BALC"]["dead_load_kpa"] == "5.3000"
        assert by_name["MEC"]["live_load_kpa"] == "7.2000"
        assert by_name["MEC"]["llrf_type"] == "N"
        assert by_name["ROOF"]["dead_load_kpa"] == "7.2750"

    def test_replace_clears_old_entries(self):
        # Create initial entries
        client.post(f"/api/projects/files/{FILE_ID}/load-table", json=STANDARD_ENTRIES)

        # Replace with fewer entries
        new_entries = [
            {"name": "CUSTOM", "description": "Custom load", "dead_load_kpa": 10.0, "live_load_kpa": 5.0},
        ]
        resp = client.post(f"/api/projects/files/{FILE_ID}/load-table", json=new_entries)
        assert resp.status_code == 201
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "CUSTOM"

        # Confirm old entries are gone
        resp = client.get(f"/api/projects/files/{FILE_ID}/load-table")
        assert len(resp.json()) == 1

    def test_empty_array_rejected(self):
        resp = client.post(f"/api/projects/files/{FILE_ID}/load-table", json=[])
        assert resp.status_code == 400

    def test_duplicate_names_rejected(self):
        dupes = [
            {"name": "RES", "dead_load_kpa": 6.1, "live_load_kpa": 1.9},
            {"name": "RES", "dead_load_kpa": 7.0, "live_load_kpa": 2.0},
        ]
        resp = client.post(f"/api/projects/files/{FILE_ID}/load-table", json=dupes)
        assert resp.status_code == 400

    def test_file_not_found(self):
        resp = client.post("/api/projects/files/999999/load-table", json=STANDARD_ENTRIES)
        assert resp.status_code == 404

    def test_default_llrf_type(self):
        """llrf_type defaults to 'N' when not specified."""
        entries = [{"name": "TEST", "dead_load_kpa": 5.0, "live_load_kpa": 2.0}]
        resp = client.post(f"/api/projects/files/{FILE_ID}/load-table", json=entries)
        assert resp.status_code == 201
        assert resp.json()[0]["llrf_type"] == "N"

    def test_created_by_populated(self):
        entries = [{"name": "TEST", "dead_load_kpa": 5.0, "live_load_kpa": 2.0}]
        resp = client.post(f"/api/projects/files/{FILE_ID}/load-table", json=entries)
        assert resp.status_code == 201
        assert resp.json()[0]["created_by"] == "system"


# ---------------------------------------------------------------------------
# PATCH /api/projects/files/{id}/load-table/{entry_id}
# ---------------------------------------------------------------------------

class TestUpdateEntry:
    def test_update_single_field(self):
        # Create an entry
        resp = client.post(
            f"/api/projects/files/{FILE_ID}/load-table",
            json=[{"name": "RES", "dead_load_kpa": 6.1, "live_load_kpa": 1.9, "llrf_type": "R0.3"}],
        )
        entry_id = resp.json()[0]["id"]

        # Update dead_load_kpa
        resp = client.patch(
            f"/api/projects/files/{FILE_ID}/load-table/{entry_id}",
            json={"dead_load_kpa": 7.5},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["dead_load_kpa"] == "7.5000"
        # Other fields unchanged
        assert data["live_load_kpa"] == "1.9000"
        assert data["llrf_type"] == "R0.3"

    def test_update_multiple_fields(self):
        resp = client.post(
            f"/api/projects/files/{FILE_ID}/load-table",
            json=[{"name": "BALC", "dead_load_kpa": 5.3, "live_load_kpa": 4.8}],
        )
        entry_id = resp.json()[0]["id"]

        resp = client.patch(
            f"/api/projects/files/{FILE_ID}/load-table/{entry_id}",
            json={"dead_load_kpa": 6.0, "live_load_kpa": 5.0, "description": "Updated balcony"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["dead_load_kpa"] == "6.0000"
        assert data["live_load_kpa"] == "5.0000"
        assert data["description"] == "Updated balcony"

    def test_entry_not_found(self):
        resp = client.patch(
            f"/api/projects/files/{FILE_ID}/load-table/999999",
            json={"dead_load_kpa": 1.0},
        )
        assert resp.status_code == 404

    def test_wrong_file_id(self):
        """Entry exists but belongs to a different file."""
        resp = client.post(
            f"/api/projects/files/{FILE_ID}/load-table",
            json=[{"name": "RES", "dead_load_kpa": 6.1, "live_load_kpa": 1.9}],
        )
        entry_id = resp.json()[0]["id"]

        # Try to update via wrong file_id
        resp = client.patch(
            f"/api/projects/files/999999/load-table/{entry_id}",
            json={"dead_load_kpa": 7.0},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/projects/files/{id}/load-table/{entry_id}
# ---------------------------------------------------------------------------

class TestDeleteEntry:
    def test_delete_single_entry(self):
        # Create 2 entries
        resp = client.post(
            f"/api/projects/files/{FILE_ID}/load-table",
            json=[
                {"name": "RES", "dead_load_kpa": 6.1, "live_load_kpa": 1.9},
                {"name": "BALC", "dead_load_kpa": 5.3, "live_load_kpa": 4.8},
            ],
        )
        entries = resp.json()
        res_id = next(e["id"] for e in entries if e["name"] == "RES")

        # Delete RES
        resp = client.delete(f"/api/projects/files/{FILE_ID}/load-table/{res_id}")
        assert resp.status_code == 204

        # Confirm only BALC remains
        resp = client.get(f"/api/projects/files/{FILE_ID}/load-table")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "BALC"

    def test_entry_not_found(self):
        resp = client.delete(f"/api/projects/files/{FILE_ID}/load-table/999999")
        assert resp.status_code == 404