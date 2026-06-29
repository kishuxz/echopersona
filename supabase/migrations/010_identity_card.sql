-- 010_identity_card.sql
-- Adds structured identity card to personas table.
-- identity_card captures WHO the persona IS (values, worldview, role_identity,
-- emotional_wiring, communication_style, life_philosophy) — distinct from
-- voice_card which captures HOW they speak.
-- Populated by Stage 4B at enrichment time (arq worker only, never on live path).
-- RLS: inherits existing USING (auth.uid() = user_id) policy on personas table.
-- Rollback: ALTER TABLE personas DROP COLUMN IF EXISTS identity_card;

ALTER TABLE personas
  ADD COLUMN IF NOT EXISTS identity_card JSONB NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN personas.identity_card IS
  'Stage 4B output: structured identity card with values[], worldview, role_identity, '
  'emotional_wiring, communication_style, life_philosophy. '
  'Used by Layer 1 of build_system_prompt in rag.py.';
