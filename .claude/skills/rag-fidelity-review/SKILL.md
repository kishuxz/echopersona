---
name: rag-fidelity-review
description: Verify that only fidelity-verified memory units enter the FAISS index and that the live reply path cannot fabricate facts. Run after any ingestion pipeline or retrieval change.
---

## When to use
- After any change to `services/ingestion/`
- After any change to `services/rag.py`
- Before changing the FAISS index build step
- Before any change to the live reply prompt assembly

## Checklist
1. Read `services/ingestion/fidelity.py` — verify fidelity check runs before Stage 4 indexing.
2. Read `services/ingestion/stage4.py` — verify only `fidelity_verified=True` units are indexed.
3. Read `services/rag.py` — verify retrieved units are injected into the prompt verbatim, not rephrased.
4. Verify the no-memory fallback activates when FAISS returns empty (spec §9.7).
5. Verify the live reply system prompt includes the "do not assert facts outside retrieved units" constraint.
6. Verify `resolved_entity_ids` is populated by Stage 3 before Stage 4 runs.
7. Verify Stage 0 writes are synchronous and do not block on Stage 1–4.

## Rule
Do not modify code. Report findings only. Do not create new markdown files.

## Required output format
```
## RAG Fidelity Review: <change or area>

### Findings
- [CRITICAL|HIGH|MEDIUM|OK] <file:line> — <finding>

### Fidelity gate
- Verified: only fidelity_verified=True units in index? <yes/no>
- No-memory fallback wired? <yes/no>
- Live prompt asserts no un-retrieved facts? <yes/no>

### Verdict: PASS | FAIL
```
