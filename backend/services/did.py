"""
D-ID video generation service.
Takes collected TTS audio + source image URL → returns talking head video URL.
Called AFTER audio has already been streamed to the client.
Video is delivered as a separate WebSocket message: {"type": "video_ready", "url": "..."}
Degrades gracefully: if DID_API_KEY is absent or generation fails, audio still played normally.
"""
import asyncio
import logging

import httpx

from config import settings

logger = logging.getLogger(__name__)

DID_BASE_URL = "https://api.d-id.com"
_POLL_INTERVAL_S = 2.0
_MAX_POLLS = 15  # 30s total


async def generate_talking_head(audio_base64: str, source_url: str) -> str | None:
    """
    Submit a D-ID talk request and poll until complete.
    Returns the result video URL, or None if generation fails or is skipped.
    Audio must be base64-encoded MP3.
    """
    if not settings.did_api_key:
        logger.debug("DID_API_KEY not configured — skipping video generation")
        return None

    headers = {
        "Authorization": f"Basic {settings.did_api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

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
                },
            )
            create_res.raise_for_status()
            talk_id = create_res.json()["id"]
            logger.info("D-ID talk submitted: %s", talk_id)

        except httpx.HTTPStatusError as exc:
            logger.error(
                "D-ID create failed: %s %s",
                exc.response.status_code,
                exc.response.text,
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
                    logger.info("D-ID talk complete: %s", url)
                    return url

                if status == "error":
                    logger.error("D-ID talk error: %s", data.get("error"))
                    return None

            except httpx.HTTPStatusError as exc:
                logger.error("D-ID poll failed: %s", exc.response.status_code)
                return None

    logger.warning("D-ID generation timed out after %ds", _MAX_POLLS * _POLL_INTERVAL_S)
    return None
