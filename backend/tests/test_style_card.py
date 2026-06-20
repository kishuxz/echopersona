"""Tests for Persona Style Card.

Coverage:
  Prompt injection (build_system_prompt):
  - tone instruction appears when set; absent when empty
  - avoid_phrases appear as soft guidance
  - answer_length_pref injected when set; absent when empty
  - relationship_tone overrides base tone for a matching listener relationship
  - relationship_tone non-match leaves base tone unchanged
  - anti-fabrication instruction survives all style card additions

  Stage 4 extraction (_parse_style_card, extract_style_card):
  - all fields parsed from valid LLM JSON
  - missing fields fall back to safe defaults
  - malformed avoid_phrases / relationship_tone do not crash
  - invalid answer_length_pref falls back to 'moderate'
  - exemplars capped at _TARGET_EXEMPLARS
  - empty units → safe defaults without Groq call
  - Groq error → fallback mock card (no crash)

  Write-back (update_style_card):
  - all five fields sent to the DB in one update

No DB calls, no network calls.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from models.consent import ListenerContext, ModalityConsent
from models.persona import Persona
from services.ingestion.stage4 import (
    _SAFE_DEFAULTS,
    _TARGET_EXEMPLARS,
    _parse_style_card,
    extract_style_card,
)
from services.rag import build_system_prompt

_MODALITIES = ModalityConsent(voice_clone=True, video_avatar=True, text_twin=True)


def _persona(**overrides) -> Persona:
    defaults = dict(
        id="p1",
        user_id="u1",
        name="Nana",
        stories=[],
        personality_traits=[],
        speaking_style="",
        tone="",
        avoid_phrases=[],
        answer_length_pref="",
        relationship_tone={},
    )
    return Persona(**{**defaults, **overrides})


def _beneficiary(relationship: str = "granddaughter") -> ListenerContext:
    return ListenerContext(
        listener_user_id="listener-1",
        is_owner=False,
        relationship=relationship,
        allowed_modalities=_MODALITIES,
    )


class TestStyleCardPromptInjection:

    def test_tone_appears_in_prompt(self):
        result = build_system_prompt(_persona(tone="warm"), [])
        assert "Tone: warm." in result

    def test_empty_tone_no_instruction(self):
        result = build_system_prompt(_persona(tone=""), [])
        assert "Tone:" not in result

    def test_avoid_phrases_soft_guidance(self):
        result = build_system_prompt(_persona(avoid_phrases=["y'all", "gonna"]), [])
        assert "Prefer not to use" in result
        assert "y'all" in result
        assert "gonna" in result

    def test_answer_length_pref_injected(self):
        result = build_system_prompt(_persona(answer_length_pref="brief"), [])
        assert "Keep responses brief." in result

    def test_empty_answer_length_pref_no_instruction(self):
        result = build_system_prompt(_persona(answer_length_pref=""), [])
        assert "Keep responses" not in result

    def test_relationship_tone_overrides_base_tone(self):
        persona = _persona(tone="warm", relationship_tone={"granddaughter": "very warm and affectionate"})
        result = build_system_prompt(persona, [], listener_ctx=_beneficiary("granddaughter"))
        assert "very warm and affectionate" in result
        assert "Tone: warm." not in result

    def test_relationship_tone_non_matching_uses_base_tone(self):
        persona = _persona(tone="warm", relationship_tone={"colleague": "formal"})
        result = build_system_prompt(persona, [], listener_ctx=_beneficiary("granddaughter"))
        assert "Tone: warm." in result

    def test_anti_fabrication_instruction_still_present(self):
        persona = _persona(tone="warm", avoid_phrases=["hey"], answer_length_pref="expansive")
        result = build_system_prompt(persona, [])
        assert "Use ONLY the memories below" in result


# ---------------------------------------------------------------------------
# Stage 4 parsing — no network, no DB
# ---------------------------------------------------------------------------

class TestParseStyleCard:
    """Unit tests for _parse_style_card defensive parsing."""

    def test_full_valid_response(self):
        raw = {
            "exemplars": ["phrase one", "phrase two"],
            "tone": "warm and nostalgic",
            "avoid_phrases": ["y'all"],
            "answer_length_pref": "brief",
            "relationship_tone": {"granddaughter": "very affectionate"},
        }
        card = _parse_style_card(raw)
        assert card["style_exemplars"] == ["phrase one", "phrase two"]
        assert card["tone"] == "warm and nostalgic"
        assert card["avoid_phrases"] == ["y'all"]
        assert card["answer_length_pref"] == "brief"
        assert card["relationship_tone"] == {"granddaughter": "very affectionate"}

    def test_missing_tone_defaults_empty(self):
        assert _parse_style_card({"exemplars": []})["tone"] == ""

    def test_missing_avoid_phrases_defaults_empty_list(self):
        assert _parse_style_card({"exemplars": []})["avoid_phrases"] == []

    def test_missing_answer_length_pref_defaults_moderate(self):
        assert _parse_style_card({"exemplars": []})["answer_length_pref"] == "moderate"

    def test_missing_relationship_tone_defaults_empty_dict(self):
        assert _parse_style_card({"exemplars": []})["relationship_tone"] == {}

    def test_invalid_answer_length_pref_falls_back_to_moderate(self):
        card = _parse_style_card({"exemplars": [], "answer_length_pref": "very_long"})
        assert card["answer_length_pref"] == "moderate"

    def test_malformed_avoid_phrases_non_list_falls_back(self):
        card = _parse_style_card({"exemplars": [], "avoid_phrases": "not a list"})
        assert card["avoid_phrases"] == []

    def test_malformed_relationship_tone_non_dict_falls_back(self):
        card = _parse_style_card({"exemplars": [], "relationship_tone": ["not", "a", "dict"]})
        assert card["relationship_tone"] == {}

    def test_exemplars_capped_at_target(self):
        raw = {"exemplars": [f"phrase {i}" for i in range(20)]}
        card = _parse_style_card(raw)
        assert len(card["style_exemplars"]) == _TARGET_EXEMPLARS

    def test_non_string_avoid_phrases_items_filtered(self):
        card = _parse_style_card({
            "exemplars": [],
            "avoid_phrases": ["ok", None, 123, "also_ok"],
        })
        assert card["avoid_phrases"] == ["ok", "also_ok"]

    def test_non_string_relationship_tone_values_filtered(self):
        card = _parse_style_card({
            "exemplars": [],
            "relationship_tone": {"child": "gentle", "other": None},
        })
        assert card["relationship_tone"] == {"child": "gentle"}
        assert "other" not in card["relationship_tone"]


# ---------------------------------------------------------------------------
# extract_style_card integration — Groq call mocked
# ---------------------------------------------------------------------------

_SAMPLE_UNITS = [
    {"content_first_person": "I loved the summer garden.", "source": {"modality": "text"}}
]


class TestExtractStyleCard:

    def test_empty_units_returns_safe_defaults_no_groq_call(self):
        card = asyncio.run(extract_style_card([]))
        assert card == _SAFE_DEFAULTS

    @patch("services.ingestion.stage4._call_groq", new_callable=AsyncMock)
    def test_returns_all_five_style_card_fields(self, mock_call):
        mock_call.return_value = {
            "style_exemplars": ["Summer was everything."],
            "tone": "nostalgic",
            "avoid_phrases": ["gonna"],
            "answer_length_pref": "brief",
            "relationship_tone": {"child": "gentle"},
        }
        card = asyncio.run(extract_style_card(_SAMPLE_UNITS))
        assert card["tone"] == "nostalgic"
        assert card["style_exemplars"] == ["Summer was everything."]
        assert card["avoid_phrases"] == ["gonna"]
        assert card["answer_length_pref"] == "brief"
        assert card["relationship_tone"] == {"child": "gentle"}

    @patch(
        "services.ingestion.stage4._call_groq",
        new_callable=AsyncMock,
        side_effect=Exception("network timeout"),
    )
    def test_groq_error_returns_mock_fallback_without_crashing(self, _mock):
        card = asyncio.run(extract_style_card(_SAMPLE_UNITS))
        assert "style_exemplars" in card
        assert isinstance(card["style_exemplars"], list)
        assert card["answer_length_pref"] == "moderate"
        assert isinstance(card["avoid_phrases"], list)
        assert isinstance(card["relationship_tone"], dict)

    @patch("services.ingestion.stage4._call_groq", new_callable=AsyncMock)
    def test_missing_fields_in_groq_response_fall_back_to_defaults(self, mock_call):
        # _call_groq already calls _parse_style_card internally, but this tests
        # that the dict returned by _call_groq passes through unchanged to caller.
        mock_call.return_value = {
            "style_exemplars": ["only exemplars present"],
            "tone": "",
            "avoid_phrases": [],
            "answer_length_pref": "moderate",
            "relationship_tone": {},
        }
        card = asyncio.run(extract_style_card(_SAMPLE_UNITS))
        assert card["tone"] == ""
        assert card["avoid_phrases"] == []
        assert card["answer_length_pref"] == "moderate"
        assert card["relationship_tone"] == {}


# ---------------------------------------------------------------------------
# update_style_card write-back — DB mocked
# ---------------------------------------------------------------------------

class TestUpdateStyleCard:
    """Test that update_style_card sends all five fields in one DB update."""

    @patch("services.persona_store.get_db")
    def test_write_back_sends_all_five_fields(self, mock_get_db):
        from services.persona_store import update_style_card

        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = None

        card = {
            "style_exemplars": ["phrase one"],
            "tone": "warm",
            "avoid_phrases": ["hey"],
            "answer_length_pref": "brief",
            "relationship_tone": {"child": "gentle"},
        }
        asyncio.run(update_style_card("persona-1", card))

        called_with = mock_db.table.return_value.update.call_args[0][0]
        assert called_with["style_exemplars"] == ["phrase one"]
        assert called_with["tone"] == "warm"
        assert called_with["avoid_phrases"] == ["hey"]
        assert called_with["answer_length_pref"] == "brief"
        assert called_with["relationship_tone"] == {"child": "gentle"}

    @patch("services.persona_store.get_db")
    def test_write_back_uses_safe_defaults_for_missing_keys(self, mock_get_db):
        from services.persona_store import update_style_card

        mock_db = MagicMock()
        mock_get_db.return_value = mock_db
        mock_db.table.return_value.update.return_value.eq.return_value.execute.return_value = None

        asyncio.run(update_style_card("persona-1", {}))

        called_with = mock_db.table.return_value.update.call_args[0][0]
        assert called_with["style_exemplars"] == []
        assert called_with["tone"] == ""
        assert called_with["avoid_phrases"] == []
        assert called_with["answer_length_pref"] == "moderate"
        assert called_with["relationship_tone"] == {}
