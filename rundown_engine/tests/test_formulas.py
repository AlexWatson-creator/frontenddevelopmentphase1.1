"""Unit tests for rundown_engine.formulas.

Each test verifies one formula against known Excel values.
Reference: rundown-spreadsheet-read-me.md Section 5.
"""

from __future__ import annotations

import math

import pytest

from rundown_engine.formulas import (
    bar_area,
    compute_alpha,
    compute_as,
    compute_cbars,
    compute_cladding,
    compute_cross_section,
    compute_cum_area,
    compute_dl_floor_load,
    compute_f_over_a,
    compute_ll_non_reducible_by_type,
    compute_ll_reducible,
    compute_llrf,
    compute_nbars,
    compute_pct_steel,
    compute_pf,
    compute_phi,
    compute_pw,
    compute_qty,
    compute_self_weight,
    format_rebar_design,
)
from rundown_engine.dtypes import LoadTypeDef


# ===================================================================
# compute_cross_section — Col Z
# ===================================================================

class TestComputeCrossSection:
    """Z = IF(Y="D", 0.25*PI*(X/1000)^2, IF(Y="S", X, IF(Y="W", X/24, X*Y/1e6)))"""

    def test_rectangular_column(self):
        """400mm × 800mm → 0.32 m²."""
        assert compute_cross_section(400, 800) == pytest.approx(0.32)

    def test_rectangular_small(self):
        """250mm × 800mm → 0.20 m²."""
        assert compute_cross_section(250, 800) == pytest.approx(0.20)

    def test_square_column(self):
        """500mm × 500mm → 0.25 m²."""
        assert compute_cross_section(500, 500) == pytest.approx(0.25)

    def test_wall(self):
        """200mm × 15840mm → 3.168 m²."""
        assert compute_cross_section(200, 15840) == pytest.approx(3.168)

    def test_circular_column(self):
        """D=400mm → 0.25 × π × 0.4² = 0.12566... m²."""
        expected = 0.25 * math.pi * 0.4**2
        assert compute_cross_section(400, "D") == pytest.approx(expected)

    def test_circular_large(self):
        """D=600mm → 0.25 × π × 0.6² = 0.28274... m²."""
        expected = 0.25 * math.pi * 0.6**2
        assert compute_cross_section(600, "D") == pytest.approx(expected)

    def test_steel_section(self):
        """Steel: X is area directly (m²)."""
        assert compute_cross_section(0.015, "S") == pytest.approx(0.015)

    def test_special_w(self):
        """Special W: X/24."""
        assert compute_cross_section(48.0, "W") == pytest.approx(2.0)

    def test_dim_y_case_insensitive(self):
        """Y="d" should work like Y="D"."""
        expected = 0.25 * math.pi * 0.4**2
        assert compute_cross_section(400, "d") == pytest.approx(expected)

    def test_zero_dimensions(self):
        """0 × 0 → 0 m²."""
        assert compute_cross_section(0, 0) == pytest.approx(0.0)


# ===================================================================
# compute_llrf — Cols CA:CY
# ===================================================================

