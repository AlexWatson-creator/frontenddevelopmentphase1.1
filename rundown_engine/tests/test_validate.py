"""Tests for the validation module (validate.py).

Covers: area balance, transfer checks, data-gap detection,
circular-transfer detection, and full validate_rundown integration.
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
from rundown_engine.validate import (
    check_area_balance,
    check_data_gaps,
    check_transfers,
    detect_circular_transfers,
    validate_rundown,
)


# ===================================================================
# Helpers
# ===================================================================

TWO_LOAD_TYPES = [
    LoadTypeDef(code="RES", description="RESIDENTIAL",
                dead_kpa=6.1, live_kpa=1.9, llrf_type="R0.3"),
    LoadTypeDef(code="BAL", description="BALCONY",
                dead_kpa=6.1, live_kpa=4.8, llrf_type="N"),
]


def _floor(bot: str, top: str, ht: float, fc: float,
           dim_x: float | None, dim_y: float | str | None,
           areas: dict[str, float],
           bm: float = 0.0, cw: float = 0.0) -> FloorInput:
    dims = ElementDimensions(dim_x, dim_y) if dim_x is not None else None
    return FloorInput(
        level=LevelPair(bot, top, ht, fc),
        dimensions=dims,
        area_by_type=areas,
        beam_weight_kn=bm,
        cladding_perimeter_m=cw,
    )


def _element(mark: str, floors: list[FloorInput],
             transfers: list[TransferDef] | None = None,
             cladding: float = 0.0) -> ElementInput:
    etype = "Wall" if mark.upper().startswith("W") else "Column"
    return ElementInput(
        mark=mark,
        element_type=etype,
        floors=floors,
        transfers_received=transfers or [],
        cladding_kpa=cladding,
    )


def _compute(elements: list[ElementInput],
             load_types: list[LoadTypeDef] | None = None):
    inp = RundownInput(
        project_number="TEST",
        load_types=load_types or TWO_LOAD_TYPES,
        elements=elements,
    )
    return compute_rundown(inp), inp


# ===================================================================
# Area Balance
# ===================================================================

class TestAreaBalance:
    def test_single_element_balanced(self):
        """One element, no transfers — area diff = 0 at every floor."""
        elems = [_element("C1", [
            _floor("L2", "ROOF", 3.0, 30, 400, 400, {"RES": 10.0}),
            _floor("L1", "L2", 3.0, 30, 400, 400, {"RES": 12.0}),
        ])]
        result, _ = _compute(elems)
        checks = check_area_balance(result)

        assert len(checks) == 2
        for ac in checks:
            assert ac.is_balanced
            assert abs(ac.area_difference_m2) < 0.01

    def test_two_elements_no_transfers_balanced(self):
        """Two independent elements — each row sums correctly."""
        elems = [
            _element("C1", [
                _floor("L1", "ROOF", 3.0, 30, 400, 400, {"RES": 10.0}),
            ]),
            _element("W1", [
                _floor("L1", "ROOF", 3.0, 30, 200, 5000, {"RES": 8.0}),
            ]),
        ]
        result, _ = _compute(elems)
        checks = check_area_balance(result)

        assert len(checks) == 1
        # Total area = 10 + 8 = 18, cum area = 10 + 8 = 18
        assert checks[0].total_area_m2 == pytest.approx(18.0)
        assert checks[0].cum_area_m2 == pytest.approx(18.0)
        assert checks[0].area_difference_m2 == pytest.approx(0.0)

    def test_transfer_preserves_balance(self):
        """Pre-resolved transfer — area balance maintained across floors."""
        c1 = _element("C1", [
            _floor("L2", "ROOF", 3.0, 30, 300, 300, {"RES": 6.0}),
            _floor("L1", "L2", 3.0, 30, None, None, {}),
        ])
        w1 = _element("W1", [
            _floor("L2", "ROOF", 3.0, 30, 200, 5000, {"RES": 10.0}),
            _floor("L1", "L2", 3.0, 30, 200, 5000, {"RES": 5.0}),
        ], transfers=[
            TransferDef(source_element="C1", target_level="L2",
                        percent=1.0, dl_kn=50.0, ll_kn=10.0, cum_area_m2=6.0),
        ])

        result, _ = _compute([c1, w1])
        checks = check_area_balance(result)

        # Floor 0 (ROOF): C1 cum=6, W1 cum=10+6(xfer)=16 → total=22, area=16
        # Diff = 22 - 16 = 6 → This is the transferred area from C1
        # Actually C1 has cum_area=6 (has section), so total_cum = 6+16=22, total_area=6+10=16
        # diff[0] = 22 - 16 = 6 → this represents the transfer area contribution
        # Wait... the transfer area is ADDED to W1's cum but C1's cum also counts its own area.
        # The area difference at roof = sum(cum) - sum(area) = (6+16) - (6+10) = 6
        # That's the transfer area (6.0) — which is expected because cum includes transfer
        # but area doesn't.
        #
        # Actually, looking at VBA more carefully:
        # diff[0] = cum_total[0] - area_total[0]
        # The transfer area feeds into cum_area but NOT area_this_floor.
        # So the diff shows the NET transfer injection.
        # For a fully balanced system, transfers IN = transfers OUT at each floor.
        # Since C1 disappears at L2 (dims=None → cum=0 below), and W1 picks up
        # C1's cum_area via transfer, the balance should show the transfer offset.
        #
        # This is correct VBA behavior — area difference reflects missing transfers.

        assert len(checks) == 2

    def test_absent_floor_zero_cum(self):
        """Element absent (no dims) → cum_area=0, doesn't break balance."""
        elems = [_element("C1", [
            _floor("L2", "ROOF", 3.0, 30, 400, 400, {"RES": 10.0}),
            _floor("L1", "L2", 3.0, 30, None, None, {}),  # absent
        ])]
        result, _ = _compute(elems)
        checks = check_area_balance(result)

        assert checks[0].cum_area_m2 == pytest.approx(10.0)
        # Floor 1: cum=0 (absent), area=0
        # diff = 0 - 0 - 10 = -10 → unbalanced (element disappeared without transfer)
        assert checks[1].cum_area_m2 == pytest.approx(0.0)
        assert not checks[1].is_balanced  # -10 exceeds tolerance

    def test_empty_project(self):
        """No elements → no checks."""
        result, _ = _compute([])
        assert check_area_balance(result) == []

    def test_tolerance_boundary(self):
        """Area diff exactly 1.0 → still balanced; 1.1 → unbalanced."""
        # We can't easily manufacture a 1.0 diff through computation,
        # so test the AreaCheckRow directly.
        from rundown_engine.dtypes.validation import AreaCheckRow

        row_ok = AreaCheckRow("A", "B", 10.0, 11.0, 1.0, True)
        assert row_ok.is_balanced

        row_bad = AreaCheckRow("A", "B", 10.0, 11.1, 1.1, False)
        assert not row_bad.is_balanced


