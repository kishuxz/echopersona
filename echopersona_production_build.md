# EchoPersona — Production Build Spec
## Senior Engineer Standards. Live Product. Job Application Differentiator.

---

## Context

EchoPersona is a real-time conversational AI avatar system — already built and
working locally. Core pipeline (STT → RAG → LLM → TTS) achieves sub-600ms
utterance-to-utterance latency. Phase 1 and Phase 2 are complete.

This document specifies the production upgrade: Supabase auth + persistence,
D-ID video avatars, professional marketing site, and live deployment.

The reviewer is a senior engineer and serial founder. Every decision must
reflect production engineering standards — not tutorial code.

REPO: /Users/kishorekumar/echopersona

---

## Non-Negotiable Engineering Standards

Before writing a single line of code, internalize these. Violating any of
them is an automatic fail in a senior engineer review.

**Security**
- Never expose service role keys to the frontend. Supabase anon key only.
- All backend API calls to Supabase use the service role key server-side.
- JWT validation on every authenticated WebSocket connection.
- RLS policies on every Supabase table — no exceptions.
- Environment variables never hardcoded, never committed.
- API keys validated at startup — crash fast with clear error if missing.

**Error Handling**
- Every external API call (Groq, ElevenLabs, Deepgram, D-ID, Supabase)
  wrapped in try/except with specific error types, not bare Exception.
- Errors logged with context (user_id, session_id, timestamp).
- Client receives clean error messages, never stack traces.
- Graceful degradation: if D-ID fails, fall back to audio-only.
  If ElevenLabs fails, return error. Never silent failures.

**Code Quality**
- No dead code, no commented-out blocks, no TODO left in production paths.
- Consistent naming: snake_case Python, camelCase TypeScript.
- Every function has a single responsibility.
- No function longer than 50 lines. Extract if needed.
- Type hints on every Python function. TypeScript strict mode.

**Database**
- Migrations, not manual schema changes.
- Foreign keys enforced at DB level.
- Indexes on every column used in WHERE clauses.
- Never SELECT * in production queries.
- Timestamps (created_at, updated_at) on every table.

---

## Phase A — Supabase Foundation

### A.1 — Read current state first

Read these files before touching anything:
- backend/main.py
- backend/routers/persona.py
- backend/models/persona.py
- backend/config.py
- frontend/src/App.tsx
- frontend/src/components/PersonaUpload.tsx

Understand exactly how personas are currently stored (in-memory dict)
and how the WebSocket authenticates sessions before making any changes.

### A.2 — Supabase project setup

You will need these from the Supabase dashboard (ask user to provide):
- SUPABASE_URL
- SUPABASE_ANON_KEY (frontend only)
- SUPABASE_SERVICE_ROLE_KEY (backend only, never frontend)

Add to backend .env:
```
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
```

Add to frontend .env:
```
VITE_SUPABASE_URL=
VITE_SUPABASE_ANON_KEY=
```

### A.3 — Database schema (run as migration in Supabase SQL editor)

