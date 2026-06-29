# EchoPersona — Build Progress

## Active feature
Slice 2 (Progressive Q&A) complete — next: Slice 3 (TBD)

## 2026-06-28 — Slice 2: Progressive Q&A ✅

Branch: `feat/slice-1-fidelity-fix` (extends same branch)

### What changed
- **`backend/data/question_bank.yaml`** — Expanded from 10 → 41 questions: 5 in origins, 4 each in family, coming_of_age (was 0), love, work, beliefs, texture, hardship, places, legacy. All questions follow §2.1 schema with intents, signals, and probes.
- **`backend/services/creation.py`** — `CreationSession` gains `answers_per_category: dict[str, int]`; `NextStep` gains `question_category: str | None`; `apply_action` increments category counter on advance and populates category in all NextStep variants; `start_session` includes category in initial NextStep.
- **`frontend/src/types/index.ts`** — `CreationSession` adds `answers_per_category: Record<string, number>`; `NextStep` adds `question_category: string | null`.
- **`frontend/src/components/CreationWizard.tsx`** — Category label + per-category answered count displayed; progress bar added; finish threshold raised from `>= 3` to `>= 30`; `TOTAL_QUESTIONS = 41`; `MIN_QUESTIONS_TO_FINISH = 30`; countdown hint shows how many more to unlock finish.
- **`backend/tests/test_progressive_qa.py`** (new) — 16 tests: bank size (>= 30), all categories have >= 2 questions, probe namespacing, no duplicate IDs, `answers_per_category` tracking, `question_category` in NextStep, done state, category ordering.

### Verification
```bash
cd backend && python -m pytest tests/ -q
# 398 passed, 5 warnings
```

### Next action
Slice 3: TBD

## 2026-06-28 — Slice 1: Persona Fidelity Fix ✅

Branch: `feat/slice-1-fidelity-fix` → PR to `main`

### What changed
- **`backend/services/rag.py`** — 6-layer prompt order enforced (listener context moved from last → Layer 3); affect-tagged memory block `[emotion, valence_label]`; `_valence_label` helper; `_affect_tag` inner function with newline-stripping + 40-char cap (prompt injection guard); in-character no-memory fallback replaces system-voice text; GROUNDING REMINDER added before RESPONSE RULES; affect-tag metadata note added to YOUR MEMORIES header; `valence` cast to `float()` before use; `affect` field now stored in `_units` from `build_index_from_units`
- **`backend/routers/ws.py`** — Readiness gate now checks `RAG_INDICES[persona_id]._units` presence; persona with live FAISS index no longer blocked by empty `stories` or non-`ready` status
- **`backend/tests/test_rag.py`** (new) — 25 tests: valence bucketing, affect tagging (all edge cases), 6-layer prompt order, no-memory fallback wording, `build_index_from_units` affect propagation
- **`backend/tests/test_ws_readiness.py`** (new) — 12 tests: readiness gate pass/block matrix
- **`backend/tests/test_listener.py`** — 1 test updated for new layer order

### Verification
```bash
cd backend && python -m pytest tests/ -q
# 382 passed, 5 warnings
```

### Pre-existing gaps flagged (tracked as future slices, not regressions)
- Fidelity gate does not block low-score units from indexing → Slice 5 (Fidelity Gate hardening)
- `resolved_entity_ids` per-unit back-link not implemented → Slice 4 (Listener Profiles)
- No cosine-similarity threshold for low-relevance retrievals → Slice 4

### Next action
Slice 2: Progressive Q&A (session-based, 15-20 questions per category, min 30 threshold)

## 2026-06-28 — Loop-engineering OS upgrade (gstack/kstack-style)

Status: scaffolding ready in `plan-loop-engineering-os` branch (seattle worktree). Implementation slice; no backend/frontend/migration code touched.

