import asyncio
import base64
import json
import logging
import mimetypes
import time
from collections.abc import AsyncGenerator

from config import settings

logger = logging.getLogger(__name__)

_EL_WS_URL = (
    "wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    "/stream-input"
    "?model_id=eleven_turbo_v2_5"
    "&output_format=mp3_22050_32"
    "&optimize_streaming_latency=4"
)
_EL_VOICE_SETTINGS = {
    "stability": 0.5,
    "similarity_boost": 0.75,
    "style": 0.0,
    "use_speaker_boost": True,
}


async def prewarm_elevenlabs_ws(voice_id: str | None = None):
    """
    Open an ElevenLabs input-streaming WebSocket and send the BOS space token
    so their server initialises the model while LLM is still streaming.
    Returns the open WS; caller owns it and must close it.
    Meant to be fire-and-forget via asyncio.create_task() on first LLM token.
    """
    import websockets

    t0 = time.perf_counter()
    vid = voice_id or settings.elevenlabs_voice_id
    url = _EL_WS_URL.format(voice_id=vid)
    el_ws = await websockets.connect(
        url,
        additional_headers={"xi-api-key": settings.elevenlabs_api_key},
    )
    # BOS: prime model initialisation on ElevenLabs side
    await el_ws.send(json.dumps({
        "text": " ",
        "try_trigger_generation": True,
        "voice_settings": _EL_VOICE_SETTINGS,
        "generation_config": {"chunk_length_schedule": [50]},
    }))
    ms = (time.perf_counter() - t0) * 1000
    logger.debug("ElevenLabs WS prewarm complete: %.0fms", ms)
    return el_ws


async def _tts_audio_chunks_prewarmed(el_ws, text: str) -> AsyncGenerator[bytes, None]:
    """Yield audio from a pre-opened ElevenLabs WS (BOS already sent)."""
    await el_ws.send(json.dumps({
        "text": text + " ",
        "try_trigger_generation": True,
    }))
    await el_ws.send(json.dumps({"text": ""}))

    async for raw in el_ws:
        data = json.loads(raw)
        if data.get("audio"):
            yield base64.b64decode(data["audio"])
        if data.get("isFinal"):
            break

    try:
        await el_ws.close()
    except Exception:
        pass


async def stream_tts_prewarmed(
    el_ws,
    text: str,
    websocket,
    first_audio_cb=None,
    send_end: bool = False,
) -> None:
    """Stream audio from pre-warmed ElevenLabs WS to the client WebSocket."""
    first_audio_sent = False
    async for chunk in _tts_audio_chunks_prewarmed(el_ws, text):
        if not first_audio_sent:
            first_audio_sent = True
            if first_audio_cb:
                first_audio_cb()
        await websocket.send_json({"type": "audio_chunk", "data": base64.b64encode(chunk).decode()})
    if send_end:
        await websocket.send_json({"type": "audio_end"})
        logger.debug("audio_end sent to client")


async def _mock_audio_chunks(text: str) -> AsyncGenerator[bytes, None]:
    for index in range(3):
        await asyncio.sleep(0.01)
        yield f"mock-mp3-chunk-{index}:{text[:20]}".encode()


async def tts_audio_chunks(text: str, voice_id: str | None = None) -> AsyncGenerator[bytes, None]:
    if not voice_id:
        raise ValueError("voice_id is required — stock voice fallback is disabled")
    if settings.mock_mode:
        async for chunk in _mock_audio_chunks(text):
            yield chunk
        return

    from elevenlabs.client import AsyncElevenLabs
    from elevenlabs import VoiceSettings

    client = AsyncElevenLabs(api_key=settings.elevenlabs_api_key)
    _total_bytes = 0
    try:
        async for chunk in client.text_to_speech.convert_as_stream(
            voice_id=voice_id,
            text=text,
            model_id="eleven_turbo_v2_5",
            output_format="mp3_22050_32",
            optimize_streaming_latency=4,
            voice_settings=VoiceSettings(
                stability=0.5,
                similarity_boost=0.75,
                style=0.0,
                use_speaker_boost=True,
            ),
        ):
            if chunk:
                _total_bytes += len(chunk)
                yield chunk
    except Exception as e:
        logger.error("TTS stream error: %s", e)
        raise
    finally:
        logger.debug("TTS total_audio_bytes=%d", _total_bytes)


async def stream_tts(text: str, websocket, first_audio_cb=None, voice_id: str | None = None, send_end: bool = False) -> None:
    first_audio_sent = False
    async for chunk in tts_audio_chunks(text, voice_id):
        if not first_audio_sent:
            first_audio_sent = True
            if first_audio_cb:
                first_audio_cb()
        await websocket.send_json(
            {
                "type": "audio_chunk",
                "data": base64.b64encode(chunk).decode(),
            }
        )
    if send_end:
        await websocket.send_json({"type": "audio_end"})
        logger.debug("audio_end sent to client")


async def clone_voice(persona_id: str, audio_files) -> str:
    if settings.mock_mode:
        return f"mock_voice_{persona_id}"

    from elevenlabs.client import AsyncElevenLabs
    from elevenlabs.core.api_error import ApiError

    client = AsyncElevenLabs(api_key=settings.elevenlabs_api_key)
    file_tuples = []
    for f in audio_files:
        audio_bytes = await f.read()
        content_type = f.content_type or "audio/mpeg"
        if content_type == "application/octet-stream":
            guessed, _ = mimetypes.guess_type(f.filename or "audio.mp3")
            content_type = guessed or "audio/mpeg"
        filename = f.filename or "sample.mp3"
        logger.info(
            "[VOICE] cloning file: name=%s size=%d content_type=%s",
            filename, len(audio_bytes), content_type,
        )
        file_tuples.append((filename, audio_bytes, content_type))

    try:
        voice = await client.voices.add(
            name=f"EchoPersona_{persona_id[:8]}",
            files=file_tuples,
            description="Cloned voice for EchoPersona",
        )
        return voice.voice_id
    except ApiError as e:
        body = e.body or {}
        detail = body.get("detail", {}) if isinstance(body, dict) else {}
        code = detail.get("code", "") if isinstance(detail, dict) else ""
        logger.error("[VOICE] ElevenLabs IVC error (code=%s): %s", code, detail)
        raise RuntimeError(f"Voice cloning failed: {code or detail}")
