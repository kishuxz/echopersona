"""
Temporary audio file store for D-ID lip-sync.
Saves assembled TTS audio to /tmp/echopersona_audio/ with a UUID filename.
Files are auto-deleted after 5 minutes (D-ID fetches within seconds).
"""
import asyncio
import logging
import uuid
from pathlib import Path

logger = logging.getLogger(__name__)

AUDIO_DIR = Path("/tmp/echopersona_audio")
AUDIO_DIR.mkdir(exist_ok=True)
AUDIO_TTL_SECONDS = 300  # 5 minutes


async def save_audio(audio_bytes: bytes, extension: str = "mp3") -> str:
    """
    Save audio bytes to a temp file.
    Returns the filename (not full path) — used to construct public URL.
    """
    filename = f"{uuid.uuid4().hex}.{extension}"
    filepath = AUDIO_DIR / filename
    filepath.write_bytes(audio_bytes)
    asyncio.create_task(_delete_after(filepath, AUDIO_TTL_SECONDS))
    logger.info("[AUDIO_STORE] saved %s (%d bytes)", filename, len(audio_bytes))
    return filename


async def _delete_after(filepath: Path, delay: float) -> None:
    await asyncio.sleep(delay)
    try:
        filepath.unlink(missing_ok=True)
        logger.debug("[AUDIO_STORE] deleted %s", filepath.name)
    except Exception as e:
        logger.warning("[AUDIO_STORE] failed to delete %s: %s", filepath.name, e)
