import psutil
from fastapi import APIRouter

from config import settings

router = APIRouter()


@router.get("/health")
async def health() -> dict:
    process = psutil.Process()
    memory_mb = process.memory_info().rss / 1024 / 1024
    return {
        "status": "ok",
        "memory_mb": round(memory_mb, 1),
        "environment": settings.environment,
        "mock_mode": settings.mock_mode,
    }
