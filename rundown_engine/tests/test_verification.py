"""Verification tests — compare compute_rundown() against real Excel values.

Uses data extracted from two production spreadsheets:
  - 20205 TEMPLE (19 floors, 3 elements: W22, C2, W10A)
  - 24043 (50 floors, 5 elements: C029, C031, W008, W004, W008.3)

All expected values (DL, LL, PW, PF, cum_area) come from openpyxl data_only=True
reads of the original .xlsm files.  Transfers use pre-resolved values (spreadsheet
path), so each element is independently testable.
"""

from __future__ import annotations

import pytest

from rundown_engine.compute import compute_rundown
from rundown_engine.dtypes import (
    ElementDimensions,
    ElementInput,
    FloorInput,
    LevelPair,
    LoadTypeDef,
    RundownInput,
    TransferDef,
)

from . import data_20205 as d20205
from . import data_24043 as d24043


# ===================================================================
# Helpers — convert dict-based data to engine dataclasses
# ===================================================================

def _build_load_types(raw: list[dict]) -> list[LoadTypeDef]:
    """Convert raw load type dicts → LoadTypeDef list."""
    result = []
    for lt in raw:
        result.append(LoadTypeDef(
            code=lt.get("code", lt.get("name", "")),
            description=lt.get("description", lt.get("name", "")),
            dead_kpa=lt["dl"],
            live_kpa=lt["ll"],
            llrf_type=lt["reduction"],
        ))
    return result


def _build_floor(level_pair: dict, floor_data: dict | None) -> FloorInput:
    """Build a FloorInput from level pair + optional floor data.

    If floor_data is None, builds a zero/absent floor.
    """
    lp = LevelPair(
        bot_level=str(level_pair["bot"]),
        top_level=str(level_pair["top"]),
        story_height_m=floor_data["ht"] if floor_data else 3.0,
        concrete_mpa=floor_data["fc"] if floor_data else 30.0,
    )

    if floor_data is None or floor_data.get("dim_x") is None:
        dims = None
    else:
        dims = ElementDimensions(
            dim_x_mm=floor_data["dim_x"],
            dim_y=floor_data["dim_y"],
        )

    if floor_data is None:
        areas = {}
        bm = 0.0
        cw = 0.0
    else:
        areas = dict(floor_data.get("areas_by_type", {}))
        bm = floor_data.get("bm") or 0.0
        cw = floor_data.get("cw") or 0.0

    return FloorInput(
        level=lp,
        dimensions=dims,
        area_by_type=areas,
        beam_weight_kn=bm,
        cladding_perimeter_m=cw,
    )


def _build_element(
    elem_data: dict,
    level_pairs: list[dict],
) -> ElementInput:
    """Build ElementInput, filling missing floors from level_pairs."""
    # Index element floors by (bot, top) for lookup
    floor_lookup: dict[tuple[str, str], dict] = {}
    for f in elem_data["floors"]:
        key = (str(f["bot"]), str(f["top"]))
        floor_lookup[key] = f

    # Build full floor list from level pairs
    floors: list[FloorInput] = []
    for lp in level_pairs:
        key = (str(lp["bot"]), str(lp["top"]))
        floor_data = floor_lookup.get(key)
        floors.append(_build_floor(lp, floor_data))

    # Build transfers
    transfers: list[TransferDef] = []
    for t in elem_data.get("transfers", []):
        transfers.append(TransferDef(
            source_element=t["source"],
            target_level=str(t["level"]),
            percent=t["percent"],
            dl_kn=t.get("dl"),
            ll_kn=t.get("ll"),
            cum_area_m2=t.get("cum_area"),
        ))

    mark = elem_data["mark"]
    etype = "Wall" if mark.upper().startswith("W") else "Column"

    return ElementInput(
        mark=mark,
        element_type=etype,
        floors=floors,
        transfers_received=transfers,
        cladding_kpa=elem_data.get("cladding_kpa", 0.0),
    )


