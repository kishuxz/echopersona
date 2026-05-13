# EchoPersona

> Real-time conversational AI avatar system. Upload voice samples and personal
> stories — anyone can then have a live voice conversation with that persona
> in under 600ms.

## Live Demo

[kishoreai.online](https://kishoreai.online)

---

## Latency

Measured on warm requests against Groq free tier + ElevenLabs Flash v2.5:

| Stage | Target | Achieved |
|-------|--------|----------|
| STT (Groq Whisper large-v3-turbo) | <200ms | ~105ms |
| LLM first token (Groq llama-3.1-8b-instant) | <150ms | ~200ms (free-tier RTT floor) |
| TTS first audio (ElevenLabs Flash v2.5) | <350ms | ~330ms |
| **Total utterance-to-utterance** | **<600ms** | **~520ms warm** |
| Cache hit (repeated questions) | — | ~320ms |

> **Cold start caveat:** First turn is ~650ms due to Groq + ElevenLabs cold path.
> Warm turns 2+ consistently hit target. To guarantee sub-600ms on all turns:
> swap Groq for local vLLM (`USE_VLLM=true` — no code changes required).

---

## Architecture

```
Browser ──(PCM audio over WebSocket)──▶ FastAPI

                 ┌──────────────────────────┐
                 │  Groq Whisper (REST)      │  ~105ms STT
                 └────────────┬─────────────┘
                              │ final transcript
              ┌───────────────▼──────────────────┐
              │  FAISS RAG lookup (persona ctx)   │
              │  Groq llama-3.1-8b-instant        │  ~200ms first token
              └───────────────┬──────────────────┘
                              │ token stream
                 ┌────────────▼─────────────┐
                 │  Sentence boundary chunker│  flush at [.!?]
                 └────────────┬─────────────┘
                              │ sentence chunks (prefetched concurrently)
                 ┌────────────▼─────────────┐
                 │  ElevenLabs Flash v2.5    │  ~330ms first audio
                 └────────────┬─────────────┘
                              │ mp3 chunks
Browser ◀──(base64 audio over WebSocket)───┘
```

Sentence 2+ is prefetched in parallel while sentence 1 is still streaming,
eliminating the inter-sentence ElevenLabs round-trip gap.

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | React 18, Vite, TypeScript, Tailwind CSS, Recharts |
| Backend | FastAPI, asyncio, WebSocket |
| Auth | Supabase (JWT) |
| Database | Supabase Postgres |
| STT | Groq Whisper large-v3-turbo (Deepgram Nova-2 fallback) |
| LLM | Groq llama-3.1-8b-instant / OpenAI-compatible vLLM (drop-in swap) |
| TTS | ElevenLabs Flash v2.5 / Cartesia Sonic-2 (env-var toggle) |
| RAG | FAISS + sentence-transformers (paraphrase-MiniLM-L3-v2) |
| Voice Cloning | ElevenLabs Instant Voice Cloning |
| Video Avatars | D-ID talking-head generation (optional) |
| Infra | Docker Compose, nginx reverse proxy |

---

## Key Technical Decisions

- **Sentence boundary chunking over full-response buffering.** Most
  implementations wait for the complete LLM response before sending to TTS,
  adding 400–800ms of dead time. EchoPersona pipes each complete sentence to
  ElevenLabs the moment it arrives from the LLM stream. The first audio byte
  plays ~330ms after the transcript, regardless of response length.

- **Concurrent sentence prefetch.** Sentence 2+ is fetched from ElevenLabs in
  parallel while sentence 1 is streaming to the client. This eliminates the
  ~400ms ElevenLabs round-trip gap between sequential sentences that would
  otherwise cause audible pauses mid-response.

- **FAISS over a hosted vector DB.** Persona memory fits in RAM for the target
  use case. FAISS runs in-process with zero network overhead — retrieval is
  ~2ms versus ~50ms for a cloud vector DB call. The sentence-transformers model
  loads once and stays warm.

- **Groq Whisper over Deepgram streaming.** Batch Whisper (Groq REST) achieves
  ~105ms — faster than Deepgram's streaming path for utterances under 10s,
  since there is no per-word partial overhead. Deepgram is retained as a
  fallback for resilience.

---

## Local Development

```bash
git clone https://github.com/kishuxz/echopersona
cd echopersona
cp .env.example .env
# Edit .env — add DEEPGRAM_API_KEY, GROQ_API_KEY, ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID
docker compose up --build
```

Open `http://localhost:3000`.

> **No API keys?** The app runs in **mock mode** automatically — the full
> WebSocket pipeline, latency dashboard, and persona flow all work without
> spending a cent. Add keys when you're ready to go live.

### Without Docker

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

## Environment Variables

Copy `.env.example` to `.env`. Minimum required for live mode:

| Variable | Required | Description |
|----------|----------|-------------|
| `GROQ_API_KEY` | Live mode | STT (Whisper) + LLM (llama-3.1-8b-instant) |
| `DEEPGRAM_API_KEY` | Live mode | STT fallback |
| `ELEVENLABS_API_KEY` | Live mode | TTS + voice cloning |
| `ELEVENLABS_VOICE_ID` | Live mode | Default voice before cloning |
| `SUPABASE_URL` | Always | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | Always | Backend DB access (never expose to frontend) |
| `SUPABASE_ANON_KEY` | Always | Auth verification |
| `DID_API_KEY` | Optional | D-ID talking-head video generation |
| `SIMLI_API_KEY` | Optional | Simli real-time lip-sync avatar |
| `CARTESIA_API_KEY` | Optional | Cartesia TTS (~80ms TTFA, faster than ElevenLabs) |
| `USE_VLLM` | Optional | `true` to route LLM to local vLLM instead of Groq |
| `VLLM_BASE_URL` | Optional | OpenAI-compatible vLLM endpoint |
| `MOCK_MODE` | Optional | `true` to force mock mode regardless of key presence |
| `CORS_ORIGINS` | Production | Comma-separated allowed origins |

### TTS provider toggle

```env
TTS_PROVIDER=elevenlabs    # default — Flash v2.5, ~330ms TTFA floor
# TTS_PROVIDER=cartesia    # Sonic-2, ~80–120ms TTFA — significantly faster
```

### Self-hosted LLM

```env
USE_VLLM=true
VLLM_BASE_URL=http://your-gpu-host:8000/v1
```

---

## WebSocket Protocol

Connect to `ws://<host>/ws/{session_id}?persona_id={id}&token={jwt}`

**Client → Server**

| Frame | Content |
|-------|---------|
| Binary | Raw Int16 PCM audio chunks while recording |
| `{"type": "audio_end"}` | Signals end of user utterance |
| `{"type": "ping"}` | Keep-alive |
| `{"type": "text_turn", "text": "..."}` | Dev bypass: skip STT |

**Server → Client** (in order per turn)

```json
{ "type": "transcript",      "text": "...", "is_final": true, "latency_ms": 105 }
{ "type": "llm_token",       "token": "...",                  "latency_ms": 200 }
{ "type": "audio_chunk",     "data": "<base64 mp3>"                              }
{ "type": "sentence_end"                                                          }
{ "type": "audio_end"                                                             }
{ "type": "latency_summary", "stt_ms": 105, "llm_first_token_ms": 200,
                             "tts_first_audio_ms": 330, "total_ms": 523          }
```

---

## Project Structure

```
echopersona/
├── backend/
│   ├── main.py              # FastAPI app, lifespan validation
│   ├── config.py            # Pydantic settings (env vars)
│   ├── middleware/
│   │   └── auth.py          # Supabase JWT verification
│   ├── models/
│   │   ├── persona.py       # Persona + PersonaCreate Pydantic models
│   │   └── session.py       # ConversationTurn, LatencySnapshot
│   ├── routers/
│   │   ├── ws.py            # WebSocket endpoint + STT→LLM→TTS pipeline
│   │   ├── persona.py       # Persona CRUD + voice/avatar upload
│   │   └── health.py        # Health check
│   └── services/
│       ├── llm.py           # Groq / vLLM streaming
│       ├── stt.py           # Groq Whisper + Deepgram fallback
│       ├── tts.py           # ElevenLabs streaming + voice cloning
│       ├── tts_cartesia.py  # Cartesia TTS (optional provider)
│       ├── rag.py           # FAISS index + system prompt builder
│       ├── persona_store.py # Supabase DB access layer
│       ├── did.py           # D-ID talking-head video
│       ├── simli.py         # Simli real-time avatar
│       ├── chunker.py       # Sentence boundary detection
│       └── latency.py       # Per-turn latency timer
├── frontend/
│   └── src/
│       ├── components/      # VoiceInterface, PersonaUpload, LatencyDashboard, …
│       ├── hooks/           # useWebSocket, useAudioRecorder, useAuth, …
│       ├── lib/             # api.ts (fetch layer), supabase.ts
│       ├── pages/           # LandingPage, Dashboard, PersonaDetail, AuthPage
│       ├── types/index.ts   # Shared TypeScript interfaces + ServerMessage union
│       └── constants.ts     # WS message types, timing values, default URLs
├── docker-compose.yml
└── tests/
    └── load_test.py         # WebSocket load test (10/25/50 concurrent users)
```

---

## Load Test

```bash
# Mock mode (measures server concurrency without external API rate limits)
MOCK_MODE=true uvicorn main:app --port 8001 &
python tests/load_test.py <persona_id> --base ws://localhost:8001

# Live mode (10→25→50 user ramp)
python tests/load_test.py <persona_id>
```

| Users | P50 | P95 | P99 | Errors |
|-------|-----|-----|-----|--------|
| 10 | 121ms | 126ms | 126ms | 0 |
| 25 | 35ms | 39ms | 40ms | 0 |
| 50 | 36ms | 40ms | 40ms | 0 |

---

## License

MIT
