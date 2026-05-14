"""SQLAlchemy ORM models for the design schema (READ-WRITE).

ARCHITECTURE:
  management.project_meta is the relationship hub.
  All design tables have:
    project_number  VARCHAR(50)  FK → management.project_meta(project_number)
    project_id      INT          loose ref to dbo.Project(Id), NO FK
    level_id        INT          loose ref to dbo.Levels(id), NO FK
  ZERO foreign keys to dbo. Design data survives Clarity wipe-reload.
  Only intra-design FKs (e.g., load_table_id → design.load_tables).

Element references use element_guid (Revit UniqueId), NEVER ElementId.

Phase 2 identity hub tables (level_identity, element_identity, rundown_uploads)
are scoped to project_number only (no file-level project_id).
"""
from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Unicode,
    UnicodeText,
    text,
)
from sqlalchemy.dialects.mssql import BIT, DATETIME2, UNIQUEIDENTIFIER
from geoalchemy2 import Geometry

from app.models.dbo import Base


# ---------------------------------------------------------------------------
# Load Tables
# ---------------------------------------------------------------------------

class LoadTable(Base):
    __tablename__ = "load_tables"
    __table_args__ = {"schema": "design"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_number = Column(String(50), ForeignKey("management.project_meta.project_number"), nullable=False)
    project_id = Column(Integer, nullable=False)                # dbo.Project(Id), NO FK
    name = Column(String(20), nullable=False)
    description = Column(String(100))
    dead_load_kpa = Column(Numeric(10, 4))
    live_load_kpa = Column(Numeric(10, 4))
    llrf_type = Column(String(10), nullable=False, server_default="N")
    created_by = Column(String(100), nullable=False)
    created_at = Column(DATETIME2, nullable=False, server_default="getutcdate()")
    updated_at = Column(DATETIME2, nullable=False, server_default="getutcdate()")


# ---------------------------------------------------------------------------
# Load Areas
# ---------------------------------------------------------------------------

class LoadArea(Base):
    __tablename__ = "load_areas"
    __table_args__ = {"schema": "design"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_number = Column(String(50), ForeignKey("management.project_meta.project_number"), nullable=False)
    project_id = Column(Integer, nullable=False)                # dbo.Project(Id), NO FK
    level_id = Column(Integer, nullable=False)                  # dbo.Levels(id), NO FK
    load_table_id = Column(Integer, ForeignKey("design.load_tables.id"), nullable=False)
    polygon_wkt = Column(Geometry(geometry_type="GEOMETRY", srid=0), nullable=False)
    source = Column(String(20), nullable=False, server_default="web_draw")
    created_by = Column(String(100), nullable=False)
    created_at = Column(DATETIME2, nullable=False, server_default="getutcdate()")
    updated_at = Column(DATETIME2, nullable=False, server_default="getutcdate()")
    version = Column(Integer, nullable=False, server_default="1")


# ---------------------------------------------------------------------------
# Tributary Results
# ---------------------------------------------------------------------------

class TributaryResult(Base):
    __tablename__ = "tributary_results"
    __table_args__ = {"schema": "design"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_number = Column(String(50), ForeignKey("management.project_meta.project_number"), nullable=False)
    element_guid = Column(String(50), nullable=False)
    element_type = Column(String(10), nullable=False)
    project_id = Column(Integer, nullable=False)                # dbo.Project(Id), NO FK
    level_id = Column(Integer, nullable=False)                  # dbo.Levels(id), NO FK
    load_table_id = Column(Integer, ForeignKey("design.load_tables.id"), nullable=False)
    tributary_polygon = Column(Geometry(geometry_type="GEOMETRY", srid=0))
    tributary_area_m2 = Column(Numeric(12, 4), nullable=False)
    beam_weights_detail = Column(String(500), nullable=True)
    # Comma-separated individual beam kN contributions, e.g. "80.5,49.8".
    # Total beam weight = sum of parsed floats. One BM= line per value in download.
    computed_at = Column(DATETIME2, nullable=False, server_default="getutcdate()")
    input_hash = Column(String(64))


# ---------------------------------------------------------------------------
# Load Assignments
# ---------------------------------------------------------------------------

class LoadAssignment(Base):
    __tablename__ = "load_assignments"
    __table_args__ = {"schema": "design"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_number = Column(String(50), ForeignKey("management.project_meta.project_number"), nullable=False)
    element_guid = Column(String(50), nullable=False)
    element_type = Column(String(10), nullable=False)
    project_id = Column(Integer, nullable=False)                # dbo.Project(Id), NO FK
    level_id = Column(Integer, nullable=False)                  # dbo.Levels(id), NO FK
    load_table_id = Column(Integer, ForeignKey("design.load_tables.id"), nullable=False)
    tributary_area_m2 = Column(Numeric(12, 4), nullable=False)
    dead_load_kn = Column(Numeric(12, 4), nullable=False)
    live_load_kn = Column(Numeric(12, 4), nullable=False)
    live_load_reduced_kn = Column(Numeric(12, 4))
    llrf_factor = Column(Numeric(6, 4))
    cumulative_supported_floors = Column(Integer)
    computed_at = Column(DATETIME2, nullable=False, server_default="getutcdate()")


# ---------------------------------------------------------------------------
# Element Marks
# ---------------------------------------------------------------------------

class ElementMark(Base):
    __tablename__ = "element_marks"
    __table_args__ = {"schema": "design"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_number = Column(String(50), ForeignKey("management.project_meta.project_number"), nullable=False)
    element_guid = Column(String(50), nullable=False)
    element_type = Column(String(10), nullable=False)
    project_id = Column(Integer, nullable=False)                # dbo.Project(Id), NO FK
    raw_mark = Column(String(255), nullable=False)
    prefix = Column(String(50))
    type_char = Column(String(1), nullable=False)
    element_number = Column(String(50), nullable=False)
    suffix = Column(String(50))
    comments = Column(String(100))
    parsed_successfully = Column(BIT, nullable=False, server_default="0")
    level_id = Column(Integer, nullable=False)                  # dbo.Levels(id), NO FK
    parsed_at = Column(DATETIME2, nullable=False, server_default="getutcdate()")


# ---------------------------------------------------------------------------
# Element Links
# ---------------------------------------------------------------------------

class ElementLink(Base):
    __tablename__ = "element_links"
    __table_args__ = {"schema": "design"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_number = Column(String(50), ForeignKey("management.project_meta.project_number"), nullable=False)
    project_id = Column(Integer, nullable=False)                # dbo.Project(Id), NO FK
    upper_element_guid = Column(String(50), nullable=False)
    upper_element_type = Column(String(10), nullable=False)
    upper_level_id = Column(Integer, nullable=False)            # dbo.Levels(id), NO FK
    lower_element_guid = Column(String(50), nullable=False)
    lower_element_type = Column(String(10), nullable=False)
    lower_level_id = Column(Integer, nullable=False)            # dbo.Levels(id), NO FK
    link_type = Column(String(20), nullable=False, server_default="Direct")
    transfer_ratio = Column(Numeric(6, 4), nullable=False, server_default="1.0")
    confidence = Column(String(10), nullable=False, server_default="Medium")
    match_method = Column(String(20), nullable=False)
    created_at = Column(DATETIME2, nullable=False, server_default="getutcdate()")
    updated_at = Column(DATETIME2, nullable=False, server_default="getutcdate()")


# ---------------------------------------------------------------------------
# Rundown
# ---------------------------------------------------------------------------

class Rundown(Base):
    """One row per floor per element — full FloorResult transparency.

    Every field in the rundown engine FloorResult dataclass is stored here.
    Legacy aggregate columns are retained for backward compatibility;
    new code writes to BOTH the legacy columns AND the breakdown columns.

    Column references (comments) map to Excel spreadsheet columns A-DY.
    """

    __tablename__ = "rundown"
    __table_args__ = {"schema": "design"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_number = Column(String(50), ForeignKey("management.project_meta.project_number"), nullable=False)
    element_guid = Column(String(50), nullable=False)           # Revit UniqueId or spreadsheet mark
    element_type = Column(String(10), nullable=False)           # "Column" / "Wall"
    project_id = Column(Integer, nullable=False)                # dbo.Project(Id), NO FK
    level_id = Column(Integer, nullable=False)                  # dbo.Levels(id), NO FK
    load_table_id = Column(Integer, nullable=True)              # design.load_tables(id), NULL for spreadsheet path

    # Legacy aggregate columns — kept for backward compatibility
    floor_dead_kn = Column(Numeric(12, 4), nullable=False, server_default="0")
    floor_live_kn = Column(Numeric(12, 4), nullable=False, server_default="0")
    floor_live_reduced_kn = Column(Numeric(12, 4), nullable=False, server_default="0")
    cumulative_dead_kn = Column(Numeric(12, 4), nullable=False, server_default="0")   # = dl_cumulative_kn
    cumulative_live_kn = Column(Numeric(12, 4), nullable=False, server_default="0")   # = ll_cumulative_kn
    cumulative_live_reduced_kn = Column(Numeric(12, 4), nullable=False, server_default="0")
    rundown_version = Column(Integer, nullable=False, server_default="1")
    computed_at = Column(DATETIME2, nullable=False, server_default="getutcdate()")

    # ---------------------------------------------------------------------------
    # Identity hub FKs + floor metadata
    # ---------------------------------------------------------------------------
    element_identity_id = Column(Integer, ForeignKey("design.element_identity.id"), nullable=True)
    level_identity_id   = Column(Integer, ForeignKey("design.level_identity.id"),   nullable=True)
    floor_order         = Column(Integer, nullable=True)        # 0 = roof, increases toward footing
    element_mark        = Column(String(100), nullable=True)    # spreadsheet mark / CAD name / Revit mark
    bot_level           = Column(String(50),  nullable=True)    # FloorResult.bot_level (BOT LEVEL name)
    top_level           = Column(String(50),  nullable=True)    # FloorResult.top_level (TOP LEVEL name)

    # ---------------------------------------------------------------------------
    # Geometry at this floor (FloorResult cols D, E, X, Y, Z)
    # ---------------------------------------------------------------------------
    story_height_m   = Column(Numeric(8, 4),  nullable=True)   # col D: HT above (m)
    concrete_mpa     = Column(Numeric(6, 2),  nullable=True)   # col E: Conc. Str. (MPa)
    dim_x_mm         = Column(Numeric(10, 2), nullable=True)   # col X: dimension 1 (mm)
    dim_y            = Column(String(10),     nullable=True)   # col Y: depth mm or "D"/"S"/"W"
    cross_section_m2 = Column(Numeric(10, 6), nullable=True)   # col Z: element cross-section (m²)

    # ---------------------------------------------------------------------------
    # Dead Load breakdown — 6 terms + cumulative (col F group)
    #   dl_from_above + dl_floor_load + dl_transfer + dl_self_weight
    #   + dl_cladding + dl_beam_weight = dl_cumulative_kn
    # ---------------------------------------------------------------------------
    dl_from_above_kn   = Column(Numeric(12, 4), nullable=True)  # F[N-1]: DL from floor above
    dl_floor_load_kn   = Column(Numeric(12, 4), nullable=True)  # SUMPRODUCT(DL_kPa × area_by_type)
    dl_transfer_kn     = Column(Numeric(12, 4), nullable=True)  # DL received from transfer elements
    dl_self_weight_kn  = Column(Numeric(12, 4), nullable=True)  # Z × story_height × 24 kN/m³
    dl_cladding_kn     = Column(Numeric(12, 4), nullable=True)  # cladding_kPa × perimeter × height_above
    dl_beam_weight_kn  = Column(Numeric(12, 4), nullable=True)  # col V: beam weight
    dl_cumulative_kn   = Column(Numeric(12, 4), nullable=True)  # col F: sum of all 6 terms

    # ---------------------------------------------------------------------------
    # Live Load breakdown — 2-path system + cumulative (col G group)
    # ---------------------------------------------------------------------------
    ll_reducible_kn                = Column(Numeric(12, 4), nullable=True)  # SUMPRODUCT(BA:BY × LL_kPa × LLRF)
    ll_non_reducible_this_floor_kn = Column(Numeric(12, 4), nullable=True)  # SUM(CZ:DX) this floor
    ll_transfer_kn                 = Column(Numeric(12, 4), nullable=True)  # LL from transfers (→ DY)
    dy_cumulative_kn               = Column(Numeric(12, 4), nullable=True)  # col DY: non-reducible LL
    ll_cumulative_kn               = Column(Numeric(12, 4), nullable=True)  # col G: ll_reducible + DY

    # ---------------------------------------------------------------------------
    # Areas — cols S, T, U
    # ---------------------------------------------------------------------------
    area_this_floor_m2 = Column(Numeric(12, 4), nullable=True)  # col S: SUM(AA:AY)
    transfer_area_m2   = Column(Numeric(12, 4), nullable=True)  # col T: SUMIF transfer CUM_AREA
    cum_area_m2        = Column(Numeric(12, 4), nullable=True)  # col U: cumulative area

    # ---------------------------------------------------------------------------
    # Derived loads + design capacity (cols H, I, J, K, L)
    # ---------------------------------------------------------------------------
    pw_kn        = Column(Numeric(12, 4), nullable=True)        # col H: DL + LL (service load)
    pf_kn        = Column(Numeric(12, 4), nullable=True)        # col I: MAX(1.25DL+1.5LL, 1.4DL)
    f_over_a_mpa = Column(Numeric(10, 4), nullable=True)        # col J: PF/1000/Z
    alpha_factor = Column(Numeric(6, 4),  nullable=True)        # col K: MAX(0.85-0.0015f'c, 0.67)
    phi          = Column(Numeric(6, 4),  nullable=True)        # capacity reduction (shape-based)
    pct_steel    = Column(Numeric(8, 6),  nullable=True)        # col L: reinforcement ratio

    # ---------------------------------------------------------------------------
    # Input data carried through (cols V, W)
    # ---------------------------------------------------------------------------
    beam_weight_kn     = Column(Numeric(10, 4), nullable=True)  # col V: B-WT (kN)
    cladding_perimeter_m = Column(Numeric(10, 4), nullable=True) # col W: C-WALL (m)

    # ---------------------------------------------------------------------------
    # Rebar design — user-editable cols M-R
    # ---------------------------------------------------------------------------
    as_mm2       = Column(Numeric(10, 2), nullable=True)        # col M: area of steel (mm²)
    bar_size     = Column(String(10),     nullable=True)        # col N: rebar designation ("20M")
    qty          = Column(Integer,        nullable=True)        # col O: quantity
    n_bars       = Column(Integer,        nullable=True)        # col P: Nbars — normal laps
    c_bars       = Column(Integer,        nullable=True)        # col Q: Cbars — couplers
    rebar_design = Column(Unicode(30),     nullable=True)        # col R: rebar string ("8-20M, 4-20M●")

    # Override tracking (BIT) — True = user manually set, False = engine auto-computed
    qty_override     = Column(Boolean, nullable=False, server_default="0")
    n_bars_override  = Column(Boolean, nullable=False, server_default="0")
    c_bars_override  = Column(Boolean, nullable=False, server_default="0")

    # ---------------------------------------------------------------------------
    # Per-type JSON breakdowns (NVARCHAR(MAX) — up to 25 load type codes)
    # ---------------------------------------------------------------------------
    area_by_type_json             = Column(UnicodeText, nullable=True)  # {code: area_m2}  AA:AY
    cum_area_by_type_json         = Column(UnicodeText, nullable=True)  # {code: cum_m2}   BA:BY
    llrf_by_type_json             = Column(UnicodeText, nullable=True)  # {code: llrf}     CA:CY
    ll_non_reducible_by_type_json = Column(UnicodeText, nullable=True)  # {code: kn}       CZ:DX

    # ---------------------------------------------------------------------------
    # Source tracking
    # ---------------------------------------------------------------------------
    data_source = Column(String(20), nullable=True, server_default="revit")
    # values: 'revit' | 'spreadsheet' | 'cad'



# ---------------------------------------------------------------------------
# Transfer definitions (user-editable, source of truth for recompute)
# ---------------------------------------------------------------------------

class RundownTransfer(Base):
    """User-defined transfer relationship.

    Stores the engineer's transfer intent independently of computed results.
    During recompute, rows are converted to TransferDef(dl_kn=None) so the
    engine resolves values from computed source element results.
    """
    __tablename__ = "rundown_transfers"
    __table_args__ = {"schema": "design"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_number = Column(String(50), ForeignKey("management.project_meta.project_number"), nullable=False)
    target_element = Column(String(100), nullable=False)
    source_element = Column(String(100), nullable=False)
    target_level = Column(String(50), nullable=False)
    percent = Column(Numeric(5, 4), nullable=False)
    created_by = Column(String(20), nullable=False, server_default="user")
    created_at = Column(DATETIME2, server_default=text("GETUTCDATE()"))
    updated_at = Column(DATETIME2, server_default=text("GETUTCDATE()"))


# ---------------------------------------------------------------------------
# Rebar
# ---------------------------------------------------------------------------

class Rebar(Base):
    __tablename__ = "rebar"
    __table_args__ = {"schema": "design"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_number = Column(String(50), ForeignKey("management.project_meta.project_number"), nullable=False)
    element_guid = Column(String(50), nullable=False)
    element_type = Column(String(10), nullable=False)
    project_id = Column(Integer, nullable=False)                # dbo.Project(Id), NO FK
    level_id = Column(Integer, nullable=False)                  # dbo.Levels(id), NO FK
    bar_size = Column(String(10), nullable=False)
    spacing_mm = Column(Integer)
    location = Column(String(20), nullable=False)
    layer = Column(Integer, nullable=False, server_default="1")
    quantity = Column(Integer)
    designed_by = Column(String(100), nullable=False)
    designed_at = Column(DATETIME2, nullable=False, server_default="getutcdate()")


# ---------------------------------------------------------------------------
# Design Results
# ---------------------------------------------------------------------------

class DesignResult(Base):
    __tablename__ = "design_results"
    __table_args__ = {"schema": "design"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_number = Column(String(50), ForeignKey("management.project_meta.project_number"), nullable=False)
    element_guid = Column(String(50), nullable=False)
    element_type = Column(String(10), nullable=False)
    project_id = Column(Integer, nullable=False)                # dbo.Project(Id), NO FK
    level_id = Column(Integer, nullable=False)                  # dbo.Levels(id), NO FK
    design_type = Column(String(20), nullable=False)
    utilization_ratio = Column(Numeric(6, 4))
    status = Column(String(20), nullable=False, server_default="Needs Review")
    parameters_json = Column(Unicode)
    designed_by = Column(String(100), nullable=False)
    designed_at = Column(DATETIME2, nullable=False, server_default="getutcdate()")


# ---------------------------------------------------------------------------
# Level Identity (Phase 2 — Identity Hub)
# Cross-source level name resolution: Revit "Level 5" = Spreadsheet "5" = ETABS "L5"
# Scoped to project_number only — survives Clarity wipe-reload
# ---------------------------------------------------------------------------

class LevelIdentity(Base):
    __tablename__ = "level_identity"
    __table_args__ = {"schema": "design"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_number = Column(String(50), ForeignKey("management.project_meta.project_number"), nullable=False)
    canonical_name = Column(String(100), nullable=False)
    sort_order = Column(Integer, nullable=False)

    # Source identifiers (all nullable)
    revit_level_id = Column(Integer, nullable=True)
    revit_name = Column(String(100), nullable=True)
    rundown_name = Column(String(100), nullable=True)
    etabs_name = Column(String(100), nullable=True)

    # Reference only — NOT used for matching (Revit elevations are unreliable)
    revit_elevation_mm = Column(Float, nullable=True)

    match_confidence = Column(Numeric(3, 2), nullable=False, server_default="1.00")
    match_method = Column(String(20), nullable=False, server_default="Manual")

    created_at = Column(DATETIME2, nullable=False, server_default="getutcdate()")
    updated_at = Column(DATETIME2, nullable=False, server_default="getutcdate()")


# ---------------------------------------------------------------------------
# Element Identity (Phase 2 — Identity Hub)
# Cross-source element resolution: central "golden record" per physical element
# Scoped to project_number only — survives Clarity wipe-reload
# ---------------------------------------------------------------------------

class ElementIdentity(Base):
    __tablename__ = "element_identity"
    __table_args__ = {"schema": "design"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_number = Column(String(50), ForeignKey("management.project_meta.project_number"), nullable=False)
    element_type = Column(String(10), nullable=False)       # 'Column' / 'Wall' (canonical)
    canonical_mark = Column(String(50), nullable=False)
    level_identity_id = Column(
        Integer,
        ForeignKey("design.level_identity.id"),
        nullable=True,
    )

    # Source identifiers (all nullable)
    revit_guid = Column(String(50), nullable=True)
    rundown_key = Column(String(100), nullable=True)
    etabs_id = Column(String(100), nullable=True)

    match_confidence = Column(Numeric(3, 2), nullable=False, server_default="1.00")
    match_method = Column(String(20), nullable=False, server_default="Manual")
    last_resolved = Column(DATETIME2, nullable=True)
    notes = Column(String(500), nullable=True)

    created_at = Column(DATETIME2, nullable=False, server_default="getutcdate()")
    updated_at = Column(DATETIME2, nullable=False, server_default="getutcdate()")


# ---------------------------------------------------------------------------
# Rundown Uploads (Phase 2)
# Raw spreadsheet data before identity resolution
# ---------------------------------------------------------------------------

class RundownUpload(Base):
    __tablename__ = "rundown_uploads"
    __table_args__ = {"schema": "design"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_number = Column(String(50), ForeignKey("management.project_meta.project_number"), nullable=False)
    upload_batch_id = Column(UNIQUEIDENTIFIER, nullable=False)
    row_number = Column(Integer, nullable=False)

    # Raw data from spreadsheet
    raw_mark = Column(String(100), nullable=False)
    raw_level = Column(String(100), nullable=False)
    dead_kn = Column(Numeric(12, 4), nullable=True)
    live_kn = Column(Numeric(12, 4), nullable=True)

    # Identity resolution (populated during match step)
    element_identity_id = Column(
        Integer,
        ForeignKey("design.element_identity.id"),
        nullable=True,
    )
    level_identity_id = Column(
        Integer,
        ForeignKey("design.level_identity.id"),
        nullable=True,
    )

    match_status = Column(String(20), nullable=False, server_default="Unmatched")
    uploaded_by = Column(String(100), nullable=False, server_default="system")
    uploaded_at = Column(DATETIME2, nullable=False, server_default="getutcdate()")


# ---------------------------------------------------------------------------
# ETABS Imports
# ---------------------------------------------------------------------------

class EtabsImport(Base):
    __tablename__ = "etabs_imports"
    __table_args__ = {"schema": "design"}

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_number = Column(String(50), ForeignKey("management.project_meta.project_number"), nullable=False)
    project_id = Column(Integer, nullable=False)                # dbo.Project(Id), NO FK
    import_type = Column(String(30), nullable=False)
    data_json = Column(Unicode, nullable=False)
    etabs_model_name = Column(String(255))
    imported_by = Column(String(100), nullable=False)
    imported_at = Column(DATETIME2, nullable=False, server_default="getutcdate()")


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------

class AuditLog(Base):
    __tablename__ = "audit_log"
    __table_args__ = {"schema": "design"}

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    table_name = Column(String(50), nullable=False)
    record_id = Column(Integer, nullable=False)
    action = Column(String(10), nullable=False)
    old_values_json = Column(Unicode)
    new_values_json = Column(Unicode)
    changed_by = Column(String(100), nullable=False)
    changed_at = Column(DATETIME2, nullable=False, server_default="getutcdate()")
