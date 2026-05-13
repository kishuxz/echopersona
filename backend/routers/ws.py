import asyncio
import base64
import contextlib
import hashlib
import json
import logging
import re
import time

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from config import settings
from middleware.auth import verify_token
from models.session import ConversationTurn
from services import did, persona_store
from services.latency import LatencyTimer
from services.llm import stream_llm
from services.chunker import extract_complete_sentence, is_sentence_complete
from services.rag import PERSONAS, RAG_INDICES, PersonaRAG, build_system_prompt
from services import stt
from services.tts import stream_tts, tts_audio_chunks
from services.tts_cartesia import stream_tts_cartesia, tts_audio_chunks_cartesia

logger = logging.getLogger(__name__)

router = APIRouter()
SESSION_HISTORY: dict[str, list[ConversationTurn]] = {}

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


def _stream_tts(text, websocket, first_audio_cb, voice_id, send_end=False):
    """Route to Cartesia or ElevenLabs based on TTS_PROVIDER setting."""
    if settings.tts_provider == "cartesia":
        return stream_tts_cartesia(text, websocket, first_audio_cb, voice_id, send_end)
    return stream_tts(text, websocket, first_audio_cb, voice_id, send_end)


async def _collect_tts_chunks(text: str, voice_id: str | None) -> list[bytes]:
    """Collect all audio chunks for a sentence (used for prefetch)."""
    chunks: list[bytes] = []
    if settings.tts_provider == "cartesia":
        async for chunk in tts_audio_chunks_cartesia(text, voice_id):
            chunks.append(chunk)
    else:
        async for chunk in tts_audio_chunks(text, voice_id):
            chunks.append(chunk)
    return chunks


