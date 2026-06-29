import asyncio
import base64
import contextlib
import hashlib
import json
import logging
import re
import time
from typing import Literal

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from config import settings
from middleware.auth import verify_token
from models.consent import ListenerContext
from models.session import ConversationTurn
from services import audio_store, did, persona_store
from services.db import get_db
from services.listener import resolve_listener_context
from services.latency import LatencyTimer
from services.llm import stream_llm
from services.chunker import extract_complete_sentence, is_sentence_complete
from services.rag import PERSONAS, RAG_INDICES, PersonaRAG, build_system_prompt
from services.ingestion.source_store import get_memory_units_for_persona
from services import stt
from services.tts import stream_tts, tts_audio_chunks
from services.tts_cartesia import stream_tts_cartesia, tts_audio_chunks_cartesia
from models.entitlements import StripeEntitlement
from services.entitlements import can_use_chat, can_use_voice, can_use_video, get_entitlement_for_user

logger = logging.getLogger(__name__)

router = APIRouter()
SESSION_HISTORY: dict[str, list[ConversationTurn]] = {}
SESSION_LISTENER: dict[str, ListenerContext | None] = {}
SESSION_ENTITLEMENT: dict[str, StripeEntitlement | None] = {}
SESSION_MODE: dict[str, Literal["text", "voice", "video"]] = {}

# In-memory response cache: md5(normalized_question) -> (response_text, expires_at)
_RESPONSE_CACHE: dict[str, tuple[str, float]] = {}

# Chunker flush thresholds (chars). First flush is aggressive to minimise ElevenLabs TTFA;
# subsequent chunks use a relaxed cap so TTS sentences are a reasonable length.
_FIRST_FLUSH_CHARS = 25
_SUBSEQUENT_FLUSH_CHARS = 50
_MIN_TTS_CHARS = 15
_TIME_FLUSH_S = 1.5
_CACHE_TTL_S = 60
_MAX_HISTORY_TURNS = 6

_background_tasks: set[asyncio.Task] = set()
_tts_semaphore = asyncio.Semaphore(1)


def _stream_tts(text, websocket, first_audio_cb, voice_id, send_end=False):
    """Route to Cartesia or ElevenLabs based on TTS_PROVIDER setting."""
    if settings.tts_provider == "cartesia":
        return stream_tts_cartesia(text, websocket, first_audio_cb, voice_id, send_end)
    return stream_tts(text, websocket, first_audio_cb, voice_id, send_end)


async def _collect_tts_chunks(text: str, voice_id: str | None) -> list[bytes]:
    """Collect all audio chunks for a sentence (used for prefetch)."""
    async with _tts_semaphore:
        chunks: list[bytes] = []
        try:
            async for chunk in tts_audio_chunks_cartesia(text, voice_id):
                chunks.append(chunk)
        except Exception:
            async for chunk in tts_audio_chunks(text, voice_id):
                chunks.append(chunk)
        return chunks


async def _generate_and_send_video(
    audio_bytes: bytes,
    source_url: str,
    websocket: WebSocket,
) -> None:
    """Background task: save pre-generated audio, submit to D-ID for lip-sync, push video_ready."""
    try:
        filename = await audio_store.save_audio(audio_bytes, extension="mp3")
        audio_url = f"{settings.public_base_url}/audio/{filename}"
        video_url = await did.generate_talking_head(audio_url, source_url)
        if video_url:
            await websocket.send_json({"type": "video_ready", "url": video_url})
        else:
            await websocket.send_json({"type": "video_error", "message": "Video generation failed"})
    except Exception as exc:
        logger.error("[D-ID] video generation failed: %s", exc)
        with contextlib.suppress(Exception):
            await websocket.send_json({"type": "video_error", "message": "Video generation failed"})