class TestComputeLLRF:
    """LLRF formulas verified against reference values."""

    def test_r03_below_threshold(self):
        """R0.3 with cum_area <= 20 → 1.0."""
        assert compute_llrf("R0.3", 15.0) == pytest.approx(1.0)

    def test_r03_at_threshold(self):
        """R0.3 with cum_area = 20 → 1.0 (not > 20)."""
        assert compute_llrf("R0.3", 20.0) == pytest.approx(1.0)

    def test_r03_above_threshold(self):
        """R0.3 with cum_area = 50 → 0.3 + sqrt(9.8/50) = 0.7427..."""
        expected = 0.3 + math.sqrt(9.8 / 50.0)
        assert compute_llrf("R0.3", 50.0) == pytest.approx(expected, abs=1e-4)

    def test_r03_large_area(self):
        """R0.3 with cum_area = 200 → 0.3 + sqrt(9.8/200)."""
        expected = 0.3 + math.sqrt(9.8 / 200.0)
        assert compute_llrf("R0.3", 200.0) == pytest.approx(expected, abs=1e-4)

    def test_r05_below_threshold(self):
        """R0.5 with cum_area <= 80 → 1.0."""
        assert compute_llrf("R0.5", 60.0) == pytest.approx(1.0)

    def test_r05_at_threshold(self):
        """R0.5 with cum_area = 80 → 1.0 (not > 80)."""
        assert compute_llrf("R0.5", 80.0) == pytest.approx(1.0)

    def test_r05_above_threshold(self):
        """R0.5 with cum_area = 100 → 0.5 + sqrt(20/100) = 0.9472..."""
        expected = 0.5 + math.sqrt(20.0 / 100.0)
        assert compute_llrf("R0.5", 100.0) == pytest.approx(expected, abs=1e-4)

    def test_non_reducible(self):
        """Type "N" → 0.0."""
        assert compute_llrf("N", 100.0) == pytest.approx(0.0)

    def test_non_reducible_zero_area(self):
        """Type "N" with zero area → 0.0."""
        assert compute_llrf("N", 0.0) == pytest.approx(0.0)


# ===================================================================
# compute_self_weight — Z × D × 24
# ===================================================================

class TestComputeSelfWeight:
    def test_basic(self):
        """0.2 m² × 2.95m × 24 = 14.16 kN."""
        assert compute_self_weight(0.2, 2.95) == pytest.approx(14.16)

    def test_zero_section(self):
        """No cross-section → 0 kN."""
        assert compute_self_weight(0.0, 3.0) == pytest.approx(0.0)

    def test_zero_height(self):
        """Zero height → 0 kN."""
        assert compute_self_weight(0.2, 0.0) == pytest.approx(0.0)

    def test_large_wall(self):
        """3.168 m² × 3.35m × 24 = 254.707 kN."""
        assert compute_self_weight(3.168, 3.35) == pytest.approx(254.7072, abs=0.01)


# ===================================================================
# compute_cladding — cladding_kPa × W × D[N-1]
# ===================================================================

class TestComputeCladding:
    def test_basic(self):
        """2.0 kPa × 4.6m × 3.35m = 30.82 kN."""
        assert compute_cladding(2.0, 4.6, 3.35) == pytest.approx(30.82)

    def test_topmost_floor(self):
        """At topmost floor, D[N-1] = 0 → no cladding."""
        assert compute_cladding(2.0, 4.6, 0.0) == pytest.approx(0.0)

    def test_no_perimeter(self):
        """No cladding perimeter → 0 kN."""
        assert compute_cladding(2.0, 0.0, 3.35) == pytest.approx(0.0)


# ===================================================================
# compute_dl_floor_load — SUMPRODUCT(DL_kPa, area)
# ===================================================================

