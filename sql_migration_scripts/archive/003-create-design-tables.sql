-- ============================================================================
-- 003-create-design-tables.sql
-- All Phase 1 design schema tables
-- ============================================================================
-- ARCHITECTURE:
--   management.project_meta is the relationship hub.
--   All design tables have:
--     project_number VARCHAR(50) FK → management.project_meta(project_number)
--     project_id     INT         — loose ref to dbo.Project(Id), NO FK
--     level_id       INT         — loose ref to dbo.Levels(id), NO FK
--   ZERO foreign keys to dbo. Design data survives Clarity wipe-reload.
--   Only intra-design FKs (e.g., load_table_id → design.load_tables).
-- ============================================================================
-- Depends on: 002-create-management-tables.sql
-- ============================================================================

USE [JAPBIMDB];
GO

----------------------------------------------------------------------
-- 1. design.load_tables
----------------------------------------------------------------------
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
GO

----------------------------------------------------------------------
-- 2. design.load_areas
----------------------------------------------------------------------
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
GO

CREATE SPATIAL INDEX SX_load_areas_polygon ON design.load_areas(polygon_wkt)
    USING GEOMETRY_AUTO_GRID;
GO

----------------------------------------------------------------------
-- 3. design.tributary_results
----------------------------------------------------------------------
CREATE TABLE design.tributary_results (
    id                  INT             IDENTITY(1,1) PRIMARY KEY,
    project_number      VARCHAR(50)     NOT NULL,
    element_guid        VARCHAR(50)     NOT NULL,
    element_type        VARCHAR(10)     NOT NULL,
    project_id          INT             NOT NULL,       -- dbo.Project(Id), NO FK
    level_id            INT             NOT NULL,       -- dbo.Levels(id), NO FK
    load_table_id       INT             NOT NULL,
    tributary_polygon   GEOMETRY        NULL,
    tributary_area_m2   DECIMAL(12,4)   NOT NULL,
    computed_at         DATETIME2       NOT NULL DEFAULT GETUTCDATE(),
    input_hash          VARCHAR(64)     NULL,

    CONSTRAINT FK_tributary_results_project_meta
        FOREIGN KEY (project_number) REFERENCES management.project_meta(project_number),

    CONSTRAINT FK_tributary_results_load_table
        FOREIGN KEY (load_table_id) REFERENCES design.load_tables(id),

    CONSTRAINT CK_tributary_results_element_type
        CHECK (element_type IN ('Column', 'Wall'))
);
GO

CREATE INDEX IX_tributary_results_element
    ON design.tributary_results(element_guid, project_id, level_id);
GO

CREATE SPATIAL INDEX SX_tributary_results_polygon ON design.tributary_results(tributary_polygon)
    USING GEOMETRY_AUTO_GRID;
GO

