"""
D-ID video generation service.
Takes LLM response text + source image URL → returns talking head video URL.
D-ID renders TTS internally (ElevenLabs when voice_id present, Microsoft fallback).
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

_MS_PROVIDER = {"type": "microsoft", "voice_id": "en-US-JennyNeural"}


async def _create_talk(
    client: httpx.AsyncClient,
    headers: dict,
    source_url: str,
    text: str,
    provider: dict,
) -> str | None:
    """POST /talks; returns talk_id or None on HTTP error."""
    try:
        res = await client.post(
            f"{DID_BASE_URL}/talks",
            headers=headers,
            json={
                "source_url": source_url,
                "script": {
                    "type": "text",
                    "input": text,
                    "provider": provider,
                },
                "config": {
                    "fluent": True,
                    "pad_audio": 0.0,
                    "stitch": True,
                },
            },
        )
        res.raise_for_status()
        talk_id = res.json()["id"]
        logger.info("D-ID talk submitted: %s (provider=%s)", talk_id, provider["type"])
        return talk_id
    except httpx.HTTPStatusError as exc:
        logger.error(
            "[D-ID] create failed: %s %s",
            exc.response.status_code,
            exc.response.text[:500],
        )
        return None


async def generate_talking_head(text: str, voice_id: str | None, source_url: str) -> str | None:
    """
    Submit a D-ID talk request and poll until complete.
    Returns the result video URL, or None if generation fails or is skipped.
    Tries ElevenLabs provider when voice_id is set; falls back to Microsoft on any
    5xx error (D-ID's ElevenLabs integration only supports its own approved voice set).
    """
    if not settings.did_api_key:
        logger.debug("DID_API_KEY not configured — skipping video generation")
        return None

    logger.info("[D-ID] source_url: %s", source_url)
    logger.info("[D-ID] raw source_url repr: %r", source_url)
    logger.info("[D-ID] text length: %d chars", len(text))
    logger.info("[D-ID] voice_id: %s", voice_id)

    headers = {
        "Authorization": f"Basic {settings.did_api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    provider = (
        {"type": "elevenlabs", "voice_id": voice_id}
        if voice_id
        else _MS_PROVIDER
    )
    logger.info("[D-ID] provider: %s", provider)

    async with httpx.AsyncClient(timeout=30.0) as client:
        talk_id = await _create_talk(client, headers, source_url, text, provider)

        # D-ID's ElevenLabs integration only supports a fixed voice set; custom/cloned
        # voices return 500. Retry with Microsoft so the video still renders.
        if talk_id is None and provider["type"] == "elevenlabs":
            logger.warning("[D-ID] ElevenLabs provider failed — retrying with Microsoft")
            logger.info("[D-ID] provider: %s", _MS_PROVIDER)
            talk_id = await _create_talk(client, headers, source_url, text, _MS_PROVIDER)

        if talk_id is None:
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
