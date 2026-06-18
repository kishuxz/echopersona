"""Tests for Step 7 Slice F — entitlement gating in the live WebSocket path.

Coverage:
  - Chat gate: free-tier (no row), creator/active, legacy/active → accept (no 4002)
  - Chat gate: chat denied → close 4002, never accept
  - Voice flag: entitlement=None → voice denied (free tier, text continues)
  - Voice flag: creator/active + consent allows → voice allowed
  - Voice flag: creator/canceled → voice denied
  - Voice flag: consent voice_clone=False → voice denied despite valid entitlement
  - Video flag: entitlement=None → video denied (text continues)
  - Video flag: creator/active → video denied (legacy required)
  - Video flag: legacy/active + consent allows → video allowed
  - Video flag: consent video_avatar=False → video denied despite valid entitlement
  - Simli gate: entitlement=None → simli_session_error with billing denial
  - Simli gate: consent video_avatar=False → gate condition fires (pure logic)
  - Simli gate: legacy/active entitlement → billing gate passes (error is config, not billing)

All DB and WebSocket calls are mocked — no Supabase, no network.
"""
import asyncio
import contextlib
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import WebSocketDisconnect

from models.consent import ListenerContext, ModalityConsent
from models.entitlements import StripeEntitlement
from services.entitlements import can_use_video, can_use_voice

# ── Fixtures ───────────────────────────────────────────────────────────────────

_SESSION_ID = "sess-ws-ent"
_USER_ID = "user-ws-ent"
_CUSTOMER_ID = "cus_ws_ent"
_ENT_ID = "ent-ws-ent"
_PERIOD_END = datetime(2027, 1, 1, tzinfo=timezone.utc)


def _make_ent(tier: str = "creator", status: str = "active") -> StripeEntitlement:
    return StripeEntitlement(
        id=_ENT_ID,
        user_id=_USER_ID,
        stripe_customer_id=_CUSTOMER_ID,
        plan_tier=tier,
        status=status,
        cancel_at_period_end=False,
        current_period_end=_PERIOD_END,
    )


def _make_ctx(voice: bool = True, video: bool = True) -> ListenerContext:
    return ListenerContext(
        is_owner=True,
        listener_user_id=_USER_ID,
        allowed_modalities=ModalityConsent(text_twin=True, voice_clone=voice, video_avatar=video),
    )


def _make_ws(extra_messages: list | None = None) -> MagicMock:
    ws = MagicMock()
    ws.query_params = {"token": "tok", "persona_id": ""}
    ws.close = AsyncMock()
    ws.accept = AsyncMock()
    ws.send_json = AsyncMock()
    msgs = list(extra_messages or [])
    ws.receive = AsyncMock(side_effect=msgs + [WebSocketDisconnect()])
    return ws


def _run_endpoint(
    ws: MagicMock,
    entitlement: StripeEntitlement | None,
    overrides: dict | None = None,
) -> None:
    """Run websocket_endpoint (freeform, no persona_id) with given entitlement."""
    async def go() -> None:
        from routers.ws import websocket_endpoint
        mocks: dict = {
            "verify_token": AsyncMock(return_value=_USER_ID),
            "get_db": MagicMock(return_value=MagicMock()),
            "get_entitlement_for_user": AsyncMock(return_value=entitlement),
        }
        if overrides:
            mocks.update(overrides)
        with contextlib.ExitStack() as stack:
            for attr, val in mocks.items():
                stack.enter_context(patch(f"routers.ws.{attr}", new=val))
            await websocket_endpoint(ws, _SESSION_ID)

    asyncio.run(go())


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Connect-time billing gate
# ═══════════════════════════════════════════════════════════════════════════════

class TestConnectTimeBillingGate:

    def test_free_tier_no_row_accepts(self):
        """No entitlement row (free tier) → accept, not 4002."""
        ws = _make_ws()
        _run_endpoint(ws, None)
        ws.accept.assert_awaited_once()
        ws.close.assert_not_awaited()

    def test_creator_active_accepts(self):
        ws = _make_ws()
        _run_endpoint(ws, _make_ent("creator", "active"))
        ws.accept.assert_awaited_once()
        ws.close.assert_not_awaited()

    def test_legacy_active_accepts(self):
        ws = _make_ws()
        _run_endpoint(ws, _make_ent("legacy", "active"))
        ws.accept.assert_awaited_once()
        ws.close.assert_not_awaited()

    def test_chat_denied_closes_4002_before_accept(self):
        """When can_use_chat returns False, close 4002 and never accept."""
        ws = _make_ws()
        _run_endpoint(ws, _make_ent(), overrides={"can_use_chat": MagicMock(return_value=False)})
        ws.close.assert_awaited_once_with(code=4002, reason="Subscription required")
        ws.accept.assert_not_awaited()


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Voice modality flag (per-turn)
# ═══════════════════════════════════════════════════════════════════════════════

