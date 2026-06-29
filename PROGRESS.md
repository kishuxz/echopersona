# EchoPersona — Build Progress

## Active feature
Slice 10 (Email + Invite Flow) complete. Next: Slice 11 — Admin Panel.

## 2026-06-29 — Slice 10: Email + Invite Flow ✅

Branch: `slice-10-email-invite-flow`

### What changed
- **`backend/migrations/014_persona_invites.sql`** + **`supabase/migrations/014_persona_invites.sql`**
  - New `persona_invites` table: token (plain text, UNIQUE), status CHECK, 7-day expires_at, single-use via accepted_at, RLS (owner only)
  - `persona_relationships.invite_id` back-reference added (idempotent ALTER)
  - Migration confirmed applied in Supabase
- **`backend/models/invite.py`** — `InviteCreate`, `InviteRecord`, `AcceptInviteRequest`, `AcceptInviteResponse` Pydantic models
- **`backend/services/email.py`** — async Resend REST wrapper (`httpx`); three functions: `send_invite_email`, `send_readiness_notification`, `send_acceptance_confirmation`; RESEND_API_KEY absent → logs warning, returns False (never raises)
- **`backend/services/invite_store.py`** — `create_invite`, `get_invites_for_persona`, `get_invite_by_id`, `get_invite_by_token`, `revoke_invite`, `accept_invite`, `count_accepted_members`; token is `secrets.token_urlsafe(32)` stored raw; expiry and single-use checked in Python
- **`backend/routers/invites.py`** — four endpoints: `POST /invites/{persona_id}` (201), `GET /invites/{persona_id}`, `DELETE /invites/{invite_id}`, `POST /invites/accept`; entitlement gate at both creation and acceptance via `can_add_family_member`; acceptance uses `db.auth.admin.get_user_by_id` to resolve owner email for confirmation
- **`backend/worker/tasks/email.py`** — `send_readiness_emails` arq task: fans out readiness notifications to all linked family members via admin API email lookup
- **`backend/config.py`** — `RESEND_API_KEY`, `RESEND_FROM_ADDRESS` settings added
- **`backend/.env.example`** — Resend vars documented
- **`backend/main.py`** — `invites` router registered
- **`backend/worker/__init__.py`** — `send_readiness_emails` added to `WorkerSettings.functions`
- **`backend/worker/tasks/enrichment.py`** — `await ctx["redis"].enqueue_job("send_readiness_emails", persona_id)` added after readiness_status=ready; guarded with `if ctx.get("redis")` so standalone/test runs are unaffected
- **`backend/tests/test_invite_flow.py`** — 25 tests, all passing

### Test results
`525 passed, 0 failed` (up from 500 before this slice)

### Operational notes
- `RESEND_FROM_ADDRESS` must be a verified sender domain in the Resend dashboard before emails will deliver
- `RESEND_API_KEY` absent → all emails silently skipped (safe for dev/test)
- Invitee must be a logged-in Supabase user before accepting (JWT required on `/invites/accept`); frontend should redirect unauthenticated users to login with `returnTo=/invite/accept?token=...`
- Token expiry enforced in Python; expired rows remain in DB (no cron cleanup — acceptable for v1, noted in backlog)

## 2026-06-29 — Slice 9: Tavus Video Mode ✅

Branch: `porto`

### What changed
- **`backend/services/tavus.py`**
  - Bug 1 fixed: URL field `download_url` → `result.get("stream_url") or result.get("hosted_url", "")` (Tavus v2 API)
  - Bug 2 fixed: primary failure status `"failed"` (was `"error"`); `"error"` kept as a deprecated defensive fallback with `logger.warning`
  - Bug 3 fixed: `_POLL_TIMEOUT` 30s → 90s (Tavus typical generation: 20–60s)
  - Mock mode guard added: `settings.mock_mode` returns `"https://example.com/mock-tavus-video.mp4"` after 2s sleep, no HTTP call
  - Empty `replica_id` guard: returns `None` immediately (was already handled but moved before `tavus_api_key` check for clarity)
  - `video_name` added to submit payload for traceability: `f"echo-{session_id[:8]}"` or `"echopersona"`
  - `session_id: str | None = None` optional param added to `generate_tavus_video`
