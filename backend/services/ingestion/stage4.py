"""Stage 4: persona style card extraction.

Extracts style exemplars plus tone, avoid_phrases, answer_length_pref, and
relationship_tone from the persona's memory units in a single Groq call.

All fields are stored on the persona record and consumed by build_system_prompt().
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
_VALID_LENGTH_PREFS = {"brief", "moderate", "expansive"}

_SAFE_DEFAULTS: dict = {
    "style_exemplars": [],
    "tone": "",
    "avoid_phrases": [],
    "answer_length_pref": "moderate",
    "relationship_tone": {},
}

_SYSTEM_PROMPT = """\
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


@retry(
    retry=retry_if_exception(_is_429),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    stop=stop_after_attempt(4),
)
async def _call_groq(corpus: str) -> dict:
    payload = {
        "model": _MODEL,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": corpus[:10000]},
        ],
        "max_tokens": 1024,
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


async def extract_style_card(units: list[dict]) -> dict:
    """Return a full style card dict for the persona.

    Keys: style_exemplars, tone, avoid_phrases, answer_length_pref, relationship_tone.
    Falls back to safe defaults on any error.
    """
    if not units:
        return dict(_SAFE_DEFAULTS)

    if settings.mock_mode:
        return _mock_style_card(units)

    source_units = _select_source_units(units)
    if not source_units:
        logger.info("[Stage4] no suitable source units for style extraction")
        return dict(_SAFE_DEFAULTS)

    corpus = _build_corpus(source_units)
    try:
        card = await _call_groq(corpus)
        logger.info(
            "[Stage4] extracted %d exemplars, tone=%r, avoid=%d phrases",
            len(card["style_exemplars"]),
            card["tone"],
            len(card["avoid_phrases"]),
        )
        return card
    except Exception as exc:
        logger.warning("[Stage4] style extraction failed (%s), using fallback", exc)
        return _mock_style_card(units)


async def extract_style_exemplars(units: list[dict]) -> list[str]:
    """Backward-compatible shim — returns only the exemplars list."""
    card = await extract_style_card(units)
    return card["style_exemplars"]
