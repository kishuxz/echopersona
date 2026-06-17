# Living Forever AI — Persona Creation & Conversation Spec

**Audience:** Claude Code (and you).
**Status:** Authoritative spec for the next build phase. Implements on top of the existing EchoPersona codebase, the Stage 0–4 ingestion pipeline + fidelity pass, and the live reply path already in place.
**Scope of this doc:** persona creation flow, the question bank (with modality tags + probes), the answer-evaluator contract, the living-subject features, the live conversation path, and the resonance mechanisms. It does **not** redefine the ingestion internals (Stages 0–4 are built); it specifies the contracts at the seams.

---

## 0. How this fits what already exists

```
                        CREATION (interactive)                 INGESTION (batch, arq)              LIVE (interactive)
  ┌─────────────┐   ┌──────────────┐   ┌────────────┐     ┌─────────────────────────────┐    ┌──────────────────────┐
  │ Question    │──▶│ Capture      │──▶│ Evaluator  │     │ Stage 0 normalize+provenance│    │ FAISS top-k (~2ms)   │
  │ bank (this  │   │ text OR a/v  │   │ (1 Groq    │     │ Stage 1 episode segmentation│    │ + persona prompt     │
  │ doc)        │   │  → Whisper   │   │  call,     │     │ Stage 2 persona transform   │    │ + voice card         │
  └─────────────┘   │  STT)        │   │  this doc) │     │ Stage 3 entity coreference  │    │ + flattened entity   │
                    └──────┬───────┘   └─────┬──────┘     │ Stage 4 style exemplar bank │    │   graph (fact-spec)  │
                           │                 │            │ + fidelity verification pass│    │ + listener context   │
                           ▼                 ▼            └──────────────┬──────────────┘    │ → ONE Groq reply call│
                    Stage 0 writes      ask_probe /                      │                   └──────────┬───────────┘
                    raw + provenance    steer / advance                  ▼                              ▼
                    synchronously       (probe ids only)         memory units +              text reply <600ms warm
                                                                 entity graph JSON           (optional async TTS)
```

Three things to hold onto, because the whole design rests on them:

1. **Persona work happens at ingestion, not query time.** The live path never does persona reasoning; it retrieves already-persona-conditioned memory units and assembles a precomputed prompt. RAG is plumbing, not the persona.
2. **Fidelity is a build-time property.** The transform's "assert nothing outside source" rule + the entity graph as fact-spec mean the runtime doesn't need a verification call. Runtime fidelity is enforced *by construction*: only verified units go in, strong prompt constraints, and a no-memory fallback (§9.7).
3. **No agents. Only bounded single-shot LLM calls.** This doc adds exactly one new optional call type (across-conversation summarizer, §9.6) and flags it explicitly in §10. Everything else maps to calls you already allow.

---

## 1. Constraints & budgets (non-negotiable)

| Constraint | Rule |
|---|---|
| Live latency | < 600ms warm, text reply. TTS is additive and async — never block text on audio. |
| Fidelity | Never assert a fact absent from the verified memory units / entity-graph fact-spec. No-memory fallback instead of fabrication. |
| Architecture | No agents. Only bounded single-shot calls: ingestion transforms (batch), the answer evaluator (creation), the live reply, and the optional summarizer (§9.6). |
| Compute | No GPU. No paid APIs. Groq free tier for all LLM/STT/vision-OCR (Tesseract CPU fallback for OCR). ElevenLabs + D-ID credits are separate, non-Groq quotas. |
| Groq limits | Free tier: **30 requests/minute** (one ~every 2s) shared across all call types — this is the real-time bottleneck, not a daily total. Per-model RPD is high (~14,400/day on `llama-3.1-8b-instant`; Whisper ~2,000/day for a/v capture) per current published limits — **verify in the Groq console**, quotas shift. Budget against RPM (§1.1). |

### 1.1 Groq request budget (the bottleneck is RPM, not a daily total)

