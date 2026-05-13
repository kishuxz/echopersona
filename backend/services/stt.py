import httpx
import logging
from config import settings

logger = logging.getLogger(__name__)

DEEPGRAM_URL = "https://api.deepgram.com/v1/listen"


async def transcribe_audio(audio_bytes: bytes, sample_rate: int = 16000) -> str | None:
    """
    Transcribe audio using Deepgram's REST pre-recorded API.
    Returns the transcript string, or None if transcription fails.
    No SDK — direct HTTP call, immune to SDK version changes.
    """
    if settings.mock_mode:
        return "Hello, tell me how this real time avatar pipeline works."

    params = {
        "model": "nova-2",
        "language": "en-US",
        "smart_format": "true",
        "punctuate": "true",
        "encoding": "linear16",
        "sample_rate": sample_rate,
        "channels": 1,
    }
    headers = {
        "Authorization": f"Token {settings.deepgram_api_key}",
        "Content-Type": "audio/raw",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                DEEPGRAM_URL,
                params=params,
                headers=headers,
                content=audio_bytes,
            )
            response.raise_for_status()
            data = response.json()
            transcript = (
                data.get("results", {})
                .get("channels", [{}])[0]
                .get("alternatives", [{}])[0]
                .get("transcript", "")
                .strip()
            )
            logger.info("[STT] transcript: %s", transcript)
            return transcript if transcript else None
    except httpx.HTTPStatusError as e:
        logger.error("[STT] Deepgram HTTP error: %s %s", e.response.status_code, e.response.text)
        return None
    except Exception as e:
        logger.error("[STT] Deepgram error: %s", e)
        return None
