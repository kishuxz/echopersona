-- Migration 011: monetization tiers — answer_count, preservation_locks, persona_relationships
-- Run manually in the Supabase SQL editor. Guards throughout prevent re-run errors.

-- ── 1. answer_count on personas ──────────────────────────────────────────────
-- Counts captured Q&A answers; gating thresholds: 30=chat, 60=voice, 90=video.
-- Backfill via migration 012 or runbook; enforcement is flag-gated (ENFORCE_ANSWER_QUOTAS).
ALTER TABLE personas
  ADD COLUMN IF NOT EXISTS answer_count INT NOT NULL DEFAULT 0;

-- ── 2. Widen plan_tier CHECK on stripe_entitlements ──────────────────────────
ALTER TABLE stripe_entitlements
  DROP CONSTRAINT IF EXISTS stripe_entitlements_plan_tier_check;

ALTER TABLE stripe_entitlements
  ADD CONSTRAINT stripe_entitlements_plan_tier_check
    CHECK (plan_tier IN ('free', 'creator', 'legacy', 'preservation'));

-- One-time Preservation payment reference (no subscription for this tier).
ALTER TABLE stripe_entitlements
  ADD COLUMN IF NOT EXISTS stripe_payment_intent_id TEXT;

-- ── 3. preservation_locks ────────────────────────────────────────────────────
-- One row per permanently locked persona. Created on Preservation payment success;
-- never deleted even if the entitlement row changes later.
CREATE TABLE IF NOT EXISTS preservation_locks (
  id                       UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  persona_id               UUID        NOT NULL
                             REFERENCES personas(id) ON DELETE RESTRICT,
  user_id                  UUID        NOT NULL
                             REFERENCES auth.users(id) ON DELETE RESTRICT,
  stripe_payment_intent_id TEXT        NOT NULL,
  locked_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
  -- tier the subject held at purchase time; determines family limit post-activation
  tier_at_lock             TEXT        NOT NULL
                             CHECK (tier_at_lock IN ('free', 'creator', 'legacy')),
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_preservation_locks_persona UNIQUE (persona_id)
);

ALTER TABLE preservation_locks ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS preservation_locks_select ON preservation_locks;
CREATE POLICY preservation_locks_select ON preservation_locks FOR SELECT
  USING (auth.uid() = user_id);

-- ── 4. persona_relationships ─────────────────────────────────────────────────
-- Family member registry. Limit enforcement (0/3/unlimited per tier) is done in Python.
CREATE TABLE IF NOT EXISTS persona_relationships (
  id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  persona_id      UUID        NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
  member_user_id  UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  relationship    TEXT        NOT NULL DEFAULT '',
  granted_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT uq_persona_relationships_pair UNIQUE (persona_id, member_user_id)
);

CREATE INDEX IF NOT EXISTS idx_persona_relationships_persona
  ON persona_relationships (persona_id);

ALTER TABLE persona_relationships ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS persona_relationships_select ON persona_relationships;
CREATE POLICY persona_relationships_select ON persona_relationships FOR SELECT
  USING (
    auth.uid() = member_user_id
    OR auth.uid() IN (SELECT user_id FROM personas WHERE id = persona_id)
  );