def _build_rundown_input(
    project_number: str,
    load_types_raw: list[dict],
    level_pairs: list[dict],
    elements_raw: list[dict],
) -> RundownInput:
    """Build full RundownInput from raw data."""
    return RundownInput(
        project_number=project_number,
        load_types=_build_load_types(load_types_raw),
        elements=[_build_element(e, level_pairs) for e in elements_raw],
    )


def _get_expected(elem_data: dict) -> list[dict]:
    """Return the floor data list with expected values (from Excel)."""
    return elem_data["floors"]


def _verify_element(result_elements, mark: str, elem_data: dict,
                    level_pairs: list[dict], tol_kn: float = 0.5,
                    tol_area: float = 0.5):
    """Verify one element's computed results against expected Excel values.

    Checks DL, LL, PW, PF, cum_area at every floor where expected != 0.
    Uses absolute tolerance (kN for loads, m² for areas).
    """
    # Find result for this element
    matches = [e for e in result_elements if e.mark == mark]
    assert len(matches) == 1, f"Expected 1 result for {mark}, got {len(matches)}"
    computed = matches[0]

    expected_floors = elem_data["floors"]

    # Build lookup of expected floors by (bot, top)
    expected_by_level: dict[tuple[str, str], dict] = {}
    for ef in expected_floors:
        key = (str(ef["bot"]), str(ef["top"]))
        expected_by_level[key] = ef

    errors: list[str] = []

    for i, cf in enumerate(computed.floors):
        key = (cf.bot_level, cf.top_level)
        ef = expected_by_level.get(key)

        if ef is None:
            # Floor not in expected data — should be a zero/absent floor
            continue

        exp_dl = ef["dl"]
        exp_ll = ef["ll"]
        exp_pw = ef["pw"]
        exp_pf = ef["pf"]
        exp_cum = ef["cum_area"]

        # Skip completely zero floors (no data to verify)
        if exp_dl == 0 and exp_ll == 0 and exp_pw == 0 and exp_pf == 0:
            # Still verify computed is zero
            if cf.dl_cumulative_kn > tol_kn:
                errors.append(
                    f"  {mark} floor {i} ({key}): expected zero DL, "
                    f"got {cf.dl_cumulative_kn:.4f}"
                )
            continue

        # Check DL
        if abs(cf.dl_cumulative_kn - exp_dl) > tol_kn:
            errors.append(
                f"  {mark} floor {i} ({key}): DL expected={exp_dl:.4f}, "
                f"got={cf.dl_cumulative_kn:.4f}, diff={cf.dl_cumulative_kn - exp_dl:.4f}"
            )

        # Check LL
        if abs(cf.ll_cumulative_kn - exp_ll) > tol_kn:
            errors.append(
                f"  {mark} floor {i} ({key}): LL expected={exp_ll:.4f}, "
                f"got={cf.ll_cumulative_kn:.4f}, diff={cf.ll_cumulative_kn - exp_ll:.4f}"
            )

        # Check PW
        if abs(cf.pw_kn - exp_pw) > tol_kn:
            errors.append(
                f"  {mark} floor {i} ({key}): PW expected={exp_pw:.4f}, "
                f"got={cf.pw_kn:.4f}, diff={cf.pw_kn - exp_pw:.4f}"
            )

        # Check PF
        if abs(cf.pf_kn - exp_pf) > tol_kn:
            errors.append(
                f"  {mark} floor {i} ({key}): PF expected={exp_pf:.4f}, "
                f"got={cf.pf_kn:.4f}, diff={cf.pf_kn - exp_pf:.4f}"
            )

        # Check cum_area
        if abs(cf.cum_area_m2 - exp_cum) > tol_area:
            errors.append(
                f"  {mark} floor {i} ({key}): CUM_AREA expected={exp_cum:.4f}, "
                f"got={cf.cum_area_m2:.4f}, diff={cf.cum_area_m2 - exp_cum:.4f}"
            )

    if errors:
        msg = f"\n{mark}: {len(errors)} mismatches:\n" + "\n".join(errors)
        pytest.fail(msg)


# ===================================================================
# 20205 TEMPLE — 19 floors, 3 elements
# ===================================================================

