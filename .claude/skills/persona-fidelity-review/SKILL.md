---
name: persona-fidelity-review
description: Review whether the EchoPersona AI twin behaves consistently, safely, and truthfully. Checks identity consistency, memory accuracy, hallucination guards, uncertainty handling, and family-member relationship safety. Run before any persona prompt, memory, or voice card change ships.
---

## Purpose
Verify that the AI persona only asserts facts grounded in verified memory units, handles uncertainty
honestly, and does not cross unsafe impersonation boundaries — especially around family-member access.

## When to use
- Any change to the live reply system prompt or RAG assembly in `services/rag.py`
- Any change to persona card or voice card injection
- Any change to the no-memory fallback (spec §9.7)
- Any change to memory unit schema, retrieval logic, or Stage 2-4 ingestion that affects what enters the index
- Any new persona creation UI that changes what memory units are generated

## Inputs expected
- The diff or description of what changed
- The relevant system prompt text (from `services/rag.py` or `backend/prompts/`)
- Sample memory units or test persona data if available

## Process

### Step 1 — Identity and voice consistency
- Does the persona card uniquely identify the persona (name, relationship context, voice tone)?
- Is the voice card injected into the system prompt before the reply is generated?
- Would two separate replies about the same topic sound like the same person?

### Step 2 — Memory accuracy and grounding
- Are retrieved memory units injected verbatim (not paraphrased) into the prompt?
- Does the system prompt explicitly instruct the model to only assert facts present in the retrieved units?
- Is the no-memory fallback (spec §9.7) reachable when FAISS returns empty or below threshold?
- Are there any instructions that could lead the model to fill gaps with invented facts?

### Step 3 — Uncertainty handling
- When memory is absent or ambiguous, does the persona acknowledge uncertainty rather than fabricate?
- Is the no-memory fallback language natural and safe ("I don't have a clear memory of that" rather than silence or confabulation)?

### Step 4 — Family-member relationship handling
- Are family-member (listener) identities and relationships explicitly provided in the prompt context?
- Does the persona behave appropriately toward the listener based on the relationship type (e.g., child vs. sibling)?
- Are there any instructions that could cause the persona to confuse listener identities or assert false relationships?

### Step 5 — Safety boundaries
- Does the system prompt include a constraint against asserting facts outside retrieved memory units?
- Is there a clear stop condition if a question would require fabricating sensitive personal details (medical, legal, financial)?
- Does the persona avoid impersonating living people in ways that could cause harm?

## Scorecard

| Dimension | Score (1-10) | Notes |
|---|---|---|
| Identity consistency | | |
| Memory accuracy / grounding | | |
| Tone fidelity | | |
| Uncertainty handling | | |
| Family-member relationship handling | | |
| Safety boundaries | | |

**Overall: Pass / Needs fixes / Block**

## Block conditions
- Persona can assert facts outside retrieved memory units (hallucination risk)
- No-memory fallback is unreachable or produces fabricated output
- Family-member access rules are undefined or could be confused
- System prompt lacks the "only assert facts from retrieved units" constraint
- Safety boundary for sensitive personal details is absent

## Required output

```
## Persona Fidelity Review — <change description>

### Scorecard
| Identity consistency | X/10 |
| Memory accuracy | X/10 |
| Tone fidelity | X/10 |
| Uncertainty handling | X/10 |
| Family-member handling | X/10 |
| Safety boundaries | X/10 |

### Findings
CRITICAL: <list or "none">
HIGH: <list or "none">
MEDIUM: <list or "none">

### Verdict
PASS / NEEDS FIXES / BLOCK

### Required fixes before ship
- <fix or "none">
```