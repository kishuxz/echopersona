---
name: interrupted-session
description: Safe recovery after a crash, context loss, branch switch, or inherited partial work. Classifies the git state, checks for partial ingestion changes, runs tests before continuing.
---

## Purpose
Recover safely when a session ends mid-task — especially during stateful operations like ingestion
pipeline changes, WS protocol edits, or partial migrations.

## When to use
- Returning to a session that was interrupted mid-implementation
- Picking up work from a different machine or worktree
- After a Claude Code crash during a complex debugging or implementation task
- Any time `git status` shows uncommitted changes you didn't write in this session

## Process

### Step 1 — Read the current state
Run these commands and read the output carefully:

```bash
git status
git diff
git log --oneline -10
git stash list
```

### Step 2 — Classify the state

| State | Description | Action |
|---|---|---|
| **committed-clean** | All changes committed, working tree clean | Safe to continue; read PROGRESS.md and proceed |
| **uncommitted-complete** | Changes staged or unstaged but logically complete (tests pass) | Review diff, run tests, then commit or continue |
| **uncommitted-partial** | Half-finished changes — partial implementation, failing tests, or interrupted mid-step | Stop. Assess before continuing. See Step 3. |
| **nothing** | No changes at all | Read PROGRESS.md and start fresh |

### Step 3 — Handle uncommitted-partial state

For **partial ingestion changes** (`services/ingestion/`, `worker/tasks/`):
- Check which Stage was being modified (0, 1, 2, 3, or 4)
- Confirm no Stage was left in a state that writes invalid memory units to the DB
- Do not run the arq worker until the partial change is resolved

For **partial WS / media changes** (`routers/ws.py`, `services/tts.py`, `services/stt.py`):
- Check whether the WS reply path is in a broken intermediate state
- Do not start the backend server until the issue is assessed

For **partial migration changes** (`backend/migrations/`, `supabase/migrations/`):
- Stop immediately — require explicit human approval before proceeding
- Do not attempt to apply or roll back a partial migration autonomously

For **partial auth changes** (`middleware/auth.py`, RLS policies):
- Stop immediately — require explicit human approval before proceeding

### Step 4 — Run tests before continuing

```bash
cd backend && python -m pytest tests/ -q
```

If tests fail, diagnose before continuing. Do not skip failures.

### Step 5 — Update PROGRESS.md

After confirming the tree is clean and tests pass, update PROGRESS.md to reflect the current
accurate state before starting new work.

## Output format

```
## Interrupted Session Recovery — <date>

### Git state
- Branch: <branch>
- HEAD: <commit hash and message>
- Working tree: <clean / uncommitted-complete / uncommitted-partial>
- Stash entries: <count>

### State classification
<committed-clean / uncommitted-complete / uncommitted-partial / nothing>

### What is safe to continue
<description or "nothing until resolved">

### What requires human review
<description or "none">

### Test results
<pytest output summary>

### Recommended next action
<one sentence>
```

## Stop conditions
- `uncommitted-partial` touches migrations, auth, billing, or RLS → stop, flag to user, require approval
- Tests fail and the cause is unclear → stop, report findings, ask user how to proceed
- Multiple unrelated partial changes are mixed together → stop, ask user to review the diff manually