-- Migration 002: add fidelity columns to memory_units
-- Run manually in Supabase SQL editor after 001_memory_tables.sql.

ALTER TABLE memory_units
    ADD COLUMN IF NOT EXISTS fidelity_flags JSONB    NOT NULL DEFAULT '[]',
    ADD COLUMN IF NOT EXISTS fidelity_score FLOAT4   NOT NULL DEFAULT 1.0;

COMMENT ON COLUMN memory_units.fidelity_flags IS
    'Array of {flagged_text, reason} objects from the fidelity verification pass.';
COMMENT ON COLUMN memory_units.fidelity_score IS
    '0.0 = completely fabricated, 1.0 = perfectly faithful to source.';

-- Index for finding units that need family review (flagged or low score)
CREATE INDEX IF NOT EXISTS memory_units_fidelity_score_idx
    ON memory_units (fidelity_score)
    WHERE fidelity_score < 0.9 OR verified = false;
