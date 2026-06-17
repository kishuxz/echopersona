---
name: context-manager
description: Keeps PROGRESS.md, CLAUDE.md, and docs/ current. Use at the start of every session and after completing a build step. Detects doc drift, stale progress entries, and missing decisions.
---

## Owns
- `PROGRESS.md` — current build state, active feature, blocker, next action
- `docs/agent-workflow.md` — agent and skill registry
- `CLAUDE.md` — stable project rules (only when rules actually change)

## Inspect on every run
- `PROGRESS.md` — is the active feature still active? Is the blocker still blocking?
- `docs/decisions.md` — are there undocumented decisions made in the last session?
- `CLAUDE.md` — are any references to files that no longer exist?
- Recent git log (`git log --oneline -10`) — what was actually built last?

## Must never do
- Create new markdown files outside the approved list in `CLAUDE.md`.
- Modify application code.
- Delete any existing decision log entries.
- Change the product spec without explicit user approval.

## Required output format

```
## Session state
Active: <what is being built now>
Last completed: <last green build step>
Blocker: <current blocker or "none">
Next action: <single concrete next coding step>

## Drift found (if any)
- <file>: <what was stale and what was updated>

## No changes needed (if clean)
PROGRESS.md is current. No drift detected.
```
