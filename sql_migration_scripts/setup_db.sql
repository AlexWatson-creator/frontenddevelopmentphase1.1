-- ============================================================================
-- JAPBIMDB — Jablonsky Data Platform  |  Fresh Database Setup
-- ============================================================================
-- Run this script against an existing JAPBIMDB instance that already has the
-- dbo schema populated by Clarity (Revit geometry sync).
--
-- Creates three schemas:
--   management  — project metadata anchor (project_meta)
--   design      — all engineering data (loads, rundown, identity, rebar, etc.)
--
-- The dbo schema is READ-ONLY from the platform's perspective; this script
-- does NOT modify any dbo tables or stored procedures.
--
-- Prerequisites:
--   - JAPBIMDB database exists
--   - dbo schema has Clarity tables: Project, Levels, Columns, Walls, Beams,
--     Floors, Foundations, Grids, ColumnType, WallType, BeamType, FloorType,
--     FoundationType, Material, SpecialMaterial
--   - guid column already present on dbo element tables (added via Clarity update)
--
-- Execution: Run in SSMS or sqlcmd. Idempotent for the design schema —
--   re-running drops and recreates all design.* tables (they hold no Clarity
--   data). The management schema is preserved across runs.
-- ============================================================================

USE [JAPBIMDB];
GO

SET QUOTED_IDENTIFIER ON;
GO

-- ============================================================================
-- SCHEMAS
-- ============================================================================

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'design')
    EXEC('CREATE SCHEMA design');
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'management')
    EXEC('CREATE SCHEMA management');
GO


-- ============================================================================
-- MANAGEMENT SCHEMA
-- ============================================================================

----------------------------------------------------------------------
-- management.project_meta
-- One row per unique project Number. The stable anchor for all
-- design and identity data. Survives Clarity wipe-reload cycles.
----------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
               WHERE TABLE_SCHEMA = 'management' AND TABLE_NAME = 'project_meta')
BEGIN
    CREATE TABLE management.project_meta (
        id              INT             IDENTITY(1,1) PRIMARY KEY,
        project_number  VARCHAR(50)     NOT NULL,
        address         VARCHAR(255)    NULL,
        job_name        NVARCHAR(255)   NULL,       -- from spreadsheet IMPORT B38
        designer        NVARCHAR(100)   NULL,       -- from spreadsheet IMPORT B40
        created_at      DATETIME2       NOT NULL DEFAULT GETUTCDATE(),
        updated_at      DATETIME2       NOT NULL DEFAULT GETUTCDATE(),

        CONSTRAINT UQ_project_meta_number UNIQUE (project_number)
    );

    CREATE INDEX IX_project_meta_number ON management.project_meta(project_number);
END;
GO

----------------------------------------------------------------------
-- Trigger: auto-create project_meta when a new project Number
-- appears in dbo.Project (after each Clarity sync)
----------------------------------------------------------------------
IF EXISTS (SELECT 1 FROM sys.triggers WHERE name = 'trg_Project_AfterInsert_SyncMeta')
    DROP TRIGGER dbo.trg_Project_AfterInsert_SyncMeta;
GO

CREATE TRIGGER trg_Project_AfterInsert_SyncMeta
ON dbo.Project
AFTER INSERT
AS
BEGIN
    SET NOCOUNT ON;
    INSERT INTO management.project_meta (project_number)
    SELECT DISTINCT i.Number
    FROM inserted i
    WHERE i.Number IS NOT NULL
      AND NOT EXISTS (
          SELECT 1 FROM management.project_meta pm
          WHERE pm.project_number = i.Number
      );
END;
GO

----------------------------------------------------------------------
-- Seed: back-fill project_meta for projects already in dbo.Project
----------------------------------------------------------------------
INSERT INTO management.project_meta (project_number, address)
SELECT DISTINCT p.Number, MIN(p.Address)
FROM dbo.Project p
WHERE p.Number IS NOT NULL
  AND NOT EXISTS (
      SELECT 1 FROM management.project_meta pm
      WHERE pm.project_number = p.Number
  )
GROUP BY p.Number;
GO


-- ============================================================================
-- DESIGN SCHEMA — PHASE 1 TABLES
-- ============================================================================

----------------------------------------------------------------------
-- Reset: drop all design tables in reverse FK order so the CREATE TABLE
-- blocks below always produce the current schema. Design tables hold no
-- Clarity data and are wholly owned by this platform.
----------------------------------------------------------------------
DROP TABLE IF EXISTS design.audit_log;
DROP TABLE IF EXISTS design.rundown_transfers;
DROP TABLE IF EXISTS design.rundown;
DROP TABLE IF EXISTS design.rundown_uploads;
DROP TABLE IF EXISTS design.element_identity;
DROP TABLE IF EXISTS design.level_identity;
DROP TABLE IF EXISTS design.etabs_imports;
DROP TABLE IF EXISTS design.design_results;
DROP TABLE IF EXISTS design.rebar;
DROP TABLE IF EXISTS design.element_links;
DROP TABLE IF EXISTS design.element_marks;
DROP TABLE IF EXISTS design.load_assignments;
DROP TABLE IF EXISTS design.tributary_results;
DROP TABLE IF EXISTS design.load_areas;
DROP TABLE IF EXISTS design.load_tables;
GO

