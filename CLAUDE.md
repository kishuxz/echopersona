# PROGRESS.md

Terse cross-session state for Claude Code. Update at the end of every session. Read after CLAUDE.md.

## Base state (already built, working)
- EchoPersona live: real-time voice pipeline STT to RAG to LLM to TTS, ~520ms warm.
- Stack: FastAPI + React/Vite/TS + Supabase + Redis, Docker Compose on private VPC, nginx.
- FAISS in-process RAG (~2ms). ElevenLabs voice clone + TTS. D-ID video. Groq STT + LLM.
- Mock mode and latency dashboard working. Load test green to 50 users.

## Active phase
Phase 1: convert naive FAISS RAG into the persona-conditioned memory pipeline. Groq free tier only, no OpenAI, no GPU.

## Done so far (Phase 1)
- Memory unit schema and `memory_sources` / `memory_units` tables: `supabase/migrations/001_memory_tables.sql`.
- Redis + arq worker. `backend/worker/tasks/ingestion.py` runs the full pipeline: Stage 0 → 1 → 2 + Fidelity per episode → `status=done` → enqueues `enrich_persona`.
- Stage 0 normalize: pytesseract (printed) + Groq vision (`meta-llama/llama-4-scout-17b-16e-instruct`) fallback. Whisper for audio/video. `OPENAI_API_KEY` removed. Tenacity backoff on all Groq calls.
- Stage 1 episode segmentation: `stage1.py` (Groq `llama-3.1-8b-instant`, JSON mode, char-offset spans).
- Stage 2 persona-conditioned transform: `stage2.py` (first-person rewrite + stance/affect/themes/entities). Writes `memory_units`.
- Fidelity verification: `fidelity.py`. Stores `fidelity_flags` + `fidelity_score`. All units `verified=false` until family review. Migration 002 adds these columns.
- `backend/routers/ingest.py` (POST /ingest/{persona_id}, multipart, enqueues job).
- **RAG rework** (`services/rag.py`):
  - `build_index_from_units(units)` embeds `content_first_person` via sentence-transformers, stores unit dicts in FAISS.
  - `retrieve()` returns `list[dict]` (text + stance/themes/entities metadata).
  - `build_index(stories)` kept as legacy fallback.
  - `build_system_prompt()` enhanced: behavior rules (dominant stance + personality + style), entity context block (from `entity_graph`), style exemplar block (from `style_exemplars`).
  - `ws.py` RAG init: tries `memory_units` from DB (verified first, all if none), falls back to `persona.stories`.
- Stage 3 entity coreference (`stage3.py`): Groq clusters entity aliases → canonical names + descriptions. Writes `entity_graph` JSONB to personas table.
- Stage 4 style exemplar bank (`stage4.py`): Groq extracts 5-8 characteristic speech excerpts (preferring audio/video units). Writes `style_exemplars` JSONB to personas table.
- Enrichment worker (`worker/tasks/enrichment.py`): `enrich_persona(persona_id)` runs Stage 3+4, then invalidates in-memory RAG index.
- Migration 003 adds `entity_graph` + `style_exemplars` to personas table.
- `persona_store.py` selects updated to include new columns; `update_entity_graph` + `update_style_exemplars` added.

## Next actions (in order)
1. **End-to-end test**: upload a sample text/audio source via POST /ingest/{persona_id}, watch worker logs for Stage 0→1→2→Fidelity→Enrich, then open a WS session and confirm the richer system prompt fires.
2. **family review UI**: endpoint + frontend widget to show unverified units (fidelity_score < 0.9 or has_additions=true) and toggle `verified=true`.
3. Stage 5 (optional now): embed `memory_units` embeddings directly in the DB column (`embedding FLOAT4[]`) so the FAISS index can be reconstructed without re-running sentence-transformers on restart.

## Action needed from Kishore
- Run `supabase/migrations/002_fidelity_columns.sql` (if not already done).
- Run `supabase/migrations/003_persona_enrichment.sql` in Supabase SQL editor.
- System packages on VPS/Docker: `apt-get install -y tesseract-ocr poppler-utils` for OCR.
- `pip install -r requirements.txt` to pull in pytesseract, Pillow, pypdf, pdf2image, tenacity.

## Pending decisions
- Live video retrieval: Tavus-native KB vs FAISS units. Decide after Tavus free-plan test.
- Memory Lane question bank source (200 questions).
- Whether to also store embeddings in Supabase so FAISS rebuilds on restart without re-encoding.

## Blockers
- Migrations 002 and 003 must be run before end-to-end testing.

## Backlog (not now)
- Tavus CVI provider behind video toggle.
- Stripe + entitlements + pricing tiers.
- Consent, family access control, deletion.
- GPU phases: per-persona fine-tuning, self-hosted inference.

## Last session
- Reworked RAG: memory_units from DB → sentence-transformers → FAISS, enriched system prompt with entity graph + style exemplars.
- Built Stage 3 (entity coreference) + Stage 4 (style exemplar extraction) as Groq-powered passes.
- Wired enrichment worker task; ingestion pipeline auto-dispatches it after units are written.
- Added migrations 003 and updated Persona model + persona_store to include entity_graph/style_exemplars.
