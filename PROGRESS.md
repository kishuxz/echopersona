# EchoPersona — Build Progress

## Active feature
Planning minimal frontend billing/upgrade UI (post Step 7 — all backend billing gates complete)

## Last completed step
Step 7 Slice F ✅ — Live-path billing entitlement gating (2026-06-17, `ec67319`)
- `backend/routers/ws.py` — `SESSION_ENTITLEMENT` dict; billing gate closes WebSocket 4002 before `accept()` if `can_use_chat` fails; per-turn `_voice_allowed` / `_video_allowed` require entitlement AND consent; Simli handler AND-gates `can_use_video` + consent; `SESSION_ENTITLEMENT.pop` in finally block
- Close codes: 4001=unauth, 4002=billing, 4003=consent, 4004=persona not found
- Persona sessions use persona owner's entitlement; freeform sessions use connecting user's entitlement
- `audio_end` unconditional — frontend never hangs on voice/video denial
- Simli gate: deny condition `(consent_blocks OR entitlement_blocks)` = AND semantics for allowing (both must pass)
- `backend/tests/test_ws_entitlements.py` — 15 new tests; 228 total passing

## Step 7 history (all ✅)

### Slice E — Billing status endpoint (2026-06-17, `251e51c`)
- `backend/models/entitlements.py` — added `BillingStatusResponse`
- `backend/routers/billing.py` — `GET /billing/status`: JWT required; free-tier defaults when no row exists
- 14 new tests; 213 total

### Slice D — Stripe webhook handler (2026-06-17, `08ef158`)
- `backend/services/stripe_webhooks.py` — `record_event_idempotent`, `handle_checkout_completed`, `handle_subscription_event`, `process_stripe_event`
- `backend/routers/billing.py` — `POST /billing/webhook`: signature verification, idempotency gate, event routing
- 23 new tests; 199 total

### Slice C — Stripe checkout route (2026-06-17, `3fff6b3`)
- `backend/services/billing.py` — `create_checkout_session`
- `backend/routers/billing.py` — `POST /billing/checkout`; `backend/main.py` — registered router
- 17 new tests; 176 total

### Slice B — Config, models, entitlement service (2026-06-17, `3c5ba8b`)
- `backend/config.py` — Stripe keys + price IDs + frontend redirect URLs
- `backend/models/entitlements.py` — `PlanTier`, `EntitlementStatus`, `StripeEntitlement`, `AccessDecision`
- `backend/services/entitlements.py` — access predicates (`can_use_chat`, `can_use_voice`, `can_use_video`)
- 32 new tests; 159 total

### Slice A — Billing migration (2026-06-17, `c21e4f1`)
- `backend/migrations/006_stripe_entitlements.sql` — `stripe_entitlements` + `stripe_webhook_events` tables, RLS, indexes
- `supabase/migrations/006_stripe_entitlements.sql` — identical copy for Supabase CLI

## Previous milestones
- Step 6 ✅ — Live-path listener/auth context (`c6d3b35`)
- Step 5b ✅ Full consent/succession vertical slice (spec §7.2, §7.3)
- Step 5a ✅ Self-review correction loop
- Step 4 ✅ Creation → ingestion handoff, provenance (Stage 0)
- Step 3 ✅ Answer evaluator + Groq RPM rate limiter
- Step 2 ✅ Creation state machine + capture
- Step 1 ✅ Question bank loader

## Current blocker
None.

## Next action
Plan minimal frontend billing/upgrade UI: subscription status display + checkout button wired to `POST /billing/checkout`. Read `docs/product-spec.md` and consult `product-architect` agent before building.

## Last known green verification
```bash
cd backend && python -m pytest tests/ -q
# 228 passed (all Step 7 slices green, 2026-06-17)
cd frontend && npx tsc --noEmit && npm run build
# typecheck clean; built in 1.10s
```

## Do not forget
- Migrations 004 and 005 are applied in Supabase SQL editor — do not re-run unless schema is reset.
- Migration 006 (`stripe_entitlements`) written but **not confirmed applied** — verify in Supabase SQL editor before testing billing in staging.
- `SESSION_LISTENER` and `SESSION_HISTORY` are not cleaned up on disconnect — known gap, defer to a future cleanup slice.
- `posthumous_verified` beneficiary activation is explicitly deferred — activation signal not yet wired.
- Tavus not yet wired in — see `docs/backlog.md`.
