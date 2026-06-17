---
name: update-project-context
description: Sync PROGRESS.md with reality. Run at the start of every session or after completing a build step.
---

## When to use
- At the start of any coding session
- After completing a build step
- When PROGRESS.md might be stale

## Checklist
1. Read `PROGRESS.md` — note the stated active feature and last completed step.
2. Run `git log --oneline -10` — compare recent commits to PROGRESS.md state.
3. Run `cd backend && python -m pytest tests/ -q` — note which tests pass.
4. Check `backend/migrations/` — note any unapplied migrations.
5. Update `PROGRESS.md` with:
   - Correct active feature (from git log)
   - Last completed step (from tests + git log)
   - Current blocker (unapplied migrations, failing tests, missing env vars)
   - Next action (concrete single coding step)
   - Last known green command (from test run)

## Rule
Do not modify any application code. Do not create new markdown files.
Update only `PROGRESS.md` (and `docs/decisions.md` if a decision was undocumented).

## Required output format
```
## Context update

Active: <feature>
Last completed: <step> (confirmed by <test or commit>)
Blocker: <blocker or "none">
Next action: <single concrete step>
Last green: <command>

Changes made:
- PROGRESS.md: <what was updated>
```
