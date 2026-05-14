"""CAD DXF parser — extract rundown data from DXF files via ezdxf.

Cross-checked against VBA ImportRundown.bas parsing rules.

User exports DWG→DXF from AutoCAD, uploads DXF to platform.
Parser reads MTEXT entities on the "RUNDOWN" layer and extracts:
  - Element name (line 0)
  - Areas by type: A{code} = {value} m²
  - Dimensions: D = {w}x{h} (rectangular) or D = {d} dia (circular)
  - Perimeter: P = {value}m
  - Beam weight: BM = {value} kN

Values accumulate: if the same area code appears multiple times on
one element, the values are summed (e.g., multiple Abal lines).

Entry points:
  extract_mtext_from_dxf(file_path, layer) -> (list[str], list[str])
  parse_cad_mtext(text, valid_codes) -> CadTextBlock
  parse_cad_file(texts, valid_codes) -> (list[CadTextBlock], list[str])
"""

from __future__ import annotations

import re

from ..dtypes.cad import CadTextBlock


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Characters invalid in Excel sheet names (used as element mark)
_INVALID_NAME_CHARS = re.compile(r'[:\\/?*\[\]]')
_MAX_NAME_LENGTH = 31

# Pattern to extract numeric value (allows negative, decimal)
_NUMERIC_RE = re.compile(r'[+-]?\d+\.?\d*')


# ---------------------------------------------------------------------------
# DXF extraction
# ---------------------------------------------------------------------------

def extract_mtext_from_dxf(
    file_path: str,
    layer: str = "RUNDOWN",
) -> tuple[list[str], list[str]]:
    """Read DXF file and extract MTEXT plain text from the specified layer.

    Layer matching is case-insensitive, starts-with — so layer="RUNDOWN"
    matches both "RUNDOWN" and "RUNDOWN-STMW".

    Args:
        file_path: Path to the .dxf file.
        layer: Layer name prefix to filter (case-insensitive starts-with).

    Returns:
        (texts, warnings) — list of plain text strings, list of warnings.
    """
    import ezdxf

    doc = ezdxf.readfile(file_path)
    msp = doc.modelspace()
    layer_upper = layer.upper()

    texts: list[str] = []
    warnings: list[str] = []
    slt_count = 0

    for entity in msp:
        if not entity.dxf.layer.upper().startswith(layer_upper):
            continue
        if entity.dxftype() == "MTEXT":
            texts.append(entity.plain_text())
        elif entity.dxftype() == "TEXT":
            slt_count += 1

    # VBA: warn about single-line text on rundown layer
    if slt_count > 0:
        warnings.append(
            f"{slt_count} single-line TEXT entities found on '{layer}' layer "
            f"(should be MTEXT)"
        )

    return texts, warnings


# ---------------------------------------------------------------------------
# Single MText block parsing
# ---------------------------------------------------------------------------

def parse_cad_mtext(
    text: str,
    valid_codes: dict[str, str] | None = None,
) -> CadTextBlock:
    """Parse a single MTEXT block into structured data.

    Args:
        text: Plain text content of one MTEXT entity.
        valid_codes: Optional {UPPER_CODE: original_code} lookup for
                     area code validation. If None, codes accepted as-is
                     (uppercased).

    Returns:
        CadTextBlock with parsed data and any errors/warnings.
    """
    lines = text.strip().split("\n")
    if not lines:
        return CadTextBlock(element_name="", errors=["empty MTEXT block"])

    # --- Line 0: element name ---
    name = lines[0].strip()
    block = CadTextBlock(element_name=name)

    # Validate element name
    if not name:
        block.errors.append("empty element name")
        return block

    if "=" in name:
        block.errors.append(
            f"element name '{name}' contains '=' — likely missing name line"
        )
        return block

    if len(name) > _MAX_NAME_LENGTH:
        block.errors.append(
            f"element name '{name}' exceeds {_MAX_NAME_LENGTH} characters"
        )

    if _INVALID_NAME_CHARS.search(name):
        block.errors.append(
            f"element name '{name}' contains invalid characters (: \\ / ? * [ ])"
        )

    # --- Lines 1+: data fields ---
    has_dimension = False

    for raw_line in lines[1:]:
        line = raw_line.strip()
        if not line:
            continue

        first_char = line[0].upper()

        if first_char == "A":
            _parse_area_line(line, block, valid_codes)
        elif first_char == "D":
            _parse_dimension_line(line, block)
            has_dimension = True
        elif first_char == "P":
            _parse_perimeter_line(line, block)
        elif first_char == "B":
            _parse_beam_weight_line(line, block)
        else:
            block.errors.append(f"unrecognized line: '{line}'")

    if not has_dimension:
        block.warnings.append(
            f"no dimension (D=) line found for element '{name}'"
        )

    return block


# ---------------------------------------------------------------------------
# Line parsers
# ---------------------------------------------------------------------------

