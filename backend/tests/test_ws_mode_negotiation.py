"""Tests for _negotiate_mode pure function — no I/O, no mocking required.

Covers the downgrade chain: video -> voice -> text.
"""
import pytest
from routers.ws import _negotiate_mode


class TestNegotiateModeText:
    def test_text_requested_returns_text(self):
        mode, reason = _negotiate_mode("text", voice_allowed=True, video_allowed=True)
        assert mode == "text"
        assert reason is None

    def test_text_requested_no_entitlements_returns_text(self):
        mode, reason = _negotiate_mode("text", voice_allowed=False, video_allowed=False)
        assert mode == "text"
        assert reason is None

    def test_unknown_requested_returns_text(self):
        mode, reason = _negotiate_mode("unknown", voice_allowed=True, video_allowed=True)
        assert mode == "text"
        assert reason is None


class TestNegotiateModeVoice:
    def test_voice_requested_voice_allowed(self):
        mode, reason = _negotiate_mode("voice", voice_allowed=True, video_allowed=False)
        assert mode == "voice"
        assert reason is None

    def test_voice_requested_voice_not_allowed_downgrades_to_text(self):
        mode, reason = _negotiate_mode("voice", voice_allowed=False, video_allowed=False)
        assert mode == "text"
        assert reason == "voice_not_entitled"

    def test_voice_requested_video_allowed_irrelevant(self):
        """video_allowed does not affect voice request."""
        mode, reason = _negotiate_mode("voice", voice_allowed=True, video_allowed=True)
        assert mode == "voice"
        assert reason is None

    def test_voice_requested_not_allowed_video_allowed_still_text(self):
        """voice_allowed=False always results in text, regardless of video_allowed."""
        mode, reason = _negotiate_mode("voice", voice_allowed=False, video_allowed=True)
        assert mode == "text"
        assert reason == "voice_not_entitled"


class TestNegotiateModeVideo:
    def test_video_requested_both_allowed(self):
        mode, reason = _negotiate_mode("video", voice_allowed=True, video_allowed=True)
        assert mode == "video"
        assert reason is None

    def test_video_requested_video_not_entitled_downgrades_to_voice(self):
        mode, reason = _negotiate_mode("video", voice_allowed=True, video_allowed=False)
        assert mode == "voice"
        assert reason == "video_not_entitled"

    def test_video_requested_neither_allowed_downgrades_to_text(self):
        mode, reason = _negotiate_mode("video", voice_allowed=False, video_allowed=False)
        assert mode == "text"
        assert reason == "voice_not_entitled"

    def test_video_requested_video_allowed_voice_not_allowed(self):
        """video_allowed=True, voice_allowed=False — video proceeds (video implies voice)."""
        mode, reason = _negotiate_mode("video", voice_allowed=False, video_allowed=True)
        assert mode == "video"
        assert reason is None

    def test_video_not_entitled_voice_not_allowed_double_downgrade(self):
        """Full double downgrade: video denied then voice denied -> text."""
        mode, reason = _negotiate_mode("video", voice_allowed=False, video_allowed=False)
        assert mode == "text"
        assert reason == "voice_not_entitled"


class TestNegotiateModeReasonValues:
    """Verify the exact reason strings match the protocol spec."""

    def test_voice_not_entitled_reason_string(self):
        _, reason = _negotiate_mode("voice", voice_allowed=False, video_allowed=False)
        assert reason == "voice_not_entitled"

    def test_video_not_entitled_reason_string(self):
        _, reason = _negotiate_mode("video", voice_allowed=True, video_allowed=False)
        assert reason == "video_not_entitled"

    def test_no_reason_when_exact_mode_granted(self):
        for requested in ("text", "voice", "video"):
            _, reason = _negotiate_mode(
                requested,
                voice_allowed=True,
                video_allowed=True,
            )
            assert reason is None, f"expected no reason for {requested!r}, got {reason!r}"
