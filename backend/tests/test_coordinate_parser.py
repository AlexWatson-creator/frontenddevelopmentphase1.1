"""Tests for coordinate_parser using real JAPBIMDB data samples."""
import pytest

from app.services.coordinate_parser import (
    parse_point,
    parse_column_location,
    parse_wall_locations,
    parse_slab_polygon,
)


# ---------------------------------------------------------------------------
# parse_point
# ---------------------------------------------------------------------------

class TestParsePoint:
    def test_basic(self):
        assert parse_point("8878.0,6675.0,5540.0") == (8878.0, 6675.0, 5540.0)

    def test_negative_values(self):
        assert parse_point("-36653.0,45097.0,31450.0") == (-36653.0, 45097.0, 31450.0)

    def test_whitespace(self):
        assert parse_point("  8878.0, 6675.0, 5540.0  ") == (8878.0, 6675.0, 5540.0)

    def test_empty_string(self):
        assert parse_point("") is None

    def test_none_input(self):
        assert parse_point(None) is None

    def test_whitespace_only(self):
        assert parse_point("   ") is None

    def test_too_few_parts(self):
        assert parse_point("8878.0,6675.0") is None

    def test_too_many_parts(self):
        assert parse_point("8878.0,6675.0,5540.0,1.0") is None

    def test_non_numeric(self):
        assert parse_point("abc,def,ghi") is None


# ---------------------------------------------------------------------------
# parse_column_location
# ---------------------------------------------------------------------------

class TestParseColumnLocation:
    def test_real_sample(self):
        """Real data: dbo.Columns id=1150391."""
        assert parse_column_location("-36653.0,45097.0,31450.0") == (-36653.0, 45097.0)

    def test_another_sample(self):
        """Real data: dbo.Columns id=1150434."""
        assert parse_column_location("-5457.0,21301.0,31450.0") == (-5457.0, 21301.0)

    def test_empty(self):
        assert parse_column_location("") is None

    def test_malformed(self):
        assert parse_column_location("not,a,point,ok") is None


# ---------------------------------------------------------------------------
# parse_wall_locations
# ---------------------------------------------------------------------------

class TestParseWallLocations:
    def test_real_sample(self):
        """Real data: dbo.Walls id=1150396."""
        result = parse_wall_locations(
            "-26757.0,45522.0,31450.0",
            "-26757.0,36502.0,31450.0",
        )
        assert result == ((-26757.0, 45522.0), (-26757.0, 36502.0))

    def test_different_wall(self):
        """Real data: dbo.Walls id=1150400."""
        result = parse_wall_locations(
            "-25782.0,34594.0,31450.0",
            "-25782.0,31959.0,31450.0",
        )
        assert result == ((-25782.0, 34594.0), (-25782.0, 31959.0))

    def test_start_none(self):
        assert parse_wall_locations("", "-26757.0,36502.0,31450.0") is None

    def test_end_none(self):
        assert parse_wall_locations("-26757.0,45522.0,31450.0", "") is None

    def test_both_none(self):
        assert parse_wall_locations("", "") is None


# ---------------------------------------------------------------------------
# parse_slab_polygon
# ---------------------------------------------------------------------------

class TestParseSlabPolygon:
    def test_single_loop(self):
        """Real data: dbo.Floors OPENING id=1173800."""
        text = (
            "-16905.0,29434.0,31450.0:-16905.0,31834.0,31450.0:"
            "-25647.0,31834.0,31450.0:-25647.0,29434.0,31450.0"
        )
        result = parse_slab_polygon(text)
        assert result is not None
        assert len(result) == 1
        assert len(result[0]) == 4
        assert result[0][0] == (-16905.0, 29434.0)
        assert result[0][3] == (-25647.0, 29434.0)

    def test_multi_loop(self):
        """Real data: dbo.Floors id=1145950 (truncated to 2 loops)."""
        text = (
            "-27690.0,19274.0,31450.0:-27690.0,20774.0,31450.0:"
            "-29389.0,20774.0,31450.0:-29389.0,19274.0,31450.0;"
            "-5131.0,19239.0,31450.0:-5131.0,20774.0,31450.0:"
            "-14402.0,20774.0,31450.0:-14402.0,19239.0,31450.0"
        )
        result = parse_slab_polygon(text)
        assert result is not None
        assert len(result) == 2
        assert len(result[0]) == 4
        assert len(result[1]) == 4

    def test_trailing_semicolon(self):
        text = (
            "-1.0,2.0,3.0:-4.0,5.0,6.0:-7.0,8.0,9.0;"
        )
        result = parse_slab_polygon(text)
        assert result is not None
        assert len(result) == 1

    def test_empty_string(self):
        assert parse_slab_polygon("") is None

    def test_none_input(self):
        assert parse_slab_polygon(None) is None

    def test_whitespace_only(self):
        assert parse_slab_polygon("   ") is None

    def test_too_few_vertices(self):
        """A loop with < 3 vertices is discarded."""
        text = "-1.0,2.0,3.0:-4.0,5.0,6.0"
        assert parse_slab_polygon(text) is None

    def test_malformed_vertex_skipped(self):
        """One bad vertex doesn't kill the whole loop."""
        text = (
            "-1.0,2.0,3.0:BAD_DATA:"
            "-4.0,5.0,6.0:-7.0,8.0,9.0"
        )
        result = parse_slab_polygon(text)
        assert result is not None
        assert len(result) == 1
        assert len(result[0]) == 3  # BAD_DATA vertex skipped