import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from services import stt

_PCM_100MS = b"\x00" * 3200  # 100ms at 16 kHz mono int16

_GOOD_DG_RESPONSE = {
    "results": {
        "channels": [{"alternatives": [{"transcript": "hello world"}]}]
    }
}


def _mock_settings(provider: str = "deepgram", dg_key: str = "dg_test_key") -> MagicMock:
    m = MagicMock()
    m.mock_mode = False
    m.stt_provider = provider
    m.deepgram_api_key = dg_key
    m.groq_api_key = "gsk_test"
    return m


def _mock_http_ctx(status: int, body: dict) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = body
    resp.text = json.dumps(body)
    if status >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            f"HTTP {status}", request=MagicMock(), response=resp
        )
    else:
        resp.raise_for_status.return_value = None

    client_inst = AsyncMock()
    client_inst.post = AsyncMock(return_value=resp)

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client_inst)
    ctx.__aexit__ = AsyncMock(return_value=None)
    return ctx


class TestDispatch:

    def test_deepgram_provider_dispatches_to_deepgram(self):
        async def go():
            with (
                patch("services.stt.settings", _mock_settings("deepgram")),
                patch("services.stt._transcribe_deepgram", AsyncMock(return_value="hi")) as mock_dg,
                patch("services.stt._transcribe_groq", AsyncMock(return_value="bye")) as mock_gr,
            ):
                result = await stt.transcribe_audio(_PCM_100MS)
                mock_dg.assert_called_once()
                mock_gr.assert_not_called()
                assert result == "hi"

        asyncio.run(go())

    def test_groq_provider_dispatches_to_groq(self):
        async def go():
            with (
                patch("services.stt.settings", _mock_settings("groq")),
                patch("services.stt._transcribe_groq", AsyncMock(return_value="hi")) as mock_gr,
                patch("services.stt._transcribe_deepgram", AsyncMock(return_value="bye")) as mock_dg,
            ):
                result = await stt.transcribe_audio(_PCM_100MS)
                mock_gr.assert_called_once()
                mock_dg.assert_not_called()
                assert result == "hi"

        asyncio.run(go())

    def test_deepgram_missing_key_returns_none_without_http_call(self):
        async def go():
            with (
                patch("services.stt.settings", _mock_settings("deepgram", dg_key="")),
                patch("services.stt.httpx.AsyncClient") as mock_client_cls,
            ):
                result = await stt.transcribe_audio(_PCM_100MS)
                assert result is None
                mock_client_cls.assert_not_called()

        asyncio.run(go())


class TestDeepgramHTTP:

    def test_deepgram_200_returns_transcript(self):
        async def go():
            ctx = _mock_http_ctx(200, _GOOD_DG_RESPONSE)
            with (
                patch("services.stt.settings", _mock_settings("deepgram")),
                patch("services.stt.httpx.AsyncClient", return_value=ctx),
            ):
                result = await stt._transcribe_deepgram(b"\x00" * 100)
                assert result == "hello world"

        asyncio.run(go())

    def test_deepgram_401_returns_none(self):
        async def go():
            ctx = _mock_http_ctx(401, {"error": {"message": "Invalid API Key"}})
            with (
                patch("services.stt.settings", _mock_settings("deepgram")),
                patch("services.stt.httpx.AsyncClient", return_value=ctx),
            ):
                result = await stt._transcribe_deepgram(b"\x00" * 100)
                assert result is None

        asyncio.run(go())