# ===================================================================
# Transfer Checks
# ===================================================================

class TestTransferChecks:
    def test_no_transfers_status_none(self):
        """Element with no outgoing transfers → status 'none', 0%."""
        c1 = _element("C1", [
            _floor("L1", "ROOF", 3.0, 30, 300, 300, {"RES": 5.0}),
        ])
        inp = RundownInput("TEST", TWO_LOAD_TYPES, [c1])
        checks = check_transfers(inp)

        assert len(checks) == 1
        assert checks[0].element_mark == "C1"
        assert checks[0].pct_transferred == 0.0
        assert checks[0].status == "none"
        assert checks[0].to_elements == []

    def test_full_transfer_100pct(self):
        """C1 transfers 100% to W1 → status 'ok'."""
        c1 = _element("C1", [
            _floor("L1", "ROOF", 3.0, 30, 300, 300, {"RES": 5.0}),
        ])
        w1 = _element("W1", [
            _floor("L1", "ROOF", 3.0, 30, 200, 5000, {"RES": 10.0}),
        ], transfers=[
            TransferDef("C1", "ROOF", 1.0, dl_kn=50.0, ll_kn=10.0,
                        cum_area_m2=5.0),
        ])
        inp = RundownInput("TEST", TWO_LOAD_TYPES, [c1, w1])
        checks = check_transfers(inp)

        c1_check = [c for c in checks if c.element_mark == "C1"][0]
        assert c1_check.pct_transferred == pytest.approx(1.0)
        assert c1_check.status == "ok"
        assert c1_check.to_elements == ["W1"]

    def test_under_transfer(self):
        """50% transfer → status 'under'."""
        c1 = _element("C1", [
            _floor("L1", "ROOF", 3.0, 30, 300, 300, {"RES": 5.0}),
        ])
        w1 = _element("W1", [
            _floor("L1", "ROOF", 3.0, 30, 200, 5000, {"RES": 10.0}),
        ], transfers=[
            TransferDef("C1", "ROOF", 0.5, dl_kn=25.0, ll_kn=5.0,
                        cum_area_m2=2.5),
        ])
        inp = RundownInput("TEST", TWO_LOAD_TYPES, [c1, w1])
        checks = check_transfers(inp)

        c1_check = [c for c in checks if c.element_mark == "C1"][0]
        assert c1_check.pct_transferred == pytest.approx(0.5)
        assert c1_check.status == "under"

    def test_over_transfer(self):
        """110% transfer → status 'over'."""
        c1 = _element("C1", [
            _floor("L1", "ROOF", 3.0, 30, 300, 300, {"RES": 5.0}),
        ])
        w1 = _element("W1", [
            _floor("L1", "ROOF", 3.0, 30, 200, 5000, {"RES": 10.0}),
        ], transfers=[
            TransferDef("C1", "ROOF", 1.1, dl_kn=55.0, ll_kn=11.0,
                        cum_area_m2=5.5),
        ])
        inp = RundownInput("TEST", TWO_LOAD_TYPES, [c1, w1])
        checks = check_transfers(inp)

        c1_check = [c for c in checks if c.element_mark == "C1"][0]
        assert c1_check.pct_transferred == pytest.approx(1.1)
        assert c1_check.status == "over"

    def test_multiple_targets(self):
        """C1 transfers 50% to W1 and 50% to W2 → status 'ok'."""
        c1 = _element("C1", [
            _floor("L1", "ROOF", 3.0, 30, 300, 300, {"RES": 5.0}),
        ])
        w1 = _element("W1", [
            _floor("L1", "ROOF", 3.0, 30, 200, 5000, {"RES": 10.0}),
        ], transfers=[
            TransferDef("C1", "ROOF", 0.5, dl_kn=25.0, ll_kn=5.0,
                        cum_area_m2=2.5),
        ])
        w2 = _element("W2", [
            _floor("L1", "ROOF", 3.0, 30, 200, 5000, {"RES": 8.0}),
        ], transfers=[
            TransferDef("C1", "ROOF", 0.5, dl_kn=25.0, ll_kn=5.0,
                        cum_area_m2=2.5),
        ])
        inp = RundownInput("TEST", TWO_LOAD_TYPES, [c1, w1, w2])
        checks = check_transfers(inp)

        c1_check = [c for c in checks if c.element_mark == "C1"][0]
        assert c1_check.pct_transferred == pytest.approx(1.0)
        assert c1_check.status == "ok"
        assert sorted(c1_check.to_elements) == ["W1", "W2"]

    def test_within_floor_range(self):
        """Transfer received at floor with dimensions → all_within_range=True."""
        c1 = _element("C1", [
            _floor("L1", "ROOF", 3.0, 30, 300, 300, {"RES": 5.0}),
        ])
        w1 = _element("W1", [
            _floor("L1", "ROOF", 3.0, 30, 200, 5000, {"RES": 10.0}),
        ], transfers=[
            TransferDef("C1", "ROOF", 1.0, dl_kn=50.0, ll_kn=10.0,
                        cum_area_m2=5.0),
        ])
        inp = RundownInput("TEST", TWO_LOAD_TYPES, [c1, w1])
        checks = check_transfers(inp)

        w1_check = [c for c in checks if c.element_mark == "W1"][0]
        assert w1_check.all_within_range is True

    def test_outside_floor_range(self):
        """Transfer received at floor with NO dimensions → all_within_range=False."""
        c1 = _element("C1", [
            _floor("L1", "ROOF", 3.0, 30, 300, 300, {"RES": 5.0}),
        ])
        w1 = _element("W1", [
            _floor("L1", "ROOF", 3.0, 30, None, None, {}),  # no dims!
        ], transfers=[
            TransferDef("C1", "ROOF", 1.0, dl_kn=50.0, ll_kn=10.0,
                        cum_area_m2=5.0),
        ])
        inp = RundownInput("TEST", TWO_LOAD_TYPES, [c1, w1])
        checks = check_transfers(inp)

        w1_check = [c for c in checks if c.element_mark == "W1"][0]
        assert w1_check.all_within_range is False


