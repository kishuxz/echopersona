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

## Stripe billing

### Local setup

1. Install the Stripe CLI: `brew install stripe/stripe-cli/stripe`
2. Authenticate: `stripe login`
3. Forward webhooks to the local backend (run in a separate terminal):
   ```bash
   stripe listen --forward-to http://localhost:8000/billing/webhook
   ```
   Copy the printed `whsec_*` value into `STRIPE_WEBHOOK_SECRET` in `backend/.env`.

### Stripe Dashboard setup

1. Switch to **Test mode** (toggle in the top-left of the dashboard).
2. Create two products with recurring monthly prices:
   - **Creator** (e.g. $9/mo) — copy the `price_*` ID into `STRIPE_PRICE_CREATOR_MONTHLY`.
   - **Legacy** (e.g. $19/mo) — copy the `price_*` ID into `STRIPE_PRICE_LEGACY_MONTHLY`.
3. Register a webhook endpoint at `https://kishoreai.online/billing/webhook` with these events:
   - `checkout.session.completed`
   - `customer.subscription.created`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
4. Copy the endpoint's signing secret into `STRIPE_WEBHOOK_SECRET` in the root `.env`.
5. Set `FRONTEND_BILLING_SUCCESS_URL=https://kishoreai.online/billing/success` and `FRONTEND_BILLING_CANCEL_URL=https://kishoreai.online/billing/cancel`.

---

## Deployment

### Primary: Private VPS at kishoreai.online — Docker Compose

**VPS outer nginx (runs on host, not in Docker):**

Handles TLS termination (port 443) and proxies to the frontend container at `localhost:3000`.
Minimum config (`/etc/nginx/sites-enabled/kishoreai.online`):

```nginx
server {
    listen 443 ssl;
    server_name kishoreai.online;

    ssl_certificate     /etc/letsencrypt/live/kishoreai.online/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/kishoreai.online/privkey.pem;

    # Allow audio file uploads (voice answers, avatars).
    client_max_body_size 50m;

    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        # Required for WebSocket upgrade (wss:// live chat).
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        # Keep WebSocket connections alive for up to 1 hour.
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}

server {
    listen 80;
    server_name kishoreai.online;
    return 301 https://$host$request_uri;
}
```

**Docker Compose deploy steps:**
1. SSH into VPS
2. `cd /opt/echopersona && git pull origin main`
3. Ensure root `.env` has all production values (see env var checklist below)
4. `docker compose up --build -d`
5. Verify: `curl https://kishoreai.online/health` → `{"status":"ok"}`
6. WebSocket: connect to `wss://kishoreai.online/ws/<session_id>?token=<jwt>`

**Rollback:**
```bash
git checkout <previous-commit>
docker compose up --build -d
```

**Important — `VITE_*` vars are baked in at build time.** Docker Compose defaults `VITE_API_BASE_URL` to `https://kishoreai.online` and `VITE_WS_BASE_URL` to `wss://kishoreai.online`. For local dev with Docker, override both in the root `.env`:
```
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_BASE_URL=ws://localhost:8000
```
Production `.env` can leave them unset (the compose defaults apply) or set them explicitly.

### Secondary/Alternative: Render (backend) + Vercel (frontend)

1. Backend → push to `main`; Render auto-deploys from `render.yaml`
2. Frontend → push to `main`; Vercel auto-deploys from `frontend/vercel.json`

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
| `PUBLIC_BASE_URL` | yes | no | D-ID audio URL base (production: `https://kishoreai.online`) |
| `DID_API_KEY` | yes | no | Optional video |
| `CARTESIA_API_KEY` | yes | no | Optional alt TTS |
| `TTS_PROVIDER` | yes | no | Optional (default: elevenlabs) |
| `STRIPE_SECRET_KEY` | yes | no | Billing (checkout + customer create) |
| `STRIPE_WEBHOOK_SECRET` | yes | no | Billing (webhook signature verification) |
| `STRIPE_PRICE_CREATOR_MONTHLY` | yes | no | Billing (Creator plan price ID) |
| `STRIPE_PRICE_LEGACY_MONTHLY` | yes | no | Billing (Legacy plan price ID) |
| `FRONTEND_BILLING_SUCCESS_URL` | yes | no | Billing (Stripe redirect after payment) |
| `FRONTEND_BILLING_CANCEL_URL` | yes | no | Billing (Stripe redirect on cancel) |

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
| CORS error | `CORS_ORIGINS` missing or wrong | Set to `https://kishoreai.online` (no trailing slash) |
| `POST /billing/checkout` returns 500 | `STRIPE_PRICE_*` env var is empty | Set the price ID env vars and restart the backend |
| Webhook returns 400 Invalid Signature | `STRIPE_WEBHOOK_SECRET` mismatched | Use the `whsec_*` from `stripe listen` output (local) or the Dashboard endpoint secret (prod) |
| `stripe_entitlements` row missing after checkout | Price ID mismatch or subscription events not registered | Confirm price IDs match exactly; add subscription events to the webhook in the Dashboard |
