import logging

from supabase import Client, create_client

from config import settings

logger = logging.getLogger(__name__)

_client: Client | None = None


def get_db() -> Client:
    global _client
    if _client is None:
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required")
        _client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    return _client
