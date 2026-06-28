---
name: pr-readiness
description: 12-row GO/NO-GO check before any commit or PR. Verifies branch, linked issue, tests, secret-free diff, PROGRESS.md updated, drafts the PR body, and refuses any AI co-author attribution. Read-only.
---

## Purpose
Catch the things that always get caught at review — wrong branch, missing tests, leaked secrets,
forgotten PROGRESS.md — *before* opening the PR.

## Trigger phrases
- "pr ready"
- "ready to commit"
- "/pr-readiness"

## Steps

1. **Branch**
   ```bash
   git branch --show-current
   ```
   Block if `main` unless the user explicitly says `--docs-only` and the diff is doc-only.
2. **Linked GitHub issue**
   ```bash
   gh issue list --state open --search "$(git branch --show-current)"
   ```
   Block if no issue is linkable. (If `gh` isn't authed, ask the user for the issue number.)
3. **Diff scope** — single concern
   ```bash
   git diff --name-only origin/main...HEAD
   ```
   If the file list crosses ≥2 unrelated areas (e.g. `backend/routers/` + `backend/migrations/` +
   `frontend/`), block and recommend splitting.
4. **Whitespace**
   ```bash
   git diff --check
   ```
5. **Secret grep** on the staged diff
   ```bash
   git diff --cached -U0 | grep -E '(GROQ_API_KEY=|ELEVENLABS_API_KEY=|SUPABASE_SERVICE_ROLE_KEY=|STRIPE_SECRET_KEY=|eyJ[A-Za-z0-9_-]{20,}|token=|Bearer\s+[A-Za-z0-9._-]+)' \
     && echo "FAIL_SECRET" || echo "OK"
   ```
   Report **only** "matched at `<file>:<line>` (redacted)" — never the matched content.
6. **No `.env*` staged**
   ```bash
   git diff --name-only --cached | grep -E '^\.env|/\.env' && echo "FAIL_ENV_STAGED" || echo "OK"
   ```
7. **Backend tests** (if backend changed)
   ```bash
   cd backend && python -m pytest tests/ -q
   ```
8. **Frontend tsc + build** (if frontend changed)
   ```bash
   cd frontend && npx tsc --noEmit && npm run build
   ```
9. **PROGRESS.md updated for this slice**
   ```bash
   git log --name-only --pretty=format: origin/main..HEAD | grep -Fx 'PROGRESS.md'
   ```
   If empty, prompt to add a milestone entry (or document a clear N/A reason in the PR body).
10. **Draft PR body** from `.github/pull_request_template.md`, filled with the diff summary,
    test results, rollback. Print it ready to paste.
11. **Rollback statement** is present in the draft PR body.
12. **No AI co-author** in the planned commit message. Strip any `Co-Authored-By: Claude*`,
    `Co-Authored-By: Anthropic*`, or `🤖 Generated with` line if encountered.

## Output format

```
## PR readiness — <date>

| # | Check | Status | Fix hint |
|---|---|---|---|
| 1 | Branch                    | PASS / NO-GO | … |
| 2 | Linked issue              | … | … |
| 3 | Diff scope                | … | … |
| 4 | Whitespace                | … | … |
| 5 | Secret grep               | … | … |
| 6 | No .env staged            | … | … |
| 7 | Backend tests             | … | … |
| 8 | Frontend tsc/build        | … | … |
| 9 | PROGRESS.md updated       | … | … |
| 10 | PR body drafted          | … | … |
| 11 | Rollback included        | … | … |
| 12 | No AI co-author          | … | … |

Verdict: GO / NO-GO
Blockers: <list>

---
### Draft PR body
<filled-in template>
```

## Stop conditions
- Any NO-GO row blocks. Do not commit, do not push.
- Secret match → stop immediately, instruct the user to rotate the key and remove from history.

## Token policy
- Print only `<file>:<line> (redacted)` for any secret match — never the matched string.
- Cap `git diff --name-only` output at 50 lines; if larger, print "+N more".
- Pytest output: keep only the summary line + the first 5 failures.

## Human approval
Not required to run; the actual `git commit` / `gh pr create` is the user's hand.
