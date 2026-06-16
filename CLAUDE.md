# EchoPersona / Living Forever AI — Project Guide

Persona-twin product on the existing EchoPersona codebase. Living people build an AI twin
(voice, stories, personality) by answering a vetted question bank; chosen family talk to the twin.
Building chat + chat-twin now; video avatar later.

## Read before building
- `docs/persona_spec.md` — **authoritative** spec for persona creation, the answer evaluator,
  the live conversation path, and resonance mechanisms. Follow its data contracts exactly,
  especially §2 (schemas) and §4 (evaluator I/O JSON). Do not invent fields.

## Hard constraints — never violate
- **Latency:** live reply < 600ms warm. The reply is ONE bounded LLM call. TTS is async — never block text on audio.
- **Fidelity:** never assert a fact absent from the verified memory units / flattened entity-graph fact-spec.
  When retrieval is empty, use the in-character no-memory fallback (spec §9.7). Do not fabricate.
- **No agents.** Only bounded single-shot LLM calls: ingestion transforms (batch), the answer evaluator
  (creation-time), the live reply, and the optional across-conversation summarizer (spec §9.6, flag-gated).
- **No GPU. No paid APIs.** All LLM/STT/vision-OCR via Groq free tier (Tesseract is the OCR-only CPU fallback).
  ElevenLabs + D-ID are separate, non-Groq quotas.
- **Groq ~1000 req/day, shared across ALL call types.** Budget it (spec §1.1). Interactive calls
  (evaluator, live reply) must preempt batch ingestion. Track a daily counter in Redis; the arq worker self-throttles.

## Use CodeGraph (MCP) to navigate
- Query the CodeGraph MCP server to locate definitions, find callers, and trace dependency edges
  BEFORE editing. Do not blind-grep. Use it to find the impact radius of any change.
- The index reflects THIS repo (the laptop tree) — which is the code you edit.

## Known drift — RESOLVED
- Deepgram startup/mock checks were removed in `stt.py` and `main.py` and committed (step 2).

## Build order (slice by slice; confirm each compiles before the next)
1. ✅ Question bank data + loader (static data from spec §5.3; no LLM).
2. ✅ Creation state machine + capture: text, and a/v → Groq Whisper STT → answer_text (spec §3).
   - `services/creation.py`, `routers/creation.py`, `tests/test_creation.py` — 31 tests green.
   - Migration `migrations/004_creation_fields.sql` — **run manually in Supabase SQL editor before exercising the live endpoint** (idempotent).
   - Evaluator is a placeholder slot in `deterministic_next_action`; step 3 wires it in.
3. Answer evaluator: the bounded Groq call + code guardrails + deterministic fallback (spec §4).
4. Creation → ingestion handoff: write raw + provenance (Stage 0), add `source_type` and
   `supersedes` for corrections (spec §6).
5. Consent + succession capture (spec §7.2, §7.3).
6. Live-path additions: precomputed voice card, listener-aware retrieval, no-memory fallback,
   attunement folded into the single live call (spec §8, §9.2–9.4, §9.7).
7. Resonance extras: feedback loop, across-conversation memory (flag-gated), optional TTS.

## Stack & conventions
FastAPI backend · React/Vite/TS frontend · Supabase (auth/Postgres/storage) · Redis · arq worker ·
Docker Compose on a private VPC · nginx. Keep every change deterministic and auditable for fidelity.