> **Correction (verify in console):** earlier drafts assumed ~1000 req/day. Current published free-tier
> limits are higher — ~14,400/day on `llama-3.1-8b-instant`, ~2,000/day on Whisper — at **30 requests/minute**.
> So daily volume is unlikely to bind at your scale; the **30 RPM ceiling** (shared across live replies,
> evaluator calls, and batch ingestion) is what to engineer around. Re-confirm against your account; if your
> tier differs, the math below scales accordingly.

A full persona creation still costs calls, but the concern is concurrency, not exhaustion:

- Evaluator: ~1 call per answer (≈52 over a 40-question session) — on `llama-3.1-8b-instant`.
- Stage 2 transform: ~1 per episode (≈80) + fidelity (≈80, currently separate — §10 decision 2).
- Stage 3 coreference: batched per persona (~3–8).
- Whisper STT: 1 per recorded a/v answer — watch the ~2,000/day Whisper limit specifically.

Engineering rules, in priority order:

1. **Rate-limit by RPM, not RPD.** A token-bucket on the Groq client (≤30/min) is the core control.
2. **Priority queue:** interactive calls (evaluator, live reply) preempt batch ingestion. When the RPM window
   is tight, the arq ingestion worker backs off — never the live path.
3. **Batch multiple episodes per transform call** where they share a source answer.
4. **Degrade the evaluator first** under pressure: the §4.4 deterministic fallback costs zero Groq calls.
5. Folding fidelity into Stage 2 (§10 decision 2) remains a pre-scale optimization, not urgent now.

Track per-minute and per-day counters in Redis; expose them so the worker self-throttles.

---

## 2. Data contracts

### 2.1 Question bank entry

```yaml
# One entry in the question bank. The bank is vetted, static data — not generated.
- id: q_origins_01                  # stable, referenced everywhere (provenance, evaluator)
  category: origins                 # Memory Lane category key (§5.1)
  order: 10                         # sort key within category (gaps of 10 for inserts)
  modality: video_audio             # text | video_audio  (tagging rule in §5.2)
  required: false                   # true => must be answered to complete creation
  prompt: "..."                     # the main question shown to the subject
  intent: "..."                     # what persona signal this targets (for humans + ingestion)
  signals: [affect, voice_texture]  # what ingestion should mine; informs evaluator scoring
  max_followups: 2                  # hard cap on probes for this question
  probes:                           # 2–3 VETTED depth probes, priority order. Evaluator SELECTS, never authors.
    - id: q_origins_01_p1
      prompt: "..."
      good_when: shallow            # hint: when this probe adds value (shallow|missing_signal|specific_thread)
    - id: q_origins_01_p2
      prompt: "..."
      good_when: missing_signal
```

### 2.2 Evaluator I/O — see §4.

### 2.3 Memory unit (RECONCILED with the built code — this is the contract Claude Code must follow)

The built `MemoryUnit` differs from the early draft of this spec. The code's names and richer types win;
the spec is corrected here. Tags below: **[code]** already exists, **[add-004]** add in the alignment
migration before step 2's Stage 0 write, **[stage3]** written back by Stage 3 enrichment (needed by §9.3, step 6).

```jsonc
{
  "unit_id": "uuid",                       // [code] (was "id" in draft)
  "persona_id": "…",                       // [add-004] passed to write_memory_unit() but not on the model — add it
  "content_first_person": "…",             // [code] persona-conditioned rewrite (was "text" in draft)
  "stance": "…",                           // [code]
  "affect": {                              // [code] STRUCTURED — keep it, do NOT flatten to tag-strings
    "emotion": "wistful",                  //        dominant emotion (the "tag")
    "valence": -0.2,                       //        attunement (§9.4) matches valence to listener register
    "intensity": 0.7                       //        and can rank units by intensity
  },
  "themes": ["childhood","father"],        // [code]
  "entities": {                            // [code] RAW mentions from Stage 2 (not resolved IDs)
    "people": ["my father"], "places": ["the old house"], "period": "…"
  },
  "resolved_entity_ids": ["ent_father"],   // [stage3] back-link to persona.entity_graph nodes — REQUIRED for §9.3
  "provenance": {
    "source_question_id": "q_origins_01",  // [add-004] CRITICAL — code only had question_category + question_text
    "question_category": "origins",        // [code] keep
    "modality": "video_audio",             // [code]
    "media_ref": "storage://…",            // [add-004] storage URL; reconcile with existing file_id (path)
    "captured_at": "ISO-8601",             // [add-004]
    "source_type": "answer"                // [add-004] answer | correction — default "answer" (§7.1)
  },
  "version": 1,                            // [add-004] default 1
  "supersedes": null                       // [add-004] unit_id this replaces, for corrections (§6/§7.1)
}
```

