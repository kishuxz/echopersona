# EchoPersona — Build Progress

## Active feature
Step 7 — Entitlements and Stripe gating (Slice F done — WebSocket entitlement gating)

## Step 7 Slice F ✅ — WebSocket entitlement gating (2026-06-17)
- `backend/routers/ws.py` — added `SESSION_ENTITLEMENT` dict; hoisted `db = get_db()` before consent block; billing gate (4002 close, chat check, `can_use_chat`) added before `websocket.accept()`; per-turn `_voice_allowed` / `_video_allowed` now AND entitlement + consent; Simli handler checks `can_use_video(entitlement)` alongside consent; `SESSION_ENTITLEMENT.pop` in finally block
- Close codes: 4001=unauth, 4002=billing, 4003=consent, 4004=persona not found
- Persona owner's entitlement checked for persona sessions; connecting user's for freeform
- `audio_end` remains unconditional — frontend never hangs on voice/video denial
- Simli gate verified: deny condition `(consent_blocks OR entitlement_blocks)` = AND semantics for allowing (both must pass)
- `backend/tests/test_ws_entitlements.py` — 15 new tests; 228 total passing

## Step 7 Slice E ✅ — Billing status endpoint (2026-06-17)
- `backend/models/entitlements.py` — added `BillingStatusResponse` (plan_tier, status, access flags, period_end; no Stripe IDs)
- `backend/routers/billing.py` — `GET /billing/status`: JWT required; reads `stripe_entitlements` only (no Stripe API calls); free-tier defaults when no row exists
- `backend/tests/test_billing_status.py` — 14 new tests; 213 total passing

## Step 7 Slice D ✅ — Stripe webhook handler (2026-06-17)
- `backend/services/stripe_webhooks.py` — `record_event_idempotent`, `handle_checkout_completed`, `handle_subscription_event`, `process_stripe_event`; price→tier mapping; status→EntitlementStatus mapping; unknown price/user handled safely
- `backend/routers/billing.py` — `POST /billing/webhook`: signature verification (400 on failure), idempotency gate (200 on duplicate), event routing
- `backend/tests/test_stripe_webhooks.py` — 23 new tests (route + service layer); 199 total passing

## Step 7 Slice C ✅ — Stripe checkout route (2026-06-17)
- `backend/services/billing.py` — `create_checkout_session`: get-or-create Stripe customer, create subscription checkout session
- `backend/routers/billing.py` — `POST /billing/checkout`: auth required; maps plan_tier to price ID from config; rejects unknown tiers (422) and missing price config (500)
- `backend/main.py` — registered `billing.router`
- `backend/tests/test_billing_checkout.py` — 17 new tests (route + service layer); 176 total passing

## Step 7 Slice B ✅ — Config, models, entitlement service (2026-06-17)
- `backend/config.py` — added `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_CREATOR_MONTHLY`, `STRIPE_PRICE_LEGACY_MONTHLY`, `FRONTEND_BILLING_SUCCESS_URL`, `FRONTEND_BILLING_CANCEL_URL`
- `backend/requirements.txt` — added `stripe>=8.0.0`
- `backend/models/entitlements.py` — `PlanTier`, `EntitlementStatus`, `StripeEntitlement`, `EntitlementUpsert`, `AccessDecision`
- `backend/services/entitlements.py` — `get_entitlement_for_user`, `get_entitlement_by_customer_or_subscription`, `upsert_entitlement_from_subscription`, `can_use_chat`, `can_use_voice`, `can_use_video`
- `backend/tests/test_entitlements.py` — 32 new tests; 159 total passing

## Step 7 Slice A ✅ — Billing migration (2026-06-17)
- `backend/migrations/006_stripe_entitlements.sql` — `stripe_entitlements` table (tier, status, Stripe IDs, period end) + `stripe_webhook_events` table (idempotency log) + RLS + indexes
- `supabase/migrations/006_stripe_entitlements.sql` — identical copy for Supabase CLI
- **Not yet applied** — run in Supabase SQL editor before Slice C (webhook handler)

## Last completed step
Step 6 ✅ — Live-path listener/auth context (spec §8.1.2, §9.3)
- `ListenerContext` model added to `backend/models/consent.py`
- `services/listener.py` — `resolve_listener_context` + `get_active_consent_for_persona`
- `services/persona_store.py` — `get_persona_by_id` (no owner filter, post-auth use only)
- `services/rag.py` — `build_system_prompt` accepts `listener_ctx`; listener block injected for non-owner beneficiaries only
- `routers/ws.py` — listener auth gate, SESSION_LISTENER, per-turn voice/video modality gating
- 127 backend tests passing; frontend typecheck clean; production build passes
- Pushed to main (`c6d3b35`)

Previous milestones:
- Step 5b ✅ Full consent/succession vertical slice (spec §7.2, §7.3)
- Step 5a ✅ Self-review correction loop
- Step 4 ✅ Creation → ingestion handoff, provenance (Stage 0), `source_type` + `supersedes`
- Step 3 ✅ Answer evaluator + Groq RPM rate limiter
- Step 2 ✅ Creation state machine + capture (31 tests green)
- Step 1 ✅ Question bank loader

## Current blocker
None.

## Next action
Step 7 complete. Next: frontend billing UI (checkout button, status display) or Step 8 (TBD).

## Last known green verification
```bash
cd backend && python -m pytest tests/ -q
# 228 passed (all slices green, 2026-06-17)
cd frontend && npx tsc --noEmit && npm run build
# typecheck clean; built in 1.10s
```

## Do not forget
- Migrations 004 and 005 are applied in Supabase SQL editor — do not re-run unless schema is reset.
- Migration 006 is written but not yet applied — run before Slice C.
- Tavus not yet wired in — see `docs/backlog.md`.
- `SESSION_LISTENER` not cleaned up on disconnect (same gap as `SESSION_HISTORY`) — close in Step 7 Slice D.
- `posthumous_verified` beneficiary activation is explicitly deferred — activation signal not yet wired.
