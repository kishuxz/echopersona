"""Tests for Persona Style Card → build_system_prompt injection (roadmap Phase 2, Slice 1).

Coverage:
  - tone instruction appears when set; absent when empty
  - avoid_phrases appear as soft guidance
  - answer_length_pref injected when set; absent when empty
  - relationship_tone overrides base tone for a matching listener relationship
  - relationship_tone non-match leaves base tone unchanged
  - anti-fabrication instruction survives all style card additions

No DB calls — build_system_prompt is tested in isolation.
"""
from models.consent import ListenerContext, ModalityConsent
from models.persona import Persona
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