----------------------------------------------------------------------
-- design.load_tables
-- Load type definitions per project file (RES, BALC, MEC, ROOF, etc.)
-- Scoped to project_id (dbo.Project.Id) + project_number.
----------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
               WHERE TABLE_SCHEMA = 'design' AND TABLE_NAME = 'load_tables')
BEGIN
    CREATE TABLE design.load_tables (
        id              INT             IDENTITY(1,1) PRIMARY KEY,
        project_number  VARCHAR(50)     NOT NULL,
        project_id      INT             NOT NULL,       -- dbo.Project(Id), NO FK
        name            VARCHAR(20)     NOT NULL,
        description     VARCHAR(100)    NULL,
        dead_load_kpa   DECIMAL(10,4)   NULL,
        live_load_kpa   DECIMAL(10,4)   NULL,
        llrf_type       VARCHAR(10)     NOT NULL DEFAULT 'N',
        created_by      VARCHAR(100)    NOT NULL,
        created_at      DATETIME2       NOT NULL DEFAULT GETUTCDATE(),
        updated_at      DATETIME2       NOT NULL DEFAULT GETUTCDATE(),

        CONSTRAINT FK_load_tables_project_meta
            FOREIGN KEY (project_number) REFERENCES management.project_meta(project_number),

        CONSTRAINT UQ_load_tables_project_name
            UNIQUE (project_id, name)
    );
END;
GO

----------------------------------------------------------------------
-- design.load_areas
-- Load area polygons drawn on the floor plan per level.
-- FK to load_tables uses NO ACTION (SQL Server cascade path limitation).
----------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
               WHERE TABLE_SCHEMA = 'design' AND TABLE_NAME = 'load_areas')
BEGIN
    CREATE TABLE design.load_areas (
        id              INT             IDENTITY(1,1) PRIMARY KEY,
        project_number  VARCHAR(50)     NOT NULL,
        project_id      INT             NOT NULL,       -- dbo.Project(Id), NO FK
        level_id        INT             NOT NULL,       -- dbo.Levels(id), NO FK
        load_table_id   INT             NOT NULL,
        polygon_wkt     GEOMETRY        NOT NULL,
        source          VARCHAR(20)     NOT NULL DEFAULT 'web_draw',
        created_by      VARCHAR(100)    NOT NULL,
        created_at      DATETIME2       NOT NULL DEFAULT GETUTCDATE(),
        updated_at      DATETIME2       NOT NULL DEFAULT GETUTCDATE(),
        version         INT             NOT NULL DEFAULT 1,

        CONSTRAINT FK_load_areas_project_meta
            FOREIGN KEY (project_number) REFERENCES management.project_meta(project_number),

        CONSTRAINT FK_load_areas_load_table
            FOREIGN KEY (load_table_id) REFERENCES design.load_tables(id),

        CONSTRAINT CK_load_areas_source
            CHECK (source IN ('web_draw', 'json_upload', 'slab_auto'))
    );

    CREATE SPATIAL INDEX SX_load_areas_polygon ON design.load_areas(polygon_wkt)
        USING GEOMETRY_AUTO_GRID
        WITH (BOUNDING_BOX = (-2000000, -2000000, 2000000, 2000000));
END;
GO

----------------------------------------------------------------------
-- design.tributary_results
-- Voronoi-computed tributary area per element per floor per load type.
----------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
               WHERE TABLE_SCHEMA = 'design' AND TABLE_NAME = 'tributary_results')
BEGIN
    CREATE TABLE design.tributary_results (
        id                      INT             IDENTITY(1,1) PRIMARY KEY,
        project_number          VARCHAR(50)     NOT NULL,
        element_guid            VARCHAR(50)     NOT NULL,
        element_type            VARCHAR(10)     NOT NULL,
        project_id              INT             NOT NULL,       -- dbo.Project(Id), NO FK
        level_id                INT             NOT NULL,       -- dbo.Levels(id), NO FK
        load_table_id           INT             NOT NULL,
        tributary_polygon       GEOMETRY        NULL,
        tributary_area_m2       DECIMAL(12,4)   NOT NULL,
        beam_weights_detail     NVARCHAR(500)   NULL,           -- comma-separated kN per beam
        computed_at             DATETIME2       NOT NULL DEFAULT GETUTCDATE(),
        input_hash              VARCHAR(64)     NULL,

        CONSTRAINT FK_tributary_results_project_meta
            FOREIGN KEY (project_number) REFERENCES management.project_meta(project_number),

        CONSTRAINT FK_tributary_results_load_table
            FOREIGN KEY (load_table_id) REFERENCES design.load_tables(id),

        CONSTRAINT CK_tributary_results_element_type
            CHECK (element_type IN ('Column', 'Wall'))
    );

    CREATE INDEX IX_tributary_results_element
        ON design.tributary_results(element_guid, project_id, level_id);

    CREATE SPATIAL INDEX SX_tributary_results_polygon ON design.tributary_results(tributary_polygon)
        USING GEOMETRY_AUTO_GRID
        WITH (BOUNDING_BOX = (-2000000, -2000000, 2000000, 2000000));