class TestComputeDlFloorLoad:
    def test_single_type(self, load_type_lookup):
        """AMT: 5.3 kPa × 5.3 m² = 28.09 kN."""
        areas = {"AMT": 5.3}
        assert compute_dl_floor_load(areas, load_type_lookup) == pytest.approx(28.09)

    def test_multiple_types(self, load_type_lookup):
        """RES: 6.1×7.8=47.58, BAL: 6.1×2.0=12.2 → total 59.78."""
        areas = {"RES": 7.8, "BAL": 2.0}
        assert compute_dl_floor_load(areas, load_type_lookup) == pytest.approx(59.78)

    def test_empty_areas(self, load_type_lookup):
        """No areas → 0."""
        assert compute_dl_floor_load({}, load_type_lookup) == pytest.approx(0.0)

    def test_unknown_code_ignored(self, load_type_lookup):
        """Unknown code should be ignored (not crash)."""
        areas = {"RES": 5.0, "UNKNOWN": 10.0}
        assert compute_dl_floor_load(areas, load_type_lookup) == pytest.approx(6.1 * 5.0)

    def test_verified_20205_c1(self, load_type_lookup):
        """20205 C1 floor load component: AMT 5.3kPa × 5.3m² + RES 6.1kPa × 1.9m².
        Wait — verified value from spreadsheet-read-me says:
        (5.3×6.1 + 1.9×5.3) = 32.33 + 10.07 = 42.40
        But that mixes DL and LL. The DL component is:
        AMT dead=5.3kPa × 5.3m² = 28.09 kN  (just AMT type area 5.3m² with dead 5.3kPa)
        """
        # From the verified formula: SUMPRODUCT($AA$4:$AY$4, AA[N]:AY[N])
        # 20205 C1 row 10: AMT area = 5.3 m², AMT dead_kpa = 5.3 → 28.09
        # But the readme says (5.3×6.1 + 1.9×5.3) which means:
        # 5.3 m² × 6.1 kPa(RES dead?) + 1.9 m² × 5.3 kPa(AMT dead?)
        # This suggests the areas are: one type 5.3m² with dead=6.1, another 1.9m² with dead=5.3
        # Based on the load types: RES dead=6.1, AMT dead=5.3
        # So: RES area=5.3m² × 6.1kPa + AMT area=1.9m² × 5.3kPa = 32.33 + 10.07 = 42.40
        areas = {"RES": 5.3, "AMT": 1.9}
        expected = 5.3 * 6.1 + 1.9 * 5.3  # 32.33 + 10.07 = 42.40
        assert compute_dl_floor_load(areas, load_type_lookup) == pytest.approx(expected, abs=0.01)


# ===================================================================
# compute_ll_reducible — SUMPRODUCT(cum_area × LL_kPa × LLRF)
# ===================================================================

class TestComputeLlReducible:
    def test_single_reducible_type(self, load_type_lookup):
        """RES: cum_area=50, LL=1.9kPa, LLRF=0.7427 → 50×1.9×0.7427 = 70.56."""
        cum_areas = {"RES": 50.0}
        llrf = {"RES": 0.3 + math.sqrt(9.8 / 50.0)}
        expected = 50.0 * 1.9 * llrf["RES"]
        assert compute_ll_reducible(cum_areas, load_type_lookup, llrf) == pytest.approx(expected, abs=0.01)

    def test_non_reducible_type_zero_llrf(self, load_type_lookup):
        """BAL (type "N"): LLRF=0 → contributes nothing via reducible path."""
        cum_areas = {"BAL": 30.0}
        llrf = {"BAL": 0.0}
        assert compute_ll_reducible(cum_areas, load_type_lookup, llrf) == pytest.approx(0.0)

    def test_mixed_types(self, load_type_lookup):
        """RES(R0.3) + BAL(N): only RES contributes."""
        cum_areas = {"RES": 50.0, "BAL": 30.0}
        llrf_res = 0.3 + math.sqrt(9.8 / 50.0)
        llrf = {"RES": llrf_res, "BAL": 0.0}
        expected = 50.0 * 1.9 * llrf_res  # BAL: 30 × 4.8 × 0 = 0
        assert compute_ll_reducible(cum_areas, load_type_lookup, llrf) == pytest.approx(expected, abs=0.01)


# ===================================================================
# compute_ll_non_reducible_by_type — Cols CZ:DX
# ===================================================================

class TestComputeLlNonReducibleByType:
    def test_n_type(self, load_type_lookup):
        """BAL (type "N"): 2.0m² × 4.8kPa = 9.6 kN."""
        areas = {"BAL": 2.0}
        result = compute_ll_non_reducible_by_type(areas, load_type_lookup)
        assert result["BAL"] == pytest.approx(9.6)

    def test_reducible_type_zero(self, load_type_lookup):
        """RES (type "R0.3"): → 0."""
        areas = {"RES": 5.0}
        result = compute_ll_non_reducible_by_type(areas, load_type_lookup)
        assert result["RES"] == pytest.approx(0.0)

    def test_mixed(self, load_type_lookup):
        """RES + BAL + STA: only BAL and STA contribute."""
        areas = {"RES": 5.0, "BAL": 2.0, "STA": 1.5}
        result = compute_ll_non_reducible_by_type(areas, load_type_lookup)
        assert result["RES"] == pytest.approx(0.0)
        assert result["BAL"] == pytest.approx(2.0 * 4.8)
        assert result["STA"] == pytest.approx(1.5 * 4.8)


