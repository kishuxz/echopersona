# EchoPersona — Build Progress

## Active feature
Build step 5b — Consent + succession capture (spec §7.2, §7.3)

## Last completed
Build step 5a — Self-review correction loop (`backend/tests/test_correction_loop.py` green)

Previous milestones:
- Step 4 ✅ Creation → ingestion handoff, provenance (Stage 0), `source_type` + `supersedes`
- Step 3 ✅ Answer evaluator + Groq RPM rate limiter
- Step 2 ✅ Creation state machine + capture (31 tests green)
- Step 1 ✅ Question bank loader

## Current blocker
Migration `backend/migrations/004_creation_fields.sql` must be run manually in Supabase SQL editor
before exercising the live creation endpoint. Idempotent — safe to re-run.

## Next action
Implement consent record capture (spec §7.2) and succession / beneficiary intent (spec §7.3).
Follow data contract in `docs/product-spec.md` §2.4–2.5. Add migration for consent + succession tables.

## Last known green verification
```bash
cd backend && python -m pytest tests/ -q
```

## Do not forget
- Run `backend/migrations/004_creation_fields.sql` in Supabase SQL editor (adds `persona_id`,
  `source_question_id`, `source_type`, `supersedes`, `captured_at`, `media_ref` to memory_units).
- Stripe, Tavus not yet wired in — see `docs/backlog.md`.
- Build steps 6 (live-path additions) and 7 (resonance) follow step 5.