END;
GO

----------------------------------------------------------------------
-- design.load_assignments
-- Resolved load per element per floor — area × kPa × LLRF.
----------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
               WHERE TABLE_SCHEMA = 'design' AND TABLE_NAME = 'load_assignments')
BEGIN
    CREATE TABLE design.load_assignments (
        id                          INT             IDENTITY(1,1) PRIMARY KEY,
        project_number              VARCHAR(50)     NOT NULL,
        element_guid                VARCHAR(50)     NOT NULL,
        element_type                VARCHAR(10)     NOT NULL,
        project_id                  INT             NOT NULL,
        level_id                    INT             NOT NULL,
        load_table_id               INT             NOT NULL,
        tributary_area_m2           DECIMAL(12,4)   NOT NULL,
        dead_load_kn                DECIMAL(12,4)   NOT NULL,
        live_load_kn                DECIMAL(12,4)   NOT NULL,
        live_load_reduced_kn        DECIMAL(12,4)   NULL,
        llrf_factor                 DECIMAL(6,4)    NULL,
        cumulative_supported_floors INT             NULL,
        computed_at                 DATETIME2       NOT NULL DEFAULT GETUTCDATE(),

        CONSTRAINT FK_load_assignments_project_meta
            FOREIGN KEY (project_number) REFERENCES management.project_meta(project_number),

        CONSTRAINT FK_load_assignments_load_table
            FOREIGN KEY (load_table_id) REFERENCES design.load_tables(id),

        CONSTRAINT CK_load_assignments_element_type
            CHECK (element_type IN ('Column', 'Wall'))
    );

    CREATE INDEX IX_load_assignments_element
        ON design.load_assignments(element_guid, project_id, level_id);
END;
GO

----------------------------------------------------------------------
-- design.element_marks
-- Parsed element labels following firm naming convention.
----------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
               WHERE TABLE_SCHEMA = 'design' AND TABLE_NAME = 'element_marks')
BEGIN
    CREATE TABLE design.element_marks (
        id                  INT             IDENTITY(1,1) PRIMARY KEY,
        project_number      VARCHAR(50)     NOT NULL,
        element_guid        VARCHAR(50)     NOT NULL,
        element_type        VARCHAR(10)     NOT NULL,
        project_id          INT             NOT NULL,
        raw_mark            VARCHAR(255)    NOT NULL,
        prefix              VARCHAR(50)     NULL,
        type_char           CHAR(1)         NOT NULL,
        element_number      VARCHAR(50)     NOT NULL,
        suffix              VARCHAR(50)     NULL,
        comments            VARCHAR(100)    NULL,
        parsed_successfully BIT             NOT NULL DEFAULT 0,
        level_id            INT             NOT NULL,
        parsed_at           DATETIME2       NOT NULL DEFAULT GETUTCDATE(),

        CONSTRAINT FK_element_marks_project_meta
            FOREIGN KEY (project_number) REFERENCES management.project_meta(project_number),

        CONSTRAINT CK_element_marks_element_type
            CHECK (element_type IN ('Column', 'Wall')),

        CONSTRAINT CK_element_marks_type_char
            CHECK (type_char IN ('C', 'W'))
    );

    CREATE INDEX IX_element_marks_lookup
        ON design.element_marks(project_id, element_type, element_number);
END;
GO

----------------------------------------------------------------------
-- design.element_links
-- Vertical chain mapping — which element supports which across floors.
----------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
               WHERE TABLE_SCHEMA = 'design' AND TABLE_NAME = 'element_links')
