"""Stage 4: style exemplar bank + voice card (primary path) and Phase 2 style card.

Primary path (extract_style_exemplars): extracts style_exemplars and a structured
voice_card from memory units in a single Groq call. voice_card is stored as JSONB
on the persona and consumed by build_system_prompt (migration 008).

Secondary path (extract_style_card): extracts Phase 2 flat style fields
(tone, avoid_phrases, answer_length_pref, relationship_tone) used by the
relationship-aware prompt and the update_style_card write-back (migration 007).

Both paths prefer audio/video transcripts, which preserve natural spoken voice.
"""
import json
import logging

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from config import settings

logger = logging.getLogger(__name__)

_GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
_MODEL = "llama-3.1-8b-instant"
_TARGET_EXEMPLARS = 6
_FORMALITY_VALUES = {"formal", "warm-casual", "casual", "informal"}
_VALID_LENGTH_PREFS = {"brief", "moderate", "expansive"}

_SAFE_DEFAULTS: dict = {
    "style_exemplars": [],
    "tone": "",
    "avoid_phrases": [],
    "answer_length_pref": "moderate",
    "relationship_tone": {},
}

# ── Primary: voice card extraction prompt ────────────────────────────────────

_VOICE_CARD_SYSTEM_PROMPT = """\
You are a speech style analyst. Given first-person memory texts written or spoken \
by one person, extract their characteristic speech style in a single JSON object.

Return ONLY this JSON structure:
{
  "exemplars": [
    "Verbatim or near-verbatim short excerpt (1-3 sentences) capturing their voice.",
    "..."
  ],
  "voice_card": {
    "catchphrases": ["signature phrase they often use", "..."],
    "address_terms": ["how they address others, e.g. buddy, sweetheart", "..."],
    "humor_style": "brief description of their humor style",
    "sentence_rhythm": "brief description of their sentence structure and cadence",
    "emotional_tone": "brief description of their typical emotional register",
    "advice_style": "brief description of how they give advice or guidance",
    "verbal_tics": ["filler word or habitual expression", "..."],
    "formality": "formal|warm-casual|casual|informal"
  }
}

Rules for exemplars:
- Extract 5-8 verbatim or near-verbatim excerpts from the provided texts only.
- Choose excerpts that show distinctive vocabulary, idioms, emotional openness, or sentence rhythm.
- Prefer spoken/conversational passages. Do NOT invent or paraphrase beyond light punctuation fixes.

Rules for voice_card:
- Describe HOW they speak based ONLY on the provided texts. Do NOT infer facts about their life.
- Use empty string "" or empty list [] for any field not evident in the texts.
- formality must be exactly one of: formal, warm-casual, casual, informal.\
"""

# ── Secondary: Phase 2 flat style card prompt ────────────────────────────────

_STYLE_CARD_SYSTEM_PROMPT = """\
You are a speech style analyst. Given first-person memory texts written or spoken \
by one person, analyse their voice and communication patterns.

Return a JSON object with EXACTLY these keys:
{
  "exemplars": [
    "Verbatim or near-verbatim characteristic excerpt.",
    ...
  ],
  "tone": "<3-8 word phrase describing the dominant emotional tone, e.g. 'warm and nostalgic'>",
  "avoid_phrases": ["expression1", "expression2"],
  "answer_length_pref": "<one of: brief | moderate | expansive>",
  "relationship_tone": {
    "<relationship label>": "<tone override for that relationship>"
  }
}

Rules:
- exemplars: 5-8 verbatim or near-verbatim excerpts showing distinctive vocabulary and cadence.
- tone: leave as empty string if unclear.
- avoid_phrases: up to 5 expressions the person visibly dislikes or never uses. Empty list if none apparent.
- answer_length_pref: infer from typical response length. Default to "moderate" if unclear.
- relationship_tone: only include relationships explicitly mentioned in the texts. Use {} if none.
- Prefer spoken/conversational passages over formal writing.
- Do NOT invent or paraphrase beyond light punctuation fixes.\
"""


def _is_429(exc: BaseException) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429