```sql
-- Enable UUID extension
create extension if not exists "uuid-ossp";

-- Users are handled by Supabase Auth (auth.users)
-- We extend with a profiles table for app-specific data

create table public.profiles (
  id uuid references auth.users(id) on delete cascade primary key,
  full_name text,
  avatar_url text,
  created_at timestamptz default now() not null,
  updated_at timestamptz default now() not null
);

create table public.personas (
  id uuid default uuid_generate_v4() primary key,
  user_id uuid references auth.users(id) on delete cascade not null,
  name text not null,
  stories text[] not null default '{}',
  personality_traits text[] not null default '{}',
  speaking_style text not null default '',
  voice_id text,
  did_avatar_url text,
  created_at timestamptz default now() not null,
  updated_at timestamptz default now() not null
);

create table public.conversations (
  id uuid default uuid_generate_v4() primary key,
  persona_id uuid references public.personas(id) on delete cascade not null,
  user_id uuid references auth.users(id) on delete cascade not null,
  messages jsonb not null default '[]',
  created_at timestamptz default now() not null,
  updated_at timestamptz default now() not null
);

-- Indexes
create index personas_user_id_idx on public.personas(user_id);
create index conversations_persona_id_idx on public.conversations(persona_id);
create index conversations_user_id_idx on public.conversations(user_id);

-- Row Level Security
alter table public.profiles enable row level security;
alter table public.personas enable row level security;
alter table public.conversations enable row level security;

-- RLS Policies: users can only access their own data
create policy "Users can view own profile"
  on public.profiles for select
  using (auth.uid() = id);

create policy "Users can update own profile"
  on public.profiles for update
  using (auth.uid() = id);

create policy "Users can insert own profile"
  on public.profiles for insert
  with check (auth.uid() = id);

create policy "Users can view own personas"
  on public.personas for select
  using (auth.uid() = user_id);

create policy "Users can create own personas"
  on public.personas for insert
  with check (auth.uid() = user_id);

create policy "Users can update own personas"
  on public.personas for update
  using (auth.uid() = user_id);

create policy "Users can delete own personas"
  on public.personas for delete
  using (auth.uid() = user_id);

create policy "Users can view own conversations"
  on public.conversations for select
  using (auth.uid() = user_id);

create policy "Users can create own conversations"
  on public.conversations for insert
  with check (auth.uid() = user_id);

-- Auto-create profile on signup
create or replace function public.handle_new_user()
returns trigger as $$
begin
  insert into public.profiles (id, full_name)
  values (new.id, new.raw_user_meta_data->>'full_name');
  return new;
end;
$$ language plpgsql security definer;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();

-- Auto-update updated_at
create or replace function public.handle_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger personas_updated_at
  before update on public.personas
  for each row execute procedure public.handle_updated_at();

create trigger conversations_updated_at
  before update on public.conversations
  for each row execute procedure public.handle_updated_at();
```

### A.4 — Backend: replace in-memory storage with Supabase

Install: `pip install supabase`

Create backend/services/db.py:

```python
from supabase import create_client, Client
from backend.config import settings
import logging

logger = logging.getLogger(__name__)

_client: Client | None = None

def get_db() -> Client:
    global _client
    if _client is None:
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required")
        _client = create_client(
            settings.supabase_url,
            settings.supabase_service_role_key  # service role — backend only
        )
    return _client
```

Create backend/services/persona_store.py to replace the in-memory dict:

```python
"""
Persona persistence layer — Supabase Postgres.
All methods are async wrappers around the Supabase Python client.
Service role key used here — this module is backend-only.
"""
from uuid import UUID
from backend.models.persona import Persona, PersonaCreate
from backend.services.db import get_db
import logging

logger = logging.getLogger(__name__)


async def create_persona(user_id: str, data: PersonaCreate) -> Persona:
    db = get_db()
    result = db.table("personas").insert({
        "user_id": user_id,
        "name": data.name,
        "stories": data.stories,
        "personality_traits": data.personality_traits,
        "speaking_style": data.speaking_style,
    }).execute()

    if not result.data:
        raise RuntimeError("Failed to create persona")

    return Persona(**result.data[0])


async def get_persona(persona_id: str, user_id: str) -> Persona | None:
    db = get_db()
    result = db.table("personas") \
        .select("id, user_id, name, stories, personality_traits, speaking_style, voice_id, did_avatar_url, created_at") \
        .eq("id", persona_id) \
        .eq("user_id", user_id) \
        .single() \
        .execute()

    if not result.data:
        return None

    return Persona(**result.data)


async def list_personas(user_id: str) -> list[Persona]:
    db = get_db()
    result = db.table("personas") \
        .select("id, user_id, name, stories, personality_traits, speaking_style, voice_id, did_avatar_url, created_at") \
        .eq("user_id", user_id) \
        .order("created_at", desc=True) \
        .execute()

    return [Persona(**row) for row in result.data]


async def update_persona_voice(persona_id: str, user_id: str, voice_id: str) -> None:
    db = get_db()
    db.table("personas") \
        .update({"voice_id": voice_id}) \
        .eq("id", persona_id) \
        .eq("user_id", user_id) \
        .execute()


async def update_persona_avatar(persona_id: str, user_id: str, avatar_url: str) -> None:
    db = get_db()
    db.table("personas") \
        .update({"did_avatar_url": avatar_url}) \
        .eq("id", persona_id) \
        .eq("user_id", user_id) \
        .execute()


async def delete_persona(persona_id: str, user_id: str) -> None:
    db = get_db()
    db.table("personas") \
        .delete() \
        .eq("id", persona_id) \
        .eq("user_id", user_id) \
        .execute()
```

