import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from arq.connections import create_pool

from config import settings
from routers import creation, health, ingest, persona, ws
from worker import WorkerSettings

logger = logging.getLogger(__name__)

_REQUIRED_ALWAYS = [
    ("supabase_url", "SUPABASE_URL"),
    ("supabase_service_role_key", "SUPABASE_SERVICE_ROLE_KEY"),
    ("supabase_anon_key", "SUPABASE_ANON_KEY"),
]
_REQUIRED_LIVE = [
    ("groq_api_key", "GROQ_API_KEY"),
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    missing = [name for attr, name in _REQUIRED_ALWAYS if not getattr(settings, attr)]
    if not settings.mock_mode:
        missing += [name for attr, name in _REQUIRED_LIVE if not getattr(settings, attr)]
    if missing:
        logger.critical("Missing required environment variables: %s", ", ".join(missing))
        sys.exit(1)
    logger.info(
        "EchoPersona starting — environment=%s mock_mode=%s",
        settings.environment,
        settings.mock_mode,
    )
    app.state.arq_pool = await create_pool(WorkerSettings.redis_settings)
    yield
    await app.state.arq_pool.aclose()


app = FastAPI(title="EchoPersona", version="1.0.0", lifespan=lifespan)

os.makedirs("/tmp/echopersona_audio", exist_ok=True)
app.mount("/audio", StaticFiles(directory="/tmp/echopersona_audio"), name="audio")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

app.include_router(health.router)
app.include_router(persona.router)
app.include_router(ingest.router)
app.include_router(creation.router)
app.include_router(ws.router)
