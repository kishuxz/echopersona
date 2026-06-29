"""Tests for Slice 10 — Email + Invite Flow.

asyncio.run() drives async cases — no pytest-asyncio needed.

Coverage:
  invite_store:
    - create_invite writes correct row
    - get_invites_for_persona returns rows
    - get_invite_by_id returns None when caller is not the owner
    - get_invite_by_token returns None for unknown token
    - revoke_invite sets status=revoked
    - accept_invite happy path: marks accepted + upserts persona_relationships
    - accept_invite rejects already-accepted invite
    - accept_invite rejects expired invite
    - accept_invite rejects revoked invite
    - count_accepted_members returns correct count

  email service:
    - send_invite_email returns False when RESEND_API_KEY is absent
    - send_invite_email calls Resend with correct payload when key is set
    - send_readiness_notification calls Resend with correct payload
    - send_acceptance_confirmation calls Resend with correct payload
    - network errors are swallowed (returns False)

  worker/tasks/email (send_readiness_emails):
    - Returns {"sent": 0} when no family members
    - Returns {"sent": N} when N members notified
    - Returns {"sent": 0} when persona not found
    - Exceptions are swallowed

  entitlement gate (unit, no DB):
    - free tier denied
    - creator under limit allowed
    - creator at limit denied
    - legacy unlimited
"""
import asyncio
import secrets
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

# ── Fixtures ──────────────────────────────────────────────────────────────────

_PERSONA_ID = "persona-invite-test"
_OWNER_ID = "owner-invite-test"
_MEMBER_ID = "member-invite-test"
_INVITE_ID = "invite-id-test"
_TOKEN = secrets.token_urlsafe(32)
_FUTURE = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
_PAST = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()


def _invite_row(status="pending", accepted_at=None, expires_at=None):
    return {
        "id": _INVITE_ID,
        "persona_id": _PERSONA_ID,
        "invited_by": _OWNER_ID,
        "email": "family@example.com",
        "relationship": "son",
        "entity_canonical": "John",
        "address_term": "Dad",
        "token": _TOKEN,
        "status": status,
        "expires_at": expires_at or _FUTURE,
        "accepted_at": accepted_at,
        "listener_user_id": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }


# ── invite_store tests ────────────────────────────────────────────────────────

class TestInviteStore:
    def test_is_expired_past(self):
        from services.invite_store import _is_expired
        assert _is_expired(_PAST) is True

    def test_is_expired_future(self):
        from services.invite_store import _is_expired
        assert _is_expired(_FUTURE) is False

    def test_create_invite_calls_db(self):
        from services import invite_store

        mock_db = MagicMock()
        mock_db.table.return_value.insert.return_value.execute.return_value.data = [
            _invite_row()
        ]

        with patch("services.invite_store.get_db", return_value=mock_db):
            row = asyncio.run(invite_store.create_invite(
                persona_id=_PERSONA_ID,
                invited_by=_OWNER_ID,
                email="family@example.com",
                relationship="son",
                entity_canonical="John",
                address_term="Dad",
            ))

        assert row["persona_id"] == _PERSONA_ID
        assert row["status"] == "pending"
        mock_db.table.return_value.insert.assert_called_once()

    def test_get_invites_for_persona_returns_list(self):
        from services import invite_store

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.order.return_value.execute.return_value.data = [
            _invite_row()
        ]

        with patch("services.invite_store.get_db", return_value=mock_db):
            rows = asyncio.run(invite_store.get_invites_for_persona(_PERSONA_ID))

        assert len(rows) == 1

    def test_get_invite_by_id_not_found_returns_none(self):
        from services import invite_store

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = None

        with patch("services.invite_store.get_db", return_value=mock_db):
            result = asyncio.run(invite_store.get_invite_by_id(_INVITE_ID, "wrong-owner"))

        assert result is None

    def test_get_invite_by_token_unknown(self):
        from services import invite_store

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = None

        with patch("services.invite_store.get_db", return_value=mock_db):
            result = asyncio.run(invite_store.get_invite_by_token("nonexistent-token"))

        assert result is None

    def test_revoke_invite_calls_update(self):
        from services import invite_store

        mock_db = MagicMock()

        with patch("services.invite_store.get_db", return_value=mock_db):
            asyncio.run(invite_store.revoke_invite(_INVITE_ID))

        mock_db.table.return_value.update.assert_called_once_with({"status": "revoked"})

    def test_accept_invite_happy_path(self):
        from services import invite_store

        invite = _invite_row()
        mock_db = MagicMock()

        with (
            patch("services.invite_store.get_invite_by_token", return_value=invite),
            patch("services.invite_store.get_db", return_value=mock_db),
        ):
            result = asyncio.run(invite_store.accept_invite(_TOKEN, _MEMBER_ID))

        assert result is not None
        assert result["persona_id"] == _PERSONA_ID
        assert result["relationship"] == "son"
        mock_db.table.return_value.update.assert_called_once()
        mock_db.table.return_value.upsert.assert_called_once()

    def test_accept_invite_already_accepted(self):
        from services import invite_store

        invite = _invite_row(status="accepted", accepted_at=datetime.now(timezone.utc).isoformat())

        with patch("services.invite_store.get_invite_by_token", return_value=invite):
            result = asyncio.run(invite_store.accept_invite(_TOKEN, _MEMBER_ID))

        assert result is None

    def test_accept_invite_expired(self):
        from services import invite_store

        invite = _invite_row(expires_at=_PAST)

        with patch("services.invite_store.get_invite_by_token", return_value=invite):
            result = asyncio.run(invite_store.accept_invite(_TOKEN, _MEMBER_ID))

        assert result is None

    def test_accept_invite_revoked(self):
        from services import invite_store

        invite = _invite_row(status="revoked")

        with patch("services.invite_store.get_invite_by_token", return_value=invite):
            result = asyncio.run(invite_store.accept_invite(_TOKEN, _MEMBER_ID))

        assert result is None

    def test_count_accepted_members(self):
        from services import invite_store

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value.count = 3

        with patch("services.invite_store.get_db", return_value=mock_db):
            count = asyncio.run(invite_store.count_accepted_members(_PERSONA_ID))

        assert count == 3


