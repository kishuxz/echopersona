# EchoPersona — Project Rules

Persona-twin product: living people build an AI twin (voice, stories, personality) by answering a
vetted question bank; chosen family talk to the twin. Chat + chat-twin now; video avatar later.

## Must read before building
- `docs/product-spec.md` — authoritative spec for persona creation, evaluator, live conversation,
  resonance mechanisms. Follow data contracts exactly (§2 schemas, §4 evaluator I/O). Do not invent fields.
- `docs/architecture.md` — how the layers connect and where each concern lives.
- `PROGRESS.md` — current build state and active blocker.
- `AGENTS.md` — agent workflow rules and kstack workflow reference.

---

## Hard constraints — never violate

| Constraint | Rule |
|---|---|
| **Latency** | Live reply < 600ms warm. ONE bounded LLM call. TTS is async — never block text on audio. |
| **Fidelity** | Never assert a fact absent from verified memory units / entity-graph fact-spec. No-memory fallback (spec §9.7) when retrieval is empty. Do not fabricate. |
| **No agents** | Only bounded single-shot LLM calls: batch ingestion transforms, answer evaluator (creation-time), live reply, optional across-conversation summarizer (spec §9.6, flag-gated). |
| **No GPU** | All LLM/STT/vision-OCR via Groq free tier. Tesseract CPU fallback for OCR only. |
| **Groq RPM** | Free tier: ~30 req/min shared across all call types. Interactive calls (evaluator, live reply) preempt batch ingestion. Track per-minute counter in Redis; arq worker self-throttles. |

---

## Operating rules — never violate

| Rule | Detail |
|---|---|
| **Source of truth** | `/Users/kishorekumar/echopersona` is authoritative. `/Users/kishorekumar/kstack` is reference only — do not copy wholesale. |
| **No secrets in output** | Never print API keys, JWTs, Supabase service-role keys, Stripe webhook secrets, or full WebSocket URLs. |
| **No deploy/SSH/VPS** | Never deploy, SSH, or touch the VPS without explicit human approval per-operation. |
| **No co-author attribution** | Never add "Co-Authored-By: Claude" or any AI attribution to commits. |
| **Narrow slices** | One concern per slice: no combining backend + frontend + migrations. Implement only after diagnosis. |
| **PROGRESS.md required** | Update PROGRESS.md at the end of every session. Run `/update-project-context` before starting new work. |
| **Worktree caution** | If working in a git worktree (split path), do not merge back to main without confirming which worktree is active. |
| **Plan before code** | Use `/plan` for any non-trivial feature or audit. Get approval before editing. |
| **Investigation first** | For bugs: reproduce first, identify root cause, then fix. Use `/investigate` or delegate to `debugger` agent. |

---

## Architecture rules

- **Persona work at ingestion, never at query time.** Live path retrieves already-persona-conditioned
  memory units; it does not do persona reasoning.
- **Supabase is source of truth** for all persistent state: personas, memory units, sessions, consent,
  entitlements.
- **Redis is temporary only**: rate-limit counters, semantic cache, job status, session state. Nothing
  in Redis is the source of truth for billing or persona data.
- **Heavy ingestion (Stages 1–4)** runs exclusively in the arq worker. Never inside an edge function
  or a FastAPI request handler.
- **Stripe entitlements table** is the billing/access source of truth once payments are wired in.
- **RAG at query time is plumbing, not persona**. FAISS retrieves pre-built memory units; the live call
  assembles them. No persona reasoning at query time.

---

## Coding rules

- Single-shot LLM calls only. No chaining, no agent loops.
- Validate all LLM JSON output in code. Never trust model output directly.
- Every DB write is auditable: include `source_type`, `captured_at`, and `provenance` fields.
- Migrations go in `backend/migrations/` (named `NNN_description.sql`) AND in `supabase/migrations/`
  for Supabase CLI tracking. Run manually in the Supabase SQL editor for now.
- Test new services before wiring into routes. Run `cd backend && python -m pytest tests/ -q` after
  each slice.

---

## Security rules

- Never expose `SUPABASE_SERVICE_ROLE_KEY` to frontend.
- All persona endpoints and WebSocket require a valid Supabase JWT (`middleware/auth.py`).
- Supabase RLS must be enabled on every table containing user data.
- Stripe webhooks must validate the `Stripe-Signature` header before processing.
- No secrets in code; use `.env` / environment variables. `.env` files are gitignored.

---

## Supabase rules

- All schema changes go through a migration file first — no ad-hoc SQL in production.
- RLS policies required on every table. Use `USING (auth.uid() = user_id)` patterns.
- Storage buckets: set appropriate RLS policies; never make user-uploaded content public without review.
- Use Supabase service role key only in the FastAPI backend (server-side). Frontend uses anon key.

---

## Stripe rules (planned — not yet built)

- Stripe checkout sessions created server-side only. Never pass price IDs from the client.
- Webhook handler must verify `Stripe-Signature`; idempotency via `stripe_event_id` column.
- Entitlements table in Supabase is updated by the webhook handler, not the checkout redirect.
- Never grant access based on URL parameters or frontend state alone.

---

## RAG / persona rules

- Memory units must pass fidelity verification before being indexed.
- `resolved_entity_ids` must be written by Stage 3 before Stage 4 indexes.
- The live reply prompt includes: retrieved memory units + persona card + voice card + entity graph
  fact-spec + listener context. Assemble in `services/rag.py`.
- No-memory fallback (spec §9.7) activates when FAISS returns empty or below threshold.

---

## Media rules

- ElevenLabs TTS is async — fire it after text is committed to the client.
- Cartesia is the fast TTS alternative (~80ms TTFA). Toggle via `TTS_PROVIDER=cartesia`.
- Voice clone requires at least one `video_audio` answer stored in Supabase Storage.
- D-ID / Simli video generation is optional and must never block the live reply path.
- Tavus integration (planned): same async non-blocking constraint applies.