BEGIN
    CREATE TABLE design.element_links (
        id                  INT             IDENTITY(1,1) PRIMARY KEY,
        project_number      VARCHAR(50)     NOT NULL,
        project_id          INT             NOT NULL,
        upper_element_guid  VARCHAR(50)     NOT NULL,
        upper_element_type  VARCHAR(10)     NOT NULL,
        upper_level_id      INT             NOT NULL,
        lower_element_guid  VARCHAR(50)     NOT NULL,
        lower_element_type  VARCHAR(10)     NOT NULL,
        lower_level_id      INT             NOT NULL,
        link_type           VARCHAR(20)     NOT NULL DEFAULT 'Direct',
        transfer_ratio      DECIMAL(6,4)    NOT NULL DEFAULT 1.0,
        confidence          VARCHAR(10)     NOT NULL DEFAULT 'Medium',
        match_method        VARCHAR(20)     NOT NULL,
        created_at          DATETIME2       NOT NULL DEFAULT GETUTCDATE(),
        updated_at          DATETIME2       NOT NULL DEFAULT GETUTCDATE(),

        CONSTRAINT FK_element_links_project_meta
            FOREIGN KEY (project_number) REFERENCES management.project_meta(project_number),

        CONSTRAINT CK_element_links_link_type
            CHECK (link_type IN ('Direct', 'Transferred', 'Partial')),

        CONSTRAINT CK_element_links_confidence
            CHECK (confidence IN ('High', 'Medium', 'Low')),

        CONSTRAINT CK_element_links_match_method
            CHECK (match_method IN ('Label', 'Geometry', 'LLM', 'Manual')),

        CONSTRAINT CK_element_links_upper_type
            CHECK (upper_element_type IN ('Column', 'Wall')),

        CONSTRAINT CK_element_links_lower_type
            CHECK (lower_element_type IN ('Column', 'Wall'))
    );

    CREATE INDEX IX_element_links_upper
        ON design.element_links(project_id, upper_element_guid, upper_level_id);

    CREATE INDEX IX_element_links_lower
        ON design.element_links(project_id, lower_element_guid, lower_level_id);
END;
GO

----------------------------------------------------------------------
-- design.rebar
-- Reinforcement records per element per floor.
----------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
               WHERE TABLE_SCHEMA = 'design' AND TABLE_NAME = 'rebar')
BEGIN
    CREATE TABLE design.rebar (
        id              INT             IDENTITY(1,1) PRIMARY KEY,
        project_number  VARCHAR(50)     NOT NULL,
        element_guid    VARCHAR(50)     NOT NULL,
        element_type    VARCHAR(10)     NOT NULL,
        project_id      INT             NOT NULL,
        level_id        INT             NOT NULL,
        bar_size        VARCHAR(10)     NOT NULL,
        spacing_mm      INT             NULL,
        location        VARCHAR(20)     NOT NULL,
        layer           INT             NOT NULL DEFAULT 1,
        quantity        INT             NULL,
        designed_by     VARCHAR(100)    NOT NULL,
        designed_at     DATETIME2       NOT NULL DEFAULT GETUTCDATE(),

        CONSTRAINT FK_rebar_project_meta
            FOREIGN KEY (project_number) REFERENCES management.project_meta(project_number),

        CONSTRAINT CK_rebar_element_type
            CHECK (element_type IN ('Column', 'Wall')),

        CONSTRAINT CK_rebar_bar_size
            CHECK (bar_size IN ('10M', '15M', '20M', '25M', '30M', '35M')),

        CONSTRAINT CK_rebar_location
            CHECK (location IN ('Top', 'Bottom', 'Vertical', 'Ties'))
    );

    CREATE INDEX IX_rebar_element
        ON design.rebar(element_guid, project_id, level_id);
END;
GO

----------------------------------------------------------------------
-- design.design_results
-- Design check outputs per element (utilization ratios, pass/fail).
----------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
               WHERE TABLE_SCHEMA = 'design' AND TABLE_NAME = 'design_results')
BEGIN
    CREATE TABLE design.design_results (
        id                  INT             IDENTITY(1,1) PRIMARY KEY,
        project_number      VARCHAR(50)     NOT NULL,
        element_guid        VARCHAR(50)     NOT NULL,
        element_type        VARCHAR(10)     NOT NULL,
        project_id          INT             NOT NULL,
        level_id            INT             NOT NULL,
        design_type         VARCHAR(20)     NOT NULL,
        utilization_ratio   DECIMAL(6,4)    NULL,
        status              VARCHAR(20)     NOT NULL DEFAULT 'Needs Review',
        parameters_json     NVARCHAR(MAX)   NULL,
        designed_by         VARCHAR(100)    NOT NULL,
        designed_at         DATETIME2       NOT NULL DEFAULT GETUTCDATE(),

        CONSTRAINT FK_design_results_project_meta
            FOREIGN KEY (project_number) REFERENCES management.project_meta(project_number),

        CONSTRAINT CK_design_results_element_type
            CHECK (element_type IN ('Column', 'Wall', 'Footing', 'Slab')),

        CONSTRAINT CK_design_results_design_type
            CHECK (design_type IN ('Footing', 'Column', 'Wall', 'Slab', 'Lateral')),

        CONSTRAINT CK_design_results_status
            CHECK (status IN ('Pass', 'Fail', 'Needs Review'))
    );

    CREATE INDEX IX_design_results_element
        ON design.design_results(element_guid, project_id, level_id);
