-- Migration 011: Add beam_weights_detail to design.tributary_results
-- Stores comma-separated individual beam kN contributions per element per level.
-- e.g. "80.5,49.8" => two beams contributing 80.5 and 49.8 kN respectively.
-- Total beam weight = SUM of parsed values. No separate total column (derived on read).

ALTER TABLE design.tributary_results
    ADD beam_weights_detail NVARCHAR(500) NULL;