**Why structured `affect` stays:** valence + intensity give attunement (§9.4) more to work with than bare tags —
you can rank units by intensity and match valence to the listener's register. The live path flattens it into
the prompt (e.g. "wistful, gently"). Multi-emotion units can wait for v2.

**Why the entity back-link:** §9.3 listener-aware retrieval needs "units involving entity X" cheaply at query
time. Stage 3 already resolves coreference into `persona.entity_graph`; it must also write `resolved_entity_ids`
onto each unit so the live path filters by ID instead of string-matching mentions at query time (which would
violate the "no persona work at query time" rule). Deferred to step 6, but the field shape is fixed now.

### 2.4 Consent record (§7.2)

```jsonc
{
  "persona_id": "…",
  "subject_user_id": "…",
  "captured_at": "…",
  "version": 1,
  "modality_consent": { "voice_clone": true, "video_avatar": false, "text_twin": true },
  "access_grants": [
    { "beneficiary_user_id": "…", "relationship": "daughter",
      "scope": "full|curated", "activation": "immediate|posthumous" }
  ],
  "rights": { "subject_may_delete": true, "subject_may_review": true },
  "affirmation_media_ref": "storage://…"   // optional recorded "yes, I consent" — strengthens the record
}
```

### 2.5 Succession / beneficiary intent (§7.3)

```jsonc
{
  "persona_id": "…",
  "beneficiaries": [
    { "user_id": "…", "relationship": "son", "address_term": "kiddo",
      "scope": "full", "activation_trigger": "posthumous_verified",
      "release_messages": ["mu_or_message_id", "…"] }
  ]
}
```

---

## 3. Persona creation flow

A deterministic state machine. The only LLM call inside it is the evaluator. STT is a Groq Whisper call on captured audio (counts toward the cap; see §3.2).

```
START
  └─▶ SELECT_NEXT_QUESTION   (coverage-ordered; required questions never skipped)
        └─▶ SERVE_QUESTION
              └─▶ CAPTURE  ── text? ──▶ answer_text
              │            └ a/v? ──▶ upload media → Whisper STT → answer_text (+ keep media_ref)
              └─▶ STAGE_0_WRITE  (raw answer + provenance, synchronous; queues nothing heavy)
                    └─▶ EVALUATE  (1 Groq call, §4)
                          ├─ next_action = ask_probe  & followups < cap ─▶ SERVE_PROBE(probe_id) ─▶ CAPTURE …
                          ├─ next_action = steer ─▶ SERVE_STEER(steer_id) ─▶ re-CAPTURE same question
                          └─ next_action = advance (or cap hit / saturated) ─▶ SELECT_NEXT_QUESTION
  └─▶ ON_SESSION_PAUSE/END
        └─▶ enqueue answers for batch ingestion (Stages 1–4 + fidelity) via arq
```

### 3.1 Ordering & coverage
- Walk categories in the §5.1 order; within a category, by `order`.
- `required: true` questions (consent, succession, a small core legacy set) are always served and cannot be skipped.
- Track per-`signal` coverage across the session. When the evaluator reports a signal already saturated elsewhere, it may `advance` with `skip_reason: covered_elsewhere` even if probes remain (this is also how over-answering is absorbed — alongside Stage 1 segmentation/dedup downstream).