# ===================================================================
# compute_pw — Col H = DL + LL
# ===================================================================

class TestComputePw:
    def test_basic(self):
        assert compute_pw(165.682, 44.63) == pytest.approx(210.312)

    def test_zero(self):
        assert compute_pw(0.0, 0.0) == pytest.approx(0.0)


# ===================================================================
# compute_pf — Col I = MAX(1.25×DL + 1.5×LL, 1.4×DL)
# ===================================================================

class TestComputePf:
    def test_verified_20205_c1_row10(self):
        """Verified: MAX(165.682×1.25 + 44.63×1.5, 1.4×165.682) = MAX(274.048, 231.955) = 274.048."""
        assert compute_pf(165.682, 44.63) == pytest.approx(274.048, abs=0.01)

    def test_dl_dominant(self):
        """When LL is tiny, 1.4×DL may dominate."""
        # 1.25×100 + 1.5×1 = 126.5 vs 1.4×100 = 140 → 140
        assert compute_pf(100.0, 1.0) == pytest.approx(140.0)

    def test_ll_dominant(self):
        """When LL is significant, 1.25DL+1.5LL dominates."""
        # 1.25×100 + 1.5×100 = 275 vs 1.4×100 = 140 → 275
        assert compute_pf(100.0, 100.0) == pytest.approx(275.0)

    def test_zero(self):
        assert compute_pf(0.0, 0.0) == pytest.approx(0.0)


# ===================================================================
# compute_f_over_a — Col J
# ===================================================================

class TestComputeFOverA:
    def test_basic(self):
        """PF=274.048kN, Z=0.2m² → 274.048/1000/0.2 = 1.37024 MPa."""
        assert compute_f_over_a(274.048, 0.2) == pytest.approx(1.37024, abs=0.001)

    def test_zero_section(self):
        """Z=0 → None."""
        assert compute_f_over_a(274.048, 0.0) is None

    def test_zero_load(self):
        """PF=0, Z=0.2 → 0.0 MPa."""
        assert compute_f_over_a(0.0, 0.2) == pytest.approx(0.0)


# ===================================================================
# compute_alpha — Col K
# ===================================================================

class TestComputeAlpha:
    def test_30mpa(self):
        """MAX(0.85 - 0.0015×30, 0.67) = MAX(0.805, 0.67) = 0.805."""
        assert compute_alpha(30.0) == pytest.approx(0.805)

    def test_35mpa(self):
        """MAX(0.85 - 0.0015×35, 0.67) = MAX(0.7975, 0.67) = 0.7975."""
        assert compute_alpha(35.0) == pytest.approx(0.7975)

    def test_40mpa(self):
        """MAX(0.85 - 0.0015×40, 0.67) = MAX(0.79, 0.67) = 0.79."""
        assert compute_alpha(40.0) == pytest.approx(0.79)

    def test_high_strength_capped(self):
        """Very high strength: alpha capped at 0.67."""
        # 0.85 - 0.0015×200 = 0.55 → MAX(0.55, 0.67) = 0.67
        assert compute_alpha(200.0) == pytest.approx(0.67)

    def test_zero_strength(self):
        """f'c=0 → 0.85."""
        assert compute_alpha(0.0) == pytest.approx(0.85)


# ===================================================================
# compute_cum_area — Col U
# ===================================================================

