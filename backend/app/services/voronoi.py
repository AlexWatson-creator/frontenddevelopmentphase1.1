"""Voronoi tributary area computation.

Based on D:\RESEARCH\CREATE_TRIBUTARY_AREA_CAD\voronoi.py.
Computes Voronoi cells for structural elements (columns, walls) clipped
to a floor boundary polygon.  All coordinates in mm.

DXF export: marked for future development.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial import Voronoi
from shapely.geometry import Polygon
from shapely.ops import unary_union


@dataclass
class ColumnSeed:
    """A column point seed for Voronoi computation."""
    guid: str
    x: float
    y: float


@dataclass
class WallSeed:
    """A wall line seed for Voronoi computation."""
    guid: str
    x1: float
    y1: float
    x2: float
    y2: float


@dataclass
class TributaryCell:
    """Result: one element's tributary area polygon."""
    element_guid: str
    element_type: str  # "column" or "wall"
    polygon: Polygon
    area_mm2: float
    area_m2: float


# ---------------------------------------------------------------------------
# Internal helpers (ported from reference voronoi.py)
# ---------------------------------------------------------------------------

def _pt_key(x: float, y: float, tol: float = 1e-3) -> tuple[int, int]:
    """Quantize a point to a grid so near-equal endpoints match."""
    return (int(round(float(x) / tol)), int(round(float(y) / tol)))


def _compute_wall_endpoint_connections(
    walls: list[WallSeed], tol: float = 1e-3,
) -> list[tuple[bool, bool]]:
    """For each wall, return (start_connected, end_connected).

    An endpoint is 'connected' if another wall shares it. Connected
    endpoints are excluded from densification to avoid duplicate seeds
    at the junction.
    """
    counts: dict[tuple[int, int], int] = {}
    for w in walls:
        k1 = _pt_key(w.x1, w.y1, tol)
        k2 = _pt_key(w.x2, w.y2, tol)
        counts[k1] = counts.get(k1, 0) + 1
        counts[k2] = counts.get(k2, 0) + 1

    flags = []
    for w in walls:
        k1 = _pt_key(w.x1, w.y1, tol)
        k2 = _pt_key(w.x2, w.y2, tol)
        flags.append((counts.get(k1, 0) > 1, counts.get(k2, 0) > 1))
    return flags


def _densify_wall_points(
    x1: float, y1: float, x2: float, y2: float,
    spacing: float = 200.0,
    include_start: bool = True,
    include_end: bool = True,
) -> list[tuple[float, float]]:
    """Generate equally spaced points along a wall segment."""
    dx = x2 - x1
    dy = y2 - y1
    length = np.hypot(dx, dy)
    if length <= 1e-9 or length < spacing:
        return []

    nseg = max(1, int(np.ceil(length / spacing)))
    xs = np.linspace(x1, x2, nseg + 1)
    ys = np.linspace(y1, y2, nseg + 1)
    pts = list(zip(xs.tolist(), ys.tolist()))

    if not include_start and pts:
        pts = pts[1:]
    if not include_end and pts:
        pts = pts[:-1]
    return pts


def _voronoi_finite_polygons_2d(
    vor: Voronoi, radius: float | None = None,
) -> tuple[list[list[int]], np.ndarray]:
    """Reconstruct infinite Voronoi regions to finite regions.

    Returns (regions, vertices) where each region is a list of vertex
    indices forming a closed polygon.
    """
    if vor.points.shape[1] != 2:
        raise ValueError("Requires 2D input")

    new_regions: list[list[int]] = []
    new_vertices = vor.vertices.tolist()

    center = vor.points.mean(axis=0)
    if radius is None:
        radius = vor.points.ptp().max() * 2

    # Map ridges for each point
    all_ridges: dict[int, list[tuple[int, int, int]]] = {}
    for (p1, p2), (v1, v2) in zip(vor.ridge_points, vor.ridge_vertices):
        all_ridges.setdefault(p1, []).append((p2, v1, v2))
        all_ridges.setdefault(p2, []).append((p1, v1, v2))

    for p1, region_idx in enumerate(vor.point_region):
        region = vor.regions[region_idx]

        # Finite region — keep as-is
        if region and (-1 not in region):
            new_regions.append(region)
            continue

        # Reconstruct infinite region
        ridges = all_ridges.get(p1, [])
        new_region = [v for v in region if v != -1] if region else []

        for p2, v1, v2 in ridges:
            if v1 == -1 or v2 == -1:
                v = v1 if v1 != -1 else v2
                t = vor.points[p2] - vor.points[p1]
                t = t / np.linalg.norm(t)
                n = np.array([-t[1], t[0]])
                midpoint = (vor.points[p1] + vor.points[p2]) / 2
                direction = np.sign(np.dot(midpoint - center, n)) * n
                far_point = vor.vertices[v] + direction * radius
                new_vertices.append(far_point.tolist())
                new_region.append(len(new_vertices) - 1)

        # Order vertices counter-clockwise
        vs = np.asarray([new_vertices[v] for v in new_region])
        c = vs.mean(axis=0)
        angles = np.arctan2(vs[:, 1] - c[1], vs[:, 0] - c[0])
        new_region = [v for _, v in sorted(zip(angles, new_region))]
        new_regions.append(new_region)

    return new_regions, np.asarray(new_vertices)


