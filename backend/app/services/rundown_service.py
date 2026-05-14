"""Rundown adapter service — bridges DB ↔ rundown_engine.

All parsing and computation is delegated to the standalone rundown_engine package.
This service handles only:
  1. File I/O (temp file for openpyxl / ezdxf)
  2. DB read/write (ORM ↔ engine dataclasses)
  3. Identity hub resolution (element_mark → element_identity_id)

IMPORTANT: No formula logic here. Call engine functions, map results to ORM rows.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy.orm import Session

if TYPE_CHECKING:
    from rundown_engine.dtypes.export import ExportInput

from app.models.design import LoadTable, Rundown, RundownTransfer
from app.models.management import ProjectMeta
from rundown_engine.compute import compute_rundown
from rundown_engine.dtypes.cad import CadTextBlock
from rundown_engine.dtypes.inputs import (
    ElementDimensions,
    ElementInput,
    FloorInput,
    LevelPair,
    LoadTypeDef,
    RundownInput,
)
from rundown_engine.dtypes.outputs import ElementResult, FloorResult, RundownResult
from rundown_engine.dtypes.spreadsheet import DiscrepancyRow, SpreadsheetParseResult
from rundown_engine.dtypes.validation import ValidationResult
from rundown_engine.parsers.cad_dxf import extract_mtext_from_dxf, parse_cad_file
from rundown_engine.parsers.spreadsheet import (
    _classify_element,
    compare_results,
    parse_rundown_spreadsheet,
)


# ---------------------------------------------------------------------------
# Spreadsheet path
# ---------------------------------------------------------------------------

def _write_temp_xlsm(file_bytes: bytes) -> str:
    """Write file_bytes to a temp .xlsm file and return the path."""
    with tempfile.NamedTemporaryFile(suffix=".xlsm", delete=False) as f:
        f.write(file_bytes)
        return f.name


def parse_spreadsheet(file_bytes: bytes) -> SpreadsheetParseResult:
    """Parse .xlsm → SpreadsheetParseResult.  No compute, no DB write.

    Used by the confirm path where compute_and_store() handles computation.
    """
    tmp_path = _write_temp_xlsm(file_bytes)
    try:
        return parse_rundown_spreadsheet(tmp_path)
    finally:
        os.unlink(tmp_path)


def preview_spreadsheet(file_bytes: bytes) -> SpreadsheetParseResult:
    """Parse .xlsm → SpreadsheetParseResult with discrepancy comparison.  No DB write.

    Runs compute_rundown() on extracted inputs and compare_results()
    to populate the discrepancy list (engine vs. Excel values).
    Used by the upload preview path.
    """
    tmp_path = _write_temp_xlsm(file_bytes)
    try:
        result = parse_rundown_spreadsheet(tmp_path)

        # Compute from extracted inputs + compare against imported Excel values
        if result.elements and not result.errors:
            input_data = RundownInput(
                project_number=result.project_number,
                load_types=result.load_types,
                elements=result.elements,
            )
            computed = compute_rundown(input_data)
            result.discrepancies = compare_results(computed, result.imported_values)

        return result
    finally:
        os.unlink(tmp_path)


def _ensure_project_meta(
    db: Session,
    project_number: str,
    parse_result: SpreadsheetParseResult,
) -> None:
    """Upsert a project_meta row so the Rundown FK constraint is satisfied.

    The spreadsheet upload path may run before any Revit model is loaded,
    so the trigger-based row may not exist yet.
    """
    meta = (
        db.query(ProjectMeta)
        .filter(ProjectMeta.project_number == project_number)
        .first()
    )
    if meta is None:
        db.add(ProjectMeta(
            project_number=project_number,
            job_name=parse_result.job_name or None,
            designer=parse_result.designer or None,
        ))
    else:
        if parse_result.job_name and not meta.job_name:
            meta.job_name = parse_result.job_name
        if parse_result.designer and not meta.designer:
            meta.designer = parse_result.designer
    db.flush()


def _sync_load_tables(
    db: Session,
    project_number: str,
    load_types: list[LoadTypeDef],
    cladding_kpa: float = 1.5,
) -> None:
    """Upsert load types to design.load_tables for this project.

    Replaces existing rows for the project_number so the load table
    always reflects the most recent upload. Deduplicates by code
    (spreadsheets may list the same type twice with identical values).

    Also inserts a "CLADDING" row to persist the building-wide cladding
    load (kPa). Default 1.5 kPa. This row does not participate in area
    calculations; it is used only for the perimeter-based DL formula.
    """
    # Only delete rundown-uploaded rows (project_id=0), preserve Revit-path rows
    db.query(LoadTable).filter(
        LoadTable.project_number == project_number,
        LoadTable.project_id == 0,
    ).delete(synchronize_session=False)
    seen_codes: set[str] = set()
    for lt in load_types:
        if lt.code in seen_codes:
            continue
        seen_codes.add(lt.code)
        db.add(LoadTable(
            project_number=project_number,
            project_id=0,
            name=lt.code,
            description=lt.description,
            dead_load_kpa=lt.dead_kpa,
            live_load_kpa=lt.live_kpa,
            llrf_type=lt.llrf_type,
            created_by="rundown_upload",
        ))
    # Persist building-wide cladding load as a special row
    db.add(LoadTable(
        project_number=project_number,
        project_id=0,
        name="CLADDING",
        description="Building-wide cladding load (perimeter × height)",
        dead_load_kpa=cladding_kpa,
        live_load_kpa=0,
        llrf_type="P",
        created_by="rundown_upload",
    ))
    db.flush()


def replace_load_tables(
    db: Session,
    project_number: str,
    entries: list[dict],
) -> int:
    """Replace rundown load types (project_id=0) from user-provided entries.

    Used by the POST /rundown/load-types endpoint for manual editing.
    Does NOT touch Revit-path rows (project_id != 0).
    Preserves created_by for unchanged rows; only marks changed/new as 'user_edit'.
    Returns the number of rows written.
    """
    # Snapshot existing rows keyed by name
    existing = (
        db.query(LoadTable)
        .filter(
            LoadTable.project_number == project_number,
            LoadTable.project_id == 0,
        )
        .all()
    )
    old_by_name: dict[str, LoadTable] = {r.name: r for r in existing}

    # Delete all existing (will re-insert)
    db.query(LoadTable).filter(
        LoadTable.project_number == project_number,
        LoadTable.project_id == 0,
    ).delete(synchronize_session=False)

    seen: set[str] = set()
    count = 0
    for e in entries:
        name = e.get("name", "")
        if not name or name in seen:
            continue
        seen.add(name)

        # Determine created_by: keep original if row is unchanged
        old = old_by_name.get(name)
        if old is not None:
            same = (
                old.description == (e.get("description") or "")
                and old.dead_load_kpa == e.get("dead_load_kpa")
                and old.live_load_kpa == e.get("live_load_kpa")
                and old.llrf_type == (e.get("llrf_type") or "N")
            )
            created_by = old.created_by if same else "user_edit"
        else:
            created_by = "user_edit"

        db.add(LoadTable(
            project_number=project_number,
            project_id=0,
            name=name,
            description=e.get("description", ""),
            dead_load_kpa=e.get("dead_load_kpa"),
            live_load_kpa=e.get("live_load_kpa"),
            llrf_type=e.get("llrf_type", "N"),
            created_by=created_by,
        ))
        count += 1
    db.commit()
    return count


def compute_and_store(
    db: Session,
    project_number: str,
    parse_result: SpreadsheetParseResult,
) -> tuple[RundownResult, int]:
    """Compute rundown from spreadsheet parse result and store all rows to DB.

    Deletes existing rundown rows for the project before inserting.
    One Rundown row per (element, floor).

    Args:
        db: SQLAlchemy session.
        project_number: Project number (e.g. "20205").
        parse_result: Output of parse_rundown_spreadsheet().

    Returns:
        Tuple of (RundownResult, rows_written).
    """
    input_data = RundownInput(
        project_number=project_number,
        load_types=parse_result.load_types,
        elements=parse_result.elements,
    )
    run_result = compute_rundown(input_data)

    # Ensure project_meta row exists (FK requirement for Rundown rows)
    _ensure_project_meta(db, project_number, parse_result)

    # Resolve cladding_kpa: must be uniform across all elements
    clad_values = {e.cladding_kpa for e in parse_result.elements}
    if len(clad_values) == 1:
        cladding = clad_values.pop()
    else:
        cladding = 0.0
        run_result.validation.warnings.append(
            f"Inconsistent cladding_kpa across elements: {sorted(clad_values)}. "
            "Stored as 0 — review and correct in load table."
        )

    # Sync load types to design.load_tables (+ CLADDING row)
    _sync_load_tables(db, project_number, parse_result.load_types, cladding_kpa=cladding)

    # Delete existing rows for this project
    db.query(Rundown).filter(Rundown.project_number == project_number).delete(
        synchronize_session=False
    )

    # Map engine output → ORM rows
    rows: list[Rundown] = []
    for elem_result in run_result.elements:
        for floor_order, floor in enumerate(elem_result.floors):
            rows.append(
                _floor_to_orm(project_number, elem_result, floor, floor_order, "spreadsheet")
            )

    db.bulk_save_objects(rows)

    # Save transfer definitions to rundown_transfers table
    _save_transfers_to_table(db, project_number, parse_result.elements)

    db.commit()
    return run_result, len(rows)


def _floor_to_orm(
    project_number: str,
    elem: ElementResult,
    floor: FloorResult,
    floor_order: int,
    data_source: str,
) -> Rundown:
    """Map one FloorResult to one Rundown ORM row (complete 1:1 field mapping)."""
    return Rundown(
        project_number=project_number,
        element_guid=elem.mark,            # mark stored in legacy guid column
        element_mark=elem.mark,
        element_type=elem.element_type,
        bot_level=floor.bot_level,
        top_level=floor.top_level,
        project_id=0,                      # resolved later when Revit project linked
        level_id=0,                        # resolved later when level identity matched
        load_table_id=None,                # NULL for spreadsheet path; resolved later via Revit
        floor_order=floor_order,
        data_source=data_source,

        # Legacy aggregate columns (backward compat)
        cumulative_dead_kn=floor.dl_cumulative_kn or 0,
        cumulative_live_kn=floor.ll_cumulative_kn or 0,

        # Geometry
        story_height_m=floor.story_height_m,
        concrete_mpa=floor.concrete_mpa,
        dim_x_mm=floor.dim_x_mm,
        dim_y=str(floor.dim_y) if floor.dim_y is not None else None,
        cross_section_m2=floor.cross_section_m2,

        # DL breakdown
        dl_from_above_kn=floor.dl_from_above_kn,
        dl_floor_load_kn=floor.dl_floor_load_kn,
        dl_transfer_kn=floor.dl_transfer_kn,
        dl_self_weight_kn=floor.dl_self_weight_kn,
        dl_cladding_kn=floor.dl_cladding_kn,
        dl_beam_weight_kn=floor.dl_beam_weight_kn,
        dl_cumulative_kn=floor.dl_cumulative_kn,

        # LL breakdown
        ll_reducible_kn=floor.ll_reducible_kn,
        ll_non_reducible_this_floor_kn=floor.ll_non_reducible_this_floor_kn,
        ll_transfer_kn=floor.ll_transfer_kn,
        dy_cumulative_kn=floor.dy_cumulative_kn,
        ll_cumulative_kn=floor.ll_cumulative_kn,

        # Areas
        area_this_floor_m2=floor.area_this_floor_m2,
        transfer_area_m2=floor.transfer_area_m2,
        cum_area_m2=floor.cum_area_m2,

        # Derived
        pw_kn=floor.pw_kn,
        pf_kn=floor.pf_kn,
        f_over_a_mpa=floor.f_over_a_mpa,
        alpha_factor=floor.alpha,
        phi=floor.phi,
        pct_steel=floor.pct_steel,

        # Inputs carried through
        beam_weight_kn=floor.beam_weight_kn,
        cladding_perimeter_m=floor.cladding_perimeter_m,

        # Rebar
        as_mm2=floor.as_mm2,
        bar_size=floor.bar_size,
        qty=floor.qty,
        n_bars=floor.n_bars,
        c_bars=floor.c_bars,
        rebar_design=floor.rebar_design,

        # JSON breakdowns
        area_by_type_json=json.dumps(floor.area_by_type),
        cum_area_by_type_json=json.dumps(floor.cum_area_by_type),
        llrf_by_type_json=json.dumps(floor.llrf_by_type),
        ll_non_reducible_by_type_json=json.dumps(floor.ll_non_reducible_by_type),

    )


# ---------------------------------------------------------------------------
# CAD DXF path
# ---------------------------------------------------------------------------

def _write_temp_dxf(file_bytes: bytes) -> str:
    """Write file_bytes to a temp .dxf file and return the path."""
    with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as f:
        f.write(file_bytes)
        return f.name


def compute_and_store_cad(
    db: Session,
    project_number: str,
    dxf_files: dict[str, bytes],
    file_level_map: list[dict],
    level_pairs: list[dict],
    load_types: list[dict],
    cladding_kpa: float = 0.0,
) -> tuple[RundownResult, int]:
    """Parse DXF files, build RundownInput, compute, and store to DB.

    Args:
        db: SQLAlchemy session.
        project_number: Project number.
        dxf_files: {filename: bytes} of uploaded DXF files.
        file_level_map: [{filename, bot_level, top_level}] — maps each DXF to a level pair.
        level_pairs: [{bot, top, height_m, concrete_mpa}] — full floor stack, top-to-bottom.
        load_types: [{code, description, dead_kpa, live_kpa, llrf_type}].
        cladding_kpa: Default cladding kPa for all elements.

    Returns:
        Tuple of (RundownResult, rows_written).
    """
    # 1. Build load type defs
    lt_defs = [
        LoadTypeDef(
            code=lt["code"],
            description=lt.get("description", lt["code"]),
            dead_kpa=float(lt["dead_kpa"]),
            live_kpa=float(lt["live_kpa"]),
            llrf_type=lt.get("llrf_type", "N"),
        )
        for lt in load_types
    ]
    valid_codes = {lt.code for lt in lt_defs}

    # 2. Build level pair list (top-to-bottom ordering)
    lp_list = [
        LevelPair(
            bot_level=str(lp["bot"]),
            top_level=str(lp["top"]),
            story_height_m=float(lp["height_m"]),
            concrete_mpa=float(lp["concrete_mpa"]),
        )
        for lp in level_pairs
    ]

    # 3. Build file → level pair lookup
    #    file_level_map: [{filename, bot_level, top_level}]
    file_to_lp: dict[str, tuple[str, str]] = {}
    for flm in file_level_map:
        file_to_lp[flm["filename"]] = (str(flm["bot_level"]), str(flm["top_level"]))

    # 4. Parse each DXF → CadTextBlock list, keyed by level pair
    #    blocks_by_level: {(bot, top): [CadTextBlock, ...]}
    blocks_by_level: dict[tuple[str, str], list[CadTextBlock]] = {}
    all_errors: list[str] = []

    for filename, file_bytes in dxf_files.items():
        if filename not in file_to_lp:
            continue  # unmapped file — skip
        lp_key = file_to_lp[filename]

        tmp_path = _write_temp_dxf(file_bytes)
        try:
            texts, warnings = extract_mtext_from_dxf(tmp_path)
            all_errors.extend(warnings)
            blocks, file_errors = parse_cad_file(texts, valid_codes=valid_codes)
            all_errors.extend(file_errors)
            blocks_by_level.setdefault(lp_key, []).extend(blocks)
        finally:
            os.unlink(tmp_path)

    if all_errors:
        # Log but don't fail — continue with what we have
        pass

    # 5. Collect all unique element names across all levels
    all_marks: set[str] = set()
    for blocks in blocks_by_level.values():
        for block in blocks:
            all_marks.add(block.element_name)

    # 6. Build ElementInput for each element
    elements: list[ElementInput] = []
    for mark in sorted(all_marks):
        floors: list[FloorInput] = []
        for lp in lp_list:
            lp_key = (lp.bot_level, lp.top_level)
            # Find this element's block at this level (if any)
            block: CadTextBlock | None = None
            for b in blocks_by_level.get(lp_key, []):
                if b.element_name == mark:
                    block = b
                    break

            if block is not None and block.dimensions is not None:
                dims = ElementDimensions(
                    dim_x_mm=block.dimensions[0],
                    dim_y=block.dimensions[1],
                )
                area_by_type = dict(block.areas)
                beam_wt = block.beam_weight_kn
                clad_p = block.perimeter_m
            else:
                dims = None
                area_by_type = {}
                beam_wt = 0.0
                clad_p = 0.0

            floors.append(FloorInput(
                level=lp,
                dimensions=dims,
                area_by_type=area_by_type,
                beam_weight_kn=beam_wt,
                cladding_perimeter_m=clad_p,
            ))

        elements.append(ElementInput(
            mark=mark,
            element_type=_classify_element(mark),
            floors=floors,
            transfers_received=[],
            cladding_kpa=cladding_kpa,
        ))

    # 7. Compute
    input_data = RundownInput(
        project_number=project_number,
        load_types=lt_defs,
        elements=elements,
    )
    run_result = compute_rundown(input_data)

    # 8. Store to DB (same pattern as spreadsheet path)
    # Ensure project_meta row exists
    exists = (
        db.query(ProjectMeta)
        .filter(ProjectMeta.project_number == project_number)
        .first()
    )
    if exists is None:
        db.add(ProjectMeta(project_number=project_number))
        db.flush()

    # Sync load types to design.load_tables (+ CLADDING row)
    _sync_load_tables(db, project_number, lt_defs, cladding_kpa=cladding_kpa)

    db.query(Rundown).filter(Rundown.project_number == project_number).delete(
        synchronize_session=False
    )

    rows: list[Rundown] = []
    for elem_result in run_result.elements:
        for floor_order, floor in enumerate(elem_result.floors):
            rows.append(
                _floor_to_orm(project_number, elem_result, floor, floor_order, "cad")
            )

    db.bulk_save_objects(rows)

    # Save transfer definitions to rundown_transfers table
    _save_transfers_to_table(db, project_number, elements)

    db.commit()
    return run_result, len(rows)


# ---------------------------------------------------------------------------
# DB read helpers
# ---------------------------------------------------------------------------

def get_rundown_rows(db: Session, project_number: str) -> list[Rundown]:
    """Return all rundown rows for a project, ordered by mark + floor_order."""
    return (
        db.query(Rundown)
        .filter(Rundown.project_number == project_number)
        .order_by(Rundown.element_mark, Rundown.floor_order)
        .all()
    )


def get_element_rows(db: Session, project_number: str, mark: str) -> list[Rundown]:
    """Return all floor rows for a single element, ordered top-to-bottom."""
    return (
        db.query(Rundown)
        .filter(
            Rundown.project_number == project_number,
            Rundown.element_mark == mark,
        )
        .order_by(Rundown.floor_order)
        .all()
    )


def group_by_element(rows: list[Rundown]) -> dict[str, list[Rundown]]:
    """Group a flat list of Rundown rows by element_mark (preserves order)."""
    groups: dict[str, list[Rundown]] = {}
    for row in rows:
        mark = row.element_mark or row.element_guid
        groups.setdefault(mark, []).append(row)
    return groups


def parse_json_field(value: Optional[str]) -> dict[str, float]:
    """Safely parse a JSON string field back to a dict."""
    if not value:
        return {}
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {}


def floor_row_to_schema_dict(row: Rundown) -> dict:
    """Convert one Rundown ORM row to a dict matching FloorResultRead schema."""
    return {
        "id": row.id,
        "bot_level": row.bot_level or "",
        "top_level": row.top_level or "",
        "story_height_m": float(row.story_height_m) if row.story_height_m is not None else None,
        "concrete_mpa": float(row.concrete_mpa) if row.concrete_mpa is not None else None,
        "dim_x_mm": float(row.dim_x_mm) if row.dim_x_mm is not None else None,
        "dim_y": row.dim_y,
        "cross_section_m2": float(row.cross_section_m2) if row.cross_section_m2 is not None else None,
        "dl_from_above_kn": float(row.dl_from_above_kn) if row.dl_from_above_kn is not None else None,
        "dl_floor_load_kn": float(row.dl_floor_load_kn) if row.dl_floor_load_kn is not None else None,
        "dl_transfer_kn": float(row.dl_transfer_kn) if row.dl_transfer_kn is not None else None,
        "dl_self_weight_kn": float(row.dl_self_weight_kn) if row.dl_self_weight_kn is not None else None,
        "dl_cladding_kn": float(row.dl_cladding_kn) if row.dl_cladding_kn is not None else None,
        "dl_beam_weight_kn": float(row.dl_beam_weight_kn) if row.dl_beam_weight_kn is not None else None,
        "dl_cumulative_kn": float(row.dl_cumulative_kn) if row.dl_cumulative_kn is not None else None,
        "ll_reducible_kn": float(row.ll_reducible_kn) if row.ll_reducible_kn is not None else None,
        "ll_non_reducible_this_floor_kn": float(row.ll_non_reducible_this_floor_kn) if row.ll_non_reducible_this_floor_kn is not None else None,
        "ll_transfer_kn": float(row.ll_transfer_kn) if row.ll_transfer_kn is not None else None,
        "dy_cumulative_kn": float(row.dy_cumulative_kn) if row.dy_cumulative_kn is not None else None,
        "ll_cumulative_kn": float(row.ll_cumulative_kn) if row.ll_cumulative_kn is not None else None,
        "area_this_floor_m2": float(row.area_this_floor_m2) if row.area_this_floor_m2 is not None else None,
        "transfer_area_m2": float(row.transfer_area_m2) if row.transfer_area_m2 is not None else None,
        "cum_area_m2": float(row.cum_area_m2) if row.cum_area_m2 is not None else None,
        "pw_kn": float(row.pw_kn) if row.pw_kn is not None else None,
        "pf_kn": float(row.pf_kn) if row.pf_kn is not None else None,
        "f_over_a_mpa": float(row.f_over_a_mpa) if row.f_over_a_mpa is not None else None,
        "alpha_factor": float(row.alpha_factor) if row.alpha_factor is not None else None,
        "phi": float(row.phi) if row.phi is not None else None,
        "pct_steel": float(row.pct_steel) if row.pct_steel is not None else None,
        "beam_weight_kn": float(row.beam_weight_kn) if row.beam_weight_kn is not None else None,
        "cladding_perimeter_m": float(row.cladding_perimeter_m) if row.cladding_perimeter_m is not None else None,
        "as_mm2": float(row.as_mm2) if row.as_mm2 is not None else None,
        "bar_size": row.bar_size,
        "qty": row.qty,
        "n_bars": row.n_bars,
        "c_bars": row.c_bars,
        "rebar_design": row.rebar_design,
        "qty_override": bool(row.qty_override) if row.qty_override is not None else False,
        "n_bars_override": bool(row.n_bars_override) if row.n_bars_override is not None else False,
        "c_bars_override": bool(row.c_bars_override) if row.c_bars_override is not None else False,
        "area_by_type": parse_json_field(row.area_by_type_json),
        "cum_area_by_type": parse_json_field(row.cum_area_by_type_json),
        "llrf_by_type": parse_json_field(row.llrf_by_type_json),
        "ll_non_reducible_by_type": parse_json_field(row.ll_non_reducible_by_type_json),
        "data_source": row.data_source,
        "floor_order": row.floor_order,
    }


# ---------------------------------------------------------------------------
# Summary matrix
# ---------------------------------------------------------------------------

SUMMARY_METRIC_COLUMNS: dict[str, str] = {
    "DL": "dl_cumulative_kn",
    "LL": "ll_cumulative_kn",
    "PW": "pw_kn",
    "PF": "pf_kn",
    "F / A": "f_over_a_mpa",
    "% Steel": "pct_steel",
    "As": "as_mm2",
    "AREA": "area_this_floor_m2",
    "XFER AREA": "transfer_area_m2",
    "CUM AREA": "cum_area_m2",
}


def get_summary_matrix(
    db: Session, project_number: str, metric: str,
) -> dict:
    """Build a cross-element pivot: levels on rows, elements on columns.

    Returns dict matching SummaryMatrixRead schema:
      columns: [{mark, element_type}]   — one per element
      levels: [str]                      — ordered top-level names (rows)
      metric: str                        — echoed back
      values: [[float|None]]            — values[level_idx][col_idx]
    """
    col_name = SUMMARY_METRIC_COLUMNS.get(metric)
    if col_name is None:
        raise ValueError(
            f"Unknown metric '{metric}'. "
            f"Valid: {', '.join(SUMMARY_METRIC_COLUMNS.keys())}"
        )

    rows = get_rundown_rows(db, project_number)
    if not rows:
        return {"columns": [], "levels": [], "metric": metric, "values": []}

    # Collect ordered levels (by floor_order ascending — top-to-bottom)
    # Each level is a {bot_level, top_level} pair, keyed by top_level for lookup
    level_order: list[dict[str, str]] = []
    seen_levels: set[str] = set()
    for r in rows:
        top = r.top_level or ""
        if top not in seen_levels:
            seen_levels.add(top)
            level_order.append({
                "bot_level": r.bot_level or "",
                "top_level": top,
            })

    level_idx = {lp["top_level"]: i for i, lp in enumerate(level_order)}

    # Group by element — preserves insertion order
    groups = group_by_element(rows)

    # Build column list (one per element)
    columns = []
    mark_idx: dict[str, int] = {}
    for i, (mark, floor_rows) in enumerate(groups.items()):
        columns.append({"mark": mark, "element_type": floor_rows[0].element_type or ""})
        mark_idx[mark] = i

    # Build values matrix: values[level_idx][col_idx]
    n_levels = len(level_order)
    n_cols = len(columns)
    values: list[list[float | None]] = [[None] * n_cols for _ in range(n_levels)]

    for mark, floor_rows in groups.items():
        ci = mark_idx[mark]
        for r in floor_rows:
            lvl = r.top_level or ""
            li = level_idx.get(lvl)
            if li is None:
                continue
            raw = getattr(r, col_name, None)
            values[li][ci] = float(raw) if raw is not None else None

    return {
        "columns": columns,
        "levels": level_order,
        "metric": metric,
        "values": values,
    }


# ---------------------------------------------------------------------------
# Rebar edit
# ---------------------------------------------------------------------------

def update_rebar(
    db: Session, project_number: str, row_id: int, patch: dict,
) -> Rundown:
    """Update rebar fields on a single rundown row with engine recomputation.

    Args:
        patch: dict with optional keys: bar_size, qty, n_bars, c_bars,
               qty_override, n_bars_override, c_bars_override.

    Returns:
        Updated Rundown ORM row.

    Raises:
        ValueError: If row not found or project mismatch.
    """
    from rundown_engine.recompute import recompute_rebar

    row = db.query(Rundown).filter(
        Rundown.id == row_id,
        Rundown.project_number == project_number,
    ).first()
    if row is None:
        raise ValueError(f"Row {row_id} not found in project '{project_number}'")

    # Determine bar_size: from patch or existing
    bar_size = patch.get("bar_size", row.bar_size)
    qty_override = patch.get("qty_override", False)
    n_bars_override = patch.get("n_bars_override", False)
    c_bars_override = patch.get("c_bars_override", False)

    result = recompute_rebar(
        bar_size=bar_size,
        qty=patch.get("qty"),
        n_bars=patch.get("n_bars"),
        c_bars=patch.get("c_bars"),
        qty_override=qty_override,
        n_bars_override=n_bars_override,
        c_bars_override=c_bars_override,
        as_mm2=float(row.as_mm2) if row.as_mm2 is not None else None,
        dim_x_mm=float(row.dim_x_mm) if row.dim_x_mm is not None else None,
        dim_y=row.dim_y,
        cross_section_m2=float(row.cross_section_m2) if row.cross_section_m2 is not None else None,
    )

    row.bar_size = result.bar_size
    row.qty = result.qty
    row.n_bars = result.n_bars
    row.c_bars = result.c_bars
    row.rebar_design = result.rebar_design
    row.qty_override = not result.qty_auto
    row.n_bars_override = not result.n_bars_auto
    row.c_bars_override = not result.c_bars_auto

    db.commit()
    db.refresh(row)
    return row


# ---------------------------------------------------------------------------
# Transfer management
# ---------------------------------------------------------------------------

def _save_transfers_to_table(
    db: Session,
    project_number: str,
    elements: list,
) -> int:
    """Save transfer definitions from ElementInput list to rundown_transfers table.

    Called by both upload flows (spreadsheet + CAD) after computation.
    Deletes existing transfers for the project first.
    """
    db.query(RundownTransfer).filter(
        RundownTransfer.project_number == project_number,
    ).delete(synchronize_session=False)

    count = 0
    seen: set[tuple[str, str, str]] = set()
    for elem in elements:
        mark = elem.mark
        for t in getattr(elem, "transfers_received", []):
            key = (mark, t.source_element, t.target_level)
            if key in seen:
                continue
            seen.add(key)
            db.add(RundownTransfer(
                project_number=project_number,
                target_element=mark,
                source_element=t.source_element,
                target_level=t.target_level,
                percent=float(t.percent),
                created_by="upload",
            ))
            count += 1
    return count


def get_transfers(
    db: Session, project_number: str, mark: str | None = None,
) -> list[RundownTransfer]:
    """Return transfer definitions for a project, optionally filtered to one target element."""
    q = db.query(RundownTransfer).filter(
        RundownTransfer.project_number == project_number,
    )
    if mark:
        q = q.filter(RundownTransfer.target_element == mark)
    return q.order_by(RundownTransfer.target_element, RundownTransfer.target_level).all()


def replace_transfers(
    db: Session,
    project_number: str,
    mark: str,
    transfers: list[dict],
) -> int:
    """Replace all transfer definitions for one element.

    Args:
        transfers: [{source_element, target_level, percent}]

    Returns:
        Number of transfer rows written.
    """
    db.query(RundownTransfer).filter(
        RundownTransfer.project_number == project_number,
        RundownTransfer.target_element == mark,
    ).delete(synchronize_session=False)

    count = 0
    for t in transfers:
        source = t.get("source_element", "")
        level = t.get("target_level", "")
        pct = float(t.get("percent", 0))
        if not source or not level or pct <= 0:
            continue
        db.add(RundownTransfer(
            project_number=project_number,
            target_element=mark,
            source_element=source,
            target_level=level,
            percent=pct,
            created_by="user",
        ))
        count += 1
    db.commit()
    return count


def _parse_dim_y(dim_y_str: str | None) -> str | float:
    """Convert stored dim_y string back to engine input type."""
    if dim_y_str is None:
        return "D"
    if dim_y_str in ("D", "S", "W"):
        return dim_y_str
    try:
        return float(dim_y_str)
    except (ValueError, TypeError):
        return dim_y_str


def recompute_project(
    db: Session,
    project_number: str,
) -> tuple[RundownResult, int]:
    """Recompute entire project from stored floor data + transfer definitions.

    Reads geometry/area/dimension data from existing rundown rows,
    loads from load_tables, and transfer definitions from rundown_transfers.
    Runs full compute_rundown() and replaces all rundown rows.
    """
    rows = get_rundown_rows(db, project_number)
    if not rows:
        raise ValueError(f"No rundown rows for project '{project_number}'")

    groups = group_by_element(rows)

    # 1. Read load types
    lt_rows = (
        db.query(LoadTable)
        .filter(LoadTable.project_number == project_number, LoadTable.project_id == 0)
        .order_by(LoadTable.id)
        .all()
    )
    cladding_kpa = 0.0
    load_types: list[LoadTypeDef] = []
    for r in lt_rows:
        if r.name == "CLADDING":
            cladding_kpa = float(r.dead_load_kpa) if r.dead_load_kpa else 0.0
            continue
        load_types.append(LoadTypeDef(
            code=r.name,
            description=r.description or "",
            dead_kpa=float(r.dead_load_kpa) if r.dead_load_kpa else 0.0,
            live_kpa=float(r.live_load_kpa) if r.live_load_kpa else 0.0,
            llrf_type=r.llrf_type or "N",
        ))

    # 2. Read transfer definitions
    transfer_rows = (
        db.query(RundownTransfer)
        .filter(RundownTransfer.project_number == project_number)
        .all()
    )
    from rundown_engine.dtypes.inputs import TransferDef
    transfers_by_target: dict[str, list[TransferDef]] = {}
    for tr in transfer_rows:
        td = TransferDef(
            source_element=tr.source_element,
            target_level=tr.target_level,
            percent=float(tr.percent),
            dl_kn=None,       # Force Path B — engine resolves from computed
            ll_kn=None,
            cum_area_m2=None,
        )
        transfers_by_target.setdefault(tr.target_element, []).append(td)

    # 3. Build ElementInput for each element from stored DB rows
    elements: list[ElementInput] = []
    original_data_source = rows[0].data_source or "recompute"
    for mark, floor_rows in groups.items():
        floors: list[FloorInput] = []
        for row in floor_rows:
            dims = None
            if row.dim_x_mm is not None and row.dim_y is not None:
                dims = ElementDimensions(
                    dim_x_mm=float(row.dim_x_mm),
                    dim_y=_parse_dim_y(row.dim_y),
                )
            area_by_type = parse_json_field(row.area_by_type_json)
            floors.append(FloorInput(
                level=LevelPair(
                    bot_level=row.bot_level or "",
                    top_level=row.top_level or "",
                    story_height_m=float(row.story_height_m or 0),
                    concrete_mpa=float(row.concrete_mpa or 30),
                ),
                dimensions=dims,
                area_by_type=area_by_type,
                beam_weight_kn=float(row.beam_weight_kn or 0),
                cladding_perimeter_m=float(row.cladding_perimeter_m or 0),
                bar_size=row.bar_size,
                qty=row.qty if row.qty_override else None,
                n_bars=row.n_bars if row.n_bars_override else None,
                c_bars=row.c_bars if row.c_bars_override else None,
            ))

        elements.append(ElementInput(
            mark=mark,
            element_type=floor_rows[0].element_type or "Column",
            floors=floors,
            transfers_received=transfers_by_target.get(mark, []),
            cladding_kpa=cladding_kpa,
        ))

    # 4. Compute
    input_data = RundownInput(
        project_number=project_number,
        load_types=load_types,
        elements=elements,
    )
    run_result = compute_rundown(input_data)

    # 5. Replace all rundown rows
    db.query(Rundown).filter(
        Rundown.project_number == project_number,
    ).delete(synchronize_session=False)

    orm_rows: list[Rundown] = []
    for elem_result in run_result.elements:
        for floor_order, floor in enumerate(elem_result.floors):
            orm_rows.append(
                _floor_to_orm(project_number, elem_result, floor, floor_order, original_data_source)
            )

    db.bulk_save_objects(orm_rows)
    db.commit()
    return run_result, len(orm_rows)


# ---------------------------------------------------------------------------
# Spreadsheet export
# ---------------------------------------------------------------------------

def build_export_input(
    db: Session,
    project_number: str,
    template_path: str,
) -> "ExportInput":
    """Gather all data from DB and build an ExportInput for the export module.

    Reads project_meta, load_tables, rundown rows, and rundown_transfers.
    """
    from rundown_engine.dtypes.export import (
        ExportElement,
        ExportFloor,
        ExportInput,
        ExportLevelPair,
        ExportLoadType,
        ExportMetadata,
        ExportTransfer,
    )

    # 1. Metadata
    meta = db.query(ProjectMeta).filter(
        ProjectMeta.project_number == project_number,
    ).first()
    metadata = ExportMetadata(
        project_number=project_number,
        job_name=meta.job_name or "" if meta else "",
        designer=meta.designer or "" if meta else "",
    )

    # 2. Load types (exclude CLADDING)
    lt_rows = (
        db.query(LoadTable)
        .filter(LoadTable.project_number == project_number, LoadTable.project_id == 0)
        .order_by(LoadTable.id)
        .all()
    )
    cladding_kpa = 0.0
    load_types: list[ExportLoadType] = []
    for r in lt_rows:
        if r.name == "CLADDING":
            cladding_kpa = float(r.dead_load_kpa) if r.dead_load_kpa else 0.0
            continue
        load_types.append(ExportLoadType(
            code=r.name,
            description=r.description or "",
            dead_kpa=float(r.dead_load_kpa) if r.dead_load_kpa else 0.0,
            live_kpa=float(r.live_load_kpa) if r.live_load_kpa else 0.0,
            llrf_type=r.llrf_type or "N",
        ))

    # 3. Rundown rows → levels + elements
    rows = get_rundown_rows(db, project_number)
    groups = group_by_element(rows)

    # Extract ordered levels from first element (all elements share same level set)
    levels: list[ExportLevelPair] = []
    seen_levels: set[str] = set()
    for r in rows:
        top = r.top_level or ""
        if top not in seen_levels:
            seen_levels.add(top)
            levels.append(ExportLevelPair(
                bot_level=r.bot_level or "",
                top_level=top,
                story_height_m=float(r.story_height_m or 0),
                concrete_mpa=float(r.concrete_mpa or 30),
            ))

    # 4. Transfer definitions — with source DL/LL/CUM AREA
    transfer_rows = get_transfers(db, project_number)
    # Build lookup: (source_mark, bot_level) → rundown row
    source_lookup: dict[tuple[str, str], Rundown] = {}
    if transfer_rows:
        source_marks = {t.source_element for t in transfer_rows}
        source_levels = {t.target_level for t in transfer_rows}
        for sr in db.query(Rundown).filter(
            Rundown.project_number == project_number,
            Rundown.element_mark.in_(source_marks),
            Rundown.bot_level.in_(source_levels),
        ).all():
            source_lookup[(sr.element_mark, sr.bot_level)] = sr

    transfers_by_target: dict[str, list[ExportTransfer]] = {}
    for tr in transfer_rows:
        pct = float(tr.percent)
        sr = source_lookup.get((tr.source_element, tr.target_level))
        et = ExportTransfer(
            source_element=tr.source_element,
            target_level=tr.target_level,
            percent=pct,
            dl_kn=round(float(sr.dl_cumulative_kn) * pct, 1) if sr and sr.dl_cumulative_kn else None,
            ll_kn=round(float(sr.ll_cumulative_kn) * pct, 1) if sr and sr.ll_cumulative_kn else None,
            cum_area_m2=round(float(sr.cum_area_m2) * pct, 2) if sr and sr.cum_area_m2 else None,
        )
        transfers_by_target.setdefault(tr.target_element, []).append(et)

    # 5. Build elements
    elements: list[ExportElement] = []
    for mark, floor_rows in groups.items():
        floors: list[ExportFloor] = []
        for r in floor_rows:
            floors.append(ExportFloor(
                bot_level=r.bot_level or "",
                top_level=r.top_level or "",
                story_height_m=float(r.story_height_m or 0),
                concrete_mpa=float(r.concrete_mpa or 30),
                dim_x_mm=float(r.dim_x_mm) if r.dim_x_mm is not None else None,
                dim_y=r.dim_y,
                cross_section_m2=float(r.cross_section_m2) if r.cross_section_m2 is not None else None,
                dl_cumulative_kn=float(r.dl_cumulative_kn or 0),
                ll_cumulative_kn=float(r.ll_cumulative_kn or 0),
                pw_kn=float(r.pw_kn or 0),
                pf_kn=float(r.pf_kn or 0),
                f_over_a_mpa=float(r.f_over_a_mpa) if r.f_over_a_mpa is not None else None,
                alpha=float(r.alpha_factor) if r.alpha_factor is not None else None,
                pct_steel=float(r.pct_steel) if r.pct_steel is not None else None,
                as_mm2=float(r.as_mm2) if r.as_mm2 is not None else None,
                bar_size=r.bar_size,
                qty=r.qty,
                n_bars=r.n_bars,
                c_bars=r.c_bars,
                rebar_design=r.rebar_design,
                area_this_floor_m2=float(r.area_this_floor_m2 or 0),
                transfer_area_m2=float(r.transfer_area_m2 or 0),
                cum_area_m2=float(r.cum_area_m2 or 0),
                beam_weight_kn=float(r.beam_weight_kn or 0),
                cladding_perimeter_m=float(r.cladding_perimeter_m or 0),
                area_by_type=parse_json_field(r.area_by_type_json),
                cum_area_by_type=parse_json_field(r.cum_area_by_type_json),
                llrf_by_type=parse_json_field(r.llrf_by_type_json),
                ll_non_reducible_by_type=parse_json_field(r.ll_non_reducible_by_type_json),
                dy_cumulative_kn=float(r.dy_cumulative_kn or 0),
            ))
        elements.append(ExportElement(
            mark=mark,
            element_type=floor_rows[0].element_type or "Column",
            floors=floors,
            transfers_received=transfers_by_target.get(mark, []),
            cladding_kpa=cladding_kpa,
        ))

    return ExportInput(
        metadata=metadata,
        load_types=load_types,
        levels=levels,
        elements=elements,
        template_path=template_path,
    )