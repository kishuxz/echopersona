"""Stage 4B: identity card extraction.

Single bounded Groq call that reads verified memory units and produces a
structured identity_card JSON capturing WHO the persona IS — values, worldview,
role_identity, emotional_wiring, communication_style, life_philosophy.

Distinct from Stage 4A (voice_card) which captures HOW they speak.
Runs in arq worker only. Never called from the live reply path.
"""
import json
import logging
import re

import httpx

from config import settings
from services.groq_limiter import groq_acquire

logger = logging.getLogger(__name__)

_IDENTITY_CARD_SYSTEM_PROMPT = """You are an identity analyst. Given first-person memory texts written or spoken by one person, extract their core identity in a single JSON object.

Return ONLY this JSON structure — no prose, no markdown, no explanation:
{
  "values": ["core value 1", "core value 2", "core value 3"],
  "worldview": "one sentence describing how this person sees life or humanity",
  "role_identity": "one sentence: who they are in the world (e.g. parent, teacher, builder, keeper of stories)",
  "emotional_wiring": "one sentence: how they process and express emotion",
  "communication_style": "one sentence: how they prefer to speak and connect with others",
  "life_philosophy": "one sentence: the guiding principle or belief they live by"
}

Rules:
- Base ALL output ONLY on the provided texts. Do not infer or fabricate beyond what is written.
- values: list of 3 to 5 strings. Each value is a single word or very short phrase (e.g. "family first", "honest work", "curiosity"). Use empty list [] if values are not evident.
- worldview, role_identity, emotional_wiring, communication_style, life_philosophy: each must be a single sentence of 10-25 words. Use empty string "" if not clearly evident in the texts.
- Do not describe how they speak — that belongs to the voice card. Focus on who they ARE and what they BELIEVE.
- Do not include proper nouns (names of people or places) in any field.
- Output must be valid JSON parseable by Python json.loads(). No trailing commas. No comments."""

_IDENTITY_CATEGORIES = {"values", "semantic", "relational"}


def _mock_identity_card() -> dict:
    return {
        "values": [],
        "worldview": "",
        "role_identity": "",
        "emotional_wiring": "",
        "communication_style": "",
        "life_philosophy": "",
    }


def _coerce_identity_card(raw: dict) -> dict:
    """Validate and coerce LLM output into the identity_card schema."""

    def _str_field(val: object, max_len: int = 200) -> str:
        if not isinstance(val, str):
            return ""
        # Strip newlines to prevent prompt injection via LLM output
        return re.sub(r"[\r\n]+", " ", val).strip()[:max_len]

    def _values_field(val: object) -> list[str]:
        if not isinstance(val, list):
            return []
        result = []
        for item in val:
            if isinstance(item, str) and item.strip():
                # Strip newlines from each value item
                result.append(re.sub(r"[\r\n]+", " ", item).strip()[:40])
        return result[:5]

    return {
        "values": _values_field(raw.get("values")),
        "worldview": _str_field(raw.get("worldview")),
        "role_identity": _str_field(raw.get("role_identity")),
        "emotional_wiring": _str_field(raw.get("emotional_wiring")),
        "communication_style": _str_field(raw.get("communication_style")),
        "life_philosophy": _str_field(raw.get("life_philosophy")),
    }


def _select_identity_units(units: list[dict]) -> list[dict]:
    """Prioritise values/semantic/relational categories, then episodic. Cap at 15."""
    priority = [u for u in units if u.get("memory_category") in _IDENTITY_CATEGORIES]
    episodic = [u for u in units if u.get("memory_category") not in _IDENTITY_CATEGORIES]
    selected = (priority + episodic)[:15]
    return selected


def _build_corpus(units: list[dict]) -> str:
    parts = []
    for i, u in enumerate(units, 1):
        text = (u.get("content_first_person") or "").strip()
        if text:
            parts.append(f"[{i}] {text}")
    return "\n\n".join(parts)


async def extract_identity_card(units: list[dict]) -> dict:
    """Extract a structured identity_card from memory units.

    Returns a fully coerced dict with all 6 identity fields.
    Falls back to _mock_identity_card() on empty input, mock mode, or any error.
    """
    if not units or settings.mock_mode:
        return _mock_identity_card()

    selected = _select_identity_units(units)
    corpus = _build_corpus(selected)
    if not corpus.strip():
        return _mock_identity_card()

    corpus = corpus[:10000]

    payload = {
        "model": "llama-3.1-8b-instant",
        "messages": [
            {"role": "system", "content": _IDENTITY_CARD_SYSTEM_PROMPT},
            {"role": "user", "content": f"Memory texts:\n\n{corpus}"},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": 512,
        "temperature": 0.2,
    }

    try:
        await groq_acquire(interactive=False)
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.groq_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            resp.raise_for_status()
            raw_text = resp.json()["choices"][0]["message"]["content"]
            raw = json.loads(raw_text)
            return _coerce_identity_card(raw)
    except Exception as exc:
        logger.warning("[Stage4B] identity card extraction failed: %s", exc)
        return _mock_identity_card()
