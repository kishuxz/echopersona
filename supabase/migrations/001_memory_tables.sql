-- Migration 001: memory_sources and memory_units tables
-- Run manually in Supabase SQL editor (Dashboard → SQL Editor → New query).

-- ─── memory_sources ──────────────────────────────────────────────────────────
-- Stores raw ingestion items before pipeline processing.
-- status: pending → processing → stage0_complete → done | error

CREATE TABLE IF NOT EXISTS memory_sources (
    id                UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           UUID        NOT NULL,
    persona_id        UUID        NOT NULL,
    modality          TEXT        NOT NULL,                 -- text|video|audio|document|photo|letter
    question_category TEXT        NOT NULL DEFAULT '',
    question_text     TEXT        NOT NULL DEFAULT '',
    group_name        TEXT        NOT NULL DEFAULT '',
    file_id           TEXT        NOT NULL DEFAULT '',      -- Supabase Storage path
    text_content      TEXT        NOT NULL DEFAULT '',      -- original text for text modality
    raw_text          TEXT        NOT NULL DEFAULT '',      -- Stage 0 output
    timestamp_range   FLOAT4[]    NOT NULL DEFAULT '{0,0}', -- [start_s, end_s] for media
    status            TEXT        NOT NULL DEFAULT 'pending',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE memory_sources ENABLE ROW LEVEL SECURITY;

CREATE POLICY "owner read-write" ON memory_sources
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

CREATE INDEX IF NOT EXISTS memory_sources_user_id_idx   ON memory_sources (user_id);
CREATE INDEX IF NOT EXISTS memory_sources_persona_id_idx ON memory_sources (persona_id);
CREATE INDEX IF NOT EXISTS memory_sources_status_idx    ON memory_sources (status);

-- ─── memory_units ────────────────────────────────────────────────────────────
-- Finished persona-conditioned memory units ready for FAISS indexing.
-- Populated by Stages 1-4 of the ingestion pipeline.

CREATE TABLE IF NOT EXISTS memory_units (
    unit_id             UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID        NOT NULL,
    persona_id          UUID        NOT NULL,
    source_id           UUID        REFERENCES memory_sources(id) ON DELETE SET NULL,
    source              JSONB       NOT NULL DEFAULT '{}',
    content_first_person TEXT       NOT NULL DEFAULT '',
    stance              TEXT        NOT NULL DEFAULT '',
    affect              JSONB       NOT NULL DEFAULT '{"emotion":"","valence":0,"intensity":0}',
    themes              TEXT[]      NOT NULL DEFAULT '{}',
    entities            JSONB       NOT NULL DEFAULT '{"people":[],"places":[],"period":""}',
    verified            BOOLEAN     NOT NULL DEFAULT false,
    embedding           FLOAT4[]    NOT NULL DEFAULT '{}', -- sentence-transformers vector (384-dim)
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE memory_units ENABLE ROW LEVEL SECURITY;

CREATE POLICY "owner read-write" ON memory_units
    USING (user_id = auth.uid())
    WITH CHECK (user_id = auth.uid());

CREATE INDEX IF NOT EXISTS memory_units_user_id_idx    ON memory_units (user_id);
CREATE INDEX IF NOT EXISTS memory_units_persona_id_idx ON memory_units (persona_id);
CREATE INDEX IF NOT EXISTS memory_units_verified_idx   ON memory_units (verified);
