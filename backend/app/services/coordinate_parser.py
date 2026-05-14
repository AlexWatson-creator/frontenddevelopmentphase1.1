"""Parse JAPBIMDB text coordinate formats into numeric tuples.

All coordinates are in mm (project-relative). Functions return None on
malformed input and log a warning rather than raising.

Formats:
  Column BaseLocation: "8878.0,6675.0,5540.0"  → comma-separated x,y,z
  Wall Start/EndLocation: same format, two points define the wall line
  Slab LocationPoints: "x,y,z:x,y,z:..." colon-separated vertices,
                       semicolons separate multiple sketch loops
"""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def parse_point(text: str) -> Optional[tuple[float, float, float]]:
    """Parse "x,y,z" text into a 3-tuple of floats.

    Returns None if the input is empty, whitespace-only, or malformed.
    """
    if not text or not text.strip():
        return None
    parts = text.strip().split(",")
    if len(parts) != 3:
        logger.warning("parse_point: expected 3 components, got %d in %r", len(parts), text)
        return None
    try:
        return (float(parts[0]), float(parts[1]), float(parts[2]))
    except ValueError:
        logger.warning("parse_point: non-numeric value in %r", text)
        return None


def parse_column_location(base_location: str) -> Optional[tuple[float, float]]:
    """Extract plan-view (x, y) from a Column BaseLocation string.

    Drops the z coordinate since we only need plan position.
    """
    pt = parse_point(base_location)
    if pt is None:
        return None
    return (pt[0], pt[1])


def parse_wall_locations(
    start_location: str, end_location: str
) -> Optional[tuple[tuple[float, float], tuple[float, float]]]:
    """Parse wall start/end location strings into two (x, y) endpoints."""
    start = parse_point(start_location)
    end = parse_point(end_location)
    if start is None or end is None:
        return None
    return ((start[0], start[1]), (end[0], end[1]))


def parse_slab_polygon(
    location_points: str,
) -> Optional[list[list[tuple[float, float]]]]:
    """Parse slab LocationPoints into a list of loops.

    Each loop is a list of (x, y) tuples. Multiple loops are separated
    by semicolons in the source text. Returns None if the input is
    empty or completely unparseable. Individual malformed vertices
    within a loop are skipped with a warning.
    """
    if not location_points or not location_points.strip():
        return None

    loops: list[list[tuple[float, float]]] = []
    raw_loops = location_points.strip().split(";")

    for loop_str in raw_loops:
        loop_str = loop_str.strip()
        if not loop_str:
            continue

        vertices: list[tuple[float, float]] = []
        for vertex_str in loop_str.split(":"):
            vertex_str = vertex_str.strip()
            if not vertex_str:
                continue
            pt = parse_point(vertex_str)
            if pt is None:
                logger.warning("parse_slab_polygon: skipping malformed vertex %r", vertex_str)
                continue
            vertices.append((pt[0], pt[1]))

        if len(vertices) >= 3:
            loops.append(vertices)
        elif vertices:
            logger.warning(
                "parse_slab_polygon: loop with only %d vertices discarded", len(vertices)
            )

    return loops if loops else None
