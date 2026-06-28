---
name: investigate
description: Root-cause investigation workflow. Reproduce first, collect evidence, form hypotheses, identify the smallest credible fix. Use for TTS/audio/WebSocket/Tavus bugs before touching any code.
---

## Purpose
Find the root cause of a bug before attempting any fix. Prevent speculative patching.

## When to use
- TTS produces no audio, wrong audio, or excessive latency
- Tavus video generation fails or blocks the reply path
- WebSocket message order is wrong or audio_url never arrives
- Any bug where the cause is not immediately obvious from the error

## Inputs expected
- Description of observed vs expected behavior
- Environment details: `TTS_PROVIDER` value, which API keys are set, local vs VPS
- Any error messages, logs, or WS network traces available

## Process

### Step 1 — Reproduce
Describe exact reproduction steps. Confirm the issue is deterministic or characterize its frequency. Do not form hypotheses yet.

### Step 2 — Collect evidence
Use CodeGraph (`codegraph_explore`) to locate the relevant code path before opening files. Read:
- The full WS reply path (`routers/ws.py`)
- The relevant service file (`services/tts.py`, `services/stt.py`, `services/did.py`, Tavus handler)
- The chunker if audio is the concern (`services/chunker.py`)

For audio bugs specifically check:
- `TTS_PROVIDER` env var and which branch of the provider switch is taken
- Whether TTS is fired after the text WS message is sent (never before — this is the latency constraint)
- Whether the chunker produces non-empty sentences before TTS is called
- Whether the audio blob URL is returned and the WS `audio_url` message is actually sent

For Tavus bugs specifically check:
- Whether the API call is async and non-blocking
- Whether any exception is swallowed silently in the async task
- Whether the callback/video_url path is reachable after the API responds

### Step 3 — Form ≤ 3 hypotheses
Each hypothesis must be falsifiable. Rank by likelihood based on evidence.

### Step 4 — Test one at a time
Test each hypothesis with evidence. Do not patch code to test — read and reason first. Only add temporary debug logging if necessary, and clean it up immediately after.

### Step 5 — Identify the smallest credible fix
Once root cause is confirmed, describe the fix as: file + line + what to change + risk level.
Do not implement — stop here and hand off.

## Output format

```
## Investigation: <issue title>

### Reproduction
- Steps: <exact steps>
- Environment: TTS_PROVIDER=<value>, keys: <present/absent>, env: <local/vps>
- Observed: <what actually happens>
- Expected: <what should happen>
- Frequency: <always / intermittent / under condition X>

### Evidence
- <file:line — what it shows>
- <relevant log/response — secrets redacted>

### Hypotheses
1. <hypothesis> — <evidence> — <result: confirmed / ruled out>
2. <hypothesis> — <evidence> — <result>
3. <hypothesis> — <evidence> — <result>

### Root cause
<one clear statement>

### Recommended fix
- File: <path>
- Line: <approx>
- Change: <description>
- Risk: <low / medium / high>

### Next step
Delegate implementation to: media-pipeline-engineer (for TTS/STT/video)
```

## Stop conditions
- Repeated blind fix attempts with no new evidence — stop and escalate to user
- Root cause requires touching auth, migrations, billing, or RLS — stop, flag to user, require approval
- Cannot reproduce the issue — document the failure and ask user for more context