END;
GO

----------------------------------------------------------------------
-- design.etabs_imports
-- Data imported from ETABS/SAFE plugin (Phase 4 placeholder).
----------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
               WHERE TABLE_SCHEMA = 'design' AND TABLE_NAME = 'etabs_imports')
BEGIN
    CREATE TABLE design.etabs_imports (
        id                  INT             IDENTITY(1,1) PRIMARY KEY,
        project_number      VARCHAR(50)     NOT NULL,
        project_id          INT             NOT NULL,
        import_type         VARCHAR(30)     NOT NULL,
        data_json           NVARCHAR(MAX)   NOT NULL,
        etabs_model_name    VARCHAR(255)    NULL,
        imported_by         VARCHAR(100)    NOT NULL,
        imported_at         DATETIME2       NOT NULL DEFAULT GETUTCDATE(),

        CONSTRAINT FK_etabs_imports_project_meta
            FOREIGN KEY (project_number) REFERENCES management.project_meta(project_number),

        CONSTRAINT CK_etabs_imports_type
            CHECK (import_type IN ('Forces', 'Drift', 'Modal', 'Reactions'))
    );
END;
GO

----------------------------------------------------------------------
-- design.audit_log
-- Full history of all changes to design data.
----------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
               WHERE TABLE_SCHEMA = 'design' AND TABLE_NAME = 'audit_log')
BEGIN
    CREATE TABLE design.audit_log (
        id                  BIGINT          IDENTITY(1,1) PRIMARY KEY,
        table_name          VARCHAR(50)     NOT NULL,
        record_id           INT             NOT NULL,
        action              VARCHAR(10)     NOT NULL,
        old_values_json     NVARCHAR(MAX)   NULL,
        new_values_json     NVARCHAR(MAX)   NULL,
        changed_by          VARCHAR(100)    NOT NULL,
        changed_at          DATETIME2       NOT NULL DEFAULT GETUTCDATE(),

        CONSTRAINT CK_audit_log_action
            CHECK (action IN ('Insert', 'Update', 'Delete'))
    );

    CREATE INDEX IX_audit_log_table_record
        ON design.audit_log(table_name, record_id);

    CREATE INDEX IX_audit_log_changed_at
        ON design.audit_log(changed_at DESC);
END;
GO


-- ============================================================================
-- DESIGN SCHEMA — PHASE 2 IDENTITY HUB TABLES
-- ============================================================================

----------------------------------------------------------------------
-- design.level_identity
-- Cross-source level name resolution.
-- "Level 5" (Revit) = "5" (Spreadsheet) = "L5" (ETABS).
-- Matched by ordinal (sort_order), NOT elevation (Revit elevations unreliable).
----------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
               WHERE TABLE_SCHEMA = 'design' AND TABLE_NAME = 'level_identity')
BEGIN
    CREATE TABLE design.level_identity (
        id                  INT             IDENTITY(1,1) PRIMARY KEY,
        project_number      VARCHAR(50)     NOT NULL,
        canonical_name      VARCHAR(100)    NOT NULL,
        sort_order          INT             NOT NULL,       -- ordinal: 1 = lowest

        -- Source identifiers (all nullable — populated as sources connect)
        revit_level_id      INT             NULL,           -- dbo.Levels.id, NO FK
        revit_name          VARCHAR(100)    NULL,
        rundown_name        VARCHAR(100)    NULL,
        etabs_name          VARCHAR(100)    NULL,

        -- Reference only — NOT used for matching
        revit_elevation_mm  FLOAT           NULL,

        match_confidence    DECIMAL(3,2)    NOT NULL DEFAULT 1.00,
        match_method        VARCHAR(20)     NOT NULL DEFAULT 'Manual',

        created_at          DATETIME2       NOT NULL DEFAULT GETUTCDATE(),
        updated_at          DATETIME2       NOT NULL DEFAULT GETUTCDATE(),

        CONSTRAINT FK_level_identity_project_meta
            FOREIGN KEY (project_number) REFERENCES management.project_meta(project_number),

        CONSTRAINT UQ_level_identity_project_canonical
            UNIQUE (project_number, canonical_name)
    );

    CREATE INDEX IX_level_identity_project
        ON design.level_identity(project_number);
END;
GO

----------------------------------------------------------------------
-- design.element_identity
-- Cross-source element resolution — the "golden record" per element.
-- No FK to dbo tables: survives Clarity wipe-reload cycles.
----------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
               WHERE TABLE_SCHEMA = 'design' AND TABLE_NAME = 'element_identity')
