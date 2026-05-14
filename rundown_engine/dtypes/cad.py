"""CAD parser types for the rundown engine.

Used by parsers/cad_dxf.py for DXF MText parsing.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CadTextBlock:
    """Parsed MText block from a DXF file on the "rundown" layer.

    One block per element per CAD file. Contains all data lines
    parsed from the MText content.
    """

    element_name: str
    areas: dict[str, float] = field(default_factory=dict)
    # {code: m²} — accumulates duplicates

    dimensions: tuple[float, str | float] | None = None
    # (dim_x_mm, dim_y) where dim_y is float (rectangular) or "D" (circular)

    perimeter_m: float = 0.0
    beam_weight_kn: float = 0.0

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
