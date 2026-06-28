---
name: start-session
description: Safe session opener for EchoPersona. Confirms worktree, branch, dirty state, last PROGRESS milestone, running services, and shell GROQ override before any work begins. Read-only.
---

## Purpose
Open a session without re-asking the same six questions. Catch wrong-worktree edits, surprise dirty
diffs, and stale shell env overrides *before* any code is touched.

## Trigger phrases
- "start session"
- "begin work"
- "what's the state"
- "/start-session"

## Steps

1. **Where am I**
   ```bash
   pwd
   git rev-parse --show-toplevel
   git branch --show-current
   git status --short
   git worktree list
   ```
2. **What's the last known good state**
   ```bash
   tail -n 80 PROGRESS.md
   ```
3. **What's in flight**
   ```bash
   gh issue list --state open --assignee @me --limit 10 2>/dev/null || echo "gh not authed or no issues"
   ```
4. **What's running locally**
   ```bash
   lsof -nP -iTCP:8000,5173,6379 -sTCP:LISTEN 2>/dev/null | awk '{print $1, $9}' | sort -u
   docker ps --format '{{.Names}}\t{{.Status}}' 2>/dev/null | grep -E 'redis|echo' || true
   ```
5. **Shell GROQ override check** (the #1 voice-loop regression)
   ```bash
   [ -n "$GROQ_API_KEY" ] && echo "WARN_SHELL_GROQ_OVERRIDE" || echo "OK"
   ```
6. **Python import smoke** — only if backend/voice work is suspected
   ```bash
   cd backend && python -c "import groq, elevenlabs, cartesia, sentence_transformers" && echo "IMPORTS_OK"
   ```

## Output format

```
## Start-session report — <date>

- Worktree: <path>
- Branch: <branch>
- HEAD: <short sha — first line of commit message>
- Dirty files: <count> (<sample>)
- Last PROGRESS milestone: <one line>
- Open issue assigned to me: <#N title or "none">
- Local services up: backend(:8000)=<y/n>, vite(:5173)=<y/n>, redis(:6379)=<y/n>
- Shell GROQ override: <ok / WARN>
- Python imports (if checked): <ok / FAIL with name>

Next safe action: <one sentence>
```

## Stop conditions
- Worktree is dirty but the dirty files don't match the current task → stop, ask before editing.
- `pwd` differs from `/Users/kishorekumar/echopersona` when the user intends to run the live app.
- Shell GROQ override present and the task involves voice/persona — flag before starting any service.

## Token policy
- Tail only the last 80 lines of `PROGRESS.md`; do not dump the whole file.
- Skip the Python import smoke when work is doc/skill/agent only.
- Never echo `.env` values, GROQ key prefixes, or full WS URLs.

## Human approval
Not required. Read-only.
