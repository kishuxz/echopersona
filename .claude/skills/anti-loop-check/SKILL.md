---
name: anti-loop-check
description: 11-row preflight that catches every known EchoPersona regression trigger — wrong worktree, dead Redis, stale shell GROQ override, placeholder ElevenLabs voice id, missing Python deps, leaked tokenized WS URLs. Read-only. Run before any voice/persona/Tavus work.
---

## Purpose
The voice loop has broken the same way too many times. This skill turns those failure modes into a
single PASS / WARN / FAIL report so the user never re-debugs the same regression.

## Trigger phrases
- "anti loop check"
- "preflight"
- "/anti-loop-check"
- "voice not working again"

## Steps

Run each check; record PASS / WARN / FAIL with a one-line fix hint per failing row. Never print
secret values — only the key name.

1. **Worktree** — `pwd` is `/Users/kishorekumar/echopersona` *or* a Conductor worktree the user
   explicitly named.
2. **Docker Redis healthy**
   ```bash
   docker ps --format '{{.Names}} {{.Status}}' | grep -Ei 'redis' || echo "NOPE"
   ```
3. **Python imports** (run from the backend venv)
   ```bash
   cd backend && python -c "import groq, elevenlabs, cartesia, sentence_transformers" && echo "IMPORTS_OK"
   ```
4. **Shell GROQ override** (the #1 culprit)
   ```bash
   [ -n "$GROQ_API_KEY" ] && echo "WARN_SHELL_GROQ_OVERRIDE" || echo "OK"
   ```
   If WARN, the fix is to start the backend as
   `env -u GROQ_API_KEY -u ELEVENLABS_VOICE_ID python -m uvicorn main:app --port 8000 --reload`.
5. **`backend/.env` key presence — NEVER values**
   ```bash
   awk -F= '/^[A-Z_]+=/ {print $1}' backend/.env | sort -u
   ```
   Expect: `GROQ_API_KEY`, `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `VOICE_ALWAYS_ON`,
   `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`.
6. **ElevenLabs voice id is not a placeholder**
   ```bash
   grep -E '^ELEVENLABS_VOICE_ID=' backend/.env | grep -Ei '(your_default_voice_id_here|TODO|REPLACE|placeholder)' \
     && echo "FAIL_PLACEHOLDER_VOICE_ID" || echo "OK"
   ```
   Do not print the actual id.
7. **`VOICE_ALWAYS_ON=true`** present for local testing
   ```bash
   grep -E '^VOICE_ALWAYS_ON=true' backend/.env >/dev/null && echo "OK" || echo "WARN_VOICE_GATE_CLOSED"
   ```
8. **Backend start command shape** — `docs/runbook.md` still documents
   `env -u GROQ_API_KEY -u ELEVENLABS_VOICE_ID python -m uvicorn main:app --port 8000 --reload`.
   If not, the runbook is stale; flag `devex-reviewer`.
9. **Frontend points to localhost** — `frontend/.env*` keys include
   `VITE_API_URL=http://localhost:8000` and `VITE_WS_URL=ws://localhost:8000` (presence check, no values).
10. **No tokenized WS URL leakage in staged diff**
    ```bash
    git diff --staged --unified=0 | grep -E '(token=|Bearer\s+[A-Za-z0-9._-]{20,})' \
      && echo "FAIL_LEAK" || echo "OK"
    ```
11. **APJ enrichment status reminder** — if the task is persona-fidelity work, the user should
    confirm in the Supabase dashboard that the APJ persona row has non-empty `voice_card` and
    `style_card` and `readiness_status='ready'`. This skill does not query Supabase — it only reminds.

## Output format

```
## Anti-loop check — <date>

| # | Check | Status | Fix hint (only if not PASS) |
|---|---|---|---|
| 1 | Worktree | PASS / WARN / FAIL | … |
| 2 | Redis | … | … |
| … (rows 3–11) | … | … | … |

Verdict: GO / NO-GO
Blockers: <list of FAILs or "none">
```

## Stop conditions
- Any **FAIL** → user fixes before running the backend / starting voice work.
- WARNs are informational; surface them but do not block.

## Token policy
- Never print `.env` values, voice ids, or API key prefixes.
- Cap any grep output to the first 5 matches; if more, print "+N more".
- Truncate any leaked-token line so only `file:line` is visible.

## Human approval
Not required. Read-only.