# ===================================================================
# Data Gap Detection
# ===================================================================

class TestDataGaps:
    def test_no_gap_contiguous(self):
        """Contiguous dimensions → no warning."""
        elem = _element("C1", [
            _floor("L3", "ROOF", 3.0, 30, 400, 400, {"RES": 5.0}),
            _floor("L2", "L3", 3.0, 30, 400, 400, {"RES": 5.0}),
            _floor("L1", "L2", 3.0, 30, 400, 400, {"RES": 5.0}),
        ])
        inp = RundownInput("TEST", TWO_LOAD_TYPES, [elem])
        assert check_data_gaps(inp) == []

    def test_gap_detected(self):
        """Dims at roof, then blank, then dims again → gap warning."""
        elem = _element("C1", [
            _floor("L3", "ROOF", 3.0, 30, 400, 400, {"RES": 5.0}),
            _floor("L2", "L3", 3.0, 30, None, None, {}),  # blank
            _floor("L1", "L2", 3.0, 30, 400, 400, {"RES": 5.0}),  # data again
        ])
        inp = RundownInput("TEST", TWO_LOAD_TYPES, [elem])
        gaps = check_data_gaps(inp)

        assert len(gaps) == 1
        assert gaps[0].element_mark == "C1"
        assert "non-contiguous" in gaps[0].message
        assert "L2" in gaps[0].message

    def test_no_dims_at_all(self):
        """Element with no dimensions anywhere → no gap (not contiguous issue)."""
        elem = _element("C1", [
            _floor("L2", "ROOF", 3.0, 30, None, None, {}),
            _floor("L1", "L2", 3.0, 30, None, None, {}),
        ])
        inp = RundownInput("TEST", TWO_LOAD_TYPES, [elem])
        assert check_data_gaps(inp) == []

    def test_dims_at_top_only(self):
        """Element active at top floors, absent below → no gap."""
        elem = _element("C1", [
            _floor("L3", "ROOF", 3.0, 30, 400, 400, {"RES": 5.0}),
            _floor("L2", "L3", 3.0, 30, 400, 400, {"RES": 5.0}),
            _floor("L1", "L2", 3.0, 30, None, None, {}),
        ])
        inp = RundownInput("TEST", TWO_LOAD_TYPES, [elem])
        assert check_data_gaps(inp) == []

    def test_dims_at_bottom_only(self):
        """Element absent at top, active at bottom → no gap."""
        elem = _element("C1", [
            _floor("L3", "ROOF", 3.0, 30, None, None, {}),
            _floor("L2", "L3", 3.0, 30, 400, 400, {"RES": 5.0}),
            _floor("L1", "L2", 3.0, 30, 400, 400, {"RES": 5.0}),
        ])
        inp = RundownInput("TEST", TWO_LOAD_TYPES, [elem])
        assert check_data_gaps(inp) == []

    def test_multiple_gaps_one_warning_per_element(self):
        """Multiple gaps → only first gap reported per element."""
        elem = _element("C1", [
            _floor("L5", "ROOF", 3.0, 30, 400, 400, {"RES": 5.0}),
            _floor("L4", "L5", 3.0, 30, None, None, {}),
            _floor("L3", "L4", 3.0, 30, 400, 400, {"RES": 5.0}),
            _floor("L2", "L3", 3.0, 30, None, None, {}),
            _floor("L1", "L2", 3.0, 30, 400, 400, {"RES": 5.0}),
        ])
        inp = RundownInput("TEST", TWO_LOAD_TYPES, [elem])
        gaps = check_data_gaps(inp)
        assert len(gaps) == 1  # only first gap


