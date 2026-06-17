# EchoPersona — Build Progress

## Active feature
Step 6 — Live-path listener/auth context (in progress)

## Completed slices this step
- Slice 1 ✅ `ListenerContext` model added to `backend/models/consent.py`
- Slice 2 ✅ `services/listener.py` — `resolve_listener_context` + `get_active_consent_for_persona`; 10 new tests
- Slice 3 ✅ `services/persona_store.py` — `get_persona_by_id` (no owner filter, post-auth use only)

## Remaining slices
- Slice 4: `services/rag.py` — add `listener_ctx` param to `build_system_prompt`
- Slice 5: `routers/ws.py` — wire auth, SESSION_LISTENER, modality gating
- Slice 6: additional ws integration tests

## Last completed step
Step 5b ✅ — Full consent/succession vertical slice (spec §7.2, §7.3)
- Migration 005 applied in Supabase SQL editor
- RLS enabled on consent + succession tables
- Backend models, services, routes, tests (112 passed)
- Frontend: `ConsentPage.tsx`, route, nav link, API client, TypeScript types
- Frontend typecheck clean; production build passes
- Pushed to main (`cdd857f`)

Previous milestones:
- Step 5a ✅ Self-review correction loop
- Step 4 ✅ Creation → ingestion handoff, provenance (Stage 0), `source_type` + `supersedes`
- Step 3 ✅ Answer evaluator + Groq RPM rate limiter
- Step 2 ✅ Creation state machine + capture (31 tests green)
- Step 1 ✅ Question bank loader

## Current blocker
None.

## Next action
Slice 4: update `build_system_prompt` in `services/rag.py` to accept `listener_ctx`.

## Last known green verification
```bash
cd backend && python -m pytest tests/ -q
# 122 passed (10 new listener tests)
```

## Do not forget
- Migrations 004 and 005 are applied in Supabase SQL editor — do not re-run unless schema is reset.
- Stripe, Tavus not yet wired in — see `docs/backlog.md`.
- Build step 7 (resonance) follows step 6.