class TestComputeCumArea:
    def test_basic(self):
        """S=5.0, T=2.0, U_prev=10.0, has_section → 17.0."""
        assert compute_cum_area(5.0, 2.0, 10.0, True) == pytest.approx(17.0)

    def test_no_section(self):
        """Z=0 → 0 regardless of areas."""
        assert compute_cum_area(5.0, 2.0, 10.0, False) == pytest.approx(0.0)

    def test_first_floor(self):
        """First floor: U_prev=0, S=5.0, T=0 → 5.0."""
        assert compute_cum_area(5.0, 0.0, 0.0, True) == pytest.approx(5.0)


# ===================================================================
# compute_phi — capacity reduction factor
# ===================================================================

class TestComputePhi:
    def test_circular(self):
        """Y="D" → phi=0.8."""
        assert compute_phi(400, "D") == pytest.approx(0.8)

    def test_square_large(self):
        """500×500 (square, >300mm) → phi=0.8."""
        assert compute_phi(500, 500) == pytest.approx(0.8)

    def test_rectangular(self):
        """250×800 → phi = 0.2 + 0.002 × MIN(250,800) = 0.2 + 0.5 = 0.7."""
        assert compute_phi(250, 800) == pytest.approx(0.7)

    def test_thin_column(self):
        """200×400 → phi = 0.2 + 0.002 × 200 = 0.6."""
        assert compute_phi(200, 400) == pytest.approx(0.6)

    def test_steel(self):
        """Y="S" → Excel MIN() ignores text, uses X only.
        X=0.015 (area in m²) → phi = 0.2 + 0.002 × 0.015 ≈ 0.2."""
        assert compute_phi(0.015, "S") == pytest.approx(0.2 + 0.002 * 0.015)

    def test_wall_special(self):
        """Y="W", X=200 → Excel MIN() ignores text, uses X=200.
        phi = 0.2 + 0.002 × 200 = 0.6."""
        assert compute_phi(200, "W") == pytest.approx(0.6)

    def test_wall_special_large(self):
        """Y="W", X=400 → MIN=400 > 300 → phi = 0.8."""
        assert compute_phi(400, "W") == pytest.approx(0.8)

    def test_rectangular_large_min(self):
        """350×500 — not square, but MIN=350 > 300 → phi=0.8.
        Excel: IF(MIN(X:Y)>300, 0.8, ...) — no square check."""
        assert compute_phi(350, 500) == pytest.approx(0.8)

    def test_square_small(self):
        """300×300 — MIN=300, NOT > 300 → phi = 0.2 + 0.002 × 300 = 0.8.
        Same result either way for this boundary."""
        assert compute_phi(300, 300) == pytest.approx(0.8)


# ===================================================================
# compute_pct_steel — Col L
# ===================================================================

class TestComputePctSteel:
    def test_basic(self):
        """Test with known values. The formula should produce a reasonable ratio."""
        # f/A=1.37 MPa, alpha=0.805, f'c=30, 250×800
        f_over_a = 1.37
        alpha = 0.805
        fc = 30.0
        phi = compute_phi(250, 800)  # 0.7
        # numerator = 1.37/0.7 - 0.805×0.65×30 = 1.957 - 15.6975 = -13.74
        # denominator = 0.85×400 - 0.805×0.65×30 = 340 - 15.6975 = 324.3025
        # ratio = -13.74 / 324.3025 = -0.0424
        # MAX(-0.0424, 0.01) = 0.01 (minimum steel ratio)
        result = compute_pct_steel(f_over_a, alpha, fc, 250, 800)
        assert result == pytest.approx(0.01)

    def test_high_stress(self):
        """High stress should produce ratio > 1%."""
        # f/A = 20 MPa, alpha=0.805, f'c=30, 400×400 (phi=0.8)
        f_over_a = 20.0
        alpha = 0.805
        fc = 30.0
        phi = compute_phi(400, 400)  # 0.8 (square >300)
        # numerator = 20/0.8 - 0.805×0.65×30 = 25 - 15.6975 = 9.3025
        # denominator = 0.85×400 - 0.805×0.65×30 = 340 - 15.6975 = 324.3025
        # ratio = 9.3025 / 324.3025 = 0.02868
        result = compute_pct_steel(f_over_a, alpha, fc, 400, 400)
        expected = (20.0 / phi - alpha * 0.65 * fc) / (0.85 * 400 - alpha * 0.65 * fc)
        assert result == pytest.approx(expected, abs=0.0001)
        assert result > 0.01  # Above minimum