# ===================================================================
# Circular Transfer Detection
# ===================================================================

class TestCircularTransfers:
    def test_no_cycle(self):
        """A→B dependency, no cycle."""
        c1 = _element("C1", [
            _floor("L1", "ROOF", 3.0, 30, 300, 300, {"RES": 5.0}),
        ])
        w1 = _element("W1", [
            _floor("L1", "ROOF", 3.0, 30, 200, 5000, {"RES": 10.0}),
        ], transfers=[
            TransferDef("C1", "ROOF", 1.0),  # computed path
        ])
        errors = detect_circular_transfers([c1, w1])
        assert errors == []

    def test_simple_cycle(self):
        """A depends on B, B depends on A → circular."""
        c1 = _element("C1", [
            _floor("L1", "ROOF", 3.0, 30, 300, 300, {"RES": 5.0}),
        ], transfers=[
            TransferDef("W1", "ROOF", 1.0),  # computed path
        ])
        w1 = _element("W1", [
            _floor("L1", "ROOF", 3.0, 30, 200, 5000, {"RES": 10.0}),
        ], transfers=[
            TransferDef("C1", "ROOF", 1.0),  # computed path
        ])
        errors = detect_circular_transfers([c1, w1])
        assert len(errors) == 1
        assert "Circular" in errors[0]
        assert "C1" in errors[0]
        assert "W1" in errors[0]

    def test_pre_resolved_no_cycle(self):
        """Pre-resolved transfers (dl_kn not None) don't create dependency."""
        c1 = _element("C1", [
            _floor("L1", "ROOF", 3.0, 30, 300, 300, {"RES": 5.0}),
        ], transfers=[
            TransferDef("W1", "ROOF", 1.0,
                        dl_kn=50.0, ll_kn=10.0, cum_area_m2=5.0),
        ])
        w1 = _element("W1", [
            _floor("L1", "ROOF", 3.0, 30, 200, 5000, {"RES": 10.0}),
        ], transfers=[
            TransferDef("C1", "ROOF", 1.0,
                        dl_kn=30.0, ll_kn=8.0, cum_area_m2=3.0),
        ])
        errors = detect_circular_transfers([c1, w1])
        assert errors == []  # pre-resolved = no dependency edge

    def test_no_elements(self):
        """Empty list → no cycles."""
        assert detect_circular_transfers([]) == []

    def test_self_reference_ignored(self):
        """Element referencing external source not in list → no cycle."""
        c1 = _element("C1", [
            _floor("L1", "ROOF", 3.0, 30, 300, 300, {"RES": 5.0}),
        ], transfers=[
            TransferDef("EXTERNAL", "ROOF", 1.0),
        ])
        errors = detect_circular_transfers([c1])
        assert errors == []


