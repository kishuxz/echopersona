from fastapi import Header, HTTPException, status

from config import settings


async def require_admin(x_admin_key: str = Header(...)) -> None:
    """FastAPI dependency that gates all admin routes behind ADMIN_KEY.

    Safe-fails (403) when ADMIN_KEY is not configured — an empty key never
    grants access.
    """
    if not settings.admin_key or x_admin_key != settings.admin_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
