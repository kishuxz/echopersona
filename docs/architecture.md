# EchoPersona — Technical Architecture

## System overview

```
Browser (React/Vite/TS)
     │  HTTPS / WSS
     ▼
FastAPI backend (uvicorn)
     ├── Supabase Postgres   — persistent source of truth
     ├── Supabase Storage    — media (voice samples, video answers)
     ├── Supabase Auth       — JWT issuance and verification
     ├── Redis (Upstash TLS) — rate counters, job status, semantic cache
     ├── arq worker          — async batch ingestion (Stages 1–4)
     └── Groq API            — LLM + Whisper STT (shared 30 RPM pool)
```

## Three execution contexts

| Context | Triggered by | LLM allowed? | Latency budget |
|---|---|---|---|
| **Creation** (interactive) | Subject answering questions | Evaluator only (1 Groq call/answer) | ~1–3s per answer; never blocks subject |
| **Ingestion** (batch, arq) | Session pause/end | Yes — Stages 1–4 transforms, fidelity | No UI deadline; throttled by RPM |
| **Live reply** (interactive) | Listener turn | 1 Groq call — the reply | < 600ms warm |

## Backend routers

| Router | File | Purpose |
|---|---|---|
| `/creation/*` | `routers/creation.py` | Question bank, answer capture, evaluator loop |
| `/ingest/*` | `routers/ingest.py` | Trigger / status for arq ingestion |
| `/persona/*` | `routers/persona.py` | Persona CRUD, voice/avatar upload |
| `/review/*` | `routers/review.py` | Self-review correction loop (step 5a) |
| `/ws/{session_id}` | `routers/ws.py` | Live WebSocket: STT → LLM → TTS pipeline |
| `/health` | `routers/health.py` | Health check + keepalive |

## Ingestion pipeline (arq worker)

```
Stage 0  normalize + provenance  (synchronous, in-request; no LLM)
Stage 1  episode segmentation    (Groq call, batch)
Stage 2  persona transform       (Groq call per episode; writes memory units)
Stage 3  entity coreference      (Groq call, per persona; writes entity_graph + resolved_entity_ids)
Stage 4  style exemplar bank     (Groq call; writes style vectors)
Fidelity verification pass       (Groq call; marks units verified or quarantined)
```

Interactive calls (evaluator, live reply) preempt ingestion when the 30 RPM window is tight.

## Live reply path

```
WebSocket audio → Groq Whisper STT (~105ms)
                → FAISS top-k retrieval (~2ms)
                → assemble prompt (memory units + persona card + entity graph + listener ctx)
                → Groq LLM first token (~200ms)
                → sentence boundary chunker
                → ElevenLabs / Cartesia TTS async (~330ms / ~80ms)
Total warm: ~520ms (text committed before TTS starts)
```

## Data model (key tables)

| Table | Source of truth for |
|---|---|
| `profiles` | user identity |
| `personas` | persona metadata, entity_graph JSON |
| `memory_units` | all verified memory; content_first_person, affect, themes, provenance |
| `conversations` | session records |
| `consent_records` | subject modality consent (planned — step 5b) |
| `succession_records` | beneficiary intent (planned — step 5b) |
| `stripe_entitlements` | billing/access tier (planned — step 7+) |

## Services map

| Service | File | Role |
|---|---|---|
| LLM | `services/llm.py` | Groq / vLLM streaming |
| STT | `services/stt.py` | Groq Whisper + Deepgram fallback |
| TTS | `services/tts.py` / `tts_cartesia.py` | ElevenLabs / Cartesia |
| RAG | `services/rag.py` | FAISS index + system prompt assembly |
| Creation | `services/creation.py` | State machine + evaluator wiring |
| Groq limiter | `services/groq_limiter.py` | RPM token bucket + Redis counter |
| Stage 0–4 | `services/ingestion/stage*.py` | Batch transforms |
| DB | `services/db.py` | Supabase Postgres access layer |
| Persona store | `services/persona_store.py` | Persona CRUD over Supabase |
| Audio store | `services/audio_store.py` | Supabase Storage write/read |

## Infrastructure

- **Docker Compose** — backend (FastAPI), frontend (nginx), Redis for local dev
- **Render.com** — backend FastAPI service (`rootDir: backend`)
- **Vercel** — frontend static SPA (`rootDir: frontend`)
- **Supabase** — auth, Postgres, Storage (hosted)
- **Upstash Redis** — TLS Redis for production rate limiting and cache
- **nginx** — reverse proxy + SSL termination in production VPS

## Planned additions

- **Stripe** — checkout, subscriptions, webhooks, entitlements table
- **Tavus** — video AI (async, non-blocking; same constraint as D-ID)
- **OpenAI embeddings** — optional upgrade path from sentence-transformers for RAG
- **Relationship-aware persona context** — listener-identity-driven tone, greeting style, and memory visibility filtering; see `docs/relationship-aware-persona-context.md`
