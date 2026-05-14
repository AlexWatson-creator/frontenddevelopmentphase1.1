-- Migration 008: Add rebar override tracking columns to design.rundown
-- These BIT columns track which rebar fields have been manually overridden
-- by the engineer (vs auto-computed by the rundown engine).

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('design.rundown') AND name = 'qty_override'
)
BEGIN
    ALTER TABLE design.rundown ADD qty_override BIT NOT NULL DEFAULT 0;
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('design.rundown') AND name = 'n_bars_override'
)
BEGIN
    ALTER TABLE design.rundown ADD n_bars_override BIT NOT NULL DEFAULT 0;
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('design.rundown') AND name = 'c_bars_override'
)
BEGIN
    ALTER TABLE design.rundown ADD c_bars_override BIT NOT NULL DEFAULT 0;
END
GO