def _parse_area_line(
    line: str,
    block: CadTextBlock,
    valid_codes: dict[str, str] | None,
) -> None:
    """Parse area line: A{code} = {value} m²."""
    if "=" not in line:
        block.errors.append(f"area line missing '=': '{line}'")
        return

    # Extract code: everything between leading 'A' and '='
    eq_pos = line.index("=")
    raw_code = line[1:eq_pos].strip()

    if not raw_code:
        block.errors.append(f"area line missing code: '{line}'")
        return

    # Validate against known codes (case-insensitive)
    if valid_codes is not None:
        matched = valid_codes.get(raw_code.upper())
        if matched is None:
            block.errors.append(
                f"undefined area code '{raw_code}' in: '{line}'"
            )
            return
        code = matched
    else:
        code = raw_code.upper()

    # Extract numeric value after '=', strip non-numeric suffix (m², etc.)
    value_str = line[eq_pos + 1:].strip()
    num_match = _NUMERIC_RE.search(value_str)
    if num_match is None:
        block.errors.append(f"non-numeric area value in: '{line}'")
        return

    value = float(num_match.group())

    # Accumulate (same code can appear multiple times)
    block.areas[code] = block.areas.get(code, 0.0) + value


def _parse_dimension_line(line: str, block: CadTextBlock) -> None:
    """Parse dimension line: D = {w}x{h} or D = {d} dia / D = {d}d."""
    if "=" not in line:
        block.errors.append(f"dimension line missing '=': '{line}'")
        return

    eq_pos = line.index("=")
    value_str = line[eq_pos + 1:].strip()

    if not value_str:
        block.errors.append(f"empty dimension value in: '{line}'")
        return

    # Circular detection: contains "dia" (with optional trailing period)
    lower = value_str.lower()
    if "dia" in lower:
        # "500 dia." or "500 dia" → dim_x=500, dim_y="D"
        dia_pos = lower.index("dia")
        num_str = value_str[:dia_pos].strip()
        num_match = _NUMERIC_RE.search(num_str)
        if num_match is None:
            block.errors.append(f"non-numeric diameter in: '{line}'")
            return
        block.dimensions = (float(num_match.group()), "D")
        return

    # Circular: ends with lone "d" (e.g., "450d")
    if lower.rstrip().endswith("d") and "x" not in lower:
        num_str = value_str.rstrip()[:-1].strip()
        num_match = _NUMERIC_RE.search(num_str)
        if num_match:
            block.dimensions = (float(num_match.group()), "D")
            return

    # Rectangular: {w}x{h} (case-insensitive x)
    parts = re.split(r"[xX]", value_str, maxsplit=1)
    if len(parts) != 2:
        block.errors.append(f"cannot parse dimensions: '{line}'")
        return

    w_match = _NUMERIC_RE.search(parts[0].strip())
    h_match = _NUMERIC_RE.search(parts[1].strip())

    if w_match is None:
        block.errors.append(f"non-numeric width in: '{line}'")
        return
    if h_match is None:
        block.errors.append(f"non-numeric height in: '{line}'")
        return

    block.dimensions = (float(w_match.group()), float(h_match.group()))


def _parse_perimeter_line(line: str, block: CadTextBlock) -> None:
    """Parse perimeter line: P = {value}m."""
    if "=" not in line:
        block.errors.append(f"perimeter line missing '=': '{line}'")
        return

    eq_pos = line.index("=")
    value_str = line[eq_pos + 1:].strip()

    num_match = _NUMERIC_RE.search(value_str)
    if num_match is None:
        block.errors.append(f"non-numeric perimeter in: '{line}'")
        return

    # Accumulate (VBA adds to existing)
    block.perimeter_m += float(num_match.group())


def _parse_beam_weight_line(line: str, block: CadTextBlock) -> None:
    """Parse beam weight line: BM = {value} kN."""
    if "=" not in line:
        block.errors.append(f"beam weight line missing '=': '{line}'")
        return

    eq_pos = line.index("=")
    value_str = line[eq_pos + 1:].strip()

    num_match = _NUMERIC_RE.search(value_str)
    if num_match is None:
        block.errors.append(f"non-numeric beam weight in: '{line}'")
        return

    # Accumulate (VBA adds to existing)
    block.beam_weight_kn += float(num_match.group())


# ---------------------------------------------------------------------------
# Multi-block parsing with validation
# ---------------------------------------------------------------------------

def parse_cad_file(
    texts: list[str],
    valid_codes: list[str] | None = None,
) -> tuple[list[CadTextBlock], list[str]]:
    """Parse all MTEXT blocks from a single DXF file.

    Args:
        texts: List of plain text strings from extract_mtext_from_dxf().
        valid_codes: Optional list of valid area codes (e.g., ["RES", "BAL"]).
                     If provided, codes not in this list generate errors.

    Returns:
        (blocks, file_errors) — parsed blocks and file-level errors
        (duplicates, etc.).
    """
    # Build case-insensitive code lookup
    code_lookup: dict[str, str] | None = None
    if valid_codes is not None:
        code_lookup = {c.upper(): c for c in valid_codes}

    blocks: list[CadTextBlock] = []
    file_errors: list[str] = []
    seen_names: dict[str, int] = {}  # UPPER name → block index

    for text in texts:
        block = parse_cad_mtext(text, code_lookup)

        # Duplicate detection
        name_upper = block.element_name.upper()
        if name_upper in seen_names:
            file_errors.append(
                f"duplicate element '{block.element_name}' — "
                f"second occurrence ignored"
            )
            continue

        seen_names[name_upper] = len(blocks)
        blocks.append(block)

    return blocks, file_errors