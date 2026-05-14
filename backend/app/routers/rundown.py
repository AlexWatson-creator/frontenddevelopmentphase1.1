"""Rundown API router.

Spreadsheet upload path (primary):
  POST /api/projects/{number}/rundown/upload         — parse .xlsm → preview
  POST /api/projects/{number}/rundown/upload/confirm — compute + store to DB

Read endpoints:
  GET  /api/projects/{number}/rundown                — element summary list
  GET  /api/projects/{number}/rundown/{mark}         — single element full stack
  GET  /api/projects/{number}/rundown/validation     — area/transfer checks
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.dependencies import get_db
from app.models.design import Rundown
from app.models.management import ProjectMeta
from app.schemas.rundown import (
    AreaCheckRow,
    DataGapWarning,
    DiscrepancyItem,
    ElementDetailRead,
    ElementSummary,
    FloorResultRead,
    LoadTypeReplaceRequest,
    LoadTypeReplaceResponse,
    RecentRundownItem,
    RecentRundownList,
    RundownComputeResult,
    RundownListRead,
    RundownRowPatch,
    RundownRowUpdated,
    SpreadsheetUploadPreview,
    SummaryMatrixRead,
    TransferCheckRow,
    TransferDefRead,
    TransferReplaceRequest,
    TransferReplaceResponse,
    ValidationRead,
)
from app.services import rundown_service as svc

router = APIRouter(tags=["rundown"])


def _verify_project_meta(db: Session, number: str) -> None:
    """Raise 404 if project number has no rows in management.project_meta.

    Read endpoints use this to return 404 for genuinely unknown projects.
    Upload endpoints do NOT call this — they upsert project_meta as needed.
    """
    exists = db.query(ProjectMeta).filter(ProjectMeta.project_number == number).first()
    if exists is None:
        raise HTTPException(status_code=404, detail=f"Project '{number}' not found")


# ---------------------------------------------------------------------------
# POST /upload — parse .xlsm → preview (no DB write)
# ---------------------------------------------------------------------------

@router.post(
    "/projects/{number}/rundown/upload",
    response_model=SpreadsheetUploadPreview,
    summary="Parse rundown spreadsheet — preview only, no DB write",
)
async def upload_rundown_spreadsheet(
    number: str,
    file: UploadFile = File(...),
) -> SpreadsheetUploadPreview:
    """Upload a .xlsm rundown spreadsheet.

    Parses the file, runs engine recomputation, and returns a preview showing:
    - Element count, level count, load type count
    - Parse errors / warnings
    - Discrepancies between engine-computed values and Excel-stored values

    Does NOT write to the database. Call `/upload/confirm` to store results.
    Project need not exist yet — upload is the onboarding path.
    """
    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=422, detail="Uploaded file is empty")

    try:
        parse_result = svc.preview_spreadsheet(file_bytes)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to parse spreadsheet: {exc}") from exc

    discrepancies = [
        DiscrepancyItem(
            element_mark=d.element_mark,
            floor_index=d.floor_index,
            top_level=d.top_level,
            field_name=d.field_name,
            computed_value=d.computed_value,
            imported_value=d.imported_value,
            difference=d.difference,
        )
        for d in parse_result.discrepancies
    ]

    return SpreadsheetUploadPreview(
        project_number=parse_result.project_number or number,
        job_name=parse_result.job_name or "",
        designer=parse_result.designer or "",
        element_count=len(parse_result.elements),
        level_count=len(parse_result.levels),
        load_type_count=len(parse_result.load_types),
        errors=parse_result.errors,
        warnings=parse_result.warnings,
        discrepancy_count=len(discrepancies),
        discrepancies=discrepancies,
    )


# ---------------------------------------------------------------------------
# POST /upload/confirm — compute + store to DB
# ---------------------------------------------------------------------------

@router.post(
    "/projects/{number}/rundown/upload/confirm",
    response_model=RundownComputeResult,
    summary="Compute rundown from spreadsheet and store all results to DB",
)
async def confirm_rundown_upload(
    number: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> RundownComputeResult:
    """Re-parse the .xlsm file, compute all floor results, and store to DB.

    Replaces any existing rundown rows for this project number.
    Returns computation statistics and validation summary.
    Creates a project_meta entry if the project doesn't exist yet.
    """
    file_bytes = await file.read()
    if len(file_bytes) == 0:
        raise HTTPException(status_code=422, detail="Uploaded file is empty")

    try:
        parse_result = svc.parse_spreadsheet(file_bytes)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Failed to parse spreadsheet: {exc}") from exc

    if parse_result.errors:
        raise HTTPException(
            status_code=422,
            detail=f"Spreadsheet has {len(parse_result.errors)} parse error(s): "
                   + "; ".join(parse_result.errors[:3]),
        )

    if not parse_result.elements:
        raise HTTPException(status_code=422, detail="No elements found in spreadsheet")

    try:
        run_result, rows_written = svc.compute_and_store(db, number, parse_result)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Computation failed: {exc}") from exc

    v = run_result.validation
    return RundownComputeResult(
        project_number=number,
        rows_written=rows_written,
        element_count=len(run_result.elements),
        validation_is_valid=v.is_valid,
        validation_errors=v.errors,
        validation_warnings=v.warnings,
    )


# ---------------------------------------------------------------------------
# POST /cad-upload — parse DXF files + user config → compute + store
# ---------------------------------------------------------------------------

@router.post(
    "/projects/{number}/rundown/cad-upload",
    response_model=RundownComputeResult,
    summary="Upload DXF files with level/load type config, compute and store rundown",
)
async def upload_cad_rundown(
    number: str,
    files: list[UploadFile] = File(...),
    file_level_map: str = Form(...),
    level_pairs: str = Form(...),
    load_types: str = Form(...),
    cladding_kpa: float = Form(0.0),
    db: Session = Depends(get_db),
) -> RundownComputeResult:
    """Upload DXF files with user-provided level pairs, file-level mapping,
    and load type definitions. Parses all DXFs, builds RundownInput,
    computes full rundown, and stores results to DB.

    Form fields (JSON strings):
      - file_level_map: [{filename, bot_level, top_level}]
      - level_pairs: [{bot, top, height_m, concrete_mpa}]
      - load_types: [{code, description, dead_kpa, live_kpa, llrf_type}]
      - cladding_kpa: default cladding kPa (float)
    """
    # Parse JSON form fields
    try:
        flm = json.loads(file_level_map)
        lps = json.loads(level_pairs)
        lts = json.loads(load_types)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid JSON in form field: {exc}") from exc

    if not files:
        raise HTTPException(status_code=422, detail="No DXF files uploaded")
    if not lps:
        raise HTTPException(status_code=422, detail="Level pairs are required")
    if not lts:
        raise HTTPException(status_code=422, detail="Load types are required")

    # Read file bytes keyed by filename
    dxf_files: dict[str, bytes] = {}
    for f in files:
        content = await f.read()
        if len(content) == 0:
            continue
        dxf_files[f.filename or f"file_{len(dxf_files)}"] = content

    if not dxf_files:
        raise HTTPException(status_code=422, detail="All uploaded files are empty")

    try:
        run_result, rows_written = svc.compute_and_store_cad(
            db=db,
            project_number=number,
            dxf_files=dxf_files,
            file_level_map=flm,
            level_pairs=lps,
            load_types=lts,
            cladding_kpa=cladding_kpa,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"CAD computation failed: {exc}") from exc

    v = run_result.validation
    return RundownComputeResult(
        project_number=number,
        rows_written=rows_written,
        element_count=len(run_result.elements),
        validation_is_valid=v.is_valid,
        validation_errors=v.errors,
        validation_warnings=v.warnings,
    )


# ---------------------------------------------------------------------------
# GET /rundown/recent — list projects that have rundown data
# ---------------------------------------------------------------------------

@router.get(
    "/rundown/recent",
    response_model=RecentRundownList,
    summary="List projects with computed rundown data",
)
def list_recent_rundowns(
    db: Session = Depends(get_db),
) -> RecentRundownList:
    """Return a summary of projects that have rundown results, most recent first."""
    from sqlalchemy import func

    from app.models.design import Rundown

    rows = (
        db.query(
            Rundown.project_number,
            func.count(func.distinct(Rundown.element_mark)).label("element_count"),
            func.max(Rundown.data_source).label("data_source"),
            func.max(Rundown.computed_at).label("computed_at"),
        )
        .group_by(Rundown.project_number)
        .order_by(func.max(Rundown.computed_at).desc())
        .all()
    )

    items = [
        RecentRundownItem(
            project_number=r.project_number,
            element_count=r.element_count,
            data_source=r.data_source,
            computed_at=r.computed_at,
        )
        for r in rows
    ]
    return RecentRundownList(items=items)


# ---------------------------------------------------------------------------
# DELETE /rundown/{number} — delete all rundown data for a project
# ---------------------------------------------------------------------------

@router.delete(
    "/projects/{number}/rundown",
    status_code=204,
    summary="Delete all rundown data for a project",
)
def delete_rundown(
    number: str,
    db: Session = Depends(get_db),
) -> None:
    """Delete rundown-specific data for a project.

    Removes: design.rundown rows, design.rundown_transfers, and
    rundown-uploaded load_tables (project_id=0).
    Does NOT delete project_meta (shared by 14 FK references) or
    identity tables (shared with Revit).
    """
    from app.models.design import LoadTable, RundownTransfer

    # 1. Delete rundown rows
    db.query(Rundown).filter(Rundown.project_number == number).delete(
        synchronize_session=False
    )

    # 2. Delete transfer definitions
    db.query(RundownTransfer).filter(RundownTransfer.project_number == number).delete(
        synchronize_session=False
    )

    # 3. Delete load_tables (rundown-uploaded, project_id=0)
    db.query(LoadTable).filter(
        LoadTable.project_number == number,
        LoadTable.project_id == 0,
    ).delete(synchronize_session=False)

    db.commit()


# ---------------------------------------------------------------------------
# GET /rundown/load-types — load types for rundown project
# ---------------------------------------------------------------------------

@router.get(
    "/projects/{number}/rundown/load-types",
    summary="Get load types stored for a rundown project",
)
def get_rundown_load_types(
    number: str,
    db: Session = Depends(get_db),
) -> list[dict]:
    """Return load types from design.load_tables for this project (project_id=0)."""
    from app.models.design import LoadTable

    rows = (
        db.query(LoadTable)
        .filter(LoadTable.project_number == number, LoadTable.project_id == 0)
        .order_by(LoadTable.id)
        .all()
    )
    return [
        {
            "id": r.id,
            "code": r.name,
            "description": r.description,
            "dead_kpa": float(r.dead_load_kpa) if r.dead_load_kpa is not None else None,
            "live_kpa": float(r.live_load_kpa) if r.live_load_kpa is not None else None,
            "llrf_type": r.llrf_type,
        }
        for r in rows
    ]


# ---------------------------------------------------------------------------
# POST /rundown/load-types — replace load types for a rundown project
# ---------------------------------------------------------------------------

@router.post(
    "/projects/{number}/rundown/load-types",
    response_model=LoadTypeReplaceResponse,
    summary="Replace all load types for a rundown project",
)
def replace_rundown_load_types(
    number: str,
    body: LoadTypeReplaceRequest,
    db: Session = Depends(get_db),
) -> LoadTypeReplaceResponse:
    """Replace rundown load types (project_id=0) with user-provided entries.

    Deletes existing rundown load types and inserts the new set.
    Does not affect Revit-path load tables (project_id != 0).
    """
    _verify_project_meta(db, number)
    count = svc.replace_load_tables(
        db, number, [e.model_dump() for e in body.entries]
    )
    return LoadTypeReplaceResponse(count=count)


# ---------------------------------------------------------------------------
# GET /rundown — element summary list
# ---------------------------------------------------------------------------

@router.get(
    "/projects/{number}/rundown",
    response_model=RundownListRead,
    summary="List all rundown elements for a project",
)
def list_rundown(
    number: str,
    db: Session = Depends(get_db),
) -> RundownListRead:
    """Return a summary of all elements computed for this project.

    Each element shows floor count and cumulative DL/LL/PF at the lowest floor.
    """
    _verify_project_meta(db, number)

    rows = svc.get_rundown_rows(db, number)
    groups = svc.group_by_element(rows)

    summaries: list[ElementSummary] = []
    for mark, floors in groups.items():
        lowest = floors[-1]  # floor_order is ascending; last = footing level
        summaries.append(
            ElementSummary(
                mark=mark,
                element_type=lowest.element_type or "",
                floor_count=len(floors),
                dl_cumulative_kn=float(lowest.dl_cumulative_kn) if lowest.dl_cumulative_kn is not None else None,
                ll_cumulative_kn=float(lowest.ll_cumulative_kn) if lowest.ll_cumulative_kn is not None else None,
                pf_kn=float(lowest.pf_kn) if lowest.pf_kn is not None else None,
                cross_section_m2=float(lowest.cross_section_m2) if lowest.cross_section_m2 is not None else None,
                data_source=lowest.data_source,
            )
        )

    computed_at = rows[0].computed_at if rows else None
    data_source = rows[0].data_source if rows else None

    # Count load types for this project
    from app.models.design import LoadTable
    lt_count = db.query(LoadTable).filter(LoadTable.project_number == number).count()

    # Fetch project metadata for job_name/designer
    meta = db.query(ProjectMeta).filter(ProjectMeta.project_number == number).first()

    return RundownListRead(
        project_number=number,
        element_count=len(summaries),
        load_type_count=lt_count,
        data_source=data_source,
        computed_at=computed_at,
        job_name=meta.job_name if meta else None,
        designer=meta.designer if meta else None,
        elements=summaries,
    )


# ---------------------------------------------------------------------------
# GET /rundown/validation — validation summary
# IMPORTANT: must be registered BEFORE /{mark} to avoid "validation" matching mark
# ---------------------------------------------------------------------------

@router.get(
    "/projects/{number}/rundown/validation",
    response_model=ValidationRead,
    summary="Get area balance and transfer validation results",
)
def get_validation(
    number: str,
    db: Session = Depends(get_db),
) -> ValidationRead:
    """Re-run validation on stored rundown results.

    Returns area balance checks, transfer checks, data gap warnings, and errors.
    An empty result (no rows) returns is_valid=False with an error message.
    """
    _verify_project_meta(db, number)

    rows = svc.get_rundown_rows(db, number)
    if not rows:
        return ValidationRead(
            project_number=number,
            is_valid=False,
            area_checks=[],
            transfer_checks=[],
            data_gaps=[],
            errors=["No rundown results found. Upload and confirm a spreadsheet first."],
            warnings=[],
        )

    # Rebuild RundownResult from DB rows and re-run validation
    from rundown_engine.dtypes.inputs import RundownInput
    from rundown_engine.validate import validate_rundown

    groups = svc.group_by_element(rows)

    # Reconstruct minimal RundownResult from DB rows for validation
    from rundown_engine.dtypes.outputs import ElementResult, FloorResult, RundownResult

    elem_results: list[ElementResult] = []
    for mark, floor_rows in groups.items():
        floor_results: list[FloorResult] = []
        for row in floor_rows:
            jr = svc.parse_json_field
            fr = FloorResult(
                bot_level=row.bot_level or str(row.floor_order),
                top_level=row.top_level or str((row.floor_order or 0) + 1),
                story_height_m=float(row.story_height_m or 0),
                concrete_mpa=float(row.concrete_mpa or 30),
                dim_x_mm=float(row.dim_x_mm) if row.dim_x_mm is not None else None,
                dim_y=row.dim_y,
                cross_section_m2=float(row.cross_section_m2) if row.cross_section_m2 is not None else None,
                area_by_type=jr(row.area_by_type_json),
                cum_area_by_type=jr(row.cum_area_by_type_json),
                area_this_floor_m2=float(row.area_this_floor_m2 or 0),
                transfer_area_m2=float(row.transfer_area_m2 or 0),
                cum_area_m2=float(row.cum_area_m2 or 0),
                dl_from_above_kn=float(row.dl_from_above_kn or 0),
                dl_floor_load_kn=float(row.dl_floor_load_kn or 0),
                dl_transfer_kn=float(row.dl_transfer_kn or 0),
                dl_self_weight_kn=float(row.dl_self_weight_kn or 0),
                dl_cladding_kn=float(row.dl_cladding_kn or 0),
                dl_beam_weight_kn=float(row.dl_beam_weight_kn or 0),
                dl_cumulative_kn=float(row.dl_cumulative_kn or 0),
                llrf_by_type=jr(row.llrf_by_type_json),
                ll_reducible_kn=float(row.ll_reducible_kn or 0),
                ll_non_reducible_by_type=jr(row.ll_non_reducible_by_type_json),
                ll_non_reducible_this_floor_kn=float(row.ll_non_reducible_this_floor_kn or 0),
                ll_transfer_kn=float(row.ll_transfer_kn or 0),
                dy_cumulative_kn=float(row.dy_cumulative_kn or 0),
                ll_cumulative_kn=float(row.ll_cumulative_kn or 0),
                pw_kn=float(row.pw_kn or 0),
                pf_kn=float(row.pf_kn or 0),
                f_over_a_mpa=float(row.f_over_a_mpa) if row.f_over_a_mpa is not None else None,
                alpha=float(row.alpha_factor) if row.alpha_factor is not None else None,
                phi=float(row.phi) if row.phi is not None else None,
                pct_steel=float(row.pct_steel) if row.pct_steel is not None else None,
                as_mm2=float(row.as_mm2) if row.as_mm2 is not None else None,
                bar_size=row.bar_size,
                qty=row.qty,
                n_bars=row.n_bars,
                c_bars=row.c_bars,
                rebar_design=row.rebar_design,
                beam_weight_kn=float(row.beam_weight_kn or 0),
                cladding_perimeter_m=float(row.cladding_perimeter_m or 0),
            )
            floor_results.append(fr)
        elem_results.append(
            ElementResult(
                mark=mark,
                element_type=floor_rows[0].element_type or "",
                floors=floor_results,
                cladding_kpa=0.0,
                transfers_received=[],
            )
        )

    from rundown_engine.dtypes.validation import ValidationResult
    run_result = RundownResult(
        project_number=number,
        elements=elem_results,
        validation=ValidationResult(
            area_checks=[], transfer_checks=[], data_gaps=[],
            errors=[], warnings=[], is_valid=True,
        ),
    )

    # Build minimal RundownInput for validate_rundown (transfers not stored yet)
    input_data = RundownInput(
        project_number=number,
        load_types=[],
        elements=[],
    )
    v = validate_rundown(input_data, run_result)

    return ValidationRead(
        project_number=number,
        is_valid=v.is_valid,
        area_checks=[
            AreaCheckRow(
                bot_level=ac.bot_level,
                top_level=ac.top_level,
                total_area_m2=ac.total_area_m2,
                cum_area_m2=ac.cum_area_m2,
                area_difference_m2=ac.area_difference_m2,
                is_balanced=ac.is_balanced,
            )
            for ac in v.area_checks
        ],
        transfer_checks=[
            TransferCheckRow(
                element_mark=tc.element_mark,
                pct_transferred=tc.pct_transferred,
                to_elements=tc.to_elements,
                all_within_range=tc.all_within_range,
                status=tc.status,
            )
            for tc in v.transfer_checks
        ],
        data_gaps=[
            DataGapWarning(element_mark=dg.element_mark, message=dg.message)
            for dg in v.data_gaps
        ],
        errors=v.errors,
        warnings=v.warnings,
    )


# ---------------------------------------------------------------------------
# GET /rundown/summary — cross-element pivot matrix
# IMPORTANT: registered BEFORE /{mark} so "summary" isn't captured as mark
# ---------------------------------------------------------------------------

@router.get(
    "/projects/{number}/rundown/summary",
    response_model=SummaryMatrixRead,
    summary="Cross-element summary matrix (levels × elements, selectable metric)",
)
def get_summary(
    number: str,
    metric: str = "PF",
    db: Session = Depends(get_db),
) -> SummaryMatrixRead:
    """Return a pivot table: levels on columns, elements on rows.

    Valid metrics: DL, LL, PW, PF, F / A, % Steel, As, AREA, XFER AREA, CUM AREA.
    """
    _verify_project_meta(db, number)

    try:
        data = svc.get_summary_matrix(db, number, metric)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return SummaryMatrixRead(**data)


# ---------------------------------------------------------------------------
# PATCH /rundown/rows/{row_id} — edit rebar fields on a single row
# ---------------------------------------------------------------------------

@router.patch(
    "/projects/{number}/rundown/rows/{row_id}",
    response_model=RundownRowUpdated,
    summary="Edit rebar fields on a single rundown row",
)
def patch_rundown_row(
    number: str,
    row_id: int,
    body: RundownRowPatch,
    db: Session = Depends(get_db),
) -> RundownRowUpdated:
    """Update bar_size, qty, n_bars, c_bars with engine recomputation.

    Override flags control which values are user-set vs auto-computed.
    Returns the updated rebar fields after recomputation.
    """
    _verify_project_meta(db, number)

    try:
        row = svc.update_rebar(db, number, row_id, body.model_dump(exclude_none=False))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    return RundownRowUpdated(
        id=row.id,
        bar_size=row.bar_size,
        qty=row.qty,
        n_bars=row.n_bars,
        c_bars=row.c_bars,
        rebar_design=row.rebar_design,
        as_mm2=float(row.as_mm2) if row.as_mm2 is not None else None,
        qty_override=bool(row.qty_override),
        n_bars_override=bool(row.n_bars_override),
        c_bars_override=bool(row.c_bars_override),
    )


# ---------------------------------------------------------------------------
# Transfer management — CRUD + recompute
# IMPORTANT: registered BEFORE /{mark} catch-all
# ---------------------------------------------------------------------------

@router.get(
    "/projects/{number}/rundown/transfers",
    response_model=list[TransferDefRead],
    summary="Get all transfer definitions for a project",
)
def list_transfers(
    number: str,
    db: Session = Depends(get_db),
) -> list[TransferDefRead]:
    """Return all transfer definitions (source → target at level, percent)."""
    _verify_project_meta(db, number)
    rows = svc.get_transfers(db, number)
    return [
        TransferDefRead(
            id=r.id, target_element=r.target_element,
            source_element=r.source_element, target_level=r.target_level,
            percent=float(r.percent), created_by=r.created_by,
        )
        for r in rows
    ]


@router.get(
    "/projects/{number}/rundown/transfers/{mark}",
    response_model=list[TransferDefRead],
    summary="Get transfer definitions for one element",
)
def get_element_transfers(
    number: str,
    mark: str,
    db: Session = Depends(get_db),
) -> list[TransferDefRead]:
    """Return transfer definitions received by one element, with source DL/LL/CUM AREA."""
    _verify_project_meta(db, number)
    rows = svc.get_transfers(db, number, mark)

    # Build lookup: (source_mark, bot_level) → rundown row for computed values
    # Transfer "at level 8" means bot_level=8 (the last active floor of the source)
    source_marks = {r.source_element for r in rows}
    source_levels = {r.target_level for r in rows}
    source_rows = (
        db.query(Rundown)
        .filter(
            Rundown.project_number == number,
            Rundown.element_mark.in_(source_marks),
            Rundown.bot_level.in_(source_levels),
        )
        .all()
    ) if source_marks else []
    lookup = {(sr.element_mark, sr.bot_level): sr for sr in source_rows}

    result = []
    for r in rows:
        sr = lookup.get((r.source_element, r.target_level))
        pct = float(r.percent)
        result.append(TransferDefRead(
            id=r.id, target_element=r.target_element,
            source_element=r.source_element, target_level=r.target_level,
            percent=pct, created_by=r.created_by,
            dl_kn=round(float(sr.dl_cumulative_kn) * pct, 1) if sr and sr.dl_cumulative_kn else None,
            ll_kn=round(float(sr.ll_cumulative_kn) * pct, 1) if sr and sr.ll_cumulative_kn else None,
            cum_area_m2=round(float(sr.cum_area_m2) * pct, 2) if sr and sr.cum_area_m2 else None,
        ))
    return result


@router.put(
    "/projects/{number}/rundown/transfers/{mark}",
    response_model=TransferReplaceResponse,
    summary="Replace all transfers for one element",
)
def replace_element_transfers(
    number: str,
    mark: str,
    body: TransferReplaceRequest,
    db: Session = Depends(get_db),
) -> TransferReplaceResponse:
    """Replace transfer definitions for one element. Does NOT recompute."""
    _verify_project_meta(db, number)
    count = svc.replace_transfers(db, number, mark, [t.model_dump() for t in body.transfers])
    return TransferReplaceResponse(count=count, target_element=mark)


@router.post(
    "/projects/{number}/rundown/recompute",
    response_model=RundownComputeResult,
    summary="Recompute entire project from stored data + transfer definitions",
)
def recompute_rundown(
    number: str,
    db: Session = Depends(get_db),
) -> RundownComputeResult:
    """Re-run the engine on stored floor data with current transfer definitions."""
    _verify_project_meta(db, number)
    try:
        run_result, rows_written = svc.recompute_project(db, number)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Recomputation failed: {exc}") from exc

    v = run_result.validation
    return RundownComputeResult(
        project_number=number,
        rows_written=rows_written,
        element_count=len(run_result.elements),
        validation_is_valid=v.is_valid,
        validation_errors=v.errors,
        validation_warnings=v.warnings,
    )


# ---------------------------------------------------------------------------
# GET /rundown/export — download .xlsm spreadsheet
# ---------------------------------------------------------------------------

@router.get(
    "/projects/{number}/rundown/export",
    summary="Export rundown data pack for VBA import",
)
def export_rundown_data_pack(
    number: str,
    db: Session = Depends(get_db),
):
    """Generate a data pack .xlsx for VBA ImportFromPlatform macro."""
    import io

    from fastapi.responses import StreamingResponse

    from rundown_engine.writers import generate_xlsx

    _verify_project_meta(db, number)

    rows = svc.get_rundown_rows(db, number)
    if not rows:
        raise HTTPException(status_code=404, detail="No rundown data to export")

    export_input = svc.build_export_input(db, number, template_path="")
    xlsx_bytes = generate_xlsx(export_input)

    filename = f"{number}_Rundown_Data.xlsx"
    return StreamingResponse(
        io.BytesIO(xlsx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# GET /rundown/{mark} — single element full stack
# IMPORTANT: registered AFTER /validation so "validation" isn't captured as mark
# ---------------------------------------------------------------------------

@router.get(
    "/projects/{number}/rundown/{mark}",
    response_model=ElementDetailRead,
    summary="Get full floor-by-floor detail for one element",
)
def get_element_detail(
    number: str,
    mark: str,
    db: Session = Depends(get_db),
) -> ElementDetailRead:
    """Return complete floor-by-floor FloorResult data for one element.

    Every intermediate value (DL breakdown, LL breakdown, areas, rebar) is included.
    """
    _verify_project_meta(db, number)

    rows = svc.get_element_rows(db, number, mark)
    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"Element '{mark}' not found in project '{number}' rundown",
        )

    floors = [FloorResultRead(**svc.floor_row_to_schema_dict(r)) for r in rows]
    return ElementDetailRead(
        mark=mark,
        element_type=rows[0].element_type or "",
        floor_count=len(floors),
        floors=floors,
    )
