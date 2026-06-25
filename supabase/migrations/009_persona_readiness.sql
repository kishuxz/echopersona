-- 009_persona_readiness.sql
-- Adds readiness_status to gate live chat until memory ingestion completes.
-- Run manually in Supabase SQL editor.
ALTER TABLE personas
  ADD COLUMN IF NOT EXISTS readiness_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (readiness_status IN ('pending', 'processing', 'ready', 'failed'));

COMMENT ON COLUMN personas.readiness_status IS
  'Pipeline gate: pending=no ingestion queued, processing=ingestion running, ready=enrichment complete, failed=error';

-- Backfill: existing personas with enrichment done or stories are immediately ready
UPDATE personas
  SET readiness_status = 'ready'
  WHERE entity_graph != '[]'::jsonb
    OR (stories IS NOT NULL AND array_length(stories, 1) > 0);
