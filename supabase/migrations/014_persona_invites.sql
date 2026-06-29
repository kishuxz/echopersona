-- 014_persona_invites.sql
-- Creates persona_invites table for the email magic-link invite flow.
-- Adds invite_id back-reference column to persona_relationships.

CREATE TABLE IF NOT EXISTS persona_invites (
    id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    persona_id       UUID        NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
    invited_by       UUID        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    email            TEXT        NOT NULL,
    relationship     TEXT        NOT NULL DEFAULT '',
    entity_canonical TEXT        NOT NULL DEFAULT '',
    address_term     TEXT        NOT NULL DEFAULT '',
    token            TEXT        NOT NULL UNIQUE,
    status           TEXT        NOT NULL DEFAULT 'pending'
                                 CHECK (status IN ('pending', 'accepted', 'revoked')),
    expires_at       TIMESTAMPTZ NOT NULL DEFAULT now() + INTERVAL '7 days',
    accepted_at      TIMESTAMPTZ,
    listener_user_id UUID        REFERENCES auth.users(id) ON DELETE SET NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_persona_invite_email UNIQUE (persona_id, email)
);

ALTER TABLE persona_invites ENABLE ROW LEVEL SECURITY;

-- Persona owner can read and manage their persona's invites
CREATE POLICY persona_invites_owner ON persona_invites
    USING  (persona_id IN (SELECT id FROM personas WHERE user_id = auth.uid()))
    WITH CHECK (persona_id IN (SELECT id FROM personas WHERE user_id = auth.uid()));

-- Add invite back-reference to persona_relationships (idempotent)
ALTER TABLE persona_relationships
    ADD COLUMN IF NOT EXISTS invite_id UUID REFERENCES persona_invites(id) ON DELETE SET NULL;
