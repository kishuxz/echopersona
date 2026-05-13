import httpx
import logging
import struct
from config import settings

logger = logging.getLogger(__name__)

DEEPGRAM_URL = "https://api.deepgram.com/v1/listen"


def _pcm_to_wav(pcm_bytes: bytes, sample_rate: int = 16000) -> bytes:
    """Wrap raw Int16 LE PCM bytes in a minimal WAV container."""
    channels = 1
    bits = 16
    data_size = len(pcm_bytes)
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + data_size, b"WAVE",
        b"fmt ", 16, 1, channels, sample_rate,
        sample_rate * channels * bits // 8,
        channels * bits // 8, bits,
        b"data", data_size,
    )
    return header + pcm_bytes


async def transcribe_audio(audio_bytes: bytes, sample_rate: int = 16000) -> str | None:
    """
    Transcribe audio using Deepgram's REST pre-recorded API.
    Returns the transcript string, or None if transcription fails.
    No SDK — direct HTTP call, immune to SDK version changes.
    PCM bytes are wrapped in a WAV container so Deepgram can parse the
    format without relying on query-param encoding hints.
    """
    if settings.mock_mode:
        return "Hello, tell me how this real time avatar pipeline works."

    if len(audio_bytes) < 3200:  # less than 100ms at 16 kHz mono int16
        logger.warning("[STT] audio too short (%d bytes) — skipping", len(audio_bytes))
        return None

    wav_bytes = _pcm_to_wav(audio_bytes, sample_rate)

    params = {
        "model": "nova-2",
        "language": "en-US",
        "smart_format": "true",
        "punctuate": "true",
    }
    headers = {
        "Authorization": f"Token {settings.deepgram_api_key}",
        "Content-Type": "audio/wav",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                DEEPGRAM_URL,
                params=params,
                headers=headers,
                content=wav_bytes,
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
