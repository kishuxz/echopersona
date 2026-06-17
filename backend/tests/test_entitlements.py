"""Tests for build step 7 — Slice B: entitlement models and service.

Coverage:
  - can_use_chat always True (all tiers, including None)
  - can_use_voice True for creator/legacy active or trialing; False otherwise
  - can_use_video True for legacy active or trialing only
  - get_entitlement_for_user returns None when no row (free default)
  - get_entitlement_for_user returns StripeEntitlement when row exists
  - upsert_entitlement_from_subscription writes expected fields with on_conflict=user_id
  - get_entitlement_by_customer_or_subscription finds by customer_id
  - get_entitlement_by_customer_or_subscription falls back to subscription_id
  - get_entitlement_by_customer_or_subscription returns None when both miss

All DB calls are mocked — no Supabase, no network.
"""
import asyncio
from datetime import datetime, timezone
from unittest.mock import MagicMock

from models.entitlements import StripeEntitlement
from services.entitlements import (
    can_use_chat,
    can_use_video,
    can_use_voice,
    get_entitlement_by_customer_or_subscription,
    get_entitlement_for_user,
    upsert_entitlement_from_subscription,
)

# ── Constants ──────────────────────────────────────────────────────────────────

_USER_ID = "user-billing-abc"
_CUSTOMER_ID = "cus_test123"
_SUBSCRIPTION_ID = "sub_test456"
_ENTITLEMENT_ID = "ent-uuid-abc"
_PERIOD_END = datetime(2026, 12, 31, tzinfo=timezone.utc)


def _row(plan_tier: str = "creator", status: str = "active") -> dict:
    return {
        "id": _ENTITLEMENT_ID,
        "user_id": _USER_ID,
        "stripe_customer_id": _CUSTOMER_ID,
        "stripe_subscription_id": _SUBSCRIPTION_ID,
        "plan_tier": plan_tier,
        "status": status,
        "cancel_at_period_end": False,
        "current_period_end": _PERIOD_END.isoformat(),
        "created_at": None,
        "updated_at": None,
    }


# ── DB mock ────────────────────────────────────────────────────────────────────

def _make_db(execute_returns: list) -> MagicMock:
    """Build a mock Supabase client whose successive .execute() calls return
    items in order. Each item in execute_returns becomes result.data."""
    q = MagicMock()
    q.select.return_value = q
    q.eq.return_value = q
    q.update.return_value = q
    q.insert.return_value = q
    q.upsert.return_value = q
    q.maybe_single.return_value = q
    q.execute.side_effect = [MagicMock(data=d) for d in execute_returns]
    db = MagicMock()
    db.table.return_value = q
    return db


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Access predicates — pure functions, no DB
# ═══════════════════════════════════════════════════════════════════════════════

class TestAccessPredicates:

    # can_use_chat

    def test_chat_none_returns_true(self):
        assert can_use_chat(None) is True

    def test_chat_free_active_returns_true(self):
        assert can_use_chat(StripeEntitlement(**_row("free", "active"))) is True

    def test_chat_creator_returns_true(self):
        assert can_use_chat(StripeEntitlement(**_row("creator", "active"))) is True

    def test_chat_legacy_returns_true(self):
        assert can_use_chat(StripeEntitlement(**_row("legacy", "active"))) is True

    # can_use_voice

    def test_voice_none_returns_false(self):
        assert can_use_voice(None) is False

    def test_voice_free_active_returns_false(self):
        assert can_use_voice(StripeEntitlement(**_row("free", "active"))) is False

    def test_voice_creator_active_returns_true(self):
        assert can_use_voice(StripeEntitlement(**_row("creator", "active"))) is True

    def test_voice_creator_trialing_returns_true(self):
        assert can_use_voice(StripeEntitlement(**_row("creator", "trialing"))) is True

    def test_voice_creator_canceled_returns_false(self):
        assert can_use_voice(StripeEntitlement(**_row("creator", "canceled"))) is False

    def test_voice_creator_past_due_returns_false(self):
        assert can_use_voice(StripeEntitlement(**_row("creator", "past_due"))) is False

    def test_voice_creator_unpaid_returns_false(self):
        assert can_use_voice(StripeEntitlement(**_row("creator", "unpaid"))) is False

    def test_voice_legacy_active_returns_true(self):
        assert can_use_voice(StripeEntitlement(**_row("legacy", "active"))) is True

    def test_voice_legacy_canceled_returns_false(self):
        assert can_use_voice(StripeEntitlement(**_row("legacy", "canceled"))) is False

    # can_use_video

    def test_video_none_returns_false(self):
        assert can_use_video(None) is False

    def test_video_free_active_returns_false(self):
        assert can_use_video(StripeEntitlement(**_row("free", "active"))) is False

    def test_video_creator_active_returns_false(self):
        assert can_use_video(StripeEntitlement(**_row("creator", "active"))) is False

    def test_video_legacy_active_returns_true(self):
        assert can_use_video(StripeEntitlement(**_row("legacy", "active"))) is True

    def test_video_legacy_trialing_returns_true(self):
        assert can_use_video(StripeEntitlement(**_row("legacy", "trialing"))) is True

    def test_video_legacy_canceled_returns_false(self):
        assert can_use_video(StripeEntitlement(**_row("legacy", "canceled"))) is False

    def test_video_legacy_past_due_returns_false(self):
        assert can_use_video(StripeEntitlement(**_row("legacy", "past_due"))) is False