def _negotiate_mode(
    requested: str,
    voice_allowed: bool,
    video_allowed: bool,
) -> tuple[Literal["text", "voice", "video"], str | None]:
    """
    Returns (negotiated_mode, reason_or_None).

    Downgrade chain: video -> voice -> text.
    Reasons:
      "voice_not_entitled"       — voice_allowed is False due to tier/quota
      "voice_not_configured"     — voice_id is None on persona (check in caller)
      "video_not_entitled"       — video tier check failed
      "replica_not_configured"   — tavus_replica_id is None on persona
    """
    if requested == "video":
        if not video_allowed:
            # Try voice fallback
            if not voice_allowed:
                return "text", "voice_not_entitled"
            return "voice", "video_not_entitled"
        return "video", None
    if requested == "voice":
        if not voice_allowed:
            return "text", "voice_not_entitled"
        return "voice", None
    # "text" or anything unrecognised
    return "text", None


async def _run_reply_core(
    user_text: str,
    mode: Literal["text", "voice", "video"],
    websocket: WebSocket,
    session_id: str,
    timer: LatencyTimer,
) -> None:
    """
    Shared LLM streaming loop, chunker logic, and latency tracking for all modes.

    mode:
      "text"  — no TTS worker created, no audio_chunk events, audio_end still sent
      "voice" — existing TTS worker path (ElevenLabs or Cartesia)
      "video" — no TTS; Tavus video background task fires after audio_end (audio is embedded in the Tavus video)
    """
    persona_id = websocket.query_params.get("persona_id")
    persona = PERSONAS.get(persona_id or "")

    listener_ctx = SESSION_LISTENER.get(session_id)
    _entitlement = SESSION_ENTITLEMENT.get(session_id)
    _is_owner = listener_ctx is not None and listener_ctx.is_owner
    _turn_answer_count = persona.answer_count if persona else 0
    _turn_voice_id = persona.voice_id if persona else None
    _voice_allowed = can_use_voice(
        _entitlement,
        answer_count=_turn_answer_count,
        voice_id=_turn_voice_id,
    ) and (
        _is_owner or listener_ctx is None or listener_ctx.allowed_modalities.voice_clone
    )
    _video_allowed = can_use_video(_entitlement, answer_count=_turn_answer_count) and (
        _is_owner or listener_ctx is None or listener_ctx.allowed_modalities.video_avatar
    )
    logger.debug(
        "[TTS_GATE] voice_always_on=%s entitlement_present=%s is_owner=%s "
        "listener_voice_clone=%s voice_allowed=%s",
        settings.voice_always_on,
        _entitlement is not None,
        _is_owner,
        listener_ctx.allowed_modalities.voice_clone if listener_ctx else "N/A",
        _voice_allowed,
    )

    # FAISS encode + search is CPU-bound; run in thread executor so it doesn't
    # block the event loop, and gather concurrently with the history fetch.
    loop = asyncio.get_running_loop()

    async def _fetch_history():
        return [turn.model_dump() for turn in SESSION_HISTORY.get(session_id, [])]

    async def _no_rag():
        return []

    _listener_entity = listener_ctx.entity_canonical if listener_ctx else None
    retrieved, history = await asyncio.gather(
        loop.run_in_executor(
            None,
            lambda: RAG_INDICES[persona_id].retrieve(user_text, top_k=3, listener_entity=_listener_entity),
        )
        if persona_id in RAG_INDICES else _no_rag(),
        _fetch_history(),
    )
    system_prompt = build_system_prompt(persona, retrieved, listener_ctx)
    if persona:
        logger.debug("persona=%r | RAG chunks=%d", persona.name, len(retrieved))
    else:
        logger.debug("no persona loaded, using default | persona_id=%r", persona_id)
    logger.debug("RAG retrieved %d chunks", len(retrieved))

    llm_started_at = time.perf_counter()
    first_token_sent = False
    response_text = ""
    voice_id = persona.voice_id if persona else None

    # Check in-memory cache before hitting Groq
    cache_key = hashlib.md5(user_text.lower().strip().encode()).hexdigest()
    _cache_entry = _RESPONSE_CACHE.get(cache_key)
    cache_hit = _cache_entry is not None and time.time() < _cache_entry[1]

    def mark_first_audio() -> None:
        if timer.tts_first_audio_ms == 0:
            timer.tts_first_audio_ms = timer.elapsed_ms()
            logger.info("TTS first audio: %.0fms", timer.tts_first_audio_ms)

    # TTS pipeline:
    # - Sentence 1 is streamed directly to ElevenLabs → websocket as chunks arrive
    #   (preserves fast first-audio; mark_first_audio fires on first ElevenLabs byte)
    # - Sentences 2+ are prefetched concurrently while sentence 1 is streaming,
    #   then sent immediately after sentence 1 finishes — eliminating the 400ms
    #   ElevenLabs round-trip gap between sequential sentences.
    # Raw audio bytes are collected into collected_audio for D-ID lip-sync.
    tts_queue: asyncio.Queue[str | None] = asyncio.Queue()
    tts_error: list[BaseException] = []
    collected_audio: list[bytes] = []

    # Whether TTS is active for this mode.
    # In video mode Tavus embeds its own audio; suppress ElevenLabs/Cartesia
    # so the user does not hear the reply twice.
    _tts_active = mode == "voice"

    async def tts_worker() -> None:
        try:
            first_text = await tts_queue.get()
            if first_text is None:
                return

            # While sentence 1 streams, collect and prefetch subsequent sentences
            prefetch: list[asyncio.Task[list[bytes]]] = []

            async def _collect_pending() -> None:
                while True:
                    text = await tts_queue.get()
                    if text is None:
                        break
                    prefetch.append(asyncio.create_task(_collect_tts_chunks(text, voice_id)))

            collector = asyncio.create_task(_collect_pending())

            # Stream sentence 1 directly — iterate chunks so we can collect raw bytes
            first_audio_sent = False
            if settings.tts_provider == "cartesia":
                chunk_gen = tts_audio_chunks_cartesia(first_text, voice_id)
            else:
                chunk_gen = tts_audio_chunks(first_text, voice_id)
            async for chunk in chunk_gen:
                if not first_audio_sent:
                    first_audio_sent = True
                    mark_first_audio()
                collected_audio.append(chunk)
                await websocket.send_json({"type": "audio_chunk", "data": base64.b64encode(chunk).decode()})
            await websocket.send_json({"type": "sentence_end"})

            # All remaining sentences collected; send pre-fetched audio in order
            await collector
            for task in prefetch:
                audio_bytes = await task
                for chunk in audio_bytes:
                    collected_audio.append(chunk)
                    await websocket.send_json(
                        {"type": "audio_chunk", "data": base64.b64encode(chunk).decode()}
                    )
                await websocket.send_json({"type": "sentence_end"})

        except BaseException as exc:
            tts_error.append(exc)

    if _tts_active:
        tts_task = asyncio.create_task(tts_worker())
    else:
        # text mode: drain the queue via a no-op task
        async def _noop_tts_drain() -> None:
            while True:
                item = await tts_queue.get()
                if item is None:
                    break
        tts_task = asyncio.create_task(_noop_tts_drain())

    # Stream LLM tokens; flush complete sentences to TTS as they arrive.
    # is_sentence_complete() detects end-of-buffer (no trailing space needed),
    # so the first sentence flushes as soon as its final punctuation token arrives.
    sentence_buf = ""
    first_chunk_flushed = False
    first_token_time = 0.0
    time_flush_done = False
    try:
        if cache_hit:
            logger.info("LLM cache hit, skipping API call")
            timer.llm_first_token_ms = 1.0
            cached_text = _cache_entry[0]
            await websocket.send_json({"type": "llm_token", "token": cached_text, "latency_ms": 1.0})
            for sentence in re.split(r'(?<=[.!?])\s+', cached_text):
                s = sentence.strip()
                if len(s) >= _MIN_TTS_CHARS:
                    if _voice_allowed and _tts_active:
                        await tts_queue.put(s)
            response_text = cached_text
        else:
            async for token in stream_llm(user_text, system_prompt, history):
                response_text += token
                sentence_buf += token
                if not first_token_sent:
                    first_token_sent = True
                    first_token_time = time.perf_counter()
                    timer.llm_first_token_ms = (first_token_time - llm_started_at) * 1000
                    logger.info("LLM first token: %.0fms", timer.llm_first_token_ms)
                await websocket.send_json(
                    {
                        "type": "llm_token",
                        "token": token,
                        "latency_ms": round(timer.llm_first_token_ms or timer.elapsed_ms(), 1),
                    }
                )
                # Paragraph break → flush immediately
                if '\n' in token:
                    chunk = sentence_buf.replace('\n', ' ').strip()
                    sentence_buf = ""
                    if len(chunk) >= _MIN_TTS_CHARS:
                        logger.debug("CHUNKER newline flush: %d chars", len(chunk))
                        if _voice_allowed and _tts_active:
                            await tts_queue.put(chunk)
                        first_chunk_flushed = True
                    continue
                # Sentence boundary detected at end of buffer (no trailing space needed)
                if is_sentence_complete(sentence_buf):
                    sentence, sentence_buf = extract_complete_sentence(sentence_buf)
                    if sentence:
                        elapsed_since_first = (time.perf_counter() - first_token_time) * 1000
                        logger.debug(
                            "CHUNKER sentence flush: %d chars, %.0fms after first token",
                            len(sentence), elapsed_since_first,
                        )
                        if _voice_allowed and _tts_active:
                            await tts_queue.put(sentence)
                        first_chunk_flushed = True
                # First-chunk safety: flush at _FIRST_FLUSH_CHARS to minimise ElevenLabs TTFA
                elif not first_chunk_flushed and len(sentence_buf) > _FIRST_FLUSH_CHARS:
                    chunk = sentence_buf.strip()
                    elapsed_since_first = (time.perf_counter() - first_token_time) * 1000
                    logger.debug(
                        "CHUNKER first-chunk safety flush: %d chars, %.0fms after first token",
                        len(chunk), elapsed_since_first,
                    )
                    if _voice_allowed and _tts_active:
                        await tts_queue.put(chunk)
                    sentence_buf = ""
                    first_chunk_flushed = True
                # Subsequent safety: cap at _SUBSEQUENT_FLUSH_CHARS to avoid long unbounded chunks
                elif first_chunk_flushed and len(sentence_buf) > _SUBSEQUENT_FLUSH_CHARS:
                    chunk = sentence_buf.strip()
                    logger.debug("CHUNKER safety flush: %d chars", len(chunk))
                    if _voice_allowed and _tts_active:
                        await tts_queue.put(chunk)
                    sentence_buf = ""
                # Time-based flush: no sentence boundary for _TIME_FLUSH_S → send what we have
                if (not time_flush_done and first_token_sent
                        and time.perf_counter() - first_token_time > _TIME_FLUSH_S
                        and sentence_buf.strip()):
                    logger.debug("CHUNKER time-based flush: %d chars", len(sentence_buf))
                    if _voice_allowed and _tts_active:
                        await tts_queue.put(sentence_buf.strip())
                    sentence_buf = ""
                    time_flush_done = True
            # Store successful response in cache
            if response_text.strip():
                _RESPONSE_CACHE[cache_key] = (response_text.strip(), time.time() + _CACHE_TTL_S)
    except Exception as e:
        logger.error("LLM streaming failed: %s", e)
        await tts_queue.put(None)
        await tts_task
        raise

    # Flush trailing text (last sentence may lack a trailing space)
    if sentence_buf.strip() and _voice_allowed and _tts_active:
        await tts_queue.put(sentence_buf.strip())
    await tts_queue.put(None)
    await tts_task

    if tts_error:
        raise tts_error[0]

    full_reply_text = response_text.strip()

    # Fire D-ID with pre-generated ElevenLabs audio for lip-sync
    if _video_allowed and persona and persona.did_avatar_url and settings.did_api_key and collected_audio:
        all_audio = b"".join(collected_audio)
        _did_task = asyncio.create_task(
            _generate_and_send_video(all_audio, persona.did_avatar_url, websocket)
        )
        _background_tasks.add(_did_task)
        _did_task.add_done_callback(_background_tasks.discard)
        logger.info("[D-ID] video queued (%d audio bytes)", len(all_audio))

    await websocket.send_json({"type": "audio_end"})
    logger.debug("audio_end sent to client")

    # Tavus video tail — async, non-blocking, fires after audio_end
    if mode == "video" and persona and persona.tavus_replica_id:
        from services.tavus import generate_tavus_video

        async def _send_tavus():
            url = await generate_tavus_video(persona.tavus_replica_id, full_reply_text, session_id=session_id)
            if url:
                await websocket.send_json({"type": "video_ready", "url": url})
            else:
                await websocket.send_json({"type": "video_error", "message": "Video generation failed"})

        task = asyncio.create_task(_send_tavus())
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    SESSION_HISTORY.setdefault(session_id, []).extend(
        [
            ConversationTurn(role="user", content=user_text),
            ConversationTurn(role="assistant", content=full_reply_text),
        ]
    )
    SESSION_HISTORY[session_id] = SESSION_HISTORY[session_id][-_MAX_HISTORY_TURNS:]

    summary = timer.summary()
    logger.info(
        "Latency — STT: %sms | LLM first token: %sms | TTS first audio: %sms | Total: %sms",
        summary["stt_ms"], summary["llm_first_token_ms"],
        summary["tts_first_audio_ms"], summary["total_ms"],
    )
    await websocket.send_json({"type": "latency_summary", **summary})


