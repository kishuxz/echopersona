"""Tests for voice_card extraction, coercion, system-prompt injection, and enrichment wiring.

Coverage:
  1. _coerce_voice_card: valid dict preserved
  2. _coerce_voice_card: missing fields default correctly
  3. _coerce_voice_card: unrecognised formality → warm-casual
  4. _coerce_voice_card: empty dict → all-default structure with all 8 keys
  5. _mock_voice_card: returns dict with all 8 required keys
  6. extract_style_exemplars: returns (list[str], dict) tuple with correct shapes
  7. extract_style_exemplars: voice_card parse failure → exemplars intact, voice_card fallback
  8. build_system_prompt: populated voice_card emits VOICE & STYLE block
  9. build_system_prompt: empty voice_card produces valid prompt with no crash
  10. enrich_persona: update_voice_card called with correct persona_id and non-None dict

All DB and LLM calls are mocked.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from models.persona import Persona
from services.ingestion.stage4 import _coerce_voice_card, _mock_voice_card, extract_style_exemplars
from services.rag import build_system_prompt
from worker.tasks.enrichment import enrich_persona

# ── helpers ───────────────────────────────────────────────────────────────────

_PERSONA_ID = "p-voice-001"

_FULL_VOICE_CARD = {
    "catchphrases": ["At the end of the day...", "Here's the thing..."],
    "address_terms": ["buddy", "sweetheart"],
    "humor_style": "dry wit with self-deprecation",
    "sentence_rhythm": "short declarative sentences; occasionally runs on when excited",
    "emotional_tone": "warm but direct",
    "advice_style": "asks questions first before offering opinions",
    "verbal_tics": ["you know?", "honestly"],
    "formality": "warm-casual",
}

_UNITS = [
    {"content_first_person": "I always say, at the end of the day, what matters is family."},
    {"content_first_person": "Here's the thing about growing up — you never stop."},
]


def _make_persona(voice_card: dict | None = None, style_exemplars: list[str] | None = None) -> Persona:
    return Persona(
        id="p1",
        user_id="u1",
        name="Gran",
        stories=[],
        personality_traits=["warm"],
        speaking_style="gentle",
        voice_card=voice_card or {},
        style_exemplars=style_exemplars or [],
    )


# ── 1. _coerce_voice_card: valid dict passes through unchanged ─────────────────

def test_coerce_voice_card_valid():
    result = _coerce_voice_card(_FULL_VOICE_CARD)
    assert result["catchphrases"] == _FULL_VOICE_CARD["catchphrases"]
    assert result["address_terms"] == _FULL_VOICE_CARD["address_terms"]
    assert result["humor_style"] == _FULL_VOICE_CARD["humor_style"]
    assert result["sentence_rhythm"] == _FULL_VOICE_CARD["sentence_rhythm"]
    assert result["emotional_tone"] == _FULL_VOICE_CARD["emotional_tone"]
    assert result["advice_style"] == _FULL_VOICE_CARD["advice_style"]
    assert result["verbal_tics"] == _FULL_VOICE_CARD["verbal_tics"]
    assert result["formality"] == "warm-casual"


# ── 2. _coerce_voice_card: missing fields default correctly ───────────────────

def test_coerce_voice_card_missing_fields():
    result = _coerce_voice_card({"formality": "casual"})
    assert result["catchphrases"] == []
    assert result["address_terms"] == []
    assert result["humor_style"] == ""
    assert result["sentence_rhythm"] == ""
    assert result["emotional_tone"] == ""
    assert result["advice_style"] == ""
    assert result["verbal_tics"] == []
    assert result["formality"] == "casual"


# ── 3. _coerce_voice_card: invalid formality → warm-casual ───────────────────

def test_coerce_voice_card_invalid_formality():
    result = _coerce_voice_card({"formality": "semi-formal"})
    assert result["formality"] == "warm-casual"


def test_coerce_voice_card_empty_formality():
    result = _coerce_voice_card({"formality": ""})
    assert result["formality"] == "warm-casual"


# ── 4. _coerce_voice_card: empty dict → all-default structure ────────────────

def test_coerce_voice_card_empty():
    result = _coerce_voice_card({})
    assert set(result.keys()) == {
        "catchphrases", "address_terms", "humor_style", "sentence_rhythm",
        "emotional_tone", "advice_style", "verbal_tics", "formality",
    }
    assert result["catchphrases"] == []
    assert result["verbal_tics"] == []
    assert result["humor_style"] == ""
    assert result["formality"] == "warm-casual"


# ── 5. _mock_voice_card: all 8 keys present ──────────────────────────────────

def test_mock_voice_card_shape():
    vc = _mock_voice_card()
    assert set(vc.keys()) == {
        "catchphrases", "address_terms", "humor_style", "sentence_rhythm",
        "emotional_tone", "advice_style", "verbal_tics", "formality",
    }
    assert isinstance(vc["catchphrases"], list)
    assert isinstance(vc["verbal_tics"], list)
    assert isinstance(vc["humor_style"], str)
    assert vc["formality"] == "warm-casual"


# ── 6. extract_style_exemplars returns (list[str], dict) with mock LLM ───────

def test_extract_style_exemplars_returns_tuple():
    llm_response = {
        "exemplars": ["At the end of the day, family is everything."],
        "voice_card": _FULL_VOICE_CARD,
    }
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": __import__("json").dumps(llm_response)}}]
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("services.ingestion.stage4.settings") as mock_settings, \
         patch("httpx.AsyncClient") as mock_client_cls:
        mock_settings.mock_mode = False
        mock_settings.groq_api_key = "test-key"
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        exemplars, voice_card = asyncio.run(extract_style_exemplars(_UNITS))

    assert isinstance(exemplars, list)
    assert len(exemplars) >= 1
    assert isinstance(voice_card, dict)
    assert "catchphrases" in voice_card
    assert "formality" in voice_card


# ── 7. extract_style_exemplars: voice_card parse failure → exemplars intact ──

def test_extract_style_exemplars_voice_card_parse_failure():
    # LLM returns valid exemplars but malformed voice_card (wrong types)
    llm_response = {
        "exemplars": ["Here's the thing about growing up."],
        "voice_card": {"formality": 12345, "catchphrases": "not-a-list"},
    }
    mock_resp = MagicMock()
    mock_resp.json.return_value = {
        "choices": [{"message": {"content": __import__("json").dumps(llm_response)}}]
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("services.ingestion.stage4.settings") as mock_settings, \
         patch("httpx.AsyncClient") as mock_client_cls:
        mock_settings.mock_mode = False
        mock_settings.groq_api_key = "test-key"
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_client

        exemplars, voice_card = asyncio.run(extract_style_exemplars(_UNITS))

    # Exemplars still returned
    assert len(exemplars) >= 1
    # voice_card coerced to defaults (not crashed)
    assert voice_card["formality"] == "warm-casual"   # 12345 → default
    assert voice_card["catchphrases"] == []            # "not-a-list" → []


# ── 8. build_system_prompt: populated voice_card emits VOICE & STYLE block ───

def test_build_system_prompt_with_voice_card():
    persona = _make_persona(voice_card=_FULL_VOICE_CARD)
    prompt = build_system_prompt(persona, [])
    assert "VOICE & STYLE:" in prompt
    assert "warm-casual" in prompt
    assert '"buddy"' in prompt
    assert '"At the end of the day..."' in prompt
    assert "dry wit" in prompt
    assert "warm but direct" in prompt
    assert '"you know?"' in prompt


# ── 9. build_system_prompt: empty voice_card → valid prompt, no crash ────────

def test_build_system_prompt_empty_voice_card():
    persona = _make_persona(voice_card={})
    prompt = build_system_prompt(persona, [])
    assert "Gran" in prompt
    assert "VOICE & STYLE:" not in prompt   # no block emitted for empty voice_card


def test_build_system_prompt_voice_card_and_exemplars_coexist():
    persona = _make_persona(
        voice_card=_FULL_VOICE_CARD,
        style_exemplars=["At the end of the day, family is everything."],
    )
    prompt = build_system_prompt(persona, [])
    assert "VOICE & STYLE:" in prompt
    assert "CHARACTERISTIC PHRASES:" in prompt
    # VOICE & STYLE appears before CHARACTERISTIC PHRASES
    assert prompt.index("VOICE & STYLE:") < prompt.index("CHARACTERISTIC PHRASES:")


# ── 10. enrich_persona: update_voice_card called with correct args ────────────

def test_enrichment_calls_update_voice_card():
    entity_graph = [{"canonical": "Mom", "type": "person", "aliases": [], "description": ""}]
    exemplars = ["Here's the thing about growing up."]
    voice_card = {**_mock_voice_card(), "formality": "casual"}

    _blank_identity = {"values": [], "worldview": "", "role_identity": "", "emotional_wiring": "", "communication_style": "", "life_philosophy": ""}

    with (
        patch("worker.tasks.enrichment.get_memory_units_for_persona", new_callable=AsyncMock,
              return_value=_UNITS),
        patch("worker.tasks.enrichment.build_entity_graph", new_callable=AsyncMock,
              return_value=entity_graph),
        patch("worker.tasks.enrichment.update_entity_graph", new_callable=AsyncMock),
        patch("worker.tasks.enrichment.extract_style_exemplars", new_callable=AsyncMock,
              return_value=(exemplars, voice_card)),
        patch("worker.tasks.enrichment.update_style_exemplars", new_callable=AsyncMock),
        patch("worker.tasks.enrichment.update_voice_card", new_callable=AsyncMock) as mock_uvc,
        patch("worker.tasks.enrichment.extract_identity_card", new_callable=AsyncMock, return_value=_blank_identity),
        patch("worker.tasks.enrichment.update_identity_card", new_callable=AsyncMock),
        patch("worker.tasks.enrichment.update_readiness_status", new_callable=AsyncMock),
        patch("worker.tasks.enrichment.RAG_INDICES", {}),
        patch("worker.tasks.enrichment.PERSONAS", {}),
    ):
        result = asyncio.run(enrich_persona({}, _PERSONA_ID))

    assert result["status"] == "done"
    assert result["exemplar_count"] == len(exemplars)
    assert "voice_card_populated" in result

    mock_uvc.assert_called_once()
    call_args = mock_uvc.call_args
    assert call_args.args[0] == _PERSONA_ID
    assert call_args.args[1] == voice_card
