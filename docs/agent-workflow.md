# EchoPersona — Agent & Skill Workflow

## Documentation ownership

| File | Owner | Update when |
|---|---|---|
| `CLAUDE.md` | All agents | Rules change; stack changes; new hard constraints |
| `PROGRESS.md` | context-manager | Build state changes; blocker resolves; step completes |
| `docs/product-spec.md` | product-architect | Product behavior, data contracts, question bank |
| `docs/architecture.md` | supabase-architect / rag-persona-engineer | Architecture changes |
| `docs/decisions.md` | product-architect | A significant architectural or product decision is made |
| `docs/backlog.md` | product-architect | New ideas; items are prioritized or removed |
| `docs/pricing-data-lifecycle.md` | stripe-entitlements-engineer | Pricing, deletion, legacy policy |
| `docs/agent-workflow.md` | context-manager | Agent list or skill list changes |
| `docs/runbook.md` | deploy-vercel-reviewer / context-manager | New commands; deploy steps change |

**Rule: never create a new markdown file without explicit user approval.** Update an existing file instead.

---

## When to use agents

Invoke a specialized agent when the task is squarely in its domain and spans multiple files.
For a single-file bug fix, use `/bugfix-minimal` skill directly — do not spawn an agent.

| Agent | Use when |
|---|---|
| `context-manager` | Starting a new session; PROGRESS.md is stale; doc drift detected |
| `product-architect` | New feature design; spec questions; data contract changes |
| `supabase-architect` | Migration authoring; RLS policy review; schema design |
| `rag-persona-engineer` | Memory unit quality; ingestion pipeline; FAISS changes |
| `media-pipeline-engineer` | TTS/STT latency; voice clone; video avatar; Tavus/D-ID |
| `stripe-entitlements-engineer` | Checkout, webhooks, entitlements, pricing |
| `frontend-react-engineer` | React components; hooks; TypeScript types; Vite config |
| `qa-security-reviewer` | Pre-merge review; RLS audit; JWT checks; Stripe sig |
| `deploy-vercel-reviewer` | Render / Vercel deploy; env var audit; CORS; keepalive |

---

## When to use skills

Skills are lightweight checklists for recurring tasks. Run them inline without spawning a full agent.

| Skill | Trigger |
|---|---|
| `/update-project-context` | Session start, or after completing a build step |
| `/plan-feature` | Before implementing anything non-trivial |
| `/supabase-rls-review` | Before any Supabase migration or table change |
| `/stripe-webhook-review` | Before any Stripe webhook handler change |
| `/rag-fidelity-review` | After ingestion pipeline change; before indexing change |
| `/ingestion-pipeline-review` | After any Stage 0–4 change |
| `/media-latency-review` | After TTS/STT/video change; before live path change |
| `/predeploy-check` | Before any push to main or deploy trigger |
| `/bugfix-minimal` | For any bug fix — enforces minimal-change discipline |

---

## Workflow for a new build step

1. Run `/update-project-context` — confirm PROGRESS.md is current.
2. Run `/plan-feature` — align on approach before writing code.
3. Implement the slice (one route / one service / one test file at a time).
4. Run affected skills (e.g. `/supabase-rls-review` if adding a table).
5. Run `cd backend && python -m pytest tests/ -q` — all tests must stay green.
6. Run `/predeploy-check` before merging.
7. Update `PROGRESS.md` with the new completed step and next action.

---

## Groq RPM discipline for agents

Any agent that issues Groq calls must:
1. Check the RPM counter in Redis before issuing the call.
2. Yield to interactive calls (evaluator, live reply) if the window is tight.
3. Never issue more than 25 Groq calls in a 60s window from batch ingestion alone.
4. Log every call with `source=ingestion|evaluator|live_reply` for observability.
