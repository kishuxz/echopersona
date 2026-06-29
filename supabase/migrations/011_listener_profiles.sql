-- 011_listener_profiles.sql
-- Slice 4: Listener Profiles + entity back-links on memory_units
--
-- 1. resolved_entity_ids TEXT[] on memory_units
--    Stage 3 writes these back after entity resolution so the live path
--    can filter by entity node without traversing the entity_graph at query time.
--
-- 2. persona_relationships table
--    Maps a listener's user_id to a canonical entity node in persona.entity_graph.
--    Populated by the persona owner via API (future) or manually.
--    Used by §9.3 listener-aware retrieval to bias toward units involving the listener.
--
-- Rollback:
--   DROP TABLE IF EXISTS persona_relationships;
--   ALTER TABLE memory_units DROP COLUMN IF EXISTS resolved_entity_ids;

ALTER TABLE memory_units
  ADD COLUMN IF NOT EXISTS resolved_entity_ids TEXT[] NOT NULL DEFAULT '{}';

COMMENT ON COLUMN memory_units.resolved_entity_ids IS
  'Stage 3 output: canonical entity names from persona.entity_graph that this unit '
  'mentions. Used by §9.3 listener-aware retrieval.';

CREATE INDEX IF NOT EXISTS idx_memory_units_resolved_entities
  ON memory_units USING gin(resolved_entity_ids);

-- ── persona_relationships ─────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS persona_relationships (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  persona_id       UUID NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
  listener_user_id UUID NOT NULL,
  entity_canonical TEXT NOT NULL,
  relationship     TEXT NOT NULL,
  address_term     TEXT NOT NULL DEFAULT '',
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (persona_id, listener_user_id)
);

COMMENT ON TABLE persona_relationships IS
  'Maps a listener user_id to a canonical entity node in persona.entity_graph. '
  'Used by §9.3 listener-aware retrieval. RLS: owner manages, listener reads own row.';

ALTER TABLE persona_relationships ENABLE ROW LEVEL SECURITY;

CREATE POLICY "owner_manage_relationships"
  ON persona_relationships
  FOR ALL
  USING (
    persona_id IN (SELECT id FROM personas WHERE user_id = auth.uid())
  );

CREATE POLICY "listener_read_own_relationship"
  ON persona_relationships
  FOR SELECT
  USING (listener_user_id = auth.uid());
