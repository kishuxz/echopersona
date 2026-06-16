import httpx
import logging
import struct
from config import settings

logger = logging.getLogger(__name__)


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
    if settings.mock_mode:
        return "Hello, tell me how this real time avatar pipeline works."

    if len(audio_bytes) < 3200:  # less than 100ms at 16 kHz mono int16
        logger.warning("[STT] audio too short (%d bytes) — skipping", len(audio_bytes))
        return None

    wav_bytes = _pcm_to_wav(audio_bytes, sample_rate)

    # Try Groq Whisper first (faster — same API connection already used for LLM)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                "https://api.groq.com/openai/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                files={"file": ("audio.wav", wav_bytes, "audio/wav")},
                data={"model": "whisper-large-v3-turbo", "language": "en", "response_format": "text"},
            )
            response.raise_for_status()
            transcript = response.text.strip()
            logger.info("[STT] Groq Whisper transcript: %s", transcript)
            return transcript if transcript else None
    except Exception as e:
        logger.error("[STT] Groq Whisper failed: %s", e)
        return None
