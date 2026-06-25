"""Direct unit tests for Stage 0 normalize_source.

All external I/O (Groq Whisper, vision OCR) is mocked — no network calls required.
"""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from services.ingestion.stage0 import normalize_source


# ── video_audio modality ──────────────────────────────────────────────────────

def test_normalize_video_audio_with_text_returns_text():
    text, ts = asyncio.run(
        normalize_source(
            modality="video_audio",
            text_content="  I grew up in Chennai near the beach.  ",
            file_bytes=None,
            filename="upload",
            content_type="",
        )
    )
    assert text == "I grew up in Chennai near the beach."
    assert ts == (0.0, 0.0)


def test_normalize_video_audio_empty_text_no_file_returns_empty():
    text, ts = asyncio.run(
        normalize_source(
            modality="video_audio",
            text_content="",
            file_bytes=None,
            filename="upload",
            content_type="",
        )
    )
    assert text == ""
    assert ts == (0.0, 0.0)


def test_normalize_video_audio_whitespace_only_treated_as_empty():
    text, ts = asyncio.run(
        normalize_source(
            modality="video_audio",
            text_content="   ",
            file_bytes=None,
            filename="upload",
            content_type="",
        )
    )
    assert text == ""
    assert ts == (0.0, 0.0)


def test_normalize_video_audio_with_file_bytes_transcribes():
    fake_bytes = b"fake-media-content"
    with patch(
        "services.ingestion.stage0._transcribe_media",
        new_callable=AsyncMock,
        return_value=("transcribed answer", 4.2),
    ) as mock_transcribe:
        text, ts = asyncio.run(
            normalize_source(
                modality="video_audio",
                text_content="",
                file_bytes=fake_bytes,
                filename="answer.mp4",
                content_type="video/mp4",
            )
        )

    mock_transcribe.assert_awaited_once_with(fake_bytes, "answer.mp4", "video/mp4")
    assert text == "transcribed answer"
    assert ts == (0.0, 4.2)


def test_normalize_video_audio_text_takes_priority_over_file():
    """text_content is preferred; file_bytes are not touched when text is present."""
    with patch(
        "services.ingestion.stage0._transcribe_media",
        new_callable=AsyncMock,
    ) as mock_transcribe:
        text, ts = asyncio.run(
            normalize_source(
                modality="video_audio",
                text_content="Typed answer wins.",
                file_bytes=b"some-bytes",
                filename="answer.mp4",
                content_type="video/mp4",
            )
        )

    mock_transcribe.assert_not_awaited()
    assert text == "Typed answer wins."
    assert ts == (0.0, 0.0)


# ── existing modalities are unaffected ───────────────────────────────────────

def test_normalize_text_modality_unchanged():
    text, ts = asyncio.run(
        normalize_source(
            modality="text",
            text_content="Hello world.",
            file_bytes=None,
            filename="",
            content_type="",
        )
    )
    assert text == "Hello world."
    assert ts == (0.0, 0.0)


def test_normalize_unknown_modality_raises():
    with pytest.raises(ValueError, match="Unknown modality"):
        asyncio.run(
            normalize_source(
                modality="hologram",
                text_content="",
                file_bytes=None,
                filename="",
                content_type="",
            )
        )
