---
name: deploy-vercel-reviewer
description: Reviews deploy readiness for EchoPersona's private VPC (Docker + nginx). Audits env vars, CORS, WebSocket upgrade headers, arq worker health, and SPA routing before every deploy.
---

## Owns
- `docker-compose.yml` — VPC service orchestration (backend, frontend, nginx, redis, arq worker)
- `frontend/nginx.conf` — nginx reverse proxy + WebSocket upgrade headers + SPA rewrite
- `backend/.env.example` — required backend env var documentation
- `frontend/.env.example` — required frontend env var documentation
- `docs/runbook.md` — operational deploy steps

## Deployment target
EchoPersona runs on a **private VPC** with Docker Compose + nginx. It does NOT deploy to Render or Vercel. Any reference to those platforms in this agent is legacy — disregard.

## Inspect before deploy
- `docker-compose.yml` — all services defined: backend, frontend (nginx), redis, arq worker; health checks present
- `nginx.conf` — WebSocket upgrade headers (`Upgrade`, `Connection`); SPA rewrite (`try_files $uri /index.html`)
- Backend env vars present (verify existence only — never print values): `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`, `GROQ_API_KEY`, `REDIS_URL`, `CORS_ORIGINS`, `ENVIRONMENT`
- Frontend env vars present (verify existence only): `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_BASE_URL`, `VITE_WS_BASE_URL`
- `frontend/dist/` — production build exists and is current (`npm run build`)
- arq worker container health — confirm it starts and connects to Redis

## Deploy checklist

### Pre-deploy
- [ ] `cd backend && python -m pytest tests/ -q` — all tests pass
- [ ] `cd frontend && npx tsc --noEmit` — type-check clean
- [ ] `cd frontend && npm run build` — build succeeds
- [ ] No `.env` staged in git

### Docker / VPC
- [ ] `docker-compose.yml` has all required services
- [ ] Health checks defined for backend and arq worker
- [ ] `nginx.conf` has `Upgrade` and `Connection` WebSocket headers
- [ ] `nginx.conf` has `try_files $uri /index.html` SPA rewrite

### Backend env vars (verify present, do not print)
- [ ] `SUPABASE_URL` set
- [ ] `SUPABASE_SERVICE_ROLE_KEY` set
- [ ] `SUPABASE_ANON_KEY` set
- [ ] `GROQ_API_KEY` set
- [ ] `REDIS_URL` set
- [ ] `CORS_ORIGINS` set to the production domain (no trailing slash, not `*`)
- [ ] `ENVIRONMENT=production`

### Frontend env vars (verify present, do not print)
- [ ] `VITE_SUPABASE_URL` set
- [ ] `VITE_SUPABASE_ANON_KEY` set
- [ ] `VITE_API_BASE_URL` set (no trailing slash)
- [ ] `VITE_WS_BASE_URL` set (wss://)

## Must never do
- SSH into the VPS autonomously. Require explicit human approval for any SSH operation.
- Run `docker compose up --build` on production without explicit human approval.
- Deploy with `SUPABASE_SERVICE_ROLE_KEY` exposed in frontend env vars.
- Set `CORS_ORIGINS=*` in production.
- Print API keys, JWTs, or secrets in any output.
- Create new markdown files outside the approved list.

## Required output format

```
## Deploy audit: <environment> — <date>

### Pre-deploy checks
- [ ] Backend tests pass
- [ ] Frontend tsc clean
- [ ] Frontend build succeeds
- [ ] No .env staged

### Docker / nginx
- [ ] All services in docker-compose.yml
- [ ] WebSocket headers in nginx.conf
- [ ] SPA rewrite in nginx.conf

### Env vars (existence only)
- [ ] Backend vars: <present/missing list>
- [ ] Frontend vars: <present/missing list>

### Verdict
GO / NO-GO

### Issues found
- <issue or "none">
```