async def _run_turn(
    websocket: WebSocket,
    session_id: str,
    audio_queue: asyncio.Queue[bytes | None],
    release_time_ref: list[float],
) -> None:
    try:
        await _run_turn_inner(websocket, session_id, audio_queue, release_time_ref)
    except Exception as e:
        logger.exception("Turn processing crashed: %s", e)
        with contextlib.suppress(Exception):
            await websocket.send_json({"type": "error", "message": str(e)})
            await websocket.send_json({"type": "audio_end"})


async def _run_turn_inner(
    websocket: WebSocket,
    session_id: str,
    audio_queue: asyncio.Queue[bytes | None],
    release_time_ref: list[float],
) -> None:
    """STT → get user_text → delegate to _run_reply_core."""
    timer = LatencyTimer()

    # Collect all PCM frames from the queue (None signals end)
    pcm_chunks: list[bytes] = []
    while True:
        chunk = await audio_queue.get()
        if chunk is None:
            break
        pcm_chunks.append(chunk)

    audio_bytes = b"".join(pcm_chunks)
    logger.info("[WS] STT audio: %d chunks, %d bytes", len(pcm_chunks), len(audio_bytes))
    user_text = await stt.transcribe_audio(audio_bytes)
    if not user_text:
        logger.warning("STT returned empty transcript, skipping turn")
        with contextlib.suppress(Exception):
            await websocket.send_json({"type": "error", "message": "Could not transcribe audio — please try again."})
            await websocket.send_json({"type": "audio_end"})
        return

    t_release = release_time_ref[0]
    if t_release > 0:
        timer.started_at = t_release  # anchor total_ms to mic-release too
    timer.stt_ms = timer.elapsed_ms()
    logger.info("STT done: %.0fms | %r", timer.stt_ms, user_text)
    await websocket.send_json(
        {
            "type": "transcript",
            "text": user_text,
            "is_final": True,
            "latency_ms": round(timer.stt_ms, 1),
        }
    )

    mode = SESSION_MODE.get(session_id, "voice")
    await _run_reply_core(user_text, mode, websocket, session_id, timer)


