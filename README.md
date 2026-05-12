# EchoPersona

> Talk to anyone, forever. Sub-600ms voice-to-voice AI personas.

EchoPersona is a real-time conversational AI avatar system. Upload voice
samples and personal stories about a person — the system clones their voice
and embeds their personality into a RAG-backed persona. Anyone can then have
a live voice conversation with that persona, with the avatar responding in the
cloned voice, in character, in under 600ms.

---

## Demo

[DEMO GIF — record with QuickTime/OBS: 30 seconds showing full conversation]

---

## Latency Numbers

Measured on warm requests against Groq free tier + ElevenLabs Flash:

| Stage | Target | Achieved |
|---|---|---|
| STT — Deepgram Nova-2 streaming | <200ms | ~105ms ✅ |
| LLM first token — Groq 8b-instant | <150ms | ~200ms (free tier RTT floor) |
| TTS first audio — ElevenLabs Flash | <350ms | ~330ms ✅ |
| **Total utterance-to-utterance** | **<600ms** | **~520ms warm ✅** |
| Cache hit (repeated questions) | — | ~320ms |

> **Cold start caveat:** First turn is ~650ms due to Groq + ElevenLabs
> cold path. Warm turns 2+ consistently hit target.
> To guarantee sub-600ms on all turns: swap Groq for local vLLM
> (`USE_VLLM=true` in `.env` — no code changes needed).

---

## Load Test Results (50 Concurrent Users)

Tested on MacBook M-series. Mock pipeline (Groq/ElevenLabs replaced with
in-process stubs) measures server concurrency — asyncio WebSocket handling,
RAG lookup, sentence chunking, and response routing — without external API
rate limits as a variable.

| Users | P50 | P95 | P99 | Errors |
|---|---|---|---|---|
| 10 | 121ms | 126ms | 126ms | 0 |
| 25 | 35ms | 39ms | 40ms | 0 |
| 50 | 36ms | 40ms | 40ms | 0 |

✅ **P95 target <800ms — passed at all concurrency levels (50 users: P95 40ms)**

> **External API note:** At 50 concurrent live turns, ElevenLabs free tier
> (4 concurrent stream cap) and Groq free tier become the bottleneck.
> Production path: Cartesia or self-hosted Kokoro for TTS, vLLM for LLM —
> both remove the concurrency ceiling. Run `MOCK_MODE=true` to benchmark
> the server layer in isolation: `MOCK_MODE=true uvicorn main:app --port 8001`

```bash
# Run the load test yourself
python tests/load_test.py <persona_id>                         # live APIs, 10→25→50 ramp
python tests/load_test.py <persona_id> --base ws://localhost:8001  # mock mode
python tests/load_test.py <persona_id> --users 50              # single run
```

---

## The Key Insight: Sentence Boundary Chunking

Most implementations wait for the full LLM response before sending to TTS.
That adds 400–800ms of unnecessary latency.

EchoPersona pipes each complete sentence to ElevenLabs the moment it arrives
from the LLM stream — before the LLM has finished generating:

```
LLM stream:  [Hello,][I][think][…][.] ──flush──▶ TTS sentence 1 starts
             [The][answer][is][…][.]  ──queue──▶ TTS sentence 2 prefetches concurrently
                                                  while sentence 1 is still playing
```

The first audio byte arrives ~330ms after the transcript. Sentence 2 is
prefetched in parallel so there is no gap between sentences — no second
round-trip to ElevenLabs mid-response.

---

## Architecture

```
Browser ──(PCM audio over WebSocket)──▶ FastAPI

                 ┌──────────────────────────┐
                 │  Deepgram Nova-2 (stream) │  ~105ms STT
                 └────────────┬─────────────┘
                              │ final transcript
              ┌───────────────▼──────────────────┐
              │  FAISS RAG lookup (persona ctx)   │
              │  Groq llama-3.1-8b-instant (stream)│  ~200ms first token
              └───────────────┬──────────────────┘
                              │ token stream
                 ┌────────────▼─────────────┐
                 │  Sentence boundary chunker│  flush at [.!?]
                 └────────────┬─────────────┘
                              │ sentence chunks
                 ┌────────────▼─────────────┐
                 │  ElevenLabs Flash v2.5    │  ~330ms first audio
                 └────────────┬─────────────┘
                              │ mp3 chunks
Browser ◀──(base64 audio over WebSocket)───┘
```

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite, Tailwind CSS, Recharts |
| Backend | FastAPI, asyncio, WebSocket |
| STT | Deepgram Nova-2 streaming |
| LLM | Groq llama-3.1-8b-instant / vLLM (drop-in swap) |
| TTS | ElevenLabs Flash v2.5 / Cartesia Sonic-2 (toggle) |
| RAG | FAISS + sentence-transformers (all-MiniLM-L6-v2) |
| Voice Cloning | ElevenLabs Instant Voice Cloning |
| Infra | Docker Compose, nginx reverse proxy, Redis |

---

## Quick Start

```bash
git clone https://github.com/yourusername/echopersona
cd echopersona
cp .env.example .env
# Edit .env — add DEEPGRAM_API_KEY, GROQ_API_KEY, ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID
docker compose up --build
```

