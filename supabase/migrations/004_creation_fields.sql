-- Migration 004: add creation-flow provenance fields
-- Run manually in Supabase SQL editor.
-- Safe to re-run (IF NOT EXISTS / DEFAULT guards).

-- memory_sources: new columns for §2.3 [add-004] provenance fields
ALTER TABLE memory_sources
  ADD COLUMN IF NOT EXISTS source_question_id text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS source_type        text NOT NULL DEFAULT 'answer',
  ADD COLUMN IF NOT EXISTS media_ref          text NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS captured_at        timestamptz;

-- memory_units: versioning + supersedes for §6/§7.1 correction loop
ALTER TABLE memory_units
  ADD COLUMN IF NOT EXISTS version    int  NOT NULL DEFAULT 1,
  ADD COLUMN IF NOT EXISTS supersedes uuid REFERENCES memory_units(unit_id);

-- Index for fast lookup of non-superseded units per persona (live retrieval)
CREATE INDEX IF NOT EXISTS idx_memory_units_persona_supersedes
  ON memory_units (persona_id, supersedes)
  WHERE supersedes IS NULL;
