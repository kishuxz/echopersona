import base64
import logging
from collections.abc import AsyncGenerator

from config import settings

logger = logging.getLogger(__name__)

async def tts_audio_chunks_cartesia(
    text: str,
    voice_id: str | None = None,
) -> AsyncGenerator[bytes, None]:
    """
    Stream audio from Cartesia's SSE TTS API.
    Uses sonic-2 (Cartesia's fastest model, ~80-120ms TTFA floor).
    Requires CARTESIA_API_KEY in .env.
    """
    from cartesia import AsyncCartesia
    from cartesia.types.sse_events import ChunkEvent

    if not voice_id:
        raise ValueError("voice_id is required — stock voice fallback is disabled")
    client = AsyncCartesia(api_key=settings.cartesia_api_key)
    vid = voice_id

    stream = await client.tts.sse(
        model_id="sonic-2",
        transcript=text,
        voice={"mode": "id", "id": vid},
        output_format={
            "container": "raw",
            "encoding": "pcm_f32le",
            "sample_rate": 22050,
        },
    )

    async for event in stream:
        if isinstance(event, ChunkEvent) and event.audio:
            yield event.audio


async def stream_tts_cartesia(
    text: str,
    websocket,
    first_audio_cb=None,
    voice_id: str | None = None,
    send_end: bool = False,
) -> None:
    first_audio_sent = False
    async for chunk in tts_audio_chunks_cartesia(text, voice_id):
        if not first_audio_sent:
            first_audio_sent = True
            if first_audio_cb:
                first_audio_cb()
        await websocket.send_json(
            {"type": "audio_chunk", "data": base64.b64encode(chunk).decode()}
        )
    if send_end:
        await websocket.send_json({"type": "audio_end"})
        logger.debug("audio_end sent to client")
