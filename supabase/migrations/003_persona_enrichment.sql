-- Migration 003: entity graph and style exemplars on personas
-- Run manually in Supabase SQL editor after 002_fidelity_columns.sql.

ALTER TABLE personas
    ADD COLUMN IF NOT EXISTS entity_graph     JSONB  NOT NULL DEFAULT '[]',
    ADD COLUMN IF NOT EXISTS style_exemplars  JSONB  NOT NULL DEFAULT '[]';

COMMENT ON COLUMN personas.entity_graph IS
    'Resolved entity graph from Stage 3: [{canonical, type, aliases, description}].';
COMMENT ON COLUMN personas.style_exemplars IS
    'Characteristic speech excerpts from Stage 4 for LLM style conditioning.';
