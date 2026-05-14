"""Tests for parsers/cad_dxf.py — CAD DXF MText parsing.

Unit tests for parse_cad_mtext and parse_cad_file, plus integration
tests against real DXF files from D:/RESEARCH/Claude/22031_CAD/.
"""

from __future__ import annotations

import os

import pytest

from rundown_engine.dtypes.cad import CadTextBlock
from rundown_engine.parsers.cad_dxf import (
    extract_mtext_from_dxf,
    parse_cad_file,
    parse_cad_mtext,
)

# Real DXF test files
_DXF_DIR = "D:/RESEARCH/Claude/22031_CAD"
_DXF_4TH = os.path.join(_DXF_DIR, "4TH FLOOR.dxf")
_DXF_GND = os.path.join(_DXF_DIR, "GROUND.dxf")

_has_dxf_files = os.path.isfile(_DXF_4TH) and os.path.isfile(_DXF_GND)
skip_no_dxf = pytest.mark.skipif(
    not _has_dxf_files, reason="DXF test files not available"
)


# ===================================================================
# Unit tests — parse_cad_mtext
# ===================================================================

class TestParseMtext:
    def test_rectangular_column(self):
        """Standard rectangular column with area, dims, perimeter, beam."""
        text = "C44A\nAres = 11.9 m²\nBM = 171.54 kN\nD = 500x500\nP = 7.3m"
        block = parse_cad_mtext(text)

        assert block.element_name == "C44A"
        assert block.areas == {"RES": pytest.approx(11.9)}
        assert block.dimensions == (500.0, 500.0)
        assert block.perimeter_m == pytest.approx(7.3)
        assert block.beam_weight_kn == pytest.approx(171.54)
        assert block.errors == []

    def test_rectangular_wall(self):
        """Wall with width x length dimensions."""
        text = "W1\nAbal = 8.6 m²\nAres = 69.5 m²\nD = 200x15840"
        block = parse_cad_mtext(text)

        assert block.element_name == "W1"
        assert block.areas["BAL"] == pytest.approx(8.6)
        assert block.areas["RES"] == pytest.approx(69.5)
        assert block.dimensions == (200.0, 15840.0)

    def test_circular_column_dia(self):
        """Circular column: D = 500 dia."""
        text = "C223\nARES = 7.2 m²\nD = 500 dia.\nP = 6.8m"
        block = parse_cad_mtext(text)

        assert block.element_name == "C223"
        assert block.dimensions == (500.0, "D")
        assert block.perimeter_m == pytest.approx(6.8)
        assert block.errors == []

    def test_circular_column_d_suffix(self):
        """Circular column: D = 450d."""
        text = "C1\nD = 450d"
        block = parse_cad_mtext(text)

        assert block.dimensions == (450.0, "D")

    def test_accumulated_areas(self):
        """Same area code repeated → values accumulate."""
        text = (
            "W1\n"
            "Abal = 8.6 m²\n"
            "Abal = 9.7 m²\n"
            "Abal = 9.7 m²\n"
            "Ares = 69.5 m²\n"
            "D = 200x15840"
        )
        block = parse_cad_mtext(text)

        assert block.areas["BAL"] == pytest.approx(8.6 + 9.7 + 9.7)
        assert block.areas["RES"] == pytest.approx(69.5)

    def test_accumulated_beam_weight(self):
        """Multiple BM lines → values accumulate."""
        text = (
            "C1\n"
            "BM = 57.11 kN\n"
            "BM = 57.11 kN\n"
            "BM = 58.34 kN\n"
            "D = 500x500"
        )
        block = parse_cad_mtext(text)

        assert block.beam_weight_kn == pytest.approx(57.11 + 57.11 + 58.34)

    def test_uppercase_area_codes(self):
        """Uppercase area codes (22031 format): ARES, ABAL."""
        text = "C223\nABAL = 4.0 m²\nARES = 7.2 m²\nD = 500 dia."
        block = parse_cad_mtext(text)

        assert block.areas == {"BAL": pytest.approx(4.0), "RES": pytest.approx(7.2)}

    def test_no_perimeter_no_beam(self):
        """Element with only area and dims — perimeter/beam default to 0."""
        text = "PC6\nAGFEXT = 53.8 m²\nD = 1000x300"
        block = parse_cad_mtext(text)

        assert block.perimeter_m == 0.0
        assert block.beam_weight_kn == 0.0
        assert block.areas == {"GFEXT": pytest.approx(53.8)}

    def test_trailing_newline(self):
        """Trailing newline doesn't affect parsing."""
        text = "W1\nAres = 10.0 m²\nD = 200x5000\n"
        block = parse_cad_mtext(text)

        assert block.element_name == "W1"
        assert block.areas == {"RES": pytest.approx(10.0)}
        assert block.errors == []

    def test_no_trailing_newline(self):
        """No trailing newline — still parses correctly."""
        text = "C47A.1\nAres = 28.9 m²\nBM = 208.23 kN\nD = 500x500"
        block = parse_cad_mtext(text)

        assert block.element_name == "C47A.1"
        assert block.dimensions == (500.0, 500.0)