### Added
- Skills (`.claude/skills/<name>/SKILL.md`):
  - `start-session` — safe session opener (worktree, branch, dirty state, services, shell GROQ override)
  - `anti-loop-check` — 11-row preflight covering every known regression trigger
  - `pr-readiness` — 12-row GO/NO-GO before commit/PR; refuses AI co-author attribution
  - `browser-test` — manual-browser script for APJ voice + Tavus video loop, redacts tokens
  - `github-issue-triage` — fuzzy chat → clean issue; one concern per ticket
  - `ponytail-context` — detects Ponytail; enforces manual token policy when absent
- Agents (`.claude/agents/<name>.md`):
  - `ceo-office-hours` — product priority advisor, read-only
  - `cto` — architecture memos with allowed-files list, read-only
  - `browser-qa` — runs `/browser-test` and routes failures
  - `test-engineer` — test plan + mocks at service boundary
  - `release-manager` — GO/NO-GO + manual deploy steps; never SSH/VPC
  - `devex-reviewer` — recommends edits to runbook, anti-loop-check, `.env.example`
- GitHub workflow:
  - `.github/ISSUE_TEMPLATE/{bug,feature,quality,infra,security}.yml`
  - `.github/pull_request_template.md`
- CLAUDE.md sections appended: Source of truth (worktree rules), Token/Ponytail policy, Secrets policy, Command routing, Current project priority

### Worktree rule (now binding)
- Live app worktree: `/Users/kishorekumar/echopersona` on `main` — run `uvicorn` / `vite` / Docker here
- Planning/feature worktrees: `/Users/kishorekumar/conductor/workspaces/echopersona/<city>` — edit here, PR to `main`, then `git pull` in live worktree
- hanoi worktree no longer exists — treat any doc reference to it as stale
- `kstack` and `gstack-kishore`: reference-only

### Ponytail / token policy (in effect)
- Ponytail not installed today. `/ponytail-context` enforces manual hygiene (rg-before-Read, narrow ranges, summarised tool output, no env/log/token dumps, PROGRESS.md as durable memory). Auto-switches when Ponytail is installed.

### Anti-loop checklist (now in /anti-loop-check)
worktree → Redis Docker → Python imports (groq, elevenlabs, cartesia, sentence_transformers) → shell GROQ override → backend/.env key presence → ElevenLabs voice id not placeholder → VOICE_ALWAYS_ON → backend start command shape → frontend localhost target → no tokenized WS URL in staged diff → APJ enrichment reminder.

### Open item — live worktree diff (Slice 0)
`/Users/kishorekumar/echopersona` has 8 uncommitted product files (layered persona prompt with emotional-register detection + per-persona cache namespacing + Stage 4 secondary style-card). Plan recommends shipping this as its own branch `feat/persona-prompt-emotional-register` via PR before pulling the merged OS layer over. Not part of this slice.

### Next product milestone
APJ persona fidelity live test (P0) → Tavus/video path fix (P0).

## 2026-06-27 — Local audible voice loop baseline locked

Status: completed locally.

### Verified
- Local backend/frontend run from `/Users/kishorekumar/echopersona` (not hanoi/conductor worktree).
- Redis uses local Docker Redis (`redis://localhost:6379`).
- Python runtime has required voice/RAG dependencies: `groq`, `elevenlabs`, `cartesia`, `sentence_transformers`.
- Groq STT/LLM auth works with current local key (`GROQ_API_KEY` in `backend/.env`).
- `VOICE_ALWAYS_ON=true` in `backend/.env` enables local voice testing before Stripe entitlement production flow is complete.
- ElevenLabs uses a real valid voice ID (not `your_default_voice_id_here`); `ELEVENLABS_VOICE_ID` in `backend/.env`.
- APJ local voice test completed: user said "Hello"; APJ replied in chat and audible TTS played.
- `.env` path fix in `config.py`: changed from `".env"` (cwd-relative) to `Path(__file__).parent / ".env"` (always resolves correctly regardless of launch directory).
- Groq STT retry: `_transcribe_groq` now retries up to 3× on transient HTTP errors.
- RAG index build now wrapped in try/except — logs warning and continues without FAISS on failure.
- Diagnostic logs (`[TTS_CALL]`, `[TTS_WORKER]`, `[TTS_QUEUE]`, `[WS_AUDIO]`, `[AUDIO_PLAYBACK]`) removed after baseline confirmed.