class TestVerification20205:
    """Verify engine output against 20205 TEMPLE spreadsheet values."""

    @pytest.fixture(scope="class")
    def result_20205(self):
        """Compute once for all 20205 tests."""
        inp = _build_rundown_input(
            "20205",
            d20205.LOAD_TYPES_20205,
            d20205.LEVEL_PAIRS_20205,
            [d20205.ELEMENT_W22, d20205.ELEMENT_C2, d20205.ELEMENT_W10A],
        )
        return compute_rundown(inp)

    def test_w22_all_floors(self, result_20205):
        """W22: tower wall, 19 floors, no transfers, MECP→AME→RES progression."""
        _verify_element(
            result_20205.elements, "W22", d20205.ELEMENT_W22,
            d20205.LEVEL_PAIRS_20205,
        )

    def test_c2_all_floors(self, result_20205):
        """C2: tower column, receives transfer from C2.2 at level 13."""
        _verify_element(
            result_20205.elements, "C2", d20205.ELEMENT_C2,
            d20205.LEVEL_PAIRS_20205,
        )

    def test_w10a_all_floors(self, result_20205):
        """W10A: wall active only at AMENITY and 14, then absent."""
        _verify_element(
            result_20205.elements, "W10A", d20205.ELEMENT_W10A,
            d20205.LEVEL_PAIRS_20205,
        )

    def test_element_count(self, result_20205):
        """All 3 elements computed."""
        assert len(result_20205.elements) == 3

    def test_input_order_preserved(self, result_20205):
        """Result order matches input order."""
        marks = [e.mark for e in result_20205.elements]
        assert marks == ["W22", "C2", "W10A"]


# ===================================================================
# 24043 — 50 floors, 5 elements
# ===================================================================

class TestVerification24043:
    """Verify engine output against 24043 spreadsheet values."""

    @pytest.fixture(scope="class")
    def result_24043(self):
        """Compute once for all 24043 tests."""
        inp = _build_rundown_input(
            "24043",
            d24043.LOAD_TYPES_24043,
            d24043.LEVEL_PAIRS_24043,
            [
                d24043.ELEMENT_C029,
                d24043.ELEMENT_C031,
                d24043.ELEMENT_W008,
                d24043.ELEMENT_W004,
                d24043.ELEMENT_W008_3,
            ],
        )
        return compute_rundown(inp)

    def test_c029_all_floors(self, result_24043):
        """C029: 50 floors, circular (dim_y='D'), 3 transfers at level 3."""
        _verify_element(
            result_24043.elements, "C029", d24043.ELEMENT_C029,
            d24043.LEVEL_PAIRS_24043,
        )

    def test_c031_all_floors(self, result_24043):
        """C031: 50 floors, rectangular column, 1 transfer."""
        _verify_element(
            result_24043.elements, "C031", d24043.ELEMENT_C031,
            d24043.LEVEL_PAIRS_24043,
        )

    def test_w008_all_floors(self, result_24043):
        """W008: large wall, 50 floors, multiple area types."""
        _verify_element(
            result_24043.elements, "W008", d24043.ELEMENT_W008,
            d24043.LEVEL_PAIRS_24043,
        )

    def test_w004_all_floors(self, result_24043):
        """W004: wall with transfers, parking/ramp areas."""
        _verify_element(
            result_24043.elements, "W004", d24043.ELEMENT_W004,
            d24043.LEVEL_PAIRS_24043,
        )

    def test_w008_3_all_floors(self, result_24043):
        """W008.3: receives 110% transfer from W008, only 12 active floors."""
        _verify_element(
            result_24043.elements, "W008.3", d24043.ELEMENT_W008_3,
            d24043.LEVEL_PAIRS_24043,
        )

    def test_element_count(self, result_24043):
        """All 5 elements computed."""
        assert len(result_24043.elements) == 5

    def test_input_order_preserved(self, result_24043):
        """Result order matches input order."""
        marks = [e.mark for e in result_24043.elements]
        assert marks == ["C029", "C031", "W008", "W004", "W008.3"]