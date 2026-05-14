"""Tests for mark_parser — pure unit tests, no DB required."""
import pytest

from app.services.mark_parser import ParsedMark, canonical_mark, detect_mark_error, parse_mark


class TestParseMark:
    def test_simple_column(self):
        p = parse_mark("C101")
        assert p.parsed_successfully
        assert p.type_char == "C"
        assert p.element_number == "101"
        assert p.prefix is None
        assert p.suffix is None
        assert p.comments is None

    def test_simple_wall(self):
        p = parse_mark("W103")
        assert p.parsed_successfully
        assert p.type_char == "W"
        assert p.element_number == "103"

    def test_with_suffix(self):
        p = parse_mark("C102A")
        assert p.parsed_successfully
        assert p.element_number == "102"
        assert p.suffix == "A"

    def test_with_dash_prefix(self):
        p = parse_mark("PH-C12")
        assert p.parsed_successfully
        assert p.prefix == "PH-"
        assert p.type_char == "C"
        assert p.element_number == "12"

    def test_no_dash_prefix(self):
        p = parse_mark("MPHW1")
        assert p.parsed_successfully
        assert p.prefix == "MPH"
        assert p.type_char == "W"
        assert p.element_number == "1"

    def test_prefix_and_suffix(self):
        p = parse_mark("MB-W5B")
        assert p.parsed_successfully
        assert p.prefix == "MB-"
        assert p.type_char == "W"
        assert p.element_number == "5"
        assert p.suffix == "B"

    def test_with_comments(self):
        p = parse_mark("C12.corner column")
        assert p.parsed_successfully
        assert p.element_number == "12"
        assert p.comments == "corner column"

    def test_full_complex(self):
        p = parse_mark("PH-C12A.notes here")
        assert p.parsed_successfully
        assert p.prefix == "PH-"
        assert p.type_char == "C"
        assert p.element_number == "12"
        assert p.suffix == "A"
        assert p.comments == "notes here"

    def test_lowercase_normalized(self):
        p = parse_mark("c5")
        assert p.parsed_successfully
        assert p.type_char == "C"
        assert p.element_number == "5"

    def test_none_input(self):
        p = parse_mark(None)
        assert not p.parsed_successfully
        assert p.raw_mark == ""

    def test_empty_string(self):
        p = parse_mark("")
        assert not p.parsed_successfully

    def test_digits_only(self):
        """Marks like '185' (no type char) are unparseable."""
        p = parse_mark("185")
        assert not p.parsed_successfully

    def test_text_with_space(self):
        """Marks like '200 PIER' are unparseable."""
        p = parse_mark("200 PIER")
        assert not p.parsed_successfully

    def test_random_text(self):
        p = parse_mark("RANDOM")
        assert not p.parsed_successfully


class TestDetectError:
    def test_wall_marked_as_column(self):
        """Wall with C-type mark is an error."""
        p = parse_mark("C180")
        assert detect_mark_error(p, "Wall") is True

    def test_column_marked_as_wall(self):
        """Column with W-type mark is an error."""
        p = parse_mark("W105B")
        assert detect_mark_error(p, "Column") is True

    def test_no_error(self):
        p = parse_mark("C101")
        assert detect_mark_error(p, "Column") is False

    def test_unparsed_not_error(self):
        """Unparseable marks are not flagged as type errors."""
        p = parse_mark("185")
        assert detect_mark_error(p, "Wall") is False


class TestCanonicalMark:
    def test_normal(self):
        p = parse_mark("C12")
        assert canonical_mark(p, "Column") == "C12"

    def test_corrects_type(self):
        """Wall with C180 mark → canonical W180."""
        p = parse_mark("C180")
        assert canonical_mark(p, "Wall") == "W180"

    def test_strips_prefix(self):
        p = parse_mark("PH-C12A")
        assert canonical_mark(p, "Column") == "C12A"

    def test_unparsed_returns_raw(self):
        p = parse_mark("185")
        assert canonical_mark(p, "Wall") == "185"
