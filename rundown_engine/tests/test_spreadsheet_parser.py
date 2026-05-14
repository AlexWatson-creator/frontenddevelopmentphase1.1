"""Tests for the spreadsheet parser (parsers/spreadsheet.py).

Tests against three real .xlsm files:
  - 20205: 19 levels, 208 elements (standard marks: C1, W22, PW101)
  - 24043: 50 levels, 184 elements (zero-padded marks: C029, W008)
  - 24025: 39 levels, 129 elements (mixed marks: C1, PW35, !FDNW6)
"""

from __future__ import annotations

import pytest

from rundown_engine.parsers.spreadsheet import (
    _classify_element,
    _level_name,
    compare_results,
    parse_rundown_spreadsheet,
)

# ---------------------------------------------------------------------------
# Paths to test spreadsheets (must exist on dev machine)
# ---------------------------------------------------------------------------

_FILE_20205 = "D:/RESEARCH/Claude/20205 2-24 TEMPLE Rundown May-24-2023.xlsm"
_FILE_24043 = "D:/RESEARCH/Claude/Rundown 24043.xlsm"
_FILE_24025 = "D:/RESEARCH/Claude/24025 - Rundown - 2026-01-091.xlsm"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_element(result, mark):
    """Find an element by mark in the parse result."""
    for e in result.elements:
        if e.mark == mark:
            return e
    pytest.fail(f"Element '{mark}' not found in parse result")


# ---------------------------------------------------------------------------
# Unit tests: helper functions
# ---------------------------------------------------------------------------

class TestLevelName:
    """Test _level_name normalization."""

    def test_string(self):
        assert _level_name("GROUND") == "GROUND"

    def test_int(self):
        assert _level_name(13) == "13"

    def test_float_whole(self):
        assert _level_name(13.0) == "13"

    def test_none(self):
        assert _level_name(None) == ""

    def test_whitespace(self):
        assert _level_name("  MPH  ") == "MPH"


class TestClassifyElement:
    """Test _classify_element type detection."""

    def test_column(self):
        assert _classify_element("C1") == "Column"

    def test_wall(self):
        assert _classify_element("W22") == "Wall"

    def test_grouped_wall(self):
        assert _classify_element("W12-W13-W14") == "Wall"

    def test_parking_column(self):
        assert _classify_element("PC104") == "Column"

    def test_parking_wall(self):
        assert _classify_element("PW101") == "Wall"

    def test_heritage_column(self):
        assert _classify_element("HC041") == "Column"

    def test_heritage_wall(self):
        assert _classify_element("HW022") == "Wall"

    def test_foundation_wall(self):
        assert _classify_element("!FDNW1") == "Wall"

    def test_foundation_column(self):
        assert _classify_element("!FDNC1") == "Column"

    def test_zero_padded_column(self):
        assert _classify_element("C029") == "Column"

    def test_zero_padded_wall(self):
        assert _classify_element("W008") == "Wall"

    def test_suffix(self):
        assert _classify_element("C1A") == "Column"

    def test_comment(self):
        assert _classify_element("C2.1") == "Column"


# ===========================================================================
# 20205 — 2-24 TEMPLE AVE (19 levels, 208 elements)
# ===========================================================================

class TestParse20205:
    """Parse 20205 spreadsheet: metadata, load types, levels."""

    @pytest.fixture(scope="class")
    def result(self):
        return parse_rundown_spreadsheet(_FILE_20205)

    def test_metadata(self, result):
        assert result.project_number == "20205"
        assert result.job_name == "2-24 TEMPLE AVE"
        assert result.designer == "JS"

    def test_no_errors(self, result):
        assert result.errors == []

    def test_load_types_count(self, result):
        assert len(result.load_types) == 25

    def test_load_type_res(self, result):
        res = next(lt for lt in result.load_types if lt.code == "RES")
        assert res.description == "RESIDENTIAL"
        assert res.dead_kpa == 6.1
        assert res.live_kpa == 1.9
        assert res.llrf_type == "R0.3"

    def test_levels_count(self, result):
        assert len(result.levels) == 19

    def test_first_level(self, result):
        assert result.levels[0].bot_level == "MPH"
        assert result.levels[0].top_level == "ROOF"

    def test_last_level(self, result):
        assert result.levels[-1].bot_level == "Ftgs"
        assert result.levels[-1].top_level == "P2"

    def test_element_count(self, result):
        assert len(result.elements) == 208

    def test_imported_values_count(self, result):
        assert len(result.imported_values) == 208


