# EchoPersona — Build Progress

## Phase A — Supabase Foundation ✅ COMPLETE

**A.3 — Database schema**: Migration applied. Tables: `profiles`, `personas`, `conversations` with RLS.

**A.4 — Backend persistence**: `services/db.py`, `services/persona_store.py`, updated `models/persona.py`.

**A.5 — JWT auth**: `middleware/auth.py`, all persona endpoints + WebSocket protected.

**A.6 — Frontend auth**: `lib/supabase.ts`, `hooks/useAuth.ts`, `lib/api.ts`, full routing.

**A.7 verified**: 422 (no header), 401 (bad token), DB tables accessible.

---

## Phase B — D-ID Video Avatars ✅ COMPLETE

- `services/did.py` — async poll with 30s timeout, graceful failure
- `ws.py` — background `asyncio.Task` kicks off after `audio_end`; sends `video_ready`
- `POST /persona/{id}/upload-avatar` — Supabase Storage, saves public URL
- Frontend: avatar placeholder → spinner → `<video>` on `video_ready`

---

## Phase C — Professional Application ✅ COMPLETE

- `/` LandingPage, `/login` `/signup` AuthPage, `/dashboard` Dashboard, `/dashboard/persona/:id` PersonaDetail
- All pages TypeScript-clean, production build succeeds

---

## Phase D — Production Deployment ✅ COMPLETE

**D.1 — Config**:
- `backend/.env.example` — all required + optional vars documented
- `frontend/.env.example` — Supabase anon key + API URLs
- Upstash Redis TLS URL in `backend/.env`

**D.2 — Backend (Render)**:
- `render.yaml` at repo root — `rootDir: backend`, Python runtime, `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Startup validation: crashes with clear error if SUPABASE_URL/SERVICE_ROLE_KEY/ANON_KEY missing

**D.3 — Frontend (Vercel)**:
- `frontend/vercel.json` — SPA rewrite `/(.*) → /index.html`

**D.4 — CORS**:
- `allow_methods=["GET","POST","PUT","DELETE"]`, `allow_headers=["Authorization","Content-Type"]`
- Origins read from `CORS_ORIGINS` env var (set to Vercel URL in production)

**D.5 — Keepalive**:
- `useKeepAlive` hook: pings `/health` every 10 min from Dashboard and PersonaDetail
- Prevents Render free tier sleep during active user sessions

**Git**:
- `git init` + 70 files committed (zero `.env` files included)
- Pushed to https://github.com/kishuxz/echopersona ✅

---

## Deployment Instructions

### Backend → Render.com

1. Create new Web Service at https://render.com/dashboard
2. Connect GitHub repo `kishuxz/echopersona`
3. **Root Directory**: `backend`
4. **Build Command**: `pip install -r requirements.txt`
5. **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
6. **Python Version**: 3.11.0
7. Set environment variables:
   ```
   ENVIRONMENT=production
   DEEPGRAM_API_KEY=<key>
   GROQ_API_KEY=<key>
   ELEVENLABS_API_KEY=<key>
   ELEVENLABS_VOICE_ID=<id>
   SUPABASE_URL=https://acngivwdqttgtalopsjw.supabase.co
   SUPABASE_SERVICE_ROLE_KEY=<key>
   SUPABASE_ANON_KEY=<key>
   DID_API_KEY=<key>
   REDIS_URL=rediss://default:...@alive-bunny-121775.upstash.io:6379
   CORS_ORIGINS=https://<your-vercel-domain>.vercel.app
   ```

### Frontend → Vercel

1. Import project at https://vercel.com/new
2. Select `kishuxz/echopersona`
3. **Root Directory**: `frontend`
4. **Framework**: Vite
5. Set environment variables:
   ```
   VITE_SUPABASE_URL=https://acngivwdqttgtalopsjw.supabase.co
   VITE_SUPABASE_ANON_KEY=<anon_key>
   VITE_API_BASE_URL=https://<your-render-service>.onrender.com
   VITE_WS_BASE_URL=wss://<your-render-service>.onrender.com
   ```
6. Deploy → get Vercel URL → update `CORS_ORIGINS` in Render
