"""Tests for services/listener.py and build_system_prompt listener injection (spec §8.1.2, §9.3).

Coverage:
  - No consent record → denied
  - text_twin=False → denied
  - Owner with active consent → granted, is_owner=True
  - Owner modalities reflected verbatim from consent record
  - Beneficiary with immediate activation → granted, is_owner=False, fields populated
  - Beneficiary with posthumous_verified → denied
  - Stranger not in succession beneficiaries → denied
  - No succession record for non-owner → denied
  - build_system_prompt: listener_ctx=None → prompt unchanged
  - build_system_prompt: is_owner=True → prompt unchanged
  - build_system_prompt: beneficiary → listener block appended

All DB calls are mocked — no Supabase, no network.
"""
import asyncio
from unittest.mock import MagicMock

from models.consent import ListenerContext, ModalityConsent
from services.listener import resolve_listener_context
from services.rag import build_system_prompt

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

# Enriched beneficiary row with optional relationship metadata (MVP addition)
_BENEFICIARY_ENRICHED = {
    **_BENEFICIARY_IMMEDIATE,
    "closeness_level": 4,
    "greeting_style": "warm and affectionate",
}

_SUCCESSION_WITH_IMMEDIATE = {"beneficiaries": [_BENEFICIARY_IMMEDIATE]}
_SUCCESSION_WITH_POSTHUMOUS = {"beneficiaries": [_BENEFICIARY_POSTHUMOUS]}
_SUCCESSION_WITH_ENRICHED = {"beneficiaries": [_BENEFICIARY_ENRICHED]}


# ── DB mock helpers ────────────────────────────────────────────────────────────

def _make_db(execute_returns: list) -> MagicMock:
    """Build a mock Supabase client whose sequential .execute() calls return items in order.

    Each value in execute_returns is wrapped as MagicMock(data=value), so None
    becomes MagicMock(data=None) — simulating an empty Supabase response object.
    """
    q = MagicMock()
    q.select.return_value = q
    q.eq.return_value = q
    q.maybe_single.return_value = q
    q.execute.side_effect = [MagicMock(data=d) for d in execute_returns]
    db = MagicMock()
    db.table.return_value = q
    return db


def _make_db_raw(execute_returns: list) -> MagicMock:
    """Like _make_db but returns values as-is — use to simulate Supabase returning None directly."""
    q = MagicMock()
    q.select.return_value = q
    q.eq.return_value = q
    q.maybe_single.return_value = q
    q.execute.side_effect = execute_returns
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

    def test_consent_query_returns_none_directly_denies(self):
        # Supabase returns None itself (not a response object) → no AttributeError
        db = _make_db_raw([None])
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

    def test_persona_query_returns_none_directly_denies(self):
        # Consent valid; persona query returns None → graceful denial, no AttributeError
        # Falls through to Gate 3; succession also None → denied
        db = _make_db_raw([MagicMock(data=_CONSENT_ROW_FULL), None, None])
        result = asyncio.run(resolve_listener_context(db, _PERSONA_ID, _STRANGER_ID))
        assert result is None

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

    def test_succession_query_returns_none_directly_denies(self):
        # Consent valid, not owner, succession query returns None itself → no AttributeError
        db = _make_db_raw([MagicMock(data=_CONSENT_ROW_FULL), MagicMock(data=_PERSONA_ROW), None])
        result = asyncio.run(resolve_listener_context(db, _PERSONA_ID, _STRANGER_ID))
        assert result is None

    def test_empty_beneficiaries_list_denies(self):
        # succession record exists but beneficiaries=[] → denied
        db = _make_db([_CONSENT_ROW_FULL, _PERSONA_ROW, {"beneficiaries": []}])
        result = asyncio.run(resolve_listener_context(db, _PERSONA_ID, _BENEFICIARY_ID))
        assert result is None

    def test_enriched_beneficiary_populates_new_fields(self):
        # JSONB row with closeness_level + greeting_style → fields propagate to ListenerContext
        db = _make_db([_CONSENT_ROW_FULL, _PERSONA_ROW, _SUCCESSION_WITH_ENRICHED])
        result = asyncio.run(resolve_listener_context(db, _PERSONA_ID, _BENEFICIARY_ID))
        assert result is not None
        assert result.closeness_level == 4
        assert result.greeting_style == "warm and affectionate"

    def test_old_beneficiary_row_backward_compat(self):
        # Legacy JSONB row without new optional keys → None, no KeyError
        db = _make_db([_CONSENT_ROW_FULL, _PERSONA_ROW, _SUCCESSION_WITH_IMMEDIATE])
        result = asyncio.run(resolve_listener_context(db, _PERSONA_ID, _BENEFICIARY_ID))
        assert result is not None
        assert result.closeness_level is None
        assert result.greeting_style is None


