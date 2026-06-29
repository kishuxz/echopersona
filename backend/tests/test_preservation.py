"""Tests for Slice 6 — Preservation Tier.

Coverage (models/preservation.py):
  - PersonaPreservation and PosthumousAccessSubscription parse correctly

Coverage (services/preservation.py):
  - get_preservation_for_persona returns None when no row
  - get_preservation_for_persona returns PersonaPreservation when row exists
  - upsert_preservation calls upsert with on_conflict=persona_id
  - get_posthumous_subscription returns None when no row
  - get_posthumous_subscription_by_stripe_id returns row when found
  - upsert_posthumous_subscription calls upsert with on_conflict=persona_id,subscriber_user_id
  - can_access_preserved_persona: True only for status='paid'
  - can_access_posthumous: True for active/trialing; False for canceled/None

Coverage (services/stripe_webhooks.py — new handlers):
  - handle_preservation_checkout: valid payment writes row
  - handle_preservation_checkout: missing user_id skips silently
  - handle_preservation_checkout: missing persona_id skips silently
  - handle_preservation_payment_intent: non-preservation purchase_type skips
  - handle_preservation_payment_intent: valid metadata writes row
  - handle_posthumous_checkout: valid session writes row
  - handle_posthumous_checkout: missing subscription_id skips
  - handle_posthumous_subscription_event: updated event upserts row
  - handle_posthumous_subscription_event: deleted event forces status=canceled
  - handle_posthumous_subscription_event: missing metadata falls back to DB lookup
  - process_stripe_event: mode=payment routes to handle_preservation_checkout
  - process_stripe_event: payment_intent.succeeded routes to handle_preservation_payment_intent
  - process_stripe_event: posthumous_access subscription routes to handle_posthumous_subscription_event

Coverage (routers/billing.py — new endpoints):
  - POST /billing/checkout/preservation: missing price config → 500
  - POST /billing/checkout/preservation: valid request → 200 with checkout_url
  - POST /billing/checkout/posthumous: missing price config → 500
  - POST /billing/checkout/posthumous: valid request → 200 with checkout_url
  - GET /billing/preservation/{persona_id}: returns preservation_locked and can_use_posthumous_chat

All Stripe and DB calls are mocked — no real network.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from middleware.auth import get_current_user
from models.preservation import PersonaPreservation, PosthumousAccessSubscription
from routers.billing import router as billing_router
from services.preservation import (
    can_access_posthumous,
    can_access_preserved_persona,
    get_posthumous_subscription,
    get_posthumous_subscription_by_stripe_id,
    get_preservation_for_persona,
    upsert_posthumous_subscription,
    upsert_preservation,
)
from services.stripe_webhooks import (
    handle_posthumous_checkout,
    handle_posthumous_subscription_event,
    handle_preservation_checkout,
    handle_preservation_payment_intent,
    process_stripe_event,
)

# ── Constants ──────────────────────────────────────────────────────────────────

_USER_ID = "user-preservation-abc"
_SUBSCRIBER_ID = "user-family-xyz"
_PERSONA_ID = "persona-uuid-001"
_CUSTOMER_ID = "cus_pres_test"
_SUB_ID = "sub_post_test"
_PI_ID = "pi_pres_test"
_SESSION_ID = "cs_pres_test"
_PRESERVATION_PRICE = "price_preservation_onetime"
_POSTHUMOUS_PRICE = "price_posthumous_monthly"
_CHECKOUT_URL = "https://checkout.stripe.com/pres_session"


# ── DB mock helpers ────────────────────────────────────────────────────────────

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


def _preservation_row(status: str = "paid") -> dict:
    return {
        "id": "pres-uuid-001",
        "persona_id": _PERSONA_ID,
        "subject_user_id": _USER_ID,
        "stripe_customer_id": _CUSTOMER_ID,
        "stripe_payment_intent_id": _PI_ID,
        "stripe_checkout_session_id": _SESSION_ID,
        "status": status,
        "paid_at": "2026-06-28T00:00:00+00:00",
        "created_at": "2026-06-28T00:00:00+00:00",
    }


def _posthumous_row(status: str = "active") -> dict:
    return {
        "id": "post-uuid-001",
        "persona_id": _PERSONA_ID,
        "subscriber_user_id": _SUBSCRIBER_ID,
        "stripe_customer_id": _CUSTOMER_ID,
        "stripe_subscription_id": _SUB_ID,
        "status": status,
        "current_period_end": "2026-07-28T00:00:00+00:00",
        "cancel_at_period_end": False,
        "created_at": "2026-06-28T00:00:00+00:00",
        "updated_at": "2026-06-28T00:00:00+00:00",
    }


def _make_checkout_session(
    mode: str = "payment",
    purchase_type: str = "preservation",
    user_id: str = _USER_ID,
    persona_id: str = _PERSONA_ID,
    subscription_id: str | None = None,
) -> MagicMock:
    session = MagicMock()
    session.id = _SESSION_ID
    session.mode = mode
    session.customer = _CUSTOMER_ID
    session.payment_intent = _PI_ID
    session.subscription = subscription_id
    session.metadata = {
        "supabase_user_id": user_id,
        "persona_id": persona_id,
        "purchase_type": purchase_type,
    }
    return session


def _make_subscription(
    status: str = "active",
    user_id: str = _SUBSCRIBER_ID,
    persona_id: str = _PERSONA_ID,
    purchase_type: str = "posthumous_access",
) -> MagicMock:
    sub = MagicMock()
    sub.id = _SUB_ID
    sub.customer = _CUSTOMER_ID
    sub.status = status
    sub.current_period_end = 1_756_339_200
    sub.cancel_at_period_end = False
    sub.metadata = {
        "supabase_user_id": user_id,
        "persona_id": persona_id,
        "purchase_type": purchase_type,
    }
    return sub


def _make_stripe_event(event_type: str, obj: MagicMock, event_id: str = "evt_pres_001") -> MagicMock:
    event = MagicMock()
    event.id = event_id
    event.type = event_type
    event.data.object = obj
    return event


def _make_client(with_auth: bool = True) -> TestClient:
    app = FastAPI()
    app.include_router(billing_router)
    if with_auth:
        app.dependency_overrides[get_current_user] = lambda: _USER_ID
    return TestClient(app, raise_server_exceptions=True)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Models
# ═══════════════════════════════════════════════════════════════════════════════

class TestPreservationModels:

    def test_persona_preservation_parses(self):
        row = _preservation_row()
        model = PersonaPreservation(**row)
        assert model.persona_id == _PERSONA_ID
        assert model.status == "paid"

    def test_posthumous_subscription_parses(self):
        row = _posthumous_row()
        model = PosthumousAccessSubscription(**row)
        assert model.persona_id == _PERSONA_ID
        assert model.status == "active"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Access predicates
# ═══════════════════════════════════════════════════════════════════════════════

class TestAccessPredicates:

    def test_can_access_preserved_none(self):
        assert can_access_preserved_persona(None) is False

    def test_can_access_preserved_paid(self):
        p = PersonaPreservation(**_preservation_row(status="paid"))
        assert can_access_preserved_persona(p) is True

    def test_can_access_preserved_refunded(self):
        p = PersonaPreservation(**_preservation_row(status="refunded"))
        assert can_access_preserved_persona(p) is False

    def test_can_access_posthumous_none(self):
        assert can_access_posthumous(None) is False

    def test_can_access_posthumous_active(self):
        s = PosthumousAccessSubscription(**_posthumous_row(status="active"))
        assert can_access_posthumous(s) is True

    def test_can_access_posthumous_trialing(self):
        s = PosthumousAccessSubscription(**_posthumous_row(status="trialing"))
        assert can_access_posthumous(s) is True

    def test_can_access_posthumous_canceled(self):
        s = PosthumousAccessSubscription(**_posthumous_row(status="canceled"))
        assert can_access_posthumous(s) is False

    def test_can_access_posthumous_past_due(self):
        s = PosthumousAccessSubscription(**_posthumous_row(status="past_due"))
        assert can_access_posthumous(s) is False


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Preservation service — DB queries
# ═══════════════════════════════════════════════════════════════════════════════

class TestPreservationService:

    def test_get_preservation_returns_none_when_no_row(self):
        db = _make_db([None])
        result = asyncio.run(
            get_preservation_for_persona(db, _PERSONA_ID)
        )
        assert result is None

    def test_get_preservation_returns_model_when_row_exists(self):
        db = _make_db([_preservation_row()])
        result = asyncio.run(
            get_preservation_for_persona(db, _PERSONA_ID)
        )
        assert isinstance(result, PersonaPreservation)
        assert result.status == "paid"

    def test_upsert_preservation_calls_correct_table(self):
        db = _make_db([None])
        asyncio.run(
            upsert_preservation(
                db,
                persona_id=_PERSONA_ID,
                subject_user_id=_USER_ID,
                stripe_customer_id=_CUSTOMER_ID,
                stripe_payment_intent_id=_PI_ID,
                stripe_checkout_session_id=_SESSION_ID,
            )
        )
        db.table.assert_called_with("persona_preservation")
        db.table().upsert.assert_called_once()
        call_kwargs = db.table().upsert.call_args
        assert call_kwargs[1]["on_conflict"] == "persona_id"
        assert call_kwargs[0][0]["status"] == "paid"

    def test_get_posthumous_returns_none_when_no_row(self):
        db = _make_db([None])
        result = asyncio.run(
            get_posthumous_subscription(db, _PERSONA_ID, _SUBSCRIBER_ID)
        )
        assert result is None

    def test_get_posthumous_by_stripe_id_returns_model(self):
        db = _make_db([_posthumous_row()])
        result = asyncio.run(
            get_posthumous_subscription_by_stripe_id(db, _SUB_ID)
        )
        assert isinstance(result, PosthumousAccessSubscription)
        assert result.stripe_subscription_id == _SUB_ID

    def test_upsert_posthumous_calls_correct_conflict_target(self):
        db = _make_db([None])
        asyncio.run(
            upsert_posthumous_subscription(
                db,
                persona_id=_PERSONA_ID,
                subscriber_user_id=_SUBSCRIBER_ID,
                stripe_customer_id=_CUSTOMER_ID,
                stripe_subscription_id=_SUB_ID,
                status="active",
                current_period_end=None,
            )
        )
        call_kwargs = db.table().upsert.call_args
        assert call_kwargs[1]["on_conflict"] == "persona_id,subscriber_user_id"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Webhook handlers — preservation
# ═══════════════════════════════════════════════════════════════════════════════

class TestPreservationWebhookHandlers:

    def test_handle_preservation_checkout_writes_row(self):
        db = _make_db([None])
        session = _make_checkout_session(mode="payment", purchase_type="preservation")
        with patch("services.stripe_webhooks.upsert_preservation", new_callable=AsyncMock) as mock_upsert:
            asyncio.run(handle_preservation_checkout(db, session))
        mock_upsert.assert_awaited_once()
        call_kwargs = mock_upsert.call_args[1]
        assert call_kwargs["persona_id"] == _PERSONA_ID
        assert call_kwargs["subject_user_id"] == _USER_ID
        assert call_kwargs["stripe_payment_intent_id"] == _PI_ID

    def test_handle_preservation_checkout_missing_user_id_skips(self):
        db = _make_db([])
        session = _make_checkout_session(user_id="")
        session.metadata = {"persona_id": _PERSONA_ID}
        with patch("services.stripe_webhooks.upsert_preservation", new_callable=AsyncMock) as mock_upsert:
            asyncio.run(handle_preservation_checkout(db, session))
        mock_upsert.assert_not_awaited()

    def test_handle_preservation_checkout_missing_persona_id_skips(self):
        db = _make_db([])
        session = _make_checkout_session()
        session.metadata = {"supabase_user_id": _USER_ID}
        with patch("services.stripe_webhooks.upsert_preservation", new_callable=AsyncMock) as mock_upsert:
            asyncio.run(handle_preservation_checkout(db, session))
        mock_upsert.assert_not_awaited()

    def test_handle_preservation_payment_intent_non_preservation_skips(self):
        db = _make_db([])
        pi = MagicMock()
        pi.metadata = {"purchase_type": "other"}
        with patch("services.stripe_webhooks.upsert_preservation", new_callable=AsyncMock) as mock_upsert:
            asyncio.run(handle_preservation_payment_intent(db, pi))
        mock_upsert.assert_not_awaited()

    def test_handle_preservation_payment_intent_valid_writes_row(self):
        db = _make_db([None])
        pi = MagicMock()
        pi.id = _PI_ID
        pi.customer = _CUSTOMER_ID
        pi.metadata = {
            "purchase_type": "preservation",
            "supabase_user_id": _USER_ID,
            "persona_id": _PERSONA_ID,
        }
        with patch("services.stripe_webhooks.upsert_preservation", new_callable=AsyncMock) as mock_upsert:
            asyncio.run(
                handle_preservation_payment_intent(db, pi)
            )
        mock_upsert.assert_awaited_once()
        assert mock_upsert.call_args[1]["stripe_payment_intent_id"] == _PI_ID


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Webhook handlers — posthumous
# ═══════════════════════════════════════════════════════════════════════════════

class TestPosthumousWebhookHandlers:

    def test_handle_posthumous_checkout_writes_row(self):
        db = _make_db([None])
        session = _make_checkout_session(
            mode="subscription", purchase_type="posthumous_access",
            user_id=_SUBSCRIBER_ID, subscription_id=_SUB_ID,
        )
        mock_sub = _make_subscription()
        with (
            patch("stripe.Subscription.retrieve", return_value=mock_sub),
            patch("services.stripe_webhooks.upsert_posthumous_subscription", new_callable=AsyncMock) as mock_upsert,
        ):
            asyncio.run(handle_posthumous_checkout(db, session))
        mock_upsert.assert_awaited_once()
        assert mock_upsert.call_args[1]["subscriber_user_id"] == _SUBSCRIBER_ID
        assert mock_upsert.call_args[1]["persona_id"] == _PERSONA_ID

    def test_handle_posthumous_checkout_no_subscription_skips(self):
        db = _make_db([])
        session = _make_checkout_session(mode="subscription", subscription_id=None)
        session.subscription = None
        with patch("services.stripe_webhooks.upsert_posthumous_subscription", new_callable=AsyncMock) as mock_upsert:
            asyncio.run(handle_posthumous_checkout(db, session))
        mock_upsert.assert_not_awaited()

    def test_handle_posthumous_subscription_event_updated(self):
        db = _make_db([None])
        sub = _make_subscription(status="active")
        with patch("services.stripe_webhooks.upsert_posthumous_subscription", new_callable=AsyncMock) as mock_upsert:
            asyncio.run(
                handle_posthumous_subscription_event(db, sub, "customer.subscription.updated")
            )
        mock_upsert.assert_awaited_once()
        assert mock_upsert.call_args[1]["status"] == "active"

    def test_handle_posthumous_subscription_event_deleted_forces_canceled(self):
        db = _make_db([None])
        sub = _make_subscription(status="active")
        with patch("services.stripe_webhooks.upsert_posthumous_subscription", new_callable=AsyncMock) as mock_upsert:
            asyncio.run(
                handle_posthumous_subscription_event(db, sub, "customer.subscription.deleted")
            )
        mock_upsert.assert_awaited_once()
        assert mock_upsert.call_args[1]["status"] == "canceled"

    def test_handle_posthumous_subscription_event_fallback_db_lookup(self):
        existing = PosthumousAccessSubscription(**_posthumous_row())
        db = _make_db([None])
        sub = _make_subscription()
        sub.metadata = {}  # no metadata — forces DB fallback

        with (
            patch(
                "services.stripe_webhooks.get_posthumous_subscription_by_stripe_id",
                new_callable=AsyncMock,
                return_value=existing,
            ),
            patch("services.stripe_webhooks.upsert_posthumous_subscription", new_callable=AsyncMock) as mock_upsert,
        ):
            asyncio.run(
                handle_posthumous_subscription_event(db, sub, "customer.subscription.updated")
            )
        mock_upsert.assert_awaited_once()
        assert mock_upsert.call_args[1]["subscriber_user_id"] == _SUBSCRIBER_ID


# ═══════════════════════════════════════════════════════════════════════════════
# 6. process_stripe_event routing
# ═══════════════════════════════════════════════════════════════════════════════

class TestProcessStripeEventRouting:

    def test_mode_payment_routes_to_preservation_checkout(self):
        obj = _make_checkout_session(mode="payment")
        event = _make_stripe_event("checkout.session.completed", obj)
        db = MagicMock()
        with patch(
            "services.stripe_webhooks.handle_preservation_checkout", new_callable=AsyncMock
        ) as mock_handler:
            asyncio.run(process_stripe_event(db, event))
        mock_handler.assert_awaited_once_with(db, obj)

    def test_payment_intent_succeeded_routes_to_preservation(self):
        pi = MagicMock()
        pi.metadata = {"purchase_type": "preservation"}
        event = _make_stripe_event("payment_intent.succeeded", pi)
        db = MagicMock()
        with patch(
            "services.stripe_webhooks.handle_preservation_payment_intent", new_callable=AsyncMock
        ) as mock_handler:
            asyncio.run(process_stripe_event(db, event))
        mock_handler.assert_awaited_once_with(db, pi)

    def test_posthumous_subscription_event_routed_correctly(self):
        sub = _make_subscription()
        event = _make_stripe_event("customer.subscription.updated", sub)
        db = MagicMock()
        with patch(
            "services.stripe_webhooks.handle_posthumous_subscription_event", new_callable=AsyncMock
        ) as mock_handler:
            asyncio.run(process_stripe_event(db, event))
        mock_handler.assert_awaited_once_with(db, sub, "customer.subscription.updated")

    def test_regular_subscription_event_still_routes_to_existing_handler(self):
        sub = MagicMock()
        sub.metadata = {}  # no purchase_type
        event = _make_stripe_event("customer.subscription.updated", sub)
        db = MagicMock()
        with patch(
            "services.stripe_webhooks.handle_subscription_event", new_callable=AsyncMock
        ) as mock_handler:
            asyncio.run(process_stripe_event(db, event))
        mock_handler.assert_awaited_once_with(db, sub)

    def test_mode_subscription_without_purchase_type_routes_to_existing(self):
        obj = _make_checkout_session(mode="subscription")
        obj.metadata = {"supabase_user_id": _USER_ID}  # no purchase_type
        event = _make_stripe_event("checkout.session.completed", obj)
        db = MagicMock()
        with patch(
            "services.stripe_webhooks.handle_checkout_completed", new_callable=AsyncMock
        ) as mock_handler:
            asyncio.run(process_stripe_event(db, event))
        mock_handler.assert_awaited_once_with(db, obj)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Router endpoints
# ═══════════════════════════════════════════════════════════════════════════════

class TestPreservationCheckoutRoute:

    def test_missing_preservation_price_returns_500(self):
        client = _make_client()
        mock_settings = MagicMock()
        mock_settings.stripe_price_preservation_onetime = ""
        mock_settings.stripe_price_posthumous_monthly = ""
        with patch("routers.billing.settings", mock_settings):
            resp = client.post(
                "/billing/checkout/preservation", json={"persona_id": _PERSONA_ID}
            )
        assert resp.status_code == 500

    def test_preservation_checkout_valid_returns_200(self):
        client = _make_client()
        mock_settings = MagicMock()
        mock_settings.stripe_price_preservation_onetime = _PRESERVATION_PRICE
        mock_settings.frontend_billing_success_url = "http://localhost/success"
        mock_settings.frontend_billing_cancel_url = "http://localhost/cancel"
        service_result = {"checkout_url": _CHECKOUT_URL, "session_id": _SESSION_ID}
        with (
            patch("routers.billing.settings", mock_settings),
            patch("routers.billing.get_db", return_value=MagicMock()),
            patch(
                "routers.billing.create_checkout_session",
                new_callable=AsyncMock,
                return_value=service_result,
            ) as mock_create,
        ):
            resp = client.post(
                "/billing/checkout/preservation", json={"persona_id": _PERSONA_ID}
            )
        assert resp.status_code == 200
        assert resp.json()["checkout_url"] == _CHECKOUT_URL
        # Verify mode=payment and purchase_type were passed
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["mode"] == "payment"
        assert call_kwargs["extra_metadata"]["purchase_type"] == "preservation"
        assert call_kwargs["extra_metadata"]["persona_id"] == _PERSONA_ID

    def test_missing_posthumous_price_returns_500(self):
        client = _make_client()
        mock_settings = MagicMock()
        mock_settings.stripe_price_posthumous_monthly = ""
        with patch("routers.billing.settings", mock_settings):
            resp = client.post(
                "/billing/checkout/posthumous", json={"persona_id": _PERSONA_ID}
            )
        assert resp.status_code == 500

    def test_posthumous_checkout_valid_returns_200(self):
        client = _make_client()
        mock_settings = MagicMock()
        mock_settings.stripe_price_posthumous_monthly = _POSTHUMOUS_PRICE
        mock_settings.frontend_billing_success_url = "http://localhost/success"
        mock_settings.frontend_billing_cancel_url = "http://localhost/cancel"
        service_result = {"checkout_url": _CHECKOUT_URL, "session_id": _SESSION_ID}
        with (
            patch("routers.billing.settings", mock_settings),
            patch("routers.billing.get_db", return_value=MagicMock()),
            patch(
                "routers.billing.create_checkout_session",
                new_callable=AsyncMock,
                return_value=service_result,
            ) as mock_create,
        ):
            resp = client.post(
                "/billing/checkout/posthumous", json={"persona_id": _PERSONA_ID}
            )
        assert resp.status_code == 200
        call_kwargs = mock_create.call_args[1]
        assert call_kwargs["mode"] == "subscription"
        assert call_kwargs["extra_metadata"]["purchase_type"] == "posthumous_access"

    def test_preservation_status_endpoint_returns_flags(self):
        client = _make_client()
        pres = PersonaPreservation(**_preservation_row(status="paid"))
        sub = PosthumousAccessSubscription(**_posthumous_row(status="active"))
        with (
            patch("routers.billing.get_db", return_value=MagicMock()),
            patch(
                "routers.billing.get_preservation_for_persona",
                new_callable=AsyncMock,
                return_value=pres,
            ),
            patch(
                "routers.billing.get_posthumous_subscription",
                new_callable=AsyncMock,
                return_value=sub,
            ),
        ):
            resp = client.get(f"/billing/preservation/{_PERSONA_ID}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["preservation_locked"] is True
        assert data["can_use_posthumous_chat"] is True

    def test_preservation_status_no_purchase_returns_false_flags(self):
        client = _make_client()
        with (
            patch("routers.billing.get_db", return_value=MagicMock()),
            patch(
                "routers.billing.get_preservation_for_persona",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch(
                "routers.billing.get_posthumous_subscription",
                new_callable=AsyncMock,
                return_value=None,
            ),
        ):
            resp = client.get(f"/billing/preservation/{_PERSONA_ID}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["preservation_locked"] is False
        assert data["can_use_posthumous_chat"] is False