class TestVoiceModalityFlag:
    """Reproduce the _voice_allowed computation from _run_turn_inner / _run_text_turn."""

    @staticmethod
    def _voice_allowed(entitlement: StripeEntitlement | None, ctx: ListenerContext | None) -> bool:
        return can_use_voice(entitlement) and (ctx is None or ctx.allowed_modalities.voice_clone)

    def test_entitlement_none_denies_voice(self):
        """Free tier (no row) → voice denied; text reply continues unaffected."""
        assert self._voice_allowed(None, _make_ctx()) is False

    def test_creator_active_consent_allows_voice(self):
        assert self._voice_allowed(_make_ent("creator", "active"), _make_ctx(voice=True)) is True

    def test_creator_canceled_denies_voice(self):
        assert self._voice_allowed(_make_ent("creator", "canceled"), _make_ctx(voice=True)) is False

    def test_consent_voice_clone_false_denies_voice(self):
        """Valid entitlement but consent blocks voice → denied."""
        assert self._voice_allowed(_make_ent("creator", "active"), _make_ctx(voice=False)) is False


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Video modality flag (per-turn)
# ═══════════════════════════════════════════════════════════════════════════════

class TestVideoModalityFlag:
    """Reproduce the _video_allowed computation from _run_turn_inner / _run_text_turn."""

    @staticmethod
    def _video_allowed(entitlement: StripeEntitlement | None, ctx: ListenerContext | None) -> bool:
        return can_use_video(entitlement) and (ctx is None or ctx.allowed_modalities.video_avatar)

    def test_entitlement_none_denies_video(self):
        """Free tier (no row) → video denied; text reply continues unaffected."""
        assert self._video_allowed(None, _make_ctx()) is False

    def test_creator_active_denies_video(self):
        """Creator tier does not include video — legacy required."""
        assert self._video_allowed(_make_ent("creator", "active"), _make_ctx(video=True)) is False

    def test_legacy_active_consent_allows_video(self):
        assert self._video_allowed(_make_ent("legacy", "active"), _make_ctx(video=True)) is True

    def test_consent_video_avatar_false_denies_video(self):
        """Valid legacy entitlement but consent blocks video → denied."""
        assert self._video_allowed(_make_ent("legacy", "active"), _make_ctx(video=False)) is False


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Simli session gate
# ═══════════════════════════════════════════════════════════════════════════════

class TestSimliGate:

    def _run_simli(self, entitlement: StripeEntitlement | None) -> MagicMock:
        ws = _make_ws(extra_messages=[{"text": json.dumps({"type": "simli_session_request"})}])
        _run_endpoint(ws, entitlement)
        return ws

    @staticmethod
    def _simli_errors(ws: MagicMock) -> list[dict]:
        return [
            c.args[0] for c in ws.send_json.call_args_list
            if c.args and c.args[0].get("type") == "simli_session_error"
        ]

    def test_simli_denied_when_entitlement_none(self):
        """No entitlement row → simli_session_error with billing denial message."""
        ws = self._run_simli(None)
        errors = self._simli_errors(ws)
        assert len(errors) == 1
        assert errors[0]["message"] == "Video not permitted"

    def test_simli_gate_condition_fires_when_consent_blocks(self):
        """Gate condition: consent video_avatar=False fires even with valid entitlement."""
        ctx = _make_ctx(video=False)
        ent = _make_ent("legacy", "active")
        gate_fires = (ctx is not None and not ctx.allowed_modalities.video_avatar) or not can_use_video(ent)
        assert gate_fires is True

    def test_simli_billing_gate_passes_for_legacy_active(self):
        """Legacy/active entitlement → billing gate passes; any error is config, not billing."""
        ws = self._run_simli(_make_ent("legacy", "active"))
        billing_denials = [e for e in self._simli_errors(ws) if e.get("message") == "Video not permitted"]
        assert len(billing_denials) == 0