def _safe_polygon(verts_xy, dedup_round: int = 8) -> Polygon:
    """Build a polygon safely, deduplicating near-equal vertices."""
    uniq = []
    seen: set[tuple[float, float]] = set()
    for x, y in verts_xy:
        key = (round(float(x), dedup_round), round(float(y), dedup_round))
        if key not in seen:
            seen.add(key)
            uniq.append((float(x), float(y)))
    if len(uniq) < 3:
        return Polygon()
    poly = Polygon(uniq)
    if not poly.is_valid:
        poly = poly.buffer(0)
    return poly if (not poly.is_empty and poly.area > 0) else Polygon()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_tributary_areas(
    boundary: Polygon,
    columns: list[ColumnSeed],
    walls: list[WallSeed],
    wall_spacing: float = 200.0,
) -> list[TributaryCell]:
    """Compute Voronoi tributary areas for columns and walls.

    Args:
        boundary: Floor boundary polygon (shapely, mm units).
        columns: Column point seeds.
        walls: Wall line seeds.
        wall_spacing: Wall densification spacing in mm.

    Returns:
        List of TributaryCell results (one per element).
    """
    if not columns and not walls:
        return []

    # Build point cloud: columns first, then densified wall points
    col_points = [(c.x, c.y) for c in columns]
    all_points: list[tuple[float, float]] = list(col_points)
    n_col = len(col_points)

    # Wall endpoint connections + densification
    conn_flags = _compute_wall_endpoint_connections(walls)
    wall_point_indices: list[list[int]] = []

    for i, wall in enumerate(walls):
        start_connected, end_connected = conn_flags[i]
        pts = _densify_wall_points(
            wall.x1, wall.y1, wall.x2, wall.y2,
            spacing=wall_spacing,
            include_start=not start_connected,
            include_end=not end_connected,
        )
        start_idx = len(all_points)
        all_points.extend(pts)
        wall_point_indices.append(list(range(start_idx, start_idx + len(pts))))

    # Edge case: single element gets the entire boundary
    if len(all_points) < 2:
        results: list[TributaryCell] = []
        if columns:
            area = boundary.area
            results.append(TributaryCell(
                element_guid=columns[0].guid,
                element_type="column",
                polygon=boundary,
                area_mm2=area,
                area_m2=area / 1e6,
            ))
        elif walls and wall_point_indices and wall_point_indices[0]:
            area = boundary.area
            results.append(TributaryCell(
                element_guid=walls[0].guid,
                element_type="wall",
                polygon=boundary,
                area_mm2=area,
                area_m2=area / 1e6,
            ))
        return results

    points_array = np.asarray(all_points, dtype=float)

    # Compute Voronoi
    vor = Voronoi(points_array)

    # Finite regions with radius tied to boundary size
    bx0, by0, bx1, by1 = boundary.bounds
    rad = max(bx1 - bx0, by1 - by0) * 4.0
    regions, vertices = _voronoi_finite_polygons_2d(vor, radius=rad)

    # Build clipped cell per input point
    clipped_cells: list[Polygon] = [Polygon() for _ in range(len(all_points))]

    for i, region in enumerate(regions):
        if not region or len(region) < 3:
            continue
        poly = _safe_polygon(vertices[region])
        if poly.is_empty:
            continue
        clipped = boundary.intersection(poly)
        if clipped.is_empty:
            continue
        if clipped.geom_type in ("Polygon", "MultiPolygon"):
            clipped_cells[i] = clipped

    results = []

    # Column cells (one cell per column)
    for i, col in enumerate(columns):
        cell = clipped_cells[i]
        if cell.is_empty:
            continue
        area = cell.area
        results.append(TributaryCell(
            element_guid=col.guid,
            element_type="column",
            polygon=cell,
            area_mm2=area,
            area_m2=area / 1e6,
        ))

    # Wall cells (merge densified point cells back per wall)
    for wall_idx, wall in enumerate(walls):
        idxs = wall_point_indices[wall_idx]
        cells = [
            clipped_cells[j] for j in idxs
            if not clipped_cells[j].is_empty
            and clipped_cells[j].geom_type in ("Polygon", "MultiPolygon")
        ]
        if not cells:
            continue
        merged = unary_union(cells)
        if not merged.is_valid:
            merged = merged.buffer(0)
        if merged.is_empty:
            continue
        area = merged.area
        results.append(TributaryCell(
            element_guid=wall.guid,
            element_type="wall",
            polygon=merged,
            area_mm2=area,
            area_m2=area / 1e6,
        ))

    return results