### .claude OS update (same slice)
- Added agents: `debugger`; updated `deploy-vercel-reviewer`
- Added skills: `ai-quality-review`, `interrupted-session`, `investigate`, `memory-safety-review`, `persona-fidelity-review`, `vpc-deploy-check`
- `AGENTS.md` and `CLAUDE.md` updated with operating rules

### Regression guard
If local voice breaks again, check in this order:
1. Correct worktree: `/Users/kishorekumar/echopersona`
2. Redis local Docker healthy
3. Python env imports: `groq`, `elevenlabs`, `cartesia`, `sentence_transformers`
4. `backend/.env` has valid `GROQ_API_KEY` (not stale shell override)
5. `backend/.env` has valid `ELEVENLABS_VOICE_ID` (not placeholder)
6. `backend/.env` has `VOICE_ALWAYS_ON=true`
7. Backend started without stale shell env vars: `env -u GROQ_API_KEY -u ELEVENLABS_VOICE_ID python -m uvicorn main:app --port 8000 --reload`
8. Browser hard refresh (Cmd+Shift+R) — no `voice_not_found` / Groq 401 in console

See `docs/runbook.md` → **Local voice baseline — start order** for full steps.

### Tests after this slice
- `backend/tests/test_entitlements.py` — 45 tests pass
- `frontend/npx tsc --noEmit` — 0 errors

### Next priority
Tavus/video integration (persona reply includes video avatar). See `docs/backlog.md`.

## Step 10 — Persona Memory Engine v1 · Slice C: Persona Readiness Gate (2026-06-24)

### Slice C: readiness_status + processing gate
- **backend/migrations/009_persona_readiness.sql** (new) — adds `readiness_status TEXT CHECK (...)` to `personas`; backfills existing enriched/story personas to `ready`
- **supabase/migrations/009_persona_readiness.sql** (new) — identical copy
- **backend/models/persona.py** — adds `readiness_status`
- **backend/services/persona_store.py** — includes readiness in persona SELECTs and adds `update_readiness_status()`
- **backend/worker/tasks/ingestion.py** — marks personas `processing` when ingestion begins and `failed` on ingestion error
- **backend/worker/tasks/enrichment.py** — marks personas `ready` after Stage 4 completes and `failed` on enrichment error
- **backend/routers/persona.py** — adds `GET /persona/{id}/readiness`
- **backend/routers/ws.py** — soft-gates WebSocket sessions for unready personas without static stories
- **frontend/src/types/index.ts** — adds readiness types
- **frontend/src/lib/api.ts** — adds `getPersonaReadiness()`
- **frontend/src/pages/PersonaDetail.tsx** — polls readiness and shows processing UI before rendering `VoiceInterface`
- **backend/tests/test_persona_readiness.py** — adds readiness tests

### Verification
- Backend tests passing
- Frontend TypeScript clean
- Frontend production build clean

### Do not forget
- Migration 009 written but **NOT YET APPLIED** in Supabase SQL editor
- Before live testing, apply migrations 007, 008, and 009 in order if they are not already applied

## Step 10 — Persona Memory Engine v1 · Slice B: Voice Card Foundation (2026-06-24)

### Slice B: structured voice_card extraction + prompt conditioning
- **backend/migrations/008_voice_card.sql** (new) — adds `voice_card JSONB NOT NULL DEFAULT '{}'` to `personas`
- **supabase/migrations/008_voice_card.sql** (new) — identical copy
- **backend/services/ingestion/stage4.py** — Stage 4 now returns both `style_exemplars` and structured `voice_card` in the existing LLM call
- **backend/models/persona.py** — adds `voice_card`
- **backend/services/persona_store.py** — includes `voice_card` in persona SELECTs and adds `update_voice_card()`
- **backend/worker/tasks/enrichment.py** — persists extracted `voice_card` during enrichment
- **backend/services/rag.py** — system prompt now includes a `VOICE & STYLE` block before characteristic phrases
- **backend/tests/test_voice_card.py** — adds 12 tests for voice card extraction/coercion/prompt behavior

