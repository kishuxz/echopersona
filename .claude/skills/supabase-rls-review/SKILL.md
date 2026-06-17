---
name: supabase-rls-review
description: Audit RLS policies before applying any Supabase migration or adding a new table. Run after supabase-architect produces a migration.
---

## When to use
- Before applying any migration that creates or alters a table
- When adding new access patterns to existing tables
- After any change to `services/db.py` or `services/persona_store.py`

## Checklist
1. List all tables in the migration.
2. For each table: verify `ENABLE ROW LEVEL SECURITY` is present.
3. For each table: verify at least one `SELECT` policy and one `INSERT/UPDATE/DELETE` policy.
4. Verify policies use `auth.uid()` — not a hardcoded value.
5. Verify no `ANON` role gets read access to PII or persona data.
6. Verify the service role key is the only credential that bypasses RLS.
7. Check `services/db.py` — does the backend use the service role key (correct) or anon key (wrong) for admin operations?
8. Verify cascade deletes or foreign keys do not bypass RLS unexpectedly.

## Rule
Do not modify code. Report findings only. Do not create new markdown files.

## Required output format
```
## RLS Review: <migration filename>

### Tables reviewed
- <table>: RLS enabled? <yes/no> | Policies: <list>

### Findings
- [CRITICAL|HIGH|MEDIUM|OK] <table>: <finding>

### Verdict: PASS | FAIL
<summary>
```
