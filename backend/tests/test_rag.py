"""Tests for services/rag.py — affect tagging, prompt layer order, no-memory fallback.

Coverage:
  - _valence_label warm / somber / neutral
  - Affect tag rendering for units with full affect, missing affect key, missing primary_emotion
  - build_system_prompt: LISTENER CONTEXT appears before VOICE & STYLE (layer 3 before layer 4)
  - "1-2 sentences max" must NOT appear anywhere in the prompt (sentence cap moved to Layer 6)
  - RESPONSE RULES block with "1-3 sentences" must appear in Layer 6
  - No-memory fallback uses in-character phrase; old "being gathered" wording must be gone
  - build_index_from_units: affect dict propagated correctly; missing affect key tolerated

All calls are pure in-process — no Supabase, no Groq, no FAISS, no network.
"""

import pytest

from models.persona import Persona
from models.consent import ListenerContext, ModalityConsent
from services.rag import PersonaRAG, build_system_prompt, _valence_label


# ── helpers ────────────────────────────────────────────────────────────────────

def _make_persona(
    *,
    name: str = "Gran",
    personality_traits: list[str] | None = None,
    speaking_style: str = "gentle",
    voice_card: dict | None = None,
    tone: str = "",
) -> Persona:
    return Persona(
        id="p1",
        user_id="owner-1",
        name=name,
        stories=[],
        personality_traits=personality_traits or ["warm"],
        speaking_style=speaking_style,
        voice_card=voice_card or {},
        tone=tone,
    )


def _make_unit(text: str, affect: dict | None = None, *, include_affect_key: bool = True) -> dict:
    """Build a memory unit dict. If include_affect_key=False, the 'affect' key is omitted entirely."""
    u: dict = {"text": text}
    if include_affect_key:
        u["affect"] = affect if affect is not None else {}
    return u


_MODALITIES = ModalityConsent(voice_clone=True, video_avatar=True, text_twin=True)

_BENEFICIARY_CTX = ListenerContext(
    listener_user_id="ben-1",
    is_owner=False,
    relationship="daughter",
    address_term="kiddo",
    scope="full",
    allowed_modalities=_MODALITIES,
)

_VOICE_CARD = {
    "formality": "informal",
    "address_terms": ["dear"],
    "catchphrases": [],
    "humor_style": "dry wit",
    "sentence_rhythm": "short bursts",
    "emotional_tone": "warm",
    "advice_style": "",
    "verbal_tics": [],
}


# ══════════════════════════════════════════════════════════════════════════════
# Group A1 — _valence_label helper (pure unit)
# ══════════════════════════════════════════════════════════════════════════════

class TestValenceLabel:

    def test_positive_valence_returns_warm(self):
        assert _valence_label(0.7) == "warm"

    def test_boundary_positive_returns_warm(self):
        # strictly greater than 0.3
        assert _valence_label(0.31) == "warm"

    def test_negative_valence_returns_somber(self):
        assert _valence_label(-0.5) == "somber"

    def test_boundary_negative_returns_somber(self):
        # strictly less than -0.3
        assert _valence_label(-0.31) == "somber"

    def test_neutral_band_returns_neutral(self):
        assert _valence_label(0.1) == "neutral"

    def test_exact_zero_returns_neutral(self):
        assert _valence_label(0.0) == "neutral"

    def test_none_returns_neutral(self):
        assert _valence_label(None) == "neutral"


# ══════════════════════════════════════════════════════════════════════════════
# Group A2 — affect tag rendering in build_system_prompt
# ══════════════════════════════════════════════════════════════════════════════

class TestAffectTagRendering:

    def test_affect_tag_warm(self):
        """Unit with joy/valence 0.7 → memory line contains [joy, warm]."""
        unit = _make_unit("I used to love dancing", affect={"primary_emotion": "joy", "valence": 0.7})
        prompt = build_system_prompt(_make_persona(), [unit])
        assert "[joy, warm]" in prompt

    def test_affect_tag_somber(self):
        """Unit with grief/valence -0.5 → memory line contains [grief, somber]."""
        unit = _make_unit("I lost my mother young", affect={"primary_emotion": "grief", "valence": -0.5})
        prompt = build_system_prompt(_make_persona(), [unit])
        assert "[grief, somber]" in prompt

    def test_affect_tag_neutral(self):
        """Unit with calm/valence 0.1 → memory line contains [calm, neutral]."""
        unit = _make_unit("I worked at the bank for thirty years", affect={"primary_emotion": "calm", "valence": 0.1})
        prompt = build_system_prompt(_make_persona(), [unit])
        assert "[calm, neutral]" in prompt

    def test_affect_tag_missing_affect_key(self):
        """Legacy unit with NO 'affect' key → raw text only, no brackets, no crash."""
        unit = _make_unit("I grew up in Chennai", include_affect_key=False)
        prompt = build_system_prompt(_make_persona(), [unit])
        assert "I grew up in Chennai" in prompt
        # No bracket-enclosed tag should appear on that line
        assert "[" not in prompt.split("I grew up in Chennai")[0].split("\n")[-1]

    def test_affect_tag_missing_primary_emotion(self):
        """Unit with affect dict that has valence but no primary_emotion → raw text only."""
        unit = _make_unit("I baked bread every Sunday", affect={"valence": 0.6})
        prompt = build_system_prompt(_make_persona(), [unit])
        assert "I baked bread every Sunday" in prompt
        # No emotion bracket should precede the text on that memory line
        memory_line = [ln for ln in prompt.splitlines() if "I baked bread every Sunday" in ln][0]
        assert not memory_line.strip().startswith("[")


# ══════════════════════════════════════════════════════════════════════════════
# Group A3 — prompt layer order
# ══════════════════════════════════════════════════════════════════════════════

