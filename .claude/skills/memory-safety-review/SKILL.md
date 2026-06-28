---
name: memory-safety-review
description: Review how EchoPersona memory is stored, accessed, deleted, and audited. Checks ownership boundaries, family-member access rules, cross-user leakage, RLS enforcement, and GDPR/preservation compliance. Run before any change to memory storage, access, or family-member relationship logic.
---

## Purpose
Verify that persona memory cannot leak across users or be accessed by unauthorized parties,
that family-member access rules are explicit and enforced at the DB level, and that delete/export
paths work correctly per the pricing and data lifecycle policy.

## When to use
- Any change to how memory units are stored, queried, or indexed
- Any change to family-member (chosen-family) access permissions
- Any change to `services/persona_store.py`, `services/db.py`, or `services/rag.py` retrieval
- Any new Supabase table that stores user or persona data
- Before any feature that exposes memory data to a new actor (new role, new frontend view)
- Any succession or posthumous access change

## Inputs expected
- The diff or description of what changed
- Relevant Supabase table schemas and RLS policies (from `backend/migrations/`)
- The family-member access model as defined in `docs/product-spec.md`

## Process

### Step 1 — What memory is stored
- Which tables store persona memory? (`memory_units`, `personas`, `sessions`, `answers`?)
- What fields are PII or sensitive? (name, voice data, audio recordings, personal stories)
- Are `source_type`, `provenance`, `captured_at` present on all memory writes?

### Step 2 — Who can read it
- Owner (creator): can always read their own memory units
- Chosen family (listeners): can read only what the owner has designated
- Public: should never have access to raw memory units or PII
- Service role: backend only — never exposed to frontend
- Verify RLS policies enforce these boundaries — no SELECT policy should allow cross-user reads

### Step 3 — Delete and export paths
- Is there a delete path for memory units that the owner can trigger?
- Does deletion cascade correctly (memory_units → FAISS index purge)?
- Is there an export path if required by GDPR or the pricing-data-lifecycle policy?
- Reference: `docs/pricing-data-lifecycle.md` for the correct retention and deletion rules

### Step 4 — Cross-user leakage
- Can a family-member session read memory units from a different persona they are not authorized for?
- Can FAISS retrieval return memory units from a different persona (wrong persona_id in the index)?
- Are persona_id and user_id filters applied at both the FAISS query level and the DB verification level?

### Step 5 — Supabase RLS enforcement
- Every table with user data has `ENABLE ROW LEVEL SECURITY`
- Every policy uses `auth.uid()` or the service role key for verification
- No ANON role on persona data, memory units, or session data
- Service role key is the only RLS bypass, and it is used only in the backend

### Step 6 — Auditability
- Are memory writes auditable? (`source_type`, `captured_at`, `provenance` fields present)
- Is there a way to trace which memory units contributed to a given reply?
- Is there a succession/posthumous access audit trail for family-member escalations?

## Block conditions
- Memory units readable across unrelated users (RLS gap)
- Family-member access rules undefined or fabricated in code (not enforced at DB level)
- Delete path missing or does not cascade to FAISS index
- Cross-user FAISS leakage possible (missing persona_id filter)
- PII stored without audit fields

## Required output

```
## Memory Safety Review — <change description>

### Storage audit
- Tables affected: <list>
- PII fields: <list>
- Audit fields present: yes / MISSING

### Access model
- Owner access: PASS / FAIL
- Family-member access: PASS / FAIL / NOT APPLICABLE
- Public access blocked: PASS / FAIL
- RLS policies: PASS / FAIL

### Delete / export
- Delete path: present / MISSING
- FAISS cascade: present / MISSING / NOT APPLICABLE
- Export path: present / MISSING / NOT REQUIRED

### Cross-user leakage
- FAISS persona_id filter: present / MISSING
- DB query persona_id filter: present / MISSING
- Verdict: safe / RISK

### Verdict
PASS / NEEDS FIXES / BLOCK

### Required fixes before ship
- <fix or "none">
```