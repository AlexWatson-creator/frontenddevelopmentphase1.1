-- ============================================================================
-- 007_alter_rundown_transparency.sql
-- Step F: Full transparency — DROP design.rundown and recreate with every
--         FloorResult field + identity hub FKs + element_mark
-- ============================================================================
-- Purpose: Replace the lean rundown table with a fully transparent schema
--   that stores EVERY field from the rundown engine FloorResult dataclass.
--   No black boxes — all DL/LL terms, areas, JSON breakdowns visible in DB.
--
-- Approach: DROP + CREATE (dev environment).  Safe to re-run — drops first.
--
-- load_table_id is kept as a nullable column (no FK) because the spreadsheet
--   upload path has no load_table reference.  Revit path populates it later.
-- ============================================================================
-- Depends on: 003-create-design-tables.sql, 004-create-identity-tables.sql
-- ============================================================================

USE [JAPBIMDB];
GO

SET QUOTED_IDENTIFIER ON;
GO

-- ============================================================================
-- Drop table (cascades nothing; no other table FKs to rundown)
-- ============================================================================

IF OBJECT_ID('design.rundown', 'U') IS NOT NULL
    DROP TABLE design.rundown;
GO

-- ============================================================================
-- Create design.rundown with full FloorResult transparency
-- ============================================================================