class TestParse20205_C1:
    """20205 C1 element — column with no transfers, known DL/LL at row 10."""

    @pytest.fixture(scope="class")
    def result(self):
        return parse_rundown_spreadsheet(_FILE_20205)

    @pytest.fixture(scope="class")
    def c1(self, result):
        return _find_element(result, "C1")

    def test_type(self, c1):
        assert c1.element_type == "Column"

    def test_floor_count(self, c1):
        assert len(c1.floors) == 19

    def test_cladding(self, c1):
        assert c1.cladding_kpa == 2.0

    def test_no_transfers(self, c1):
        assert len(c1.transfers_received) == 0

    def test_first_floor_levels(self, c1):
        f = c1.floors[0]
        assert f.level.bot_level == "MPH"
        assert f.level.top_level == "ROOF"

    def test_first_floor_height(self, c1):
        assert c1.floors[0].level.story_height_m == 3.55

    def test_imported_dl_row10(self, result):
        """C1 row 10 (index 3): DL=165.682 (verified against Excel)."""
        vals = result.imported_values["C1"]
        assert abs(vals[3].dl_kn - 165.682) < 0.01

    def test_imported_ll_row10(self, result):
        """C1 row 10 (index 3): LL=44.63."""
        vals = result.imported_values["C1"]
        assert abs(vals[3].ll_kn - 44.63) < 0.01

    def test_imported_pf_row10(self, result):
        """C1 row 10 (index 3): PF=274.048."""
        vals = result.imported_values["C1"]
        assert abs(vals[3].pf_kn - 274.048) < 0.01


class TestParse20205_C2:
    """20205 C2 — column with one transfer from C2.2."""

    @pytest.fixture(scope="class")
    def result(self):
        return parse_rundown_spreadsheet(_FILE_20205)

    @pytest.fixture(scope="class")
    def c2(self, result):
        return _find_element(result, "C2")

    def test_transfer_count(self, c2):
        assert len(c2.transfers_received) == 1

    def test_transfer_source(self, c2):
        t = c2.transfers_received[0]
        assert t.source_element == "C2.2"

    def test_transfer_level(self, c2):
        t = c2.transfers_received[0]
        assert t.target_level == "13"

    def test_transfer_percent(self, c2):
        t = c2.transfers_received[0]
        assert abs(t.percent - 0.759) < 0.001

    def test_transfer_dl(self, c2):
        t = c2.transfers_received[0]
        assert t.dl_kn is not None
        assert abs(t.dl_kn - 215.595) < 0.1

    def test_transfer_ll(self, c2):
        t = c2.transfers_received[0]
        assert t.ll_kn is not None
        assert abs(t.ll_kn - 65.09) < 0.1


class TestParse20205_W22:
    """20205 W22 — wall with areas, known values."""

    @pytest.fixture(scope="class")
    def result(self):
        return parse_rundown_spreadsheet(_FILE_20205)

    @pytest.fixture(scope="class")
    def w22(self, result):
        return _find_element(result, "W22")

    def test_type(self, w22):
        assert w22.element_type == "Wall"

    def test_floor_count(self, w22):
        assert len(w22.floors) == 19

    def test_cladding(self, w22):
        assert w22.cladding_kpa == 2.0

    def test_areas_present(self, w22):
        """W22 should have area data on at least some floors."""
        floors_with_areas = [f for f in w22.floors if f.area_by_type]
        assert len(floors_with_areas) > 0

    def test_dimensions_present(self, w22):
        """W22 should have dimensions on most floors."""
        floors_with_dims = [f for f in w22.floors if f.dimensions is not None]
        assert len(floors_with_dims) > 0


# ===========================================================================
# 24043 — 2810 Bayview (50 levels, 184 elements, zero-padded marks)
# ===========================================================================

class TestParse24043:
    """Parse 24043 spreadsheet: metadata, levels, elements."""

    @pytest.fixture(scope="class")
    def result(self):
        return parse_rundown_spreadsheet(_FILE_24043)

    def test_metadata(self, result):
        assert result.project_number == "24043"
        assert "Bayview" in result.job_name
        assert result.designer == "DM"

    def test_no_errors(self, result):
        assert result.errors == []

    def test_load_types_count(self, result):
        assert len(result.load_types) == 25

    def test_levels_count(self, result):
        assert len(result.levels) == 50

    def test_element_count(self, result):
        assert len(result.elements) == 184


