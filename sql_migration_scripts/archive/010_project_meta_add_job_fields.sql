-- Migration 010: Add job_name and designer to management.project_meta
-- These fields are extracted from spreadsheet uploads (IMPORT B38/B40).

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('management.project_meta') AND name = 'job_name'
)
BEGIN
    ALTER TABLE management.project_meta ADD job_name NVARCHAR(255) NULL;
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('management.project_meta') AND name = 'designer'
)
BEGIN
    ALTER TABLE management.project_meta ADD designer NVARCHAR(100) NULL;
END
GO