CREATE TABLE design.rundown (

    -- -----------------------------------------------------------------------
    -- Primary key + project scope
    -- -----------------------------------------------------------------------
    id             INT IDENTITY(1,1)  NOT NULL  CONSTRAINT PK_rundown PRIMARY KEY,
    project_number VARCHAR(50)        NOT NULL,

    -- -----------------------------------------------------------------------
    -- Element identity (legacy + hub)
    -- -----------------------------------------------------------------------
    element_guid        VARCHAR(50)    NOT NULL,    -- Revit UniqueId or spreadsheet mark (legacy)
    element_type        VARCHAR(10)    NOT NULL,    -- 'Column' / 'Wall'
    element_mark        NVARCHAR(100)  NULL,        -- spreadsheet mark / CAD name / Revit mark
    bot_level           VARCHAR(50)    NULL,        -- FloorResult.bot_level (BOT LEVEL name)
    top_level           VARCHAR(50)    NULL,        -- FloorResult.top_level (TOP LEVEL name)
    element_identity_id INT            NULL,        -- → design.element_identity(id)
    level_identity_id   INT            NULL,        -- → design.level_identity(id)
    floor_order         INT            NULL,        -- 0 = roof, increases toward footing

    -- -----------------------------------------------------------------------
    -- Loose references (no FK — survive Clarity wipe-reload)
    -- -----------------------------------------------------------------------
    project_id    INT  NOT NULL,    -- dbo.Project(Id), NO FK
    level_id      INT  NOT NULL,    -- dbo.Levels(id), NO FK
    load_table_id INT  NULL,        -- design.load_tables(id), NULL for spreadsheet path

    -- -----------------------------------------------------------------------
    -- Legacy aggregate columns — kept for backward compatibility
    --   (same value as dl_cumulative_kn / ll_cumulative_kn)
    -- -----------------------------------------------------------------------
    floor_dead_kn              DECIMAL(12,4)  NOT NULL  DEFAULT 0,
    floor_live_kn              DECIMAL(12,4)  NOT NULL  DEFAULT 0,
    floor_live_reduced_kn      DECIMAL(12,4)  NOT NULL  DEFAULT 0,
    cumulative_dead_kn         DECIMAL(12,4)  NOT NULL  DEFAULT 0,
    cumulative_live_kn         DECIMAL(12,4)  NOT NULL  DEFAULT 0,
    cumulative_live_reduced_kn DECIMAL(12,4)  NOT NULL  DEFAULT 0,
    rundown_version            INT            NOT NULL  DEFAULT 1,
    computed_at                DATETIME2      NOT NULL  DEFAULT GETUTCDATE(),

    -- -----------------------------------------------------------------------
    -- Geometry at this floor (FloorResult cols D, E, X, Y, Z)
    -- -----------------------------------------------------------------------
    story_height_m   DECIMAL(8,4)   NULL,   -- col D: HT above (m)
    concrete_mpa     DECIMAL(6,2)   NULL,   -- col E: Conc. Str. (MPa)
    dim_x_mm         DECIMAL(10,2)  NULL,   -- col X: dimension 1 (mm)
    dim_y            NVARCHAR(10)   NULL,   -- col Y: depth mm or "D"/"S"/"W"
    cross_section_m2 DECIMAL(10,6)  NULL,   -- col Z: cross-section area (m²)

    -- -----------------------------------------------------------------------
    -- Dead Load breakdown — 6 terms + cumulative (col F group)
    -- -----------------------------------------------------------------------
    dl_from_above_kn  DECIMAL(12,4)  NULL,  -- F[N-1]: DL carried from floor above
    dl_floor_load_kn  DECIMAL(12,4)  NULL,  -- SUMPRODUCT(DL_kPa × area_by_type)
    dl_transfer_kn    DECIMAL(12,4)  NULL,  -- DL received via transfer elements
    dl_self_weight_kn DECIMAL(12,4)  NULL,  -- Z × story_height × 24 kN/m³
    dl_cladding_kn    DECIMAL(12,4)  NULL,  -- cladding_kPa × perimeter × height_above
    dl_beam_weight_kn DECIMAL(12,4)  NULL,  -- col V: beam weight
    dl_cumulative_kn  DECIMAL(12,4)  NULL,  -- col F: sum of all 6 DL terms

    -- -----------------------------------------------------------------------
    -- Live Load breakdown — 2-path system + cumulative (col G group)
    -- -----------------------------------------------------------------------
    ll_reducible_kn                DECIMAL(12,4)  NULL,  -- SUMPRODUCT(BA:BY × LL_kPa × LLRF)
    ll_non_reducible_this_floor_kn DECIMAL(12,4)  NULL,  -- SUM(CZ:DX) this floor
    ll_transfer_kn                 DECIMAL(12,4)  NULL,  -- LL from transfers → DY
    dy_cumulative_kn               DECIMAL(12,4)  NULL,  -- col DY: cumulative non-reducible LL
    ll_cumulative_kn               DECIMAL(12,4)  NULL,  -- col G: ll_reducible + dy_cumulative

    -- -----------------------------------------------------------------------
    -- Areas — cols S, T, U
    -- -----------------------------------------------------------------------
    area_this_floor_m2 DECIMAL(12,4)  NULL,  -- col S: SUM(AA:AY)
    transfer_area_m2   DECIMAL(12,4)  NULL,  -- col T: SUMIF transfer CUM_AREA
    cum_area_m2        DECIMAL(12,4)  NULL,  -- col U: cumulative tributary area

    -- -----------------------------------------------------------------------
    -- Derived loads + design capacity checks (cols H, I, J, K, L)
    -- -----------------------------------------------------------------------
    pw_kn        DECIMAL(12,4)  NULL,   -- col H: DL + LL (service load)
    pf_kn        DECIMAL(12,4)  NULL,   -- col I: MAX(1.25DL+1.5LL, 1.4DL)
    f_over_a_mpa DECIMAL(10,4)  NULL,   -- col J: PF/1000/Z (axial stress)
    alpha_factor DECIMAL(6,4)   NULL,   -- col K: MAX(0.85-0.0015f'c, 0.67)
    phi          DECIMAL(6,4)   NULL,   -- capacity reduction (shape-based)
    pct_steel    DECIMAL(8,6)   NULL,   -- col L: reinforcement ratio

    -- -----------------------------------------------------------------------
    -- Input data carried through (cols V, W)
    -- -----------------------------------------------------------------------
    beam_weight_kn       DECIMAL(10,4)  NULL,   -- col V: B-WT (kN)
    cladding_perimeter_m DECIMAL(10,4)  NULL,   -- col W: C-WALL (m)

    -- -----------------------------------------------------------------------
    -- Rebar design — user-editable (cols M-R)
    -- -----------------------------------------------------------------------
    as_mm2       DECIMAL(10,2)  NULL,   -- col M: area of steel (mm²)
    bar_size     VARCHAR(10)    NULL,   -- col N: rebar designation ("20M")
    qty          INT            NULL,   -- col O: quantity
    n_bars       INT            NULL,   -- col P: Nbars — normal laps
    c_bars       INT            NULL,   -- col Q: Cbars — couplers
    rebar_design VARCHAR(20)    NULL,   -- col R: rebar string ("8-20M")

    -- -----------------------------------------------------------------------
    -- Per-type JSON breakdowns (NVARCHAR(MAX) — up to 25 load type codes)
    -- -----------------------------------------------------------------------
    area_by_type_json             NVARCHAR(MAX)  NULL,  -- {code: area_m2}  cols AA:AY
    cum_area_by_type_json         NVARCHAR(MAX)  NULL,  -- {code: cum_m2}   cols BA:BY
    llrf_by_type_json             NVARCHAR(MAX)  NULL,  -- {code: llrf}     cols CA:CY
    ll_non_reducible_by_type_json NVARCHAR(MAX)  NULL,  -- {code: kn}       cols CZ:DX

    -- -----------------------------------------------------------------------
    -- Source tracking
    -- -----------------------------------------------------------------------
    data_source VARCHAR(20)  NULL
        CONSTRAINT DF_rundown_data_source DEFAULT 'revit',
        -- values: 'revit' | 'spreadsheet' | 'cad'

    -- -----------------------------------------------------------------------
    -- Transfer relationships (JSON array of TransferDef dicts per floor)
    -- -----------------------------------------------------------------------
    transfers_json NVARCHAR(MAX)  NULL,   -- [{source_element, target_level, percent, dl_kn, ll_kn, cum_area_m2}]

    -- -----------------------------------------------------------------------
    -- FK constraints
    -- -----------------------------------------------------------------------
    CONSTRAINT FK_rundown_project_meta
        FOREIGN KEY (project_number)
        REFERENCES management.project_meta(project_number),

    CONSTRAINT FK_rundown_element_identity
        FOREIGN KEY (element_identity_id)
        REFERENCES design.element_identity(id),

    CONSTRAINT FK_rundown_level_identity
        FOREIGN KEY (level_identity_id)
        REFERENCES design.level_identity(id)
);
GO

-- ============================================================================
-- Unique index: one row per (element_identity, level_identity)
--   Filtered: only enforced when element_identity_id IS NOT NULL
-- ============================================================================

CREATE UNIQUE INDEX UX_rundown_element_floor
    ON design.rundown(element_identity_id, level_identity_id)
    WHERE element_identity_id IS NOT NULL;
GO

-- ============================================================================
-- Column map (DB column → FloorResult field → Excel column)
-- ============================================================================
--
--  DB column                         FloorResult field                Excel ref
--  --------------------------------  --------------------------------  ---------
--  element_mark                      ElementResult.mark               (sheet name)
--  story_height_m                    FloorResult.story_height_m       col D
--  concrete_mpa                      FloorResult.concrete_mpa         col E
--  dim_x_mm                          FloorResult.dim_x_mm             col X
--  dim_y                             FloorResult.dim_y                col Y
--  cross_section_m2                  FloorResult.cross_section_m2     col Z
--  dl_from_above_kn                  FloorResult.dl_from_above_kn     F[N-1]
--  dl_floor_load_kn                  FloorResult.dl_floor_load_kn     (AA:AY×kPa)
--  dl_transfer_kn                    FloorResult.dl_transfer_kn       (xfer DL)
--  dl_self_weight_kn                 FloorResult.dl_self_weight_kn    (Z×D×24)
--  dl_cladding_kn                    FloorResult.dl_cladding_kn       (kPa×W×D)
--  dl_beam_weight_kn                 FloorResult.dl_beam_weight_kn    col V
--  dl_cumulative_kn                  FloorResult.dl_cumulative_kn     col F
--  ll_reducible_kn                   FloorResult.ll_reducible_kn      (BA:BY×LL×LLRF)
--  ll_non_reducible_this_floor_kn    FloorResult.ll_non_reducible_this_floor_kn  SUM(CZ:DX)
--  ll_transfer_kn                    FloorResult.ll_transfer_kn       (xfer LL)
--  dy_cumulative_kn                  FloorResult.dy_cumulative_kn     col DY
--  ll_cumulative_kn                  FloorResult.ll_cumulative_kn     col G
--  area_this_floor_m2                FloorResult.area_this_floor_m2   col S
--  transfer_area_m2                  FloorResult.transfer_area_m2     col T
--  cum_area_m2                       FloorResult.cum_area_m2          col U
--  pw_kn                             FloorResult.pw_kn                col H
--  pf_kn                             FloorResult.pf_kn                col I
--  f_over_a_mpa                      FloorResult.f_over_a_mpa         col J
--  alpha_factor                      FloorResult.alpha                col K
--  phi                               FloorResult.phi                  —
--  pct_steel                         FloorResult.pct_steel            col L
--  beam_weight_kn                    FloorResult.beam_weight_kn       col V (input)
--  cladding_perimeter_m              FloorResult.cladding_perimeter_m col W (input)
--  as_mm2 / bar_size / qty / ...     FloorResult rebar fields         cols M-R
--  area_by_type_json                 FloorResult.area_by_type         cols AA:AY
--  cum_area_by_type_json             FloorResult.cum_area_by_type     cols BA:BY
--  llrf_by_type_json                 FloorResult.llrf_by_type         cols CA:CY
--  ll_non_reducible_by_type_json     FloorResult.ll_non_reducible_by_type  cols CZ:DX
--  transfers_json                    ElementResult.transfers_received      (filtered per floor)
--
-- Legacy columns (backward compat):
--  cumulative_dead_kn  ← same value as dl_cumulative_kn
--  cumulative_live_kn  ← same value as ll_cumulative_kn

PRINT '007_alter_rundown_transparency.sql completed successfully.';
GO