BEGIN
    CREATE TABLE design.element_identity (
        id                  INT             IDENTITY(1,1) PRIMARY KEY,
        project_number      VARCHAR(50)     NOT NULL,
        element_type        VARCHAR(10)     NOT NULL,       -- 'Column' / 'Wall'
        canonical_mark      VARCHAR(50)     NOT NULL,
        level_identity_id   INT             NULL,

        -- Source identifiers (all nullable)
        revit_guid          VARCHAR(50)     NULL,
        rundown_key         VARCHAR(100)    NULL,
        etabs_id            VARCHAR(100)    NULL,           -- Phase 4 placeholder

        match_confidence    DECIMAL(3,2)    NOT NULL DEFAULT 1.00,
        match_method        VARCHAR(20)     NOT NULL DEFAULT 'Manual',
        last_resolved       DATETIME2       NULL,
        notes               VARCHAR(500)    NULL,

        created_at          DATETIME2       NOT NULL DEFAULT GETUTCDATE(),
        updated_at          DATETIME2       NOT NULL DEFAULT GETUTCDATE(),

        CONSTRAINT FK_element_identity_project_meta
            FOREIGN KEY (project_number) REFERENCES management.project_meta(project_number),

        CONSTRAINT FK_element_identity_level
            FOREIGN KEY (level_identity_id) REFERENCES design.level_identity(id)
    );

    CREATE INDEX IX_element_identity_project
        ON design.element_identity(project_number);

    -- One revit_guid per project (filtered: only when not NULL)
    CREATE UNIQUE INDEX UX_element_identity_revit_guid
        ON design.element_identity(project_number, revit_guid)
        WHERE revit_guid IS NOT NULL;
END;
GO

----------------------------------------------------------------------
-- design.rundown_uploads
-- Raw spreadsheet data before identity resolution.
----------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
               WHERE TABLE_SCHEMA = 'design' AND TABLE_NAME = 'rundown_uploads')
BEGIN
    CREATE TABLE design.rundown_uploads (
        id                      INT                 IDENTITY(1,1) PRIMARY KEY,
        project_number          VARCHAR(50)         NOT NULL,
        upload_batch_id         UNIQUEIDENTIFIER    NOT NULL,
        row_number              INT                 NOT NULL,

        -- Raw data from spreadsheet
        raw_mark                VARCHAR(100)        NOT NULL,
        raw_level               VARCHAR(100)        NOT NULL,
        dead_kn                 DECIMAL(12,4)       NULL,
        live_kn                 DECIMAL(12,4)       NULL,

        -- Identity resolution (populated during match step)
        element_identity_id     INT                 NULL,
        level_identity_id       INT                 NULL,

        match_status            VARCHAR(20)         NOT NULL DEFAULT 'Unmatched',
        uploaded_by             VARCHAR(100)        NOT NULL DEFAULT 'system',
        uploaded_at             DATETIME2           NOT NULL DEFAULT GETUTCDATE(),

        CONSTRAINT FK_rundown_uploads_project_meta
            FOREIGN KEY (project_number) REFERENCES management.project_meta(project_number),

        CONSTRAINT FK_rundown_uploads_element
            FOREIGN KEY (element_identity_id) REFERENCES design.element_identity(id),

        CONSTRAINT FK_rundown_uploads_level
            FOREIGN KEY (level_identity_id) REFERENCES design.level_identity(id)
    );

    CREATE INDEX IX_rundown_uploads_batch
        ON design.rundown_uploads(upload_batch_id);

    CREATE INDEX IX_rundown_uploads_project
        ON design.rundown_uploads(project_number);
END;
GO


-- ============================================================================
-- DESIGN SCHEMA — RUNDOWN (FULL TRANSPARENCY)
-- ============================================================================
-- design.rundown stores every intermediate value from the rundown engine
-- (FloorResult dataclass). No black boxes — all DL/LL terms, areas, and
-- JSON breakdowns are visible in the DB. Engineers can verify any value.
--
-- Column map (DB col → FloorResult field → Excel column):
--   story_height_m   → FloorResult.story_height_m   → col D
--   concrete_mpa     → FloorResult.concrete_mpa     → col E
--   dim_x_mm         → FloorResult.dim_x_mm         → col X
--   dim_y            → FloorResult.dim_y             → col Y
--   cross_section_m2 → FloorResult.cross_section_m2 → col Z
--   dl_cumulative_kn → FloorResult.dl_cumulative_kn → col F
--   ll_cumulative_kn → FloorResult.ll_cumulative_kn → col G
--   pw_kn            → FloorResult.pw_kn            → col H
--   pf_kn            → FloorResult.pf_kn            → col I
--   f_over_a_mpa     → FloorResult.f_over_a_mpa     → col J
--   alpha_factor     → FloorResult.alpha             → col K
--   pct_steel        → FloorResult.pct_steel         → col L
--   as_mm2 ... rebar → FloorResult rebar fields      → cols M-R
--   area_this_floor_m2 → FloorResult.area_this_floor_m2 → col S
--   transfer_area_m2 → FloorResult.transfer_area_m2  → col T
--   cum_area_m2      → FloorResult.cum_area_m2       → col U
--   beam_weight_kn   → FloorResult.beam_weight_kn    → col V
--   cladding_perimeter_m → FloorResult.cladding_perimeter_m → col W
--   area_by_type_json → FloorResult.area_by_type     → cols AA:AY
-- ============================================================================

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
               WHERE TABLE_SCHEMA = 'design' AND TABLE_NAME = 'rundown')
