---
name: github-issue-triage
description: Convert a fuzzy chat request into a clean GitHub issue. Picks the right template (bug/feature/quality/infra/security), drafts acceptance criteria + test plan + risk, recommends a branch name and the one implementing agent. Asks before running `gh issue create`.
---

## Purpose
Stop "Kishore says a thing" from turning into half-implemented work. Funnel every non-trivial
request through a one-issue-per-concern check before code is written.

## Trigger phrases
- "make an issue"
- "triage this"
- "/github-issue-triage"
- "open a ticket for …"

## Steps

1. **Restate** the request in one sentence. Read it back to the user.
2. **Classify** into one of:
   | Kind | Template | Typical sign |
   |---|---|---|
   | bug | `bug.yml` | regression, repro steps, "this used to work" |
   | feature | `feature.yml` | new capability, new user value |
   | quality | `quality.yml` | refactor, no-op, test coverage, tech debt |
   | infra | `infra.yml` | Docker, nginx, Redis, Supabase, runbook |
   | security | `security.yml` | auth, JWT, RLS, secret leak, OWASP-shaped |
3. **Draft** the issue body:
   - Summary (one sentence)
   - Context — link the latest relevant `PROGRESS.md` entry; reference the spec section if any
   - Acceptance criteria (3–6 testable bullets)
   - Test plan — exact pytest path *or* `/browser-test` scenario rows
   - Risk — low / medium / high, with one-line reason
   - Labels (default by kind)
4. **Recommend a branch name** — `kind/short-slug` (`fix/tavus-video-blank`,
   `feat/relationship-listener`, `chore/redact-ws-logs`).
5. **Recommend the one implementing agent** and the review skill(s) that gate the merge.
6. **Recommend** whether `/plan-feature` or `/investigate` should run before any code is written.
7. **Split** if the request spans ≥2 lanes (e.g. backend + migration + frontend). Open one issue
   per lane and link them with "blocked by / blocks".
8. **Print the gh command** for the user to run — do not execute it without confirmation:
   ```bash
   gh issue create --template <kind>.yml --title "<draft title>" --body-file -
   ```

## Output format

```
## Issue triage — <date>

- Restated: <one sentence>
- Kind: <bug | feature | quality | infra | security>
- Title: <one line>
- Branch: <kind/short-slug>
- Implementing agent: <agent name>
- Reviewer skills: <skill names>
- First step: /plan-feature OR /investigate OR straight-to-implement
- Risk: <low|medium|high — why>

---
### Draft issue body (ready to paste)
<filled-in template>

---
### Run when ready
gh issue create --template <kind>.yml --title "…" --body-file -
```

## Stop conditions
- Request crosses ≥2 unrelated lanes → split into multiple issues *before* opening any.
- Request is "do everything for X" with no acceptance criteria → ask for the smallest first slice.
- Security-shaped request → confirm severity with the user before creating a public issue;
  consider opening it as a private security advisory instead.

## Token policy
- Do not paste the entire prior chat into the issue. Summarise.
- For bug context, link the latest `PROGRESS.md` milestone rather than quoting it.
- Strip any tokens from pasted logs before they enter the issue body.

## Human approval
**Required** before `gh issue create` runs. Show the draft, get a yes.