- **`backend/routers/ws.py`** (narrow change only)
  - `_tts_active = mode in ("voice", "video")` → `_tts_active = mode == "voice"`: suppresses ElevenLabs/Cartesia TTS in video mode so user does not hear the reply twice (Tavus video has embedded audio)
  - `_send_tavus()` closure passes `session_id=session_id` to `generate_tavus_video`
- **`backend/tests/test_tavus.py`** (new) — 6 tests covering: submit failure, poll→ready (stream_url), poll→failed, timeout, mock mode, empty replica_id
- **`frontend/src/components/VoiceInterface.tsx`** (narrow change only)
  - Added `negotiatedModeRef = useRef<ChatMode>(initialMode)` — mirrors `negotiatedMode` state so `onmessage` closure reads the live value
  - `negotiatedModeRef.current = negotiated` written in `MODE_NEGOTIATED` handler alongside `setNegotiatedMode`
  - `TRANSCRIPT` handler: `setVideoLoading(true)` now guarded by `negotiatedModeRef.current === "video"` (was firing in all modes)
  - `AUDIO_END` handler: `setVideoLoading(false)` added as safety reset when mode is not video

### Quality gates
- pytest: 500 passed, 0 failures (`python -m pytest tests/ -q`)
- tsc: clean (`npx tsc --noEmit`)
- No new env vars. No new migrations. No secrets printed.

### Latency impact
- Stage: Video
- Before: video generation often returned None (wrong URL field — download_url never present in Tavus v2)
- After: stream_url / hosted_url correctly extracted; URL validation guard unchanged
- TTS in video mode: suppressed (was firing concurrently with Tavus — double audio bug)
- Measurement: observe `video_ready` WS message after reply; confirm no `audio_chunk` events arrive in video mode

### Do not forget
- `TAVUS_API_KEY` required in production `.env`; `tavus_replica_id` must be set per persona in Supabase before video mode activates
- Browser test: connect in video mode → send text → confirm no TTS audio plays → confirm `video_ready` message arrives with an https URL

## 2026-06-29 — Browser QA + Threshold Rescale ✅

### Q&A unlock thresholds (canonical — follow these exactly)
| Threshold | Old | New | Unlocks |
|---|---|---|---|
| Text chat | 30 | **10** | Owner text-chat preview |
| Voice chat | 60 | **20** | Voice clone + voice chat |
| Video chat | 90 | **30** | Video chat + rich retrieval |

**Why:** Question bank has 41 questions; old thresholds (30/60/90) were physically unreachable for testing and impractical for early users. Bank will grow with meaningful questions over time. For testing, 10/20/30 lets you verify all modes without answering 90 questions.

### Files changed
- `backend/services/entitlements.py` — `FREE_QUESTION_LIMIT=10`, `VOICE_QUESTION_THRESHOLD=20`, `VIDEO_QUESTION_THRESHOLD=30`
- `frontend/src/components/CreationWizard.tsx` — `MIN_QUESTIONS_TO_FINISH=10`
- `frontend/src/components/VoiceInterface.tsx` — "Voice: Default" → "Voice: Not configured" (Slice 8 invariant fix)
- `backend/tests/test_progressive_qa.py` — bank size assertion updated to `>= 10`

### Browser QA findings (Slices 1–8)
- Slices 1, 5, 6, 7: PASS
- Slice 2: PASS (after threshold rescale)
- Slice 3: backend PASS; voice_card/style_card not surfaced in PersonaDetail UI (cosmetic, tracked in backlog)
- Slice 4: backend PASS; no family-member management UI (functional gap, tracked in backlog)
- Slice 8: PASS (after "Voice: Not configured" label fix)
- STT → TTS → audio path: needs interactive browser test with live mic + ready persona (pending)

## 2026-06-29 — Slice 8: Cloned Voice Only Gate ✅

Branch: `slice-8-cloned-voice-only`

