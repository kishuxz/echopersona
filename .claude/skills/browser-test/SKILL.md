---
name: browser-test
description: Standardised manual-browser walkthrough for EchoPersona's user-visible voice loop. Produces a printable scenario checklist (load persona → start session → STT → reply → audible TTS → Tavus video). Redacts tokens. The user drives the browser; this skill is the script.
---

## Purpose
Make "did the change break the user-facing loop?" a question with a deterministic answer. The skill
emits a checklist that the user walks through in Chrome with DevTools open.

## Trigger phrases
- "browser test"
- "manual qa"
- "/browser-test"
- "test voice in the browser"

## Pre-flight
- Backend up on `:8000`, frontend up on `:5173`, Redis up on `:6379`.
- `/anti-loop-check` PASS (or known WARN list documented).
- Logged-in test account with at least one persona (APJ by default).

## Scenarios

| # | Step | Expected | Notes for tester |
|---|---|---|---|
| 1 | Open `http://localhost:5173`, log in. | Dashboard renders; no console error. | If 401, the JWT expired — re-login. |
| 2 | Open the APJ persona detail page. | Persona card + Start Session button visible; `readiness_status` is `ready`. | If "processing", run `/anti-loop-check` and check enrichment logs. |
| 3 | Click **Start Session**. | WS connects; status indicator green. | Record host + path only (e.g. `ws://localhost:8000/ws/session`). **Never** paste a URL containing `?token=…`. |
| 4 | Hold mic, say a short canned phrase (e.g. "Hello"). | STT transcript appears within ~2s. | If silent, check mic permissions in Chrome site settings. |
| 5 | Wait for the model reply. | Reply text appears within ~600ms warm. | First reply may be slower (cold path). |
| 6 | Listen for TTS. | Audible reply plays end-to-end without clipping. | If no audio, check `audio_end` event and ElevenLabs voice id. |
| 7 | Open DevTools → Console. | No WS errors, no Groq 4xx, no `voice_not_found`, no unhandled promise rejection. | Filter for `[WS_`, `[TTS_`, `[STT_`. |
| 8 | (If video mode is on) Tavus element appears. | Video element renders + plays; lipsync roughly aligns. | If blank, hand off to `media-pipeline-engineer` — do not silently retry. |
| 9 | Capture failures. | Screenshot saved to `.context/browser-test/<YYYY-MM-DD>/<step>.png` (gitignored). | Redact any visible token in the screenshot before sharing. |

## Output format

```
## Browser test — <date> — persona=<APJ|…>

| # | Step | Pass/Fail | Notes |
|---|---|---|---|
| 1 | Load dashboard | … | … |
| 2 | Open APJ detail | … | … |
| 3 | Start Session   | … | host=<ws://localhost:8000/...> (token redacted) |
| 4 | STT transcript  | … | latency=<~ms> |
| 5 | Model reply     | … | latency=<~ms> |
| 6 | Audible TTS     | … | … |
| 7 | Console clean   | … | <count> warnings, <count> errors |
| 8 | Tavus video     | PASS / FAIL / N/A | … |

Verdict: GO / NO-GO
Blockers: <list>
```

## Stop conditions
- Any FAIL → do not say "voice works". Route the failure:
  - STT/TTS/WS → `media-pipeline-engineer`
  - Persona content / fidelity → `rag-persona-engineer`
  - Frontend rendering → `frontend-react-engineer`
  - Unknown → `debugger`

## Token policy
- Redact `?token=…`, `Authorization: Bearer …`, and any host string containing a token. Keep only
  `host:port` + path.
- Console excerpts: paste at most 20 lines around a relevant error; trim the rest.
- Never paste a JWT, even partially.

## Human approval
Not required.
