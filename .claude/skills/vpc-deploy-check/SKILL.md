---
name: vpc-deploy-check
description: Review EchoPersona's private VPC deployment readiness. Checks Docker Compose, nginx WebSocket headers, SPA routing, env var presence (not values), arq worker, and CORS. Read-only unless edits are explicitly approved. Never SSH autonomously.
---

## Purpose
Verify the VPC deployment is correctly configured before any `docker compose up --build` on production.
This is a read-only audit — report findings, do not apply changes without explicit human approval.

## When to use
- Before any production deploy
- After changes to `docker-compose.yml`, `nginx.conf`, or env var structure
- After a new service or worker is added to the stack
- As part of `/predeploy-check` for the VPC deployment path

## Inputs expected
- Access to `docker-compose.yml`, `nginx.conf`, `backend/.env.example`, `frontend/.env.example`
- Knowledge of which env vars are currently set (existence check only — never print values)

## Process

### Step 1 — docker-compose.yml
- All required services present: `backend`, `frontend` (nginx), `redis`, `arq` (worker)
- Each service has a `restart: unless-stopped` or equivalent
- Health checks defined for `backend` and `arq` services
- Redis port not exposed externally (internal network only)
- No secrets hardcoded in the compose file

### Step 2 — nginx.conf
WebSocket support:
- [ ] `proxy_http_version 1.1;`
- [ ] `proxy_set_header Upgrade $http_upgrade;`
- [ ] `proxy_set_header Connection "upgrade";`

SPA routing:
- [ ] `try_files $uri $uri/ /index.html;` in the frontend location block

General:
- [ ] Backend `/api/` and `/ws/` paths proxied to the correct upstream
- [ ] No wildcard CORS headers in nginx (CORS is handled in FastAPI)

### Step 3 — Backend env vars (verify existence only — never print values)
Required:
- [ ] `SUPABASE_URL`
- [ ] `SUPABASE_SERVICE_ROLE_KEY`
- [ ] `SUPABASE_ANON_KEY`
- [ ] `GROQ_API_KEY`
- [ ] `REDIS_URL`
- [ ] `CORS_ORIGINS` (must not be `*` in production)
- [ ] `ENVIRONMENT` (must be `production` in production)
- [ ] `JWT_SECRET` or equivalent auth secret

### Step 4 — Frontend env vars (verify existence only — never print values)
Required:
- [ ] `VITE_SUPABASE_URL`
- [ ] `VITE_SUPABASE_ANON_KEY`
- [ ] `VITE_API_BASE_URL` (no trailing slash)
- [ ] `VITE_WS_BASE_URL` (wss:// in production)

### Step 5 — Pre-deploy code checks
- [ ] `cd backend && python -m pytest tests/ -q` — all tests pass
- [ ] `cd frontend && npx tsc --noEmit` — type-check clean
- [ ] `cd frontend && npm run build` — build succeeds
- [ ] No `.env` or secrets staged in git (`git status`)

### Step 6 — CORS sanity
- [ ] `CORS_ORIGINS` is set to the exact production domain (no trailing slash)
- [ ] `CORS_ORIGINS` is NOT `*`
- [ ] No wildcard CORS anywhere in nginx.conf

## Must never do
- SSH into the VPS autonomously
- Run `docker compose up --build` on production without explicit human approval
- Print env var values, API keys, or secrets in any output
- Apply changes to nginx.conf or docker-compose.yml without explicit human approval

## Required output

```
## VPC Deploy Audit — <date>

### docker-compose.yml
- Services: <list or MISSING>
- Health checks: <present / absent>
- Secrets in compose file: <none / FOUND: describe>

### nginx.conf
- WebSocket headers: PASS / FAIL
- SPA rewrite: PASS / FAIL
- CORS in nginx: clean / ISSUE

### Backend env vars (existence only)
- SUPABASE_URL: present / MISSING
- SUPABASE_SERVICE_ROLE_KEY: present / MISSING
- SUPABASE_ANON_KEY: present / MISSING
- GROQ_API_KEY: present / MISSING
- REDIS_URL: present / MISSING
- CORS_ORIGINS: present / MISSING
- ENVIRONMENT: present / MISSING (value: production/staging/other — safe to show env name)

### Frontend env vars (existence only)
- VITE_SUPABASE_URL: present / MISSING
- VITE_SUPABASE_ANON_KEY: present / MISSING
- VITE_API_BASE_URL: present / MISSING
- VITE_WS_BASE_URL: present / MISSING

### Code checks
- pytest: PASS / FAIL
- tsc: PASS / FAIL
- build: PASS / FAIL
- No secrets staged: PASS / FAIL

### Verdict
GO / NO-GO

### Blockers
- <list or "none">
```