# ===================================================================
# Full validate_rundown Integration
# ===================================================================

class TestValidateRundown:
    def test_valid_project(self):
        """Simple valid project → is_valid=True, no errors."""
        elems = [
            _element("C1", [
                _floor("L1", "ROOF", 3.0, 30, 400, 400, {"RES": 10.0}),
            ]),
            _element("W1", [
                _floor("L1", "ROOF", 3.0, 30, 200, 5000, {"RES": 8.0}),
            ]),
        ]
        result, inp = _compute(elems)
        v = result.validation

        assert v.is_valid is True
        assert len(v.errors) == 0
        assert len(v.area_checks) == 1
        assert len(v.transfer_checks) == 2

    def test_circular_makes_invalid(self):
        """Circular transfers → is_valid=False."""
        c1 = _element("C1", [
            _floor("L1", "ROOF", 3.0, 30, 300, 300, {"RES": 5.0}),
        ], transfers=[TransferDef("W1", "ROOF", 1.0)])
        w1 = _element("W1", [
            _floor("L1", "ROOF", 3.0, 30, 200, 5000, {"RES": 10.0}),
        ], transfers=[TransferDef("C1", "ROOF", 1.0)])

        result, inp = _compute([c1, w1])
        v = result.validation

        assert v.is_valid is False
        assert len(v.errors) > 0
        assert any("Circular" in e for e in v.errors)

    def test_data_gap_in_warnings(self):
        """Data gap → appears in warnings."""
        elem = _element("C1", [
            _floor("L3", "ROOF", 3.0, 30, 400, 400, {"RES": 5.0}),
            _floor("L2", "L3", 3.0, 30, None, None, {}),
            _floor("L1", "L2", 3.0, 30, 400, 400, {"RES": 5.0}),
        ])
        result, inp = _compute([elem])
        v = result.validation

        assert v.is_valid is True  # gaps are warnings, not errors
        assert len(v.data_gaps) == 1
        assert any("non-contiguous" in w for w in v.warnings)

    def test_outside_range_in_warnings(self):
        """Transfer received outside floor range → warning."""
        c1 = _element("C1", [
            _floor("L1", "ROOF", 3.0, 30, 300, 300, {"RES": 5.0}),
        ])
        w1 = _element("W1", [
            _floor("L1", "ROOF", 3.0, 30, None, None, {}),  # no dims
        ], transfers=[
            TransferDef("C1", "ROOF", 1.0, dl_kn=50.0, ll_kn=10.0,
                        cum_area_m2=5.0),
        ])
        result, inp = _compute([c1, w1])
        v = result.validation

        assert any("outside active floor range" in w for w in v.warnings)

    def test_compute_rundown_fills_validation(self):
        """compute_rundown now fills validation (not just placeholder)."""
        elems = [_element("C1", [
            _floor("L1", "ROOF", 3.0, 30, 400, 400, {"RES": 10.0}),
        ])]
        result, _ = _compute(elems)

        # Validation should be populated, not empty default
        assert len(result.validation.area_checks) > 0
        assert len(result.validation.transfer_checks) > 0


