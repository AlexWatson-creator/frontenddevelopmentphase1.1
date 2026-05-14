"""End-to-end rundown workflow test.

Simulates the real user workflow:
  1. Upload .xlsm spreadsheet → platform previews
  2. Confirm upload → engine computes + stores to DB
  3. Read element list → verify element count and summaries
  4. Read single element → spot-check DL/LL/PF against known Excel values
  5. Read validation → verify area balance passes

Uses the smaller project: 20205 TEMPLE (19 levels, 208 elements).
Reference values from rundown_engine/tests/data_20205.py.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.dependencies import get_db
from app.models.design import Rundown
from tests.conftest import TestSession

# ---------------------------------------------------------------------------
# Reference spreadsheet
# ---------------------------------------------------------------------------

_SPREADSHEET = Path(r"D:\RESEARCH\Claude\20205 2-24 TEMPLE Rundown May-24-2023.xlsm")
_PROJECT = "20205"
_TOLERANCE = 0.5  # kN — same as engine verification tests

# Known Excel values (from data_20205.py, extracted with openpyxl data_only=True)
# W22: active AMENITY → GROUND (no transfers, simple RES wall)
_W22_GROUND = {  # bot="GROUND", top="2", floor index 15 (0-based)
    "dl": 904.2332,
    "ll": 196.2853,
    "pw": 1100.5185,
    "pf": 1424.7195,
    "cum_area": 102.8,
}
_W22_FIRST_ACTIVE = {  # bot="AMENITY", top="MPH", floor index 1
    "dl": 105.1112,
    "ll": 59.04,
    "pf": 219.949,
}
# C2: receives transfer from C2.2 at level 13 — tests transfer path
_C2_FIRST_ACTIVE = {  # bot="12", top="13", floor index 4
    "dl": 416.6275,
    "ll": 116.5918,
    "pf": 695.6721,
    "area": 18.1,
    "xfer_area": 19.4304,
    "cum_area": 37.5304,
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def client():
    """FastAPI test client with DB dependency override."""
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
def cleanup():
    """Remove rundown rows for 20205 before and after the module."""
    with TestSession() as db:
        db.query(Rundown).filter(Rundown.project_number == _PROJECT).delete(
            synchronize_session=False
        )
        db.commit()
    yield
    with TestSession() as db:
        db.query(Rundown).filter(Rundown.project_number == _PROJECT).delete(
            synchronize_session=False
        )
        db.commit()


def _require():
    if not _SPREADSHEET.exists():
        pytest.skip(f"Reference spreadsheet not found: {_SPREADSHEET}")


# ---------------------------------------------------------------------------
# Step 1: Upload → preview
# ---------------------------------------------------------------------------

class TestStep1Preview:
    """User uploads .xlsm → platform parses and shows preview."""

    def test_preview_parses_all_elements(self, client: TestClient):
        _require()
        with open(_SPREADSHEET, "rb") as f:
            resp = client.post(
                f"/api/projects/{_PROJECT}/rundown/upload",
                files={"file": ("20205.xlsm", f, "application/octet-stream")},
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert data["project_number"] == _PROJECT
        assert data["element_count"] == 208, f"Expected 208 elements, got {data['element_count']}"
        assert data["level_count"] == 19
        assert data["load_type_count"] >= 17
        assert data["errors"] == [], f"Unexpected parse errors: {data['errors']}"

    def test_preview_returns_discrepancies(self, client: TestClient):
        _require()
        with open(_SPREADSHEET, "rb") as f:
            resp = client.post(
                f"/api/projects/{_PROJECT}/rundown/upload",
                files={"file": ("20205.xlsm", f, "application/octet-stream")},
            )
        data = resp.json()
        # Discrepancy list should exist (may be empty if engine matches Excel perfectly)
        assert "discrepancy_count" in data
        assert isinstance(data["discrepancies"], list)


# ---------------------------------------------------------------------------
# Step 2: Confirm → compute + store
# ---------------------------------------------------------------------------

class TestStep2Confirm:
    """User confirms → engine computes full rundown and stores to DB."""

    def test_confirm_writes_all_rows(self, client: TestClient):
        _require()
        with open(_SPREADSHEET, "rb") as f:
            resp = client.post(
                f"/api/projects/{_PROJECT}/rundown/upload/confirm",
                files={"file": ("20205.xlsm", f, "application/octet-stream")},
            )
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert data["project_number"] == _PROJECT
        assert data["element_count"] == 208
        # 208 elements × 19 levels = 3952 rows
        assert data["rows_written"] == 208 * 19, (
            f"Expected {208 * 19} rows, got {data['rows_written']}"
        )
        assert data["validation_is_valid"] is True
        assert data["validation_errors"] == []

    def test_rows_exist_in_db(self, client: TestClient):
        """Verify rows actually landed in the DB."""
        with TestSession() as db:
            count = (
                db.query(Rundown)
                .filter(Rundown.project_number == _PROJECT)
                .count()
            )
        assert count == 208 * 19, f"Expected {208 * 19} DB rows, got {count}"


# ---------------------------------------------------------------------------
# Step 3: Read element list
# ---------------------------------------------------------------------------

class TestStep3List:
    """User views the element summary list."""

    def test_list_returns_208_elements(self, client: TestClient):
        resp = client.get(f"/api/projects/{_PROJECT}/rundown")
        assert resp.status_code == 200
        data = resp.json()

        assert data["element_count"] == 208
        assert len(data["elements"]) == 208

    def test_w22_summary_has_correct_base_dl(self, client: TestClient):
        """W22 footing-level DL matches known Excel value."""
        resp = client.get(f"/api/projects/{_PROJECT}/rundown")
        elements = {e["mark"]: e for e in resp.json()["elements"]}

        w22 = elements["W22"]
        assert w22["element_type"] == "Wall"
        assert w22["floor_count"] == 19
        # Lowest floor DL should match the last active floor's cumulative DL
        assert w22["dl_cumulative_kn"] == pytest.approx(
            _W22_GROUND["dl"], abs=_TOLERANCE
        ), f"W22 base DL: expected {_W22_GROUND['dl']}, got {w22['dl_cumulative_kn']}"

    def test_c2_in_list(self, client: TestClient):
        resp = client.get(f"/api/projects/{_PROJECT}/rundown")
        marks = {e["mark"] for e in resp.json()["elements"]}
        assert "C2" in marks


# ---------------------------------------------------------------------------
# Step 4: Read single element — spot-check values
# ---------------------------------------------------------------------------

class TestStep4ElementDetail:
    """User clicks an element → sees full floor-by-floor breakdown."""

    def test_w22_floor_count(self, client: TestClient):
        resp = client.get(f"/api/projects/{_PROJECT}/rundown/W22")
        assert resp.status_code == 200
        data = resp.json()
        assert data["mark"] == "W22"
        assert data["element_type"] == "Wall"
        assert data["floor_count"] == 19

    def test_w22_ground_level_values(self, client: TestClient):
        """W22 at GROUND level (floor_order 15) — DL/LL/PF match Excel."""
        resp = client.get(f"/api/projects/{_PROJECT}/rundown/W22")
        floors = resp.json()["floors"]

        # floor_order 15 = bot GROUND, top 2
        ground = floors[15]
        assert ground["dl_cumulative_kn"] == pytest.approx(_W22_GROUND["dl"], abs=_TOLERANCE)
        assert ground["ll_cumulative_kn"] == pytest.approx(_W22_GROUND["ll"], abs=_TOLERANCE)
        assert ground["pw_kn"] == pytest.approx(_W22_GROUND["pw"], abs=_TOLERANCE)
        assert ground["pf_kn"] == pytest.approx(_W22_GROUND["pf"], abs=_TOLERANCE)
        assert ground["cum_area_m2"] == pytest.approx(_W22_GROUND["cum_area"], abs=0.1)

    def test_w22_first_active_floor(self, client: TestClient):
        """W22 first active floor (AMENITY→MPH, floor_order 1) — DL/LL/PF match."""
        resp = client.get(f"/api/projects/{_PROJECT}/rundown/W22")
        floors = resp.json()["floors"]

        first = floors[1]
        assert first["dl_cumulative_kn"] == pytest.approx(_W22_FIRST_ACTIVE["dl"], abs=_TOLERANCE)
        assert first["ll_cumulative_kn"] == pytest.approx(_W22_FIRST_ACTIVE["ll"], abs=_TOLERANCE)
        assert first["pf_kn"] == pytest.approx(_W22_FIRST_ACTIVE["pf"], abs=_TOLERANCE)

    def test_w22_roof_is_zero(self, client: TestClient):
        """W22 roof floor (floor_order 0) — no cross-section, all loads zero."""
        resp = client.get(f"/api/projects/{_PROJECT}/rundown/W22")
        roof = resp.json()["floors"][0]

        assert roof["dl_cumulative_kn"] == pytest.approx(0.0, abs=0.01)
        assert roof["ll_cumulative_kn"] == pytest.approx(0.0, abs=0.01)
        assert roof["cross_section_m2"] is None

    def test_w22_dl_breakdown_sums_correctly(self, client: TestClient):
        """The 6 DL terms must sum to dl_cumulative for each active floor."""
        resp = client.get(f"/api/projects/{_PROJECT}/rundown/W22")
        floors = resp.json()["floors"]

        for i, fl in enumerate(floors):
            if fl["cross_section_m2"] is None:
                continue  # skip absent floors
            dl_sum = (
                (fl["dl_from_above_kn"] or 0)
                + (fl["dl_floor_load_kn"] or 0)
                + (fl["dl_transfer_kn"] or 0)
                + (fl["dl_self_weight_kn"] or 0)
                + (fl["dl_cladding_kn"] or 0)
                + (fl["dl_beam_weight_kn"] or 0)
            )
            assert dl_sum == pytest.approx(fl["dl_cumulative_kn"], abs=0.01), (
                f"W22 floor {i}: DL breakdown sum {dl_sum:.4f} != cumulative {fl['dl_cumulative_kn']}"
            )

    def test_w22_ll_two_path_sums(self, client: TestClient):
        """LL = ll_reducible + dy_cumulative for each floor."""
        resp = client.get(f"/api/projects/{_PROJECT}/rundown/W22")
        floors = resp.json()["floors"]

        for i, fl in enumerate(floors):
            ll_expected = (fl["ll_reducible_kn"] or 0) + (fl["dy_cumulative_kn"] or 0)
            assert ll_expected == pytest.approx(fl["ll_cumulative_kn"] or 0, abs=0.01), (
                f"W22 floor {i}: ll_reducible + dy != ll_cumulative"
            )

    def test_w22_json_area_breakdowns(self, client: TestClient):
        """Active floors have per-type area breakdowns in JSON."""
        resp = client.get(f"/api/projects/{_PROJECT}/rundown/W22")
        floors = resp.json()["floors"]

        # Floor 1 (AMENITY→MPH) should have MECP area
        fl1 = floors[1]
        assert fl1["area_by_type"] is not None
        assert "MECP" in fl1["area_by_type"]
        assert fl1["area_by_type"]["MECP"] == pytest.approx(8.2, abs=0.1)

        # Floor 3 (13→14) should have RES area
        fl3 = floors[3]
        assert fl3["area_by_type"] is not None
        assert "RES" in fl3["area_by_type"]
        assert fl3["area_by_type"]["RES"] == pytest.approx(6.5, abs=0.1)

    def test_c2_transfer_values(self, client: TestClient):
        """C2 receives transfer from C2.2 — DL/LL at first active floor match Excel."""
        resp = client.get(f"/api/projects/{_PROJECT}/rundown/C2")
        assert resp.status_code == 200
        floors = resp.json()["floors"]

        # C2 first active floor is at floor_order 4 (bot=12, top=13)
        active = floors[4]
        assert active["dl_cumulative_kn"] == pytest.approx(_C2_FIRST_ACTIVE["dl"], abs=_TOLERANCE)
        assert active["ll_cumulative_kn"] == pytest.approx(_C2_FIRST_ACTIVE["ll"], abs=_TOLERANCE)
        assert active["pf_kn"] == pytest.approx(_C2_FIRST_ACTIVE["pf"], abs=_TOLERANCE)
        assert active["area_this_floor_m2"] == pytest.approx(_C2_FIRST_ACTIVE["area"], abs=0.1)
        assert active["transfer_area_m2"] == pytest.approx(_C2_FIRST_ACTIVE["xfer_area"], abs=0.1)
        assert active["cum_area_m2"] == pytest.approx(_C2_FIRST_ACTIVE["cum_area"], abs=0.1)

    def test_c2_transfer_dl_nonzero(self, client: TestClient):
        """C2's first active floor must show nonzero dl_transfer_kn (from C2.2)."""
        resp = client.get(f"/api/projects/{_PROJECT}/rundown/C2")
        active = resp.json()["floors"][4]
        assert active["dl_transfer_kn"] is not None
        assert active["dl_transfer_kn"] > 100, (
            f"C2 should have >100 kN DL transfer from C2.2, got {active['dl_transfer_kn']}"
        )

    def test_data_source_is_spreadsheet(self, client: TestClient):
        """All rows should have data_source = 'spreadsheet'."""
        resp = client.get(f"/api/projects/{_PROJECT}/rundown/W22")
        floors = resp.json()["floors"]
        for fl in floors:
            assert fl["data_source"] == "spreadsheet"


