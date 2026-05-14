-- ============================================================================
-- 002-create-management-tables.sql
-- Management schema: the RELATIONSHIP HUB linking all data sources
-- ============================================================================
-- management.project_meta is the stable anchor for the entire platform.
-- All design tables FK to project_meta via project_number.
-- dbo tables link here via trigger (dbo.Project INSERT → project_meta).
-- ============================================================================
-- Depends on: 001-create-schemas.sql
-- ============================================================================

USE [JAPBIMDB];
GO

----------------------------------------------------------------------
-- 1. project_meta — one row per project (stable across wipe-reload)
----------------------------------------------------------------------
IF NOT EXISTS (SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'management' AND TABLE_NAME = 'project_meta')
BEGIN
    CREATE TABLE management.project_meta (
        id              INT IDENTITY(1,1) PRIMARY KEY,
        project_number  VARCHAR(50)     NOT NULL,
        address         VARCHAR(255)    NULL,
        created_at      DATETIME2       NOT NULL DEFAULT GETUTCDATE(),
        updated_at      DATETIME2       NOT NULL DEFAULT GETUTCDATE(),

        CONSTRAINT UQ_project_meta_number UNIQUE (project_number)
    );

    CREATE INDEX IX_project_meta_number ON management.project_meta(project_number);
END;
GO

----------------------------------------------------------------------
-- 2. Trigger: auto-create project_meta when new Number appears in dbo.Project
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
-- 3. Seed: create project_meta rows for existing projects
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

PRINT '002-create-management-tables completed successfully.';
GO