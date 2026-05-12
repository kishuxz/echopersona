import asyncio
import contextlib
from collections.abc import AsyncGenerator

from config import settings


async def stream_stt(audio_queue: asyncio.Queue[bytes | None]) -> AsyncGenerator[dict, None]:
    """
    Consume PCM audio chunks and yield the final transcript.
    Transcript is produced when finish() is called (audio_end received) — ~200ms after mic release.
    endpointing=300 acts as a fast-path fallback if silence is detected during speech.
    """
    if settings.mock_mode:
        chunks = 0
        while True:
            chunk = await audio_queue.get()
            if chunk is None:
                break
            chunks += 1
        await asyncio.sleep(0.08)
        yield {
            "text": "Hello, tell me how this real time avatar pipeline works.",
            "is_final": True,
            "chunks": chunks,
        }
        return

    from deepgram import DeepgramClient, LiveOptions, LiveTranscriptionEvents

    print("[STT] connecting to Deepgram...")
    client = DeepgramClient(settings.deepgram_api_key)
    dg_connection = client.listen.asyncwebsocket.v("1")
    transcript_queue: asyncio.Queue[dict | None] = asyncio.Queue()

    # Gate: prevent duplicate yields if both endpointing and finish() fire a final transcript
    final_sent = False

    async def on_message(_self, result, **_kwargs):
        nonlocal final_sent
        channel = result.channel
        if not channel.alternatives:
            return
        transcript = channel.alternatives[0].transcript
        is_final = bool(result.is_final)
        print(f"[STT] transcript (final={is_final}): {transcript!r}")
        if not transcript or not is_final:
            return
        if not final_sent:
            final_sent = True
            await transcript_queue.put({"text": transcript, "is_final": True})

    async def on_close(_self, close, **_kwargs):
        # Do NOT signal None here — the SDK fires on_close before the final
        # on_message in some versions, so sender() controls the None put after
        # polling final_sent.
        print("[STT] Deepgram connection closed")

    async def on_error(_self, error, **_kwargs):
        print(f"[STT] Deepgram error: {error}")
        await transcript_queue.put(None)

    dg_connection.on(LiveTranscriptionEvents.Transcript, on_message)
    dg_connection.on(LiveTranscriptionEvents.Close, on_close)
    dg_connection.on(LiveTranscriptionEvents.Error, on_error)

    options = LiveOptions(
        model="nova-2",
        language="en-US",
        encoding="linear16",
        sample_rate=16000,
        channels=1,
        endpointing=300,
        interim_results=True,
        utterance_end_ms=1000,
        vad_events=True,
        smart_format=False,
    )
    started = await dg_connection.start(options)
    print(f"[STT] Deepgram started: {started}")

    async def sender() -> None:
        chunks_sent = 0
        while True:
            chunk = await audio_queue.get()
            if chunk is None:
                print(f"[STT] audio_end received, sent {chunks_sent} chunks — calling finish()")
                await dg_connection.finish()
                # on_close fires before on_message in the deepgram-sdk asyncio
                # event queue, so poll here until the final transcript arrives
                # rather than relying on on_close to signal stream end.
                for _ in range(50):   # 50 × 10ms = 500ms max, exits early once received
                    if final_sent:
                        break
                    await asyncio.sleep(0.01)
                if not final_sent:
                    print("[STT] no final transcript received after finish()")
                await transcript_queue.put(None)
                return
            await dg_connection.send(chunk)
            chunks_sent += 1

    sender_task = asyncio.create_task(sender())
    try:
        while True:
            item = await transcript_queue.get()
            if item is None:
                print("[STT] transcript stream ended")
                break
            yield item
    finally:
        sender_task.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await sender_task
        # sender() called finish() on normal exit; only repeat it if the task
        # was cancelled before it could (error / early-exit path).
        if sender_task.cancelled():
            with contextlib.suppress(Exception):
                await asyncio.wait_for(dg_connection.finish(), timeout=1.0)