async def _run_text_turn(websocket: WebSocket, session_id: str, user_text: str) -> None:
    """Dev-only: run LLM→chunker→TTS pipeline with a pre-supplied transcript.

    Dev bypass caps at voice — never triggers video mode.
    """
    timer = LatencyTimer()
    timer.stt_ms = 0
    try:
        await websocket.send_json({"type": "transcript", "text": user_text, "is_final": True, "latency_ms": 0})

        # Cap at voice for dev bypass: never fire Tavus from a text_turn
        _session_mode = SESSION_MODE.get(session_id, "voice")
        mode: Literal["text", "voice", "video"] = "voice" if _session_mode == "video" else _session_mode

        await _run_reply_core(user_text, mode, websocket, session_id, timer)
    except Exception as e:
        logger.exception("Text turn processing failed: %s", e)
        with contextlib.suppress(Exception):
            await websocket.send_json({"type": "error", "message": str(e)})
            await websocket.send_json({"type": "audio_end"})


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str) -> None:
    token = websocket.query_params.get("token", "")
    persona_id = websocket.query_params.get("persona_id", "")
    requested_mode = websocket.query_params.get("mode", "voice")

    try:
        user_id = await verify_token(token)
    except HTTPException:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    # Validate access: consent gate + owner/beneficiary check
    db = get_db()
    listener_ctx: ListenerContext | None = None
    if persona_id:
        listener_ctx = await resolve_listener_context(db, persona_id, user_id)
        if listener_ctx is None:
            await websocket.close(code=4003, reason="Access denied")
            return
        if persona_id not in PERSONAS:
            persona = await persona_store.get_persona_by_id(persona_id)
            if not persona:
                await websocket.close(code=4004, reason="Persona not found")
                return
            PERSONAS[persona_id] = persona
            if persona_id not in RAG_INDICES:
                loop = asyncio.get_running_loop()
                rag = PersonaRAG()
                units = await get_memory_units_for_persona(persona_id, verified_only=True)
                if not units:
                    units = await get_memory_units_for_persona(persona_id, verified_only=False)
                try:
                    if units:
                        await loop.run_in_executor(None, rag.build_index_from_units, units)
                    else:
                        await loop.run_in_executor(None, rag.build_index, PERSONAS[persona_id].stories)
                except Exception as _rag_err:
                    logger.warning("[WS] RAG index build failed (%s) — continuing without FAISS", _rag_err)
                RAG_INDICES[persona_id] = rag

    # Billing gate: check persona owner's entitlement (or connecting user's for freeform sessions).
    _owner_id = PERSONAS[persona_id].user_id if persona_id else user_id
    entitlement = await get_entitlement_for_user(db, _owner_id)
    _persona_for_gate = PERSONAS.get(persona_id) if persona_id else None
    _gate_answer_count = _persona_for_gate.answer_count if _persona_for_gate else 0
    _is_owner_gate = listener_ctx is None or listener_ctx.is_owner
    if not can_use_chat(entitlement, answer_count=_gate_answer_count, is_owner=_is_owner_gate):
        await websocket.close(code=4002, reason="Subscription required")
        return

    # Readiness gate: block only when status not ready AND no FAISS units AND no legacy stories
    if persona_id:
        _p = PERSONAS.get(persona_id)
        _rag = RAG_INDICES.get(persona_id)
        _has_index = bool(_rag and _rag._units)
        if _p and _p.readiness_status not in ("ready",) and not _has_index and not _p.stories:
            await websocket.close(code=4010, reason="memories_processing")
            return

    # Mode negotiation — before accept
    _neg_persona = PERSONAS.get(persona_id) if persona_id else None
    _neg_answer_count = _neg_persona.answer_count if _neg_persona else 0
    _neg_is_owner = listener_ctx is None or listener_ctx.is_owner
    _neg_voice_allowed = can_use_voice(
        entitlement,
        answer_count=_neg_answer_count,
        voice_id=_neg_persona.voice_id if _neg_persona else None,
    ) and (_neg_is_owner or listener_ctx is None or listener_ctx.allowed_modalities.voice_clone)
    _neg_video_allowed = can_use_video(entitlement, answer_count=_neg_answer_count) and (
        _neg_is_owner or listener_ctx is None or listener_ctx.allowed_modalities.video_avatar
    )
    # Additional precondition checks for voice/video configuration
    if requested_mode in ("voice", "video") and _neg_persona and not _neg_persona.voice_id:
        negotiated: Literal["text", "voice", "video"] = "text"
        negotiation_reason: str | None = "voice_not_configured"
    elif requested_mode == "video" and _neg_persona and not _neg_persona.tavus_replica_id:
        # voice_id is set but replica is missing — downgrade to voice if allowed, else text
        if _neg_voice_allowed:
            negotiated = "voice"
        else:
            negotiated = "text"
        negotiation_reason = "replica_not_configured"
    else:
        negotiated, negotiation_reason = _negotiate_mode(
            requested_mode, _neg_voice_allowed, _neg_video_allowed
        )

    await websocket.accept()
    SESSION_LISTENER[session_id] = listener_ctx
    SESSION_ENTITLEMENT[session_id] = entitlement
    SESSION_MODE[session_id] = negotiated

    _mode_negotiated_msg: dict = {"type": "mode_negotiated", "mode": negotiated, "requested": requested_mode}
    if negotiation_reason:
        _mode_negotiated_msg["reason"] = negotiation_reason
    await websocket.send_json(_mode_negotiated_msg)

    logger.info("Connection opened: session=%s mode=%s", session_id, negotiated)
    audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
    release_time_ref: list[float] = [0.0]
    turn_task: asyncio.Task | None = None  # created lazily on first audio frame

    try:
        while True:
            data = await websocket.receive()

            # Client closed — exit cleanly without calling receive() again
            if data.get("type") == "websocket.disconnect":
                break

            # Binary frame — raw Int16 PCM audio, forward directly to STT queue
            raw = data.get("bytes")
            if raw:
                logger.info("[WS] received binary chunk: %d bytes", len(raw))
                if turn_task is None or turn_task.done():
                    turn_task = asyncio.create_task(
                        _run_turn(websocket, session_id, audio_queue, release_time_ref)
                    )
                await audio_queue.put(raw)
                continue

            # Text frame — JSON control message
            text = data.get("text")
            if not text:
                continue
            message = json.loads(text)
            msg_type = message.get("type")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
            elif msg_type == "text_turn":
                # Dev bypass: inject text directly, skip STT
                user_text = message.get("text", "").strip()
                if user_text:
                    await _run_text_turn(websocket, session_id, user_text)
            elif msg_type == "audio_end":
                logger.debug("audio_end received")
                release_time_ref[0] = time.perf_counter()  # start timer at mic release
                await audio_queue.put(None)
                if turn_task:
                    await turn_task
                audio_queue = asyncio.Queue()
                release_time_ref = [0.0]
                turn_task = None  # next _run_turn created lazily on first audio frame
            elif msg_type == "simli_session_request":
                _l = SESSION_LISTENER.get(session_id)
                _ent = SESSION_ENTITLEMENT.get(session_id)
                _simli_pid = websocket.query_params.get("persona_id", "")
                _simli_persona = PERSONAS.get(_simli_pid)
                _simli_ac = _simli_persona.answer_count if _simli_persona else 0
                if (_l is not None and not _l.allowed_modalities.video_avatar) or not can_use_video(_ent, answer_count=_simli_ac):
                    await websocket.send_json({"type": "simli_session_error", "message": "Video not permitted"})
                else:
                    if _simli_persona and _simli_persona.simli_face_id:
                        from services import simli as simli_svc
                        simli_token = await simli_svc.create_session(_simli_persona.simli_face_id)
                        if simli_token:
                            await websocket.send_json({"type": "simli_session_token", "token": simli_token})
                        else:
                            await websocket.send_json({"type": "simli_session_error", "message": "Simli session creation failed"})
                    else:
                        await websocket.send_json({"type": "simli_session_error", "message": "No Simli face configured for this persona"})
            else:
                await websocket.send_json({"type": "error", "message": f"Unknown message type: {msg_type}"})
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.exception("Unexpected WebSocket error: %s", exc)
        with contextlib.suppress(Exception):
            await websocket.send_json({"type": "error", "message": str(exc)})
    finally:
        if turn_task:
            turn_task.cancel()
        for _bg_task in list(_background_tasks):
            _bg_task.cancel()
        SESSION_ENTITLEMENT.pop(session_id, None)
        SESSION_LISTENER.pop(session_id, None)
        SESSION_MODE.pop(session_id, None)
        SESSION_HISTORY.pop(session_id, None)