BEGIN
    CREATE TABLE design.rundown (

        -- Primary key + project scope
        id             INT IDENTITY(1,1)  NOT NULL  CONSTRAINT PK_rundown PRIMARY KEY,
        project_number VARCHAR(50)        NOT NULL,

        -- Element identity (legacy + hub)
        element_guid        VARCHAR(50)    NOT NULL,
        element_type        VARCHAR(10)    NOT NULL,    -- 'Column' / 'Wall'
        element_mark        NVARCHAR(100)  NULL,        -- spreadsheet / CAD / Revit mark
        bot_level           VARCHAR(50)    NULL,
        top_level           VARCHAR(50)    NULL,
        element_identity_id INT            NULL,        -- → design.element_identity(id)
        level_identity_id   INT            NULL,        -- → design.level_identity(id)
        floor_order         INT            NULL,        -- 0 = roof, increases toward footing

        -- Loose references (no FK — survive Clarity wipe-reload)
        project_id    INT  NOT NULL,                    -- dbo.Project(Id), NO FK
        level_id      INT  NOT NULL,                    -- dbo.Levels(id), NO FK
        load_table_id INT  NULL,                        -- NULL for spreadsheet/CAD path

        -- Legacy aggregate columns (backward compat — same value as dl/ll_cumulative)
        floor_dead_kn              DECIMAL(12,4)  NOT NULL  DEFAULT 0,
        floor_live_kn              DECIMAL(12,4)  NOT NULL  DEFAULT 0,
        floor_live_reduced_kn      DECIMAL(12,4)  NOT NULL  DEFAULT 0,
        cumulative_dead_kn         DECIMAL(12,4)  NOT NULL  DEFAULT 0,
        cumulative_live_kn         DECIMAL(12,4)  NOT NULL  DEFAULT 0,
        cumulative_live_reduced_kn DECIMAL(12,4)  NOT NULL  DEFAULT 0,
        rundown_version            INT            NOT NULL  DEFAULT 1,
        computed_at                DATETIME2      NOT NULL  DEFAULT GETUTCDATE(),

        -- Geometry at this floor
        story_height_m   DECIMAL(8,4)   NULL,
        concrete_mpa     DECIMAL(6,2)   NULL,
        dim_x_mm         DECIMAL(10,2)  NULL,
        dim_y            NVARCHAR(10)   NULL,
        cross_section_m2 DECIMAL(10,6)  NULL,

        -- Dead Load breakdown — 6 terms (col F)
        dl_from_above_kn  DECIMAL(12,4)  NULL,
        dl_floor_load_kn  DECIMAL(12,4)  NULL,
        dl_transfer_kn    DECIMAL(12,4)  NULL,
        dl_self_weight_kn DECIMAL(12,4)  NULL,
        dl_cladding_kn    DECIMAL(12,4)  NULL,
        dl_beam_weight_kn DECIMAL(12,4)  NULL,
        dl_cumulative_kn  DECIMAL(12,4)  NULL,         -- col F

        -- Live Load breakdown — 2-path system (col G)
        ll_reducible_kn                DECIMAL(12,4)  NULL,
        ll_non_reducible_this_floor_kn DECIMAL(12,4)  NULL,
        ll_transfer_kn                 DECIMAL(12,4)  NULL,
        dy_cumulative_kn               DECIMAL(12,4)  NULL,
        ll_cumulative_kn               DECIMAL(12,4)  NULL,  -- col G

        -- Areas (cols S, T, U)
        area_this_floor_m2 DECIMAL(12,4)  NULL,
        transfer_area_m2   DECIMAL(12,4)  NULL,
        cum_area_m2        DECIMAL(12,4)  NULL,

        -- Derived loads + capacity checks (cols H-L)
        pw_kn        DECIMAL(12,4)  NULL,
        pf_kn        DECIMAL(12,4)  NULL,
        f_over_a_mpa DECIMAL(10,4)  NULL,
        alpha_factor DECIMAL(6,4)   NULL,
        phi          DECIMAL(6,4)   NULL,
        pct_steel    DECIMAL(8,6)   NULL,

        -- Input data (cols V, W)
        beam_weight_kn       DECIMAL(10,4)  NULL,
        cladding_perimeter_m DECIMAL(10,4)  NULL,

        -- Rebar design — user-editable (cols M-R)
        as_mm2       DECIMAL(10,2)  NULL,
        bar_size     VARCHAR(10)    NULL,
        qty          INT            NULL,
        n_bars       INT            NULL,              -- Nbars = normal laps
        c_bars       INT            NULL,              -- Cbars = couplers
        rebar_design VARCHAR(20)    NULL,

        -- Rebar override flags (set when engineer manually edits)
        qty_override   BIT  NOT NULL  DEFAULT 0,
        n_bars_override BIT NOT NULL  DEFAULT 0,
        c_bars_override BIT NOT NULL  DEFAULT 0,

        -- Per-type JSON breakdowns (up to 25 project-specific load type codes)
        area_by_type_json             NVARCHAR(MAX)  NULL,
        cum_area_by_type_json         NVARCHAR(MAX)  NULL,
        llrf_by_type_json             NVARCHAR(MAX)  NULL,
        ll_non_reducible_by_type_json NVARCHAR(MAX)  NULL,

        -- Source tracking ('revit' | 'spreadsheet' | 'cad')
        data_source VARCHAR(20)  NULL  DEFAULT 'revit',

        -- FK constraints
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

    -- One row per (element_identity, level_identity) — filtered when not NULL
    CREATE UNIQUE INDEX UX_rundown_element_floor
        ON design.rundown(element_identity_id, level_identity_id)
        WHERE element_identity_id IS NOT NULL;

    CREATE INDEX IX_rundown_element_stack
        ON design.rundown(element_guid, project_id, level_id);
END;
GO

----------------------------------------------------------------------
-- design.rundown_transfers
-- Engineer-defined load transfer relationships per project.
-- Stores source → target element transfer rules independent of computed results.
----------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
               WHERE TABLE_SCHEMA = 'design' AND TABLE_NAME = 'rundown_transfers')
