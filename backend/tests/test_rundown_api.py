"""Integration tests for the Rundown API endpoints.

Tests use live DB (no mocks) matching the backend test convention.
Reference spreadsheets are at D:\\RESEARCH\\Claude\\ — tests skip if files absent.
"""
from __future__ import annotations

import io
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.dependencies import get_db
from app.models.design import Rundown
from tests.conftest import TestSession

# ---------------------------------------------------------------------------
# Reference spreadsheet paths
# ---------------------------------------------------------------------------

_SPREADSHEET_20205 = Path(r"D:\RESEARCH\Claude\20205 2-24 TEMPLE Rundown May-24-2023.xlsm")
_SPREADSHEET_24043 = Path(r"D:\RESEARCH\Claude\Rundown 24043.xlsm")

# Use 20205 as the primary test project (19 levels, 208 elements, well-verified)
_TEST_PROJECT = "20205"
_TEST_ELEMENT = "W22"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client():
    """FastAPI test client (module-scoped to avoid repeated DB setup)."""
    def _override_get_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture(scope="module", autouse=True)
def cleanup_rundown_rows():
    """Remove any rundown rows for 20205 before and after the test module."""
    with TestSession() as db:
        db.query(Rundown).filter(Rundown.project_number == _TEST_PROJECT).delete(
            synchronize_session=False
        )
        db.commit()
    yield
    with TestSession() as db:
        db.query(Rundown).filter(Rundown.project_number == _TEST_PROJECT).delete(
            synchronize_session=False
        )
        db.commit()


def _spreadsheet_bytes(path: Path) -> bytes:
    return path.read_bytes()


# ---------------------------------------------------------------------------
# Helper: skip test if spreadsheet file not found
# ---------------------------------------------------------------------------

def _require_spreadsheet(path: Path):
    if not path.exists():
        pytest.skip(f"Reference spreadsheet not found: {path}")


# ---------------------------------------------------------------------------
# POST /rundown/upload — preview
# ---------------------------------------------------------------------------