### What changed
- **`backend/services/entitlements.py`** — `can_use_voice`: moved `voice_id` falsy check BEFORE `voice_always_on` early return. The no-stock-voice rule is a product-integrity invariant, not a billing rule — `voice_always_on` (dev billing bypass) must not override it.
- **`backend/services/tts.py`** — `tts_audio_chunks`: raises `ValueError("voice_id is required — stock voice fallback is disabled")` at top of function before any I/O or mock path. Removed `voice_id or settings.elevenlabs_voice_id` fallback.
- **`backend/services/tts_cartesia.py`** — `tts_audio_chunks_cartesia`: same guard at top. Removed `_DEFAULT_VOICE` constant and `voice_id or settings.cartesia_voice_id or _DEFAULT_VOICE` fallback. `vid = voice_id` (no fallback).
- **`backend/tests/test_cloned_voice_gate.py`** (new) — 14 tests: `TestClonedVoiceGate` (can_use_voice gate with/without voice_id across all plan tiers and `voice_always_on` flag) + `TestTTSGuard` (ElevenLabs and Cartesia raise ValueError on null/empty voice_id)

### Existing gate (already in place from Slice 7, no change)
- `ws.py:585-594` — connection-time negotiation already correctly downgrades to text + `"voice_not_configured"` reason when `persona.voice_id` is null. Slice 8 hardens the downstream paths as defense-in-depth.

### Quality gates
- pytest: 494 passed, 0 failures; /media-latency-review: PASS; /anti-loop-check: GO

### Do not forget
- Slice 9: Tavus Video Mode — `media-pipeline-engineer`; `tavus_replica_id` must be set per persona before video mode activates
- `TAVUS_API_KEY` required in production `.env`

## 2026-06-28 — Slice 7: Three Chat Modes ✅

Branch: `slice-7-three-chat-modes`

### What changed
- **`backend/migrations/013_tavus_replica_id.sql`** (new) + `supabase/migrations/013_tavus_replica_id.sql` (new)
  - `tavus_replica_id TEXT` column on `personas`; applied via Supabase MCP 2026-06-28
- **`backend/config.py`** — `tavus_api_key` field added (reads `TAVUS_API_KEY`)
- **`backend/models/persona.py`** — `tavus_replica_id: str | None = None` added
- **`backend/routers/ws.py`**
  - `SESSION_MODE: dict[str, Literal["text", "voice", "video"]]` added
  - `_negotiate_mode(requested, voice_allowed, video_allowed)` — pure function, testable in isolation
  - `_run_reply_core(user_text, mode, websocket, session_id)` — extracted from near-duplicate `_run_turn_inner`/`_run_text_turn`; both become thin wrappers
  - `mode_negotiated` message sent immediately after `websocket.accept()`
  - Tavus video tail fires after `audio_end` in video mode (async `create_task`, non-blocking)
  - Dev bypass (`_run_text_turn`) caps at voice — never triggers video mode
  - D-ID silent failure fixed — now sends `video_error` to client on exception
  - `finally` block: background tasks cancelled on disconnect; `SESSION_HISTORY` cleaned up (pre-existing leak fixed)
- **`backend/services/tavus.py`** (new) — async Tavus video submit + poll; `https://` URL validation; `asyncio.get_running_loop()`; 30s timeout; returns URL or None
- **`backend/.env.example`** — `TAVUS_API_KEY=` documented
- **`frontend/src/lib/api.ts`** — `buildWsUrl` gains optional `mode?: ChatMode` param (URI-encoded)
- **`frontend/src/components/VoiceInterface.tsx`** — mode picker (text/voice/video), `mode_negotiated` handler, conditional mic/text/video UI, `video_ready`/`video_error` handlers, downgrade notice
- **`frontend/src/types/index.ts`** — `ChatMode`, `ModeNegotiatedMessage`, `VideoReadyMessage`, `VideoErrorMessage` types added
- **`frontend/src/constants.ts`** — `MODE_NEGOTIATED`, `VIDEO_ERROR` added to `WS_SERVER_MSG`
- **`backend/tests/test_ws_mode_negotiation.py`** (new) — 15 tests for `_negotiate_mode` pure function

