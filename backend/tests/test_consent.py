"""Tests for build step 5b: consent capture and succession intent (spec §7.2, §7.3).

Coverage:
  - POST /personas/{id}/consent creates active consent with version=1
  - Second POST supersedes old active row; new row gets version=2
  - GET /personas/{id}/consent returns active record; 404 when absent
  - Wrong-owner or missing persona returns 404
  - POST /personas/{id}/succession creates active succession record
  - Second POST supersedes old succession row
  - GET /personas/{id}/succession returns 404 when absent
  - scope="admin" rejected by Pydantic with 422 before service is called
  - subject_user_id is always sourced from the JWT, never from the request body

All DB calls are mocked — no Supabase, no network.
"""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from middleware.auth import get_current_user
from models.consent import (
    ConsentCreate,
    ConsentRecord,
    ConsentRights,
    ModalityConsent,
    SuccessionCreate,
    SuccessionRecord,
)
from routers.consent import router as consent_router
from services.consent import write_consent_record, write_succession_record


# ── Constants ──────────────────────────────────────────────────────────────────

_USER_ID = "user-abc"
_PERSONA_ID = "persona-abc"
_OLD_CONSENT_ID = "consent-old-uuid"
_NEW_CONSENT_ID = "consent-new-uuid"
_OLD_SUCCESSION_ID = "succession-old-uuid"
_NEW_SUCCESSION_ID = "succession-new-uuid"
_CAPTURED_AT = "2026-06-17T00:00:00+00:00"

_CONSENT_PAYLOAD = {
    "modality_consent": {"voice_clone": True, "video_avatar": False, "text_twin": True},
    "rights": {"subject_may_delete": True, "subject_may_review": True},
    "policy_version": "1",
    "affirmation_media_ref": None,
}

_SUCCESSION_PAYLOAD = {
    "beneficiaries": [
        {
            "user_id": "beneficiary-user",
            "relationship": "daughter",
            "address_term": "kiddo",
            "scope": "full",
            "activation_trigger": "posthumous_verified",
            "release_messages": [],
        }
    ]
}

_SUCCESSION_PAYLOAD_ENRICHED = {
    "beneficiaries": [
        {
            "user_id": "beneficiary-user",
            "relationship": "granddaughter",
            "address_term": "Sofia dear",
            "scope": "full",
            "activation_trigger": "immediate",
            "release_messages": [],
            "closeness_level": 4,
            "greeting_style": "warm and affectionate",
        }
    ]
}

_CONSENT_ROW_V1 = {
    "id": _NEW_CONSENT_ID,
    "persona_id": _PERSONA_ID,
    "subject_user_id": _USER_ID,
    "captured_at": _CAPTURED_AT,
    "status": "active",
    "ended_at": None,
    "supersedes": None,
    "consent_version": 1,
    "policy_version": "1",
    "modality_consent": {"voice_clone": True, "video_avatar": False, "text_twin": True},
    "rights": {"subject_may_delete": True, "subject_may_review": True},
    "affirmation_media_ref": None,
}

_CONSENT_ROW_V2 = {
    **_CONSENT_ROW_V1,
    "id": _NEW_CONSENT_ID,
    "consent_version": 2,
    "supersedes": _OLD_CONSENT_ID,
}

_SUCCESSION_ROW_V1 = {
    "id": _NEW_SUCCESSION_ID,
    "persona_id": _PERSONA_ID,
    "subject_user_id": _USER_ID,
    "captured_at": _CAPTURED_AT,
    "status": "active",
    "ended_at": None,
    "supersedes": None,
    "beneficiaries": _SUCCESSION_PAYLOAD["beneficiaries"],
}

_SUCCESSION_ROW_ENRICHED = {
    **_SUCCESSION_ROW_V1,
    "beneficiaries": _SUCCESSION_PAYLOAD_ENRICHED["beneficiaries"],
}

_SUCCESSION_ROW_V2 = {
    **_SUCCESSION_ROW_V1,
    "supersedes": _OLD_SUCCESSION_ID,
}

_ACTIVE_CONSENT = ConsentRecord(
    id=_NEW_CONSENT_ID,
    persona_id=_PERSONA_ID,
    subject_user_id=_USER_ID,
    captured_at=datetime(2026, 6, 17, tzinfo=timezone.utc),
    status="active",
    ended_at=None,
    supersedes=None,
    consent_version=1,
    policy_version="1",
    modality_consent=ModalityConsent(voice_clone=True, video_avatar=False, text_twin=True),
    rights=ConsentRights(subject_may_delete=True, subject_may_review=True),
    affirmation_media_ref=None,
)

