-- Migration 009: Create design.rundown_transfers table + drop transfers_json column
--
-- design.rundown_transfers stores the engineer's transfer definitions
-- (source element, target level, [percent]) independently of computed results.
-- This replaces the transfers_json column on design.rundown.

-- 1. Create the new table
IF NOT EXISTS (
    SELECT 1 FROM sys.tables t
    JOIN sys.schemas s ON t.schema_id = s.schema_id
    WHERE s.name = 'design' AND t.name = 'rundown_transfers'
)
BEGIN
    CREATE TABLE design.rundown_transfers (
        id              INT IDENTITY(1,1) PRIMARY KEY,
        project_number  VARCHAR(50)  NOT NULL,
        target_element  VARCHAR(100) NOT NULL,
        source_element  VARCHAR(100) NOT NULL,
        target_level    VARCHAR(50)  NOT NULL,
        [percent]         DECIMAL(5,4) NOT NULL,
        created_by      VARCHAR(20)  NOT NULL DEFAULT 'user',
        created_at      DATETIME2    NOT NULL DEFAULT GETUTCDATE(),
        updated_at      DATETIME2    NOT NULL DEFAULT GETUTCDATE(),
        CONSTRAINT FK_rundown_transfers_project
            FOREIGN KEY (project_number)
            REFERENCES management.project_meta(project_number),
        CONSTRAINT CK_rundown_transfers_[percent]
            CHECK ([percent] > 0 AND [percent] <= 2.0)
    );

    CREATE INDEX IX_rundown_transfers_project_target
        ON design.rundown_transfers (project_number, target_element);

    CREATE INDEX IX_rundown_transfers_project_source
        ON design.rundown_transfers (project_number, source_element);
END
GO

-- 2. Drop the old transfers_json column from design.rundown
IF EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('design.rundown') AND name = 'transfers_json'
)
BEGIN
    ALTER TABLE design.rundown DROP COLUMN transfers_json;
END
GO