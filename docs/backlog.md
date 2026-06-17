# EchoPersona — Backlog

Future ideas and deferred work. Items here are NOT committed to; they require explicit prioritization
before implementation. Do not implement from this list without confirmation.

---

## Build steps (committed sequence — see PROGRESS.md for current state)

- [ ] Step 5b — Consent capture (spec §7.2)
- [ ] Step 5c — Succession / beneficiary intent (spec §7.3)
- [ ] Step 6 — Live-path additions: precomputed voice card, listener-aware retrieval, no-memory
      fallback, attunement in single live call (spec §8, §9.2–9.4, §9.7)
- [ ] Step 7 — Resonance extras: feedback loop, across-conversation memory (flag-gated), optional TTS

---

## Payments (not started)

- Stripe checkout sessions for subscription plans
- Stripe webhook handler (verify signature, idempotent, update entitlements table)
- `stripe_entitlements` Supabase table + RLS
- Frontend paywall / upgrade prompts

---

## Media pipeline

- Tavus video AI integration (async, non-blocking; mirrors D-ID pattern)
- Improve voice clone quality: require minimum audio duration before ElevenLabs clone
- Video avatar quality: evaluate Simli vs D-ID vs Tavus for latency

---

## RAG / persona quality

- Fold fidelity pass into Stage 2 (one Groq call instead of two per episode) — spec §10 decision 2
- Upgrade embeddings from sentence-transformers to OpenAI text-embedding-3-small for better retrieval
- Semantic cache for repeated live-path queries (Redis; spec §9.5)
- Across-conversation summarizer (flag-gated; spec §9.6)

---

## Operational

- Monitoring / alerting for Groq RPM headroom (expose Redis counter to an admin endpoint)
- Structured logging with correlation IDs across creation → ingestion → live paths
- Admin dashboard: persona health, ingestion queue depth, fidelity pass rate

---

## UX / frontend

- Creation flow UI (question carousel, recording, progress indicator)
- Consent and succession UI (spec §7.2, §7.3)
- Listener conversation UI (voice-first, text fallback)
- Persona gallery / management for subjects