# ===================================================================
# compute_as — Col M: As = %steel × Z × 1e6
# ===================================================================

class TestComputeAs:
    def test_basic(self):
        """1% steel, Z=0.2m² → 0.01 × 0.2 × 1e6 = 2000 mm²."""
        assert compute_as(0.01, 0.2) == pytest.approx(2000.0)

    def test_zero_steel(self):
        assert compute_as(0.0, 0.2) == pytest.approx(0.0)

    def test_zero_section(self):
        assert compute_as(0.01, 0.0) == pytest.approx(0.0)


# ===================================================================
# bar_area — lookup from BAR_SIZES
# ===================================================================

class TestBarArea:
    def test_10m(self):
        assert bar_area("10M") == 100

    def test_20m(self):
        assert bar_area("20M") == 300

    def test_25m(self):
        assert bar_area("25M") == 500

    def test_55m(self):
        assert bar_area("55M") == 2500

    def test_all_sizes(self):
        """Verify all 8 standard sizes."""
        expected = {
            "10M": 100, "15M": 200, "20M": 300, "25M": 500,
            "30M": 700, "35M": 1000, "45M": 1500, "55M": 2500,
        }
        for size, area in expected.items():
            assert bar_area(size) == area

    def test_unknown_raises(self):
        """Unknown bar size should raise KeyError."""
        with pytest.raises(KeyError):
            bar_area("99M")


# ===================================================================
# compute_qty — Col O: bars distributed evenly across faces
# ===================================================================

class TestComputeQty:
    def test_verified_20205_c1(self):
        """20205 C1: As=2000, 20M, 250×800 (rect, mult=2).
        per_face = ceil(2000/300/2) = ceil(3.33) = 4. total = 2×4 = 8.
        """
        assert compute_qty(2000.0, "20M", 250, 800) == 8

    def test_square_column(self):
        """Square 500×500 (mult=4). As=2000, 20M.
        per_face = ceil(2000/300/4) = ceil(1.67) = 2. total = 4×2 = 8.
        """
        assert compute_qty(2000.0, "20M", 500, 500) == 8

    def test_circular_column(self):
        """Circular Y="D" (mult=1). As=2000, 20M.
        per_face = ceil(2000/300/1) = ceil(6.67) = 7. total = 1×7 = 7.
        """
        assert compute_qty(2000.0, "20M", 400, "D") == 7

    def test_zero_as(self):
        """0 mm² → 0 bars."""
        assert compute_qty(0.0, "20M", 250, 800) == 0

    def test_exact_fit(self):
        """As=1200, 20M (300mm²), rect 250×800 (mult=2).
        per_face = ceil(1200/300/2) = ceil(2.0) = 2. total = 2×2 = 4.
        """
        assert compute_qty(1200.0, "20M", 250, 800) == 4

    def test_large_bar(self):
        """As=5000, 25M (500mm²), square 400×400 (mult=4).
        per_face = ceil(5000/500/4) = ceil(2.5) = 3. total = 4×3 = 12.
        """
        assert compute_qty(5000.0, "25M", 400, 400) == 12


# ===================================================================
# compute_nbars — Col P: face bars with 4%/8% split logic
# ===================================================================