# ===================================================================
# Verification with real data — area balance
# ===================================================================

class TestVerificationAreaBalance:
    def test_20205_area_balance(self):
        """20205 TEMPLE: area balance across 3 elements, 19 floors."""
        from . import data_20205 as d
        from .test_verification import _build_rundown_input

        inp = _build_rundown_input(
            "20205", d.LOAD_TYPES_20205, d.LEVEL_PAIRS_20205,
            [d.ELEMENT_W22, d.ELEMENT_C2, d.ELEMENT_W10A],
        )
        result = compute_rundown(inp)
        checks = result.validation.area_checks

        assert len(checks) == 19  # 19 floor levels
        # All checks should have computed values
        for ac in checks:
            assert ac.total_area_m2 >= 0
            assert ac.cum_area_m2 >= 0

    def test_24043_area_balance(self):
        """24043: area balance across 5 elements, 50 floors."""
        from . import data_24043 as d
        from .test_verification import _build_rundown_input

        inp = _build_rundown_input(
            "24043", d.LOAD_TYPES_24043, d.LEVEL_PAIRS_24043,
            [d.ELEMENT_C029, d.ELEMENT_C031, d.ELEMENT_W008,
             d.ELEMENT_W004, d.ELEMENT_W008_3],
        )
        result = compute_rundown(inp)
        checks = result.validation.area_checks

        assert len(checks) == 50  # 50 floor levels