"""Tests for services/listener.py — live-path access resolution (spec §8.1.2, §9.3).

Coverage:
  - No consent record → denied
  - text_twin=False → denied
  - Owner with active consent → granted, is_owner=True
  - Owner modalities reflected verbatim from consent record
  - Beneficiary with immediate activation → granted, is_owner=False, fields populated
  - Beneficiary with posthumous_verified → denied
  - Stranger not in succession beneficiaries → denied
  - No succession record for non-owner → denied

All DB calls are mocked — no Supabase, no network.
"""
import asyncio
from unittest.mock import MagicMock

from models.consent import ListenerContext
from services.listener import resolve_listener_context

# ── Constants ──────────────────────────────────────────────────────────────────

_PERSONA_ID = "persona-abc"
_OWNER_ID = "owner-user"
_BENEFICIARY_ID = "beneficiary-user"
_STRANGER_ID = "stranger-user"
_CAPTURED_AT = "2026-06-17T00:00:00+00:00"

_CONSENT_ROW_FULL = {
    "id": "consent-1",
    "persona_id": _PERSONA_ID,
    "subject_user_id": _OWNER_ID,
    "captured_at": _CAPTURED_AT,
    "status": "active",
    "ended_at": None,
    "supersedes": None,
    "consent_version": 1,
    "policy_version": "1",
    "modality_consent": {"voice_clone": True, "video_avatar": True, "text_twin": True},
    "rights": {"subject_may_delete": True, "subject_may_review": True},
    "affirmation_media_ref": None,
}

_CONSENT_ROW_NO_VOICE = {
    **_CONSENT_ROW_FULL,
    "modality_consent": {"voice_clone": False, "video_avatar": False, "text_twin": True},
}

_CONSENT_ROW_NO_TEXT = {
    **_CONSENT_ROW_FULL,
    "modality_consent": {"voice_clone": True, "video_avatar": True, "text_twin": False},
}

_PERSONA_ROW = {"user_id": _OWNER_ID}

_BENEFICIARY_IMMEDIATE = {
    "user_id": _BENEFICIARY_ID,
    "relationship": "daughter",
    "address_term": "kiddo",
    "scope": "full",
    "activation_trigger": "immediate",
    "release_messages": [],
}

_BENEFICIARY_POSTHUMOUS = {
    **_BENEFICIARY_IMMEDIATE,
    "activation_trigger": "posthumous_verified",
}

_SUCCESSION_WITH_IMMEDIATE = {"beneficiaries": [_BENEFICIARY_IMMEDIATE]}
_SUCCESSION_WITH_POSTHUMOUS = {"beneficiaries": [_BENEFICIARY_POSTHUMOUS]}


# ── DB mock helper (matches test_consent.py pattern) ──────────────────────────

def _make_db(execute_returns: list) -> MagicMock:
    """Build a mock Supabase client whose sequential .execute() calls return items in order."""
    q = MagicMock()
    q.select.return_value = q
    q.eq.return_value = q
    q.maybe_single.return_value = q
    q.execute.side_effect = [MagicMock(data=d) for d in execute_returns]
    db = MagicMock()
    db.table.return_value = q
    return db


# ═══════════════════════════════════════════════════════════════════════════════
# Consent gate (Gate 1)
# ═══════════════════════════════════════════════════════════════════════════════

class TestConsentGate:

    def test_no_consent_record_denies(self):
        db = _make_db([None])
        result = asyncio.run(resolve_listener_context(db, _PERSONA_ID, _OWNER_ID))
        assert result is None

    def test_text_twin_false_denies(self):
        db = _make_db([_CONSENT_ROW_NO_TEXT])
        result = asyncio.run(resolve_listener_context(db, _PERSONA_ID, _OWNER_ID))
        assert result is None


# ═══════════════════════════════════════════════════════════════════════════════
# Owner access (Gate 2)
# ═══════════════════════════════════════════════════════════════════════════════