class TestComputeNbars:
    def test_normal_case_all_face(self):
        """Low ratio → P = O (all face bars).
        O=8, 20M (300mm²), Z=0.2m². ratio = 8×300/(0.2×1e6) = 1.2% < 4%.
        """
        assert compute_nbars(8, "20M", 0.2) == 8

    def test_large_bar_45m(self):
        """Bar > 35M → P = 0 (all corner)."""
        assert compute_nbars(4, "45M", 0.2) == 0

    def test_large_bar_55m(self):
        """Bar > 35M → P = 0."""
        assert compute_nbars(2, "55M", 0.2) == 0

    def test_high_ratio_split(self):
        """Ratio > 4%: P = floor(0.08×Z×1e6/bar_area) - O.
        O=12, 25M (500mm²), Z=0.1m². ratio = 12×500/(0.1×1e6) = 6% > 4%.
        max_at_8% = floor(0.08×0.1×1e6/500) = floor(16) = 16.
        P = 16 - 12 = 4.
        """
        assert compute_nbars(12, "25M", 0.1) == 4

    def test_zero_qty(self):
        """O=0 → P=0."""
        assert compute_nbars(0, "20M", 0.2) == 0

    def test_35m_bar_is_not_large(self):
        """35M is NOT > 35, so normal logic applies."""
        # O=6, 35M (1000mm²), Z=0.2m². ratio = 6×1000/(0.2×1e6) = 3% < 4%.
        assert compute_nbars(6, "35M", 0.2) == 6


# ===================================================================
# compute_cbars — Col Q: corner bars = O - P
# ===================================================================

class TestComputeCbars:
    def test_normal_all_face(self):
        """P = O → Q = 0 (no corner bars when ratio < 4%)."""
        assert compute_cbars(8, 8) == 0

    def test_high_ratio_split(self):
        """P = 4, O = 12 → Q = 8 corner bars."""
        assert compute_cbars(12, 4) == 8

    def test_large_bar(self):
        """P = 0 (large bar) → Q = O = all corner."""
        assert compute_cbars(4, 0) == 4

    def test_zero(self):
        """O = 0, P = 0 → Q = 0."""
        assert compute_cbars(0, 0) == 0


# ===================================================================
# format_rebar_design — Col R: firm standard rebar string
# ===================================================================

class TestFormatRebarDesign:
    def test_main_bars_only(self):
        """6 main bars of 20M, no corners. Z=0.2 m²."""
        result = format_rebar_design("20M", 6, 0, 0.2)
        assert result == "6-20M"

    def test_main_and_corner(self):
        """6 main + 4 corner of 20M. Z=0.2 m²."""
        result = format_rebar_design("20M", 6, 4, 0.2)
        assert result == "6-20M, 4-20M\u25cf"

    def test_corner_only(self):
        """0 main + 4 coupler."""
        result = format_rebar_design("20M", 0, 4, 0.2)
        assert result == "4-20M\u25cf"

    def test_over_8_percent(self):
        """Steel ratio > 8% → 'OVER 8%'.
        20 bars × 500mm² (25M) = 10000mm² / (0.1m² × 1e6) = 10% > 8%.
        """
        result = format_rebar_design("25M", 16, 4, 0.1)
        assert result == "OVER 8%"

    def test_exactly_8_percent(self):
        """Steel ratio = exactly 8% → still OK (not over, condition is > 0.08).
        16 bars × 500mm² (25M) = 8000mm² / (0.1m² × 1e6) = 8.0% = 0.08 → NOT > 0.08.
        """
        result = format_rebar_design("25M", 12, 4, 0.1)
        assert result == "12-25M, 4-25M\u25cf"

    def test_under_8_percent(self):
        """Comfortably under 8%.
        8 bars × 300mm² (20M) = 2400mm² / (0.2m² × 1e6) = 1.2%.
        """
        result = format_rebar_design("20M", 4, 4, 0.2)
        assert result == "4-20M, 4-20M\u25cf"

    def test_unknown_bar_size(self):
        """Unknown bar size → None."""
        assert format_rebar_design("99M", 6, 4, 0.2) is None

    def test_zero_section(self):
        """Z=0 → None."""
        assert format_rebar_design("20M", 6, 4, 0.0) is None

    def test_no_bars(self):
        """0 main + 0 corner → None."""
        assert format_rebar_design("20M", 0, 0, 0.2) is None