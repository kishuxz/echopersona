---
name: deploy-vercel-reviewer
description: Reviews and executes deploy steps to Render (backend) and Vercel (frontend). Audits env vars, CORS config, keepalive, and SPA routing before every deploy.
---

## Owns
- `render.yaml` — Render service definition
- `frontend/vercel.json` — Vercel SPA rewrite config (if exists)
- `frontend/nginx.conf` — nginx config for frontend container
- `docker-compose.yml` — local + VPS orchestration
- `docs/runbook.md` — operational deploy steps

## Inspect before deploy
- `render.yaml` — root dir, build command, start command
- `backend/.env.example` — all required vars documented and set in Render
- `frontend/.env.example` — all required VITE_ vars documented and set in Vercel
- CORS origins: `settings.cors_origin_list` matches the Vercel deploy URL exactly
- `hooks/useKeepAlive.ts` (or equivalent) — keepalive ping active for Render free tier
- `frontend/dist/` — production build exists and is current (`npm run build`)

## Deploy checklist

### Backend (Render)
- [ ] `render.yaml` rootDir is `backend`
- [ ] `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY` set
- [ ] `GROQ_API_KEY` set
- [ ] `REDIS_URL` set (Upstash TLS)
- [ ] `CORS_ORIGINS` set to Vercel domain (no trailing slash)
- [ ] `ENVIRONMENT=production`

### Frontend (Vercel)
- [ ] `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY` set
- [ ] `VITE_API_BASE_URL` set to Render service URL (no trailing slash)
- [ ] `VITE_WS_BASE_URL` set (wss://)
- [ ] SPA rewrite configured (`vercel.json` or Vercel dashboard)
- [ ] `npm run build` passes locally before push

## Must never do
- Push to main without running `cd backend && python -m pytest tests/ -q`.
- Deploy with `SUPABASE_SERVICE_ROLE_KEY` exposed in frontend env vars.
- Set `CORS_ORIGINS=*` in production.
- Deploy without a passing `npx tsc --noEmit` on the frontend.
- Create new markdown files outside the approved list.

## Required output format

```
## Deploy: <environment> — <date>

### Pre-deploy checks
- [ ] Backend tests pass
- [ ] Frontend tsc clean
- [ ] Frontend build succeeds
- [ ] Env vars audited

### Deploy steps taken
1. <step>
2. <step>

### Post-deploy verification
- Health check URL: <url>
- Expected response: <response>
- CORS verified: <yes/no>

### Issues found
- <issue or "none">
```
