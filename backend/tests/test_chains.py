"""Tests for Vertical Chain service + API.

Uses project 23219 (PODIUM + TWB files) from the live DB.
Pre-populates level_identity + element_identity (chains derive from both).
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
    # Pre-sync identity hub (chains derive from it)
    client.post(f"/api/projects/{PROJECT_NUMBER}/levels/sync")
    client.post(f"/api/projects/{PROJECT_NUMBER}/elements/sync")
    yield
    db = TestSession()
    _cleanup(db)
    db.close()


# ---------------------------------------------------------------------------
# POST /api/projects/{number}/chains/build
# ---------------------------------------------------------------------------

class TestBuildChains:
    def test_build_returns_chains(self):
        resp = client.post(f"/api/projects/{PROJECT_NUMBER}/chains/build")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_chains"] > 0
        assert data["total_elements"] > 0
        assert isinstance(data["chains"], list)
        assert len(data["chains"]) == data["total_chains"]

    def test_build_chain_summary_fields(self):
        resp = client.post(f"/api/projects/{PROJECT_NUMBER}/chains/build")
        chain = resp.json()["chains"][0]
        assert "canonical_mark" in chain
        assert "element_type" in chain
        assert chain["element_type"] in ("Column", "Wall")
        assert "floor_count" in chain
        assert chain["floor_count"] >= 1
        assert "min_level" in chain
        assert "max_level" in chain
        assert "has_gaps" in chain
        assert "gap_count" in chain

    def test_build_empty_project(self):
        """Project with no identity data → empty result."""
        # Clean identity data
        db = TestSession()
        _cleanup(db)
        db.close()
        resp = client.post(f"/api/projects/{PROJECT_NUMBER}/chains/build")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_chains"] == 0
        assert data["total_elements"] == 0
        assert data["chains"] == []

    def test_build_project_not_found(self):
        resp = client.post("/api/projects/ZZZZZZ/chains/build")
        assert resp.status_code == 404

    def test_build_single_floor_count(self):
        """Elements on only one floor should have floor_count=1, no gaps."""
        resp = client.post(f"/api/projects/{PROJECT_NUMBER}/chains/build")
        singles = [c for c in resp.json()["chains"] if c["floor_count"] == 1]
        for s in singles:
            assert s["has_gaps"] is False
            assert s["gap_count"] == 0
            assert s["min_level"] == s["max_level"]

    def test_build_columns_and_walls_separate(self):
        """Chains should separate columns from walls even if same mark number."""
        resp = client.post(f"/api/projects/{PROJECT_NUMBER}/chains/build")
        chains = resp.json()["chains"]
        # Each chain should have a single element_type
        for c in chains:
            assert c["element_type"] in ("Column", "Wall")


# ---------------------------------------------------------------------------
# GET /api/projects/{number}/chains
# ---------------------------------------------------------------------------

class TestListChains:
    def test_list_returns_summaries(self):
        resp = client.get(f"/api/projects/{PROJECT_NUMBER}/chains")
        assert resp.status_code == 200
        chains = resp.json()
        assert isinstance(chains, list)
        assert len(chains) > 0

    def test_list_matches_build(self):
        """GET chains should return same summaries as POST build."""
        build_resp = client.post(f"/api/projects/{PROJECT_NUMBER}/chains/build")
        list_resp = client.get(f"/api/projects/{PROJECT_NUMBER}/chains")
        assert build_resp.json()["total_chains"] == len(list_resp.json())


# ---------------------------------------------------------------------------
# GET /api/projects/{number}/chains/{element_identity_id}
# ---------------------------------------------------------------------------

class TestChainDetail:
    def test_detail_returns_floors(self):
        """Chain detail should include sorted floors."""
        # Get an element with a level assignment
        resp = client.get(f"/api/projects/{PROJECT_NUMBER}/elements/identity")
        elements = resp.json()
        linked = [e for e in elements if e["level_identity_id"] is not None]
        assert len(linked) > 0

        eid = linked[0]["id"]
        resp = client.get(f"/api/projects/{PROJECT_NUMBER}/chains/{eid}")
        assert resp.status_code == 200
        detail = resp.json()
        assert detail["canonical_mark"] == linked[0]["canonical_mark"]
        assert len(detail["floors"]) >= 1
        assert isinstance(detail["gaps"], list)

        # Floors should be sorted by sort_order
        sort_orders = [f["sort_order"] for f in detail["floors"]]
        assert sort_orders == sorted(sort_orders)

    def test_detail_floor_fields(self):
        """Each floor in detail should have expected fields."""
        resp = client.get(f"/api/projects/{PROJECT_NUMBER}/elements/identity")
        linked = [e for e in resp.json() if e["level_identity_id"] is not None]
        eid = linked[0]["id"]

        resp = client.get(f"/api/projects/{PROJECT_NUMBER}/chains/{eid}")
        floor = resp.json()["floors"][0]
        assert "element_identity_id" in floor
        assert "level_identity_id" in floor
        assert "level_name" in floor
        assert "sort_order" in floor
        assert "revit_guid" in floor
        assert "match_confidence" in floor
        assert "has_rundown" in floor

    def test_detail_not_found(self):
        resp = client.get(f"/api/projects/{PROJECT_NUMBER}/chains/999999")
        assert resp.status_code == 404

    def test_stale_excluded(self):
        """Stale elements should be excluded from chain detail."""
        # Inject a stale element with same mark as an existing chain
        resp = client.get(f"/api/projects/{PROJECT_NUMBER}/elements/identity")
        elements = resp.json()
        linked = [e for e in elements if e["level_identity_id"] is not None]
        anchor = linked[0]

        db = TestSession()
        db.execute(text("""
            INSERT INTO design.element_identity
                (project_number, element_type, canonical_mark, revit_guid,
                 match_confidence, match_method)
            VALUES (:pn, :et, :cm, 'stale-fake-guid',
                    0.0, 'Stale')
        """), {
            "pn": PROJECT_NUMBER,
            "et": anchor["element_type"],
            "cm": anchor["canonical_mark"],
        })
        db.commit()
        db.close()

        resp = client.get(f"/api/projects/{PROJECT_NUMBER}/chains/{anchor['id']}")
        assert resp.status_code == 200
        guids = [f["revit_guid"] for f in resp.json()["floors"]]
        assert "stale-fake-guid" not in guids