### Quality gates
- pytest: 480 passed, 0 failures; tsc: clean; /media-latency-review: PASS; /qa-security: PASS WITH NOTES (all FAIL items patched)

### Do not forget
- `TAVUS_API_KEY` must be set in production `.env`
- Set `tavus_replica_id` per persona in the DB once a Tavus replica is created: `UPDATE personas SET tavus_replica_id = 'r_...' WHERE id = '...'`
- Slice 8: Cloned Voice Only gate — enforce that voice mode silently downgrades to text when `elevenlabs_voice_id` is null (no stock voices, no fallback)

## 2026-06-28 — Slice 6: Preservation Tier ✅

Branch: `slice-6-preservation-tier`

### What changed
- **`backend/migrations/012_preservation.sql`** (new) + `supabase/migrations/012_preservation.sql` (new)
  - `persona_preservation`: one-time purchase record per persona; UNIQUE on `persona_id`; RLS subject-read-only
  - `posthumous_access_subscriptions`: recurring subscription per (persona, family subscriber); UNIQUE on `(persona_id, subscriber_user_id)`; RLS subscriber-read-only; `updated_at` trigger
  - **Applied via Supabase MCP 2026-06-28** (version `20260629062603`)
- **`backend/models/preservation.py`** (new) — `PersonaPreservation`, `PosthumousAccessSubscription` Pydantic models
- **`backend/services/preservation.py`** (new) — DB queries + access predicates (`can_access_preserved_persona`, `can_access_posthumous`)
- **`backend/config.py`** — added `STRIPE_PRICE_POSTHUMOUS_MONTHLY`; merged `ENFORCE_ANSWER_QUOTAS` from Slice 5
- **`backend/services/billing.py`** — `create_checkout_session` uses `mode` + `extra_metadata` params
- **`backend/services/stripe_webhooks.py`** — four new handlers; `process_stripe_event` routes by `session.mode` and `metadata.purchase_type`
- **`backend/models/entitlements.py`** — `BillingStatusResponse` gains `can_use_posthumous_chat`; merged `family_member_limit`, `is_preservation_locked`, `PersonaAccessDecision` from Slice 5
- **`backend/routers/billing.py`** — three new endpoints: `POST /billing/checkout/preservation`, `POST /billing/checkout/posthumous`, `GET /billing/preservation/{persona_id}`
- **`backend/tests/test_preservation.py`** (new) — 37 tests; 465 total passing

## 2026-06-28 — Slice 5: Monetization Tiers ✅

Branch: `slice-5-continuation` → PR to `main`

### What changed
- **`backend/migrations/012_monetization_tiers.sql`** (new) — `answer_count` on `personas`; `preservation` plan tier; `stripe_payment_intent_id` on `stripe_entitlements`; `preservation_locks` table; `persona_relationships` table
- **`backend/config.py`** — `STRIPE_PRICE_PRESERVATION_ONETIME`, `ENFORCE_ANSWER_QUOTAS`
- **`backend/models/entitlements.py`** — `PlanTier` adds `"preservation"`; new fields; `PersonaAccessDecision`
- **`backend/services/entitlements.py`** — answer quota thresholds; `can_add_family_member`; `family_member_limit_for_tier`; sentinel pattern for voice_id
- **`backend/routers/billing.py`** — preservation in `CheckoutRequest`; `GET /billing/persona/{persona_id}/access`
- **`backend/routers/ws.py`** — billing gate passes `answer_count` + `is_owner` + `voice_id`
- **Frontend** — `BillingStatus` + `PersonaAccess` types; `startCheckout` + `getPersonaAccess`; preservation badge

### Quality gates
- pytest: 408 passed, 0 failures; /stripe-webhook-review: PASS; /supabase-rls-review: PASS

### Do not forget
- `ENFORCE_ANSWER_QUOTAS=true` must NOT be set until answer_count backfill is confirmed
- `persona_relationships` INSERT policy needed when Slice 10 (invite flow) ships


## 2026-06-28 — Slice 4: Listener Profiles + Entity Back-links + Retrieval Score Threshold ✅

Branch: `doha`

