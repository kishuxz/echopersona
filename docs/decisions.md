# EchoPersona — Decision Log

Append new entries at the bottom. Do not delete past decisions; mark them superseded if reversed.

---

## [2026-06] Supabase is the persistent source of truth

**Decision:** All persistent state (personas, memory units, sessions, consent, entitlements) lives in
Supabase Postgres. No other store is authoritative for persistent data.

**Rationale:** Single consistent RLS-enforced store; Supabase Auth JWT flows naturally into row-level
security; hosted Postgres with zero ops overhead for this scale.

---

## [2026-06] Redis is temporary state only

**Decision:** Redis (Upstash) is used exclusively for: Groq RPM/RPD rate-limit counters, semantic
prompt cache, arq job status, and short-lived session state. Nothing written to Redis is the source
of truth for billing, persona data, or consent.

**Rationale:** Redis is ephemeral and can be flushed. Treating it as a cache avoids data loss
surprises; all durable state lives in Supabase.

---

## [2026-06] Heavy ingestion runs in arq worker only

**Decision:** Stages 1–4 of ingestion (episode segmentation, persona transform, entity coreference,
style exemplar bank, fidelity) run exclusively in the arq background worker. They never run inside
a FastAPI request handler or a Supabase Edge Function.

**Rationale:** These stages make multiple Groq calls and can take tens of seconds per persona.
Running them synchronously would block the web server and exhaust the RPM budget on the live path.

---

## [2026-06] RAG / persona transformation is a build-time property

**Decision:** All persona conditioning happens at ingestion time (Stages 1–4). The live reply path
retrieves already-persona-conditioned memory units. No persona reasoning at query time.

**Rationale:** Keeps live latency predictable and cheap (FAISS ~2ms retrieval). Fidelity is
enforced by construction: only fidelity-verified units enter the index.

---

## [2026-06] Live video retrieval must not block the reply

**Decision:** D-ID / Simli / Tavus video generation is always fired asynchronously after the text
reply is committed to the client. The WebSocket sends `text_reply`, then triggers video in the
background, then sends `video_ready` when available.

**Rationale:** Video generation takes 5–30s. Blocking the reply on it would violate the 600ms
latency constraint and frustrate listeners.

---

## [2026-06] Stripe entitlements table is billing source of truth

**Decision:** When Stripe is wired in, the `stripe_entitlements` Supabase table (updated by
webhook handler) is the only authoritative signal for feature access. Frontend and API handlers
read from it; they do not trust URL parameters or checkout redirect signals.

**Rationale:** Webhooks arrive asynchronously; checkout redirects can be replayed or tampered with.
Idempotent webhook handling + entitlements table is the standard safe pattern.

---

## [2026-06] Markdown sprawl is forbidden

**Decision:** No new markdown files may be created without explicit approval. The approved file list
is enumerated in `CLAUDE.md` under Documentation rules. If documentation doesn't fit an existing
file, ask before creating a new one.

**Rationale:** Multiple conflicting markdown files caused context sprawl and outdated information
being used during builds. Single source of truth per concern.

---

## [2026-06] No GPU, no paid LLM APIs in the core path

**Decision:** All LLM, STT, and OCR in the core path uses Groq free tier (or Tesseract CPU for
OCR). ElevenLabs and D-ID are separate non-Groq quotas and are optional/async. No GPU required.

**Rationale:** Cost constraint. Groq free tier is sufficient for the current scale; the architecture
can swap to paid Groq or local vLLM via `USE_VLLM=true` without code changes.