# ═══════════════════════════════════════════════════════════════════════════════
# build_system_prompt — listener context injection
# ═══════════════════════════════════════════════════════════════════════════════

def _make_persona():
    from models.persona import Persona
    return Persona(
        id="p1",
        user_id=_OWNER_ID,
        name="Gran",
        stories=[],
        personality_traits=["warm"],
        speaking_style="gentle",
    )

_MODALITIES_FULL = ModalityConsent(voice_clone=True, video_avatar=True, text_twin=True)

_OWNER_CTX = ListenerContext(
    listener_user_id=_OWNER_ID,
    is_owner=True,
    allowed_modalities=_MODALITIES_FULL,
)

_BENEFICIARY_CTX = ListenerContext(
    listener_user_id=_BENEFICIARY_ID,
    is_owner=False,
    relationship="daughter",
    address_term="kiddo",
    scope="full",
    allowed_modalities=_MODALITIES_FULL,
)

_BENEFICIARY_CTX_MINIMAL = ListenerContext(
    listener_user_id=_BENEFICIARY_ID,
    is_owner=False,
    relationship="son",
    allowed_modalities=_MODALITIES_FULL,
)

_BENEFICIARY_CTX_ENRICHED = ListenerContext(
    listener_user_id=_BENEFICIARY_ID,
    is_owner=False,
    relationship="daughter",
    address_term="kiddo",
    closeness_level=4,
    greeting_style="warm and affectionate",
    scope="full",
    allowed_modalities=_MODALITIES_FULL,
)


class TestBuildSystemPromptListenerInjection:

    def _base_prompt(self):
        """Baseline prompt with no listener_ctx for comparison."""
        return build_system_prompt(_make_persona(), [])

    def test_no_listener_ctx_unchanged(self):
        assert build_system_prompt(_make_persona(), []) == self._base_prompt()

    def test_owner_ctx_unchanged(self):
        # is_owner=True → no listener block, identical to no-ctx output
        result = build_system_prompt(_make_persona(), [], listener_ctx=_OWNER_CTX)
        assert result == self._base_prompt()

    def test_beneficiary_ctx_adds_listener_block(self):
        result = build_system_prompt(_make_persona(), [], listener_ctx=_BENEFICIARY_CTX)
        assert "LISTENER CONTEXT:" in result
        assert "daughter" in result
        assert '"kiddo"' in result
        assert "full" in result
        assert "Do not infer listener identity" in result

    def test_beneficiary_ctx_does_not_alter_persona_block(self):
        # Core persona identity must be unchanged even with listener block
        base = self._base_prompt()
        result = build_system_prompt(_make_persona(), [], listener_ctx=_BENEFICIARY_CTX)
        assert result.startswith(base)

    def test_beneficiary_ctx_minimal_no_address_or_scope(self):
        # address_term=None, scope=None → those lines omitted, no KeyError
        result = build_system_prompt(_make_persona(), [], listener_ctx=_BENEFICIARY_CTX_MINIMAL)
        assert "LISTENER CONTEXT:" in result
        assert "son" in result
        assert "kiddo" not in result   # address_term absent → not injected
        assert "scope" not in result.lower().split("listener")[1]  # scope line absent

    def test_enriched_ctx_includes_closeness_and_greeting_style(self):
        # closeness_level + greeting_style present → both appear in listener block
        result = build_system_prompt(_make_persona(), [], listener_ctx=_BENEFICIARY_CTX_ENRICHED)
        assert "Closeness level: 4/5" in result
        assert "warm and affectionate" in result

    def test_anti_fabrication_instruction_present_for_beneficiary(self):
        # Anti-fabrication guardrail must appear whenever a listener block is injected
        result = build_system_prompt(_make_persona(), [], listener_ctx=_BENEFICIARY_CTX)
        assert "Do not assert shared memories" in result

    def test_owner_ctx_has_no_anti_fabrication_listener_block(self):
        # Owner path → no listener block at all → anti-fabrication line absent
        result = build_system_prompt(_make_persona(), [], listener_ctx=_OWNER_CTX)
        assert "LISTENER CONTEXT:" not in result
        assert "Do not assert shared memories" not in result