def _select_source_units(units: list[dict]) -> list[dict]:
    """Prioritise audio/video units (they capture real spoken voice)."""
    spoken: list[dict] = []
    written: list[dict] = []
    for u in units:
        src = u.get("source") or {}
        modality = (src.get("modality") or "").lower()
        if modality in ("audio", "video"):
            spoken.append(u)
        else:
            written.append(u)
    return spoken[:10] + written[:5]


def _build_corpus(units: list[dict]) -> str:
    parts = []
    for i, u in enumerate(units, 1):
        text = (u.get("content_first_person") or "").strip()
        if text:
            parts.append(f"[{i}] {text}")
    return "\n\n".join(parts)


# ── Primary: voice card helpers ──────────────────────────────────────────────

def _coerce_voice_card(raw: dict) -> dict:
    """Validate and default all voice_card fields from raw LLM output."""
    def _str_list(val, max_items: int = 5, max_len: int = 60) -> list[str]:
        if not isinstance(val, list):
            return []
        return [str(s)[:max_len].strip() for s in val if s][:max_items]

    def _str_field(val, max_len: int = 120) -> str:
        if not isinstance(val, str):
            return ""
        return val[:max_len].strip()

    formality = _str_field(raw.get("formality"))
    if formality not in _FORMALITY_VALUES:
        formality = "warm-casual"

    return {
        "catchphrases": _str_list(raw.get("catchphrases"), max_items=3),
        "address_terms": _str_list(raw.get("address_terms"), max_items=5),
        "humor_style": _str_field(raw.get("humor_style")),
        "sentence_rhythm": _str_field(raw.get("sentence_rhythm")),
        "emotional_tone": _str_field(raw.get("emotional_tone")),
        "advice_style": _str_field(raw.get("advice_style")),
        "verbal_tics": _str_list(raw.get("verbal_tics"), max_items=5),
        "formality": formality,
    }


def _mock_voice_card() -> dict:
    return {
        "catchphrases": [],
        "address_terms": [],
        "humor_style": "",
        "sentence_rhythm": "",
        "emotional_tone": "",
        "advice_style": "",
        "verbal_tics": [],
        "formality": "warm-casual",
    }


def _mock_exemplars(units: list[dict]) -> list[str]:
    selected = _select_source_units(units)[:_TARGET_EXEMPLARS]
    return [
        (u.get("content_first_person") or "")[:150].strip()
        for u in selected
        if u.get("content_first_person")
    ]


# ── Secondary: Phase 2 style card helpers ────────────────────────────────────

def _parse_style_card(raw: dict) -> dict:
    """Parse and validate raw LLM JSON into a style card dict with safe defaults."""
    exemplars = [str(e).strip() for e in (raw.get("exemplars") or []) if e]

    tone = raw.get("tone") or ""
    if not isinstance(tone, str):
        tone = ""
    tone = tone.strip()

    avoid_phrases_raw = raw.get("avoid_phrases") or []
    if not isinstance(avoid_phrases_raw, list):
        avoid_phrases_raw = []
    avoid_phrases = [
        str(p).strip() for p in avoid_phrases_raw if p and isinstance(p, str)
    ]

    answer_length_pref = raw.get("answer_length_pref") or "moderate"
    if (
        not isinstance(answer_length_pref, str)
        or answer_length_pref not in _VALID_LENGTH_PREFS
    ):
        answer_length_pref = "moderate"

    relationship_tone_raw = raw.get("relationship_tone") or {}
    if not isinstance(relationship_tone_raw, dict):
        relationship_tone_raw = {}
    relationship_tone = {
        str(k): str(v)
        for k, v in relationship_tone_raw.items()
        if k and v and isinstance(k, str) and isinstance(v, str)
    }

    return {
        "style_exemplars": exemplars[:_TARGET_EXEMPLARS],
        "tone": tone,
        "avoid_phrases": avoid_phrases[:5],
        "answer_length_pref": answer_length_pref,
        "relationship_tone": relationship_tone,
    }


