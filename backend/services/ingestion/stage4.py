"""Stage 4: style exemplar bank + voice card.

Extracts 5-8 characteristic speech excerpts (style_exemplars) and a structured
voice_card from the persona's memory units in a single Groq call.
Prefers audio/video transcripts, which preserve natural spoken voice.
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

_SYSTEM_PROMPT = """\
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


@retry(
    retry=retry_if_exception(_is_429),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    stop=stop_after_attempt(4),
)
async def _call_groq(corpus: str) -> tuple[list[str], dict]:
    payload = {
        "model": _MODEL,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": corpus[:10000]},  # guard token limit
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


async def extract_style_exemplars(units: list[dict]) -> tuple[list[str], dict]:
    """Return (exemplars, voice_card) extracted from the persona's memory units.

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