class TestOwnerAccess:

    def test_owner_with_full_consent_granted(self):
        # consent ok → persona.user_id matches → granted as owner
        db = _make_db([_CONSENT_ROW_FULL, _PERSONA_ROW])
        result = asyncio.run(resolve_listener_context(db, _PERSONA_ID, _OWNER_ID))
        assert isinstance(result, ListenerContext)
        assert result.is_owner is True
        assert result.listener_user_id == _OWNER_ID
        assert result.relationship is None
        assert result.address_term is None
        assert result.scope is None

    def test_owner_modalities_match_consent(self):
        # voice_clone=False in consent → reflected in ListenerContext
        db = _make_db([_CONSENT_ROW_NO_VOICE, _PERSONA_ROW])
        result = asyncio.run(resolve_listener_context(db, _PERSONA_ID, _OWNER_ID))
        assert result is not None
        assert result.is_owner is True
        assert result.allowed_modalities.voice_clone is False
        assert result.allowed_modalities.video_avatar is False
        assert result.allowed_modalities.text_twin is True


# ═══════════════════════════════════════════════════════════════════════════════
# Beneficiary access (Gate 3)
# ═══════════════════════════════════════════════════════════════════════════════

class TestBeneficiaryAccess:

    def test_immediate_beneficiary_granted(self):
        # consent ok → not owner → succession has immediate beneficiary → granted
        db = _make_db([_CONSENT_ROW_FULL, _PERSONA_ROW, _SUCCESSION_WITH_IMMEDIATE])
        result = asyncio.run(resolve_listener_context(db, _PERSONA_ID, _BENEFICIARY_ID))
        assert isinstance(result, ListenerContext)
        assert result.is_owner is False
        assert result.listener_user_id == _BENEFICIARY_ID
        assert result.relationship == "daughter"
        assert result.address_term == "kiddo"
        assert result.scope == "full"
        assert result.allowed_modalities.text_twin is True

    def test_immediate_beneficiary_modalities_from_consent(self):
        # beneficiary inherits consent modalities, not their own
        db = _make_db([_CONSENT_ROW_NO_VOICE, _PERSONA_ROW, _SUCCESSION_WITH_IMMEDIATE])
        result = asyncio.run(resolve_listener_context(db, _PERSONA_ID, _BENEFICIARY_ID))
        assert result is not None
        assert result.allowed_modalities.voice_clone is False
        assert result.allowed_modalities.video_avatar is False

    def test_posthumous_verified_beneficiary_denied(self):
        # found in succession but activation_trigger=posthumous_verified → denied
        db = _make_db([_CONSENT_ROW_FULL, _PERSONA_ROW, _SUCCESSION_WITH_POSTHUMOUS])
        result = asyncio.run(resolve_listener_context(db, _PERSONA_ID, _BENEFICIARY_ID))
        assert result is None

    def test_stranger_not_in_succession_denied(self):
        # user_id not in beneficiaries list → denied
        db = _make_db([_CONSENT_ROW_FULL, _PERSONA_ROW, _SUCCESSION_WITH_IMMEDIATE])
        result = asyncio.run(resolve_listener_context(db, _PERSONA_ID, _STRANGER_ID))
        assert result is None

    def test_no_succession_record_denies_non_owner(self):
        # no succession record at all → non-owner denied
        db = _make_db([_CONSENT_ROW_FULL, _PERSONA_ROW, None])
        result = asyncio.run(resolve_listener_context(db, _PERSONA_ID, _STRANGER_ID))
        assert result is None

    def test_empty_beneficiaries_list_denies(self):
        # succession record exists but beneficiaries=[] → denied
        db = _make_db([_CONSENT_ROW_FULL, _PERSONA_ROW, {"beneficiaries": []}])
        result = asyncio.run(resolve_listener_context(db, _PERSONA_ID, _BENEFICIARY_ID))
        assert result is None