def _mock_style_card(units: list[dict]) -> dict:
    selected = _select_source_units(units)[:_TARGET_EXEMPLARS]
    exemplars = [
        (u.get("content_first_person") or "")[:150].strip()
        for u in selected
        if u.get("content_first_person")
    ]
    return {
        "style_exemplars": exemplars,
        "tone": "",
        "avoid_phrases": [],
        "answer_length_pref": "moderate",
        "relationship_tone": {},
    }


# ── Groq callers ─────────────────────────────────────────────────────────────

@retry(
    retry=retry_if_exception(_is_429),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    stop=stop_after_attempt(4),
)
async def _call_groq(corpus: str) -> tuple[list[str], dict]:
    """Primary call: returns (exemplars, voice_card) for the voice card path."""
    payload = {
        "model": _MODEL,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _VOICE_CARD_SYSTEM_PROMPT},
            {"role": "user", "content": corpus[:10000]},
        ],
        "max_tokens": 1536,
        "temperature": 0.3,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            _GROQ_CHAT_URL,
            headers={
                "Authorization": f"Bearer {settings.groq_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
    data = json.loads(resp.json()["choices"][0]["message"]["content"])
    exemplars = [str(e).strip() for e in (data.get("exemplars") or []) if e]
    voice_card = _coerce_voice_card(data.get("voice_card") or {})
    return exemplars, voice_card


@retry(
    retry=retry_if_exception(_is_429),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    stop=stop_after_attempt(4),
)
async def _call_groq_style_card(corpus: str) -> dict:
    """Secondary call: returns parsed style card dict for the Phase 2 path."""
    payload = {
        "model": _MODEL,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _STYLE_CARD_SYSTEM_PROMPT},
            {"role": "user", "content": corpus[:10000]},
        ],
        "max_tokens": 1536,
        "temperature": 0.3,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            _GROQ_CHAT_URL,
            headers={
                "Authorization": f"Bearer {settings.groq_api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
    raw = json.loads(resp.json()["choices"][0]["message"]["content"])
    return _parse_style_card(raw)


# ── Public extraction functions ──────────────────────────────────────────────

async def extract_style_exemplars(units: list[dict]) -> tuple[list[str], dict]:
    """Return (exemplars, voice_card) extracted from the persona's memory units.

    Used by the enrichment worker to write style_exemplars + voice_card to the DB.
    Falls back to snippet exemplars and empty voice_card on any error.
    """
    if not units:
        return [], _mock_voice_card()

    if settings.mock_mode:
        return _mock_exemplars(units), _mock_voice_card()

    source_units = _select_source_units(units)
    if not source_units:
        logger.info("[Stage4] no suitable source units for style extraction")
        return [], _mock_voice_card()

    corpus = _build_corpus(source_units)
    try:
        exemplars, voice_card = await _call_groq(corpus)
        exemplars = exemplars[:_TARGET_EXEMPLARS]
        logger.info(
            "[Stage4] extracted %d exemplars, voice_card formality=%s",
            len(exemplars),
            voice_card.get("formality", ""),
        )
        return exemplars, voice_card
    except Exception as exc:
        logger.warning("[Stage4] style extraction failed (%s), using fallback", exc)
        return _mock_exemplars(units), _mock_voice_card()


async def extract_style_card(units: list[dict]) -> dict:
    """Return Phase 2 style card dict for the persona.

    Keys: style_exemplars, tone, avoid_phrases, answer_length_pref, relationship_tone.
    Used by update_style_card to write Phase 2 flat fields. Falls back to safe defaults.
    """
    if not units:
        return dict(_SAFE_DEFAULTS)

    if settings.mock_mode:
        return _mock_style_card(units)

    source_units = _select_source_units(units)
    if not source_units:
        logger.info("[Stage4] no suitable source units for style card extraction")
        return dict(_SAFE_DEFAULTS)

    corpus = _build_corpus(source_units)
    try:
        card = await _call_groq_style_card(corpus)
        logger.info(
            "[Stage4] extracted style card — %d exemplars, tone=%r, avoid=%d phrases",
            len(card["style_exemplars"]),
            card["tone"],
            len(card["avoid_phrases"]),
        )
        return card
    except Exception as exc:
        logger.warning("[Stage4] style card extraction failed (%s), using fallback", exc)
        return _mock_style_card(units)