class TestParseValidation:
    def test_missing_name_empty(self):
        """Truly empty name → error."""
        block = parse_cad_mtext("")
        assert any("empty" in e for e in block.errors)

    def test_missing_name_data_as_first_line(self):
        """Data line as first line (no element name) → caught by '=' check."""
        block = parse_cad_mtext("Ares = 5 m²\nD = 300x300")
        assert any("contains '='" in e for e in block.errors)

    def test_name_with_equals(self):
        """Name containing '=' → error (missing name line)."""
        block = parse_cad_mtext("Ares = 5 m²\nD = 300x300")
        assert any("contains '='" in e for e in block.errors)

    def test_name_too_long(self):
        """Name > 31 chars → error."""
        long_name = "A" * 32
        block = parse_cad_mtext(f"{long_name}\nD = 300x300")
        assert any("exceeds 31" in e for e in block.errors)

    def test_invalid_name_chars(self):
        """Name with invalid chars → error."""
        block = parse_cad_mtext("C1:A\nD = 300x300")
        assert any("invalid characters" in e for e in block.errors)

    def test_missing_dimension_warning(self):
        """No D= line → warning (not error)."""
        block = parse_cad_mtext("C1\nAres = 5 m²")
        assert any("no dimension" in w for w in block.warnings)
        assert block.dimensions is None

    def test_area_missing_equals(self):
        """Area line without '=' → error."""
        block = parse_cad_mtext("C1\nAres 5 m²\nD = 300x300")
        assert any("missing '='" in e for e in block.errors)

    def test_non_numeric_area(self):
        """Non-numeric area value → error."""
        block = parse_cad_mtext("C1\nAres = abc m²\nD = 300x300")
        assert any("non-numeric area" in e for e in block.errors)

    def test_undefined_area_code(self):
        """Unknown area code when valid_codes provided → error."""
        codes = {"RES": "RES", "BAL": "BAL"}
        block = parse_cad_mtext("C1\nAXYZ = 5 m²\nD = 300x300", codes)
        assert any("undefined area code" in e for e in block.errors)

    def test_valid_code_matching(self):
        """valid_codes preserves original case of the matched code."""
        codes = {"RES": "RES", "BAL": "BAL"}
        block = parse_cad_mtext("C1\nAres = 5 m²\nD = 300x300", codes)
        assert "RES" in block.areas

    def test_dimension_missing_equals(self):
        """Dimension line without '=' → error."""
        block = parse_cad_mtext("C1\nD 300x300")
        assert any("missing '='" in e for e in block.errors)

    def test_unrecognized_line(self):
        """Line not starting with A/D/P/B → error."""
        block = parse_cad_mtext("C1\nX = something\nD = 300x300")
        assert any("unrecognized" in e for e in block.errors)

    def test_empty_block(self):
        """Empty text → error."""
        block = parse_cad_mtext("")
        assert any("empty" in e for e in block.errors)


# ===================================================================
# Unit tests — parse_cad_file
# ===================================================================

class TestParseCadFile:
    def test_multiple_blocks(self):
        """Parse multiple blocks, each gets its own CadTextBlock."""
        texts = [
            "C1\nAres = 10 m²\nD = 400x400",
            "W1\nAres = 20 m²\nD = 200x5000",
        ]
        blocks, errors = parse_cad_file(texts)

        assert len(blocks) == 2
        assert blocks[0].element_name == "C1"
        assert blocks[1].element_name == "W1"
        assert errors == []

    def test_duplicate_detection(self):
        """Same element name twice → file error, second occurrence skipped."""
        texts = [
            "C1\nAres = 10 m²\nD = 400x400",
            "C1\nAres = 20 m²\nD = 300x300",  # duplicate
        ]
        blocks, errors = parse_cad_file(texts)

        assert len(blocks) == 1
        assert blocks[0].areas["RES"] == pytest.approx(10.0)
        assert len(errors) == 1
        assert "duplicate" in errors[0].lower()

    def test_duplicate_case_insensitive(self):
        """Duplicate detection is case-insensitive."""
        texts = [
            "C1\nD = 400x400",
            "c1\nD = 300x300",  # same name, different case
        ]
        blocks, errors = parse_cad_file(texts)

        assert len(blocks) == 1
        assert len(errors) == 1

    def test_valid_codes_filter(self):
        """valid_codes restricts accepted area codes."""
        texts = ["C1\nAres = 10 m²\nAXYZ = 5 m²\nD = 400x400"]
        blocks, errors = parse_cad_file(texts, valid_codes=["RES"])

        assert len(blocks) == 1
        assert "RES" in blocks[0].areas
        assert "XYZ" not in blocks[0].areas
        assert any("undefined" in e for e in blocks[0].errors)


# ===================================================================
# Integration tests — real DXF files from 22031_CAD
# ===================================================================

