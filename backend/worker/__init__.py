from urllib.parse import urlparse

from arq.connections import RedisSettings

from config import settings
from worker.tasks.email import send_readiness_emails
from worker.tasks.enrichment import enrich_persona
from worker.tasks.ingestion import ingest_correction_unit, ingest_memory_unit


def _redis_settings() -> RedisSettings:
    parsed = urlparse(settings.redis_url)
    return RedisSettings(
        host=parsed.hostname or "localhost",
        port=parsed.port or 6379,
        password=parsed.password or None,
        database=int(parsed.path.lstrip("/") or "0"),
    )


class WorkerSettings:
    functions = [ingest_memory_unit, ingest_correction_unit, enrich_persona, send_readiness_emails]
    redis_settings = _redis_settings()
