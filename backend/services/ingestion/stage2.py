"""Stage 2: persona-conditioned first-person transform.

For each episode from Stage 1, calls Groq to:
  - Rewrite to first-person (if not already)
  - Extract stance, affect (emotion/valence/intensity), themes, entities

Returns a list of dicts ready to be inserted into memory_units.
"""
import json
import logging

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from config import settings

logger = logging.getLogger(__name__)

_GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
_TRANSFORM_MODEL = "llama-3.1-8b-instant"

_MEMORY_CATEGORIES = frozenset({
    "episodic", "semantic", "procedural", "relational",
    "values", "humor", "advice",
})

_SYSTEM_PROMPT = """\
You are a persona memory analyst. Given a memory episode and context about the person, \
transform it into a structured first-person memory unit.

Return a JSON object with exactly these fields:
{
  "content_first_person": "The memory in natural first-person voice. If already first-person, preserve it. If third-person, rewrite to first-person. Keep it authentic.",
  "memory_category": "one of: episodic | semantic | procedural | relational | values | humor | advice",
  "stance": "Overall emotional stance, e.g. nostalgic, proud, wistful, regretful, joyful (one or two words)",
  "affect": {
    "emotion": "primary emotion label",
    "valence": 0.5,
    "intensity": 0.7
  },
  "themes": ["family", "childhood"],
  "entities": {
    "people": ["Name1", "Name2"],
    "places": ["Place1"],
    "period": "approximate time period, e.g. 1960s or summer of 1978 or early childhood"
  }
}

memory_category rules:
  episodic   — a specific event or experience ("The day my father...")
  semantic   — a general belief or world view ("I always believed...")
  procedural — a ritual, habit, or skill ("Every Sunday I would...")
  relational — about a specific person and what they mean ("My sister was...")
  values     — core convictions or principles ("What mattered most to me...")
  humor      — a joke, funny story, or running gag ("We used to laugh about...")
  advice     — wisdom they would pass on ("Here is what I would tell you...")

valence: -1.0 (very negative) to 1.0 (very positive).
intensity: 0.0 (mild) to 1.0 (overwhelming).
Keep content_first_person faithful — do not add events or emotions not in the source.\
"""


def _is_429(exc: BaseException) -> bool:
    return isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429


def _mock_unit(episode: dict, source_meta: dict) -> dict:
    return {
        "content_first_person": episode["episode_text"],
        "memory_category": "episodic",
        "stance": "reflective",
        "affect": {"emotion": "nostalgic", "valence": 0.5, "intensity": 0.4},
        "themes": ["memory"],
        "entities": {"people": [], "places": [], "period": ""},
    }


@retry(
    retry=retry_if_exception(_is_429),
    wait=wait_exponential(multiplier=1, min=4, max=60),
    stop=stop_after_attempt(4),
)
async def _call_groq(user_message: str) -> dict:
    payload = {
        "model": _TRANSFORM_MODEL,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "max_tokens": 2048,
        "temperature": 0.2,
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
    return json.loads(resp.json()["choices"][0]["message"]["content"])


def _build_user_message(episode: dict, source_meta: dict) -> str:
    parts = []
    if source_meta.get("question_category"):
        parts.append(f"Memory category: {source_meta['question_category']}")
    if source_meta.get("question_text"):
        parts.append(f"Prompt question: {source_meta['question_text']}")
    if source_meta.get("group_name"):
        parts.append(f"Family group: {source_meta['group_name']}")
    parts.append(f"\nMemory text:\n{episode['episode_text']}")
    return "\n".join(parts)


def _coerce_unit(raw: dict) -> dict:
    """Normalize Groq output to expected shape. Invalid memory_category defaults to 'episodic'."""
    affect_raw = raw.get("affect") or {}
    affect = {
        "emotion": str(affect_raw.get("emotion", "")),
        "valence": float(affect_raw.get("valence", 0.0)),
        "intensity": float(affect_raw.get("intensity", 0.0)),
    }
    entities_raw = raw.get("entities") or {}
    entities = {
        "people": list(entities_raw.get("people") or []),
        "places": list(entities_raw.get("places") or []),
        "period": str(entities_raw.get("period", "")),
    }
    raw_category = str(raw.get("memory_category") or "").strip().lower()
    memory_category = raw_category if raw_category in _MEMORY_CATEGORIES else "episodic"
    return {
        "content_first_person": str(raw.get("content_first_person", "")).strip(),
        "memory_category": memory_category,
        "stance": str(raw.get("stance", "")).strip(),
        "affect": affect,
        "themes": list(raw.get("themes") or []),
        "entities": entities,
    }


async def transform_episode(episode: dict, source_meta: dict) -> dict:
    """Transform one episode into a memory unit dict (without DB ids).

    Returns keys: content_first_person, stance, affect, themes, entities.
    Falls back to a minimal unit if the LLM call fails.
    """
    if settings.mock_mode:
        return _mock_unit(episode, source_meta)

    try:
        user_message = _build_user_message(episode, source_meta)
        raw = await _call_groq(user_message)
        unit = _coerce_unit(raw)
        if not unit["content_first_person"]:
            raise ValueError("Empty content_first_person")
        logger.info("[Stage2] transformed episode (%d chars)", len(unit["content_first_person"]))
        return unit
    except Exception as exc:
        logger.warning("[Stage2] transform failed (%s), using raw episode text", exc)
        return _mock_unit(episode, source_meta)
