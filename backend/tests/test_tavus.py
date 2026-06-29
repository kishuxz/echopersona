"""Tests for services/tavus.py — all HTTP calls are mocked."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services import tavus as tavus_module
from services.tavus import generate_tavus_video


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(status: int, json_data: dict) -> MagicMock:
    """Build a mock aiohttp response context manager."""
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_data)
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _make_session(post_resp: MagicMock, get_resps: list) -> MagicMock:
    """
    Build a mock aiohttp.ClientSession whose .post() returns post_resp and
    whose .get() returns successive responses from get_resps on each call.
    """
    session = MagicMock()
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)

    session.post = MagicMock(return_value=post_resp)

    get_iter = iter(get_resps)

    def _get(*args, **kwargs):
        return next(get_iter)

    session.get = MagicMock(side_effect=_get)
    return session


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_submit_failure_returns_none():
    """POST returns HTTP 400 — generate_tavus_video must return None."""
    post_resp = _make_response(400, {})
    mock_session = _make_session(post_resp, [])

    async def go():
        with (
            patch("services.tavus.settings") as mock_settings,
            patch("aiohttp.ClientSession", return_value=mock_session),
        ):
            mock_settings.mock_mode = False
            mock_settings.tavus_api_key = "test-key"
            return await generate_tavus_video("replica-abc", "Hello world")

    result = asyncio.run(go())
    assert result is None


def test_poll_reaches_ready_returns_url():
    """
    POST succeeds, first poll returns generating, second poll returns ready
    with stream_url — function must return the stream URL.
    """
    post_resp = _make_response(201, {"video_id": "abc"})
    poll_generating = _make_response(200, {"status": "generating"})
    poll_ready = _make_response(200, {"status": "ready", "stream_url": "https://cdn.tavus.io/video.mp4"})
    mock_session = _make_session(post_resp, [poll_generating, poll_ready])

    async def go():
        with (
            patch("services.tavus.settings") as mock_settings,
            patch("aiohttp.ClientSession", return_value=mock_session),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_settings.mock_mode = False
            mock_settings.tavus_api_key = "test-key"
            return await generate_tavus_video("replica-abc", "Hello world", session_id="sess-001")

    result = asyncio.run(go())
    assert result == "https://cdn.tavus.io/video.mp4"


def test_poll_reaches_failed_returns_none():
    """Poll immediately returns failed — function must return None."""
    post_resp = _make_response(200, {"video_id": "abc"})
    poll_failed = _make_response(200, {"status": "failed"})
    mock_session = _make_session(post_resp, [poll_failed])

    async def go():
        with (
            patch("services.tavus.settings") as mock_settings,
            patch("aiohttp.ClientSession", return_value=mock_session),
            patch("asyncio.sleep", new_callable=AsyncMock),
        ):
            mock_settings.mock_mode = False
            mock_settings.tavus_api_key = "test-key"
            return await generate_tavus_video("replica-abc", "Hello world")

    result = asyncio.run(go())
    assert result is None


def test_poll_timeout_returns_none(monkeypatch):
    """
    With a tiny timeout/interval, poll always returns generating — function
    must time out and return None.
    """
    monkeypatch.setattr(tavus_module, "_POLL_TIMEOUT", 0.1)
    monkeypatch.setattr(tavus_module, "_POLL_INTERVAL", 0.05)

    post_resp = _make_response(201, {"video_id": "abc"})
    # Supply enough generating responses to outlast the poll loop
    get_resps = [_make_response(200, {"status": "generating"}) for _ in range(20)]
    mock_session = _make_session(post_resp, get_resps)

    async def go():
        with (
            patch("services.tavus.settings") as mock_settings,
            patch("aiohttp.ClientSession", return_value=mock_session),
        ):
            mock_settings.mock_mode = False
            mock_settings.tavus_api_key = "test-key"
            return await generate_tavus_video("replica-abc", "Hello world")

    result = asyncio.run(go())
    assert result is None


def test_mock_mode_returns_dummy_url():
    """When mock_mode=True, no HTTP calls made; returns an https string."""
    async def go():
        with (
            patch("services.tavus.settings") as mock_settings,
            patch("aiohttp.ClientSession") as mock_cls,
        ):
            mock_settings.mock_mode = True
            mock_settings.tavus_api_key = "test-key"
            result = await generate_tavus_video("replica-abc", "Hello world")
            mock_cls.assert_not_called()
            return result

    result = asyncio.run(go())
    assert isinstance(result, str)
    assert result.startswith("https://")


def test_empty_replica_id_returns_none():
    """Empty replica_id — return None immediately without any network call."""
    async def go():
        with (
            patch("services.tavus.settings") as mock_settings,
            patch("aiohttp.ClientSession") as mock_cls,
        ):
            mock_settings.mock_mode = False
            mock_settings.tavus_api_key = "test-key"
            result = await generate_tavus_video("", "Hello world")
            mock_cls.assert_not_called()
            return result

    result = asyncio.run(go())
    assert result is None
