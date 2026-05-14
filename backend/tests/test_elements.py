"""Tests for Elements position API.

Uses TWB file data resolved dynamically from conftest:
- TWB file (23219 project)
- Level above: has floors (slab boundary)
- Level below: has 12 columns, 17 walls

Tests against the live DB (read-only — no design schema writes).
"""
from fastapi.testclient import TestClient

from app.dependencies import get_db
from app.main import app

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


def test_get_elements_columns_and_walls():
    """Basic test: returns columns and walls for a known level."""
    resp = client.get(
        f"/api/projects/files/{FILE_ID}/levels/{LEVEL_BELOW}/elements",
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["project_id"] == FILE_ID
    assert data["level_id"] == LEVEL_BELOW

    # Level has 12 columns and 17 walls
    assert len(data["columns"]) == 12
    assert len(data["walls"]) == 17

    # Each column has guid, x, y
    col = data["columns"][0]
    assert "guid" in col
    assert isinstance(col["x"], (int, float))
    assert isinstance(col["y"], (int, float))

    # Each wall has guid, x1, y1, x2, y2
    wall = data["walls"][0]
    assert "guid" in wall
    assert isinstance(wall["x1"], (int, float))
    assert isinstance(wall["y1"], (int, float))
    assert isinstance(wall["x2"], (int, float))
    assert isinstance(wall["y2"], (int, float))


def test_get_elements_grids():
    """Grids are project-wide — returned as list (may be empty if project has none)."""
    resp = client.get(
        f"/api/projects/files/{FILE_ID}/levels/{LEVEL_BELOW}/elements",
    )
    assert resp.status_code == 200
    data = resp.json()

    # grids is always a list
    assert isinstance(data["grids"], list)

    # If grids exist, verify structure
    if len(data["grids"]) > 0:
        grid = data["grids"][0]
        assert "name" in grid
        assert isinstance(grid["x1"], (int, float))
        assert isinstance(grid["y1"], (int, float))
        assert isinstance(grid["x2"], (int, float))
        assert isinstance(grid["y2"], (int, float))


def test_get_elements_slab_boundary():
    """Level above has floors — should return slab boundary WKT."""
    resp = client.get(
        f"/api/projects/files/{FILE_ID}/levels/{LEVEL_ABOVE}/elements",
    )
    assert resp.status_code == 200
    data = resp.json()

    # Level has floors, so slab boundary should exist
    assert data["slab_boundary_wkt"] is not None
    assert data["slab_boundary_wkt"].startswith("POLYGON") or \
        data["slab_boundary_wkt"].startswith("MULTIPOLYGON")


def test_get_elements_no_slab_boundary():
    """Level below has elements but may not have floors — boundary could be null."""
    resp = client.get(
        f"/api/projects/files/{FILE_ID}/levels/{LEVEL_BELOW}/elements",
    )
    assert resp.status_code == 200
    data = resp.json()
    # slab_boundary_wkt is either null or a valid WKT (level may or may not have floors)
    if data["slab_boundary_wkt"] is not None:
        assert "POLYGON" in data["slab_boundary_wkt"]


def test_get_elements_column_structure():
    """Columns have correct schema including optional mark field."""
    resp = client.get(
        f"/api/projects/files/{FILE_ID}/levels/{LEVEL_BELOW}/elements",
    )
    data = resp.json()

    # All columns have required fields
    for col in data["columns"]:
        assert "guid" in col
        assert "mark" in col  # present even if None
        assert "x" in col
        assert "y" in col


def test_get_elements_wall_thickness():
    """Walls should have thickness from WallType."""
    resp = client.get(
        f"/api/projects/files/{FILE_ID}/levels/{LEVEL_BELOW}/elements",
    )
    data = resp.json()

    # At least some walls should have thickness
    thicknesses = [w["thickness"] for w in data["walls"] if w["thickness"]]
    assert len(thicknesses) > 0


def test_get_elements_file_not_found():
    """Non-existent file_id returns 404."""
    resp = client.get("/api/projects/files/99999/levels/1/elements")
    assert resp.status_code == 404


def test_get_elements_level_not_found():
    """Non-existent level_id returns 404."""
    resp = client.get(
        f"/api/projects/files/{FILE_ID}/levels/99999/elements",
    )
    assert resp.status_code == 404


def test_get_elements_coordinates_in_mm():
    """Verify coordinates are in mm range (not 0-1 or degrees)."""
    resp = client.get(
        f"/api/projects/files/{FILE_ID}/levels/{LEVEL_BELOW}/elements",
    )
    data = resp.json()

    # Building coordinates should be in mm range (typically 1000-50000+)
    for col in data["columns"]:
        assert abs(col["x"]) > 100, "Column X seems too small for mm"
        assert abs(col["y"]) > 100, "Column Y seems too small for mm"

    for wall in data["walls"]:
        assert abs(wall["x1"]) > 100, "Wall X1 seems too small for mm"
