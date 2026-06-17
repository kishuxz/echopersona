# EchoPersona — Build Progress

## Active feature
Step 7 — Entitlements and Stripe gating (planning)

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
Plan Step 7 using plan-feature skill — entitlements table, Stripe checkout, webhook handler, and access gating by plan tier.

## Last known green verification
```bash
cd backend && python -m pytest tests/ -q
# 127 passed (all slices green, 2026-06-17)
cd frontend && npx tsc --noEmit && npm run build
# typecheck clean; built in 1.10s
```

## Do not forget
- Migrations 004 and 005 are applied in Supabase SQL editor — do not re-run unless schema is reset.
- Stripe, Tavus not yet wired in — see `docs/backlog.md`.
- `SESSION_LISTENER` not cleaned up on disconnect (same gap as `SESSION_HISTORY`) — close in Step 7 or 8.
- `posthumous_verified` beneficiary activation is explicitly deferred — activation signal not yet wired.