# ═══════════════════════════════════════════════════════════════════════════════
# 2. get_entitlement_for_user
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetEntitlementForUser:

    def test_returns_none_when_no_row(self):
        """No DB row → None (caller treats this as free tier)."""
        db = _make_db([None])
        result = asyncio.run(get_entitlement_for_user(db, _USER_ID))
        assert result is None

    def test_returns_entitlement_for_creator(self):
        db = _make_db([_row("creator", "active")])
        result = asyncio.run(get_entitlement_for_user(db, _USER_ID))
        assert result is not None
        assert result.plan_tier == "creator"
        assert result.status == "active"
        assert result.user_id == _USER_ID

    def test_returns_entitlement_for_legacy(self):
        db = _make_db([_row("legacy", "trialing")])
        result = asyncio.run(get_entitlement_for_user(db, _USER_ID))
        assert result is not None
        assert result.plan_tier == "legacy"
        assert result.status == "trialing"

    def test_queries_correct_table_and_user(self):
        db = _make_db([_row()])
        q = db.table.return_value
        asyncio.run(get_entitlement_for_user(db, _USER_ID))
        db.table.assert_called_with("stripe_entitlements")
        q.eq.assert_called_with("user_id", _USER_ID)


# ═══════════════════════════════════════════════════════════════════════════════
# 3. upsert_entitlement_from_subscription
# ═══════════════════════════════════════════════════════════════════════════════

class TestUpsertEntitlement:

    def test_writes_expected_fields(self):
        db = _make_db([None])
        q = db.table.return_value

        asyncio.run(
            upsert_entitlement_from_subscription(
                db,
                user_id=_USER_ID,
                stripe_customer_id=_CUSTOMER_ID,
                stripe_subscription_id=_SUBSCRIPTION_ID,
                plan_tier="creator",
                status="active",
                current_period_end=_PERIOD_END,
                cancel_at_period_end=False,
            )
        )

        q.upsert.assert_called_once()
        payload = q.upsert.call_args.args[0]
        assert payload["user_id"] == _USER_ID
        assert payload["stripe_customer_id"] == _CUSTOMER_ID
        assert payload["stripe_subscription_id"] == _SUBSCRIPTION_ID
        assert payload["plan_tier"] == "creator"
        assert payload["status"] == "active"
        assert payload["cancel_at_period_end"] is False
        assert payload["current_period_end"] is not None

    def test_uses_on_conflict_user_id(self):
        db = _make_db([None])
        q = db.table.return_value

        asyncio.run(
            upsert_entitlement_from_subscription(
                db,
                user_id=_USER_ID,
                stripe_customer_id=_CUSTOMER_ID,
                stripe_subscription_id=None,
                plan_tier="legacy",
                status="trialing",
                current_period_end=None,
            )
        )

        assert q.upsert.call_args.kwargs.get("on_conflict") == "user_id"

    def test_null_period_end_stored_as_none(self):
        db = _make_db([None])
        q = db.table.return_value

        asyncio.run(
            upsert_entitlement_from_subscription(
                db,
                user_id=_USER_ID,
                stripe_customer_id=_CUSTOMER_ID,
                stripe_subscription_id=None,
                plan_tier="creator",
                status="canceled",
                current_period_end=None,
            )
        )

        payload = q.upsert.call_args.args[0]
        assert payload["current_period_end"] is None


# ═══════════════════════════════════════════════════════════════════════════════
# 4. get_entitlement_by_customer_or_subscription
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetEntitlementByCustomerOrSubscription:

    def test_finds_by_customer_id(self):
        db = _make_db([_row("creator", "active")])
        result = asyncio.run(
            get_entitlement_by_customer_or_subscription(db, _CUSTOMER_ID, None)
        )
        assert result is not None
        assert result.stripe_customer_id == _CUSTOMER_ID

    def test_falls_back_to_subscription_id_when_customer_misses(self):
        """Customer query returns nothing; subscription query returns the row."""
        db = _make_db([None, _row("legacy", "active")])
        result = asyncio.run(
            get_entitlement_by_customer_or_subscription(db, _CUSTOMER_ID, _SUBSCRIPTION_ID)
        )
        assert result is not None
        assert result.plan_tier == "legacy"

    def test_returns_none_when_both_miss(self):
        db = _make_db([None, None])
        result = asyncio.run(
            get_entitlement_by_customer_or_subscription(db, _CUSTOMER_ID, _SUBSCRIPTION_ID)
        )
        assert result is None

    def test_returns_none_when_no_ids_given(self):
        db = _make_db([])
        result = asyncio.run(
            get_entitlement_by_customer_or_subscription(db, None, None)
        )
        assert result is None

    def test_skips_customer_query_when_customer_id_none(self):
        """With no customer_id, only the subscription query runs."""
        db = _make_db([_row("creator", "active")])
        result = asyncio.run(
            get_entitlement_by_customer_or_subscription(db, None, _SUBSCRIPTION_ID)
        )
        assert result is not None
        assert result.plan_tier == "creator"
