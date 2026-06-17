-- Migration 005: consent_records + succession_records (build step 5b)
-- Run manually in Supabase SQL editor. Safe to re-run (IF NOT EXISTS guards on tables/indexes).

-- ─── consent_records ───────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS consent_records (
  id                    uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  persona_id            uuid        NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
  subject_user_id       uuid        NOT NULL,
  captured_at           timestamptz NOT NULL DEFAULT now(),
  status                text        NOT NULL DEFAULT 'active'
                                    CHECK (status IN ('active', 'superseded', 'revoked')),
  ended_at              timestamptz,
  supersedes            uuid        REFERENCES consent_records(id),
  consent_version       int         NOT NULL DEFAULT 1,
  policy_version        text        NOT NULL DEFAULT '1',
  modality_consent      jsonb       NOT NULL DEFAULT
                                      '{"voice_clone":false,"video_avatar":false,"text_twin":true}',
  rights                jsonb       NOT NULL DEFAULT
                                      '{"subject_may_delete":true,"subject_may_review":true}',
  affirmation_media_ref text
);

-- Enforce at most one active row per (persona, subject)
CREATE UNIQUE INDEX IF NOT EXISTS idx_consent_records_one_active
  ON consent_records (persona_id, subject_user_id)
  WHERE status = 'active';

-- ─── succession_records ────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS succession_records (
  id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  persona_id      uuid        NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
  subject_user_id uuid        NOT NULL,
  captured_at     timestamptz NOT NULL DEFAULT now(),
  status          text        NOT NULL DEFAULT 'active'
                              CHECK (status IN ('active', 'superseded', 'revoked')),
  ended_at        timestamptz,
  supersedes      uuid        REFERENCES succession_records(id),
  beneficiaries   jsonb       NOT NULL DEFAULT '[]'
);

-- Enforce at most one active row per (persona, subject)
CREATE UNIQUE INDEX IF NOT EXISTS idx_succession_records_one_active
  ON succession_records (persona_id, subject_user_id)
  WHERE status = 'active';

-- ─── RLS ───────────────────────────────────────────────────────────────────────

ALTER TABLE consent_records    ENABLE ROW LEVEL SECURITY;
ALTER TABLE succession_records ENABLE ROW LEVEL SECURITY;

-- consent_records policies

DROP POLICY IF EXISTS consent_select ON consent_records;
CREATE POLICY consent_select ON consent_records FOR SELECT
  USING (
    subject_user_id = auth.uid()
    AND EXISTS (
      SELECT 1 FROM personas
      WHERE personas.id      = consent_records.persona_id
        AND personas.user_id = auth.uid()
    )
  );

DROP POLICY IF EXISTS consent_insert ON consent_records;
CREATE POLICY consent_insert ON consent_records FOR INSERT
  WITH CHECK (
    subject_user_id = auth.uid()
    AND EXISTS (
      SELECT 1 FROM personas
      WHERE personas.id      = consent_records.persona_id
        AND personas.user_id = auth.uid()
    )
  );

DROP POLICY IF EXISTS consent_update ON consent_records;
CREATE POLICY consent_update ON consent_records FOR UPDATE
  USING (
    subject_user_id = auth.uid()
    AND EXISTS (
      SELECT 1 FROM personas
      WHERE personas.id      = consent_records.persona_id
        AND personas.user_id = auth.uid()
    )
  )
  WITH CHECK (
    subject_user_id = auth.uid()
    AND EXISTS (
      SELECT 1 FROM personas
      WHERE personas.id      = consent_records.persona_id
        AND personas.user_id = auth.uid()
    )
  );

-- No DELETE policy → DELETE is denied by default when RLS is enabled.

-- succession_records policies

DROP POLICY IF EXISTS succession_select ON succession_records;
CREATE POLICY succession_select ON succession_records FOR SELECT
  USING (
    subject_user_id = auth.uid()
    AND EXISTS (
      SELECT 1 FROM personas
      WHERE personas.id      = succession_records.persona_id
        AND personas.user_id = auth.uid()
    )
  );

DROP POLICY IF EXISTS succession_insert ON succession_records;
CREATE POLICY succession_insert ON succession_records FOR INSERT
  WITH CHECK (
    subject_user_id = auth.uid()
    AND EXISTS (
      SELECT 1 FROM personas
      WHERE personas.id      = succession_records.persona_id
        AND personas.user_id = auth.uid()
    )
  );

DROP POLICY IF EXISTS succession_update ON succession_records;
CREATE POLICY succession_update ON succession_records FOR UPDATE
  USING (
    subject_user_id = auth.uid()
    AND EXISTS (
      SELECT 1 FROM personas
      WHERE personas.id      = succession_records.persona_id
        AND personas.user_id = auth.uid()
    )
  )
  WITH CHECK (
    subject_user_id = auth.uid()
    AND EXISTS (
      SELECT 1 FROM personas
      WHERE personas.id      = succession_records.persona_id
        AND personas.user_id = auth.uid()
    )
  );
