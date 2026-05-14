-- ============================================================================
-- 004-create-identity-tables.sql
-- Phase 2: Identity Hub tables for cross-source element resolution
-- ============================================================================
-- These tables are scoped to project_number only (no file-level project_id).
-- FK to management.project_meta(project_number) — the stable anchor.
-- Intra-design FKs: element_identity → level_identity, rundown_uploads → both.
-- ============================================================================
-- Depends on: 002-create-management-tables.sql
-- ============================================================================

USE [JAPBIMDB];
GO

SET QUOTED_IDENTIFIER ON;
GO

----------------------------------------------------------------------
-- 1. design.level_identity
-- Cross-source level name resolution:
--   Revit "Level 5" = Spreadsheet "5" = ETABS "L5"
----------------------------------------------------------------------
CREATE TABLE design.level_identity (
    id                  INT             IDENTITY(1,1) PRIMARY KEY,
    project_number      VARCHAR(50)     NOT NULL,
    canonical_name      VARCHAR(100)    NOT NULL,
    sort_order          INT             NOT NULL,       -- ordinal: 1 = lowest

    -- Source identifiers (all nullable — populated as sources are connected)
    revit_level_id      INT             NULL,           -- dbo.Levels.id (loose ref, NO FK)
    revit_name          VARCHAR(100)    NULL,
    rundown_name        VARCHAR(100)    NULL,
    etabs_name          VARCHAR(100)    NULL,

    -- Reference only — NOT used for matching (Revit elevations are unreliable)
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
GO

CREATE INDEX IX_level_identity_project
    ON design.level_identity(project_number);
GO

----------------------------------------------------------------------
-- 2. design.element_identity
-- Cross-source element resolution: central "golden record" per element
----------------------------------------------------------------------
CREATE TABLE design.element_identity (
    id                  INT             IDENTITY(1,1) PRIMARY KEY,
    project_number      VARCHAR(50)     NOT NULL,
    element_type        VARCHAR(10)     NOT NULL,       -- 'Column' / 'Wall'
    canonical_mark      VARCHAR(50)     NOT NULL,
    level_identity_id   INT             NULL,

    -- Source identifiers (all nullable)
    revit_guid          VARCHAR(50)     NULL,
    rundown_key         VARCHAR(100)    NULL,
    etabs_id            VARCHAR(100)    NULL,

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
GO

CREATE INDEX IX_element_identity_project
    ON design.element_identity(project_number);
GO

-- Filtered unique index: one revit_guid per project (when not NULL)
CREATE UNIQUE INDEX UX_element_identity_revit_guid
    ON design.element_identity(project_number, revit_guid)
    WHERE revit_guid IS NOT NULL;
GO

----------------------------------------------------------------------
-- 3. design.rundown_uploads
-- Raw spreadsheet data before identity resolution
----------------------------------------------------------------------
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
GO

CREATE INDEX IX_rundown_uploads_batch
    ON design.rundown_uploads(upload_batch_id);
GO

CREATE INDEX IX_rundown_uploads_project
    ON design.rundown_uploads(project_number);
GO

----------------------------------------------------------------------
PRINT '004-create-identity-tables completed successfully.';
GO