### Verification
- Backend tests passing
- Frontend TypeScript clean
- Frontend production build clean

### Do not forget
- Migration 008 written but **NOT YET APPLIED** in Supabase SQL editor
- Existing personas will have `voice_card = {}` until re-enriched

## Last completed step
Step 10 Slice A ✅ — Memory category foundation (2026-06-24)
- `backend/migrations/007_persona_memory_engine.sql` (new) — `memory_category TEXT CHECK (...)` on `memory_units`, `NOT NULL DEFAULT 'episodic'`; index on `(persona_id, memory_category) WHERE supersedes IS NULL`
- `supabase/migrations/007_persona_memory_engine.sql` (new) — identical copy
- `backend/models/memory_unit.py` — `MEMORY_CATEGORIES` frozenset exported; `memory_category: str = "episodic"` on `MemoryUnit` + `MemoryUnitCreate`
- `backend/services/ingestion/stage2.py` — 7-category system prompt; `_coerce_unit()` validates and defaults to `"episodic"` on any invalid/missing value; `_mock_unit()` includes `"episodic"`; zero extra Groq calls
- `backend/services/ingestion/source_store.py` — `memory_category` param added to `write_memory_unit()` INSERT
- `backend/worker/tasks/ingestion.py` — passes `unit_data.get("memory_category", "episodic")` to `write_memory_unit()`
- `backend/tests/test_memory_category.py` (new) — 15 tests: valid categories, invalid/missing/None fallbacks, mock unit, pipeline write
- Backend: 243 tests passing (228 prior + 15 new); TypeScript clean; build clean

## Step 10 ✅ — Guided question-led persona creation UI (2026-06-20)
- `frontend/src/components/CreationWizard.tsx` — guided interview; auto-finish on `action=done`; ref guard prevents double-finish race
- `frontend/src/pages/Dashboard.tsx` — 3-state `createStep` flow (`idle`→`shell`→`interview`)
- `frontend/src/lib/api.ts` — added `startCreationSession`, `captureTextAnswer`, `finishCreationSession`
- `frontend/src/types/index.ts` — added `CreationSession`, `StartSessionResponse`, `CaptureResponse`

## Hotfix ✅ — No-memory fallback in build_system_prompt (2026-06-24)
- `backend/services/rag.py` — `FALLBACK` directive injected when context empty; prevents blank-slate LLM improvisation

## Step 8E.2 ✅ — Structural frontend safety polish (2026-06-17)
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
None.

## Next action
Browser verification of full Guided Q&A → readiness gate flow (merged integration).

## Last known green verification
```bash
cd backend && python -m pytest tests/ -q
# TBD — post-merge run pending
cd frontend && npx tsc --noEmit && npm run build
# TBD — post-merge run pending
```

## Do not forget
- Migrations 004 and 005 are applied in Supabase SQL editor — do not re-run unless schema is reset.
- Migration 006 (`stripe_entitlements`) **confirmed applied** (2026-06-20).
- Migration 007 (`persona_style_card`) **confirmed applied** (2026-06-20) — `tone`, `avoid_phrases`, `answer_length_pref`, `relationship_tone` on `personas`.
- Migration 007 (`persona_memory_engine`) **confirmed applied** (2026-06-24) — `memory_category` on `memory_units`.
- Migration 008 (`voice_card`) **confirmed applied** (2026-06-24) — `voice_card JSONB` on `personas`.
- Migration 009 (`persona_readiness`) **confirmed applied** (2026-06-24) — `readiness_status` on `personas`.
- `SESSION_LISTENER` and `SESSION_HISTORY` are not cleaned up on disconnect — known gap, defer to a future cleanup slice.
- `posthumous_verified` beneficiary activation is explicitly deferred — activation signal not yet wired.
- Tavus not yet wired in — see `docs/backlog.md`.
