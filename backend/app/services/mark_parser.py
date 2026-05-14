"""Mark parser — pure functions for parsing Revit element marks.

Handles real-world patterns from Revit:
  Simple:    C101, W103, C102A, W103B
  Prefixed:  PH-C12, MPHW1 (dash or no-dash prefix)
  Comments:  C12.corner column (dot-separated)
  Errors:    Wall marked C180 (type mismatch), digits-only "185"
"""
import dataclasses
import re


@dataclasses.dataclass
class ParsedMark:
    raw_mark: str
    prefix: str | None = None        # e.g. "PH-", "MPH"
    type_char: str | None = None     # "C" or "W" (uppercased)
    element_number: str | None = None  # "101", "12"
    suffix: str | None = None        # "A", "B" (trailing alpha after digits)
    comments: str | None = None      # text after "." separator
    parsed_successfully: bool = False


# Non-greedy prefix captures anything before the C/W type char.
# Handles "PH-C12", "MPHW1", and plain "C101".
_MARK_RE = re.compile(
    r"^(?P<prefix>.*?)"
    r"(?P<type_char>[CcWw])"
    r"(?P<number>\d+)"
    r"(?P<suffix>[A-Za-z]{0,3})"
    r"$"
)


def parse_mark(raw_mark: str | None) -> ParsedMark:
    """Parse a raw mark string into structured components.

    Returns ParsedMark with parsed_successfully=False for
    None, empty, or unparseable marks.
    """
    if not raw_mark or not raw_mark.strip():
        return ParsedMark(raw_mark=raw_mark or "")

    mark = raw_mark.strip()

    # Split on first "." to separate comments
    comments = None
    if "." in mark:
        mark_body, comments = mark.split(".", 1)
        comments = comments.strip() or None
        mark_body = mark_body.strip()
    else:
        mark_body = mark

    # Spaces in mark body → unparseable (e.g. "200 PIER")
    if " " in mark_body:
        return ParsedMark(raw_mark=raw_mark, comments=comments)

    m = _MARK_RE.match(mark_body)
    if not m:
        return ParsedMark(raw_mark=raw_mark, comments=comments)

    prefix = m.group("prefix") or None
    suffix = m.group("suffix") or None

    return ParsedMark(
        raw_mark=raw_mark,
        prefix=prefix,
        type_char=m.group("type_char").upper(),
        element_number=m.group("number"),
        suffix=suffix,
        comments=comments,
        parsed_successfully=True,
    )


def detect_mark_error(parsed: ParsedMark, element_type_from_db: str) -> bool:
    """Return True if the mark's type_char doesn't match the element's DB type.

    element_type_from_db: "Column" or "Wall" (from which dbo table).
    """
    if not parsed.parsed_successfully or parsed.type_char is None:
        return False

    expected = "C" if element_type_from_db == "Column" else "W"
    return parsed.type_char != expected


def canonical_mark(parsed: ParsedMark, element_type_from_db: str) -> str:
    """Build canonical mark, correcting type_char if mismatched.

    - Strips prefix and comments (canonical = type + number + suffix).
    - Corrects type: wall with "C12" mark → "W12".
    - Returns raw_mark as-is if parse failed.
    """
    if not parsed.parsed_successfully:
        return parsed.raw_mark

    correct_type = "C" if element_type_from_db == "Column" else "W"
    return f"{correct_type}{parsed.element_number}{parsed.suffix or ''}"