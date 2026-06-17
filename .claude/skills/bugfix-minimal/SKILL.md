---
name: bugfix-minimal
description: Fix a bug with the smallest possible change. Enforces that only the broken thing is touched — no cleanup, no refactor, no unrelated improvements.
---

## When to use
For any bug fix, whether small or complex.

## Checklist
1. Use CodeGraph MCP to find the exact line(s) where the bug originates — do not guess.
2. Read the failing test or reproduction steps to confirm the root cause before editing.
3. Write the fix — smallest possible change that makes the test pass or the bug go away.
4. Do NOT refactor surrounding code unless it is part of the root cause.
5. Do NOT add error handling for scenarios that can't happen.
6. Do NOT rename variables or reformat code in the same commit.
7. Run `cd backend && python -m pytest tests/ -q` — verify the fix and no regressions.
8. If the fix touches a Supabase table, run `/supabase-rls-review`.
9. If the fix touches the live path, run `/media-latency-review`.

## Rule
The diff must be minimal. If you find yourself changing more than the broken thing, stop and ask.
Do not create new markdown files.

## Required output format
```
## Bugfix: <description>

### Root cause
<file:line> — <what was wrong>

### Fix
<file:line> — <what changed and why this fixes it>

### Not changed (and why)
<anything you consciously left alone>

### Test result
`python -m pytest tests/ -q` — <N passed, N failed>
Regression check: <pass/fail>
```
