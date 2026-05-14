-- ============================================================================
-- 001-create-schemas.sql
-- Create design and management schemas
-- ============================================================================
-- Prerequisites: production JAPBIMDB with dbo tables already present
-- ============================================================================

USE [JAPBIMDB];
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'design')
    EXEC('CREATE SCHEMA design');
GO

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'management')
    EXEC('CREATE SCHEMA management');
GO

PRINT '001-create-schemas completed successfully.';
GO