class TestPromptLayerOrder:

    def test_listener_before_voice_in_prompt(self):
        """LISTENER CONTEXT: (layer 3) must appear before VOICE & STYLE: (layer 4)."""
        persona = _make_persona(voice_card=_VOICE_CARD)
        prompt = build_system_prompt(persona, [], listener_ctx=_BENEFICIARY_CTX)
        assert "LISTENER CONTEXT:" in prompt, "LISTENER CONTEXT block missing"
        assert "VOICE & STYLE:" in prompt, "VOICE & STYLE block missing"
        assert prompt.index("LISTENER CONTEXT:") < prompt.index("VOICE & STYLE:")

    def test_sentence_cap_removed_from_layer1(self):
        """Layer 1 (identity) must NOT contain the old '1-2 sentences max' wording."""
        prompt = build_system_prompt(_make_persona(), [])
        assert "1-2 sentences max" not in prompt

    def test_sentence_cap_in_layer6(self):
        """RESPONSE RULES block (layer 6) must contain '1-3 sentences'."""
        prompt = build_system_prompt(_make_persona(), [])
        assert "RESPONSE RULES" in prompt
        # Find the RESPONSE RULES block and confirm the cap is there
        idx = prompt.index("RESPONSE RULES")
        tail = prompt[idx:]
        assert "1-3 sentences" in tail

    def test_response_rules_appears_after_voice_style_block(self):
        """RESPONSE RULES (layer 6) must appear after VOICE & STYLE (layer 4)."""
        persona = _make_persona(voice_card=_VOICE_CARD)
        prompt = build_system_prompt(persona, [])
        assert "VOICE & STYLE:" in prompt
        assert "RESPONSE RULES" in prompt
        assert prompt.index("VOICE & STYLE:") < prompt.index("RESPONSE RULES")


# ══════════════════════════════════════════════════════════════════════════════
# Group A4 — no-memory fallback (in-character wording)
# ══════════════════════════════════════════════════════════════════════════════

class TestNoMemoryFallback:

    def test_no_memory_fallback_in_character_phrase_present(self):
        """When no units retrieved, fallback must include the in-character placeholder phrase."""
        prompt = build_system_prompt(_make_persona(), [])
        assert "That's not something I can quite place right now" in prompt

    def test_no_memory_fallback_no_being_gathered_wording(self):
        """Old 'being gathered' wording (pre-fix) must not appear in the prompt."""
        prompt = build_system_prompt(_make_persona(), [])
        assert "being gathered" not in prompt

    def test_no_memory_fallback_no_ready_soon_wording(self):
        """Old 'ready soon' wording must not appear in the prompt."""
        prompt = build_system_prompt(_make_persona(), [])
        assert "ready soon" not in prompt

    def test_no_memory_fallback_absent_when_units_present(self):
        """Fallback phrase must NOT appear when memories are retrieved."""
        unit = _make_unit("I lived in Chennai for decades", affect={"primary_emotion": "nostalgia", "valence": 0.4})
        prompt = build_system_prompt(_make_persona(), [unit])
        assert "That's not something I can quite place right now" not in prompt

    def test_no_memory_fallback_includes_anti_fabrication_guard(self):
        """Fallback block must instruct the model not to fabricate or use outside knowledge."""
        prompt = build_system_prompt(_make_persona(), [])
        assert "Do not fabricate" in prompt


# ══════════════════════════════════════════════════════════════════════════════
# Group B — build_index_from_units: affect propagation
# ══════════════════════════════════════════════════════════════════════════════

class TestBuildIndexFromUnits:

    def test_build_index_propagates_affect(self):
        """Affect dict from the raw unit must be stored on the indexed unit."""
        rag = PersonaRAG()
        rag.build_index_from_units([
            {
                "content_first_person": "I grew up in Chennai",
                "affect": {"primary_emotion": "nostalgia", "valence": 0.4},
            }
        ])
        assert len(rag._units) == 1
        assert rag._units[0]["affect"] == {"primary_emotion": "nostalgia", "valence": 0.4}

    def test_build_index_tolerates_missing_affect(self):
        """Unit with no 'affect' key must not raise; stored affect must be empty dict."""
        rag = PersonaRAG()
        rag.build_index_from_units([
            {"content_first_person": "I loved the monsoon season"}
        ])
        assert len(rag._units) == 1
        assert rag._units[0]["affect"] == {}

    def test_build_index_tolerates_none_affect(self):
        """Unit with affect=None must not raise; stored affect must be empty dict."""
        rag = PersonaRAG()
        rag.build_index_from_units([
            {"content_first_person": "Sunday mornings were peaceful", "affect": None}
        ])
        assert len(rag._units) == 1
        assert rag._units[0]["affect"] == {}

    def test_build_index_skips_empty_content(self):
        """Units with empty or whitespace-only content_first_person must be skipped."""
        rag = PersonaRAG()
        rag.build_index_from_units([
            {"content_first_person": "   "},
            {"content_first_person": "I grew up in Madurai", "affect": {"primary_emotion": "pride", "valence": 0.6}},
        ])
        assert len(rag._units) == 1
        assert "Madurai" in rag._units[0]["text"]

    def test_build_index_multiple_units_affect_order_preserved(self):
        """Multiple units with different affects must be stored in order with correct affects."""
        rag = PersonaRAG()
        rag.build_index_from_units([
            {"content_first_person": "I loved to sing", "affect": {"primary_emotion": "joy", "valence": 0.8}},
            {"content_first_person": "I missed my father", "affect": {"primary_emotion": "grief", "valence": -0.6}},
        ])
        assert rag._units[0]["affect"]["primary_emotion"] == "joy"
        assert rag._units[1]["affect"]["primary_emotion"] == "grief"
