import logging

from fastapi import Header, HTTPException, status
from supabase import create_client

from config import settings

logger = logging.getLogger(__name__)


async def verify_token(token: str) -> str:
    """Verify a Supabase JWT and return the authenticated user_id.

    Raises HTTPException(401) on invalid or expired token.
    Never trusts the client's claimed user_id — always extracts from verified JWT.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
        )
    try:
        client = create_client(settings.supabase_url, settings.supabase_anon_key)
        response = client.auth.get_user(token)
        if not response or not response.user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )
        return response.user.id
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Token verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )


async def get_current_user(authorization: str = Header(...)) -> str:
    """FastAPI dependency: extract and verify JWT from Authorization: Bearer <token>."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header",
        )
    token = authorization.split(" ", 1)[1]
    return await verify_token(token)