# ---------------------------------------------------------------------------
# Step 5: Validation
# ---------------------------------------------------------------------------

class TestStep5Validation:
    """User checks the validation tab — area balance and transfer checks."""

    def test_validation_passes(self, client: TestClient):
        resp = client.get(f"/api/projects/{_PROJECT}/rundown/validation")
        assert resp.status_code == 200
        data = resp.json()

        assert data["project_number"] == _PROJECT
        assert data["is_valid"] is True
        assert data["errors"] == []

    def test_area_checks_present(self, client: TestClient):
        resp = client.get(f"/api/projects/{_PROJECT}/rundown/validation")
        data = resp.json()
        # Area checks should have entries (19 levels)
        assert isinstance(data["area_checks"], list)
        assert isinstance(data["transfer_checks"], list)
        assert isinstance(data["data_gaps"], list)


# ---------------------------------------------------------------------------
# Step 6: Idempotency — confirming twice replaces, not appends
# ---------------------------------------------------------------------------

class TestStep6Idempotency:
    """Confirming a second time replaces all rows, doesn't double them."""

    def test_reconfirm_same_count(self, client: TestClient):
        _require()
        with TestSession() as db:
            before = db.query(Rundown).filter(
                Rundown.project_number == _PROJECT
            ).count()

        with open(_SPREADSHEET, "rb") as f:
            resp = client.post(
                f"/api/projects/{_PROJECT}/rundown/upload/confirm",
                files={"file": ("20205.xlsm", f, "application/octet-stream")},
            )
        assert resp.status_code == 200

        with TestSession() as db:
            after = db.query(Rundown).filter(
                Rundown.project_number == _PROJECT
            ).count()

        assert after == before, f"Row count changed: {before} → {after} (should replace)"