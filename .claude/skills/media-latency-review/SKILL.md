---
name: media-latency-review
description: Verify that TTS, STT, and video generation remain async and non-blocking after any media pipeline change. Run after any services/tts.py, services/stt.py, or video avatar change.
---

## When to use
- After any change to `services/tts.py`, `services/tts_cartesia.py`, `services/stt.py`
- After any change to `services/did.py`, `services/simli.py`, or future Tavus integration
- After any change to `routers/ws.py` that affects the media path

## Checklist
1. Trace the WebSocket reply path in `routers/ws.py` — confirm text reply is sent to client BEFORE TTS fires.
2. Verify TTS is `await`ed only after `yield` / client send — never blocking the text commit.
3. Verify video generation (D-ID / Simli / Tavus) is launched as a background task — `video_ready` event sent separately.
4. Verify sentence chunker fires TTS per sentence, not after full LLM response.
5. Verify STT (Groq Whisper) is called only during creation capture, not on the live reply path.
6. Check Groq Whisper call count against the ~2,000/day Whisper RPD limit.
7. Verify Cartesia fallback path is reachable via `TTS_PROVIDER=cartesia` env var.

## Rule
Do not modify code. Report findings only. Do not create new markdown files.

## Required output format
```
## Media Latency Review: <change>

### Latency path
STT target: <200ms | actual: <N>ms (if measurable)
TTS first audio target: <350ms EL / <120ms Cartesia | actual: <N>ms
Total target: <600ms | expected: <N>ms

### Async guarantee
Text committed before TTS starts? <yes/no>
Video generation non-blocking? <yes/no>

### Findings
- [CRITICAL|HIGH|MEDIUM|OK] <file:line> — <finding>

### Verdict: PASS | FAIL
```