### 3.2 Modality handling
- **text:** answer captured as typed text. No STT.
- **video_audio:** capture media → extract audio (video) → **Groq Whisper STT** → `answer_text`. Keep `media_ref` in provenance regardless; it feeds the voice clone (ElevenLabs) and later video avatar. STT is one Groq call per recorded answer — include it in the §1.1 budget (it's modest but real).
- Tesseract is the OCR fallback for *images/documents*, not for speech. Do not route audio through it.

### 3.3 Robustness
- Creation must survive Groq rate-limiting. If the evaluator call fails/times out/returns invalid JSON, take the deterministic fallback (§4.4) and keep moving. Never block the subject on the cap.
- Stage 0 write is synchronous and cheap (no LLM). Heavy ingestion is deferred to the worker so the subject never waits on it.

---

## 4. The answer evaluator

A single bounded Groq call per answer. **Creation-time only — never on the live path**, so its latency budget is loose (~1–3s acceptable). Its job is to score the answer and pick the next *prepared* move. It does **not** author questions.

### 4.1 Input

```jsonc
{
  "question": { "id": "q_origins_01", "prompt": "…", "category": "origins",
                "intent": "…", "signals": ["affect","voice_texture"] },
  "prepared_probes": [                       // ONLY these ids are selectable
    { "id": "q_origins_01_p1", "prompt": "…", "good_when": "shallow" },
    { "id": "q_origins_01_p2", "prompt": "…", "good_when": "missing_signal" }
  ],
  "answer_text": "…",                         // post-STT if it was a/v
  "session_state": {
    "followups_used_this_question": 1,
    "max_followups": 2,
    "signal_coverage": { "affect": "saturated", "voice_texture": "partial" },
    "topics_well_covered": ["father","hometown"]   // running, for dedup-aware skipping
  }
}
```

### 4.2 Output (strict JSON — validate it)

```jsonc
{
  "answered": true,
  "answer_quality": {
    "depth": "shallow|adequate|rich",
    "on_topic": true,
    "multi_topic": false,
    "topics_touched": ["father","first home"],
    "signals_present": ["affect"]
  },
  "next_action": "ask_probe|advance|steer",
  "probe_id": "q_origins_01_p2",   // REQUIRED iff ask_probe; MUST be one of prepared_probes ids
  "steer_id": "refocus",           // REQUIRED iff steer; one of the global steering ids (§5.4)
  "skip_reason": "saturated|capped|covered_elsewhere|low_value|null",  // when advancing with probes left
  "confidence": 0.0
}
```

### 4.3 Hard guardrails (enforced in code, around the model)
- `probe_id` **must** be in `prepared_probes`. If not → treat as `advance`. The model can never introduce a question.
- Enforce `max_followups` in code regardless of model output. At the cap, force `advance`.
- If `signal_coverage` shows all target signals saturated → bias to `advance` (let code override `ask_probe`).
- **Conservative by default:** when `confidence` < 0.5 or output is ambiguous → `advance`. The product should under-pester, not over-pester. A twin built from a frustrated subject is worse than one with a slightly thinner answer.

### 4.4 Deterministic fallback (zero Groq calls)
On call failure / timeout / invalid JSON / rate-limit:
1. If `followups_used == 0` and the raw answer is < N chars (configurable, e.g. 120) → serve `probes[0]` (the highest-priority prepared probe), once.
2. Otherwise → `advance`.

This keeps creation fully functional when the Groq cap is exhausted.

---

## 5. The question bank

### 5.1 Memory Lane categories (order = creation order)

| key | name | typical default modality |
|---|---|---|
| `origins` | Origins & Early Childhood | video_audio |
| `family` | Family & Relationships | video_audio |
| `coming_of_age` | Coming of Age & Youth | video_audio |
| `love` | Love & Partnership | video_audio |
| `work` | Work & Vocation | text-leaning |
| `beliefs` | Beliefs, Values & Worldview | mixed |
| `texture` | Joys, Humor & Everyday Texture | video_audio |
| `hardship` | Hardship & Resilience | mixed |
| `places` | Places & Homes | text-leaning |
| `legacy` | Legacy, Wisdom & Messages | video_audio |
| `_consent` | Consent & Succession (required) | text + recorded affirmation |

### 5.2 Modality tagging rule
Tag `video_audio` when the *delivery* carries persona signal — emotional storytelling, humor, relationships, catchphrases, legacy messages — because those answers feed the voice clone and surface affect + speech texture. Tag `text` when the *content* is the point and delivery isn't — factual lists, structured timelines, or sensitive items a subject would rather type than perform. When in doubt for emotionally rich content, prefer `video_audio`; you can always also keep the transcript.

### 5.3 Seed bank (extensible — authoring guide in §5.5)

```yaml
questions:
  # ── origins ──────────────────────────────────────────────────────────
  - id: q_origins_01
    category: origins
    order: 10
    modality: video_audio
    required: false
    prompt: "Where did you grow up, and what's the first place that feels like 'home' when you close your eyes?"
    intent: "Anchor a vivid origin scene; capture how the subject narrates place + sensory memory."
    signals: [affect, voice_texture, themes]
    max_followups: 2
    probes:
      - id: q_origins_01_p1
        prompt: "Walk me through that place — what did you hear, smell, or see first when you came home?"
        good_when: shallow
      - id: q_origins_01_p2
        prompt: "Who else was usually there with you?"
        good_when: missing_signal

  - id: q_origins_02
    category: origins
    order: 20
    modality: video_audio
    required: false
    prompt: "What's a story your family always told about you as a child?"
    intent: "Capture family-myth narration + humor register; seeds entity aliases (who tells it)."
    signals: [voice_texture, humor, entities]
    max_followups: 2
    probes:
      - id: q_origins_02_p1
        prompt: "Who told it best, and how did they tell it?"
        good_when: specific_thread
      - id: q_origins_02_p2
        prompt: "Was it true, or did it grow a little over the years?"
        good_when: shallow

  # ── family ───────────────────────────────────────────────────────────
  - id: q_family_01
    category: family
    order: 10
    modality: video_audio
    required: false
    prompt: "Tell me about the people you grew up with — who shaped you most?"
    intent: "Primary entity seeding + relationship stance + what they CALL people (aliases)."
    signals: [entities, affect, voice_texture]
    max_followups: 3
    probes:
      - id: q_family_01_p1
        prompt: "What did you call them — by name, a nickname, something only you used?"
        good_when: missing_signal          # directly feeds entity-graph aliases / address terms
      - id: q_family_01_p2
        prompt: "What's one thing you learned from them that you still carry?"
        good_when: shallow
      - id: q_family_01_p3
        prompt: "Was there tension there too? It's okay if it wasn't simple."
        good_when: specific_thread

  # ── love ─────────────────────────────────────────────────────────────
  - id: q_love_01
    category: love
    order: 10
    modality: video_audio
    required: false
    prompt: "Tell me about a love that mattered — how did it begin?"
    intent: "Capture warmth/affect, address terms for a partner, narrative cadence."
    signals: [affect, voice_texture, entities]
    max_followups: 2
    probes:
      - id: q_love_01_p1
        prompt: "What did you call each other?"
        good_when: missing_signal
      - id: q_love_01_p2
        prompt: "What's a small ordinary moment with them you'd want remembered?"
        good_when: shallow

  # ── work ─────────────────────────────────────────────────────────────
  - id: q_work_01
    category: work
    order: 10
    modality: text
    required: false
    prompt: "What kinds of work have you done over the years? Walk me through it."
    intent: "Factual vocational timeline — content over delivery; seeds entities (places, roles)."
    signals: [entities, themes]
    max_followups: 1
    probes:
      - id: q_work_01_p1
        prompt: "Which of those felt most like 'you'?"
        good_when: shallow

  # ── beliefs ──────────────────────────────────────────────────────────
  - id: q_beliefs_01
    category: beliefs
    order: 10
    modality: video_audio
    required: false
    prompt: "What do you believe about how a person should live? Where did that come from?"
    intent: "Capture stance + values + the voice they use when they get serious."
    signals: [stance, affect, voice_texture]
    max_followups: 2
    probes:
      - id: q_beliefs_01_p1
        prompt: "Has that belief ever been tested?"
        good_when: shallow
      - id: q_beliefs_01_p2
        prompt: "Is there something you used to believe and changed your mind about?"
        good_when: missing_signal

  # ── texture ──────────────────────────────────────────────────────────
  - id: q_texture_01
    category: texture
    order: 10
    modality: video_audio
    required: false
    prompt: "What's a phrase or expression people would recognize as yours?"
    intent: "DIRECT speech-texture capture — catchphrases for the voice card (§9.2)."
    signals: [voice_texture, humor]
    max_followups: 2
    probes:
      - id: q_texture_01_p1
        prompt: "When do you find yourself saying it?"
        good_when: shallow
      - id: q_texture_01_p2
        prompt: "What about something that makes you laugh every time?"
        good_when: missing_signal

  # ── hardship ─────────────────────────────────────────────────────────
  - id: q_hardship_01
    category: hardship
    order: 10
    modality: video_audio
    required: false
    prompt: "Tell me about a hard stretch in your life and how you got through it."
    intent: "Capture resilience stance + somber affect register (matters for attunement, §9.4)."
    signals: [affect, stance, themes]
    max_followups: 2
    probes:
      - id: q_hardship_01_p1
        prompt: "Who, or what, helped?"
        good_when: shallow
      - id: q_hardship_01_p2
        prompt: "What would you say to someone going through that now?"
        good_when: specific_thread

  # ── places ───────────────────────────────────────────────────────────
  - id: q_places_01
    category: places
    order: 10
    modality: text
    required: false
    prompt: "List the homes and places you've lived. A line each is fine."
    intent: "Factual place entities for the graph; content over delivery."
    signals: [entities]
    max_followups: 1
    probes:
      - id: q_places_01_p1
        prompt: "Which one would you go back to if you could?"
        good_when: shallow

  # ── legacy ───────────────────────────────────────────────────────────
  - id: q_legacy_01
    category: legacy
    order: 10
    modality: video_audio
    required: true
    prompt: "If the people you love could hear one thing from you, years from now, what would it be?"
    intent: "Core legacy message — high-affect, voice-clone gold. Often released per §7.3."
    signals: [affect, voice_texture, stance]
    max_followups: 1
    probes:
      - id: q_legacy_01_p1
        prompt: "Is there someone specific you'd want to say something just to?"
        good_when: shallow
```

### 5.4 Global steering bank (vetted; selected by the evaluator via `steer_id`)

```yaml
steering:
  refocus: "I love that — let's hold that thread for a second. Coming back to {topic}, what comes to mind?"
  wrap_up: "That's a rich one. Before we move on, is there anything you'd want to add?"
  too_short: "Take your time — even a small detail or a single moment helps."
  sensitive_ok: "You can share as much or as little as you'd like here."
```

`{topic}` is filled from the current question's category/intent in code — the evaluator only chooses the steer id.

### 5.5 Authoring guide (for extending the bank)
- 1 main question per row; 2–3 probes; probes must *deepen*, never restate.
- Every probe is independently sensible if asked cold (the evaluator may pick `p2` without `p1`).
- Set `signals` honestly — it drives evaluator scoring and §3.1 saturation skipping.
- Use `modality` per §5.2. If a question is borderline, pick `video_audio` and rely on the transcript for content.
- Keep `max_followups` low (1–2 typical, 3 only for foundational questions like `q_family_01`). Conservative beats exhaustive.

---

## 6. Ingestion handoff

Answers and probes captured in a session are enqueued for batch ingestion at session pause/end. The contract Stage 0 receives is the raw answer + the §2.3 provenance block. Stages 1–4 + the fidelity pass are unchanged.

The only additions this doc requires:

- **`source_type` in provenance:** `answer` (creation) or `correction` (§7.1). The fidelity rule is identical for both — the text is treated as the new source of truth.
- **Versioning / `supersedes`:** corrections produce memory units that point at the unit(s) they replace. Retrieval must prefer the latest non-superseded version. Keep old versions for audit, exclude them from live retrieval.

---

## 7. Living-subject features

These are the things the living-subject model unlocks that a posthumous-only product can't do.

### 7.1 Self-review / correction loop
1. Subject talks to their own twin (same live path, listener = self).
2. On any reply, subject can **flag** it: `wrong_fact | wrong_tone | missing | good`.
3. `wrong_fact` → subject supplies the correction text. It's captured as a normal answer with `source_type: correction` and re-enters ingestion (Stages 0–4 + fidelity). Resulting memory units `supersede` the offending ones (§6).
4. `wrong_tone` → routes to Stage 4 style-exemplar tuning, not the fact graph.
5. `missing` → logs a gap report (§9.1) that can re-surface a relevant question.

The correction is itself verified source — so the twin can only ever get *more* faithful, never invent.

### 7.2 Consent capture (at creation, §2.4)
Capture explicitly and version it: which modalities are permitted (voice clone, video avatar, text), who may access, posthumous-vs-immediate activation, and the subject's right to review/delete. Strongly prefer also recording a short spoken affirmation (`affirmation_media_ref`) — it doubles as voice-clone material and as a durable consent artifact. This is a `required` flow in the `_consent` category.

### 7.3 Succession / beneficiary intent (§2.5)
Capture who inherits access, when it activates, per-beneficiary scope, and any messages to be released to specific people. This wires directly into listener-aware retrieval (§9.3): the beneficiary identity is authenticated from these records, never guessed.

---

## 8. Live conversation path

One bounded Groq call. Budget is dominated by that call; everything else is precomputed or ~free.

### 8.1 Prompt assembly (deterministic, no extra LLM calls)
Assemble from precomputed parts at request time:
1. **Persona system prompt** — identity + fidelity rules (assert only what's provided; otherwise no-memory fallback) + the **voice card** (§9.2) + the **flattened entity-graph fact-spec** (§9.3). All precomputed per persona; no live graph traversal.
2. **Listener context** — who they are, relationship, address term, and the across-conversation summary (§9.6). From authenticated consent/succession records.
3. **Retrieved memory units** — FAISS top-k (~2ms), persona-conditioned, with affect tags. Cap `k`.
4. **Within-conversation turns** — recent turns from session state (§9.5).
5. **User message.**

### 8.2 The 600ms warm budget
```
FAISS retrieval        ~2 ms
prompt assembly        < 1 ms (string ops on precomputed parts)
Groq reply call        the rest  ← this is your entire latency budget in practice
```
To protect it: cap `k`, keep the voice card and fact-spec compact, cap output tokens, keep the system prompt static (cache-friendly). If voice replies are on, **TTS is additive and async** — return text first, stream audio after.

### 8.3 Runtime fidelity (no verification call)
No second Groq call. Fidelity holds because: (a) only verified, non-superseded memory units are retrieved; (b) the system prompt forbids asserting anything outside them; (c) the no-memory fallback (§9.7) covers the gap. The expensive checking already happened at ingestion.

---

## 9. Resonance mechanisms

For each: **what it is**, **where it's computed** (ingestion/precompute vs runtime), and **where it's injected**. The bias is always to precompute and keep the live path to a single call.

### 9.1 Family / subject feedback loop
Flags from family members and from the subject's self-review (§7.1). Routing: `wrong_fact` → correction pipeline; `wrong_tone` → Stage 4 exemplar tuning; `missing` → gap report that can re-surface a question. Computed offline; closes the loop back into ingestion.

### 9.2 Speech-texture capture → "voice card"
Catchphrases, humor register, filler/cadence, and **what they call people** (address terms). Mined at ingestion (Stage 4 exemplar bank + Stage 3 entity aliases). Compiled once per persona into a compact **voice card** (a few catchphrases, address-term map, humor note, 2–3 short verbatim exemplars) that's injected into the system prompt. **Precomputed — not retrieved per query.**

### 9.3 Listener-aware retrieval
The current listener maps to an entity node (e.g. "your daughter Priya"), authenticated from §2.4/§2.5 records — never inferred. Retrieval biases toward memory units involving that entity and uses the correct address term + relationship-appropriate register. The flattened entity graph (already the fidelity fact-spec) carries the aliases. Injected via listener context (§8.1.2); the graph itself is never traversed live.

### 9.4 Emotional attunement (affect tags)
Each memory unit carries a structured `affect` object (`emotion`, `valence`, `intensity`) from Stage 2.
Attunement is folded **into the single live call** — the system prompt instructs the model to read the
listener's register from the conversation and prefer affect-appropriate units and tone (e.g. a grief-toned
listener → warmer, gentler units). Use `valence` to match register and `intensity` to rank candidates.
**Deliberately no separate sentiment call** — that would cost latency and a Groq request. One call does it.

### 9.5 Within-conversation memory
Recent turns + established referents held in session state and passed into the live call's context. No extra call; cheap.

### 9.6 Across-conversation memory  ⚠️ *new bounded call — see §10*
A durable per-`(persona, listener)` summary so the twin "remembers" prior chats with that specific person. Updated at **end of session** by one bounded summarizer call (batch, off the hot path), stored, and injected as a compact summary at the next session's start. **Not an agent** — single-shot, deterministic, bounded. Alternative if you want zero new call types: build the summary heuristically (key entities + last-topic + turn count) with no LLM. Flagged for your decision in §10.

### 9.7 In-character graceful no-memory fallback  ★ most important runtime guard
When retrieval returns nothing above a confidence threshold, the twin must **not** fabricate. It responds in-character acknowledging it doesn't recall / that wasn't something they spoke about, and optionally turns it back warmly ("Tell me what you remember about it"). Provide vetted fallback lines *in the persona's register* (the voice card informs the phrasing). This is the single line of defense that turns the fidelity constraint into believable behavior instead of a robotic refusal. Enforced in the system prompt; triggered by a retrieval-confidence threshold checked in code before/within the live call.

### 9.8 Optional voice replies
ElevenLabs TTS of the twin's text reply, cloned voice. Separate (non-Groq) quota. **Async/streamed — text returns within the 600ms budget, audio follows.** Never gate text on TTS.

---

## 10. Assumptions & open decisions (please confirm)

These are choices I made or flagged so they're explicit, not buried:

1. **Memory Lane categories (§5.1)** are proposed here, since the prior chat didn't fix a specific list. Adjust the set/order freely — everything keys off the category `key` string.
2. **Fidelity fold — RULED: defer + instrument.** The built pipeline runs fidelity as a separate Groq call
   per unit (`verify_fidelity`), which roughly doubles the heaviest bucket (§1.1). It works and the cap is not
   binding at test volume, so do **not** refactor now. Instead add the Redis daily Groq counter (already in
   CLAUDE.md) for visibility, and fold the self-check into the Stage 2 transform call before scaling, when the
   counter approaches the cap. Measure first; optimize on signal, not speculation.
3. **Across-conversation memory (§9.6)** introduces a 4th bounded call type beyond the three you'd allowed (transforms, evaluator, live reply). It's single-shot/off-path, not an agent — but it *is* an addition. Options: (a) accept the bounded summarizer call, (b) do it heuristically with no LLM, or (c) drop across-conversation memory for v1. My default is (a) gated behind a flag.
4. **Emotional attunement and listener-register detection are folded into the single live call** (§9.4) rather than a separate classifier, to protect the 600ms budget and the request cap. Confirm you're happy trading a little tone precision for zero extra calls.
5. **Evaluator depth thresholds** (the `< N chars` fallback in §4.4, the `confidence < 0.5 → advance` rule in §4.3) are starting values — tune against real sessions.
6. **The seed question bank (§5.3) is ~10 questions** to lock the schema and modality rule. It's meant to be extended to your full ~40 using §5.5; say the word and I'll flesh out the rest of the bank.