---

## Documentation rules

- **Do not create new markdown files** unless explicitly approved or no existing category fits.
- Update existing docs rather than creating new ones. Approved doc files:
  - `CLAUDE.md` — stable project rules (this file)
  - `PROGRESS.md` — current session state only
  - `README.md` — public-facing project overview
  - `docs/product-spec.md` — product behavior, data contracts, question bank
  - `docs/architecture.md` — technical architecture
  - `docs/decisions.md` — decision log
  - `docs/backlog.md` — future ideas
  - `docs/pricing-data-lifecycle.md` — pricing, preservation, deletion, legacy policy
  - `docs/agent-workflow.md` — how agents and skills should be used
  - `docs/runbook.md` — operational commands and steps
  - `backend/prompts/evaluator_system.md` — LLM prompt (not documentation)
  - `AGENTS.md` — agent workflow rules and kstack reference
- `docs/archive/` — obsolete files only; include an archive note at the top.

---

## Verification commands

```bash
# Backend tests
cd backend && python -m pytest tests/ -q

# Type-check frontend
cd frontend && npx tsc --noEmit

# Start backend dev server (requires .env)
# --host :: binds IPv6 dual-stack so Chrome (which resolves localhost → ::1 on this machine) can connect
cd backend && uvicorn main:app --host :: --port 8000 --reload

# Start frontend dev
cd frontend && npm run dev

# Docker stack
docker compose up --build
```

---

## CodeGraph (MCP)

Query the CodeGraph MCP server to locate definitions, find callers, and trace dependency edges
BEFORE editing. Use `codegraph_explore` for most questions. Do not blind-grep.

---

## Source of truth — worktree rules

- `/Users/kishorekumar/echopersona` is the **live local app worktree** on `main`. Run `uvicorn`,
  `npm run dev`, and `docker compose` from here. Treat it as production-of-local — do not edit it
  casually.
- `/Users/kishorekumar/conductor/workspaces/echopersona/<city>` are **Conductor planning / feature
  worktrees**. Edit `.claude/`, `.github/`, docs, and feature slices here. Open PRs from these
  branches into `main`. After merge, `git pull` inside the live worktree so it picks up the change.
- `/Users/kishorekumar/kstack` and `/Users/kishorekumar/conductor/repos/gstack-kishore` are
  **reference-only**. Read patterns, never copy wholesale, never vendor files.
- The **hanoi worktree no longer exists**. Any doc/code reference to it is stale — flag for removal.
- Before any edit, confirm `pwd` matches the intended worktree. Mismatched-worktree edits are the
  single biggest source of "but I fixed that already" loops.

---

## Token / Ponytail policy

- If Ponytail is installed locally, use it per its documented invocation (`/ponytail-context` runs
  the detection). Never invent flags.
- If Ponytail is not installed, enforce manual token hygiene:
  - Use `rg` before `cat`/`Read` for any file larger than ~400 lines.
  - Read narrow ranges (`Read offset/limit`, `sed -n 'A,Bp'` capped to ~200 lines).
  - Summarise tool outputs over ~50 lines before quoting them back.
  - Never paste full logs, full WebSocket URLs, or `.env` contents into chat.
  - Use `PROGRESS.md` as durable cross-session memory. Write a checkpoint there when context starts
    to feel noisy, then continue.
  - When handing off between agents, write a one-paragraph handoff first; don't dump the prior
    chat into the subagent prompt.

---

## Secrets policy

- Never print API keys, JWTs, Supabase service-role keys, Stripe webhook secrets, or full
  WebSocket URLs that contain tokens.
- Never `cat`/`Read` `.env` files. Report key *presence* only (e.g. via
  `awk -F= '/^[A-Z_]+=/ {print $1}' backend/.env`).
- Logs pasted into chat must redact `?token=…`, `Authorization:` headers, and any host string that
  contains a session token. Keep only `host:port` + path.
- The same rule applies to GitHub issue/PR bodies, screenshots, and `.context/` artifacts.

---

## Command routing

| Trigger | Skill | When |
|---|---|---|
| Session start | `/start-session` | First command after `cd` into a worktree. |
| Before voice/persona/Tavus work | `/anti-loop-check` | Catches the 8 known regression triggers. |
| New feature / architecture | `/plan-feature` | Use plan mode; require approval before edits. |
| Bug | `/investigate` | Reproduce first; do not "fix forward" without root cause. |
| Crashed / inherited session | `/interrupted-session` | Classify git state before continuing. |
| User-visible change | `/browser-test` | Walk the APJ voice loop end-to-end. |
| Before commit/PR | `/pr-readiness` | 12-row GO/NO-GO check. |
| Fuzzy work → ticket | `/github-issue-triage` | One concern per issue. |
| Context bloat | `/ponytail-context` | Compact, summarise, checkpoint. |
| Pre-deploy | `/predeploy-check` or `/vpc-deploy-check` | Read-only review only. |

**Conductor `/batch` is for read-only review lanes only. Max one implementation lane at a time,
after diagnosis.** Unsafe lanes (migrations, `routers/ws.py`, `middleware/auth.py`,
`worker/tasks/*`, `services/rag.py`, RLS, Stripe webhooks) are serial only — never parallel.

---

## Current project priority

Rotate this section as priorities shift. Every agent reads it.

- **P0** — Lock local voice/persona baseline; run APJ persona fidelity live test; fix Tavus/video path.
- **P1** — Anti-loop guard live; WebSocket / JWT log redaction; GitHub issue/PR workflow in use.
- **P2 (later)** — Relationship-aware listener/persona quality; production hardening on the VPC.
