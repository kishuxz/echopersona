"""Tests for build step 7 — Slice D: Stripe webhook handler and service.

Coverage (route layer):
  - Invalid Stripe signature → 400
  - Valid signature accepted → 200
  - Duplicate event_id (idempotency) → 200, process_stripe_event not called

Coverage (service — record_event_idempotent):
  - New event_id → inserts row, returns True
  - Existing event_id → no insert, returns False

Coverage (service — _price_to_tier):
  - Configured creator price → "creator"
  - Configured legacy price → "legacy"
  - Unknown price → None (never grants paid access)
  - Empty price_id → None

Coverage (service — handle_subscription_event):
  - subscription.updated with valid price+status → entitlement upserted
  - subscription.deleted (status=canceled) → status=canceled upserted
  - Unknown price → upsert skipped
  - Missing user (no metadata, no DB row) → skipped safely

Coverage (service — handle_checkout_completed):
  - checkout.session.completed with subscription + user_id → upsert called
  - No subscription_id in session → skipped
  - No user_id in session or DB → skipped

All Stripe API calls and DB calls are mocked — no real network.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import stripe
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routers.billing import router as billing_router

# ── Constants ──────────────────────────────────────────────────────────────────

_USER_ID = "user-webhook-abc"
_CUSTOMER_ID = "cus_wh_test"
_SUB_ID = "sub_wh_test"
_SESSION_ID_STR = "cs_wh_test"
_CREATOR_PRICE = "price_creator_wh_test"
_LEGACY_PRICE = "price_legacy_wh_test"
_EVENT_ID = "evt_wh_test_001"


# ── Mock builders ──────────────────────────────────────────────────────────────

def _make_db(execute_returns: list) -> MagicMock:
    q = MagicMock()
    q.select.return_value = q
    q.eq.return_value = q
    q.insert.return_value = q
    q.upsert.return_value = q
    q.maybe_single.return_value = q
    q.execute.side_effect = [MagicMock(data=d) for d in execute_returns]
    db = MagicMock()
    db.table.return_value = q
    return db


def _make_subscription(
    price_id: str = _CREATOR_PRICE,
    status: str = "active",
    user_id: str | None = _USER_ID,
    sub_id: str = _SUB_ID,
    customer: str = _CUSTOMER_ID,
    period_end: int = 1_735_689_600,
) -> MagicMock:
    """Build a mock Stripe Subscription object."""
    sub = MagicMock()
    sub.id = sub_id
    sub.customer = customer
    sub.status = status
    sub.current_period_end = period_end
    sub.cancel_at_period_end = False
    sub.metadata = {"supabase_user_id": user_id} if user_id else {}

    price_item = MagicMock()
    price_item.price.id = price_id
    sub.items.data = [price_item]
    return sub


def _make_session(
    subscription_id: str | None = _SUB_ID,
    customer: str = _CUSTOMER_ID,
    user_id: str | None = _USER_ID,
) -> MagicMock:
    """Build a mock Stripe CheckoutSession object."""
    session = MagicMock()
    session.id = _SESSION_ID_STR
    session.subscription = subscription_id
    session.customer = customer
    session.metadata = {"supabase_user_id": user_id} if user_id else {}
    _data = {
        "subscription": subscription_id,
        "customer": customer,
        "metadata": {"supabase_user_id": user_id} if user_id else {},
        "id": _SESSION_ID_STR,
    }
    session.get = lambda k, d=None: _data.get(k, d)
    return session


def _make_stripe_event(event_type: str, obj: MagicMock, event_id: str = _EVENT_ID) -> MagicMock:
    event = MagicMock()
    event.id = event_id
    event.type = event_type
    event.data.object = obj
    return event


def _settings_with_prices(
    creator: str = _CREATOR_PRICE,
    legacy: str = _LEGACY_PRICE,
) -> MagicMock:
    m = MagicMock()
    m.stripe_price_creator_monthly = creator
    m.stripe_price_legacy_monthly = legacy
    return m


def _make_route_client() -> TestClient:
    app = FastAPI()
    app.include_router(billing_router)
    return TestClient(app, raise_server_exceptions=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Route layer
# ═══════════════════════════════════════════════════════════════════════════════

class TestWebhookRoute:

    def test_invalid_signature_returns_400(self):
        client = _make_route_client()
        with patch(
            "stripe.Webhook.construct_event",
            side_effect=stripe.SignatureVerificationError("bad sig", "header"),
        ):
            resp = client.post(
                "/billing/webhook",
                content=b"fake_body",
                headers={"stripe-signature": "bad_sig"},
            )
        assert resp.status_code == 400

    def test_malformed_payload_returns_400(self):
        client = _make_route_client()
        with patch("stripe.Webhook.construct_event", side_effect=ValueError("bad json")):
            resp = client.post(
                "/billing/webhook",
                content=b"not_json",
                headers={"stripe-signature": "any"},
            )
        assert resp.status_code == 400

    def test_valid_event_returns_200(self):
        client = _make_route_client()
        mock_event = _make_stripe_event("customer.subscription.updated", _make_subscription())
        with patch("stripe.Webhook.construct_event", return_value=mock_event), \
             patch("routers.billing.record_event_idempotent", new_callable=AsyncMock, return_value=True), \
             patch("routers.billing.process_stripe_event", new_callable=AsyncMock):
            resp = client.post(
                "/billing/webhook",
                content=b"fake_body",
                headers={"stripe-signature": "sig"},
            )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    def test_duplicate_event_returns_200_without_processing(self):
        """Idempotency: already-seen event returns 200 and skips process_stripe_event."""
        client = _make_route_client()
        mock_event = _make_stripe_event("customer.subscription.updated", _make_subscription())
        with patch("stripe.Webhook.construct_event", return_value=mock_event), \
             patch("routers.billing.record_event_idempotent", new_callable=AsyncMock, return_value=False) as mock_record, \
             patch("routers.billing.process_stripe_event", new_callable=AsyncMock) as mock_process:
            resp = client.post(
                "/billing/webhook",
                content=b"fake_body",
                headers={"stripe-signature": "sig"},
            )
        assert resp.status_code == 200
        mock_record.assert_called_once()
        mock_process.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════════
# 2. record_event_idempotent
# ═══════════════════════════════════════════════════════════════════════════════

class TestRecordEventIdempotent:

    def test_new_event_inserts_and_returns_true(self):
        from services.stripe_webhooks import record_event_idempotent

        db = _make_db([None, None])  # select→nothing, insert→ok
        q = db.table.return_value

        result = asyncio.run(record_event_idempotent(db, _EVENT_ID, "customer.subscription.updated"))

        assert result is True
        q.insert.assert_called_once()
        payload = q.insert.call_args.args[0]
        assert payload["stripe_event_id"] == _EVENT_ID
        assert payload["event_type"] == "customer.subscription.updated"

    def test_existing_event_skips_insert_and_returns_false(self):
        from services.stripe_webhooks import record_event_idempotent

        db = _make_db([{"stripe_event_id": _EVENT_ID}])  # select→found
        q = db.table.return_value

        result = asyncio.run(record_event_idempotent(db, _EVENT_ID, "customer.subscription.updated"))

        assert result is False
        q.insert.assert_not_called()


# ═══════════════════════════════════════════════════════════════════════════════
# 3. _price_to_tier
# ═══════════════════════════════════════════════════════════════════════════════

class TestPriceToTier:

    def test_creator_price_returns_creator(self):
        from services.stripe_webhooks import _price_to_tier

        with patch("services.stripe_webhooks.settings", _settings_with_prices()):
            assert _price_to_tier(_CREATOR_PRICE) == "creator"

    def test_legacy_price_returns_legacy(self):
        from services.stripe_webhooks import _price_to_tier

        with patch("services.stripe_webhooks.settings", _settings_with_prices()):
            assert _price_to_tier(_LEGACY_PRICE) == "legacy"

    def test_unknown_price_returns_none(self):
        from services.stripe_webhooks import _price_to_tier

        with patch("services.stripe_webhooks.settings", _settings_with_prices()):
            assert _price_to_tier("price_unknown_xyz") is None

    def test_empty_price_returns_none(self):
        from services.stripe_webhooks import _price_to_tier

        with patch("services.stripe_webhooks.settings", _settings_with_prices()):
            assert _price_to_tier("") is None

    def test_unconfigured_price_env_never_matches(self):
        """If env vars are empty, no price matches — never grants paid tier."""
        from services.stripe_webhooks import _price_to_tier

        with patch("services.stripe_webhooks.settings", _settings_with_prices(creator="", legacy="")):
            assert _price_to_tier(_CREATOR_PRICE) is None


# ═══════════════════════════════════════════════════════════════════════════════
# 4. handle_subscription_event
# ═══════════════════════════════════════════════════════════════════════════════

class TestHandleSubscriptionEvent:

    def _run(self, subscription, upsert_mock, lookup_return=None):
        from services.stripe_webhooks import handle_subscription_event

        with patch("services.stripe_webhooks.settings", _settings_with_prices()), \
             patch(
                 "services.stripe_webhooks.get_entitlement_by_customer_or_subscription",
                 new_callable=AsyncMock,
                 return_value=lookup_return,
             ), \
             patch(
                 "services.stripe_webhooks.upsert_entitlement_from_subscription",
                 upsert_mock,
             ):
            asyncio.run(handle_subscription_event(MagicMock(), subscription))

    def test_subscription_updated_upserts_entitlement(self):
        upsert = AsyncMock()
        self._run(_make_subscription(price_id=_CREATOR_PRICE, status="active"), upsert)
        upsert.assert_called_once()
        kwargs = upsert.call_args.kwargs
        assert kwargs["plan_tier"] == "creator"
        assert kwargs["status"] == "active"
        assert kwargs["user_id"] == _USER_ID

    def test_subscription_deleted_upserts_canceled_status(self):
        """customer.subscription.deleted sends status='canceled' — access should be denied."""
        upsert = AsyncMock()
        self._run(_make_subscription(price_id=_CREATOR_PRICE, status="canceled"), upsert)
        upsert.assert_called_once()
        assert upsert.call_args.kwargs["status"] == "canceled"

    def test_legacy_subscription_upserts_legacy_tier(self):
        upsert = AsyncMock()
        self._run(_make_subscription(price_id=_LEGACY_PRICE, status="active"), upsert)
        upsert.assert_called_once()
        assert upsert.call_args.kwargs["plan_tier"] == "legacy"

    def test_unknown_price_skips_upsert(self):
        upsert = AsyncMock()
        self._run(_make_subscription(price_id="price_unknown_xyz", status="active"), upsert)
        upsert.assert_not_called()

    def test_missing_user_skips_upsert_safely(self):
        """No metadata user_id and no DB row → log warning, do nothing."""
        upsert = AsyncMock()
        sub = _make_subscription(user_id=None)  # no metadata
        self._run(sub, upsert, lookup_return=None)  # no DB row
        upsert.assert_not_called()

    def test_user_resolved_from_db_when_no_metadata(self):
        """User_id comes from existing entitlement row when metadata is empty."""
        from models.entitlements import StripeEntitlement

        existing_entitlement = StripeEntitlement(
            id="ent-uuid",
            user_id=_USER_ID,
            stripe_customer_id=_CUSTOMER_ID,
            plan_tier="creator",
            status="active",
        )
        upsert = AsyncMock()
        sub = _make_subscription(user_id=None)  # no metadata
        self._run(sub, upsert, lookup_return=existing_entitlement)
        upsert.assert_called_once()
        assert upsert.call_args.kwargs["user_id"] == _USER_ID

    def test_past_due_status_mapped_correctly(self):
        upsert = AsyncMock()
        self._run(_make_subscription(price_id=_CREATOR_PRICE, status="past_due"), upsert)
        upsert.assert_called_once()
        assert upsert.call_args.kwargs["status"] == "past_due"

    def test_unknown_stripe_status_defaults_to_canceled(self):
        """Unknown Stripe status (e.g. 'incomplete') defaults to 'canceled' — safe deny."""
        upsert = AsyncMock()
        self._run(_make_subscription(price_id=_CREATOR_PRICE, status="incomplete"), upsert)
        upsert.assert_called_once()
        assert upsert.call_args.kwargs["status"] == "canceled"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. handle_checkout_completed
# ═══════════════════════════════════════════════════════════════════════════════

class TestHandleCheckoutCompleted:

    def _run(self, session, retrieved_subscription, upsert_mock):
        from services.stripe_webhooks import handle_checkout_completed

        with patch("services.stripe_webhooks.settings", _settings_with_prices()), \
             patch(
                 "stripe.Subscription.retrieve",
                 return_value=retrieved_subscription,
             ), \
             patch(
                 "services.stripe_webhooks.get_entitlement_by_customer_or_subscription",
                 new_callable=AsyncMock,
                 return_value=None,
             ), \
             patch(
                 "services.stripe_webhooks.upsert_entitlement_from_subscription",
                 upsert_mock,
             ):
            asyncio.run(handle_checkout_completed(MagicMock(), session))

    def test_checkout_completed_retrieves_subscription_and_upserts(self):
        upsert = AsyncMock()
        session = _make_session(subscription_id=_SUB_ID, user_id=_USER_ID)
        sub = _make_subscription(price_id=_CREATOR_PRICE, status="active", user_id=None)
        self._run(session, sub, upsert)
        upsert.assert_called_once()
        kwargs = upsert.call_args.kwargs
        assert kwargs["plan_tier"] == "creator"
        assert kwargs["user_id"] == _USER_ID  # came from session metadata

    def test_no_subscription_id_skips(self):
        upsert = AsyncMock()
        session = _make_session(subscription_id=None)
        self._run(session, _make_subscription(), upsert)
        upsert.assert_not_called()

    def test_no_user_id_in_session_or_db_skips(self):
        upsert = AsyncMock()
        session = _make_session(user_id=None)
        sub = _make_subscription(user_id=None)  # also no metadata on sub
        self._run(session, sub, upsert)
        upsert.assert_not_called()

    def test_stripe_subscription_retrieve_called_with_subscription_id(self):
        upsert = AsyncMock()
        session = _make_session(subscription_id=_SUB_ID)
        sub = _make_subscription(price_id=_CREATOR_PRICE)

        with patch("services.stripe_webhooks.settings", _settings_with_prices()), \
             patch("stripe.Subscription.retrieve", return_value=sub) as mock_retrieve, \
             patch("services.stripe_webhooks.get_entitlement_by_customer_or_subscription", new_callable=AsyncMock, return_value=None), \
             patch("services.stripe_webhooks.upsert_entitlement_from_subscription", upsert):
            asyncio.run(
                __import__("services.stripe_webhooks", fromlist=["handle_checkout_completed"])
                .handle_checkout_completed(MagicMock(), session)
            )

        mock_retrieve.assert_called_once_with(_SUB_ID)
