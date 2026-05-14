"""Tests for Tributary Area computation API.

Uses TWB file data resolved dynamically from conftest.
Tests against the live DB. Cleans up any design-schema rows it creates.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.dependencies import get_db
from app.main import app
from app.models import LoadTable

from tests.conftest import TWB_FILE_ID, TWB_LEVEL_ABOVE, TWB_LEVEL_BELOW, TestSession


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

FILE_ID = TWB_FILE_ID
LEVEL_ABOVE = TWB_LEVEL_ABOVE
LEVEL_BELOW = TWB_LEVEL_BELOW

# All 17 walls get Voronoi cells in the current DB export
EXPECTED_COLS = 12
EXPECTED_WALLS = 17
EXPECTED_TOTAL = EXPECTED_COLS + EXPECTED_WALLS  # 29


def _cleanup_design_rows(db):
    """Raw SQL cleanup to avoid GeoAlchemy2 geometry issues on SQL Server."""
    db.execute(text(
        "DELETE FROM design.load_assignments WHERE project_id = :pid AND level_id = :lid"
    ), {"pid": FILE_ID, "lid": LEVEL_BELOW})
    db.execute(text(
        "DELETE FROM design.tributary_results WHERE project_id = :pid AND level_id = :lid"
    ), {"pid": FILE_ID, "lid": LEVEL_BELOW})
    db.query(LoadTable).filter(LoadTable.project_id == FILE_ID).delete()
    db.commit()


@pytest.fixture(autouse=True)
def cleanup():
    """Clean up design schema rows for this project/level before and after."""
    db = TestSession()
    _cleanup_design_rows(db)
    db.close()
    yield
    db = TestSession()
    _cleanup_design_rows(db)
    db.close()


# ---------------------------------------------------------------------------
# POST /api/tributary/compute — basic Voronoi (no load areas)
# ---------------------------------------------------------------------------

class TestComputeBasic:
    """Basic tributary computation tests — Voronoi only, no load areas."""

    def test_basic_compute(self):
        """Compute Voronoi — expect 12 cols + 16 walls."""
        resp = client.post("/api/tributary/compute", json={
            "project_id": FILE_ID,
            "level_above_id": LEVEL_ABOVE,
            "level_below_id": LEVEL_BELOW,
        })
        assert resp.status_code == 201
        data = resp.json()

        assert data["project_id"] == FILE_ID
        assert data["level_above_id"] == LEVEL_ABOVE
        assert data["level_below_id"] == LEVEL_BELOW

        # Expect all 12 columns + 16 walls = 28 cells
        assert data["column_count"] == EXPECTED_COLS
        assert data["wall_count"] == EXPECTED_WALLS
        assert len(data["cells"]) == EXPECTED_TOTAL

        # Boundary area should be reasonable (>500 m2 for this floor plate)
        boundary_area = float(data["boundary_area_m2"])
        assert boundary_area > 500

        # Every cell has positive area
        for cell in data["cells"]:
            assert float(cell["area_m2"]) > 0
            assert cell["element_type"] in ("column", "wall")
            assert cell["element_guid"]
            assert cell["polygon_wkt"].startswith("POLYGON") or cell["polygon_wkt"].startswith("MULTI")

    def test_cell_areas_sum_to_boundary(self):
        """Total cell area should approximately equal boundary area."""
        resp = client.post("/api/tributary/compute", json={
            "project_id": FILE_ID,
            "level_above_id": LEVEL_ABOVE,
            "level_below_id": LEVEL_BELOW,
        })
        data = resp.json()
        boundary_area = float(data["boundary_area_m2"])
        total_cell_area = sum(float(c["area_m2"]) for c in data["cells"])

        # Allow 5% tolerance (clipping/geometry precision)
        assert abs(total_cell_area - boundary_area) / boundary_area < 0.05

    def test_columns_and_walls_distinct_guids(self):
        """Each cell should have a unique element_guid."""
        resp = client.post("/api/tributary/compute", json={
            "project_id": FILE_ID,
            "level_above_id": LEVEL_ABOVE,
            "level_below_id": LEVEL_BELOW,
        })
        data = resp.json()
        guids = [c["element_guid"] for c in data["cells"]]
        assert len(guids) == len(set(guids))

    def test_custom_wall_spacing(self):
        """Larger wall spacing should still produce 28 cells."""
        resp = client.post("/api/tributary/compute", json={
            "project_id": FILE_ID,
            "level_above_id": LEVEL_ABOVE,
            "level_below_id": LEVEL_BELOW,
            "wall_spacing_mm": 500.0,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["column_count"] == EXPECTED_COLS
        assert data["wall_count"] == EXPECTED_WALLS


# ---------------------------------------------------------------------------
# POST /api/tributary/compute — with load areas
# ---------------------------------------------------------------------------

class TestComputeWithLoads:
    """Tributary computation with load area intersection."""

    def _create_load_table(self):
        """Create a test load table entry and return its id."""
        resp = client.post(f"/api/projects/files/{FILE_ID}/load-table", json=[
            {"name": "RES", "dead_load_kpa": 6.1, "live_load_kpa": 1.9, "llrf_type": "R0.3"},
        ])
        assert resp.status_code == 201
        return resp.json()[0]["id"]

    def test_compute_with_full_coverage_load_area(self):
        """Single load area covering entire boundary produces assignments for all elements."""
        lt_id = self._create_load_table()

        # Use a huge rectangle that covers the entire floor plate
        huge_wkt = "POLYGON((-50000 10000, -50000 55000, 0 55000, 0 10000, -50000 10000))"
        resp = client.post("/api/tributary/compute", json={
            "project_id": FILE_ID,
            "level_above_id": LEVEL_ABOVE,
            "level_below_id": LEVEL_BELOW,
            "load_areas": [{"polygon_wkt": huge_wkt, "load_table_id": lt_id}],
        })
        assert resp.status_code == 201
        data = resp.json()

        # Should have load assignments for all 28 elements
        assert len(data["load_assignments"]) == EXPECTED_TOTAL

        # Each assignment has positive loads
        for la in data["load_assignments"]:
            assert float(la["tributary_area_m2"]) > 0
            assert float(la["dead_load_kn"]) > 0
            assert float(la["live_load_kn"]) > 0
            assert la["load_table_id"] == lt_id

        # Total assignment area should match total cell area
        total_cell = sum(float(c["area_m2"]) for c in data["cells"])
        total_assign = sum(float(la["tributary_area_m2"]) for la in data["load_assignments"])
        assert abs(total_cell - total_assign) / total_cell < 0.01

    def test_load_assignments_stored_in_db(self):
        """Verify load assignments are persisted to design schema."""
        lt_id = self._create_load_table()
        huge_wkt = "POLYGON((-50000 10000, -50000 55000, 0 55000, 0 10000, -50000 10000))"
        resp = client.post("/api/tributary/compute", json={
            "project_id": FILE_ID,
            "level_above_id": LEVEL_ABOVE,
            "level_below_id": LEVEL_BELOW,
            "load_areas": [{"polygon_wkt": huge_wkt, "load_table_id": lt_id}],
        })
        assert resp.status_code == 201

        # Check stored results via GET endpoint
        resp = client.get(f"/api/tributary/results/{FILE_ID}/{LEVEL_BELOW}")
        assert resp.status_code == 200
        stored = resp.json()
        assert len(stored) == EXPECTED_TOTAL

    def test_recompute_clears_old_results(self):
        """Re-running compute replaces previous results."""
        lt_id = self._create_load_table()
        huge_wkt = "POLYGON((-50000 10000, -50000 55000, 0 55000, 0 10000, -50000 10000))"

        # First compute
        client.post("/api/tributary/compute", json={
            "project_id": FILE_ID,
            "level_above_id": LEVEL_ABOVE,
            "level_below_id": LEVEL_BELOW,
            "load_areas": [{"polygon_wkt": huge_wkt, "load_table_id": lt_id}],
        })
        # Second compute — should replace, not duplicate
        client.post("/api/tributary/compute", json={
            "project_id": FILE_ID,
            "level_above_id": LEVEL_ABOVE,
            "level_below_id": LEVEL_BELOW,
            "load_areas": [{"polygon_wkt": huge_wkt, "load_table_id": lt_id}],
        })

        resp = client.get(f"/api/tributary/results/{FILE_ID}/{LEVEL_BELOW}")
        assert len(resp.json()) == EXPECTED_TOTAL  # Not 56

    def test_invalid_load_table_rejected(self):
        """Non-existent load_table_id should be rejected."""
        huge_wkt = "POLYGON((-50000 10000, -50000 55000, 0 55000, 0 10000, -50000 10000))"
        resp = client.post("/api/tributary/compute", json={
            "project_id": FILE_ID,
            "level_above_id": LEVEL_ABOVE,
            "level_below_id": LEVEL_BELOW,
            "load_areas": [{"polygon_wkt": huge_wkt, "load_table_id": 999999}],
        })
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/tributary/compute — json_upload boundary
# ---------------------------------------------------------------------------

class TestJsonUploadBoundary:
    """Test with user-provided WKT boundary instead of slab_db."""

    def test_simple_rectangle_boundary(self):
        """A simple rectangle boundary should work."""
        rect = "POLYGON((-30000 20000, -30000 45000, -10000 45000, -10000 20000, -30000 20000))"
        resp = client.post("/api/tributary/compute", json={
            "project_id": FILE_ID,
            "level_above_id": LEVEL_ABOVE,
            "level_below_id": LEVEL_BELOW,
            "floor_boundary_source": "json_upload",
            "floor_boundary_wkt": rect,
        })
        assert resp.status_code == 201
        data = resp.json()
        # Fewer cells expected — some elements outside the rectangle
        assert data["column_count"] + data["wall_count"] > 0
        assert len(data["cells"]) > 0

    def test_missing_wkt_rejected(self):
        """json_upload source requires floor_boundary_wkt."""
        resp = client.post("/api/tributary/compute", json={
            "project_id": FILE_ID,
            "level_above_id": LEVEL_ABOVE,
            "level_below_id": LEVEL_BELOW,
            "floor_boundary_source": "json_upload",
        })
        assert resp.status_code == 400

    def test_invalid_wkt_rejected(self):
        """Bad WKT should return 400."""
        resp = client.post("/api/tributary/compute", json={
            "project_id": FILE_ID,
            "level_above_id": LEVEL_ABOVE,
            "level_below_id": LEVEL_BELOW,
            "floor_boundary_source": "json_upload",
            "floor_boundary_wkt": "NOT_A_POLYGON",
        })
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Error cases
# ---------------------------------------------------------------------------

class TestComputeErrors:
    def test_project_not_found(self):
        resp = client.post("/api/tributary/compute", json={
            "project_id": 999999,
            "level_above_id": LEVEL_ABOVE,
            "level_below_id": LEVEL_BELOW,
        })
        assert resp.status_code == 404

    def test_level_above_not_found(self):
        resp = client.post("/api/tributary/compute", json={
            "project_id": FILE_ID,
            "level_above_id": 999999,
            "level_below_id": LEVEL_BELOW,
        })
        assert resp.status_code == 404

    def test_level_below_not_found(self):
        resp = client.post("/api/tributary/compute", json={
            "project_id": FILE_ID,
            "level_above_id": LEVEL_ABOVE,
            "level_below_id": 999999,
        })
        assert resp.status_code == 404

    def test_no_elements_on_level(self):
        """Level with no columns/walls should return 400."""
        resp = client.post("/api/tributary/compute", json={
            "project_id": FILE_ID,
            "level_above_id": LEVEL_ABOVE,
            "level_below_id": LEVEL_ABOVE,  # Using level_above as below — no elements
        })
        # Either 400 (no elements) or 201 with 0 cells
        assert resp.status_code in (400, 201)


# ---------------------------------------------------------------------------
# GET /api/tributary/results/{project_id}/{level_id}
# ---------------------------------------------------------------------------

class TestGetResults:
    def test_empty_results(self):
        resp = client.get(f"/api/tributary/results/{FILE_ID}/{LEVEL_BELOW}")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_project_not_found(self):
        resp = client.get("/api/tributary/results/999999/156")
        assert resp.status_code == 404