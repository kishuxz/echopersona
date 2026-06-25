# Relationship-Aware Persona Context

This document extends `docs/product-spec.md` §9.3 (listener-aware retrieval). That section specifies the foundation: the live path identifies the current listener from consent/succession records, biases FAISS retrieval toward memory units involving that entity via `resolved_entity_ids`, and uses address terms from the precomputed entity graph. This document fills the gaps not yet specced: the relationship model, structured memory metadata, persona style cards, and future speaker recognition.

---

## 1. Purpose

EchoPersona should feel personal, not generic. When Sofia talks to Grandpa's twin, the response should open with "Hello Sofia dear" — not a neutral greeting. When a spouse connects, the tone should shift accordingly. The persona already knows who it is; it should also know who it is talking to and how they are connected.

The current system identifies the listener (via JWT → consent record) and injects the flattened entity graph into the system prompt. But it does not carry a structured relationship model — no `closeness_level`, no `greeting_style`, no per-listener nickname, no memory visibility tier. That is the gap this feature closes.

---

## 2. Current State vs. Desired State

### What works today

- Listener identified from Supabase JWT → matched to `consent_records.access_grants.beneficiary_user_id`
- FAISS retrieval biased toward `resolved_entity_ids` matching the listener's entity node (spec §9.3)
- Address terms pulled from the entity graph (Stage 3 alias extraction)
- `scope: full | curated` on the access grant — but `curated` is undefined (see §4 below)

### What is missing

| Gap | Impact |
|---|---|
| No `relationship_label` per listener | Persona cannot calibrate register (grandchild vs. spouse vs. friend) |
| No `nickname` per listener | Generic address term; no "Sofia dear" |
| No `closeness_level` | Cannot adjust warmth or formality gradient |
| No `greeting_style` | First message is not personalized |
| No per-unit `visibility` field | `scope: curated` has no enforcement definition |
| No `allowed_memory_visibility` per relationship | Cannot restrict sensitive memories by relationship type |
| No speaker recognition | Multi-person household cannot personalize without login switching |

---

## 3. MVP — Relationship-Aware Context from Logged-In Identity

The MVP uses the logged-in user's identity only. No voice recognition. No guessing. The listener is whoever is authenticated.

### 3.1 Conceptual data model

A `persona_relationships` table, one row per (persona, listener-user) pair:

```
persona_id                UUID        FK → personas
user_id                   UUID        FK → profiles (the listener)
relationship_label        TEXT        e.g. "granddaughter", "spouse", "close friend"
nickname                  TEXT        how the persona addresses this person, e.g. "Sofia dear"
closeness_level           INTEGER     1 (formal acquaintance) → 5 (intimate family)
greeting_style            TEXT        e.g. "warm_familial", "affectionate", "respectful"
allowed_memory_visibility TEXT[]      which visibility tiers this listener may receive,
                                      e.g. ["shared", "public"] — not ["private"]
```

This table is seeded when the subject grants access (consent flow, spec §7.2). The subject defines the nickname and relationship label as part of the access grant — not inferred by the system.

No schema migration in this slice. This is the conceptual target; the migration and backend wiring are Phase 1 build work.

### 3.2 Prompt injection

`services/rag.py` assembles the system prompt. The relationship record adds one new block injected after the entity-graph fact-spec and before the retrieved memory units:

```
## Listener relationship
Relationship: granddaughter
Address as: Sofia dear
Closeness: 5/5 (intimate family)
Greeting style: warm_familial
Memory visibility allowed: shared, public
```

This block is entirely preloaded from the database — it never triggers an extra LLM call. The live call budget stays at one Groq call.

### 3.3 Non-fabrication invariant

Relationship context personalizes tone and address. It never authorizes factual claims. The persona must not say "I remember when we..." unless a retrieved memory unit supports it. If no memory unit covers a claimed shared event, use the no-memory fallback (spec §9.7).

Correct:
> "Hello Sofia dear! It's so lovely to hear your voice."