_ACTIVE_SUCCESSION = SuccessionRecord(
    id=_NEW_SUCCESSION_ID,
    persona_id=_PERSONA_ID,
    subject_user_id=_USER_ID,
    captured_at=datetime(2026, 6, 17, tzinfo=timezone.utc),
    status="active",
    ended_at=None,
    supersedes=None,
    beneficiaries=[],
)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_client() -> TestClient:
    """Build a TestClient for the consent router with auth stubbed to _USER_ID."""
    app = FastAPI()
    app.include_router(consent_router)
    app.dependency_overrides[get_current_user] = lambda: _USER_ID
    return TestClient(app, raise_server_exceptions=True)


def _make_db(execute_returns: list) -> MagicMock:
    """Build a mock Supabase client whose successive .execute() calls return items in order.

    Each item in execute_returns becomes result.data for that call.
    """
    q = MagicMock()
    q.select.return_value = q
    q.eq.return_value = q
    q.update.return_value = q
    q.insert.return_value = q
    q.maybe_single.return_value = q
    q.execute.side_effect = [MagicMock(data=d) for d in execute_returns]
    db = MagicMock()
    db.table.return_value = q
    return db


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Consent router — HTTP behaviour
# ═══════════════════════════════════════════════════════════════════════════════

class TestConsentRouter:

    def test_get_consent_returns_active(self):
        client = _make_client()
        with patch(
            "routers.consent.get_active_consent_record",
            new_callable=AsyncMock,
            return_value=_ACTIVE_CONSENT,
        ):
            resp = client.get(f"/personas/{_PERSONA_ID}/consent")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == _NEW_CONSENT_ID
        assert data["consent_version"] == 1
        assert data["status"] == "active"

    def test_get_consent_not_found(self):
        client = _make_client()
        with patch(
            "routers.consent.get_active_consent_record",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.get(f"/personas/{_PERSONA_ID}/consent")
        assert resp.status_code == 404

    def test_consent_wrong_owner_returns_404(self):
        """Service returns None when persona doesn't belong to the authenticated user."""
        client = _make_client()
        with patch(
            "routers.consent.write_consent_record",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.post(f"/personas/{_PERSONA_ID}/consent", json=_CONSENT_PAYLOAD)
        assert resp.status_code == 404

    def test_get_succession_not_found(self):
        client = _make_client()
        with patch(
            "routers.consent.get_active_succession_record",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.get(f"/personas/{_PERSONA_ID}/succession")
        assert resp.status_code == 404

    def test_succession_invalid_scope_422(self):
        """Pydantic rejects an unknown scope value before the service is called."""
        client = _make_client()
        payload = {
            "beneficiaries": [
                {
                    "user_id": "some-user",
                    "relationship": "son",
                    "scope": "admin",          # not in Literal["full", "curated"]
                    "activation_trigger": "immediate",
                }
            ]
        }
        resp = client.post(f"/personas/{_PERSONA_ID}/succession", json=payload)
        assert resp.status_code == 422

    def test_succession_wrong_owner_returns_404(self):
        """Service returns None when persona doesn't belong to the authenticated user."""
        client = _make_client()
        with patch(
            "routers.consent.write_succession_record",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.post(f"/personas/{_PERSONA_ID}/succession", json=_SUCCESSION_PAYLOAD)
        assert resp.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Consent service — write / supersede logic
# ═══════════════════════════════════════════════════════════════════════════════

class TestWriteConsentService:

    def test_write_consent_first_write(self):
        """First write: version=1, supersedes=None, subject_user_id from arg not payload."""
        db = _make_db([
            {"id": _PERSONA_ID},   # ensure_persona_owner
            None,                   # no existing active consent
            [_CONSENT_ROW_V1],     # insert returns new row
        ])
        q = db.table.return_value

        payload = ConsentCreate(**_CONSENT_PAYLOAD)
        record = asyncio.run(write_consent_record(db, _PERSONA_ID, _USER_ID, payload))

        assert record is not None
        assert record.consent_version == 1
        assert record.supersedes is None
        assert record.status == "active"

        # subject_user_id must come from the user_id argument, not the request payload
        inserted = q.insert.call_args.args[0]
        assert inserted["subject_user_id"] == _USER_ID
        assert q.execute.call_count == 3  # owner check + find existing + insert

    def test_write_consent_supersedes_old(self):
        """Second write marks old row superseded and inserts new row with version=2."""
        db = _make_db([
            {"id": _PERSONA_ID},                            # ensure_persona_owner
            {"id": _OLD_CONSENT_ID, "consent_version": 1}, # existing active found
            [],                                              # UPDATE old → superseded
            [_CONSENT_ROW_V2],                              # insert new row
        ])
        q = db.table.return_value

        payload = ConsentCreate(**_CONSENT_PAYLOAD)
        record = asyncio.run(write_consent_record(db, _PERSONA_ID, _USER_ID, payload))

        assert record is not None
        assert record.consent_version == 2
        assert record.supersedes == _OLD_CONSENT_ID
        assert record.status == "active"
        assert q.execute.call_count == 4  # owner + find + update + insert

    def test_write_consent_wrong_owner_returns_none(self):
        db = _make_db([None])  # ensure_persona_owner returns None → not owner
        payload = ConsentCreate(**_CONSENT_PAYLOAD)
        record = asyncio.run(write_consent_record(db, _PERSONA_ID, _USER_ID, payload))
        assert record is None


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Succession service — write / supersede logic
# ═══════════════════════════════════════════════════════════════════════════════

class TestWriteSuccessionService:

    def test_write_succession_first_write(self):
        """First succession write: supersedes=None, subject_user_id from arg."""
        db = _make_db([
            {"id": _PERSONA_ID},   # ensure_persona_owner
            None,                   # no existing active succession
            [_SUCCESSION_ROW_V1],  # insert result
        ])
        q = db.table.return_value

        payload = SuccessionCreate(**_SUCCESSION_PAYLOAD)
        record = asyncio.run(write_succession_record(db, _PERSONA_ID, _USER_ID, payload))

        assert record is not None
        assert record.supersedes is None
        assert record.status == "active"
        assert q.insert.call_args.args[0]["subject_user_id"] == _USER_ID
        assert q.execute.call_count == 3

    def test_write_succession_supersedes_old(self):
        """Second succession write marks old row superseded; new row points to old id."""
        db = _make_db([
            {"id": _PERSONA_ID},        # ensure_persona_owner
            {"id": _OLD_SUCCESSION_ID}, # existing active found
            [],                          # UPDATE old → superseded
            [_SUCCESSION_ROW_V2],       # insert new row
        ])
        q = db.table.return_value

        payload = SuccessionCreate(**_SUCCESSION_PAYLOAD)
        record = asyncio.run(write_succession_record(db, _PERSONA_ID, _USER_ID, payload))

        assert record is not None
        assert record.supersedes == _OLD_SUCCESSION_ID
        assert record.status == "active"
        assert q.execute.call_count == 4


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Enriched beneficiary fields — validation and JSONB write
# ═══════════════════════════════════════════════════════════════════════════════

class TestEnrichedBeneficiaryFields:

    def test_enriched_fields_reach_jsonb_insert(self):
        """closeness_level + greeting_style + address_term are serialized into the JSONB insert."""
        db = _make_db([
            {"id": _PERSONA_ID},        # ensure_persona_owner
            None,                        # no existing active succession
            [_SUCCESSION_ROW_ENRICHED], # insert result
        ])
        q = db.table.return_value

        payload = SuccessionCreate(**_SUCCESSION_PAYLOAD_ENRICHED)
        record = asyncio.run(write_succession_record(db, _PERSONA_ID, _USER_ID, payload))

        assert record is not None
        assert record.status == "active"
        inserted_ben = q.insert.call_args.args[0]["beneficiaries"][0]
        assert inserted_ben["closeness_level"] == 4
        assert inserted_ben["greeting_style"] == "warm and affectionate"
        assert inserted_ben["address_term"] == "Sofia dear"

    def test_old_payload_without_enriched_fields_accepted(self):
        """Backward compat: a payload without the new optional fields is still valid."""
        db = _make_db([
            {"id": _PERSONA_ID},
            None,
            [_SUCCESSION_ROW_V1],
        ])
        payload = SuccessionCreate(**_SUCCESSION_PAYLOAD)
        record = asyncio.run(write_succession_record(db, _PERSONA_ID, _USER_ID, payload))
        assert record is not None
        assert record.status == "active"

    def test_closeness_level_zero_rejected(self):
        """closeness_level=0 is below ge=1 — Pydantic returns 422 before the service runs."""
        client = _make_client()
        payload = {
            "beneficiaries": [{
                "user_id": "some-user",
                "relationship": "son",
                "scope": "full",
                "activation_trigger": "immediate",
                "closeness_level": 0,
            }]
        }
        resp = client.post(f"/personas/{_PERSONA_ID}/succession", json=payload)
        assert resp.status_code == 422

    def test_closeness_level_six_rejected(self):
        """closeness_level=6 exceeds le=5 — Pydantic returns 422 before the service runs."""
        client = _make_client()
        payload = {
            "beneficiaries": [{
                "user_id": "some-user",
                "relationship": "son",
                "scope": "full",
                "activation_trigger": "immediate",
                "closeness_level": 6,
            }]
        }
        resp = client.post(f"/personas/{_PERSONA_ID}/succession", json=payload)
        assert resp.status_code == 422

    def test_closeness_level_null_accepted(self):
        """closeness_level=null is valid (field is optional); 404 here means Pydantic passed."""
        client = _make_client()
        payload = {
            "beneficiaries": [{
                "user_id": "some-user",
                "relationship": "son",
                "scope": "full",
                "activation_trigger": "immediate",
                "closeness_level": None,
            }]
        }
        with patch(
            "routers.consent.write_succession_record",
            new_callable=AsyncMock,
            return_value=None,
        ):
            resp = client.post(f"/personas/{_PERSONA_ID}/succession", json=payload)
        # Service returned None → 404, but Pydantic accepted the payload (no 422)
        assert resp.status_code == 404