### What changed
- **`backend/migrations/011_listener_profiles.sql`** (new) + `supabase/migrations/011_listener_profiles.sql` (new)
  - `resolved_entity_ids TEXT[] NOT NULL DEFAULT '{}'` on `memory_units`; GIN index
  - `persona_relationships` table: maps `(persona_id, listener_user_id)` → `(entity_canonical, relationship, address_term)`; RLS: owner-manage + listener-read-own
  - Migration applied via Supabase MCP 2026-06-28
- **`backend/services/ingestion/stage3.py`** — `resolve_unit_entity_ids()`: maps unit raw entity mentions to canonical names using alias lookups; returns `{unit_id: [canonical, ...]}` for enrichment.py to write back
- **`backend/services/ingestion/source_store.py`** — `update_unit_resolved_entities()` writes Stage 3 back-links; `get_persona_relationship()` fetches entity canonical for a listener
- **`backend/worker/tasks/enrichment.py`** — after Stage 3, calls `resolve_unit_entity_ids` + `update_unit_resolved_entities` for every unit with matches
- **`backend/models/consent.py`** — `ListenerContext` gains `entity_canonical: str | None = None` (§9.3 — from `persona_relationships`)
- **`backend/services/listener.py`** — immediate-beneficiary path now queries `persona_relationships` via passed `db` and sets `entity_canonical` on `ListenerContext`
- **`backend/services/rag.py`**
  - `_SCORE_THRESHOLD = 0.25` (§9.7 confidence floor — units below are dropped, triggering no-memory fallback)
  - `_ENTITY_BOOST = 0.15` (§9.3 — score bonus for units whose `resolved_entity_ids` includes the listener's entity)
  - `build_index_from_units` stores `resolved_entity_ids` per unit in `_units`
  - `retrieve(query, top_k, listener_entity)` — fetches 3× candidates, applies entity boost, filters by threshold
- **`backend/routers/ws.py`** — both retrieve call sites pass `listener_entity=listener_ctx.entity_canonical` (None-safe)
- **`backend/tests/test_listener_profiles.py`** (new) — 19 tests: alias resolution, entity boost, threshold constants
- **`backend/tests/test_listener.py`** — updated for entity_canonical

### Pre-existing gaps (tracked, not fixed here)
- No API endpoint to register `persona_relationships` rows yet — table seeded manually for now

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
Slice 11: Admin Panel — rag-persona-engineer (router) + frontend-react-engineer.

## Last known green verification
```bash
cd backend && python -m pytest tests/ -q
# 525 passed, 5 warnings (2026-06-29, Slice 10)
```

## Do not forget
- Migrations 004 and 005 are applied in Supabase SQL editor — do not re-run unless schema is reset.
- Migration 006 (`stripe_entitlements`) **confirmed applied** (2026-06-20).
- Migration 007 (`persona_style_card`) **confirmed applied** (2026-06-20) — `tone`, `avoid_phrases`, `answer_length_pref`, `relationship_tone` on `personas`.
- Migration 007 (`persona_memory_engine`) **confirmed applied** (2026-06-24) — `memory_category` on `memory_units`.
- Migration 008 (`voice_card`) **confirmed applied** (2026-06-24) — `voice_card JSONB` on `personas`.
- Migration 009 (`persona_readiness`) **confirmed applied** (2026-06-24) — `readiness_status` on `personas`.
- Migration 010 (`identity_card`) applied manually in Supabase SQL editor.
- Migration 011 (`listener_profiles`) **applied via Supabase MCP** (2026-06-28) — `resolved_entity_ids` on `memory_units`, `persona_relationships` table.
- Migration 014 (`persona_invites`) **applied via Supabase MCP** (2026-06-29) — `persona_invites` table, `invite_id` on `persona_relationships`.
- `SESSION_LISTENER` and `SESSION_HISTORY` are not cleaned up on disconnect — known gap, defer to a future cleanup slice.
- `posthumous_verified` beneficiary activation is explicitly deferred — activation signal not yet wired.
- `persona_relationships` rows must be seeded manually (no API endpoint yet) — future Admin UI or API slice.
- Tavus not yet wired in — see `docs/backlog.md`.