Incorrect (fabricated):
> "Hello Sofia dear! I was just thinking about our trip to the coast last summer."
> _(unless a verified memory unit contains that event)_

### 3.4 Acceptance criterion

Given: user Sofia has `relationship_label=granddaughter`, `nickname="Sofia dear"`, `closeness_level=5`, `greeting_style=warm_familial` for the Grandpa persona.

When: Sofia sends "hello grandpa" in a live session.

Then: the persona response opens with a greeting that addresses her as "Sofia dear" (or equivalent warm address term), and the response does not assert any shared memory not present in the FAISS-retrieved memory units.

---

## 4. Structured Memory Metadata + Persona Style Cards

### 4.1 Memory unit schema expansion

Current `memory_units` schema has: `content_first_person`, `affect` (emotion/valence/intensity), `themes`, `entities`, `resolved_entity_ids`, `provenance`, `version`, `supersedes`.

Recommended additions (Phase 2 — no migration now):

```
memory_type       TEXT     e.g. "episodic", "semantic", "procedural", "relational"
topic             TEXT     short label, e.g. "childhood", "career", "family", "values"
people            TEXT[]   names of people mentioned in this unit
place             TEXT     primary location, if any
time_period       TEXT     e.g. "1960s", "early career", "retirement"
importance        INTEGER  1 (background) → 5 (defining memory)
confidence        FLOAT    fidelity pass score (0.0–1.0)
visibility        TEXT     "public" | "shared" | "private"
                           public: any authenticated listener
                           shared: only listeners with explicit access grant
                           private: subject-only; never surfaced to any listener
```

These fields enable `scope: curated` enforcement (see §4.3) and listener-relationship-aware retrieval filtering at query time.

### 4.2 Persona style cards

The voice card (spec §9.2) captures speech texture: catchphrases, humor register, filler/cadence. The style card is the text-register equivalent — how the persona writes, not how it sounds.

Fields (stored per-persona in the `personas` table or a dedicated `persona_style_cards` table):

```
tone                  TEXT     e.g. "warm", "formal", "playful", "stoic"
common_phrases        TEXT[]   phrases the persona says often
avoid_phrases         TEXT[]   words or constructions out of character
answer_length_pref    TEXT     "brief" | "moderate" | "expansive"
relationship_tone     JSONB    per-relationship-label tone override,
                               e.g. {"granddaughter": "very warm", "colleague": "formal"}
```

Style cards are mined at Stage 4 (alongside the exemplar bank) and injected into the system prompt alongside the voice card. No additional Groq call — Stage 4 already runs a Groq call; style card extraction is added to that prompt.

### 4.3 Defining `scope: curated`

`scope: curated` appears in consent/succession records (spec §2.4/§2.5) but is undefined. Recommended definition:

- `curated` = only memory units with `importance >= 3` AND `visibility IN ("shared", "public")`
- `full` = all memory units with `visibility IN ("shared", "public")` (never `private`)
- `private` units are NEVER surfaced to any listener under any scope

This is enforced at retrieval time in `services/rag.py` by filtering the FAISS candidate set before re-ranking.

---

## 5. Future — Speaker-Aware Recognition

Speaker recognition is a Phase 4 capability. It is listed here to establish the architecture direction and privacy invariants before any implementation begins.

### 5.1 What it is (and is not)

Speaker recognition identifies who is speaking in an audio stream and maps them to a known family member. It is **not authentication** — it never gates system access. It is personalization only: if we are confident it is Sofia, inject Sofia's relationship context automatically.

Voice enrollment for recognition is distinct from voice cloning. A family member enrolls a short voice sample for identification purposes; that sample is never used to synthesize speech.

### 5.2 Recognition pipeline

The audio stream from the browser reaches the WebSocket handler. Speaker recognition sits between the WebSocket audio buffer and the STT call:

```
WebSocket audio → [speaker recognizer] → Groq Whisper STT
                         │
                         ▼
                  speaker_id + confidence
                         │
                   ┌─────┴────────┐
              high (>0.85)     medium (0.6–0.85)     low (<0.6)
                   │                  │                    │
          inject relationship    ask confirmation      unknown listener
              context            in persona voice      no-memory fallback
                                 ("Is that you,        (spec §9.7)
                                  Sofia dear?")
```

Confirmation questions are delivered in the persona's voice and tracked as a special turn type — they do not consume the main live reply budget.

### 5.3 Confidence thresholds

| Band | Score | Behavior |
|---|---|---|
| High | > 0.85 | Personalize automatically; inject relationship context |
| Medium | 0.60–0.85 | Ask one confirmation question; personalize only on "yes" |
| Low | < 0.60 | Treat as unknown; use no-memory fallback; do not guess |

Thresholds are tunable via environment variable. Starting values above are defaults.

### 5.4 Consent and privacy rules

- Voice enrollment requires a dedicated consent flag (`speaker_recognition_enrolled: bool`) separate from `voice_clone` consent.
- Enrolled voice samples are stored in Supabase Storage under a separate bucket with explicit RLS; they are never co-mingled with voice clone samples.
- The subject (persona owner) must approve enrollment for each family member.
- Every enrolled user must have a deletion path — UI to remove their enrollment.
- The persona must never reveal in its response that speaker recognition occurred. The listener experiences personalization, not surveillance.
- If the speaker recognizer is unavailable, fall back to logged-in user identity (the MVP path). Never degrade to unknown-listener mode when a valid JWT is present.

### 5.5 Implementation note

No paid speaker-recognition API is approved for this project. Phase 4 implementation will evaluate open-source options (e.g., SpeechBrain speaker embeddings on CPU) that fit the no-GPU / no-new-paid-API constraints. This section is architectural guidance only.

---

## 6. Safety and Privacy Rules

These rules apply to all phases and must be enforced in `services/rag.py` and the WebSocket handler.

1. Always filter FAISS retrieval by `persona_id`. Cross-persona retrieval is never permitted.
2. Always enforce listener permission from the consent record before loading any relationship context.
3. Relationship context personalizes tone and address. It never authorizes factual claims not backed by a retrieved memory unit.
4. `visibility: private` units are never surfaced to any listener, regardless of relationship or scope.
5. `scope: curated` enforces the importance/visibility filter defined in §4.3. The RAG path must not bypass this filter.
6. No-memory fallback (spec §9.7) activates when FAISS returns no results above threshold. Relationship context does not suppress the fallback.
7. Speaker recognition state must not appear in persona responses — not as a statement, not as a hint. The listener experiences natural personalization.
8. Voice enrollment data and voice clone data are stored in separate buckets with separate consent flags.
9. If relationship context cannot be loaded (DB error, missing record), the system falls back to the address term from the entity graph (spec §9.3 baseline). It does not fail the session.

---

## 7. Non-Goals for MVP

These items are explicitly out of scope for Phase 1:

- Voice biometrics or speaker recognition
- Multi-speaker diarization
- Neo4j or GraphRAG
- Autonomous runtime agents
- Model fine-tuning
- New paid APIs
- Schema migration (this slice is architecture documentation only)
- Multi-party / family-conversation mode (more than one listener per session)

---

## 8. Phased Roadmap

| Phase | Capability | Dependency |
|---|---|---|
| **1** | Relationship-aware context from logged-in identity | `persona_relationships` table + RAG prompt injection |
| **2** | Structured memory metadata + persona style cards | Memory unit schema expansion + Stage 4 update |
| **3** | No-fabrication validator improvements + `scope: curated` enforcement | Phase 2 `visibility` field |
| **4** | Speaker recognition with enrollment, consent, and confidence thresholds | Phase 1 relationship model + open-source recognizer |
| **5** | Multimodal ingestion (transcripts/captions/summaries) + graph-style relationship memory | Phase 2 memory metadata |

Phases are sequential. Do not begin Phase 2 without Phase 1 in production. Speaker recognition (Phase 4) requires the relationship model (Phase 1) to know what to inject when recognition succeeds.