# ── email service tests ───────────────────────────────────────────────────────

class TestEmailService:
    def test_send_invite_no_api_key_returns_false(self):
        from services import email as email_svc

        with patch("services.email.settings") as mock_settings:
            mock_settings.resend_api_key = ""
            result = asyncio.run(email_svc.send_invite_email(
                to_email="test@example.com",
                inviter_name="Alice",
                persona_name="Bob",
                token="tok123",
            ))

        assert result is False

    def test_send_invite_email_calls_resend(self):
        from services import email as email_svc

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with (
            patch("services.email.settings") as mock_settings,
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_settings.resend_api_key = "re_test_key"
            mock_settings.resend_from_address = "noreply@test.com"
            mock_settings.public_base_url = "https://app.test"

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = asyncio.run(email_svc.send_invite_email(
                to_email="family@example.com",
                inviter_name="Alice",
                persona_name="Bob",
                token="testtoken",
            ))

        assert result is True
        call_args = mock_client.post.call_args
        payload = call_args[1].get("json") or call_args[0][1]
        assert payload["to"] == ["family@example.com"]
        assert "testtoken" in payload["text"]

    def test_send_readiness_notification_calls_resend(self):
        from services import email as email_svc

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with (
            patch("services.email.settings") as mock_settings,
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_settings.resend_api_key = "re_test_key"
            mock_settings.resend_from_address = "noreply@test.com"
            mock_settings.public_base_url = "https://app.test"

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = asyncio.run(email_svc.send_readiness_notification(
                to_email="family@example.com",
                persona_name="Bob",
                persona_id=_PERSONA_ID,
            ))

        assert result is True
        call_args = mock_client.post.call_args
        payload = call_args[1].get("json") or call_args[0][1]
        assert _PERSONA_ID in payload["text"]

    def test_send_acceptance_confirmation_calls_resend(self):
        from services import email as email_svc

        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        with (
            patch("services.email.settings") as mock_settings,
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_settings.resend_api_key = "re_test_key"
            mock_settings.resend_from_address = "noreply@test.com"
            mock_settings.public_base_url = "https://app.test"

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            result = asyncio.run(email_svc.send_acceptance_confirmation(
                to_email="owner@example.com",
                persona_name="Bob",
                member_email="family@example.com",
            ))

        assert result is True

    def test_send_email_swallows_network_error(self):
        from services import email as email_svc

        with (
            patch("services.email.settings") as mock_settings,
            patch("httpx.AsyncClient") as mock_client_cls,
        ):
            mock_settings.resend_api_key = "re_test_key"
            mock_settings.resend_from_address = "noreply@test.com"
            mock_settings.public_base_url = "https://app.test"

            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(side_effect=Exception("network error"))
            mock_client_cls.return_value = mock_client

            result = asyncio.run(email_svc.send_invite_email(
                to_email="family@example.com",
                inviter_name="Alice",
                persona_name="Bob",
                token="testtoken",
            ))

        assert result is False


# ── worker/tasks/email tests ──────────────────────────────────────────────────

class TestSendReadinessEmailsTask:
    def test_no_members_returns_zero(self):
        from worker.tasks import email as email_task

        mock_db = MagicMock()

        def table_side_effect(tbl):
            t = MagicMock()
            if tbl == "personas":
                t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {"name": "Bob"}
            elif tbl == "persona_relationships":
                t.select.return_value.eq.return_value.execute.return_value.data = []
            return t

        mock_db.table.side_effect = table_side_effect

        with patch("worker.tasks.email.get_db", return_value=mock_db):
            result = asyncio.run(email_task.send_readiness_emails({}, _PERSONA_ID))

        assert result["sent"] == 0

    def test_sends_email_per_member(self):
        from worker.tasks import email as email_task

        mock_db = MagicMock()

        mock_user = MagicMock()
        mock_user.user.email = "member@example.com"
        mock_db.auth.admin.get_user_by_id.return_value = mock_user

        def table_side_effect(tbl):
            t = MagicMock()
            if tbl == "personas":
                t.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = {"name": "Bob"}
            elif tbl == "persona_relationships":
                t.select.return_value.eq.return_value.execute.return_value.data = [
                    {"listener_user_id": _MEMBER_ID}
                ]
            return t

        mock_db.table.side_effect = table_side_effect

        async def _mock_notify(**kwargs):
            return True

        with (
            patch("worker.tasks.email.get_db", return_value=mock_db),
            patch("worker.tasks.email.email_service.send_readiness_notification", new_callable=AsyncMock, return_value=True),
        ):
            result = asyncio.run(email_task.send_readiness_emails({}, _PERSONA_ID))

        assert result["sent"] == 1

    def test_persona_not_found_returns_zero(self):
        from worker.tasks import email as email_task

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.maybe_single.return_value.execute.return_value.data = None

        with patch("worker.tasks.email.get_db", return_value=mock_db):
            result = asyncio.run(email_task.send_readiness_emails({}, _PERSONA_ID))

        assert result["sent"] == 0

    def test_exception_is_swallowed(self):
        from worker.tasks import email as email_task

        mock_db = MagicMock()
        mock_db.table.side_effect = Exception("db down")

        with patch("worker.tasks.email.get_db", return_value=mock_db):
            result = asyncio.run(email_task.send_readiness_emails({}, _PERSONA_ID))

        assert result["sent"] == 0
        assert "error" in result


# ── entitlement gate (unit, no DB) ────────────────────────────────────────────

class TestFamilyMemberGate:
    def test_free_tier_denied(self):
        from services.entitlements import can_add_family_member
        decision = can_add_family_member(None, 0)
        assert decision.allowed is False

    def test_creator_under_limit_allowed(self):
        from models.entitlements import StripeEntitlement
        from services.entitlements import can_add_family_member

        ent = StripeEntitlement(
            id="e1",
            user_id=_OWNER_ID,
            plan_tier="creator",
            status="active",
            stripe_customer_id="cus_x",
            stripe_subscription_id="sub_x",
            current_period_end=datetime(2027, 1, 1, tzinfo=timezone.utc),
        )
        decision = can_add_family_member(ent, 2)
        assert decision.allowed is True

    def test_creator_at_limit_denied(self):
        from models.entitlements import StripeEntitlement
        from services.entitlements import can_add_family_member

        ent = StripeEntitlement(
            id="e2",
            user_id=_OWNER_ID,
            plan_tier="creator",
            status="active",
            stripe_customer_id="cus_x",
            stripe_subscription_id="sub_x",
            current_period_end=datetime(2027, 1, 1, tzinfo=timezone.utc),
        )
        decision = can_add_family_member(ent, 3)
        assert decision.allowed is False

    def test_legacy_unlimited(self):
        from models.entitlements import StripeEntitlement
        from services.entitlements import can_add_family_member

        ent = StripeEntitlement(
            id="e3",
            user_id=_OWNER_ID,
            plan_tier="legacy",
            status="active",
            stripe_customer_id="cus_x",
            stripe_subscription_id="sub_x",
            current_period_end=datetime(2027, 1, 1, tzinfo=timezone.utc),
        )
        decision = can_add_family_member(ent, 999)
        assert decision.allowed is True
