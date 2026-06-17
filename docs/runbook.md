# EchoPersona — Runbook

Operational commands and steps. Update this file when deploy steps or commands change.

---

## Local development

```bash
# Clone + setup
git clone https://github.com/kishuxz/echopersona
cd echopersona
cp .env.example .env
# Edit .env — add SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, SUPABASE_ANON_KEY, GROQ_API_KEY, etc.

# Docker (full stack)
docker compose up --build

# Without Docker — backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --port 8000 --reload

# Without Docker — frontend
cd frontend
npm install
npm run dev   # → http://localhost:5173

# arq worker (needed for ingestion)
cd backend && source .venv/bin/activate
arq worker.WorkerSettings
```

---

## Testing

```bash
# All backend tests
cd backend && python -m pytest tests/ -q

# Specific test file
cd backend && python -m pytest tests/test_creation.py -v

# Frontend type check
cd frontend && npx tsc --noEmit

# Frontend build
cd frontend && npm run build
```

---

## Database migrations

Migrations live in two places:
- `backend/migrations/` — numbered `NNN_description.sql`
- `supabase/migrations/` — Supabase CLI format

**To apply a migration:**
1. Copy SQL to Supabase SQL editor at https://supabase.com/dashboard
2. Run it (idempotent; all migrations use `IF NOT EXISTS` / `IF NOT EXISTS` guards)
3. Verify in Table Editor that columns/tables exist

**Pending migrations:**
- `backend/migrations/004_creation_fields.sql` — adds `persona_id`, `source_question_id`,
  `source_type`, `supersedes`, `captured_at`, `media_ref` to `memory_units`

---

## Deployment

### Backend → Render.com

1. Push to `main` (Render auto-deploys on push)
2. Or manually: Render dashboard → Manual Deploy
3. Required env vars: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_ANON_KEY`,
   `GROQ_API_KEY`, `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID`, `REDIS_URL`, `CORS_ORIGINS`

### Frontend → Vercel

1. Push to `main` (Vercel auto-deploys)
2. Required env vars: `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_BASE_URL`,
   `VITE_WS_BASE_URL`

### Environment variable checklist

| Var | Backend | Frontend | Required |
|---|---|---|---|
| `SUPABASE_URL` | yes | yes (VITE_) | Always |
| `SUPABASE_SERVICE_ROLE_KEY` | yes | no | Backend always |
| `SUPABASE_ANON_KEY` | yes | yes (VITE_) | Always |
| `GROQ_API_KEY` | yes | no | Live mode |
| `ELEVENLABS_API_KEY` | yes | no | TTS live mode |
| `ELEVENLABS_VOICE_ID` | yes | no | TTS live mode |
| `REDIS_URL` | yes | no | Rate limiting |
| `CORS_ORIGINS` | yes | no | Production |
| `DID_API_KEY` | yes | no | Optional video |
| `CARTESIA_API_KEY` | yes | no | Optional alt TTS |
| `TTS_PROVIDER` | yes | no | Optional (default: elevenlabs) |

---

## Mock mode

Set `MOCK_MODE=true` to run the full pipeline without Groq/ElevenLabs/D-ID API keys.
Useful for testing WebSocket flow and UI.

```bash
MOCK_MODE=true uvicorn main:app --port 8000 --reload
```

---

## Load testing

```bash
# Mock mode (measures server concurrency)
MOCK_MODE=true uvicorn main:app --port 8001 &
python tests/load_test.py <persona_id> --base ws://localhost:8001

# Live mode
python tests/load_test.py <persona_id>
```

---

## Groq rate limit monitoring

```bash
# Check current RPM counter (if Redis is accessible locally)
redis-cli -u $REDIS_URL GET groq:rpm:$(date +%s | awk '{print int($1/60)}')
```

---

## Common issues

| Symptom | Likely cause | Fix |
|---|---|---|
| 422 on any API call | Missing or malformed JWT | Check `Authorization: Bearer <token>` header |
| 401 on API call | Expired or invalid Supabase JWT | Re-login; check `SUPABASE_ANON_KEY` |
| Ingestion stuck | arq worker not running | `arq worker.WorkerSettings` in backend dir |
| Evaluator always advances | Groq rate limit hit | Check Redis RPM counter; wait 60s |
| `memory_units` insert fails | Migration 004 not applied | Run `004_creation_fields.sql` in Supabase |
| CORS error | `CORS_ORIGINS` missing or wrong | Set to exact Vercel domain including protocol |
