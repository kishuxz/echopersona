"""Tests for build step 7 — Slice C: billing checkout route and service.

Coverage (route layer):
  - Unauthenticated request is rejected (401 or 422)
  - Invalid plan_tier ("free", "premium", missing) → 422
  - Missing price config → 500
  - creator tier maps to STRIPE_PRICE_CREATOR_MONTHLY (not client-supplied)
  - legacy tier maps to STRIPE_PRICE_LEGACY_MONTHLY (not client-supplied)
  - Client-supplied price_id in body is silently ignored
  - Response shape: checkout_url + session_id

Coverage (service layer):
  - Creates new Stripe customer when no entitlement row exists
  - Reuses stripe_customer_id from existing entitlement row (no duplicate customer)
  - Checkout session created with mode=subscription, correct line_items, URLs
  - Returns checkout_url and session_id

All Stripe and DB calls are mocked — no real network.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from middleware.auth import get_current_user
from routers.billing import router as billing_router

# ── Constants ──────────────────────────────────────────────────────────────────

_USER_ID = "user-checkout-abc"
_CUSTOMER_ID = "cus_test_abc"
_SESSION_ID = "cs_test_abc"
_CHECKOUT_URL = "https://checkout.stripe.com/test_session"
_CREATOR_PRICE = "price_creator_test_monthly"
_LEGACY_PRICE = "price_legacy_test_monthly"
_SUCCESS_URL = "http://localhost:5173/billing/success"
_CANCEL_URL = "http://localhost:5173/billing/cancel"

_MOCK_SERVICE_RESULT = {"checkout_url": _CHECKOUT_URL, "session_id": _SESSION_ID}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_client(with_auth: bool = True) -> TestClient:
    app = FastAPI()
    app.include_router(billing_router)
    if with_auth:
        app.dependency_overrides[get_current_user] = lambda: _USER_ID
    return TestClient(app, raise_server_exceptions=True)


def _mock_settings(creator_price: str = _CREATOR_PRICE, legacy_price: str = _LEGACY_PRICE) -> MagicMock:
    m = MagicMock()
    m.stripe_price_creator_monthly = creator_price
    m.stripe_price_legacy_monthly = legacy_price
    m.frontend_billing_success_url = _SUCCESS_URL
    m.frontend_billing_cancel_url = _CANCEL_URL
    return m


def _mock_stripe_customer(customer_id: str = _CUSTOMER_ID) -> MagicMock:
    c = MagicMock()
    c.id = customer_id
    return c


def _mock_stripe_session() -> MagicMock:
    s = MagicMock()
    s.url = _CHECKOUT_URL
    s.id = _SESSION_ID
    return s


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Route layer
# ═══════════════════════════════════════════════════════════════════════════════

class TestCheckoutRoute:

    def test_unauthenticated_request_rejected(self):
        """No auth dependency override and no Authorization header → rejected."""
        client = _make_client(with_auth=False)
        resp = client.post("/billing/checkout", json={"plan_tier": "creator"})
        assert resp.status_code in (401, 422)

    def test_invalid_tier_free_returns_422(self):
        """'free' is not in Literal["creator", "legacy"] → Pydantic 422."""
        client = _make_client()
        resp = client.post("/billing/checkout", json={"plan_tier": "free"})
        assert resp.status_code == 422

    def test_invalid_tier_unknown_returns_422(self):
        client = _make_client()
        resp = client.post("/billing/checkout", json={"plan_tier": "premium"})
        assert resp.status_code == 422

    def test_missing_plan_tier_returns_422(self):
        client = _make_client()
        resp = client.post("/billing/checkout", json={})
        assert resp.status_code == 422

    def test_missing_price_config_returns_500(self):
        """Empty price ID in settings → 500 before Stripe is called."""
        client = _make_client()
        with patch("routers.billing.settings", _mock_settings(creator_price="")):
            resp = client.post("/billing/checkout", json={"plan_tier": "creator"})
        assert resp.status_code == 500

    def test_missing_legacy_price_config_returns_500(self):
        client = _make_client()
        with patch("routers.billing.settings", _mock_settings(legacy_price="")):
            resp = client.post("/billing/checkout", json={"plan_tier": "legacy"})
        assert resp.status_code == 500

    def test_creator_maps_to_creator_price(self):
        client = _make_client()
        with patch("routers.billing.settings", _mock_settings()), \
             patch("routers.billing.create_checkout_session", new_callable=AsyncMock) as mock_svc:
            mock_svc.return_value = _MOCK_SERVICE_RESULT
            resp = client.post("/billing/checkout", json={"plan_tier": "creator"})

        assert resp.status_code == 200
        assert mock_svc.call_args.kwargs["price_id"] == _CREATOR_PRICE

    def test_legacy_maps_to_legacy_price(self):
        client = _make_client()
        with patch("routers.billing.settings", _mock_settings()), \
             patch("routers.billing.create_checkout_session", new_callable=AsyncMock) as mock_svc:
            mock_svc.return_value = _MOCK_SERVICE_RESULT
            resp = client.post("/billing/checkout", json={"plan_tier": "legacy"})

        assert resp.status_code == 200
        assert mock_svc.call_args.kwargs["price_id"] == _LEGACY_PRICE

    def test_client_cannot_inject_price_id(self):
        """Extra body field 'price_id' is ignored; server-side mapping always wins."""
        client = _make_client()
        with patch("routers.billing.settings", _mock_settings()), \
             patch("routers.billing.create_checkout_session", new_callable=AsyncMock) as mock_svc:
            mock_svc.return_value = _MOCK_SERVICE_RESULT
            resp = client.post(
                "/billing/checkout",
                json={"plan_tier": "creator", "price_id": "price_attacker_9999"},
            )

        assert resp.status_code == 200
        used_price = mock_svc.call_args.kwargs["price_id"]
        assert used_price == _CREATOR_PRICE
        assert used_price != "price_attacker_9999"

    def test_response_shape(self):
        client = _make_client()
        with patch("routers.billing.settings", _mock_settings()), \
             patch("routers.billing.create_checkout_session", new_callable=AsyncMock) as mock_svc:
            mock_svc.return_value = _MOCK_SERVICE_RESULT
            resp = client.post("/billing/checkout", json={"plan_tier": "creator"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["checkout_url"] == _CHECKOUT_URL
        assert data["session_id"] == _SESSION_ID

    def test_service_receives_user_id(self):
        client = _make_client()
        with patch("routers.billing.settings", _mock_settings()), \
             patch("routers.billing.create_checkout_session", new_callable=AsyncMock) as mock_svc:
            mock_svc.return_value = _MOCK_SERVICE_RESULT
            client.post("/billing/checkout", json={"plan_tier": "legacy"})

        assert mock_svc.call_args.kwargs["user_id"] == _USER_ID


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Service layer
# ═══════════════════════════════════════════════════════════════════════════════

class TestCreateCheckoutSessionService:

    def test_creates_new_stripe_customer_when_no_entitlement(self):
        """No existing entitlement → stripe.Customer.create called with supabase_user_id metadata."""
        from services.billing import create_checkout_session

        with patch("services.billing.get_entitlement_for_user", new_callable=AsyncMock, return_value=None), \
             patch("stripe.Customer.create", return_value=_mock_stripe_customer()) as mock_cust, \
             patch("stripe.checkout.Session.create", return_value=_mock_stripe_session()):

            asyncio.run(create_checkout_session(
                db=MagicMock(),
                user_id=_USER_ID,
                price_id=_CREATOR_PRICE,
                success_url=_SUCCESS_URL,
                cancel_url=_CANCEL_URL,
            ))

        mock_cust.assert_called_once_with(metadata={"supabase_user_id": _USER_ID})

    def test_reuses_existing_stripe_customer_id(self):
        """Existing entitlement with customer_id → no new customer created."""
        from services.billing import create_checkout_session
        from models.entitlements import StripeEntitlement

        existing = StripeEntitlement(
            id="ent-uuid",
            user_id=_USER_ID,
            stripe_customer_id=_CUSTOMER_ID,
            plan_tier="creator",
            status="active",
        )

        with patch("services.billing.get_entitlement_for_user", new_callable=AsyncMock, return_value=existing), \
             patch("stripe.Customer.create") as mock_cust_create, \
             patch("stripe.checkout.Session.create", return_value=_mock_stripe_session()) as mock_sess:

            asyncio.run(create_checkout_session(
                db=MagicMock(),
                user_id=_USER_ID,
                price_id=_CREATOR_PRICE,
                success_url=_SUCCESS_URL,
                cancel_url=_CANCEL_URL,
            ))

        mock_cust_create.assert_not_called()
        assert mock_sess.call_args.kwargs["customer"] == _CUSTOMER_ID

    def test_checkout_session_mode_is_subscription(self):
        from services.billing import create_checkout_session

        with patch("services.billing.get_entitlement_for_user", new_callable=AsyncMock, return_value=None), \
             patch("stripe.Customer.create", return_value=_mock_stripe_customer()), \
             patch("stripe.checkout.Session.create", return_value=_mock_stripe_session()) as mock_sess:

            asyncio.run(create_checkout_session(
                db=MagicMock(),
                user_id=_USER_ID,
                price_id=_CREATOR_PRICE,
                success_url=_SUCCESS_URL,
                cancel_url=_CANCEL_URL,
            ))

        kwargs = mock_sess.call_args.kwargs
        assert kwargs["mode"] == "subscription"

    def test_checkout_session_line_items(self):
        from services.billing import create_checkout_session

        with patch("services.billing.get_entitlement_for_user", new_callable=AsyncMock, return_value=None), \
             patch("stripe.Customer.create", return_value=_mock_stripe_customer()), \
             patch("stripe.checkout.Session.create", return_value=_mock_stripe_session()) as mock_sess:

            asyncio.run(create_checkout_session(
                db=MagicMock(),
                user_id=_USER_ID,
                price_id=_CREATOR_PRICE,
                success_url=_SUCCESS_URL,
                cancel_url=_CANCEL_URL,
            ))

        kwargs = mock_sess.call_args.kwargs
        assert kwargs["line_items"] == [{"price": _CREATOR_PRICE, "quantity": 1}]
        assert kwargs["success_url"] == _SUCCESS_URL
        assert kwargs["cancel_url"] == _CANCEL_URL

    def test_checkout_session_includes_user_metadata(self):
        from services.billing import create_checkout_session

        with patch("services.billing.get_entitlement_for_user", new_callable=AsyncMock, return_value=None), \
             patch("stripe.Customer.create", return_value=_mock_stripe_customer()), \
             patch("stripe.checkout.Session.create", return_value=_mock_stripe_session()) as mock_sess:

            asyncio.run(create_checkout_session(
                db=MagicMock(),
                user_id=_USER_ID,
                price_id=_CREATOR_PRICE,
                success_url=_SUCCESS_URL,
                cancel_url=_CANCEL_URL,
            ))

        assert mock_sess.call_args.kwargs["metadata"]["supabase_user_id"] == _USER_ID

    def test_returns_checkout_url_and_session_id(self):
        from services.billing import create_checkout_session

        with patch("services.billing.get_entitlement_for_user", new_callable=AsyncMock, return_value=None), \
             patch("stripe.Customer.create", return_value=_mock_stripe_customer()), \
             patch("stripe.checkout.Session.create", return_value=_mock_stripe_session()):

            result = asyncio.run(create_checkout_session(
                db=MagicMock(),
                user_id=_USER_ID,
                price_id=_CREATOR_PRICE,
                success_url=_SUCCESS_URL,
                cancel_url=_CANCEL_URL,
            ))

        assert result["checkout_url"] == _CHECKOUT_URL
        assert result["session_id"] == _SESSION_ID
