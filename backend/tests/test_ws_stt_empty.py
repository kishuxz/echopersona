"""Tests for Slice D — WebSocket STT empty/None unblock.

When STT returns None (e.g. stale API key, too-short audio, silent recording),
the backend must:
  - send {"type": "error", ...} so VoiceInterface clears isProcessing and shows a banner
  - send {"type": "audio_end"} so VoiceInterface resets stage to idle
  - NOT call the LLM
  - NOT call TTS
  - keep the WebSocket open for the next turn
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from routers.ws import _run_turn


def _make_ws() -> MagicMock:
    ws = MagicMock()
    ws.query_params = {"persona_id": ""}
    ws.send_json = AsyncMock()
    return ws


def _sent_types(ws: MagicMock) -> list[str]:
    return [c.args[0]["type"] for c in ws.send_json.call_args_list if c.args]


class TestSTTEmptyUnblock:

    def _run(self, stt_return_value) -> MagicMock:
        """Run one turn with STT returning the given value; return the mock WebSocket."""
        ws = _make_ws()
        session_id = "sess-stt-empty"

        async def go():
            queue: asyncio.Queue[bytes | None] = asyncio.Queue()
            await queue.put(b"\x00" * 3200)  # 100ms of silence
            await queue.put(None)
            release_ref = [0.0]
            with patch("routers.ws.stt.transcribe_audio", AsyncMock(return_value=stt_return_value)):
                await _run_turn(ws, session_id, queue, release_ref)

        asyncio.run(go())
        return ws

    def test_stt_none_sends_error_event(self):
        ws = self._run(None)
        types = _sent_types(ws)
        assert "error" in types, f"expected error event, got: {types}"

    def test_stt_none_sends_audio_end_event(self):
        ws = self._run(None)
        types = _sent_types(ws)
        assert "audio_end" in types, f"expected audio_end event, got: {types}"

    def test_stt_empty_string_sends_error_and_audio_end(self):
        ws = self._run("")
        types = _sent_types(ws)
        assert "error" in types
        assert "audio_end" in types

    def test_stt_none_error_message_is_user_readable(self):
        ws = self._run(None)
        error_calls = [
            c.args[0] for c in ws.send_json.call_args_list
            if c.args and c.args[0].get("type") == "error"
        ]
        assert error_calls, "no error event found"
        assert "transcribe" in error_calls[0]["message"].lower() or "again" in error_calls[0]["message"].lower()

    def test_stt_none_error_before_audio_end(self):
        """error must arrive before audio_end so UI can show the banner before clearing state."""
        ws = self._run(None)
        types = _sent_types(ws)
        assert types.index("error") < types.index("audio_end")

    def test_stt_none_no_llm_call(self):
        ws = _make_ws()

        async def go():
            queue: asyncio.Queue[bytes | None] = asyncio.Queue()
            await queue.put(b"\x00" * 3200)
            await queue.put(None)
            with (
                patch("routers.ws.stt.transcribe_audio", AsyncMock(return_value=None)),
                patch("routers.ws.stream_llm") as mock_llm,
            ):
                await _run_turn(ws, "sess-no-llm", queue, [0.0])
                mock_llm.assert_not_called()

        asyncio.run(go())

    def test_stt_none_no_tts_call(self):
        ws = _make_ws()

        async def go():
            queue: asyncio.Queue[bytes | None] = asyncio.Queue()
            await queue.put(b"\x00" * 3200)
            await queue.put(None)
            with (
                patch("routers.ws.stt.transcribe_audio", AsyncMock(return_value=None)),
                patch("routers.ws.stream_tts_cartesia") as mock_tts_c,
                patch("routers.ws.stream_tts") as mock_tts,
            ):
                await _run_turn(ws, "sess-no-tts", queue, [0.0])
                mock_tts_c.assert_not_called()
                mock_tts.assert_not_called()

        asyncio.run(go())

    def test_stt_none_does_not_raise(self):
        """STT failure must not propagate an exception — turn should complete cleanly."""
        try:
            self._run(None)
        except Exception as exc:
            raise AssertionError(f"_run_turn raised unexpectedly: {exc}") from exc

    def test_stt_none_only_error_and_audio_end_sent(self):
        """No spurious events (transcript, llm_token, audio_chunk) should arrive."""
        ws = self._run(None)
        types = _sent_types(ws)
        allowed = {"error", "audio_end"}
        unexpected = [t for t in types if t not in allowed]
        assert not unexpected, f"unexpected events sent: {unexpected}"
