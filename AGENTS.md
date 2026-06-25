# Agent Instructions — EchoPersona

## Workflow reference
Read the AI engineering workflow before starting any task:
`/Users/kishorekumar/kstack/docs/ai-operating-system.md`

Reusable assets in kstack:
- `/Users/kishorekumar/kstack/agents/` — role-based reviewer agents (staff-engineer, security-officer, qa-lead, release-engineer, debugger, engineering-manager, founder, technical-writer)
- `/Users/kishorekumar/kstack/templates/` — fill-in task templates (feature-plan, backend-safe-slice, frontend-safe-slice, vpc-deploy-check, review-before-commit, docs-release, interrupted-session, plus report templates: AI_EVAL_REPORT, PERSONA_FIDELITY_REPORT, RAG_REVIEW_REPORT, SECURITY_REPORT, QA_REPORT, VERIFICATION_REPORT, CHANGE_SUMMARY, HANDOFF)
- `/Users/kishorekumar/kstack/skills/` — agent skill prompts (spec, plan, implement, review, qa, ship, investigate, code-quality, security-review, ai-quality-review, rag-review, persona-fidelity-review, latency-review, memory-safety-review, retro)
- `/Users/kishorekumar/kstack/conductor/` — lanes: read-only-review, docs, implementation, qa, security, release; playbooks: bug-fix-sprint, feature-sprint, refactor-sprint, release-sprint (Conductor not yet configured for EchoPersona)
- `/Users/kishorekumar/kstack/docs/review-gates.md` — required gates before shipping (scope, architecture, test, security, AI quality, docs, release)
- `/Users/kishorekumar/kstack/docs/ai-product-quality.md` — AI product quality standards (grounding, fidelity, safety, user trust)
- `/Users/kishorekumar/kstack/docs/safety.md` — safety rules for AI-assisted work
- `/Users/kishorekumar/kstack/docs/release-process.md` — release checklist and handoff protocol
- `/Users/kishorekumar/kstack/examples/echopersona/` — isolated EchoPersona reference examples (AGENTS.md template, review-gates.md, workflow.md); treat as reference only, not authoritative

## EchoPersona overrides
These narrow or override the generic kstack workflow for this product.

### Deployment
- Primary target is a private VPC running Docker + nginx (not Vercel or Render).
- Any deployment change requires explicit human approval before execution.

### Autonomy limits
- No autonomous runtime agents. All LLM calls are bounded, single-shot, and validated.
- Conductor is not yet configured — do not attempt to activate it.

### Paid APIs
- Do not add or expand paid API calls (OpenAI, ElevenLabs, D-ID, Tavus, Cartesia, etc.) unless explicitly approved.
- Default to Groq free tier for all LLM, STT, and vision-OCR work.

### Persona fidelity and provenance
- Never fabricate facts. Every assertion must trace to a verified memory unit or entity-graph fact-spec.
- No-memory fallback (`spec §9.7`) applies when retrieval is empty or below threshold.
- Persona memory writes must preserve provenance.
- Memory source/unit writes must preserve `source_type`, `provenance`, versioning, and supersession fields where applicable.

### Scope discipline
- One slice at a time. Do not combine backend + frontend + migrations in a single task.
- Migrations, RLS changes, WebSocket protocol changes, and billing changes require explicit human approval before execution.

### Infrastructure
- Redis and the arq worker are real, required components of the ingestion deployment.
- Do not remove, stub out, or mock them in any plan or implementation.
