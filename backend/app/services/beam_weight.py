"""Compute beam weight contributions per tributary cell.

Returns per-element lists of individual beam contributions (one value per beam),
not a single total. This preserves transparency — every beam's load is traceable.

Volume in m³ (Clarity converts Revit ft³ on export).
TypeName LIKE '%CONCRETE%' only.
Coordinates in mm (matching platform mm convention for all geometry).
"""
from __future__ import annotations

import re

from shapely.geometry import LineString
from sqlalchemy import text
from sqlalchemy.orm import Session

_NUM_RE = re.compile(r"[-\d.]+")
CONCRETE_KN_M3 = 24.0


def _parse_xy(loc: str | None) -> tuple[float, float] | None:
    """Extract (x, y) mm from POINT(x y z) or 'x y z' text."""
    if not loc:
        return None
    nums = _NUM_RE.findall(loc)
    return (float(nums[0]), float(nums[1])) if len(nums) >= 2 else None


def compute_beam_weights(
    db: Session,
    project_id: int,
    level_id: int,
    cells: list,
) -> dict[str, list[float]]:
    """Return {element_guid: [bm1_kn, bm2_kn, ...]} — one entry per contributing beam.

    Only beams whose polygon intersection is non-empty appear in a cell's list.
    Volume stored in m³ (Clarity converts Revit ft³ on export).
    Only beams with TypeName LIKE '%CONCRETE%' are included.

    Args:
        db: SQLAlchemy session.
        project_id: dbo.Project.Id
        level_id: dbo.Levels.id (beams' reference level)
        cells: list[TributaryCell] from compute_tributary_areas()

    Returns:
        Dict keyed by element_guid. Each value is a list of rounded kN floats,
        one per beam that overlaps that cell. Empty list = no beam weight.
    """
    cell_map = {c.element_guid: c.polygon for c in cells}
    result: dict[str, list[float]] = {c.element_guid: [] for c in cells}

    rows = db.execute(
        text("""
            SELECT b.StartLocation, b.EndLocation, b.Volume, bt.TypeName
            FROM   dbo.Beams b
            JOIN   dbo.BeamType bt ON bt.id = b.Section_id
            WHERE  b.Project_id = :pid
              AND  b.Level_id   = :lid
              AND  UPPER(bt.TypeName) LIKE '%CONCRETE%'
        """),
        {"pid": project_id, "lid": level_id},
    ).fetchall()

    for row in rows:
        p1 = _parse_xy(row.StartLocation)
        p2 = _parse_xy(row.EndLocation)
        vol = row.Volume  # m³  (if values look ~1e9× too large, multiply by 1e-9 first)
        if p1 is None or p2 is None or not vol or vol <= 0:
            continue

        beam_line = LineString([p1, p2])
        if beam_line.length < 1e-6:
            continue

        total_kn = float(vol) * CONCRETE_KN_M3

        for guid, poly in cell_map.items():
            intr = beam_line.intersection(poly)
            if not intr.is_empty:
                bm = round((intr.length / beam_line.length) * total_kn, 1)
                if bm > 0:
                    result[guid].append(bm)

    return result
