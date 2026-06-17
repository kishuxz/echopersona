---
name: predeploy-check
description: Full pre-deploy checklist before any push to main or deploy trigger. Covers tests, types, build, env vars, and security basics.
---

## When to use
Before any push to `main` or manual deploy trigger on Render / Vercel.

## Checklist

### Code correctness
- [ ] `cd backend && python -m pytest tests/ -q` — all tests pass
- [ ] `cd frontend && npx tsc --noEmit` — no TypeScript errors
- [ ] `cd frontend && npm run build` — production build succeeds

### Security
- [ ] No `.env` files staged (`git status` check)
- [ ] No secrets hardcoded in any file (`git diff main | grep -i "key\|secret\|password"`)
- [ ] CORS_ORIGINS is explicit (not `*`)
- [ ] All new tables have RLS enabled

### Environment variables
- [ ] Backend env vars match `.env.example`
- [ ] Frontend env vars match `frontend/.env.example`
- [ ] `SUPABASE_SERVICE_ROLE_KEY` is NOT in frontend env vars

### Migrations
- [ ] All pending migrations have been applied in Supabase SQL editor
- [ ] No `memory_units` inserts failing due to missing columns

### Sync
- [ ] `PROGRESS.md` reflects current state
- [ ] `docs/decisions.md` has any new decisions from this session

## Rule
Do not deploy if any checklist item is red. Fix first, then re-run.
Do not create new markdown files.

## Required output format
```
## Pre-deploy check: <date>

### Results
- [ / x] Backend tests: <pass/fail — N passed, N failed>
- [ / x] Frontend tsc: <pass/fail>
- [ / x] Frontend build: <pass/fail>
- [ / x] No .env staged
- [ / x] No hardcoded secrets
- [ / x] Migrations applied
- [ / x] Env vars audited

### Verdict: GO | NO-GO
<summary of blockers if NO-GO>
```