class TestParse24043_C029:
    """24043 C029 — column with 3 transfers, 50 floors."""

    @pytest.fixture(scope="class")
    def result(self):
        return parse_rundown_spreadsheet(_FILE_24043)

    @pytest.fixture(scope="class")
    def c029(self, result):
        return _find_element(result, "C029")

    def test_type(self, c029):
        assert c029.element_type == "Column"

    def test_floor_count(self, c029):
        assert len(c029.floors) == 50

    def test_cladding(self, c029):
        assert c029.cladding_kpa == 1.5

    def test_transfer_count(self, c029):
        assert len(c029.transfers_received) == 3

    def test_transfer_sources(self, c029):
        sources = {t.source_element for t in c029.transfers_received}
        assert "W030" in sources
        assert "C050" in sources
        assert "HC060" in sources


class TestParse24043_W008:
    """24043 W008 — wall with transfers from C034 and C008."""

    @pytest.fixture(scope="class")
    def result(self):
        return parse_rundown_spreadsheet(_FILE_24043)

    @pytest.fixture(scope="class")
    def w008(self, result):
        return _find_element(result, "W008")

    def test_type(self, w008):
        assert w008.element_type == "Wall"

    def test_transfer_count(self, w008):
        assert len(w008.transfers_received) == 2

    def test_c008_transfer(self, w008):
        """C008 transfers 100% to W008 at level 44."""
        t = next(t for t in w008.transfers_received if t.source_element == "C008")
        assert abs(t.percent - 1.0) < 0.01
        assert t.target_level == "44"
        assert t.dl_kn is not None
        assert t.dl_kn > 200  # ~220 kN


# ===========================================================================
# 24025 — 39 levels, 129 elements, empty metadata
# ===========================================================================

class TestParse24025:
    """Parse 24025 spreadsheet: empty metadata, mixed marks."""

    @pytest.fixture(scope="class")
    def result(self):
        return parse_rundown_spreadsheet(_FILE_24025)

    def test_empty_metadata(self, result):
        # Metadata cells are empty in this file
        assert result.project_number == ""
        assert result.job_name == ""

    def test_no_errors(self, result):
        assert result.errors == []

    def test_load_types_count(self, result):
        assert len(result.load_types) == 25

    def test_levels_count(self, result):
        assert len(result.levels) == 39

    def test_first_level(self, result):
        assert result.levels[0].bot_level == "MPH_MEZ"
        assert result.levels[0].top_level == "ROOF"

    def test_element_count(self, result):
        assert len(result.elements) == 129

    def test_imported_values_count(self, result):
        assert len(result.imported_values) == 129


class TestParse24025_Elements:
    """24025 element type classification and structure."""

    @pytest.fixture(scope="class")
    def result(self):
        return parse_rundown_spreadsheet(_FILE_24025)

    def test_column_count(self, result):
        cols = [e for e in result.elements if e.element_type == "Column"]
        assert len(cols) == 55

    def test_wall_count(self, result):
        walls = [e for e in result.elements if e.element_type == "Wall"]
        assert len(walls) == 74

    def test_parking_wall_type(self, result):
        pw1 = _find_element(result, "PW1")
        assert pw1.element_type == "Wall"

    def test_foundation_wall_type(self, result):
        fdn = _find_element(result, "!FDNW1")
        assert fdn.element_type == "Wall"

    def test_c1_floors(self, result):
        c1 = _find_element(result, "C1")
        assert len(c1.floors) == 39

    def test_c1_cladding(self, result):
        c1 = _find_element(result, "C1")
        assert c1.cladding_kpa == 1.5

    def test_c4_transfers(self, result):
        """C4 has a transfer from W60 at MPH level."""
        c4 = _find_element(result, "C4")
        assert len(c4.transfers_received) >= 1
        sources = {t.source_element for t in c4.transfers_received}
        assert "W60" in sources


# ===========================================================================
# Cross-file consistency tests
# ===========================================================================