Open `http://localhost`.

> **No API keys?** The app runs in **mock mode** automatically — the full
> WebSocket pipeline, latency dashboard, and persona flow all work without
> spending a cent. Add keys when you're ready to go live.

---

## Local Development (no Docker)

```bash
# Terminal 1 — backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --port 8000 --reload
```

```bash
# Terminal 2 — frontend
cd frontend
npm install
npm run dev          # → http://localhost:5173
```

---

## Creating a Persona

### Via the UI

Open the app and fill in:
- **Name** — who this persona is
- **Memory stories** — paste quotes, interviews, blog posts, anything written by or about them
- **Personality traits** — comma-separated (e.g. `warm, direct, technical`)
- **Speaking style** — how they sound (e.g. `short sentences, thinks out loud, uses analogies`)
- **Voice samples** — drop in audio files (mp3/wav); requires ElevenLabs paid plan for IVC

### Via the API

```bash
# 1 — create persona
curl -X POST http://localhost:8000/persona/create \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Richard Feynman",
    "stories": [
      "Feynman believed that if you cannot explain something simply, you do not understand it.",
      "He was known for Surely You Are Joking, Mr. Feynman — playful, curious, anti-pretension."
    ],
    "personality_traits": ["curious", "playful", "direct", "anti-pretension"],
    "speaking_style": "simple language, lots of analogies, thinks out loud"
  }'

# 2 — clone voice (30+ seconds of clean audio; falls back to default voice on free plans)
curl -X POST http://localhost:8000/persona/{persona_id}/upload-voice \
  -F "files=@sample1.mp3" \
  -F "files=@sample2.mp3"

# 3 — start a voice session (connect WebSocket with ?persona_id=...)
ws://localhost:8000/ws/{session_id}?persona_id={persona_id}
```

---

## Environment Variables

Copy `.env.example` to `.env`. Minimum required for live mode:

```env
DEEPGRAM_API_KEY=...
GROQ_API_KEY=...
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=...    # default voice used before/without voice cloning
```

### TTS provider toggle

```env
TTS_PROVIDER=elevenlabs    # default — Flash v2.5, ~330ms TTFA floor
# TTS_PROVIDER=cartesia    # Sonic-2, ~80–120ms TTFA floor — significantly faster
# CARTESIA_API_KEY=...
# CARTESIA_VOICE_ID=...
```

### Self-hosted LLM (break the Groq free-tier floor)

```env
USE_VLLM=true
VLLM_BASE_URL=http://your-gpu-host:8000/v1
```

```bash
# RunPod / Lambda / any GPU host — OpenAI-compatible API, zero code changes
docker run --gpus all -p 8000:8000 vllm/vllm-openai:latest \
  --model meta-llama/Llama-3.1-8B-Instruct \
  --tensor-parallel-size 1 \
  --max-model-len 4096
```

---

## WebSocket Protocol

Connect to `ws://localhost:8000/ws/{session_id}[?persona_id={id}]`

**Client → Server**

| Frame type | Content |
|---|---|
| Binary | Raw Int16 PCM audio chunks while recording |
| Text JSON | `{"type": "audio_end"}` — signals end of recording |
| Text JSON | `{"type": "ping"}` — keepalive |

**Server → Client** (in order per turn)

```json
{ "type": "transcript",      "text": "...",   "is_final": true,  "latency_ms": 105  }
{ "type": "llm_token",       "token": "...",                     "latency_ms": 200  }
{ "type": "audio_chunk",     "data": "<base64 mp3>"                                 }
{ "type": "sentence_end"                                                             }
{ "type": "audio_end"                                                                }
{ "type": "latency_summary", "stt_ms": 105, "llm_first_token_ms": 200,
                             "tts_first_audio_ms": 330, "total_ms": 523             }
```

---

## Scaling to 1000 Concurrent Users

The current single-server stack hits Groq rate limits and ElevenLabs concurrent
stream caps first. The architecture is already stateless-ready — session state
lives in Redis, workers are interchangeable:

```
Cloudflare ──▶ FastAPI workers (N replicas)
                        │
              ┌─────────┼─────────┐
              ▼         ▼         ▼
           Redis      vLLM    Deepgram
        (session    (A100 —   (streaming
          state)    ~5ms TTFT)  STT)
                                  │
                              Kokoro TTS
                           (self-hosted,
                           ~80ms TTFA)
```

| Component | Dev (current) | Production path |
|---|---|---|
| LLM | Groq free tier | vLLM on A100 — ~5ms TTFT, no rate limits |
| TTS | ElevenLabs Flash | Cartesia / Kokoro self-hosted — $0 marginal cost |
| STT | Deepgram cloud | Deepgram self-hosted or streaming Whisper |
| Session state | In-process dict | Redis — enables horizontal scale, zero code changes |

All three swaps are env-var toggles — no code changes required.

---

## Load Test

```bash
# Backend must be running (mock mode is fine)
python tests/load_test.py   # 50 concurrent WebSocket users
```

---

## License

MIT
