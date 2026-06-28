## Linked issue
Closes #

## Root cause / evidence
<!-- For bugs: the reproduction and the smoking-gun line(s). For features: the spec line being implemented. -->

## Solution
<!-- One paragraph describing the approach. -->

## Files changed
<!-- Paste from `git diff --name-only origin/main...HEAD` -->

## Tests run
- [ ] `cd backend && python -m pytest tests/ -q` — N passed
- [ ] `cd frontend && npx tsc --noEmit` — clean
- [ ] `cd frontend && npm run build` — clean (if frontend changed)

## Browser verification
- [ ] `/browser-test` scenarios pass (or N/A — explain)
- [ ] Screenshots: <paths in `.context/browser-test/<date>/` or N/A>

## Risk
low / medium / high — <why>

## Rollback
<one or two commands or "git revert <sha>">

## Checklist
- [ ] No `.env*` staged
- [ ] No secrets / JWTs / full WS URLs in diff or PR body
- [ ] PROGRESS.md updated for meaningful milestone (or N/A — explain)
- [ ] One implementation lane only
- [ ] Migrations (if any) applied in Supabase SQL editor and noted in PROGRESS.md "do not forget"
- [ ] No deploy with this PR unless explicitly approved
- [ ] No `Co-Authored-By: Claude`, no `🤖 Generated with`, no AI attribution in commits