### A.5 — Backend: JWT authentication middleware

WebSocket connections must be authenticated. The frontend sends the
Supabase JWT as a query parameter on connect.

Create backend/middleware/auth.py:

```python
"""
JWT validation for WebSocket and HTTP endpoints.
Uses Supabase's JWKS endpoint to verify tokens.
Never trusts the client's claimed user_id — always extract from verified JWT.
"""
from fastapi import HTTPException, status
from supabase import create_client
from backend.config import settings
import logging

logger = logging.getLogger(__name__)


async def verify_token(token: str) -> str:
    """
    Verifies a Supabase JWT and returns the authenticated user_id.
    Raises HTTPException on invalid/expired token.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token"
        )

    try:
        client = create_client(settings.supabase_url, settings.supabase_anon_key)
        user = client.auth.get_user(token)
        if not user or not user.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token"
            )
        return user.user.id
    except Exception as e:
        logger.warning(f"Token verification failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )
```

Update backend/routers/ws.py WebSocket endpoint signature:

```python
@router.websocket("/ws/{session_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    session_id: str,
    persona_id: str,
    token: str,  # Supabase JWT passed as query param
):
    # Verify JWT before accepting connection
    try:
        user_id = await verify_token(token)
    except HTTPException:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    # Verify persona belongs to this user
    persona = await get_persona(persona_id, user_id)
    if not persona:
        await websocket.close(code=4004, reason="Persona not found")
        return

    await websocket.accept()
    # ... rest of pipeline
```

Update backend/routers/persona.py to require auth on all endpoints:

```python
from fastapi import APIRouter, Depends, HTTPException, Header
from backend.middleware.auth import verify_token

router = APIRouter(prefix="/persona", tags=["persona"])

async def get_current_user(authorization: str = Header(...)) -> str:
    """Extract and verify JWT from Authorization: Bearer <token> header."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid authorization header")
    token = authorization.split(" ", 1)[1]
    return await verify_token(token)

@router.post("/create")
async def create_persona(
    data: PersonaCreate,
    user_id: str = Depends(get_current_user)
):
    persona = await persona_store.create_persona(user_id, data)
    # Build FAISS index for this persona
    rag_instances[persona.id] = PersonaRAG()
    rag_instances[persona.id].build_index(persona.stories)
    return persona

@router.get("/")
async def list_personas(user_id: str = Depends(get_current_user)):
    return await persona_store.list_personas(user_id)

@router.get("/{persona_id}")
async def get_persona_endpoint(
    persona_id: str,
    user_id: str = Depends(get_current_user)
):
    persona = await persona_store.get_persona(persona_id, user_id)
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")
    return persona

@router.delete("/{persona_id}")
async def delete_persona_endpoint(
    persona_id: str,
    user_id: str = Depends(get_current_user)
):
    await persona_store.delete_persona(persona_id, user_id)
    rag_instances.pop(persona_id, None)
    return {"status": "deleted"}
```

### A.6 — Frontend: Supabase auth

Install: `npm install @supabase/supabase-js`

Create frontend/src/lib/supabase.ts:

```typescript
import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY

if (!supabaseUrl || !supabaseAnonKey) {
  throw new Error('Missing Supabase environment variables')
}

export const supabase = createClient(supabaseUrl, supabaseAnonKey)
```

Create frontend/src/hooks/useAuth.ts:

```typescript
import { useEffect, useState } from 'react'
import { User, Session } from '@supabase/supabase-js'
import { supabase } from '../lib/supabase'

export function useAuth() {
  const [user, setUser] = useState<User | null>(null)
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    supabase.auth.getSession().then(({ data: { session } }) => {
      setSession(session)
      setUser(session?.user ?? null)
      setLoading(false)
    })

    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (_event, session) => {
        setSession(session)
        setUser(session?.user ?? null)
      }
    )

    return () => subscription.unsubscribe()
  }, [])

  const signUp = async (email: string, password: string, fullName: string) => {
    const { error } = await supabase.auth.signUp({
      email,
      password,
      options: { data: { full_name: fullName } }
    })
    if (error) throw error
  }

  const signIn = async (email: string, password: string) => {
    const { error } = await supabase.auth.signInWithPassword({ email, password })
    if (error) throw error
  }

  const signOut = async () => {
    const { error } = await supabase.auth.signOut()
    if (error) throw error
  }

  return { user, session, loading, signUp, signIn, signOut }
}
```

All API calls from frontend must include the JWT:

```typescript
// frontend/src/lib/api.ts
import { supabase } from './supabase'

async function getAuthHeaders(): Promise<HeadersInit> {
  const { data: { session } } = await supabase.auth.getSession()
  if (!session) throw new Error('Not authenticated')
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${session.access_token}`
  }
}

export async function createPersona(data: PersonaCreate): Promise<Persona> {
  const headers = await getAuthHeaders()
  const res = await fetch(`${import.meta.env.VITE_API_BASE_URL}/persona/create`, {
    method: 'POST',
    headers,
    body: JSON.stringify(data)
  })
  if (!res.ok) {
    const err = await res.json()
    throw new Error(err.detail || 'Failed to create persona')
  }
  return res.json()
}

export async function listPersonas(): Promise<Persona[]> {
  const headers = await getAuthHeaders()
  const res = await fetch(`${import.meta.env.VITE_API_BASE_URL}/persona/`, { headers })
  if (!res.ok) throw new Error('Failed to fetch personas')
  return res.json()
}

export function buildWsUrl(sessionId: string, personaId: string, token: string): string {
  const base = import.meta.env.VITE_WS_BASE_URL || 'ws://localhost:8000'
  return `${base}/ws/${sessionId}?persona_id=${personaId}&token=${token}`
}
```

### A.7 — Test Phase A end-to-end

1. Start backend: `uvicorn main:app --port 8000`
2. Start frontend: `npm run dev`
3. Sign up with a real email at http://localhost:5173
4. Create a persona — verify it appears in Supabase dashboard → Table Editor
5. Refresh page — persona must still be there (persistence test)
6. Try accessing another user's persona via curl with wrong JWT → must get 401
7. WebSocket connection without token → must be rejected with code 4001

---

## Phase B — D-ID Video Avatars

### B.1 — What D-ID does

D-ID takes: (1) a face image and (2) an audio file
Returns: a talking head video of the face speaking the audio.

In the pipeline:
```
TTS generates MP3 → D-ID animates face → browser plays video
```

The latency cost is ~2-4s for video generation — D-ID is not real-time.
Architecture decision: use D-ID for the "full response" video,
while audio plays immediately via the existing sub-600ms pipeline.

This is the honest production pattern — audio first (fast), video follows.

### B.2 — D-ID service

Sign up at d-id.com. Free tier: 20 credits (~20 seconds of video).
Get API key from dashboard.

Add to .env:
```
DID_API_KEY=
DID_DEFAULT_SOURCE_URL=  # URL to a face image (or user uploads one)
```

Create backend/services/did.py:

```python
"""
D-ID video generation service.
Takes collected TTS audio + source image → returns talking head video URL.
Called AFTER audio has already been streamed to client.
Video is delivered as a separate message type: {"type": "video_ready", "url": "..."}
"""
import asyncio
import httpx
import base64
import logging
from backend.config import settings

logger = logging.getLogger(__name__)

DID_BASE_URL = "https://api.d-id.com"


