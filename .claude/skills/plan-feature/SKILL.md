---
name: plan-feature
description: Design a feature slice before writing code. Reads the spec and outputs an ordered implementation plan with Groq call budget and test strategy.
---

## When to use
Before implementing any feature that touches more than one file or introduces a new LLM call.

## Checklist
1. Read `docs/product-spec.md` — find the relevant spec section(s).
2. Read `docs/architecture.md` — understand which layer(s) are affected.
3. Read `docs/decisions.md` — check for constraints that apply.
4. Read existing code in the affected area (use CodeGraph MCP first).
5. Identify the data contract changes (if any) against spec §2.
6. Count the new Groq calls (if any) and compute RPM impact.
7. List the migration(s) needed (if any).
8. Write the implementation plan: ordered steps, each < 1 day of work.

## Rule
Do not write application code during planning. Do not invent data fields not in the spec.
Do not create new markdown files.

## Required output format
```
## Plan: <feature name>

### Spec reference
<section> — <what it says>

### Files to change (in order)
1. <file> — <what changes>
2. <file> — <what changes>

### New migrations needed
- <NNN_description.sql>: <what it adds>

### New Groq calls
- Type: <evaluator|ingestion|live_reply>
- Budget: ~<N> calls per <session|day>
- RPM risk: <low|medium|high>

### Tests to write
- <test file>: <what to test>

### Open questions
- <question>
```
