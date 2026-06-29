-- 012_preservation.sql
-- Preservation Tier: one-time purchase locks persona storage permanently.
-- Posthumous access: family members pay a recurring subscription for live chat
-- after the subject passes.
--
-- Two new tables; stripe_entitlements is NOT changed.

-- ── persona_preservation ──────────────────────────────────────────────────────
-- One row per persona. Created when a one-time preservation payment succeeds.
-- Service role writes only; subjects may read their own row.

CREATE TABLE persona_preservation (
  id                          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  persona_id                  uuid        NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
  subject_user_id             uuid        NOT NULL REFERENCES auth.users(id),
  stripe_customer_id          text        NOT NULL,
  stripe_payment_intent_id    text        UNIQUE,
  stripe_checkout_session_id  text,
  status                      text        NOT NULL DEFAULT 'paid'
                              CHECK (status IN ('paid', 'refunded')),
  paid_at                     timestamptz NOT NULL DEFAULT now(),
  created_at                  timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_persona_preservation UNIQUE (persona_id)
);

ALTER TABLE persona_preservation ENABLE ROW LEVEL SECURITY;

CREATE POLICY "subject reads own persona_preservation"
  ON persona_preservation FOR SELECT
  USING (auth.uid() = subject_user_id);

CREATE INDEX idx_persona_preservation_persona_id ON persona_preservation (persona_id);
CREATE INDEX idx_persona_preservation_subject    ON persona_preservation (subject_user_id);


-- ── posthumous_access_subscriptions ──────────────────────────────────────────
-- One row per (persona, family-member subscriber). Updated by Stripe webhook
-- on subscription lifecycle events.

CREATE TABLE posthumous_access_subscriptions (
  id                      uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  persona_id              uuid        NOT NULL REFERENCES personas(id) ON DELETE CASCADE,
  subscriber_user_id      uuid        NOT NULL REFERENCES auth.users(id),
  stripe_customer_id      text        NOT NULL,
  stripe_subscription_id  text        UNIQUE,
  status                  text        NOT NULL DEFAULT 'active'
                          CHECK (status IN ('active', 'trialing', 'past_due', 'canceled', 'unpaid')),
  current_period_end      timestamptz,
  cancel_at_period_end    boolean     NOT NULL DEFAULT false,
  created_at              timestamptz NOT NULL DEFAULT now(),
  updated_at              timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_posthumous_per_persona_subscriber UNIQUE (persona_id, subscriber_user_id)
);

ALTER TABLE posthumous_access_subscriptions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "subscriber reads own posthumous_access_subscriptions"
  ON posthumous_access_subscriptions FOR SELECT
  USING (auth.uid() = subscriber_user_id);

CREATE INDEX idx_posthumous_persona_id   ON posthumous_access_subscriptions (persona_id);
CREATE INDEX idx_posthumous_subscriber   ON posthumous_access_subscriptions (subscriber_user_id);
CREATE INDEX idx_posthumous_sub_id       ON posthumous_access_subscriptions (stripe_subscription_id);

-- updated_at auto-trigger
CREATE OR REPLACE FUNCTION handle_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$;

CREATE TRIGGER set_posthumous_updated_at
  BEFORE UPDATE ON posthumous_access_subscriptions
  FOR EACH ROW EXECUTE FUNCTION handle_updated_at();
