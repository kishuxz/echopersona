"""Tests for build step 7 — Slice E: GET /billing/status endpoint.

Coverage:
  - Unauthenticated request rejected (401 or 422)
  - No entitlement row → free tier defaults, all paid access false
  - Active creator entitlement → can_use_chat/voice true, video false
  - Active legacy entitlement → can_use_chat/voice/video true
  - Canceled entitlement → all paid access false
  - Unpaid entitlement → all paid access false
  - Past-due entitlement → all paid access false
  - Response never includes stripe_customer_id or stripe_subscription_id
  - No Stripe API calls made

All DB calls are mocked — no real network.
"""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from middleware.auth import get_current_user
from models.entitlements import StripeEntitlement
from routers.billing import router as billing_router

# ── Constants ──────────────────────────────────────────────────────────────────

_USER_ID = "user-status-abc"
_CUSTOMER_ID = "cus_status_test"
_SUB_ID = "sub_status_test"
_PERIOD_END = datetime(2026, 1, 1, tzinfo=timezone.utc)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_client(with_auth: bool = True) -> TestClient:
    app = FastAPI()
    app.include_router(billing_router)
    if with_auth:
        app.dependency_overrides[get_current_user] = lambda: _USER_ID
    return TestClient(app, raise_server_exceptions=True)


def _make_entitlement(
    plan_tier: str = "creator",
    status: str = "active",
) -> StripeEntitlement:
    return StripeEntitlement(
        id="ent-uuid",
        user_id=_USER_ID,
        stripe_customer_id=_CUSTOMER_ID,
        stripe_subscription_id=_SUB_ID,
        plan_tier=plan_tier,
        status=status,
        cancel_at_period_end=False,
        current_period_end=_PERIOD_END,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Auth
# ═══════════════════════════════════════════════════════════════════════════════

class TestBillingStatusAuth:

    def test_unauthenticated_request_rejected(self):
        """No auth override + no Authorization header → rejected (401 or 422)."""
        client = _make_client(with_auth=False)
        resp = client.get("/billing/status")
        assert resp.status_code in (401, 422)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Free-tier defaults
# ═══════════════════════════════════════════════════════════════════════════════

class TestBillingStatusNoEntitlement:

    def test_no_row_returns_free_tier(self):
        client = _make_client()
        with patch("routers.billing.get_entitlement_for_user", new_callable=AsyncMock, return_value=None):
            resp = client.get("/billing/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["plan_tier"] == "free"
        assert data["status"] is None

    def test_no_row_all_paid_access_false(self):
        client = _make_client()
        with patch("routers.billing.get_entitlement_for_user", new_callable=AsyncMock, return_value=None):
            resp = client.get("/billing/status")
        data = resp.json()
        assert data["can_use_chat"] is True   # chat is always free
        assert data["can_use_voice"] is False
        assert data["can_use_video"] is False

    def test_no_row_period_end_and_cancel_are_null_false(self):
        client = _make_client()
        with patch("routers.billing.get_entitlement_for_user", new_callable=AsyncMock, return_value=None):
            resp = client.get("/billing/status")
        data = resp.json()
        assert data["current_period_end"] is None
        assert data["cancel_at_period_end"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Active creator
# ═══════════════════════════════════════════════════════════════════════════════

class TestBillingStatusCreator:

    def test_active_creator_tier_and_status(self):
        client = _make_client()
        ent = _make_entitlement(plan_tier="creator", status="active")
        with patch("routers.billing.get_entitlement_for_user", new_callable=AsyncMock, return_value=ent):
            resp = client.get("/billing/status")
        data = resp.json()
        assert data["plan_tier"] == "creator"
        assert data["status"] == "active"

    def test_active_creator_access_flags(self):
        client = _make_client()
        ent = _make_entitlement(plan_tier="creator", status="active")
        with patch("routers.billing.get_entitlement_for_user", new_callable=AsyncMock, return_value=ent):
            resp = client.get("/billing/status")
        data = resp.json()
        assert data["can_use_chat"] is True
        assert data["can_use_voice"] is True
        assert data["can_use_video"] is False  # creator does not include video


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Active legacy
# ═══════════════════════════════════════════════════════════════════════════════

class TestBillingStatusLegacy:

    def test_active_legacy_all_access_true(self):
        client = _make_client()
        ent = _make_entitlement(plan_tier="legacy", status="active")
        with patch("routers.billing.get_entitlement_for_user", new_callable=AsyncMock, return_value=ent):
            resp = client.get("/billing/status")
        data = resp.json()
        assert data["plan_tier"] == "legacy"
        assert data["can_use_chat"] is True
        assert data["can_use_voice"] is True
        assert data["can_use_video"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# 5. Non-active statuses deny paid access
# ═══════════════════════════════════════════════════════════════════════════════

class TestBillingStatusDeniedAccess:

    def _assert_paid_access_denied(self, status: str):
        client = _make_client()
        ent = _make_entitlement(plan_tier="creator", status=status)
        with patch("routers.billing.get_entitlement_for_user", new_callable=AsyncMock, return_value=ent):
            resp = client.get("/billing/status")
        data = resp.json()
        assert data["can_use_voice"] is False, f"status={status} should deny voice"
        assert data["can_use_video"] is False, f"status={status} should deny video"

    def test_canceled_denies_paid_access(self):
        self._assert_paid_access_denied("canceled")

    def test_unpaid_denies_paid_access(self):
        self._assert_paid_access_denied("unpaid")

    def test_past_due_denies_paid_access(self):
        self._assert_paid_access_denied("past_due")


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Response shape — no Stripe IDs exposed
# ═══════════════════════════════════════════════════════════════════════════════

class TestBillingStatusResponseShape:

    def test_response_does_not_expose_stripe_customer_id(self):
        client = _make_client()
        ent = _make_entitlement()
        with patch("routers.billing.get_entitlement_for_user", new_callable=AsyncMock, return_value=ent):
            resp = client.get("/billing/status")
        assert "stripe_customer_id" not in resp.json()

    def test_response_does_not_expose_stripe_subscription_id(self):
        client = _make_client()
        ent = _make_entitlement()
        with patch("routers.billing.get_entitlement_for_user", new_callable=AsyncMock, return_value=ent):
            resp = client.get("/billing/status")
        assert "stripe_subscription_id" not in resp.json()

    def test_no_stripe_api_calls_made(self):
        """Endpoint reads only from DB — zero Stripe API calls."""
        client = _make_client()
        ent = _make_entitlement()
        with patch("routers.billing.get_entitlement_for_user", new_callable=AsyncMock, return_value=ent), \
             patch("stripe.Customer.retrieve") as mock_cust, \
             patch("stripe.Subscription.retrieve") as mock_sub:
            client.get("/billing/status")
        mock_cust.assert_not_called()
        mock_sub.assert_not_called()

    def test_current_period_end_present_in_response(self):
        client = _make_client()
        ent = _make_entitlement()
        with patch("routers.billing.get_entitlement_for_user", new_callable=AsyncMock, return_value=ent):
            resp = client.get("/billing/status")
        assert resp.json()["current_period_end"] is not None
