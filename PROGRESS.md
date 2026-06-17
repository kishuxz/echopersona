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
Migration `backend/migrations/005_consent_succession.sql` must be run manually in Supabase SQL editor
before building the consent/succession service layer. Idempotent — safe to re-run.

## Next action
Implement `backend/services/consent.py`, `backend/routers/consent.py`, and
`backend/tests/test_consent.py` (spec §7.2, §7.3, §2.4–2.5).

## Completed this session
- `backend/models/consent.py` ✅ — `ModalityConsent`, `ConsentRights`, `ConsentCreate`,
  `ConsentRecord`, `SuccessionBeneficiary`, `SuccessionCreate`, `SuccessionRecord`
- `backend/services/consent.py` ✅ — `ensure_persona_owner`, `get_active_consent_record`,
  `write_consent_record`, `get_active_succession_record`, `write_succession_record`

## Last known green verification
```bash
cd backend && python -m pytest tests/ -q
```

## Do not forget
- Run `backend/migrations/004_creation_fields.sql` in Supabase SQL editor (adds `persona_id`,
  `source_question_id`, `source_type`, `supersedes`, `captured_at`, `media_ref` to memory_units).
- Run `backend/migrations/005_consent_succession.sql` in Supabase SQL editor (adds `consent_records`
  and `succession_records` tables with append-only semantics, unique-active indexes, and RLS).
- Stripe, Tavus not yet wired in — see `docs/backlog.md`.
- Build steps 6 (live-path additions) and 7 (resonance) follow step 5.
