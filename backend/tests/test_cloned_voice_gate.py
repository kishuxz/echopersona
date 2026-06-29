"""Tests for Slice 8 — Cloned Voice Only gate.

Verifies that voice mode cannot activate without a cloned voice_id,
regardless of billing tier or dev-mode flags.
"""
import asyncio
import pytest
from unittest.mock import patch

import services.entitlements as _ent_mod
from services.entitlements import can_use_voice
from models.entitlements import StripeEntitlement


def _row(tier: str, status: str) -> dict:
    return {
        "id": "ent_001",
        "user_id": "user_001",
        "stripe_customer_id": "cus_001",
        "stripe_subscription_id": "sub_001",
        "stripe_price_id": "price_001",
        "plan_tier": tier,
        "status": status,
        "current_period_end": "2099-01-01T00:00:00",
        "created_at": "2026-01-01T00:00:00",
        "updated_at": "2026-01-01T00:00:00",
    }


class TestClonedVoiceGate:
    """No-stock-voice rule: voice_id=None → can_use_voice returns False,
    regardless of billing tier or voice_always_on dev flag."""

    def test_no_voice_id_blocks_voice_always_on(self):
        with patch.object(_ent_mod.settings, "voice_always_on", True):
            assert can_use_voice(None, voice_id=None) is False

    def test_no_voice_id_blocks_creator_entitlement(self):
        entitlement = StripeEntitlement(**_row("creator", "active"))
        assert can_use_voice(entitlement, voice_id=None) is False

    def test_no_voice_id_blocks_legacy_entitlement(self):
        entitlement = StripeEntitlement(**_row("legacy", "active"))
        assert can_use_voice(entitlement, voice_id=None) is False

    def test_no_voice_id_blocks_preservation_entitlement(self):
        entitlement = StripeEntitlement(**_row("preservation", "active"))
        assert can_use_voice(entitlement, voice_id=None) is False

    def test_empty_string_voice_id_treated_as_no_clone(self):
        with patch.object(_ent_mod.settings, "voice_always_on", True):
            assert can_use_voice(None, voice_id="") is False

    def test_cloned_voice_id_passes_with_voice_always_on(self):
        with patch.object(_ent_mod.settings, "voice_always_on", True):
            assert can_use_voice(None, voice_id="el_abc123") is True

    def test_cloned_voice_id_passes_with_creator_plan(self):
        entitlement = StripeEntitlement(**_row("creator", "active"))
        assert can_use_voice(entitlement, voice_id="el_abc123") is True

    def test_cloned_voice_id_passes_with_legacy_plan(self):
        entitlement = StripeEntitlement(**_row("legacy", "active"))
        assert can_use_voice(entitlement, voice_id="el_abc123") is True

    def test_sentinel_preserves_billing_only_check_voice_always_on_true(self):
        """Omitting voice_id uses sentinel — billing bypass via voice_always_on still works."""
        with patch.object(_ent_mod.settings, "voice_always_on", True):
            assert can_use_voice(None) is True

    def test_sentinel_preserves_billing_only_check_no_entitlement(self):
        """Omitting voice_id uses sentinel — billing check still applies when off."""
        assert can_use_voice(None) is False


class TestTTSGuard:
    """TTS services raise ValueError when called without a voice_id.

    These are defense-in-depth checks — by the time TTS is reached,
    can_use_voice should have already blocked the null voice_id. These
    tests verify the guard is also present inside the TTS layer itself.
    """

    def test_elevenlabs_raises_without_voice_id(self):
        from services.tts import tts_audio_chunks

        async def go():
            async for _ in tts_audio_chunks("hello", voice_id=None):
                pass

        with pytest.raises(ValueError, match="voice_id is required"):
            asyncio.run(go())

    def test_elevenlabs_raises_with_empty_string_voice_id(self):
        from services.tts import tts_audio_chunks

        async def go():
            async for _ in tts_audio_chunks("hello", voice_id=""):
                pass

        with pytest.raises(ValueError, match="voice_id is required"):
            asyncio.run(go())

    def test_cartesia_raises_without_voice_id(self):
        from services.tts_cartesia import tts_audio_chunks_cartesia

        async def go():
            async for _ in tts_audio_chunks_cartesia("hello", voice_id=None):
                pass

        with pytest.raises(ValueError, match="voice_id is required"):
            asyncio.run(go())

    def test_cartesia_raises_with_empty_string_voice_id(self):
        from services.tts_cartesia import tts_audio_chunks_cartesia

        async def go():
            async for _ in tts_audio_chunks_cartesia("hello", voice_id=""):
                pass

        with pytest.raises(ValueError, match="voice_id is required"):
            asyncio.run(go())
