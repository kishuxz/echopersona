---
name: ingestion-pipeline-review
description: Review any change to the Stage 0–4 ingestion pipeline for correctness, Groq RPM impact, and worker isolation. Run after any services/ingestion/ or worker/tasks/ change.
---

## When to use
- After any change to `services/ingestion/stage*.py`
- After any change to `worker/tasks/ingestion.py`
- After adding a new transform or fidelity check
- Before changing the Stage 0 synchronous write

## Checklist
1. Verify Stage 0 remains synchronous, cheap, and LLM-free.
2. Verify Stages 1–4 are only called from the arq worker — not from a FastAPI route.
3. Count new Groq calls introduced; compute RPM impact at 30 RPM ceiling.
4. Verify the worker checks the RPM counter before issuing each Groq call.
5. Verify interactive calls (evaluator, live reply) still preempt batch ingestion in the priority queue.
6. Verify memory unit writes include all required provenance fields (spec §2.3).
7. Verify the deterministic fallback path in the evaluator is still reachable (spec §4.4).
8. Run `cd backend && python -m pytest tests/test_ingestion_handoff.py -v`.

## Rule
Focus on the changed area. Do not rewrite surrounding code. Do not create new markdown files.

## Required output format
```
## Ingestion Review: <change>

### Stages affected
- Stage <N>: <what changed>

### Groq call budget
- Before: ~<N> calls per session
- After: ~<N> calls per session
- RPM risk: <low|medium|high> — <reason>

### Worker isolation
Stage 0 still synchronous + LLM-free? <yes/no>
Stages 1–4 still in arq only? <yes/no>

### Findings
- [CRITICAL|HIGH|MEDIUM|OK] <file:line> — <finding>

### Verdict: PASS | FAIL
```