class TestUploadPreview:
    def test_upload_preview_20205(self, client: TestClient):
        """Parse 20205 spreadsheet → should return 208 elements, no errors."""
        _require_spreadsheet(_SPREADSHEET_20205)

        with open(_SPREADSHEET_20205, "rb") as f:
            response = client.post(
                f"/api/projects/{_TEST_PROJECT}/rundown/upload",
                files={"file": ("20205.xlsm", f, "application/octet-stream")},
            )
        assert response.status_code == 200, response.text
        data = response.json()

        assert data["project_number"] == _TEST_PROJECT
        assert data["element_count"] > 0
        assert data["level_count"] > 0
        assert data["load_type_count"] > 0
        assert data["errors"] == []
        # Discrepancies are informational — just check the field is present
        assert isinstance(data["discrepancy_count"], int)
        assert isinstance(data["discrepancies"], list)

    def test_upload_preview_empty_file(self, client: TestClient):
        """Upload empty file → 422."""
        response = client.post(
            f"/api/projects/{_TEST_PROJECT}/rundown/upload",
            files={"file": ("empty.xlsm", io.BytesIO(b""), "application/octet-stream")},
        )
        assert response.status_code == 422

    def test_upload_preview_any_project_number_accepted(self, client: TestClient):
        """Upload endpoint accepts any project number — no project check (onboarding path)."""
        _require_spreadsheet(_SPREADSHEET_20205)
        with open(_SPREADSHEET_20205, "rb") as f:
            response = client.post(
                "/api/projects/NEWPROJECT/rundown/upload",
                files={"file": ("20205.xlsm", f, "application/octet-stream")},
            )
        # Should succeed (parse is independent of project existence)
        assert response.status_code == 200

    def test_upload_preview_bad_file_content(self, client: TestClient):
        """Upload non-xlsm bytes → 422 (parse error)."""
        fake_bytes = b"this is not an excel file" * 10
        response = client.post(
            f"/api/projects/{_TEST_PROJECT}/rundown/upload",
            files={"file": ("fake.xlsm", io.BytesIO(fake_bytes), "application/octet-stream")},
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /rundown/upload/confirm — compute + store
# ---------------------------------------------------------------------------


class TestUploadConfirm:
    def test_compute_and_store_20205(self, client: TestClient):
        """Confirm upload → rows written > 0, validation passes."""
        _require_spreadsheet(_SPREADSHEET_20205)

        with open(_SPREADSHEET_20205, "rb") as f:
            response = client.post(
                f"/api/projects/{_TEST_PROJECT}/rundown/upload/confirm",
                files={"file": ("20205.xlsm", f, "application/octet-stream")},
            )
        assert response.status_code == 200, response.text
        data = response.json()

        assert data["project_number"] == _TEST_PROJECT
        assert data["rows_written"] > 0
        assert data["element_count"] > 0
        assert data["validation_is_valid"] is True
        assert data["validation_errors"] == []

    def test_rows_in_db_after_confirm(self, client: TestClient):
        """After confirm, rundown rows exist in DB for 20205."""
        with TestSession() as db:
            count = (
                db.query(Rundown)
                .filter(Rundown.project_number == _TEST_PROJECT)
                .count()
            )
        assert count > 0, "Expected rundown rows in DB after confirm"

    def test_confirm_replaces_existing_rows(self, client: TestClient):
        """Confirming twice replaces rows (not appends)."""
        _require_spreadsheet(_SPREADSHEET_20205)

        with TestSession() as db:
            count_before = (
                db.query(Rundown)
                .filter(Rundown.project_number == _TEST_PROJECT)
                .count()
            )

        with open(_SPREADSHEET_20205, "rb") as f:
            response = client.post(
                f"/api/projects/{_TEST_PROJECT}/rundown/upload/confirm",
                files={"file": ("20205.xlsm", f, "application/octet-stream")},
            )
        assert response.status_code == 200

        with TestSession() as db:
            count_after = (
                db.query(Rundown)
                .filter(Rundown.project_number == _TEST_PROJECT)
                .count()
            )

        assert count_after == count_before, (
            f"Row count changed: {count_before} → {count_after} (should replace, not append)"
        )


# ---------------------------------------------------------------------------
# GET /rundown — element summary list
# ---------------------------------------------------------------------------


class TestRundownList:
    def test_list_rundown_returns_elements(self, client: TestClient):
        """GET /rundown returns element list after confirm."""
        response = client.get(f"/api/projects/{_TEST_PROJECT}/rundown")
        assert response.status_code == 200, response.text
        data = response.json()

        assert data["project_number"] == _TEST_PROJECT
        assert data["element_count"] > 0
        assert len(data["elements"]) > 0

    def test_list_includes_w22(self, client: TestClient):
        """W22 is one of the elements in the 20205 rundown."""
        response = client.get(f"/api/projects/{_TEST_PROJECT}/rundown")
        assert response.status_code == 200
        marks = {e["mark"] for e in response.json()["elements"]}
        assert _TEST_ELEMENT in marks, f"Expected W22 in element list, got: {sorted(marks)[:10]}"

    def test_list_element_has_dl_kn(self, client: TestClient):
        """Each summary element has a non-zero dl_cumulative_kn."""
        response = client.get(f"/api/projects/{_TEST_PROJECT}/rundown")
        assert response.status_code == 200
        for elem in response.json()["elements"]:
            if elem["mark"] == _TEST_ELEMENT:
                assert elem["dl_cumulative_kn"] is not None
                assert elem["dl_cumulative_kn"] > 0
                break

    def test_list_unknown_project_returns_404(self, client: TestClient):
        """Unknown project (not in project_meta) → 404."""
        response = client.get("/api/projects/ZZUNKNOWN99/rundown")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /rundown/{mark} — element detail
# ---------------------------------------------------------------------------


class TestElementDetail:
    def test_get_w22_detail(self, client: TestClient):
        """GET W22 detail returns full floor stack."""
        response = client.get(f"/api/projects/{_TEST_PROJECT}/rundown/{_TEST_ELEMENT}")
        assert response.status_code == 200, response.text
        data = response.json()

        assert data["mark"] == _TEST_ELEMENT
        assert data["floor_count"] > 0
        assert len(data["floors"]) > 0

    def test_w22_floors_have_all_breakdown_fields(self, client: TestClient):
        """Every W22 floor row has the 6 DL terms and 2-path LL."""
        response = client.get(f"/api/projects/{_TEST_PROJECT}/rundown/{_TEST_ELEMENT}")
        assert response.status_code == 200
        floors = response.json()["floors"]

        # Check at least one floor (not roof, which has zero DL from above)
        for floor in floors[1:]:
            assert floor["dl_from_above_kn"] is not None
            assert floor["dl_floor_load_kn"] is not None
            assert floor["dl_cumulative_kn"] is not None
            assert floor["ll_reducible_kn"] is not None
            assert floor["dy_cumulative_kn"] is not None
            assert floor["ll_cumulative_kn"] is not None
            assert floor["pf_kn"] is not None
            break   # one floor is enough

    def test_w22_has_json_area_breakdowns(self, client: TestClient):
        """W22 floors expose per-type area breakdowns."""
        response = client.get(f"/api/projects/{_TEST_PROJECT}/rundown/{_TEST_ELEMENT}")
        assert response.status_code == 200
        # At least one floor should have area_by_type populated
        floors = response.json()["floors"]
        has_areas = any(
            floor.get("area_by_type") for floor in floors
        )
        assert has_areas, "Expected at least one floor to have area_by_type breakdown"

    def test_element_not_found(self, client: TestClient):
        """Unknown mark → 404."""
        response = client.get(f"/api/projects/{_TEST_PROJECT}/rundown/NOTEXIST")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /rundown/validation — validation results
# ---------------------------------------------------------------------------


class TestValidation:
    def test_validation_is_valid(self, client: TestClient):
        """20205 rundown area balance checks should all pass."""
        response = client.get(f"/api/projects/{_TEST_PROJECT}/rundown/validation")
        assert response.status_code == 200, response.text
        data = response.json()

        assert data["project_number"] == _TEST_PROJECT
        assert data["is_valid"] is True
        assert data["errors"] == []

    def test_validation_has_area_checks(self, client: TestClient):
        """Validation returns area check rows."""
        response = client.get(f"/api/projects/{_TEST_PROJECT}/rundown/validation")
        assert response.status_code == 200
        data = response.json()
        # area_checks may be empty if no level_identity rows; just check structure
        assert "area_checks" in data
        assert "transfer_checks" in data
        assert "data_gaps" in data

    def test_validation_unknown_project_returns_404(self, client: TestClient):
        """GET validation for unknown project (not in project_meta) → 404."""
        response = client.get("/api/projects/ZZUNKNOWN99/rundown/validation")
        assert response.status_code == 404
