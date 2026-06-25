-- Migration 007: Persona Memory Engine v1 — Slice A
-- Adds memory_category to memory_units.
-- Safe to re-run (ADD COLUMN IF NOT EXISTS guard).

ALTER TABLE memory_units
    ADD COLUMN IF NOT EXISTS memory_category TEXT NOT NULL DEFAULT 'episodic'
    CHECK (memory_category IN (
        'episodic','semantic','procedural','relational',
        'values','humor','advice'
    ));

COMMENT ON COLUMN memory_units.memory_category IS
    'Semantic type assigned by Stage 2. Enum: episodic|semantic|procedural|relational|values|humor|advice. Default: episodic.';

CREATE INDEX IF NOT EXISTS idx_memory_units_persona_category
    ON memory_units (persona_id, memory_category)
    WHERE supersedes IS NULL;