@skip_no_dxf
class TestDxf22031_4thFloor:
    """Integration tests against 22031 4TH FLOOR.dxf."""

    @pytest.fixture(scope="class")
    def parsed(self):
        texts, warnings = extract_mtext_from_dxf(_DXF_4TH)
        blocks, file_errors = parse_cad_file(texts)
        return texts, warnings, blocks, file_errors

    def test_extraction_count(self, parsed):
        """Should extract 62 MTEXT blocks."""
        texts, _, _, _ = parsed
        assert len(texts) == 62

    def test_no_file_errors(self, parsed):
        """No duplicates or file-level errors."""
        _, _, _, file_errors = parsed
        assert file_errors == []

    def test_no_extraction_warnings(self, parsed):
        """No single-line text warnings."""
        _, warnings, _, _ = parsed
        assert warnings == []

    def test_block_count(self, parsed):
        """All 62 blocks parsed (no duplicates)."""
        _, _, blocks, _ = parsed
        assert len(blocks) == 62

    def test_circular_column_c223(self, parsed):
        """C223 is a circular column (500 dia.)."""
        _, _, blocks, _ = parsed
        c223 = [b for b in blocks if b.element_name == "C223"]
        assert len(c223) == 1
        b = c223[0]

        assert b.dimensions == (500.0, "D")
        assert "BAL" in b.areas
        assert "RES" in b.areas
        assert b.perimeter_m > 0

    def test_wall_w225(self, parsed):
        """W225 is a rectangular wall with BAL + RES areas."""
        _, _, blocks, _ = parsed
        w225 = [b for b in blocks if b.element_name == "W225"]
        assert len(w225) == 1
        b = w225[0]

        assert b.dimensions == (7410.0, 250.0)
        assert b.areas["BAL"] == pytest.approx(7.8)
        assert b.areas["RES"] == pytest.approx(46.9)
        assert b.perimeter_m == pytest.approx(5.2)

    def test_all_have_dimensions(self, parsed):
        """Every block on 4th floor should have dimensions."""
        _, _, blocks, _ = parsed
        missing = [b.element_name for b in blocks if b.dimensions is None]
        assert missing == [], f"Elements missing dimensions: {missing}"

    def test_area_codes_only_bal_res(self, parsed):
        """4th floor only has BAL and RES area codes."""
        _, _, blocks, _ = parsed
        all_codes = set()
        for b in blocks:
            all_codes.update(b.areas.keys())
        assert all_codes == {"BAL", "RES"}

    def test_no_parse_errors(self, parsed):
        """No parsing errors on any block."""
        _, _, blocks, _ = parsed
        errors = []
        for b in blocks:
            for e in b.errors:
                errors.append(f"{b.element_name}: {e}")
        assert errors == [], f"Parse errors: {errors}"


@skip_no_dxf
class TestDxf22031_Ground:
    """Integration tests against 22031 GROUND.dxf."""

    @pytest.fixture(scope="class")
    def parsed(self):
        texts, warnings = extract_mtext_from_dxf(_DXF_GND)
        blocks, file_errors = parse_cad_file(texts)
        return texts, warnings, blocks, file_errors

    def test_extraction_count(self, parsed):
        """Should extract 185 MTEXT blocks from RUNDOWN-STMW layer."""
        texts, _, _, _ = parsed
        assert len(texts) == 185

    def test_layer_prefix_matching(self, parsed):
        """RUNDOWN-STMW layer matched via starts-with 'RUNDOWN'."""
        texts, _, _, _ = parsed
        assert len(texts) > 0  # proves layer matching worked

    def test_block_count(self, parsed):
        """All blocks parsed (checking for duplicates)."""
        _, _, blocks, file_errors = parsed
        # Some duplicates may exist
        assert len(blocks) + len(file_errors) >= 185

    def test_foundation_element_pc6(self, parsed):
        """PC6 foundation column with GFEXT area code."""
        _, _, blocks, _ = parsed
        pc6 = [b for b in blocks if b.element_name == "PC6"]
        assert len(pc6) == 1
        b = pc6[0]

        assert b.areas["GFEXT"] == pytest.approx(53.8)
        assert b.dimensions == (1000.0, 300.0)

    def test_area_codes_variety(self, parsed):
        """Ground floor has multiple area codes."""
        _, _, blocks, _ = parsed
        all_codes = set()
        for b in blocks:
            all_codes.update(b.areas.keys())
        # Should have GFEXT plus several others
        assert "GFEXT" in all_codes
        assert len(all_codes) >= 3

    def test_beam_weights_present(self, parsed):
        """Some ground floor elements have beam weights."""
        _, _, blocks, _ = parsed
        with_bm = [b for b in blocks if b.beam_weight_kn > 0]
        assert len(with_bm) > 0

    def test_no_parse_errors(self, parsed):
        """No parsing errors on any block."""
        _, _, blocks, _ = parsed
        errors = []
        for b in blocks:
            for e in b.errors:
                errors.append(f"{b.element_name}: {e}")
        assert errors == [], f"Parse errors: {errors}"