BEGIN
    CREATE TABLE design.rundown_transfers (
        id              INT IDENTITY(1,1) PRIMARY KEY,
        project_number  VARCHAR(50)  NOT NULL,
        target_element  VARCHAR(100) NOT NULL,
        source_element  VARCHAR(100) NOT NULL,
        target_level    VARCHAR(50)  NOT NULL,
        [percent]       DECIMAL(5,4) NOT NULL,
        created_by      VARCHAR(20)  NOT NULL DEFAULT 'user',
        created_at      DATETIME2    NOT NULL DEFAULT GETUTCDATE(),
        updated_at      DATETIME2    NOT NULL DEFAULT GETUTCDATE(),

        CONSTRAINT FK_rundown_transfers_project
            FOREIGN KEY (project_number)
            REFERENCES management.project_meta(project_number),

        CONSTRAINT CK_rundown_transfers_percent
            CHECK ([percent] > 0 AND [percent] <= 2.0)
    );

    CREATE INDEX IX_rundown_transfers_project_target
        ON design.rundown_transfers (project_number, target_element);

    CREATE INDEX IX_rundown_transfers_project_source
        ON design.rundown_transfers (project_number, source_element);
END;
GO

----------------------------------------------------------------------
-- User creation and storage.
-- Shows user's email, role (platform_admin / structural_designer / bim_designer), and ban status.
-- Can store new users.
----------------------------------------------------------------------
IF EXISTS (SELECT * FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'management' AND TABLE_NAME = 'users')
BEGIN
    DROP TABLE management.users;
END

IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES
               WHERE TABLE_SCHEMA = 'management' AND TABLE_NAME = 'users')
BEGIN
    CREATE TABLE management.users (
        id              INT             IDENTITY(1,1) PRIMARY KEY,
        email           VARCHAR(255)    NOT NULL,
        password_hash   VARCHAR(255)    NOT NULL,
        first_name      VARCHAR(100)    NOT NULL,
        last_name       VARCHAR(100)    NOT NULL,
        role            VARCHAR(30)     NOT NULL DEFAULT 'STRUCTURAL DESIGNER',
        is_banned       BIT             NOT NULL DEFAULT 0,
        created_at      DATETIME2       NOT NULL DEFAULT GETUTCDATE(),
        updated_at      DATETIME2       NOT NULL DEFAULT GETUTCDATE(),

        CONSTRAINT CK_users_role CHECK (
            role IN ('PLATFORM ADMIN', 'STRUCTURAL DESIGNER', 'BIM DESIGNER')
        ),
        CONSTRAINT UQ_users_email UNIQUE (email)
    );
END;
GO

-- ============================================================================
PRINT 'JAPBIMDB setup complete. All management and design schema tables created.';
GO
