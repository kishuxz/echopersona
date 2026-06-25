-- Migration 007: Persona Style Card columns
-- Adds structured style card fields to the personas table.
-- Safe ALTER TABLE with NOT NULL defaults — no backfill required.
-- Stage 4 populates these fields for new/re-enriched personas.

ALTER TABLE personas
    ADD COLUMN IF NOT EXISTS tone               TEXT     NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS avoid_phrases      TEXT[]   NOT NULL DEFAULT '{}',
    ADD COLUMN IF NOT EXISTS answer_length_pref TEXT     NOT NULL DEFAULT 'moderate',
    ADD COLUMN IF NOT EXISTS relationship_tone  JSONB    NOT NULL DEFAULT '{}';
