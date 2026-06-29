import asyncio
import logging
import aiohttp
from config import settings

logger = logging.getLogger(__name__)
_TAVUS_BASE = "https://tavusapi.com/v2"
_POLL_INTERVAL = 2.0
_POLL_TIMEOUT = 90.0


async def generate_tavus_video(
    replica_id: str,
    script: str,
    session_id: str | None = None,
) -> str | None:
    """
    Submit a Tavus video generation job and poll until ready.
    Returns the stream/hosted URL or None on failure/timeout.
    """
    if not replica_id:
        return None

    if settings.mock_mode:
        await asyncio.sleep(2)
        return "https://example.com/mock-tavus-video.mp4"

    if not settings.tavus_api_key:
        return None

    headers = {"x-api-key": settings.tavus_api_key, "Content-Type": "application/json"}
    payload = {
        "replica_id": replica_id,
        "script": script,
        "video_name": f"echo-{session_id[:8]}" if session_id else "echopersona",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{_TAVUS_BASE}/videos", json=payload, headers=headers) as resp:
                if resp.status not in (200, 201):
                    logger.error("Tavus submit failed: %s", resp.status)
                    return None
                data = await resp.json()
                video_id = data.get("video_id")
                if not video_id:
                    return None
            # Poll for completion
            loop = asyncio.get_running_loop()
            deadline = loop.time() + _POLL_TIMEOUT
            while loop.time() < deadline:
                await asyncio.sleep(_POLL_INTERVAL)
                async with session.get(f"{_TAVUS_BASE}/videos/{video_id}", headers=headers) as poll:
                    result = await poll.json()
                    status = result.get("status")
                    if status == "ready":
                        url = result.get("stream_url") or result.get("hosted_url", "")
                        if not url.startswith("https://"):
                            logger.error("Tavus returned non-https URL, rejecting")
                            return None
                        return url
                    if status == "failed":
                        logger.error("Tavus generation failed: status=%s", status)
                        return None
                    if status == "error":
                        logger.warning("Tavus returned deprecated error status, treating as failed")
                        return None
    except Exception:
        logger.exception("Tavus video generation error")
        return None
    logger.warning("Tavus generation timed out for video_id=%s", video_id)
    return None
