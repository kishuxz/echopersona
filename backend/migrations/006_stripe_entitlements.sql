-- Migration 006: stripe_entitlements + stripe_webhook_events (build step 7 — billing)
-- Run manually in Supabase SQL editor. Safe to re-run (IF NOT EXISTS guards on tables/indexes).

-- ─── stripe_entitlements ────────────────────────────────────────────────────────
-- Single source of truth for a user's billing tier and subscription state.
-- Written exclusively by the Stripe webhook handler (service-role key, bypasses RLS).
-- Read by API routes to gate feature access.

CREATE TABLE IF NOT EXISTS stripe_entitlements (
  id                      uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id                 uuid        NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  stripe_customer_id      text        NOT NULL,
  stripe_subscription_id  text,
  plan_tier               text        NOT NULL DEFAULT 'free'
                                      CHECK (plan_tier IN ('free', 'creator', 'legacy')),
  status                  text        NOT NULL DEFAULT 'active'
                                      CHECK (status IN ('active', 'trialing', 'past_due', 'canceled', 'unpaid')),
  cancel_at_period_end    boolean     NOT NULL DEFAULT false,
  current_period_end      timestamptz,
  created_at              timestamptz NOT NULL DEFAULT now(),
  updated_at              timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_stripe_entitlements_user UNIQUE (user_id)
);

-- Webhook lookup by Stripe customer/subscription ID
CREATE INDEX IF NOT EXISTS idx_stripe_entitlements_customer
  ON stripe_entitlements (stripe_customer_id);

CREATE INDEX IF NOT EXISTS idx_stripe_entitlements_subscription
  ON stripe_entitlements (stripe_subscription_id)
  WHERE stripe_subscription_id IS NOT NULL;

-- Auto-update updated_at (reuses the handle_updated_at() function from initial schema)
CREATE OR REPLACE TRIGGER stripe_entitlements_updated_at
  BEFORE UPDATE ON stripe_entitlements
  FOR EACH ROW EXECUTE PROCEDURE handle_updated_at();

-- ─── stripe_webhook_events ──────────────────────────────────────────────────────
-- Idempotency log. Before processing any webhook event, attempt an INSERT here.
-- The UNIQUE constraint on stripe_event_id causes a conflict on duplicate delivery,
-- which the handler uses as the signal to skip re-processing.

CREATE TABLE IF NOT EXISTS stripe_webhook_events (
  id              uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  stripe_event_id text        NOT NULL,
  event_type      text        NOT NULL,
  processed_at    timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_stripe_webhook_events_event UNIQUE (stripe_event_id)
);

-- ─── RLS ────────────────────────────────────────────────────────────────────────

ALTER TABLE stripe_entitlements   ENABLE ROW LEVEL SECURITY;
ALTER TABLE stripe_webhook_events ENABLE ROW LEVEL SECURITY;

-- stripe_entitlements: each user can read their own row.
-- All writes use the service-role key (bypasses RLS) via the webhook handler.

DROP POLICY IF EXISTS entitlements_select ON stripe_entitlements;
CREATE POLICY entitlements_select ON stripe_entitlements FOR SELECT
  USING (auth.uid() = user_id);

-- No INSERT/UPDATE/DELETE policies → denied for anon/authenticated roles.
-- Only the service-role key (backend) may mutate this table.

-- stripe_webhook_events: no user-facing access; service role only.
-- RLS enabled with no permissive policies = full deny for non-service roles.
