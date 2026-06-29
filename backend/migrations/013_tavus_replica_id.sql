-- Slice 7: add Tavus replica_id per persona for video chat mode
-- tavus_replica_id: references a Tavus digital-twin replica created from the person's training video
-- NULL means video mode is unavailable for this persona

ALTER TABLE personas
    ADD COLUMN IF NOT EXISTS tavus_replica_id TEXT;
