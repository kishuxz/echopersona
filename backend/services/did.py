"""
D-ID video generation service.
Accepts a pre-generated audio URL → returns talking head video URL.
D-ID lip-syncs the avatar to the provided ElevenLabs audio (type=audio script).
Video is delivered as a separate WebSocket message: {"type": "video_ready", "url": "..."}
Degrades gracefully: if DID_API_KEY is absent or generation fails, audio still plays normally.
"""
import asyncio
import logging

import httpx

from config import settings

logger = logging.getLogger(__name__)

DID_BASE_URL = "https://api.d-id.com"
_POLL_INTERVAL_S = 2.0
_MAX_POLLS = 15  # 30s total


async def generate_talking_head(
    audio_url: str,
    source_url: str,
) -> str | None:
    """
    Submit a D-ID talk request using pre-generated audio URL.
    D-ID lip-syncs the avatar to the provided audio — no TTS generation.
    Returns the result video URL, or None if generation fails.
    """
    if not settings.did_api_key:
        logger.debug("DID_API_KEY not configured — skipping video generation")
        return None

    headers = {
        "Authorization": f"Basic {settings.did_api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    payload = {
        "source_url": source_url,
        "script": {
            "type": "audio",
            "audio_url": audio_url,
        },
        "config": {
            "fluent": True,
            "pad_audio": 0.0,
            "stitch": True,
        },
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            logger.info("[D-ID] source_url: %s", source_url)
            logger.info("[D-ID] audio_url: %s", audio_url)

            create_res = await client.post(
                f"{DID_BASE_URL}/talks",
                headers=headers,
                json=payload,
            )
            create_res.raise_for_status()
            talk_id = create_res.json()["id"]
            logger.info("[D-ID] talk submitted: %s (type=audio)", talk_id)
        except httpx.HTTPStatusError as exc:
            logger.error(
                "[D-ID] create failed: %s %s",
                exc.response.status_code,
                exc.response.text[:500],
            )
            return None

        for _ in range(_MAX_POLLS):
            await asyncio.sleep(_POLL_INTERVAL_S)
            try:
                poll_res = await client.get(
                    f"{DID_BASE_URL}/talks/{talk_id}", headers=headers
                )
                poll_res.raise_for_status()
                data = poll_res.json()
                status = data.get("status")
                if status == "done":
                    url = data.get("result_url")
                    logger.info("[D-ID] talk complete: %s", url)
                    return url
                if status == "error":
                    logger.error("[D-ID] talk error: %s", data.get("error"))
                    return None
            except httpx.HTTPStatusError as exc:
                logger.error("[D-ID] poll failed: %s", exc.response.status_code)
                return None

    logger.warning("[D-ID] timed out after %ds", _MAX_POLLS * _POLL_INTERVAL_S)
    return None
