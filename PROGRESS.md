# EchoPersona — Build Progress

## Active feature
Step 9B — Deployment reconciliation: private VPS Docker Compose at kishoreai.online (correcting stale Render+Vercel config from Step 9).

## Last completed step
Step 8E.2 ✅ — Structural frontend safety polish (2026-06-17)
- `frontend/src/components/ErrorBoundary.tsx` — new class component; `getDerivedStateFromError` sets hasError; renders "Something went wrong" fallback with Reload button (`window.location.href = '/'`); no sensitive data logged
- `frontend/src/main.tsx` — `<ErrorBoundary>` wraps `<RouterProvider>`; prevents blank-screen crashes in production
- `frontend/src/components/ProtectedRoute.tsx` — unauthenticated redirect now passes `state: { returnTo: location.pathname }` so the original URL survives the login round-trip
- `frontend/src/pages/AuthPage.tsx` — reads `location.state.returnTo` on mount; login and email-confirmation redirect both navigate to `returnTo` (default `/dashboard`); signup flow unaffected
- `frontend/src/App.tsx` — deleted (confirmed zero imports via grep)
- TypeScript: clean; build: clean (`npm run build` succeeded, 2026-06-17)

## Step 8E.1 ✅ — Final frontend polish mini-slice (2026-06-17)
- `frontend/src/components/LatencyDashboard.tsx` — Total metric card now uses `total_ms` (was incorrectly using `tts_first_audio_ms`)
- `frontend/src/pages/Dashboard.tsx` — Billing link always visible (removed `hidden sm:block`); main content padding `px-4 sm:px-8` for better mobile layout
- `frontend/src/pages/LandingPage.tsx` — Privacy and Terms footer links changed from `href="#"` to `/privacy` and `/terms`; pricing CTAs softened from "Coming soon" → "Launching soon"
- `frontend/src/router.tsx` — Added `/privacy` and `/terms` placeholder routes; replaced silent catch-all redirect with a proper 404 page (NotFoundPage component with "Go home" / "Go back" actions)
- TypeScript: clean; build: clean (`npm run build` succeeded, 2026-06-17)

## Step 8 Slice B ✅ — Persona creation and upload UX polish (2026-06-17)
- `frontend/src/components/PersonaUpload.tsx` — cleared pre-filled demo defaults (name/traits/style/stories now start empty); hard validation blocks submit on empty name (<2 chars) or all-empty stories with inline error; `avatarError` state surfaces photo upload failures inline (was silent console.error); section hints updated ("Required —" prefix on stories, "Quiet room, natural speech —" on voice); Simli Face ID hint upgraded to a clickable `<a>` link
- `frontend/src/pages/Dashboard.tsx` — `handlePersonaCreated` now navigates to `/dashboard/persona/:id` after creation; cancel button styled with underline + hover color
- TypeScript: clean; build: clean (`npm run build` succeeded, 2026-06-17)

## Step 8 Slice A ✅ — Landing page and dashboard polish (2026-06-17)
- `frontend/src/pages/LandingPage.tsx` — stats grid responsive (`grid-cols-1 sm:grid-cols-3`); border-r gated on `sm:` breakpoint; added 3-tier pricing section (Free / Creator / Legacy) between speed section and CTA; footer Dashboard link is now auth-aware (guests see "Sign In"); added Privacy · Terms stub links; footer nav wraps on mobile
- `frontend/src/pages/Dashboard.tsx` — `displayName` now reads `user.user_metadata.full_name` with email-slug fallback; `handleDelete` now prompts for confirmation and surfaces API errors; header right-side buttons use `gap-3` and "Billing & Plan" label shortened to "Billing" and hidden on xs via `sm:block`
- TypeScript: clean; build: clean (`npm run build` succeeded, 2026-06-17)

## Step 7 last completed step
Step 7 Slice G ✅ — Minimal frontend billing and upgrade UI (2026-06-17)
- `frontend/src/types/index.ts` — added `BillingStatus` interface
- `frontend/src/lib/api.ts` — added `getBillingStatus()` (GET /billing/status) and `startCheckout()` (POST /billing/checkout; redirects internally, price IDs never exposed to frontend)
- `frontend/src/pages/BillingPage.tsx` — new page at `/dashboard/billing`; shows plan tier pill, status, Chat/Voice/Video access pills, renewal/cancellation date; upgrade buttons rendered per tier order (free→both, creator→legacy only, legacy→none); two independent error states (fatal load error vs. inline checkout error)
- `frontend/src/router.tsx` — added protected `/dashboard/billing` route
- `frontend/src/pages/Dashboard.tsx` — added "Billing & Plan" nav button in header
- TypeScript: clean (`npx tsc --noEmit` 0 errors); build: clean (`npm run build` succeeded)

### Slice F — Live-path billing entitlement gating (2026-06-17, `ec67319`)
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
None. Stage 4 persona style-card extraction and write-back complete (2026-06-20). Next: Step 9B production deployment verification (`kishoreai.online` Docker Compose).

## Next action
Step 9B.1 done — docs/config reconciled to private VPC Docker. Next: fix docker-compose.yml build arg defaults (CORS_ORIGINS, VITE_API_BASE_URL, VITE_WS_BASE_URL) for production; then SSH to VPS, write production .env, `docker compose up --build -d`, verify `https://kishoreai.online/health`.

## Last known green verification
```bash
cd backend && python -m pytest tests/ -q
# 228 passed (all Step 7 slices green, 2026-06-17)
cd frontend && npx tsc --noEmit && npm run build
# typecheck clean; built in 1.06s (Step 8 Slice B, 2026-06-17)
```

## Do not forget
- Migrations 004 and 005 are applied in Supabase SQL editor — do not re-run unless schema is reset.
- Migration 006 (`stripe_entitlements`) **confirmed applied** (2026-06-20) — `stripe_entitlements` table present in Supabase project `acngivwdqttgtalopsjw`.
- Migration 007 (`persona_style_card`) **confirmed applied and verified** (2026-06-20) — four columns confirmed on `personas`: `tone TEXT NOT NULL DEFAULT ''`, `avoid_phrases TEXT[] NOT NULL DEFAULT '{}'`, `answer_length_pref TEXT NOT NULL DEFAULT 'moderate'`, `relationship_tone JSONB NOT NULL DEFAULT '{}'`. Stage 4 extraction and write-back **complete** (2026-06-20) — 25/25 tests pass.
- `SESSION_LISTENER` and `SESSION_HISTORY` are not cleaned up on disconnect — known gap, defer to a future cleanup slice.
- `posthumous_verified` beneficiary activation is explicitly deferred — activation signal not yet wired.
- Tavus not yet wired in — see `docs/backlog.md`.
