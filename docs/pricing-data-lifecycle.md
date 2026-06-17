# EchoPersona — Pricing, Data Lifecycle & Legacy Policy

## Pricing model (planned — Stripe not yet wired)

Tiers are not finalized. This section will be updated when Stripe is integrated.

Likely structure:
- **Free** — limited persona creation (N questions), text replies only
- **Creator** — full question bank, voice clone, unlimited creation sessions
- **Legacy** — full Creator + video avatar + multi-beneficiary succession + post-activation

Entitlement checks: read `stripe_entitlements` table (Supabase). Never derive access from
frontend state or checkout redirect parameters.

---

## Data lifecycle

### Creation data
- Raw answers (text + media): written by Stage 0 synchronously, stored in Supabase Storage and
  `memory_units` table with `source_type = "answer"`.
- Corrections: new memory unit with `source_type = "correction"` and `supersedes` pointing to
  the unit being replaced. The original unit is NOT deleted (audit trail).
- Processing happens in arq worker (Stages 1–4). Failures are retried; quarantined units are
  flagged `fidelity_verified = false` and excluded from RAG.

### Memory units
- Fidelity-verified units only go into the FAISS index.
- Units remain in Supabase permanently unless the subject explicitly requests deletion.
- `resolved_entity_ids` back-links (written by Stage 3) are required before Stage 4 indexing.

### Consent records
- Written once; immutable except by the subject.
- `affirmation_media_ref` stores the recorded "yes, I consent" for legal strengthening.
- `modality_consent` controls which output modalities (voice, video, text) are active.

### Succession / activation
- Beneficiaries listed in `succession_records` with `activation_trigger`.
- `posthumous_verified` activation requires an explicit signal (not automated); TBD.
- `release_messages` are pre-written memory units unlocked at activation.

---

## Data deletion

- Subject may request full deletion: all memory units, persona record, media, consent record.
- Deletion cascades: FAISS index rebuilt after unit removal.
- Stripe subscription records: retain for financial audit purposes per payment processor requirements.
- Correction chains: when a unit is deleted, also delete its corrections (`supersedes` chain).

---

## Legacy / preservation policy

- Personas of deceased subjects remain accessible to activated beneficiaries until:
  - Explicit deletion request from designated estate contact, OR
  - Subscription lapses beyond grace period (policy TBD)
- No persona is auto-deleted without a 30-day warning (planned).
- Data portability: subject may export all raw answers and memory units (planned).

---

## Third-party data handling

| Vendor | Data sent | Retention |
|---|---|---|
| Groq | Answer transcripts (STT), answer text (evaluator), episode text (Stage 2) | Per Groq privacy policy; no training on free tier (verify) |
| ElevenLabs | Audio clips for voice cloning; TTS text | Per ElevenLabs privacy policy |
| D-ID / Tavus | Still image + audio clip for video | Per vendor privacy policy |
| Supabase | All persistent data | Hosted Postgres; EU/US region per project config |
| Upstash Redis | Ephemeral counters and cache; no PII in keys | TTL-based; auto-expires |