class TestCrossFile:
    """Tests that span multiple spreadsheets."""

    def test_all_elements_have_floors(self):
        """Every element in all 3 files must have at least 1 floor."""
        for path in [_FILE_20205, _FILE_24043, _FILE_24025]:
            result = parse_rundown_spreadsheet(path)
            for e in result.elements:
                assert len(e.floors) > 0, f"{e.mark} in {path} has no floors"

    def test_area_codes_match_load_types(self):
        """Spot check: area codes used in elements exist in load types."""
        result = parse_rundown_spreadsheet(_FILE_20205)
        lt_codes = {lt.code for lt in result.load_types}
        for e in result.elements[:10]:  # sample first 10
            for f in e.floors:
                for code in f.area_by_type:
                    assert code in lt_codes, (
                        f"Unknown area code '{code}' in {e.mark}"
                    )

    def test_imported_dl_non_negative(self):
        """DL should be non-negative (cumulative dead load)."""
        result = parse_rundown_spreadsheet(_FILE_20205)
        for mark, vals in result.imported_values.items():
            for i, v in enumerate(vals):
                assert v.dl_kn >= 0, (
                    f"{mark} floor {i}: DL={v.dl_kn} is negative"
                )

    def test_imported_pf_ge_pw(self):
        """PF >= PW (factored always >= service for positive loads)."""
        result = parse_rundown_spreadsheet(_FILE_20205)
        for mark, vals in result.imported_values.items():
            for i, v in enumerate(vals):
                if v.pw_kn > 0:
                    assert v.pf_kn >= v.pw_kn - 0.01, (
                        f"{mark} floor {i}: PF={v.pf_kn} < PW={v.pw_kn}"
                    )


# ===========================================================================
# compare_results (unit test with mock data)
# ===========================================================================

class TestCompareResults:
    """Test compare_results function with synthetic data."""

    def test_no_discrepancies(self):
        """Matching values → empty list."""
        from unittest.mock import MagicMock

        comp = MagicMock()
        floor = MagicMock()
        floor.dl_cumulative_kn = 100.0
        floor.ll_cumulative_kn = 50.0
        floor.pw_kn = 150.0
        floor.pf_kn = 200.0
        floor.area_this_floor_m2 = 10.0
        floor.cum_area_m2 = 30.0
        floor.top_level = "5"
        elem = MagicMock()
        elem.mark = "C1"
        elem.floors = [floor]
        comp.elements = [elem]

        imp = {"C1": [SpreadsheetFloorValues(
            dl_kn=100.0, ll_kn=50.0, pw_kn=150.0, pf_kn=200.0,
            f_over_a_mpa=None, alpha=None, pct_steel=None, as_mm2=None,
            area_m2=10.0, xfer_area_m2=0.0, cum_area_m2=30.0,
            cross_section_m2=None,
        )]}

        discs = compare_results(comp, imp, tolerance_kn=0.5)
        assert len(discs) == 0

    def test_detects_discrepancy(self):
        """Different DL → one discrepancy."""
        from unittest.mock import MagicMock

        comp = MagicMock()
        floor = MagicMock()
        floor.dl_cumulative_kn = 100.0
        floor.ll_cumulative_kn = 50.0
        floor.pw_kn = 150.0
        floor.pf_kn = 200.0
        floor.area_this_floor_m2 = 10.0
        floor.cum_area_m2 = 30.0
        floor.top_level = "5"
        elem = MagicMock()
        elem.mark = "C1"
        elem.floors = [floor]
        comp.elements = [elem]

        imp = {"C1": [SpreadsheetFloorValues(
            dl_kn=105.0,  # 5 kN off
            ll_kn=50.0, pw_kn=150.0, pf_kn=200.0,
            f_over_a_mpa=None, alpha=None, pct_steel=None, as_mm2=None,
            area_m2=10.0, xfer_area_m2=0.0, cum_area_m2=30.0,
            cross_section_m2=None,
        )]}

        discs = compare_results(comp, imp, tolerance_kn=0.5)
        assert len(discs) == 1
        assert discs[0].field_name == "dl_kn"
        assert abs(discs[0].difference - 5.0) < 0.01

    def test_missing_element_no_error(self):
        """Element in computed but not in imported → no crash."""
        from unittest.mock import MagicMock

        comp = MagicMock()
        elem = MagicMock()
        elem.mark = "C99"
        elem.floors = []
        comp.elements = [elem]

        discs = compare_results(comp, {}, tolerance_kn=0.5)
        assert len(discs) == 0


# Need this import for compare_results tests
from rundown_engine.dtypes.spreadsheet import SpreadsheetFloorValues
