---
name: ponytail-context
description: Token-budget skill. Detects Ponytail locally and uses it if installed; otherwise enforces a Ponytail-compatible manual token policy (rg-before-Read, narrow ranges, summarise tool output, no env/log/token dumps, PROGRESS.md as durable memory).
---

## Purpose
Keep context lean. Either delegate to real Ponytail when installed, or enforce the same discipline
manually so the agent doesn't bloat the conversation with full files, full logs, or pasted secrets.

## Trigger phrases
- "context is getting big"
- "compact"
- "checkpoint and continue"
- "/ponytail-context"

## Step 1 — Detect Ponytail

```bash
command -v ponytail 2>/dev/null
find ~/.claude ~/.gstack /Users/kishorekumar -maxdepth 5 -iname '*ponytail*' 2>/dev/null | head -5
```

If a binary or skill directory is found, report:
- discovered path
- documented invocation (do **not** invent flags — read its README/SKILL.md first)
- defer to it for the rest of this session

If nothing is found (current state on this machine), continue to Step 2.

## Step 2 — Enforce manual token hygiene (Ponytail-compatible policy)

These rules mirror what Ponytail would enforce. Use them as the operating contract for the rest
of the session.

### Reading files
- `rg` before `cat` / `Read` for any file expected to be > 400 lines.
- For known-large files, read narrow ranges with `Read offset/limit` or `sed -n 'A,Bp'` capped at
  ~200 lines per call.
- Never `cat .env`. Read key names only: `awk -F= '/^[A-Z_]+=/ {print $1}' backend/.env`.

### Tool output
- Summarise any tool output > 50 lines before quoting it back to the user.
- For logs, keep at most 20 lines of context around the relevant marker. Strip everything else.
- For diffs > 200 lines, paste only the summary (`git diff --stat`) plus the 1–2 most relevant
  hunks; reference the rest by file:line.

### Secrets / URLs
- Never paste full WebSocket URLs that contain `?token=…`.
- Never paste `Authorization: Bearer …` headers.
- Never paste API keys, even partially. Report "key present" / "key missing" only.

### Memory across turns
- `PROGRESS.md` is the durable cross-session memory. Write a one-paragraph checkpoint when
  context starts to feel noisy. Do **not** rely on chat scrollback for important decisions.
- When handing off to a subagent (or to a future session), write the handoff first to
  `.context/handoff-<YYYY-MM-DD>.md` (gitignored) — then pass that path to the next agent rather
  than the raw chat.

### Agent switching
- One specialist agent owns one slice. Switching agents mid-edit costs context — write the
  handoff, then switch.

## Step 3 — Compact suggestion

If the session feels heavy (lots of read files, lots of tool output already in context), suggest:

```
## Suggested checkpoint
Write `.context/handoff-<date>.md` summarising:
- What was decided
- What was already verified
- What's the next concrete step
Then end this turn and restart fresh.
```

## Output format

```
## Ponytail status — <date>
- Ponytail installed: yes / no
- Path: <path or "n/a">
- Mode: <delegated to ponytail | manual policy>

### Active rules this session
<bullet list of the rules above, trimmed to those that matter for the current task>

### Checkpoint suggestion
<none | write .context/handoff-<date>.md and restart>
```

## Stop conditions
None. Advisory skill.

## Token policy
This skill **is** the token policy. Keep its own output short — never re-paste the full rule list
unless asked.

## Human approval
Not required.
