from fastapi import APIRouter

from config import settings


router = APIRouter()


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "environment": settings.environment,
        "mock_mode": settings.mock_mode,
    }
