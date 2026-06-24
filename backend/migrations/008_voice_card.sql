-- 008_voice_card.sql
-- Adds structured voice/speech style card to personas.
-- Extracted at Stage 4 enrichment time alongside style_exemplars.
ALTER TABLE personas ADD COLUMN IF NOT EXISTS voice_card JSONB DEFAULT '{}'::jsonb;
COMMENT ON COLUMN personas.voice_card IS
  'Structured speech style extracted at Stage 4 enrichment: catchphrases, address_terms, humor_style, sentence_rhythm, emotional_tone, advice_style, verbal_tics, formality';
