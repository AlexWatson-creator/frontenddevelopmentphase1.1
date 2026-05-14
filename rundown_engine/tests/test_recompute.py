"""Tests for rebar recomputation (user override flow)."""
from rundown_engine.formulas import (
    compute_as,
    compute_cbars,
    compute_nbars,
    compute_qty,
    format_rebar_design,
)
from rundown_engine.recompute import RebarResult, recompute_rebar


# Shared test geometry: 500mm × 500mm square column, 30 MPa
DIM_X = 500.0
DIM_Y = 500.0  # numeric = rectangular (but square → 4-face)
CROSS_SECTION = 0.25  # 500×500 / 1e6
AS_MM2 = 2500.0  # example steel area


def _auto(bar_size: str = "20M") -> RebarResult:
    """Helper: full auto recompute."""
    return recompute_rebar(
        bar_size=bar_size,
        qty=None, n_bars=None, c_bars=None,
        qty_override=False, n_bars_override=False, c_bars_override=False,
        as_mm2=AS_MM2, dim_x_mm=DIM_X, dim_y=DIM_Y,
        cross_section_m2=CROSS_SECTION,
    )


class TestAllAuto:
    """All fields auto-computed from bar_size + As."""

    def test_auto_qty_matches_formula(self):
        r = _auto("20M")
        expected = compute_qty(AS_MM2, "20M", DIM_X, DIM_Y)
        assert r.qty == expected
        assert r.qty_auto is True

    def test_auto_nbars_matches_formula(self):
        r = _auto("20M")
        expected_qty = compute_qty(AS_MM2, "20M", DIM_X, DIM_Y)
        expected = compute_nbars(expected_qty, "20M", CROSS_SECTION)
        assert r.n_bars == expected
        assert r.n_bars_auto is True

    def test_auto_cbars_matches_formula(self):
        r = _auto("20M")
        expected_qty = compute_qty(AS_MM2, "20M", DIM_X, DIM_Y)
        expected_n = compute_nbars(expected_qty, "20M", CROSS_SECTION)
        expected = compute_cbars(expected_qty, expected_n)
        assert r.c_bars == expected
        assert r.c_bars_auto is True

    def test_auto_rebar_design(self):
        r = _auto("20M")
        assert r.rebar_design is not None
        assert "20M" in r.rebar_design


class TestQtyOverride:
    """User overrides qty — n_bars and c_bars still auto from it."""

    def test_qty_preserved(self):
        r = recompute_rebar(
            bar_size="20M", qty=12, n_bars=None, c_bars=None,
            qty_override=True, n_bars_override=False, c_bars_override=False,
            as_mm2=AS_MM2, dim_x_mm=DIM_X, dim_y=DIM_Y,
            cross_section_m2=CROSS_SECTION,
        )
        assert r.qty == 12
        assert r.qty_auto is False

    def test_nbars_derived_from_override_qty(self):
        r = recompute_rebar(
            bar_size="20M", qty=12, n_bars=None, c_bars=None,
            qty_override=True, n_bars_override=False, c_bars_override=False,
            as_mm2=AS_MM2, dim_x_mm=DIM_X, dim_y=DIM_Y,
            cross_section_m2=CROSS_SECTION,
        )
        expected_n = compute_nbars(12, "20M", CROSS_SECTION)
        assert r.n_bars == expected_n
        assert r.n_bars_auto is True

    def test_cbars_derived_from_override_qty(self):
        r = recompute_rebar(
            bar_size="20M", qty=12, n_bars=None, c_bars=None,
            qty_override=True, n_bars_override=False, c_bars_override=False,
            as_mm2=AS_MM2, dim_x_mm=DIM_X, dim_y=DIM_Y,
            cross_section_m2=CROSS_SECTION,
        )
        expected_n = compute_nbars(12, "20M", CROSS_SECTION)
        expected_c = compute_cbars(12, expected_n)
        assert r.c_bars == expected_c


class TestNoBarSize:
    """No bar_size → all rebar fields None."""

    def test_none_bar_size(self):
        r = recompute_rebar(
            bar_size=None, qty=None, n_bars=None, c_bars=None,
            qty_override=False, n_bars_override=False, c_bars_override=False,
            as_mm2=AS_MM2, dim_x_mm=DIM_X, dim_y=DIM_Y,
            cross_section_m2=CROSS_SECTION,
        )
        assert r.qty is None
        assert r.n_bars is None
        assert r.c_bars is None
        assert r.rebar_design is None

    def test_invalid_bar_size(self):
        r = recompute_rebar(
            bar_size="99M", qty=None, n_bars=None, c_bars=None,
            qty_override=False, n_bars_override=False, c_bars_override=False,
            as_mm2=AS_MM2, dim_x_mm=DIM_X, dim_y=DIM_Y,
            cross_section_m2=CROSS_SECTION,
        )
        assert r.qty is None
        assert r.rebar_design is None


class TestLargeBarAllCouplers:
    """Bar > 35M → n_bars=0, c_bars=qty (all couplers)."""

    def test_45m_all_couplers(self):
        r = _auto("45M")
        assert r.n_bars == 0
        assert r.c_bars == r.qty
        assert r.qty is not None and r.qty > 0


class TestMatchesComputeChain:
    """Recompute with all-auto matches the standalone formula chain."""

    def test_full_chain_20m(self):
        r = _auto("20M")
        qty = compute_qty(AS_MM2, "20M", DIM_X, DIM_Y)
        n = compute_nbars(qty, "20M", CROSS_SECTION)
        c = compute_cbars(qty, n)
        design = format_rebar_design("20M", n, c, CROSS_SECTION)
        assert r.qty == qty
        assert r.n_bars == n
        assert r.c_bars == c
        assert r.rebar_design == design

    def test_full_chain_35m(self):
        r = _auto("35M")
        qty = compute_qty(AS_MM2, "35M", DIM_X, DIM_Y)
        n = compute_nbars(qty, "35M", CROSS_SECTION)
        c = compute_cbars(qty, n)
        design = format_rebar_design("35M", n, c, CROSS_SECTION)
        assert r.qty == qty
        assert r.n_bars == n
        assert r.c_bars == c
        assert r.rebar_design == design


class TestNbarsOverride:
    """User overrides n_bars — c_bars auto-derived."""

    def test_nbars_override_cbars_auto(self):
        r = recompute_rebar(
            bar_size="20M", qty=None, n_bars=4, c_bars=None,
            qty_override=False, n_bars_override=True, c_bars_override=False,
            as_mm2=AS_MM2, dim_x_mm=DIM_X, dim_y=DIM_Y,
            cross_section_m2=CROSS_SECTION,
        )
        assert r.n_bars == 4
        assert r.n_bars_auto is False
        # c_bars = qty - n_bars (auto)
        assert r.c_bars == max((r.qty or 0) - 4, 0)
        assert r.c_bars_auto is True