async def generate_talking_head(
    audio_base64: str,
    source_url: str,
) -> str | None:
    """
    Submits a D-ID talk request and polls until complete.
    Returns video URL or None if generation fails.
    Audio must be base64-encoded MP3.
    """
    if not settings.did_api_key:
        logger.warning("DID_API_KEY not set — skipping video generation")
        return None

    headers = {
        "Authorization": f"Basic {settings.did_api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    # Submit talk request
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            create_res = await client.post(
                f"{DID_BASE_URL}/talks",
                headers=headers,
                json={
                    "source_url": source_url,
                    "script": {
                        "type": "audio",
                        "audio_url": f"data:audio/mp3;base64,{audio_base64}",
                    },
                    "config": {
                        "fluent": True,
                        "pad_audio": 0.0,
                        "stitch": True,
                    },
                }
            )
            create_res.raise_for_status()
            talk_id = create_res.json()["id"]

        except httpx.HTTPStatusError as e:
            logger.error(f"D-ID create failed: {e.response.status_code} {e.response.text}")
            return None

        # Poll for completion (max 30s)
        for attempt in range(15):
            await asyncio.sleep(2)
            try:
                status_res = await client.get(
                    f"{DID_BASE_URL}/talks/{talk_id}",
                    headers=headers
                )
                status_res.raise_for_status()
                data = status_res.json()

                if data["status"] == "done":
                    return data.get("result_url")
                elif data["status"] == "error":
                    logger.error(f"D-ID talk failed: {data.get('error')}")
                    return None

            except httpx.HTTPStatusError as e:
                logger.error(f"D-ID poll failed: {e.response.status_code}")
                return None

    logger.warning("D-ID timed out after 30s")
    return None
```

### B.3 — Wire D-ID into ws.py pipeline

After TTS audio is fully collected, kick off D-ID generation as a
background task. When ready, send video_ready message to client.

In ws.py, after the TTS pipeline completes a full response:

```python
# Collect all TTS audio chunks for D-ID (runs in parallel with streaming)
full_audio_chunks = []  # accumulate during TTS streaming

# After audio_end is sent to client:
if persona.did_avatar_url and settings.did_api_key:
    full_audio_b64 = base64.b64encode(b"".join(full_audio_chunks)).decode()
    asyncio.create_task(
        _generate_and_send_video(
            websocket=websocket,
            audio_b64=full_audio_b64,
            source_url=persona.did_avatar_url,
        )
    )

async def _generate_and_send_video(
    websocket: WebSocket,
    audio_b64: str,
    source_url: str,
) -> None:
    try:
        video_url = await did.generate_talking_head(audio_b64, source_url)
        if video_url:
            await websocket.send_json({
                "type": "video_ready",
                "url": video_url,
            })
    except Exception as e:
        logger.error(f"Video generation failed: {e}")
        # Silent failure — audio already played, video is enhancement only
```

### B.4 — Frontend: video playback

In VoiceInterface.tsx, handle video_ready message:

```typescript
// Add video ref to component
const videoRef = useRef<HTMLVideoElement>(null)
const [videoUrl, setVideoUrl] = useState<string | null>(null)

// In WebSocket message handler:
case 'video_ready':
  setVideoUrl(msg.url)
  if (videoRef.current) {
    videoRef.current.src = msg.url
    videoRef.current.play()
  }
  break

// In JSX — video player with fallback to avatar placeholder:
{videoUrl ? (
  <video
    ref={videoRef}
    className="w-48 h-48 rounded-full object-cover border-2 border-green"
    autoPlay
    playsInline
  />
) : (
  <div className="w-48 h-48 rounded-full bg-surface border-2 border-border
                  flex items-center justify-center">
    <span className="font-mono text-textdim text-sm">
      {isProcessing ? 'generating...' : persona?.name?.[0] ?? '?'}
    </span>
  </div>
)}
```

### B.5 — Avatar image upload

Add to PersonaUpload — step to upload a face photo for D-ID:

```typescript
// After voice cloning step, add:
if (avatarImage) {
  const formData = new FormData()
  formData.append('file', avatarImage)
  const headers = await getAuthHeadersNoContentType()
  const res = await fetch(
    `${API_BASE}/persona/${personaId}/upload-avatar`,
    { method: 'POST', headers, body: formData }
  )
  // Backend uploads to Supabase Storage, saves public URL to persona
}
```

Backend endpoint: store image in Supabase Storage, return public URL,
save to persona.did_avatar_url.

---

## Phase C — Professional Application

### C.1 — App structure

Replace the current single-page layout with a proper routed application.

Install: `npm install react-router-dom`

Routes:
```
/                    → LandingPage (public)
/login               → AuthPage (login tab)
/signup              → AuthPage (signup tab)
/dashboard           → Dashboard (protected)
/dashboard/persona/:id → PersonaDetail (protected)
/dashboard/conversation/:id → ConversationView (protected)
```

Create frontend/src/router.tsx:

```typescript
import { createBrowserRouter, Navigate } from 'react-router-dom'
import { LandingPage } from './pages/LandingPage'
import { AuthPage } from './pages/AuthPage'
import { Dashboard } from './pages/Dashboard'
import { PersonaDetail } from './pages/PersonaDetail'
import { ProtectedRoute } from './components/ProtectedRoute'

export const router = createBrowserRouter([
  { path: '/', element: <LandingPage /> },
  { path: '/login', element: <AuthPage mode="login" /> },
  { path: '/signup', element: <AuthPage mode="signup" /> },
  {
    path: '/dashboard',
    element: <ProtectedRoute><Dashboard /></ProtectedRoute>
  },
  {
    path: '/dashboard/persona/:personaId',
    element: <ProtectedRoute><PersonaDetail /></ProtectedRoute>
  },
])
```

ProtectedRoute: redirect to /login if no session.

### C.2 — Landing page

The landing page is the founder's first impression. It must:
- Load in under 2 seconds
- Communicate the product value in 5 seconds
- Have a clear CTA above the fold

Structure:
```
[Nav] Logo | Features | How It Works | Pricing | Login | Get Started →

[Hero]
"Talk to the people you love. Forever."
Sub-headline: Real-time AI personas built from memories, stories, and voice.
CTA: [Create Your Legacy →] [Watch Demo ▶]
Latency badge: ⚡ Sub-600ms response — feels like a real conversation

[Social proof]
Stat cards: <600ms latency | 50+ concurrent users | Voice cloned in 2 min

[How It Works — 3 steps]
1. Upload Stories — Share memories, personality, speaking style
2. Clone Voice — 30 seconds of audio is all it takes
3. Start Talking — Real-time voice conversation, in their voice

[Features]
RAG-backed memory | Voice cloning | Live latency dashboard | Secure & private

[CTA Section]
"Preserve someone's voice today."
[Get Started Free →]

[Footer]
```

Design rules (match EchoPersona aesthetic):
- Background: #0a0a0a
- Accent: #00ff88
- All text: Inter
- Numbers/code: JetBrains Mono
- No stock photos — use CSS/SVG illustrations only
- Animations: subtle, purposeful (not decorative)

### C.3 — Auth page

Single page with login/signup tabs.
Supabase Auth handles email verification.

```typescript
// Clean, minimal auth form
// Email + password for both login and signup
// Signup adds full name field
// Error messages shown inline, not as alerts
// "Forgot password" link → Supabase password reset email
// After login → redirect to /dashboard
// After signup → show "Check your email to confirm" message
```

### C.4 — Dashboard

After login, user sees their personas.

Layout:
```
[Sidebar]
- EchoPersona logo
- Dashboard (home)
- My Personas
- Settings
- Sign Out

[Main Content]
Header: "My Personas" + "New Persona" button

[Persona Cards Grid]
Each card:
- Persona name
- Created date
- Number of stories
- Voice status (cloned / default)
- Avatar status (image / none)
- [Talk Now] [Edit] [Delete] buttons
```

### C.5 — Conversation view

This is the core product screen. When user clicks "Talk Now":

Layout:
```
Left panel (35%):
  - Persona info card (name, avatar, traits)
  - Conversation history list

Right panel (65%):
  - Video avatar (D-ID) or avatar placeholder (top, prominent)
  - Live latency dashboard (below avatar)
  - Voice interface (mic button, pipeline status)
  - Transcript (scrolling, real-time)
```

This screen should feel like a real product, not a demo.

---

## Phase D — Production Deployment

### D.1 — Environment configuration

Production requires separate .env values.
Never use development keys in production.

Backend production .env (set on Render):
```
ENVIRONMENT=production
DEEPGRAM_API_KEY=
GROQ_API_KEY=
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_ANON_KEY=
DID_API_KEY=
CORS_ORIGINS=https://your-vercel-domain.vercel.app
REDIS_URL=  # Render Redis or Upstash free tier
```

Frontend production .env (set on Vercel):
```
VITE_SUPABASE_URL=
VITE_SUPABASE_ANON_KEY=
VITE_API_BASE_URL=https://your-render-backend.onrender.com
VITE_WS_BASE_URL=wss://your-render-backend.onrender.com
```

### D.2 — Backend deployment (Render)

render.yaml at repo root:
```yaml
services:
  - type: web
    name: echopersona-backend
    env: python
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn main:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: PYTHON_VERSION
        value: 3.11.0
    rootDir: backend
```

### D.3 — Frontend deployment (Vercel)

vercel.json at frontend root:
```json
{
  "rewrites": [
    { "source": "/(.*)", "destination": "/index.html" }
  ]
}
```

### D.4 — CORS configuration

Backend must only allow requests from the production frontend domain.
In production, CORS_ORIGINS must be the exact Vercel URL — not wildcard.

```python
# backend/main.py
origins = settings.cors_origins.split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
```

### D.5 — WebSocket production considerations

Render free tier sleeps after 15 minutes of inactivity.
Add a health ping from frontend every 10 minutes to prevent sleep:

```typescript
// Keep backend alive during active sessions
useEffect(() => {
  const interval = setInterval(() => {
    fetch(`${API_BASE}/health`).catch(() => {})
  }, 10 * 60 * 1000)
  return () => clearInterval(interval)
}, [])
```

---

## Phase E — Build Order for Claude Code

Execute strictly in this order. Each step must be tested before next.

```
1.  Run Supabase schema migration (A.3) — verify tables exist in dashboard
2.  backend/services/db.py — Supabase client singleton
3.  backend/services/persona_store.py — replace in-memory dict
4.  backend/middleware/auth.py — JWT verification
5.  backend/routers/persona.py — add auth dependency to all endpoints
6.  backend/routers/ws.py — add token param, verify on connect
7.  backend/config.py — add Supabase env vars
8.  Test Phase A: signup → create persona → verify in DB → WS auth
9.  backend/services/did.py — D-ID integration
10. Wire D-ID into ws.py pipeline
11. frontend/src/lib/supabase.ts — Supabase client
12. frontend/src/hooks/useAuth.ts — auth state
13. frontend/src/lib/api.ts — authenticated API calls
14. frontend/src/pages/AuthPage.tsx — login/signup
15. frontend/src/components/ProtectedRoute.tsx
16. frontend/src/router.tsx — routing setup
17. frontend/src/pages/LandingPage.tsx — marketing page
18. frontend/src/pages/Dashboard.tsx — persona list
19. frontend/src/pages/PersonaDetail.tsx — conversation view
20. Test Phase B+C: full flow signup → create persona → talk → video
21. render.yaml — backend deployment config
22. vercel.json — frontend deployment config
23. Deploy backend to Render, set env vars
24. Deploy frontend to Vercel, set env vars
25. Test production: full flow on live URLs
26. Update README with live URL
```

---

## Definition of Done

The product is complete when a reviewer can:

- [ ] Visit a live URL (not localhost)
- [ ] Sign up with their email and receive confirmation
- [ ] Log in and see their dashboard
- [ ] Create a persona with stories and voice sample
- [ ] Click "Talk Now" and have a real-time voice conversation
- [ ] See the latency dashboard showing real sub-600ms numbers
- [ ] See a D-ID video avatar respond (or graceful fallback)
- [ ] Log out and log back in with data persisted
- [ ] Attempt to access another user's persona and be rejected (RLS)
- [ ] See professional landing page that explains the product clearly

---

## What This Demonstrates to the Hiring Team

**Senior engineering judgment:**
- RLS instead of application-level auth checks
- Service role key never in frontend
- JWT on WebSocket (non-trivial)
- Graceful degradation (D-ID fails → audio still works)
- Parallel async calls (RAG + Redis with asyncio.gather)

**Production thinking:**
- Migrations not manual schema changes
- Environment-specific configuration
- CORS locked to specific origins
- Crash-fast on missing config at startup

**Product instinct:**
- Audio plays immediately (<600ms), video follows async
- Persona data persists across sessions
- Multi-user with proper isolation
- Latency dashboard is the hero element

This is the work of someone who has shipped production systems,
not someone who followed a tutorial.