----------------------------------------------------------------------
-- 4. design.load_assignments
----------------------------------------------------------------------
CREATE TABLE design.load_assignments (
    id                          INT             IDENTITY(1,1) PRIMARY KEY,
    project_number              VARCHAR(50)     NOT NULL,
    element_guid                VARCHAR(50)     NOT NULL,
    element_type                VARCHAR(10)     NOT NULL,
    project_id                  INT             NOT NULL,       -- dbo.Project(Id), NO FK
    level_id                    INT             NOT NULL,       -- dbo.Levels(id), NO FK
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
GO

CREATE INDEX IX_load_assignments_element
    ON design.load_assignments(element_guid, project_id, level_id);
GO

----------------------------------------------------------------------
-- 5. design.element_marks
----------------------------------------------------------------------
CREATE TABLE design.element_marks (
    id                  INT             IDENTITY(1,1) PRIMARY KEY,
    project_number      VARCHAR(50)     NOT NULL,
    element_guid        VARCHAR(50)     NOT NULL,
    element_type        VARCHAR(10)     NOT NULL,
    project_id          INT             NOT NULL,       -- dbo.Project(Id), NO FK
    raw_mark            VARCHAR(255)    NOT NULL,
    prefix              VARCHAR(50)     NULL,
    type_char           CHAR(1)         NOT NULL,
    element_number      VARCHAR(50)     NOT NULL,
    suffix              VARCHAR(50)     NULL,
    comments            VARCHAR(100)    NULL,
    parsed_successfully BIT             NOT NULL DEFAULT 0,
    level_id            INT             NOT NULL,       -- dbo.Levels(id), NO FK
    parsed_at           DATETIME2       NOT NULL DEFAULT GETUTCDATE(),

    CONSTRAINT FK_element_marks_project_meta
        FOREIGN KEY (project_number) REFERENCES management.project_meta(project_number),

    CONSTRAINT CK_element_marks_element_type
        CHECK (element_type IN ('Column', 'Wall')),

    CONSTRAINT CK_element_marks_type_char
        CHECK (type_char IN ('C', 'W'))
);
GO

CREATE INDEX IX_element_marks_lookup
    ON design.element_marks(project_id, element_type, element_number);
GO

----------------------------------------------------------------------
-- 6. design.element_links
----------------------------------------------------------------------
CREATE TABLE design.element_links (
    id                  INT             IDENTITY(1,1) PRIMARY KEY,
    project_number      VARCHAR(50)     NOT NULL,
    project_id          INT             NOT NULL,       -- dbo.Project(Id), NO FK
    upper_element_guid  VARCHAR(50)     NOT NULL,
    upper_element_type  VARCHAR(10)     NOT NULL,
    upper_level_id      INT             NOT NULL,       -- dbo.Levels(id), NO FK
    lower_element_guid  VARCHAR(50)     NOT NULL,
    lower_element_type  VARCHAR(10)     NOT NULL,
    lower_level_id      INT             NOT NULL,       -- dbo.Levels(id), NO FK
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
GO

CREATE INDEX IX_element_links_upper
    ON design.element_links(project_id, upper_element_guid, upper_level_id);
GO

CREATE INDEX IX_element_links_lower
    ON design.element_links(project_id, lower_element_guid, lower_level_id);
GO

----------------------------------------------------------------------
-- 7. design.rundown
----------------------------------------------------------------------
CREATE TABLE design.rundown (
    id                          INT             IDENTITY(1,1) PRIMARY KEY,
    project_number              VARCHAR(50)     NOT NULL,
    element_guid                VARCHAR(50)     NOT NULL,
    element_type                VARCHAR(10)     NOT NULL,
    project_id                  INT             NOT NULL,       -- dbo.Project(Id), NO FK
    level_id                    INT             NOT NULL,       -- dbo.Levels(id), NO FK
    load_table_id               INT             NOT NULL,
    floor_dead_kn               DECIMAL(12,4)   NOT NULL DEFAULT 0,
    floor_live_kn               DECIMAL(12,4)   NOT NULL DEFAULT 0,
    floor_live_reduced_kn       DECIMAL(12,4)   NOT NULL DEFAULT 0,
    cumulative_dead_kn          DECIMAL(12,4)   NOT NULL DEFAULT 0,
    cumulative_live_kn          DECIMAL(12,4)   NOT NULL DEFAULT 0,
    cumulative_live_reduced_kn  DECIMAL(12,4)   NOT NULL DEFAULT 0,
    rundown_version             INT             NOT NULL DEFAULT 1,
    computed_at                 DATETIME2       NOT NULL DEFAULT GETUTCDATE(),

    CONSTRAINT FK_rundown_project_meta
        FOREIGN KEY (project_number) REFERENCES management.project_meta(project_number),

    CONSTRAINT FK_rundown_load_table
        FOREIGN KEY (load_table_id) REFERENCES design.load_tables(id),

    CONSTRAINT CK_rundown_element_type
        CHECK (element_type IN ('Column', 'Wall'))
);
GO

CREATE INDEX IX_rundown_element_stack
    ON design.rundown(element_guid, project_id, level_id);
GO

----------------------------------------------------------------------
-- 8. design.rebar
----------------------------------------------------------------------
CREATE TABLE design.rebar (
    id              INT             IDENTITY(1,1) PRIMARY KEY,
    project_number  VARCHAR(50)     NOT NULL,
    element_guid    VARCHAR(50)     NOT NULL,
    element_type    VARCHAR(10)     NOT NULL,
    project_id      INT             NOT NULL,       -- dbo.Project(Id), NO FK
    level_id        INT             NOT NULL,       -- dbo.Levels(id), NO FK
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
GO

CREATE INDEX IX_rebar_element
    ON design.rebar(element_guid, project_id, level_id);
GO

----------------------------------------------------------------------
-- 9. design.design_results
----------------------------------------------------------------------
CREATE TABLE design.design_results (
    id                  INT             IDENTITY(1,1) PRIMARY KEY,
    project_number      VARCHAR(50)     NOT NULL,
    element_guid        VARCHAR(50)     NOT NULL,
    element_type        VARCHAR(10)     NOT NULL,
    project_id          INT             NOT NULL,       -- dbo.Project(Id), NO FK
    level_id            INT             NOT NULL,       -- dbo.Levels(id), NO FK
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
GO

CREATE INDEX IX_design_results_element
    ON design.design_results(element_guid, project_id, level_id);
GO

----------------------------------------------------------------------
-- 10. design.etabs_imports
----------------------------------------------------------------------
CREATE TABLE design.etabs_imports (
    id                  INT             IDENTITY(1,1) PRIMARY KEY,
    project_number      VARCHAR(50)     NOT NULL,
    project_id          INT             NOT NULL,       -- dbo.Project(Id), NO FK
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
GO

----------------------------------------------------------------------
-- 11. design.audit_log
----------------------------------------------------------------------
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
GO

CREATE INDEX IX_audit_log_table_record
    ON design.audit_log(table_name, record_id);
GO

CREATE INDEX IX_audit_log_changed_at
    ON design.audit_log(changed_at DESC);
GO

----------------------------------------------------------------------
PRINT '003-create-design-tables completed successfully.';
GO