async def _generate_and_send_video(
    websocket: WebSocket,
    response_text: str,
    voice_id: str | None,
    source_url: str,
) -> None:
    """Background task: generate D-ID talking-head video from text, push video_ready to client."""
    try:
        video_url = await did.generate_talking_head(response_text, voice_id, source_url)
        if video_url:
            await websocket.send_json({"type": "video_ready", "url": video_url})
    except Exception as exc:
        logger.error("D-ID video generation failed: %s", exc)


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
    timer = LatencyTimer()

    # Collect all PCM frames from the queue (None signals end)
    pcm_chunks: list[bytes] = []
    while True:
        chunk = await audio_queue.get()
        if chunk is None:
            break
        pcm_chunks.append(chunk)

    user_text = await stt.transcribe_audio(b"".join(pcm_chunks))
    if not user_text:
        logger.warning("STT returned empty transcript, skipping turn")
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

    persona_id = websocket.query_params.get("persona_id")
    persona = PERSONAS.get(persona_id or "")

    # FAISS encode + search is CPU-bound; run in thread executor so it doesn't
    # block the event loop, and gather concurrently with the history fetch.
    loop = asyncio.get_running_loop()

    async def _fetch_history():
        return [turn.model_dump() for turn in SESSION_HISTORY.get(session_id, [])]

    async def _no_rag():
        return []

    retrieved, history = await asyncio.gather(
        loop.run_in_executor(None, lambda: RAG_INDICES[persona_id].retrieve(user_text, top_k=3))
        if persona_id in RAG_INDICES else _no_rag(),
        _fetch_history(),
    )
    system_prompt = build_system_prompt(persona, retrieved)
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
    tts_queue: asyncio.Queue[str | None] = asyncio.Queue()
    tts_error: list[BaseException] = []

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

            # Stream sentence 1 directly — fires mark_first_audio on first TTS byte
            await _stream_tts(first_text, websocket, mark_first_audio, voice_id, send_end=False)
            await websocket.send_json({"type": "sentence_end"})

            # All remaining sentences collected; send pre-fetched audio in order
            await collector
            for task in prefetch:
                audio_bytes = await task
                for chunk in audio_bytes:
                    await websocket.send_json(
                        {"type": "audio_chunk", "data": base64.b64encode(chunk).decode()}
                    )
                await websocket.send_json({"type": "sentence_end"})

        except BaseException as exc:
            tts_error.append(exc)

    tts_task = asyncio.create_task(tts_worker())

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
                    await tts_queue.put(s)
            response_text = cached_text
            if persona and persona.did_avatar_url and settings.did_api_key and cached_text.strip():
                _did_task = asyncio.create_task(
                    _generate_and_send_video(
                        websocket=websocket,
                        response_text=cached_text.strip(),
                        voice_id=voice_id,
                        source_url=persona.did_avatar_url,
                    )
                )
                _background_tasks.add(_did_task)
                _did_task.add_done_callback(_background_tasks.discard)
                logger.info("D-ID video queued for cached response (%d chars)", len(cached_text.strip()))
        else:
            # Latency floor: ~620-640ms warm on Groq free tier due to network RTT.
            # To break 600ms: set USE_VLLM=true in .env (local vLLM, 5-30ms TTFT).
            # Architecture is correct — bottleneck is API network, not code.
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
                    await tts_queue.put(chunk)
                    sentence_buf = ""
                    first_chunk_flushed = True
                # Subsequent safety: cap at _SUBSEQUENT_FLUSH_CHARS to avoid long unbounded chunks
                elif first_chunk_flushed and len(sentence_buf) > _SUBSEQUENT_FLUSH_CHARS:
                    chunk = sentence_buf.strip()
                    logger.debug("CHUNKER safety flush: %d chars", len(chunk))
                    await tts_queue.put(chunk)
                    sentence_buf = ""
                # Time-based flush: no sentence boundary for _TIME_FLUSH_S → send what we have
                if (not time_flush_done and first_token_sent
                        and time.perf_counter() - first_token_time > _TIME_FLUSH_S
                        and sentence_buf.strip()):
                    logger.debug("CHUNKER time-based flush: %d chars", len(sentence_buf))
                    await tts_queue.put(sentence_buf.strip())
                    sentence_buf = ""
                    time_flush_done = True
            # Store successful response in cache
            if response_text.strip():
                _RESPONSE_CACHE[cache_key] = (response_text.strip(), time.time() + _CACHE_TTL_S)
            # Fire D-ID with the complete response once LLM finishes
            if persona and persona.did_avatar_url and settings.did_api_key and response_text.strip():
                _did_task = asyncio.create_task(
                    _generate_and_send_video(
                        websocket=websocket,
                        response_text=response_text.strip(),
                        voice_id=voice_id,
                        source_url=persona.did_avatar_url,
                    )
                )
                _background_tasks.add(_did_task)
                _did_task.add_done_callback(_background_tasks.discard)
                logger.info("D-ID video queued for response (%d chars)", len(response_text.strip()))
    except Exception as e:
        logger.error("LLM streaming failed: %s", e)
        await tts_queue.put(None)
        await tts_task
        raise

    # Flush trailing text (last sentence may lack a trailing space)
    if sentence_buf.strip():
        await tts_queue.put(sentence_buf.strip())
    await tts_queue.put(None)
    await tts_task

    if tts_error:
        raise tts_error[0]

    await websocket.send_json({"type": "audio_end"})
    logger.debug("audio_end sent to client")

    SESSION_HISTORY.setdefault(session_id, []).extend(
        [
            ConversationTurn(role="user", content=user_text),
            ConversationTurn(role="assistant", content=response_text.strip()),
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


async def _run_text_turn(websocket: WebSocket, session_id: str, user_text: str) -> None:
    """Dev-only: run LLM→chunker→TTS pipeline with a pre-supplied transcript."""
    timer = LatencyTimer()
    try:
        persona_id = websocket.query_params.get("persona_id")
        persona = PERSONAS.get(persona_id or "")

        loop = asyncio.get_running_loop()

        async def _fetch_history():
            return [turn.model_dump() for turn in SESSION_HISTORY.get(session_id, [])]

        async def _no_rag():
            return []

        retrieved, history = await asyncio.gather(
            loop.run_in_executor(None, lambda: RAG_INDICES[persona_id].retrieve(user_text, top_k=3))
            if persona_id in RAG_INDICES else _no_rag(),
            _fetch_history(),
        )
        system_prompt = build_system_prompt(persona, retrieved)
        logger.debug("RAG retrieved %d chunks", len(retrieved))
        voice_id = persona.voice_id if persona else None

        await websocket.send_json({"type": "transcript", "text": user_text, "is_final": True, "latency_ms": 0})
        timer.stt_ms = 0

        def mark_first_audio() -> None:
            if timer.tts_first_audio_ms == 0:
                timer.tts_first_audio_ms = timer.elapsed_ms()
                logger.info("TTS first audio: %.0fms", timer.tts_first_audio_ms)

        tts_queue: asyncio.Queue[str | None] = asyncio.Queue()
        tts_error: list[BaseException] = []

        async def tts_worker() -> None:
            try:
                first_text = await tts_queue.get()
                if first_text is None:
                    return
                prefetch: list[asyncio.Task[list[bytes]]] = []

                async def _collect_pending() -> None:
                    while True:
                        text = await tts_queue.get()
                        if text is None:
                            break
                        prefetch.append(asyncio.create_task(_collect_tts_chunks(text, voice_id)))

                collector = asyncio.create_task(_collect_pending())
                await _stream_tts(first_text, websocket, mark_first_audio, voice_id, send_end=False)
                await websocket.send_json({"type": "sentence_end"})
                await collector
                for task in prefetch:
                    audio_bytes = await task
                    for chunk in audio_bytes:
                        await websocket.send_json(
                            {"type": "audio_chunk", "data": base64.b64encode(chunk).decode()}
                        )
                    await websocket.send_json({"type": "sentence_end"})
            except BaseException as exc:
                tts_error.append(exc)

        tts_task = asyncio.create_task(tts_worker())
        sentence_buf = ""
        first_chunk_flushed = False
        first_token_time = 0.0
        time_flush_done = False
        llm_started_at = time.perf_counter()
        first_token_sent = False
        response_text = ""

        cache_key = hashlib.md5(user_text.lower().strip().encode()).hexdigest()
        _cache_entry = _RESPONSE_CACHE.get(cache_key)
        cache_hit = _cache_entry is not None and time.time() < _cache_entry[1]

        try:
            if cache_hit:
                logger.info("LLM cache hit, skipping API call")
                timer.llm_first_token_ms = 1.0
                cached_text = _cache_entry[0]
                await websocket.send_json({"type": "llm_token", "token": cached_text, "latency_ms": 1.0})
                for sentence in re.split(r'(?<=[.!?])\s+', cached_text):
                    s = sentence.strip()
                    if len(s) >= _MIN_TTS_CHARS:
                        await tts_queue.put(s)
                response_text = cached_text
                if persona and persona.did_avatar_url and settings.did_api_key and cached_text.strip():
                    _did_task = asyncio.create_task(
                        _generate_and_send_video(
                            websocket=websocket,
                            response_text=cached_text.strip(),
                            voice_id=voice_id,
                            source_url=persona.did_avatar_url,
                        )
                    )
                    _background_tasks.add(_did_task)
                    _did_task.add_done_callback(_background_tasks.discard)
                    logger.info("D-ID video queued for cached response (%d chars)", len(cached_text.strip()))
            else:
                async for token in stream_llm(user_text, system_prompt, history):
                    response_text += token
                    sentence_buf += token
                    if not first_token_sent:
                        first_token_sent = True
                        first_token_time = time.perf_counter()
                        timer.llm_first_token_ms = (first_token_time - llm_started_at) * 1000
                        logger.info("LLM first token: %.0fms", timer.llm_first_token_ms)
                    await websocket.send_json({"type": "llm_token", "token": token, "latency_ms": round(timer.llm_first_token_ms or timer.elapsed_ms(), 1)})
                    if '\n' in token:
                        chunk = sentence_buf.replace('\n', ' ').strip()
                        sentence_buf = ""
                        if len(chunk) >= _MIN_TTS_CHARS:
                            logger.debug("CHUNKER newline flush: %d chars", len(chunk))
                            await tts_queue.put(chunk)
                            first_chunk_flushed = True
                        continue
                    if is_sentence_complete(sentence_buf):
                        sentence, sentence_buf = extract_complete_sentence(sentence_buf)
                        if sentence:
                            logger.debug("CHUNKER sentence flush: %d chars", len(sentence))
                            await tts_queue.put(sentence)
                            first_chunk_flushed = True
                    elif not first_chunk_flushed and len(sentence_buf) > _FIRST_FLUSH_CHARS:
                        chunk = sentence_buf.strip()
                        logger.debug("CHUNKER first-chunk safety flush: %d chars", len(chunk))
                        await tts_queue.put(chunk)
                        sentence_buf = ""
                        first_chunk_flushed = True
                    elif first_chunk_flushed and len(sentence_buf) > _SUBSEQUENT_FLUSH_CHARS:
                        chunk = sentence_buf.strip()
                        logger.debug("CHUNKER safety flush: %d chars", len(chunk))
                        await tts_queue.put(chunk)
                        sentence_buf = ""
                    if (not time_flush_done and first_token_sent
                            and time.perf_counter() - first_token_time > _TIME_FLUSH_S
                            and sentence_buf.strip()):
                        logger.debug("CHUNKER time-based flush: %d chars", len(sentence_buf))
                        await tts_queue.put(sentence_buf.strip())
                        sentence_buf = ""
                        time_flush_done = True
                if response_text.strip():
                    _RESPONSE_CACHE[cache_key] = (response_text.strip(), time.time() + _CACHE_TTL_S)
                if persona and persona.did_avatar_url and settings.did_api_key and response_text.strip():
                    _did_task = asyncio.create_task(
                        _generate_and_send_video(
                            websocket=websocket,
                            response_text=response_text.strip(),
                            voice_id=voice_id,
                            source_url=persona.did_avatar_url,
                        )
                    )
                    _background_tasks.add(_did_task)
                    _did_task.add_done_callback(_background_tasks.discard)
                    logger.info("D-ID video queued for response (%d chars)", len(response_text.strip()))
        except Exception as e:
            logger.error("LLM streaming failed: %s", e)
            await tts_queue.put(None)
            await tts_task
            raise

        if sentence_buf.strip():
            await tts_queue.put(sentence_buf.strip())
        await tts_queue.put(None)
        await tts_task

        if tts_error:
            raise tts_error[0]

        await websocket.send_json({"type": "audio_end"})

        SESSION_HISTORY.setdefault(session_id, []).extend([
            ConversationTurn(role="user", content=user_text),
            ConversationTurn(role="assistant", content=response_text.strip()),
        ])
        SESSION_HISTORY[session_id] = SESSION_HISTORY[session_id][-_MAX_HISTORY_TURNS:]
        summary = timer.summary()
        logger.info(
            "Latency — STT: %sms | LLM first token: %sms | TTS first audio: %sms | Total: %sms",
            summary["stt_ms"], summary["llm_first_token_ms"],
            summary["tts_first_audio_ms"], summary["total_ms"],
        )
        await websocket.send_json({"type": "latency_summary", **summary})
    except Exception as e:
        logger.exception("Text turn processing failed: %s", e)
        with contextlib.suppress(Exception):
            await websocket.send_json({"type": "error", "message": str(e)})
            await websocket.send_json({"type": "audio_end"})


@router.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str) -> None:
    token = websocket.query_params.get("token", "")
    persona_id = websocket.query_params.get("persona_id", "")

    try:
        user_id = await verify_token(token)
    except HTTPException:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    # Load persona from DB if not already in-memory, verify ownership
    if persona_id:
        if persona_id in PERSONAS:
            if PERSONAS[persona_id].user_id != user_id:
                await websocket.close(code=4003, reason="Forbidden")
                return
        else:
            persona = await persona_store.get_persona(persona_id, user_id)
            if not persona:
                await websocket.close(code=4004, reason="Persona not found")
                return
            PERSONAS[persona_id] = persona
            if persona_id not in RAG_INDICES:
                loop = asyncio.get_running_loop()
                rag = PersonaRAG()
                await loop.run_in_executor(None, rag.build_index, persona.stories)
                RAG_INDICES[persona_id] = rag

    await websocket.accept()
    logger.info("Connection opened: session=%s", session_id)
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
                logger.debug("Binary frame: %d bytes", len(raw))
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
                pid = websocket.query_params.get("persona_id", "")
                p = PERSONAS.get(pid)
                if p and p.simli_face_id:
                    from services import simli as simli_svc
                    simli_token = await simli_svc.create_session(p.simli_face_id)
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
