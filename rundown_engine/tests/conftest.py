"""Shared fixtures and known-good values for rundown engine tests.

Reference projects:
  - 20205 TEMPLE: 19 levels, normal marks (C1, W1, PW101)
  - 24043: varies levels, zero-padded marks (C001, W001)

Verified values come from actual Excel cell output.
"""

import pytest

from rundown_engine.dtypes import LoadTypeDef


@pytest.fixture
def sample_load_types() -> list[LoadTypeDef]:
    """Load types loosely based on 20205 TEMPLE (subset for testing)."""
    return [
        LoadTypeDef(code="RES", description="RESIDENTIAL", dead_kpa=6.1, live_kpa=1.9, llrf_type="R0.3"),
        LoadTypeDef(code="BAL", description="BALCONY", dead_kpa=6.1, live_kpa=4.8, llrf_type="N"),
        LoadTypeDef(code="PAR", description="PARKING", dead_kpa=4.8, live_kpa=2.4, llrf_type="R0.5"),
        LoadTypeDef(code="MEC", description="MECHANICAL", dead_kpa=6.1, live_kpa=3.6, llrf_type="N"),
        LoadTypeDef(code="STA", description="STAIRWELL", dead_kpa=6.1, live_kpa=4.8, llrf_type="N"),
        LoadTypeDef(code="AMT", description="AMENITY", dead_kpa=5.3, live_kpa=4.8, llrf_type="R0.3"),
    ]


@pytest.fixture
def load_type_lookup(sample_load_types: list[LoadTypeDef]) -> dict[str, LoadTypeDef]:
    """Lookup dict keyed by code."""
    return {lt.code: lt for lt in sample_load_types}